"""Fail-closed selection of the complete scientific identity path."""
from __future__ import annotations

import os
from typing import Callable

from . import scientific_identity_validation as native_validation
from .scientific_target_registration_routing import (
    DEFAULT_PROFILE,
    PROFILE_ENV,
    SUPPORTED_PROFILES,
)


def _legacy_module():
    from Analyzer_next.compatibility.legacy_analyzer import (
        production_research_cycle_launcher_handoff,
    )
    return production_research_cycle_launcher_handoff


def resolve_identity_validation_function(
    profile: str | None = None,
) -> Callable:
    selected = str(
        profile if profile is not None else os.environ.get(
            PROFILE_ENV,
            DEFAULT_PROFILE,
        )
    ).strip().lower()
    if selected == "native":
        return native_validation.telemetry_identity_issues
    if selected == "legacy":
        return _legacy_module().telemetry_identity_issues
    raise RuntimeError(
        f"Unsupported scientific-target registration profile: {selected!r}; "
        f"expected one of {SUPPORTED_PROFILES}"
    )


telemetry_identity_issues = resolve_identity_validation_function()


__all__ = [
    "DEFAULT_PROFILE",
    "PROFILE_ENV",
    "SUPPORTED_PROFILES",
    "resolve_identity_validation_function",
    "telemetry_identity_issues",
]
