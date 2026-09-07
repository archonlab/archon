"""Immutable ScientificTarget construction and integrity checks.

The target is deliberately semantic rather than physical.  Rule ids and
runtime geometry remain in the existing target-resolution contract; this
object states which scientific claim the controlled experiment is intended to
test.  Carrying the object proves intent only.  It never implies support.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from Analyzer_next.core.scientific_claims import CLAIM_SPECS


SCHEMA = "archon_scientific_target_v1"
VERSION = "1.0"
_GP_PATTERN = re.compile(r"\bGP[-_ ]?(\d{3})\b", re.IGNORECASE)
_QUESTION_TYPES = {
    "perturbation_recovery_test": "perturbation_response",
    "metric_validation_baseline": "metric_validation",
    "counterexample_search": "counterexample_search",
    "cohort_gap_program": "counterexample_search",
    "long_run_replication": "replication",
    "controlled_action_validation": "controlled_comparison",
}
_TARGET_METRIC_EXTENSIONS = {
    "GP-102": (
        "knowledge_transfer",
        "feedback_knowledge_impact",
        "feedback_environment_impact",
        "feedback_regime",
    ),
}


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


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _unique_text(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _principle_ids(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        for match in _GP_PATTERN.finditer(str(value or "")):
            claim_id = f"GP-{match.group(1)}"
            if claim_id not in result:
                result.append(claim_id)
    return result


def _target_id(
    action: Mapping[str, Any],
    intent: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> str | None:
    explicit = _as_dict(action.get("scientific_target"))
    candidates = _principle_ids(
        [explicit.get("target_id"), action.get("based_on_prediction")]
    )
    if len(candidates) == 1:
        return candidates[0]

    action_candidates = _principle_ids([action.get("action_id"), action.get("id")])
    if len(action_candidates) == 1:
        return action_candidates[0]

    provenance_candidates = _principle_ids(
        _as_list(provenance.get("source_principle_ids"))
    )
    if len(provenance_candidates) == 1:
        return provenance_candidates[0]

    semantic_candidates = _principle_ids([
        action.get("suggested_target"),
        action.get("done_when"),
        intent.get("hypothesis_prompt"),
        intent.get("target_description"),
        *_as_list(intent.get("success_criteria")),
    ])
    return semantic_candidates[0] if len(semantic_candidates) == 1 else None


def scientific_target_hash(target: Mapping[str, Any]) -> str:
    immutable = {
        key: value
        for key, value in target.items()
        if key != "target_hash"
    }
    return canonical_hash(immutable)


def validate_scientific_target(
    target: Any,
) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(target, Mapping):
        return False, ("SCIENTIFIC_TARGET_NOT_OBJECT",)
    failures: list[str] = []
    if target.get("schema") != SCHEMA:
        failures.append("SCIENTIFIC_TARGET_SCHEMA_INVALID")
    if str(target.get("target_type") or "") != "principle":
        failures.append("SCIENTIFIC_TARGET_TYPE_INVALID")
    target_id = str(target.get("target_id") or "")
    if target_id not in CLAIM_SPECS:
        failures.append("SCIENTIFIC_TARGET_ID_UNKNOWN")
    if not str(target.get("action_id") or "").strip():
        failures.append("SCIENTIFIC_TARGET_ACTION_ID_MISSING")
    if not str(target.get("question_type") or "").strip():
        failures.append("SCIENTIFIC_TARGET_QUESTION_TYPE_MISSING")
    if not _as_list(target.get("success_criteria")):
        failures.append("SCIENTIFIC_TARGET_SUCCESS_CRITERIA_MISSING")
    if not _unique_text(_as_list(target.get("target_metrics"))):
        failures.append("SCIENTIFIC_TARGET_METRICS_MISSING")
    expected = scientific_target_hash(target)
    if str(target.get("target_hash") or "") != expected:
        failures.append("SCIENTIFIC_TARGET_HASH_MISMATCH")
    return not failures, tuple(sorted(set(failures)))


def build_scientific_target(
    *,
    action: Mapping[str, Any],
    experiment_intent: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Build a deterministic target from verified Director/Planner state.

    Ambiguous or non-principle actions return ``None``.  They remain valid
    experiments, but are not allowed into the target-specific evidence lane.
    """
    target_id = _target_id(action, experiment_intent, provenance)
    spec = CLAIM_SPECS.get(target_id or "")
    if spec is None:
        return None

    action_id = str(
        action.get("action_id")
        or action.get("id")
        or provenance.get("source_action_id")
        or ""
    ).strip()
    if not action_id:
        return None

    experiment_type = str(
        experiment_intent.get("experiment_type")
        or action.get("kind")
        or ""
    ).strip()
    explicit = _as_dict(action.get("scientific_target"))
    criteria = _as_list(explicit.get("success_criteria")) or _as_list(
        experiment_intent.get("success_criteria")
    )
    criteria = [
        value if isinstance(value, Mapping) else str(value).strip()
        for value in criteria
        if isinstance(value, Mapping) or str(value or "").strip()
    ]
    if not criteria:
        return None

    explicit_metrics = _unique_text(_as_list(explicit.get("target_metrics")))
    target_metrics = explicit_metrics or _unique_text((
        *spec.required_fields,
        *_TARGET_METRIC_EXTENSIONS.get(spec.id, ()),
    ))
    target: dict[str, Any] = {
        "schema": SCHEMA,
        "version": VERSION,
        "target_type": "principle",
        "target_id": target_id,
        "action_id": action_id,
        "question_type": str(
            explicit.get("question_type")
            or _QUESTION_TYPES.get(experiment_type)
            or "controlled_comparison"
        ),
        "success_criteria": criteria,
        "target_metrics": target_metrics,
        "claim_spec": {
            "claim_id": spec.id,
            "claim_version": spec.version,
            "claim_family": spec.family,
        },
        "scientific_policy": {
            "intent_is_not_support": True,
            "target_specific_interpretation_required": True,
            "automatic_principle_promotion": False,
            "fail_closed_on_hash_mismatch": True,
        },
    }
    target["target_hash"] = scientific_target_hash(target)
    return target


__all__ = [
    "SCHEMA",
    "VERSION",
    "build_scientific_target",
    "canonical_hash",
    "scientific_target_hash",
    "validate_scientific_target",
]
