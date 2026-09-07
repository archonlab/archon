"""Native facade matching the protected scientific-target registration API."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from Analyzer_next.application.telemetry.scientific_target_registration import (
    register_scientific_identities,
)

from .sqlite_scientific_target_registration import (
    SQLiteScientificIdentityRegistrationRepository,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_identities(
    database: Path,
    *,
    plan: Dict[str, Any],
    plan_hash: str,
    rule_ids: List[int],
    condition: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    return register_scientific_identities(
        repository=SQLiteScientificIdentityRegistrationRepository(database),
        plan=plan,
        plan_hash=plan_hash,
        rule_ids=rule_ids,
        condition=condition,
        timestamp=now_iso(),
    )


__all__ = ["register_identities"]
