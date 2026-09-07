"""Fail-closed Stage 7.5 telemetry-inspection selection."""
from __future__ import annotations

import os
from typing import Callable

from . import telemetry_run_inspection as native_inspection


PROFILE_ENV = "ARCHON_PRODUCTION_OBSERVER_INTAKE_PROFILE"
DEFAULT_PROFILE = "native"
SUPPORTED_PROFILES = ("native", "legacy")


def _legacy_module():
    from Analyzer_next.compatibility.legacy_analyzer import (
        production_observer_result_intake,
    )
    return production_observer_result_intake


def resolve_inspection_function(
    profile: str | None = None,
) -> Callable:
    selected = str(
        profile if profile is not None else os.environ.get(
            PROFILE_ENV,
            DEFAULT_PROFILE,
        )
    ).strip().lower()
    if selected == "native":
        return native_inspection.inspect_sqlite
    if selected == "legacy":
        return _legacy_module().inspect_sqlite
    raise RuntimeError(
        f"Unsupported production observer intake profile: {selected!r}; "
        f"expected one of {SUPPORTED_PROFILES}"
    )


inspect_sqlite = resolve_inspection_function()


__all__ = [
    "DEFAULT_PROFILE",
    "PROFILE_ENV",
    "SUPPORTED_PROFILES",
    "inspect_sqlite",
    "resolve_inspection_function",
]
