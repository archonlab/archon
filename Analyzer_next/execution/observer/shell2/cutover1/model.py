"""Pure OL2-CUTOVER1 profile and acceptance models."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class CutoverError(RuntimeError):
    """Raised when production profile state is absent, invalid, or unauthorized."""


class LauncherProfile(str, Enum):
    LEGACY = "legacy"
    MODULAR_V1 = "modular-v1"
    OL2 = "ol2"


@dataclass(frozen=True)
class AcceptanceReceipt:
    schema: str
    milestone: str
    candidate_profile: LauncherProfile
    visual_acceptance: bool
    operational_acceptance: bool
    accepted_at: str
    fingerprints: Mapping[str, str]
    receipt_hash: str




@dataclass(frozen=True)
class ReleaseAuthorization:
    """Portable production authorization sealed from a human-accepted OL2 source tree."""

    schema: str
    milestone: str
    launcher_profile: LauncherProfile
    cutover_milestone: str
    parent_acceptance_receipt_hash: str
    sealed_at: str
    fingerprints: Mapping[str, str]
    authorization_hash: str


@dataclass(frozen=True)
class ProfileRecord:
    schema: str
    profile: LauncherProfile
    updated_at: str
    acceptance_receipt_hash: str | None = None
