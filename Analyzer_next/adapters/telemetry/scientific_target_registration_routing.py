"""Fail-closed selection of the complete identity-registration transaction."""
from __future__ import annotations

import os
from typing import Callable

from . import scientific_target_registration as native_registration


PROFILE_ENV = "ARCHON_SCIENTIFIC_TARGET_REGISTRATION_PROFILE"
DEFAULT_PROFILE = "native"
SUPPORTED_PROFILES = ("native", "legacy")


def _legacy_module():
    from Analyzer_next.compatibility.legacy_analyzer import (
        scientific_target_resolver,
    )
    return scientific_target_resolver


def resolve_registration_function(
    profile: str | None = None,
) -> Callable:
    selected = str(
        profile if profile is not None else os.environ.get(
            PROFILE_ENV, DEFAULT_PROFILE
        )
    ).strip().lower()
    if selected == "native":
        return native_registration.register_identities
    if selected == "legacy":
        return _legacy_module().register_identities
    raise RuntimeError(
        f"Unsupported scientific-target registration profile: {selected!r}; "
        f"expected one of {SUPPORTED_PROFILES}"
    )


register_identities = resolve_registration_function()


__all__ = [
    "DEFAULT_PROFILE",
    "PROFILE_ENV",
    "SUPPORTED_PROFILES",
    "register_identities",
    "resolve_registration_function",
]
