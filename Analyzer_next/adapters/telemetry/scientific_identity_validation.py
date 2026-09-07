"""Native facade matching the protected launcher identity-check API."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from Analyzer_next.application.telemetry.scientific_identity_validation import (
    validate_scientific_identities,
)

from .sqlite_scientific_identity_validation import (
    SQLiteScientificIdentityValidationRepository,
)


def telemetry_identity_issues(
    database: Path,
    *,
    experiment_id: Optional[str],
    condition_id: Optional[str],
) -> List[str]:
    if not database.is_file():
        return [f"TELEMETRY_DATABASE_INVALID:{database}"]
    return validate_scientific_identities(
        repository=SQLiteScientificIdentityValidationRepository(database),
        experiment_id=experiment_id,
        condition_id=condition_id,
    )


__all__ = ["telemetry_identity_issues"]
