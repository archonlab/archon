"""Storage-independent contract for atomic scientific identity registration."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Protocol, Sequence

from .experimental_conditions import ExperimentalConditionsRepositoryPort


class ScientificIdentityRegistrationError(RuntimeError):
    """Raised when the registration adapter cannot complete atomically."""


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ScientificIdentityRegistration:
    experiment_id: str
    condition_id: str
    plan_id: str
    plan_hash: str
    title: str
    research_question: str | None
    experiment_type: str | None
    source_action_id: Any
    rule_ids: Sequence[int]
    condition: Mapping[str, Any]
    timestamp: str


@dataclass(frozen=True, slots=True)
class ScientificIdentityRegistrationResult:
    experiment_id: str
    condition_id: str
    failures: tuple[str, ...] = ()


class ScientificIdentityRegistrationPort(
    ExperimentalConditionsRepositoryPort,
    Protocol,
):
    def register(
        self,
        command: ScientificIdentityRegistration,
    ) -> ScientificIdentityRegistrationResult: ...


__all__ = [
    "ScientificIdentityRegistration",
    "ScientificIdentityRegistrationError",
    "ScientificIdentityRegistrationPort",
    "ScientificIdentityRegistrationResult",
    "canonical_hash",
]
