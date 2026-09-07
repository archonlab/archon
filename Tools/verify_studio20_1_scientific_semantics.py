#!/usr/bin/env python3
"""Fail-closed STUDIO20.1 scientific semantics and release-closure verifier."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WHITELIST = ROOT / "Release/STUDIO20.1/packaging_whitelist.txt"
INTEGRATION = ROOT / "Release/STUDIO20.1/studio_release_integration.json"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def rows(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def run(*args: str | Path, cwd: Path = ROOT) -> str:
    proc = subprocess.run(
        [str(x) for x in args], cwd=cwd, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
    )
    require(proc.returncode == 0, proc.stdout)
    return proc.stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    # The original audit reproducer must now pass unchanged.
    run(sys.executable, "-B", ROOT / "Docs/Audits/2026-09-06/reproduce/test_mechanism_zero_values.py")
    run(sys.executable, "-B", ROOT / "Docs/Audits/2026-09-06/reproduce/test_mechanism_scientific_semantics.py")

    source = (ROOT / "Analyzer_next/adapters/mechanism/file_repository.py").read_text(encoding="utf-8")
    require('collapse_tick in (None, "", 0)' not in source, "collapse tick zero is still treated as missing")
    require('profile.get("longest_age")\n                or profile.get("final_tick")' not in source,
            "zero lifetime is still replaced by final_tick")

    # Exercise the actual Mechanism CLI with an observed rule absent from Atlas.
    with tempfile.TemporaryDirectory(prefix="archon-studio20.1-no-atlas-") as raw:
        project = Path(raw)
        results = project / "Results/Universe_Search"
        results.mkdir(parents=True)
        (results / "observer_profiles_v30.json").write_text(json.dumps({"profiles": [{
            "rule": "00000", "collapse_tick": 0, "longest_age": 0, "final_tick": 256,
            "analyzer_category": "collapsed_world"
        }]}), encoding="utf-8")
        out = run(sys.executable, "-B", ROOT / "Analyzer_next/cli/mechanism_engine.py", results)
        require("DEFERRED: ATLAS_CONTEXT_UNAVAILABLE" in out, "Mechanism CLI did not expose Atlas deferral")
        payload = json.loads((results / "mechanism_report.json").read_text(encoding="utf-8"))
        require(payload["rules_failed"] == 0 and payload["rules_deferred"] == 1,
                "missing Atlas context is still a mechanism failure")
        require(payload["deferred"][0]["status"] == "ATLAS_CONTEXT_UNAVAILABLE",
                "missing Atlas context status mismatch")

    # Current release closure must be exact and self-consistent.
    listed = rows(WHITELIST)
    require(len(listed) == len(set(listed)), "STUDIO20.1 packaging whitelist contains duplicates")
    require(all((ROOT / rel).is_file() for rel in listed), "STUDIO20.1 whitelist references a missing file")
    integration = json.loads(INTEGRATION.read_text(encoding="utf-8"))
    require(integration["studio_version"] == "STUDIO20.1" and integration["status"] == "PASS",
            "STUDIO20.1 integration status mismatch")
    require(integration["counts"]["packaging_files"] == len(listed), "packaging count mismatch")
    hashes = integration["file_hashes"]
    expected_keys = {rel for rel in listed if rel != "Release/STUDIO20.1/studio_release_integration.json"}
    require(set(hashes) == expected_keys, "STUDIO20.1 hash closure mismatch")
    for rel in sorted(expected_keys):
        require(hashes[rel] == sha256(ROOT / rel), f"STUDIO20.1 integration hash mismatch: {rel}")

    # All three common staging targets must consume the fixed release closure.
    stage_builder = ROOT / "Tools/archon_distribution_stage.py"
    with tempfile.TemporaryDirectory(prefix="archon-studio20.1-stage-") as raw:
        base = Path(raw)
        for platform in ("windows", "macos", "linux"):
            output = base / platform
            text = run(sys.executable, "-B", stage_builder, "--root", ROOT, "--platform", platform, "--output", output)
            require("PASS: STUDIO20.1" in text, f"{platform} stage did not use STUDIO20.1")
            manifest = json.loads((output / "DISTRIBUTION_STAGE.json").read_text(encoding="utf-8"))
            require(manifest["studio_version"] == "STUDIO20.1", f"{platform} stage version mismatch")
            require(manifest["release_files"] == len(listed), f"{platform} stage file count mismatch")

    # Windows exact staging must also consume the same repaired closure.
    sys.path.insert(0, str(ROOT / "Tools"))
    from archon_windows_distribution import stage, verify  # type: ignore
    with tempfile.TemporaryDirectory(prefix="archon-studio20.1-windows-") as raw:
        output = Path(raw) / "stage"
        manifest = stage(ROOT, output)
        verify(output)
        require(manifest["milestone"] == "STUDIO20.1", "Windows distribution still targets old release closure")

    # Existing platform/runtime behavior remains alive.
    run(sys.executable, "-B", ROOT / "Tools/verify_studio18_platform_portability.py")
    run(sys.executable, "-B", ROOT / "Tools/archon_studio_runtime.py", "--root", ROOT, "--self-test")
    run(sys.executable, "-B", ROOT / "Tools/archon_studio_desktop.py", "--root", ROOT, "--headless-smoke", "--port", "0")

    print(
        f"PASS: STUDIO20.1 preserves zero-valued observation semantics, defers missing Atlas context without hiding corruption, "
        f"and stages {len(listed)} exact files for Windows/macOS/Linux"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
