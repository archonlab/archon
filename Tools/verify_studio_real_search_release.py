#!/usr/bin/env python3
"""Execute one genuine Universe Search generation through Studio in a clean stage."""
from __future__ import annotations

import collections
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def run(*args: object, cwd: Path = ROOT, timeout: int = 300) -> str:
    result = subprocess.run(
        [str(value) for value in args], cwd=cwd, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
    )
    require(result.returncode == 0, result.stdout)
    return result.stdout


def prepare_one_generation_checkpoint(stage: Path) -> None:
    """Prepare a normal resume input; do not modify staged application files."""
    old_cwd = Path.cwd()
    old_path = list(sys.path)
    try:
        os.chdir(stage)
        sys.path.insert(0, str(stage))
        from Universe_Search import search_job_loader
        from Universe_Search import universe_search_v34_closed_research_cycle as search

        config = search_job_loader.load_search_mode_config(
            project_root=stage, search_mode="ordinary", requested_score_mode="balanced",
        )
        search.save_checkpoint(
            search.GENERATIONS - 1, "balanced", [search.base.make_random_rule(1)],
            [], 2, 0, None, collections.deque(), [], config,
        )
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path


def main() -> int:
    platform_name = "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "linux")
    with tempfile.TemporaryDirectory(prefix="archon-studio-real-search-release-") as raw:
        stage = Path(raw) / "clean release"
        run(
            sys.executable, "-B", ROOT / "Tools/archon_distribution_stage.py",
            "--root", ROOT, "--platform", platform_name, "--output", stage,
        )
        manifest = json.loads((stage / "DISTRIBUTION_STAGE.json").read_text(encoding="utf-8"))
        require(manifest["runtime_mode"] == "source-runtime", "unexpected release runtime mode")
        require((stage / "Universe_Search/search_runtime_contract.py").is_file(), "shared Search runtime contract missing from release")
        prepare_one_generation_checkpoint(stage)

        sys.path.insert(0, str(stage / "Tools"))
        sys.path.insert(0, str(stage))
        from archon_studio_runtime import StudioRuntimeBridge

        bridge = StudioRuntimeBridge(stage)
        runtime = bridge.engines["search"]
        required_layer = stage / "Universe_Search/theory_engine.py"
        hidden_layer = required_layer.with_suffix(".py.missing")
        required_layer.replace(hidden_layer)
        try:
            refused_code, refused = bridge.start_engine("search", {
                "ui_mode": "embedded", "run_command": "resume",
                "score_mode": "balanced", "search_mode": "ordinary",
            })
            require(refused_code == 500 and refused.get("error") == "canonical_search_runtime_incomplete", "incomplete release did not fail closed")
            require(runtime.process is None, "incomplete release started a fallback process")
        finally:
            hidden_layer.replace(required_layer)

        command, clean = bridge._build_search_command({
            "ui_mode": "embedded", "run_command": "resume",
            "score_mode": "balanced", "search_mode": "ordinary",
        })
        require(Path(command[len(bridge.python_command) + 1]).resolve() == bridge.search_script, "Studio did not select canonical Search entrypoint")
        require(clean["run_command"] == "resume", "release probe did not use canonical resume")

        code, payload = bridge.start_engine("search", {
            "ui_mode": "embedded", "run_command": "resume",
            "score_mode": "balanced", "search_mode": "ordinary",
        })
        require(code == 200, str(payload))
        launched_pid = int(payload["engine"]["pid"])
        require(runtime.process is not None and runtime.process.pid == launched_pid, "no real Search process was launched")
        if os.name == "posix":
            os.kill(launched_pid, 0)

        saw_running_attestation = False
        deadline = time.monotonic() + 260.0
        try:
            while time.monotonic() < deadline:
                engine = bridge.payload()["engines"]["search"]
                live = engine["live"]
                if engine["status"] == "RUNNING" and live.get("process_attested"):
                    saw_running_attestation = live.get("source_pid") == launched_pid
                if engine["status"] not in {"RUNNING", "PAUSED"}:
                    break
                time.sleep(0.2)
            else:
                bridge.stop_engine("search")
                raise AssertionError("real Search release probe timed out")

            engine = bridge.payload()["engines"]["search"]
            live = engine["live"]
            require(saw_running_attestation, "telemetry was not bound to live Search PID")
            require(engine["status"] == "COMPLETE" and engine["exit_code"] == 0, f"real Search failed: {engine}")
            require(live.get("runtime_backend") == "canonical_universe_search_process", "non-canonical backend active")
            require(live.get("telemetry_source") == "process_stdout", "telemetry was not process-derived")
            require(live.get("process_attested") and live.get("completion_attested"), "process lifecycle was not attested")
            require(live.get("source_pid") == launched_pid, "telemetry PID mismatch")
            require(live.get("generation") == 8 and live.get("evaluated") == 1, "real generation progress missing")
            require(live.get("committed_generations") == [8] and live.get("artifact_verified"), "generation artifact not committed")

            artifact = (stage / str(live.get("artifact_path"))).resolve()
            artifact.relative_to((stage / "Results/Universe_Search").resolve())
            rows = json.loads(artifact.read_text(encoding="utf-8"))
            require(len(rows) == 1, "real generation output has wrong result count")
            require(isinstance(rows[0].get("rule"), dict) and isinstance(rows[0].get("metrics"), dict), "output is not a genuine Search result")
            require((stage / "Results/Universe_Search/checkpoint_observer_niches.json").is_file(), "checkpoint pipeline was not used")
            require((stage / "Atlas/Worlds/atlas_index.json").is_file(), "Atlas pipeline was not reached")
            combined = "\n".join(str(item.get("message") or "") for item in engine["events"]).lower()
            require("generation 8/8" in combined and "search complete." in combined, "real Search lifecycle missing")
            require(not any(token in combined for token in ("demo progress", "mock search", "simulated generation", "fake search")), "simulation path detected")
        finally:
            if runtime.process is not None and runtime.process.poll() is None:
                bridge.stop_engine("search")
            bridge.shutdown()

    print("PASS: clean staged Studio launched canonical Universe Search, observed PID-bound real generation telemetry, and verified a genuine result artifact; no simulation path was active")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
