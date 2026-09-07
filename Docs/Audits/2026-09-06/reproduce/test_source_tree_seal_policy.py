#!/usr/bin/env python3
"""Regression: source edits warn, structurally corrupt provenance still blocks."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Analyzer_next.execution.observer.shell2.cutover1 import CutoverError, CutoverService, LauncherProfile


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def main() -> int:
    service = CutoverService(ROOT)

    # The current development tree intentionally differs from its historical
    # RELEASE6 seal. Strict verification must still detect that fact.
    try:
        service.read_profile(verify_ol2_acceptance=True)
    except CutoverError as exc:
        require("changed after sealing" in str(exc), f"strict seal did not detect source drift: {exc}")
    else:
        raise AssertionError("strict seal unexpectedly accepted the modified source tree")

    # Runtime source-mode policy validates provenance structure but does not
    # treat legitimate local source edits as an execution authorization error.
    profile = service.read_profile(
        verify_ol2_acceptance=True,
        allow_modified_sources=True,
    )
    require(profile.profile is LauncherProfile.OL2, "relaxed source policy did not preserve OL2")
    changes = service.source_modifications(acceptance_bound=False)
    require(bool(changes), "modified source tree was not reported")
    require("Analyzer_next/cli/observer_launcher_profile.py" in changes,
            "current policy edit is missing from modification report")

    proc = subprocess.run(
        [sys.executable, "-B", str(ROOT / "Analyzer_next/cli/observer_launcher_profile.py"), "--profile-status"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    require(proc.returncode == 0, proc.stdout + proc.stderr)
    require("integrity=MODIFIED_SOURCE_TREE" in proc.stdout, proc.stdout)
    require("WARNING: MODIFIED_SOURCE_TREE" in proc.stderr, proc.stderr)

    # Corrupt provenance is a different class of problem and remains fail-closed.
    original = json.loads((ROOT / "Release/ARCHON_RELEASE1_PRODUCTION.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="archon-seal-policy-") as raw:
        tmp = Path(raw)
        corrupt = tmp / "ARCHON_RELEASE1_PRODUCTION.json"
        payload = dict(original)
        payload["schema"] = "corrupt.schema"
        corrupt.write_text(json.dumps(payload), encoding="utf-8")
        corrupt_service = CutoverService(
            ROOT,
            profile_path=tmp / "missing-profile.json",
            acceptance_path=tmp / "missing-acceptance.json",
            release_authorization_path=corrupt,
        )
        try:
            corrupt_service.read_profile(
                verify_ol2_acceptance=True,
                allow_modified_sources=True,
            )
        except CutoverError as exc:
            require("Invalid production authorization schema/milestone" in str(exc), str(exc))
        else:
            raise AssertionError("corrupt production authorization was not blocked")

    print("PASS: modified source trees warn and continue; corrupt provenance remains fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
