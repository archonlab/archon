#!/usr/bin/env python3
"""Fail-closed STUDIO20.4 Search Launcher UX and cumulative release verifier."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "Universe_Search" / "search_launcher.py"
CORE = ROOT / "Universe_Search" / "universe_search_core.py"
CYCLE = ROOT / "Universe_Search" / "universe_search_v34_closed_research_cycle.py"
WHITELIST = ROOT / "Release" / "STUDIO20.4" / "packaging_whitelist.txt"
INTEGRATION = ROOT / "Release" / "STUDIO20.4" / "studio_release_integration.json"
CORE_SHA256 = "f2a715465c9506dc63a4317b3de22049f1c55719b2c87a7eacfb16a693ac871b"
CYCLE_SHA256 = "cd9374eea215a9bfe775fcf0383c1a3d7f4d8e00a0ea062b80d9fa0621ec2e81"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def run(*args: object, cwd: Path = ROOT, timeout: int = 240) -> str:
    result = subprocess.run([str(value) for value in args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    require(result.returncode == 0, result.stdout)
    return result.stdout


def load_launcher_module():
    spec = importlib.util.spec_from_file_location("archon_search_launcher_ux_test", LAUNCHER)
    require(spec is not None and spec.loader is not None, "cannot load Search Launcher module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_search_ux() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")
    require("messagebox.askyesno" not in source, "native locale-dependent askyesno remains")
    require("def ask_yes_no_english" in source, "English confirmation helper missing")
    require('text="Yes"' in source and 'text="No"' in source, "explicit English Yes/No labels missing")
    require("command=self._show_settings_dialog" in source, "Settings button is not wired to settings dialog")
    require("def _show_settings_dialog" in source, "Search settings dialog missing")
    require("_show_settings_info" not in source, "obsolete informational Settings handler remains")
    require("Follow Studio" in source and "confirm_close" in source, "launcher preference controls missing")

    module = load_launcher_module()
    args = module.build_arg_parser().parse_args([])
    require(args.theme == "auto", "Search Launcher still defaults to forced dark theme")

    with tempfile.TemporaryDirectory(prefix="archon-search-ux-") as raw:
        temp = Path(raw)
        module.SEARCH_LAUNCHER_SETTINGS = temp / "search_launcher_settings.json"
        module.STUDIO_SETTINGS = temp / "studio_settings.json"
        module.STUDIO_SETTINGS.write_text(json.dumps({"schema": "archon_studio_settings_v1", "settings": {"appearance": "light"}}), encoding="utf-8")
        require(module.resolve_launcher_theme("follow_studio") == "light", "light Studio theme is not inherited")
        module.STUDIO_SETTINGS.write_text(json.dumps({"schema": "archon_studio_settings_v1", "settings": {"appearance": "graphite"}}), encoding="utf-8")
        require(module.resolve_launcher_theme("follow_studio") == "dark", "graphite Studio theme must map to dark Search palette")
        require(module.resolve_launcher_theme("light") == "light", "explicit light preference ignored")
        require(module.resolve_launcher_theme("dark") == "dark", "explicit dark preference ignored")
        module.save_search_launcher_settings({"theme": "light", "confirm_close": False})
        restored = module.load_search_launcher_settings()
        require(restored == {"theme": "light", "confirm_close": False}, f"settings round-trip mismatch: {restored}")
        payload = json.loads(module.SEARCH_LAUNCHER_SETTINGS.read_text(encoding="utf-8"))
        require(payload.get("schema") == module.SEARCH_LAUNCHER_SETTINGS_SCHEMA, "settings schema missing")

    require(sha256(CORE) == CORE_SHA256, "Universe Search scientific core changed in UX-only milestone")
    require(sha256(CYCLE) == CYCLE_SHA256, "Universe Search cycle changed in UX-only milestone")


def main() -> int:
    verify_search_ux()

    # Preserve source-tree policy and scientific semantic gates without relying
    # on historical release hashes that intentionally predate STUDIO20.4.
    for rel in [
        "Docs/Audits/2026-09-06/reproduce/test_source_tree_seal_policy.py",
        "Docs/Audits/2026-09-06/reproduce/test_mechanism_zero_values.py",
        "Docs/Audits/2026-09-06/reproduce/test_mechanism_scientific_semantics.py",
        "Docs/Audits/2026-09-06/reproduce/test_sciencefix2_value_semantics.py",
    ]:
        run(sys.executable, "-B", ROOT / rel)
    status = run(sys.executable, "-B", ROOT / "Analyzer_next/cli/observer_launcher_profile.py", "--profile-status")
    require("integrity=MODIFIED_SOURCE_TREE" in status, "source-tree warning policy regressed")
    headless = run(sys.executable, "-B", ROOT / "Analyzer_next/cli/observer_launcher_profile.py", "--headless-check")
    require('"active_profile": "ol2"' in headless, "Observer OL2 headless runtime regressed")

    listed = rows(WHITELIST)
    require(len(listed) == len(set(listed)), "packaging whitelist duplicates")
    require(all((ROOT / rel).is_file() for rel in listed), "packaging whitelist references missing file")
    for rel in listed:
        parts = Path(rel).parts
        require("__pycache__" not in parts and ".git" not in parts and ".agents" not in parts, f"dev/cache leak: {rel}")
        require(not rel.endswith((".pyc", ".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz")), f"archive/cache leak: {rel}")
        require(not rel.startswith("Artifacts/"), f"internal artifact leak: {rel}")

    integration = json.loads(INTEGRATION.read_text(encoding="utf-8"))
    require(integration.get("studio_version") == "STUDIO20.4" and integration.get("status") == "PASS", "integration status mismatch")
    hashes = integration["file_hashes"]
    expected = {rel for rel in listed if rel != "Release/STUDIO20.4/studio_release_integration.json"}
    require(set(hashes) == expected, "integration hash closure mismatch")
    for rel in expected:
        require(hashes[rel] == sha256(ROOT / rel), f"integration hash mismatch: {rel}")

    dist = json.loads((ROOT / "Packaging/distribution_contract.json").read_text(encoding="utf-8"))
    win = json.loads((ROOT / "Packaging/windows/distribution.json").read_text(encoding="utf-8"))
    require(dist["studio_version"] == "STUDIO20.4", "distribution version stale")
    require(dist["stage"]["whitelist"] == "Release/STUDIO20.4/packaging_whitelist.txt", "distribution whitelist stale")
    require(win["milestone"] == "STUDIO20.4" and win["whitelist"] == "Release/STUDIO20.4/packaging_whitelist.txt", "Windows contract stale")

    with tempfile.TemporaryDirectory(prefix="archon-studio20.4-stage-") as raw:
        base = Path(raw)
        for platform in ("windows", "macos", "linux"):
            out = base / platform
            text = run(sys.executable, "-B", ROOT / "Tools/archon_distribution_stage.py", "--root", ROOT, "--platform", platform, "--output", out)
            require("PASS: STUDIO20.4" in text, f"{platform} stage version stale")
            manifest = json.loads((out / "DISTRIBUTION_STAGE.json").read_text(encoding="utf-8"))
            require(manifest["release_files"] == len(listed), f"{platform} stage count mismatch")
        win_out = base / "windows-exact"
        run(sys.executable, "-B", ROOT / "Tools/archon_windows_distribution.py", "stage", "--root", ROOT, "--output", win_out)
        run(sys.executable, "-B", ROOT / "Tools/archon_windows_distribution.py", "verify", "--output", win_out)

    run(sys.executable, "-B", ROOT / "Tools/verify_studio18_platform_portability.py")
    run(sys.executable, "-B", ROOT / "Tools/archon_studio_runtime.py", "--root", ROOT, "--self-test")
    run(sys.executable, "-B", ROOT / "Tools/archon_studio_desktop.py", "--root", ROOT, "--headless-smoke", "--port", "0")

    print(f"PASS: STUDIO20.4 Search UX fixes are release-safe; English confirmations, persisted settings and Studio-theme inheritance stage cleanly in {len(listed)} exact files")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
