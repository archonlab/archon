"""Storage-independent contract for scientific identity validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ScientificIdentityValidationError(RuntimeError):
    """Raised when an identity repository cannot complete its read."""


@dataclass(frozen=True, slots=True)
class ScientificIdentityValidation:
    experiment_id: str | None
    condition_id: str | None


class ScientificIdentityValidationPort(Protocol):
    def identity_issues(
        self,
        request: ScientificIdentityValidation,
    ) -> tuple[str, ...]: ...


__all__ = [
    "ScientificIdentityValidation",
    "ScientificIdentityValidationError",
    "ScientificIdentityValidationPort",
]
