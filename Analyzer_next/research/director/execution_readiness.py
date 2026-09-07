"""Canonical ResearchAction execution-readiness policy.

BRIDGE5.8.2 keeps governance reviewability separate from executable scientific
readiness.  Legacy prediction actions must not remain READY when a newer
canonical target-aware action supersedes them, and target-bound experiments
must not be materialized without concrete precommitted rule targets.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


_LEGACY_GP_ACTION_RE = re.compile(r"^EXP-GP-?(\d{3})$", re.IGNORECASE)
_CANONICAL_PERT_ACTION_RE = re.compile(r"^EXP-PERT-GP-(\d{3})$", re.IGNORECASE)

# These action kinds enter the Observer scientific-target/runtime lane and
# therefore require concrete canonical rule targets before materialization.
_TARGET_BOUND_KINDS = {
    "matched_control_study",
    "perturbation_evidence_program",
    "perturbation_recovery_test",
    "perturbation_test",
}


def normalize_rule_targets(values: Any) -> List[str]:
    """Return only concrete canonical-looking rule IDs, preserving order."""
    if not isinstance(values, (list, tuple, set)):
        return []
    output: List[str] = []
    for raw in values:
        text = str(raw).strip()
        if not text or not text.isdigit() or len(text) > 5:
            continue
        rule_id = text.zfill(5)
        if rule_id not in output:
            output.append(rule_id)
    return output


def _canonical_perturbation_actions(
    experiment_plan: Iterable[Dict[str, Any]],
) -> Dict[str, str]:
    canonical: Dict[str, str] = {}
    for item in experiment_plan:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("id") or "").strip()
        match = _CANONICAL_PERT_ACTION_RE.fullmatch(action_id)
        if not match:
            continue
        principle_id = f"GP-{match.group(1)}"
        previous = canonical.get(principle_id)
        if previous is None or action_id < previous:
            canonical[principle_id] = action_id
    return canonical


def classify_action_execution_readiness(
    experiment_plan: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Classify current Planner actions for Director/OL2 execution readiness.

    The result is deliberately advisory to governance validation.  It does not
    create, mutate, approve, or materialize any experiment.
    """
    plan = [dict(item) for item in experiment_plan if isinstance(item, dict)]
    canonical_by_principle = _canonical_perturbation_actions(plan)
    result: Dict[str, Dict[str, Any]] = {}

    for item in plan:
        action_id = str(item.get("id") or "").strip()
        if not action_id:
            continue
        kind = str(item.get("type") or "experiment").strip().lower()
        target_rules = normalize_rule_targets(item.get("target_rules"))
        revision_required = bool(item.get("requires_target_revision"))

        legacy_match = _LEGACY_GP_ACTION_RE.fullmatch(action_id)
        superseded_by = None
        if legacy_match:
            principle_id = f"GP-{legacy_match.group(1)}"
            superseded_by = canonical_by_principle.get(principle_id)

        if superseded_by and superseded_by != action_id:
            result[action_id] = {
                "status": "SUPERSEDED",
                "reason": (
                    f"{action_id} is superseded by canonical target-aware action "
                    f"{superseded_by}; the legacy action must not be materialized."
                ),
                "target_rules": target_rules,
                "superseded_by_action_id": superseded_by,
            }
            continue

        if revision_required:
            continuation = item.get("continuation")
            continuation = continuation if isinstance(continuation, dict) else {}
            prior_result = str(continuation.get("prior_result") or "NON_DIAGNOSTIC")
            prior_experiment = str(continuation.get("prior_experiment_id") or "prior targeted experiment")
            result[action_id] = {
                "status": "NEEDS_REVISION",
                "reason": (
                    f"{action_id} already produced {prior_result} in "
                    f"{prior_experiment}; the previous immutable ScientificTarget "
                    "must not be materialized again until a revised target with a "
                    "new target_hash and changed diagnostic design axis is precommitted."
                ),
                "target_rules": target_rules,
                "superseded_by_action_id": None,
            }
            continue

        if kind in _TARGET_BOUND_KINDS and not target_rules:
            result[action_id] = {
                "status": "WAITING_FOR_TARGET",
                "reason": (
                    f"{action_id} requires concrete precommitted target_rules "
                    "before scientific target resolution and runtime materialization."
                ),
                "target_rules": [],
                "superseded_by_action_id": None,
            }
            continue

        result[action_id] = {
            "status": "READY",
            "reason": (
                "Canonical execution prerequisites are available."
                if kind in _TARGET_BOUND_KINDS
                else "No target-readiness blocker is declared for this action kind."
            ),
            "target_rules": target_rules,
            "superseded_by_action_id": None,
        }

    return result


__all__ = [
    "classify_action_execution_readiness",
    "normalize_rule_targets",
]
