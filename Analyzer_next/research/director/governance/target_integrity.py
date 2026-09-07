"""Scientific target-integrity helpers for Research Director governance.

Principle-specific actions such as EXP-GP102 or EXP-PERT-GP-105 are bound to
that principle.  Governance may record cross-principle dependencies, but it
must not rewrite a principle-bound action's scientific target, success
criterion, title, or rationale to test a different GP.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set


_BOUND_PRINCIPLE_RE = re.compile(r"(?:^|[-_])GP-?(\d{3})(?:$|[-_])", re.IGNORECASE)
_EXPLICIT_PRINCIPLE_RE = re.compile(r"\bGP[-_ ]?(\d{3})\b", re.IGNORECASE)

PATCHABLE_SCIENTIFIC_FIELDS = {
    "title",
    "suggested_target",
    "done_when",
    "rationale",
}


def canonical_principle_id(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper().replace("_", "-").replace(" ", "-")
    match = re.fullmatch(r"GP-?(\d{3})", text)
    if not match:
        return None
    return f"GP-{match.group(1)}"


def bound_principle_for_action(action_id: Any) -> Optional[str]:
    """Return the GP explicitly encoded by a principle-bound action ID."""
    text = str(action_id or "").strip()
    match = _BOUND_PRINCIPLE_RE.search(text)
    if not match:
        return None
    return f"GP-{match.group(1)}"


def explicit_principles(value: Any) -> Set[str]:
    text = str(value or "")
    return {f"GP-{m.group(1)}" for m in _EXPLICIT_PRINCIPLE_RE.finditer(text)}


def action_accepts_principle(action_id: Any, principle_id: Any) -> bool:
    """Whether a recommendation for principle_id may target action_id.

    Generic actions without a GP in their ID remain cross-principle capable.
    A principle-bound action only accepts its own GP.
    """
    bound = bound_principle_for_action(action_id)
    principle = canonical_principle_id(principle_id)
    if bound is None or principle is None:
        return True
    return bound == principle


def _new_foreign_principles(before: Any, after: Any, bound: str) -> Set[str]:
    before_ids = explicit_principles(before)
    after_ids = explicit_principles(after)
    return {pid for pid in (after_ids - before_ids) if pid != bound}


def validate_snapshot_transition(
    action_id: Any,
    before_snapshot: Dict[str, Any],
    after_snapshot: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return fail-closed issues for new cross-principle target rewrites."""
    bound = bound_principle_for_action(action_id)
    if bound is None:
        return []

    issues: List[Dict[str, Any]] = []
    for field_name in sorted(PATCHABLE_SCIENTIFIC_FIELDS):
        before = before_snapshot.get(field_name, "") if isinstance(before_snapshot, dict) else ""
        after = after_snapshot.get(field_name, "") if isinstance(after_snapshot, dict) else ""
        foreign = sorted(_new_foreign_principles(before, after, bound))
        if not foreign:
            continue
        issues.append({
            "type": "cross_principle_target_rewrite",
            "severity": "ERROR",
            "field": field_name,
            "bound_principle": bound,
            "foreign_principles": foreign,
            "message": (
                f"{action_id} is bound to {bound}; governance must not add "
                f"scientific target semantics for {', '.join(foreign)} to {field_name}."
            ),
        })
    return issues


def validate_proposal_principles(
    action_id: Any,
    affected_principles: Iterable[Any],
) -> List[Dict[str, Any]]:
    """Validate proposal-level principle routing before patch application."""
    bound = bound_principle_for_action(action_id)
    if bound is None:
        return []
    foreign = sorted({
        pid
        for raw in affected_principles
        for pid in [canonical_principle_id(raw)]
        if pid is not None and pid != bound
    })
    if not foreign:
        return []
    return [{
        "type": "cross_principle_target_route",
        "severity": "ERROR",
        "bound_principle": bound,
        "foreign_principles": foreign,
        "message": (
            f"{action_id} is bound to {bound}; recommendations for "
            f"{', '.join(foreign)} must target their own or a generic action."
        ),
    }]


def validate_persisted_override(
    action_id: Any,
    override: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Check whether an already-persisted override crossed a GP boundary.

    The rollback snapshot is the authoritative pre-patch state.  This preserves
    any foreign GP references that already existed before the patch while
    rejecting newly introduced cross-principle scientific semantics.
    """
    snapshot = override.get("snapshot", {}) if isinstance(override, dict) else {}
    rollback = override.get("rollback_snapshot", {}) if isinstance(override, dict) else {}
    before = rollback.get("snapshot", {}) if isinstance(rollback, dict) else {}
    if not isinstance(snapshot, dict) or not isinstance(before, dict):
        return []
    return validate_snapshot_transition(action_id, before, snapshot)


__all__ = [
    "PATCHABLE_SCIENTIFIC_FIELDS",
    "action_accepts_principle",
    "bound_principle_for_action",
    "canonical_principle_id",
    "explicit_principles",
    "validate_persisted_override",
    "validate_proposal_principles",
    "validate_snapshot_transition",
]
