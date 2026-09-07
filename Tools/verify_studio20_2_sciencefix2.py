#!/usr/bin/env python3
"""Fail-closed STUDIO20.2 SCIENCEFIX2 verifier."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WHITELIST = ROOT / "Release/STUDIO20.2/packaging_whitelist.txt"
INTEGRATION = ROOT / "Release/STUDIO20.2/studio_release_integration.json"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def rows(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def run(*args: str | Path, cwd: Path = ROOT) -> str:
    proc = subprocess.run([str(x) for x in args], cwd=cwd, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=180)
    require(proc.returncode == 0, proc.stdout)
    return proc.stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    # Scientific semantic gates.
    run(sys.executable, "-B", ROOT / "Docs/Audits/2026-09-06/reproduce/test_mechanism_zero_values.py")
    run(sys.executable, "-B", ROOT / "Docs/Audits/2026-09-06/reproduce/test_mechanism_scientific_semantics.py")
    run(sys.executable, "-B", ROOT / "Docs/Audits/2026-09-06/reproduce/test_sciencefix2_value_semantics.py")

    # Legacy Observer must now use the shared runtime resolver and direct Analyzer entrypoint.
    observer = (ROOT / "Observer/observer_launcher.py").read_text(encoding="utf-8")
    require("runtime_python_command" in observer, "Observer does not use runtime Python resolver")
    require('cmd = [\n            "python3"' not in observer, "Observer still hardcodes python3")
    require('["bash", str(ANALYZER_LAUNCHER)]' not in observer, "Observer still launches Analyzer through bash")
    require("ANALYZER_ENTRYPOINT" in observer, "Observer direct Analyzer entrypoint missing")

    # Declared runtime contract is intentionally Python 3.12+.
    linux = json.loads((ROOT / "Release/ARCHON_LINUX_RUNTIME_REQUIREMENTS.json").read_text())
    windows = json.loads((ROOT / "Packaging/windows/distribution.json").read_text())
    studio_req = json.loads((ROOT / "Release/STUDIO20.2/studio_runtime_requirements.json").read_text())
    require(linux["release_target"]["python"] == ">=3.12", "Linux Python contract is not >=3.12")
    require(any("Python >=3.12" in x for x in windows["runtime_dependencies"]), "Windows Python contract is not >=3.12")
    require(studio_req["python"]["minimum"] == "3.12", "Studio Python contract is not 3.12")

    # Exact release closure and payload hygiene.
    listed = rows(WHITELIST)
    require(len(listed) == len(set(listed)), "packaging whitelist contains duplicates")
    require(all((ROOT / rel).is_file() for rel in listed), "packaging whitelist references a missing file")
    banned_suffixes = (".pyc", ".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz")
    for rel in listed:
        parts = Path(rel).parts
        require("__pycache__" not in parts and ".git" not in parts and ".agents" not in parts,
                f"development/cache path in sealed payload: {rel}")
        require(not rel.endswith(banned_suffixes), f"archive/cache file in sealed payload: {rel}")
        require(not rel.startswith("Artifacts/"), f"internal artifact leaked into sealed payload: {rel}")

    integration = json.loads(INTEGRATION.read_text(encoding="utf-8"))
    require(integration["studio_version"] == "STUDIO20.2" and integration["status"] == "PASS",
            "STUDIO20.2 integration status mismatch")
    require(integration["counts"]["packaging_files"] == len(listed), "packaging count mismatch")
    hashes = integration["file_hashes"]
    expected_keys = {rel for rel in listed if rel != "Release/STUDIO20.2/studio_release_integration.json"}
    require(set(hashes) == expected_keys, "STUDIO20.2 hash closure mismatch")
    for rel in sorted(expected_keys):
        require(hashes[rel] == sha256(ROOT / rel), f"integration hash mismatch: {rel}")

    # Current distribution contracts must point at the same closure.
    dist = json.loads((ROOT / "Packaging/distribution_contract.json").read_text())
    require(dist["studio_version"] == "STUDIO20.2", "distribution contract version is stale")
    require(dist["stage"]["whitelist"] == "Release/STUDIO20.2/packaging_whitelist.txt",
            "distribution contract whitelist is stale")
    require(windows["milestone"] == "STUDIO20.2", "Windows milestone is stale")
    require(windows["whitelist"] == "Release/STUDIO20.2/packaging_whitelist.txt",
            "Windows whitelist is stale")

    # Exact staging for all platforms.
    stage_builder = ROOT / "Tools/archon_distribution_stage.py"
    with tempfile.TemporaryDirectory(prefix="archon-studio20.2-stage-") as raw:
        tmp = Path(raw)
        for platform in ("windows", "macos", "linux"):
            out = tmp / platform
            text = run(sys.executable, "-B", stage_builder, "--root", ROOT,
                       "--platform", platform, "--output", out)
            require("PASS: STUDIO20.2" in text, f"{platform} staging uses stale milestone")
            manifest = json.loads((out / "DISTRIBUTION_STAGE.json").read_text())
            require(manifest["studio_version"] == "STUDIO20.2", f"{platform} stage version mismatch")
            require(manifest["release_files"] == len(listed), f"{platform} stage file count mismatch")

    # Windows exact-stage contract.
    sys.path.insert(0, str(ROOT / "Tools"))
    from archon_windows_distribution import stage, verify  # type: ignore
    with tempfile.TemporaryDirectory(prefix="archon-studio20.2-win-") as raw:
        out = Path(raw) / "stage"
        manifest = stage(ROOT, out)
        verify(out)
        require(manifest["milestone"] == "STUDIO20.2", "Windows stage milestone mismatch")

    # Existing shared Studio behavior remains live.
    run(sys.executable, "-B", ROOT / "Tools/verify_studio18_platform_portability.py")
    run(sys.executable, "-B", ROOT / "Tools/archon_studio_runtime.py", "--root", ROOT, "--self-test")
    run(sys.executable, "-B", ROOT / "Tools/archon_studio_desktop.py", "--root", ROOT, "--headless-smoke", "--port", "0")

    print(
        f"PASS: STUDIO20.2 preserves zero-valued scientific measurements across prediction/discovery/"
        f"mutation/director paths, removes legacy Observer interpreter/shell drift, enforces Python >=3.12, "
        f"and stages {len(listed)} clean exact files"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
