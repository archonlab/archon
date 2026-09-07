#!/usr/bin/env python3
"""Stable launcher-profile router for OBSERVER.sh."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.execution.observer.shell2.cutover1 import CutoverError, CutoverService, LauncherProfile
from Analyzer_next.release.config_bootstrap import ConfigBootstrapError, ensure_config_layout


def _run_python_file(path: Path, argv: Sequence[str]) -> int:
    spec = importlib.util.spec_from_file_location(f"archon_launcher_profile_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise CutoverError(f"Cannot load launcher target: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    main = getattr(module, "main", None)
    if not callable(main):
        raise CutoverError(f"Launcher target has no main(): {path}")
    old_argv = sys.argv[:]
    try:
        sys.argv = [str(path), *argv]
        result = main()
    finally:
        sys.argv = old_argv
    return int(result or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARCHON Observer launcher profile router", add_help=False)
    parser.add_argument("--profile-status", action="store_true")
    known, passthrough = parser.parse_known_args(argv)
    service = CutoverService(PROJECT_ROOT)
    try:
        record = service.read_profile(
            verify_ol2_acceptance=True,
            allow_modified_sources=True,
        )
        ensure_config_layout(PROJECT_ROOT, active_profile=record.profile.value)
    except (CutoverError, ConfigBootstrapError) as exc:
        print(f"ERROR: launcher profile is invalid: {exc}", file=sys.stderr)
        return 2

    source_changes: tuple[str, ...] = ()
    if record.profile is LauncherProfile.OL2:
        try:
            source_changes = service.source_modifications(
                acceptance_bound=bool(record.acceptance_receipt_hash),
            )
        except CutoverError as exc:
            print(f"ERROR: launcher provenance is invalid: {exc}", file=sys.stderr)
            return 2
        if source_changes and known.profile_status:
            print(
                "WARNING: MODIFIED_SOURCE_TREE: local production sources differ from the "
                "accepted/sealed release; continuing in source mode. Changed: "
                + ", ".join(source_changes),
                file=sys.stderr,
            )

    if known.profile_status:
        target = service.target_path(record.profile)
        print(f"profile={record.profile.value}")
        print(f"target={target}")
        print(f"source={'implicit-default' if record.updated_at == 'implicit-default' else ('release-default' if record.updated_at == 'release-default' else 'profile-file')}")
        print(f"integrity={'MODIFIED_SOURCE_TREE' if source_changes else 'VERIFIED'}")
        if source_changes:
            print("modified=" + ",".join(source_changes))
        return 0

    if record.profile is LauncherProfile.OL2:
        from Analyzer_next.cli.observer_launcher_2 import main as ol2_main
        return ol2_main(list(passthrough))

    target = service.target_path(record.profile)
    if target is None or not target.is_file():
        print(f"ERROR: launcher target is missing: {target}", file=sys.stderr)
        return 2
    try:
        return _run_python_file(target, passthrough)
    except CutoverError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
