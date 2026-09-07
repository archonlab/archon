"""Application service for one atomic condition/experiment registration."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from Analyzer_next.core.telemetry.scientific_target_registration import (
    ScientificIdentityRegistration,
    ScientificIdentityRegistrationError,
    ScientificIdentityRegistrationPort,
    canonical_hash,
)


def register_scientific_identities(
    *,
    repository: ScientificIdentityRegistrationPort,
    plan: Mapping[str, Any],
    plan_hash: str,
    rule_ids: Sequence[int],
    condition: Mapping[str, Any],
    timestamp: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    plan_id = str(plan.get("plan_id"))
    experiment_id = (
        "EXP-AUTO-"
        + canonical_hash({"plan_id": plan_id, "plan_hash": plan_hash})[
            :16
        ].upper()
    )
    condition_id = (
        "COND-AUTO-" + str(condition["condition_hash"])[:16].upper()
    )
    provenance = plan.get("provenance")
    source_action_id = (
        provenance.get("source_action_id")
        if isinstance(provenance, Mapping)
        else None
    )
    command = ScientificIdentityRegistration(
        experiment_id=experiment_id,
        condition_id=condition_id,
        plan_id=plan_id,
        plan_hash=plan_hash,
        title=str(plan.get("title") or plan_id),
        research_question=_text_or_none(plan.get("hypothesis")),
        experiment_type=_text_or_none(plan.get("experiment_type")),
        source_action_id=source_action_id,
        rule_ids=tuple(rule_ids),
        condition=dict(condition),
        timestamp=timestamp,
    )
    try:
        result = repository.register(command)
    except ScientificIdentityRegistrationError as error:
        return None, [f"IDENTITY_REGISTRATION_FAILED:{error}"]
    if result.failures:
        return None, list(result.failures)
    identities = {
        "experiment_id": result.experiment_id,
        "condition_id": result.condition_id,
        "rule_id": rule_ids[0] if len(rule_ids) == 1 else None,
        "rule_ids": list(rule_ids),
    }
    return identities, []


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["register_scientific_identities"]
