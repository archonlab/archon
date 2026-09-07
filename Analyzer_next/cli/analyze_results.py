#!/usr/bin/env python3
"""Stable production entrypoint for the modular Analyzer cutover.

The modular profile now enters the ``Analyzer_next`` execution shell directly.
The coordinator, content-aware DAG, fingerprint policy, process execution, and
receipt attestation are native. Parity-approved scientific modules use
fail-closed ``Analyzer_next`` routes. Set
``ARCHON_ANALYZER_ENTRYPOINT_PROFILE=legacy`` (or pass
``--entrypoint-profile legacy``) for an immediate rollback through the original
coordinator without changing the production request path.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.production.routing import (
    DEFAULT_PROFILE,
    MODULE_OVERRIDES_ENV,
    PROFILE_ENV,
    SUPPORTED_PROFILES,
    build_module_overrides,
)


def parse_profile(argv: list[str]) -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--entrypoint-profile",
        choices=SUPPORTED_PROFILES,
        default=os.environ.get(PROFILE_ENV, DEFAULT_PROFILE),
    )
    namespace, remaining = parser.parse_known_args(argv)
    return str(namespace.entrypoint_profile), remaining


def main(argv: list[str] | None = None) -> int:
    profile, remaining = parse_profile(
        list(sys.argv[1:] if argv is None else argv)
    )
    if profile == "legacy":
        configured = os.environ.get(
            "ARCHON_LEGACY_ANALYZER_ENTRYPOINT", ""
        ).strip()
        coordinator = (
            Path(configured).expanduser().resolve()
            if configured
            else None
        )
        if coordinator is None or not coordinator.is_file():
            print(
                "[FAILED] legacy Analyzer rollback requires "
                "ARCHON_LEGACY_ANALYZER_ENTRYPOINT",
                file=sys.stderr,
            )
            return 2
        environment = os.environ.copy()
        environment[PROFILE_ENV] = profile
        environment.pop(MODULE_OVERRIDES_ENV, None)
        command = [sys.executable, str(coordinator), *remaining]
        os.execve(sys.executable, command, environment)
        return 127

    overrides = build_module_overrides(PROJECT_ROOT)
    os.environ[PROFILE_ENV] = profile
    os.environ[MODULE_OVERRIDES_ENV] = json.dumps(
        overrides,
        ensure_ascii=False,
        sort_keys=True,
    )
    from Analyzer_next.production.coordinator import main as coordinator_main

    return coordinator_main(
        remaining,
        module_overrides=overrides,
        profile=profile,
    )


if __name__ == "__main__":
    raise SystemExit(main())
