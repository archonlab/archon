#!/usr/bin/env python3
"""Fail-closed STUDIO20.5/WORLD1 cumulative release verifier."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WHITELIST = ROOT / "Release/STUDIO20.5/packaging_whitelist.txt"
INTEGRATION = ROOT / "Release/STUDIO20.5/studio_release_integration.json"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def run(*args: object, cwd: Path = ROOT, timeout: int = 300) -> str:
    result = subprocess.run([str(value) for value in args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    require(result.returncode == 0, result.stdout)
    return result.stdout


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from Universe_Search.search_runtime_contract import REQUIRED_RUNTIME_FILES

    run(sys.executable, "-B", ROOT / "Tools/verify_python_runtime_inheritance.py")
    run(sys.executable, "-B", ROOT / "Tools/verify_world1_portability.py")
    run(sys.executable, "-B", ROOT / "Tools/verify_ol2_ux_fix.py")
    run(sys.executable, "-B", ROOT / "Tools/verify_search_launcher_small_screen.py")
    run(sys.executable, "-B", ROOT / "Tools/verify_studio_real_search_release.py", timeout=300)
    for rel in [
        "Docs/Audits/2026-09-06/reproduce/test_source_tree_seal_policy.py",
        "Docs/Audits/2026-09-06/reproduce/test_mechanism_zero_values.py",
        "Docs/Audits/2026-09-06/reproduce/test_mechanism_scientific_semantics.py",
        "Docs/Audits/2026-09-06/reproduce/test_sciencefix2_value_semantics.py",
    ]:
        run(sys.executable, "-B", ROOT / rel)
    status = run(sys.executable, "-B", ROOT / "Analyzer_next/cli/observer_launcher_profile.py", "--profile-status")
    require("integrity=MODIFIED_SOURCE_TREE" in status, "modifiable source-tree warning policy regressed")
    headless = run(sys.executable, "-B", ROOT / "Analyzer_next/cli/observer_launcher_profile.py", "--headless-check")
    require('"active_profile": "ol2"' in headless, "Observer OL2 headless runtime regressed")

    listed = rows(WHITELIST)
    runtime_listed = set(rows(ROOT / "Release/STUDIO20.5/runtime_whitelist.txt"))
    require(listed == sorted(listed), "packaging whitelist is not sorted")
    require(len(listed) == len(set(listed)), "packaging whitelist contains duplicates")
    require(all((ROOT / rel).is_file() for rel in listed), "packaging whitelist references a missing file")
    require(set(REQUIRED_RUNTIME_FILES) <= set(listed), "canonical Search closure missing from packaging whitelist")
    require(set(REQUIRED_RUNTIME_FILES) <= runtime_listed, "canonical Search closure missing from runtime whitelist")
    for rel in listed:
        parts = Path(rel).parts
        require("__pycache__" not in parts and ".git" not in parts and ".agents" not in parts, f"development/cache leak: {rel}")
        require(not rel.endswith((".pyc", ".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz", ".archon-world")), f"generated/package leak: {rel}")
        require(not rel.startswith(("Artifacts/", "Results/", "Config/")), f"generated state leaked into release: {rel}")

    integration = json.loads(INTEGRATION.read_text(encoding="utf-8"))
    require(integration.get("studio_version") == "STUDIO20.5" and integration.get("status") == "PASS", "integration status mismatch")
    expected = {rel for rel in listed if rel != "Release/STUDIO20.5/studio_release_integration.json"}
    require(set(integration.get("file_hashes", {})) == expected, "release hash closure mismatch")
    for rel in expected:
        require(integration["file_hashes"][rel] == sha256(ROOT / rel), f"release hash mismatch: {rel}")

    dist = json.loads((ROOT / "Packaging/distribution_contract.json").read_text())
    win = json.loads((ROOT / "Packaging/windows/distribution.json").read_text())
    require(dist["studio_version"] == "STUDIO20.5" and dist["stage"]["whitelist"] == "Release/STUDIO20.5/packaging_whitelist.txt", "distribution contract stale")
    require(win["milestone"] == "STUDIO20.5" and win["whitelist"] == "Release/STUDIO20.5/packaging_whitelist.txt", "Windows contract stale")

    build = json.loads((ROOT / "archon-studio/dist/archon-studio-build.json").read_text())
    require(build["studio_version"] == "STUDIO20.5" and build["file_count"] == 6, "frontend production build receipt stale")
    recorded = {item["path"]: item for item in build["files"]}
    for rel in ("assets/world-portability.js", "assets/world-portability.css", "index.html", "manifest.json"):
        path = ROOT / "archon-studio/dist" / rel
        require(recorded[rel]["bytes"] == path.stat().st_size and recorded[rel]["sha256"] == sha256(path), f"frontend receipt mismatch: {rel}")
    source = (ROOT / "archon-studio/dist/assets/world-portability.js").read_text(encoding="utf-8")
    require("/import/inspect" in source and "/import-all/inspect" in source and "Export World" in source and "Open World" in source and "Export All Worlds" in source and "Import World Collection" in source, "WORLD1 Studio actions missing")

    with tempfile.TemporaryDirectory(prefix="archon-studio20.5-stage-") as raw:
        base = Path(raw)
        for platform in ("windows", "macos", "linux"):
            out = base / platform
            text = run(sys.executable, "-B", ROOT / "Tools/archon_distribution_stage.py", "--root", ROOT, "--platform", platform, "--output", out)
            require("PASS: STUDIO20.5" in text, f"{platform} stage milestone stale")
            manifest = json.loads((out / "DISTRIBUTION_STAGE.json").read_text())
            require(manifest["release_files"] == len(listed), f"{platform} stage count mismatch")
        win_out = base / "windows-exact"
        run(sys.executable, "-B", ROOT / "Tools/archon_windows_distribution.py", "stage", "--root", ROOT, "--output", win_out)
        run(sys.executable, "-B", ROOT / "Tools/archon_windows_distribution.py", "verify", "--output", win_out)

    run(sys.executable, "-B", ROOT / "Tools/verify_studio18_platform_portability.py")
    run(sys.executable, "-B", ROOT / "Tools/archon_studio_runtime.py", "--root", ROOT, "--self-test")
    run(sys.executable, "-B", ROOT / "Tools/archon_studio_desktop.py", "--root", ROOT, "--headless-smoke", "--port", "0")
    print(f"PASS: STUDIO20.5 WORLD1 stages {len(listed)} exact files for Linux, Windows and macOS with scientific and source-policy gates intact")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
