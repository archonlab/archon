#!/usr/bin/env python3
"""Fail-closed verification for STUDIO19 distribution packaging foundation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Tools/archon_studio_runtime.py"
DESKTOP = ROOT / "Tools/archon_studio_desktop.py"
CONTRACT = ROOT / "Packaging/distribution_contract.json"
WHITELIST = ROOT / "Release/STUDIO19/packaging_whitelist.txt"
INTEGRATION = ROOT / "Release/STUDIO19/studio_release_integration.json"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def rows(path: Path) -> list[str]:
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip() and not x.lstrip().startswith("#")]


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract["schema"] == "archon_distribution_contract_v1", "distribution contract schema mismatch")
    expected = {
        "windows": "ARCHON-Studio-1.0.0.exe",
        "macos": "ARCHON-Studio-1.0.0.dmg",
        "linux": "ARCHON-Studio-1.0.0.AppImage",
    }
    require(set(contract["platforms"]) == set(expected), "platform matrix is incomplete")
    for platform, artifact in expected.items():
        require(contract["platforms"][platform]["target_artifact"] == artifact, f"wrong {platform} target artifact")

    runtime = RUNTIME.read_text(encoding="utf-8")
    desktop = DESKTOP.read_text(encoding="utf-8")
    require("runtime_python_selection" in runtime and "self.python_selection = runtime_python_selection(self.root)" in runtime,
            "runtime bridge does not own the child interpreter contract")
    require('command = ["python3"' not in runtime and '["python3", str(self.snapshot_builder)' not in runtime,
            "Studio runtime still contains a hardcoded python3 process launch")
    require("runtime_python_command(root)" in desktop, "desktop snapshot path bypasses the child interpreter contract")

    sys.path.insert(0, str(ROOT / "Tools"))
    from archon_runtime_python import runtime_python_command  # type: ignore
    source_cmd = runtime_python_command(ROOT)
    require(bool(source_cmd) and Path(source_cmd[0]).is_file(), "source runtime interpreter cannot be resolved")
    with tempfile.TemporaryDirectory(prefix="archon-studio19-runtime-") as raw:
        fake = Path(raw) / ("python.exe" if os.name == "nt" else "python3")
        fake.write_bytes(b"runtime-probe")
        old = os.environ.get("ARCHON_RUNTIME_PYTHON")
        os.environ["ARCHON_RUNTIME_PYTHON"] = str(fake)
        try:
            resolved = runtime_python_command(ROOT)
        finally:
            if old is None:
                os.environ.pop("ARCHON_RUNTIME_PYTHON", None)
            else:
                os.environ["ARCHON_RUNTIME_PYTHON"] = old
        require(Path(resolved[0]) == fake.resolve(), "ARCHON_RUNTIME_PYTHON does not take precedence")

    listed = rows(WHITELIST)
    require(len(listed) == len(set(listed)), "STUDIO19 packaging whitelist contains duplicates")
    for rel in listed:
        require((ROOT / rel).is_file(), f"whitelisted file missing: {rel}")

    integration = json.loads(INTEGRATION.read_text(encoding="utf-8"))
    require(integration["studio_version"] == "STUDIO19" and integration["status"] == "PASS", "integration manifest status mismatch")
    require(integration["counts"]["packaging_files"] == len(listed), "integration manifest packaging count mismatch")
    hashes = integration.get("file_hashes") or {}
    expected_hashed = [rel for rel in listed if rel != "Release/STUDIO19/studio_release_integration.json"]
    require(set(hashes) == set(expected_hashed), "integration manifest hash closure mismatch")
    for rel in expected_hashed:
        digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        require(hashes[rel] == digest, f"integration hash mismatch: {rel}")

    builder = ROOT / "Tools/archon_distribution_stage.py"
    with tempfile.TemporaryDirectory(prefix="archon-studio19-stage-") as raw:
        base = Path(raw)
        for platform in ("windows", "macos", "linux"):
            out = base / platform
            proc = subprocess.run(
                [sys.executable, str(builder), "--root", str(ROOT), "--platform", platform, "--output", str(out)],
                cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            require(proc.returncode == 0, f"{platform} stage builder failed: {proc.stdout}")
            manifest = json.loads((out / "DISTRIBUTION_STAGE.json").read_text(encoding="utf-8"))
            require(manifest["platform"] == platform and manifest["release_files"] == len(listed), f"{platform} stage manifest mismatch")
            require(manifest["runtime_mode"] == "source-runtime", f"{platform} source stage mode mismatch")
            require(all((out / rel).is_file() for rel in listed), f"{platform} stage is not exact-whitelist complete")

    self_test = subprocess.run(
        [sys.executable, str(DESKTOP), "--root", str(ROOT), "--self-test"], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    require(self_test.returncode == 0 and "PASS:" in self_test.stdout, f"desktop self-test failed: {self_test.stdout}")

    print(
        f"PASS: STUDIO19 establishes one distribution contract for Windows/macOS/Linux, resolves child Python without hardcoded python3, "
        f"and materializes {len(listed)} exact release files into all three platform staging trees"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
