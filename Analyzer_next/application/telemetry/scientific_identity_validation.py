"""Application service for read-only scientific identity validation."""
from __future__ import annotations

from Analyzer_next.core.telemetry.scientific_identity_validation import (
    ScientificIdentityValidation,
    ScientificIdentityValidationError,
    ScientificIdentityValidationPort,
)


def validate_scientific_identities(
    *,
    repository: ScientificIdentityValidationPort,
    experiment_id: str | None,
    condition_id: str | None,
) -> list[str]:
    request = ScientificIdentityValidation(
        experiment_id=experiment_id,
        condition_id=condition_id,
    )
    try:
        return list(repository.identity_issues(request))
    except ScientificIdentityValidationError as error:
        return [f"TELEMETRY_IDENTITY_CHECK_FAILED:{error}"]


__all__ = ["validate_scientific_identities"]
