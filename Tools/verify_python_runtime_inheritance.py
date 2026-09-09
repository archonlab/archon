#!/usr/bin/env python3
"""Regression gates for canonical ARCHON Python ownership and Search preflight."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Tools"
for value in (str(ROOT), str(TOOLS)):
    if value not in sys.path:
        sys.path.insert(0, value)

import archon_runtime_python as runtime_python
from Universe_Search import search_runtime_contract
from Universe_Search import universe_search_core as core
from Universe_Search import universe_search_v34_closed_research_cycle as cycle


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_macos_venv_symlink_identity(base: Path) -> str:
    venv_python = base / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(Path(sys.executable))
    clean_env = {
        key: value for key, value in os.environ.items()
        if key not in {
            runtime_python.ENV_NAME,
            runtime_python.PROPAGATED_ENV_NAME,
            runtime_python.SOURCE_ENV_NAME,
        }
    }
    with patch.object(runtime_python.sys, "executable", str(venv_python)), patch.object(runtime_python.sys, "frozen", False, create=True):
        selected = runtime_python.runtime_python_selection(base, environ=clean_env)
    require(selected.executable == str(venv_python), "venv symlink was dereferenced")
    require(selected.source == "inherited", "venv parent was not classified as inherited")
    require(selected.executable != str(venv_python.resolve()), "test did not distinguish venv from physical Python")
    return selected.executable


def test_precedence_and_environment() -> None:
    with tempfile.TemporaryDirectory(prefix="archon runtime precedence ") as raw:
        base = Path(raw)
        configured = base / "configured python"
        packaged = base / "Runtime" / "python" / "bin" / "python3"
        configured.write_bytes(b"configured")
        packaged.parent.mkdir(parents=True)
        packaged.write_bytes(b"packaged")
        selected = runtime_python.runtime_python_selection(base, environ={runtime_python.ENV_NAME: str(configured)})
        require(selected.executable == str(configured) and selected.source == "configured", "configured precedence failed")
        selected = runtime_python.runtime_python_selection(base, environ={})
        require(selected.executable == str(packaged) and selected.source == "packaged", "packaged precedence failed")
        original = {"VIRTUAL_ENV": "/tmp/example venv", "ARCHON_TEST_SENTINEL": "kept"}
        propagated = runtime_python.runtime_python_environment(base, original, selection=selected)
        require(propagated["VIRTUAL_ENV"] == original["VIRTUAL_ENV"], "VIRTUAL_ENV was discarded")
        require(propagated["ARCHON_TEST_SENTINEL"] == "kept", "base environment was replaced")
        require(propagated[runtime_python.PROPAGATED_ENV_NAME] == str(packaged), "runtime owner was not propagated")


def test_platform_command_construction(venv_python: str) -> None:
    with tempfile.TemporaryDirectory(prefix="archon windows path ") as raw:
        root = Path(raw) / "ARCHON With Spaces"
        win = list(runtime_python._candidate_paths(root, windows=True))
        require(win[0] == root / "Runtime" / "python" / "python.exe", "Windows runtime layout is invalid")
        command = [str(win[0]), str(root / "Tools" / "child.py"), "--value", "with spaces"]
        require(len(command) == 4 and command[0].endswith("python.exe"), "Windows command is not an argument array")

    env = {
        **os.environ,
        runtime_python.PROPAGATED_ENV_NAME: venv_python,
        runtime_python.SOURCE_ENV_NAME: "inherited",
    }
    with patch.dict(os.environ, env, clear=True):
        from archon_studio_runtime import StudioRuntimeBridge
        bridge = StudioRuntimeBridge(ROOT)
        embedded_search, _ = bridge._build_search_command({})
        require(embedded_search[0] == venv_python, "Embedded Search lost Studio interpreter")
        for key in ("search", "observer", "analyzer"):
            require(bridge.specs[key].command[0] == venv_python, f"{key} native launch lost Studio interpreter")
        diagnostics = bridge.diagnostics_payload()["python"]
        require(diagnostics["executable"] == venv_python, "Studio diagnostics report the wrong interpreter")
        require(diagnostics["runtime_source"] == "inherited", "Studio diagnostics omit runtime source")
        bridge.python_command = [sys.executable, "-S"]
        status, payload = bridge.start_engine("search", {"ui_mode": "embedded"})
        require(status == 500 and payload.get("error") == "search_runtime_dependency_missing",
                "Studio did not fail Search cleanly at dependency preflight")
        require(bridge.engines["search"].process is None, "Studio started Search after failed preflight")


def test_dependency_preflight_and_scientific_boundary() -> None:
    selected = runtime_python.runtime_python_selection(ROOT)
    passed = search_runtime_contract.preflight_search_dependencies(selected.command)
    require(passed["dependency"] == "numpy", "NumPy backend was not preflighted")
    try:
        search_runtime_contract.preflight_search_dependencies([selected.executable, "-S"])
    except search_runtime_contract.SearchDependencyError as exc:
        require(exc.dependency == "numpy", "missing dependency was misclassified")
        require("Universe Search cannot start" in str(exc), "dependency failure is not operator-readable")
    else:
        raise AssertionError("interpreter without site packages passed NumPy preflight")

    original_numpy = core._np
    original_backend = os.environ.get("ART_EVO_FIELD_BACKEND")
    try:
        core._np = None
        os.environ["ART_EVO_FIELD_BACKEND"] = "numpy"
        try:
            core.require_field_backend()
        except core.FieldBackendDependencyError:
            pass
        else:
            raise AssertionError("missing evaluator backend was not an infrastructure error")
    finally:
        core._np = original_numpy
        if original_backend is None:
            os.environ.pop("ART_EVO_FIELD_BACKEND", None)
        else:
            os.environ["ART_EVO_FIELD_BACKEND"] = original_backend

    probe_rule = core.make_random_rule(987654321)
    worker_args = (0, core.rule_to_dict(probe_rule), "balanced", None, None)
    with patch.object(cycle.base, "score_rule", side_effect=core.FieldBackendDependencyError("test dependency")):
        try:
            cycle.evaluate_one_worker(worker_args)
        except core.FieldBackendDependencyError:
            pass
        else:
            raise AssertionError("worker converted dependency failure into a candidate score")

    cycle_source = (ROOT / "Universe_Search" / "universe_search_v34_closed_research_cycle.py").read_text(encoding="utf-8")
    require("except base.FieldBackendError:" in cycle_source and "'evaluation_status': 'CANDIDATE_ERROR'" in cycle_source,
            "infrastructure/candidate failure boundary is missing")
    require("base.require_field_backend()" in cycle_source, "engine does not preflight before generations")


def test_no_studio_python_path_fallback() -> None:
    studio = (ROOT / "Tools" / "archon_studio_runtime.py").read_text(encoding="utf-8")
    launcher = (ROOT / "Universe_Search" / "search_launcher.py").read_text(encoding="utf-8")
    handoff = (ROOT / "Analyzer_next" / "adapters" / "observer" / "cohort_search_execution_handoff.py").read_text(encoding="utf-8")
    require('command = [sys.executable' not in studio + launcher + handoff, "Studio-owned launch still uses ad-hoc sys.executable")
    require('subprocess.Popen(["python3"' not in studio + launcher + handoff, "Studio-owned launch hardcodes python3")
    require("preflight_search_dependencies" in studio and "preflight_search_dependencies" in launcher,
            "Embedded and native Search do not share dependency preflight")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="archon mac venv ") as raw:
        venv_python = test_macos_venv_symlink_identity(Path(raw))
        test_platform_command_construction(venv_python)
    test_precedence_and_environment()
    test_dependency_preflight_and_scientific_boundary()
    test_no_studio_python_path_fallback()
    print("PASS: ARCHON Python runtime inheritance, macOS venv identity, dependency preflight, and Linux/Windows command construction")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)
