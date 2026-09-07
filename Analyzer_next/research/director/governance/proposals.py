"""Patch proposal construction and validation."""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, List, Tuple

from Analyzer_next.research.director.common import canonical_json_hash
from Analyzer_next.research.director.contracts import ResearchAction
from Analyzer_next.research.director.governance.target_integrity import (
    bound_principle_for_action,
    explicit_principles,
    validate_proposal_principles,
    validate_snapshot_transition,
)


DIRECT_ACTION_EXECUTION = "DIRECT_ACTION_EXECUTION"


def _direct_action_priority(action: ResearchAction) -> str:
    urgency = str(action.urgency or "").strip().upper()
    if urgency in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
        return urgency
    priority = int(action.priority or 0)
    if priority >= 7:
        return "CRITICAL"
    if priority >= 5:
        return "HIGH"
    if priority >= 3:
        return "MEDIUM"
    return "LOW"


def _direct_action_execution_proposal(
    action: ResearchAction,
) -> Dict[str, Any]:
    """Expose a complete Director action without inventing a semantic patch.

    Recommendation patch proposals are refinements, not the action inventory.
    A scientifically complete action must remain reviewable when Consensus has
    no additional patch recommendation for it.  The immutable action snapshot
    lets the existing human-review and atomic gateway fail closed on drift.
    """
    snapshot = _research_action_snapshot(action)
    principles = set()
    bound = bound_principle_for_action(action.action_id)
    if bound:
        principles.add(bound)
    else:
        for value in (
            action.title,
            action.suggested_target,
            action.done_when,
            action.rationale,
        ):
            principles.update(explicit_principles(value))
    return {
        "proposal_id": f"RAEP-{action.action_id}",
        "proposal_kind": DIRECT_ACTION_EXECUTION,
        "target_action_id": action.action_id,
        "target_action_title": action.title,
        "highest_priority": _direct_action_priority(action),
        "affected_principles": sorted(principles),
        "affected_signals": ["DIRECT_ACTION_EXECUTION"],
        "source_recommendations": [],
        "patch_operations": [],
        "action_snapshot": snapshot,
        "action_snapshot_hash": canonical_json_hash(snapshot),
        "proposed_title": action.title,
        "proposed_target_additions": [],
        "proposed_success_criteria": [],
        "proposed_rationale_extensions": [],
        "application_status": "NOT_APPLIED",
        "requires_review": True,
        "automatic_application": False,
        "semantic_patch_required": False,
        "execution_readiness": str(action.execution_readiness or "UNKNOWN"),
        "execution_readiness_reason": action.execution_readiness_reason,
        "superseded_by_action_id": action.superseded_by_action_id,
        "target_rules": list(action.target_rules),
    }

def build_recommendation_patch_proposals(
    consolidated: Dict[str, Any],
    actions: List[ResearchAction],
) -> Dict[str, Any]:
    """Build review proposals for every current Director action.

    Coverage recommendations produce semantic patch proposals. Actions that
    need no refinement produce snapshot-protected execution proposals.
    """
    actions_by_id = {
        action.action_id: action
        for action in actions
    }

    proposals: List[Dict[str, Any]] = []
    proposal_type_counts: Dict[str, int] = {}

    groups = (
        consolidated.get("recommendations_by_action", [])
        if isinstance(consolidated, dict)
        else []
    )
    if not isinstance(groups, list):
        groups = []

    for group in groups:
        if not isinstance(group, dict):
            continue

        action_id = group.get("target_action_id")
        if not action_id:
            continue
        action = actions_by_id.get(str(action_id))
        if action is None:
            continue

        primary = group.get("primary_recommendation")
        secondary = group.get("secondary_recommendations", [])
        if not isinstance(secondary, list):
            secondary = []

        recommendations = (
            ([primary] if isinstance(primary, dict) else [])
            + [x for x in secondary if isinstance(x, dict)]
        )

        proposed_target_additions: List[str] = []
        proposed_success_criteria: List[str] = []
        proposed_rationale_extensions: List[str] = []
        source_recommendations: List[str] = []
        affected_principles: List[str] = []
        affected_signals: List[str] = []

        title_suffixes: List[str] = []

        for item in recommendations:
            rec_id = str(item.get("recommendation_id") or "")
            if rec_id and rec_id not in source_recommendations:
                source_recommendations.append(rec_id)

            principle_id = str(item.get("principle_id") or "")
            signal_type = str(item.get("signal_type") or "")
            rec_type = str(item.get("recommendation_type") or "")
            refinement = str(
                item.get("recommended_refinement") or ""
            ).strip()

            if principle_id and principle_id not in affected_principles:
                affected_principles.append(principle_id)
            if signal_type and signal_type not in affected_signals:
                affected_signals.append(signal_type)

            if rec_type == "add_missing_target":
                target = (
                    f"Explicitly test {signal_type} for {principle_id}"
                )
                if target not in proposed_target_additions:
                    proposed_target_additions.append(target)
                criterion = (
                    f"{principle_id}:{signal_type} has an explicit "
                    "pass/fail result under declared conditions"
                )
                if criterion not in proposed_success_criteria:
                    proposed_success_criteria.append(criterion)
                if principle_id not in title_suffixes:
                    title_suffixes.append(principle_id)

            elif rec_type == "extend_action_scope":
                target = (
                    f"Extend scope to cover {principle_id}:{signal_type}"
                )
                if target not in proposed_target_additions:
                    proposed_target_additions.append(target)
                criterion = (
                    f"Action reports scope-specific evidence for "
                    f"{principle_id}:{signal_type}"
                )
                if criterion not in proposed_success_criteria:
                    proposed_success_criteria.append(criterion)

            elif rec_type == "resolve_blocked_dependency":
                criterion = (
                    f"Blocking dependency for {principle_id}:{signal_type} "
                    "is resolved before execution"
                )
                if criterion not in proposed_success_criteria:
                    proposed_success_criteria.append(criterion)

            elif rec_type == "refine_existing_action":
                target = (
                    f"Add dedicated target for {principle_id}:{signal_type}"
                )
                if target not in proposed_target_additions:
                    proposed_target_additions.append(target)
                criterion = (
                    f"Dedicated evidence is produced for "
                    f"{principle_id}:{signal_type}"
                )
                if criterion not in proposed_success_criteria:
                    proposed_success_criteria.append(criterion)

            rationale_extension = (
                f"Consensus coverage refinement for "
                f"{principle_id}:{signal_type}. {refinement}"
            ).strip()
            if (
                rationale_extension
                and rationale_extension not in proposed_rationale_extensions
            ):
                proposed_rationale_extensions.append(
                    rationale_extension
                )

        proposed_title = action.title
        if title_suffixes:
            missing = [
                pid for pid in title_suffixes
                if pid.lower() not in action.title.lower()
            ]
            if missing:
                proposed_title = (
                    action.title + " [" + ", ".join(missing) + "]"
                )

        patch_ops: List[Dict[str, Any]] = []

        if proposed_title != action.title:
            patch_ops.append({
                "op": "replace",
                "field": "title",
                "current_value": action.title,
                "proposed_value": proposed_title,
            })
            proposal_type_counts["title"] = (
                proposal_type_counts.get("title", 0) + 1
            )

        if proposed_target_additions:
            patch_ops.append({
                "op": "append_unique",
                "field": "suggested_target",
                "current_value": action.suggested_target,
                "proposed_additions": proposed_target_additions,
            })
            proposal_type_counts["suggested_target"] = (
                proposal_type_counts.get("suggested_target", 0) + 1
            )

        if proposed_success_criteria:
            patch_ops.append({
                "op": "append_unique",
                "field": "done_when",
                "current_value": action.done_when,
                "proposed_additions": proposed_success_criteria,
            })
            proposal_type_counts["done_when"] = (
                proposal_type_counts.get("done_when", 0) + 1
            )

        if proposed_rationale_extensions:
            patch_ops.append({
                "op": "append_unique",
                "field": "rationale",
                "current_value": action.rationale,
                "proposed_additions": proposed_rationale_extensions,
            })
            proposal_type_counts["rationale"] = (
                proposal_type_counts.get("rationale", 0) + 1
            )

        if not patch_ops:
            continue

        proposals.append({
            "proposal_id": f"RAPP-{action.action_id}",
            "target_action_id": action.action_id,
            "target_action_title": action.title,
            "highest_priority": group.get("highest_priority"),
            "affected_principles": affected_principles,
            "affected_signals": affected_signals,
            "source_recommendations": source_recommendations,
            "patch_operations": patch_ops,
            "proposed_title": proposed_title,
            "proposed_target_additions": proposed_target_additions,
            "proposed_success_criteria": proposed_success_criteria,
            "proposed_rationale_extensions": proposed_rationale_extensions,
            "application_status": "NOT_APPLIED",
            "requires_review": True,
            "automatic_application": False,
        })

    represented_action_ids = {
        str(item.get("target_action_id") or "")
        for item in proposals
        if isinstance(item, dict)
    }
    for action in actions:
        if action.action_id in represented_action_ids:
            continue
        proposals.append(_direct_action_execution_proposal(action))
        proposal_type_counts["direct_action_execution"] = (
            proposal_type_counts.get("direct_action_execution", 0) + 1
        )

    priority_order = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }
    proposals.sort(
        key=lambda item: (
            priority_order.get(str(item.get("highest_priority")), 0),
            len(item.get("patch_operations", [])),
            str(item.get("target_action_id")),
        ),
        reverse=True,
    )

    return {
        "schema": "archon_recommendation_action_patch_proposals_v1",
        "available": bool(proposals),
        "proposal_count": len(proposals),
        "proposal_type_counts": proposal_type_counts,
        "proposals": proposals,
        "scientific_policy": {
            "proposal_only": True,
            "automatic_application": False,
            "modifies_existing_actions": False,
            "creates_research_actions": False,
            "changes_director_priority": False,
            "changes_strategic_score": False,
            "requires_human_review": True,
        },
    }


_REVISION_RE = re.compile(r"^(?P<root>.+?)(?:-R(?P<revision>\d+))?$")


def _research_action_snapshot(action: ResearchAction) -> Dict[str, Any]:
    return {
        "action_id": action.action_id,
        "title": action.title,
        "suggested_target": action.suggested_target,
        "done_when": action.done_when,
        "rationale": action.rationale,
    }


def _next_proposal_revision_id(source_proposal_id: str) -> str:
    match = _REVISION_RE.fullmatch(str(source_proposal_id or "").strip())
    if not match:
        return f"{source_proposal_id}-R2"
    root = str(match.group("root") or source_proposal_id)
    revision = int(match.group("revision") or 1) + 1
    return f"{root}-R{revision}"


def _proposal_from_active_recovery_override(
    action: ResearchAction,
    override: Dict[str, Any],
) -> Dict[str, Any] | None:
    """Rehydrate an already-applied recovery revision for provenance continuity."""
    proposal_id = str(override.get("source_proposal_id") or "")
    if not re.search(r"-R\d+$", proposal_id):
        return None
    bound = bound_principle_for_action(action.action_id)
    rollback = override.get("rollback_snapshot", {}) if isinstance(override, dict) else {}
    before = rollback.get("snapshot", {}) if isinstance(rollback, dict) else {}
    after = override.get("snapshot", {}) if isinstance(override, dict) else {}
    if not bound or not isinstance(before, dict) or not isinstance(after, dict):
        return None
    if canonical_json_hash(before) != rollback.get("snapshot_hash"):
        return None
    if canonical_json_hash(after) != override.get("snapshot_hash"):
        return None
    if canonical_json_hash(_research_action_snapshot(action)) != override.get("snapshot_hash"):
        return None
    if validate_snapshot_transition(action.action_id, before, after):
        return None

    operations: List[Dict[str, Any]] = []
    for field_name in ("title", "suggested_target", "done_when", "rationale"):
        if before.get(field_name) == after.get(field_name):
            continue
        operations.append({
            "op": "replace",
            "field": field_name,
            "current_value": after.get(field_name),
            "proposed_value": after.get(field_name),
        })
    if not operations:
        return None
    return {
        "proposal_id": proposal_id,
        "target_action_id": action.action_id,
        "target_action_title": action.title,
        "highest_priority": action.urgency or "HIGH",
        "affected_principles": [bound],
        "affected_signals": ["scientific_target_integrity_recovery"],
        "source_recommendations": [],
        "patch_operations": operations,
        "proposed_title": action.title,
        "proposed_target_additions": [],
        "proposed_success_criteria": [],
        "proposed_rationale_extensions": [],
        "application_status": "ALREADY_APPLIED",
        "requires_review": True,
        "automatic_application": False,
        "revision_kind": "SCIENTIFIC_TARGET_INTEGRITY_RECOVERY",
        "supersedes_proposal_id": None,
        "recovery_application_id": override.get("application_id"),
    }


def build_integrity_recovery_revisions(
    patch_bundle: Dict[str, Any],
    actions: List[ResearchAction],
    patch_state: Dict[str, Any],
    integrity_rejections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mint a clean review revision after a quarantined cross-GP override.

    The revision is deliberately not a replay of current Consensus patch
    recommendations.  It is a narrowly-scoped, human-reviewed recovery patch
    that records target-integrity revalidation on the action's own principle.
    The old proposal remains historical and its prior approval is not reusable.
    """
    bundle = deepcopy(patch_bundle) if isinstance(patch_bundle, dict) else {}
    proposals = [
        deepcopy(x) for x in bundle.get("proposals", [])
        if isinstance(x, dict)
    ]
    superseded = [
        deepcopy(x) for x in bundle.get("superseded_proposals", [])
        if isinstance(x, dict)
    ]
    actions_by_id = {action.action_id: action for action in actions}
    overrides = [
        x for x in (patch_state.get("overrides", []) if isinstance(patch_state, dict) else [])
        if isinstance(x, dict)
    ]
    incident_actions = {
        str(x.get("action_id") or "")
        for x in integrity_rejections
        if isinstance(x, dict) and x.get("action_id")
    }
    revisions: List[Dict[str, Any]] = []
    refusals: List[Dict[str, Any]] = []

    # Keep an applied recovery revision addressable on subsequent Director runs
    # so the planner can still resolve the approved proposal provenance.
    for override in overrides:
        action_id = str(override.get("action_id") or "")
        if not action_id or action_id in incident_actions:
            continue
        action = actions_by_id.get(action_id)
        if action is None:
            continue
        active = _proposal_from_active_recovery_override(action, override)
        if active is None:
            continue
        displaced = [x for x in proposals if str(x.get("target_action_id") or "") == action_id]
        for old in displaced:
            historical = deepcopy(old)
            historical["superseded_by_proposal_id"] = active["proposal_id"]
            historical["supersession_reason"] = "ACTIVE_INTEGRITY_RECOVERY_REVISION"
            superseded.append(historical)
        proposals = [x for x in proposals if str(x.get("target_action_id") or "") != action_id]
        proposals.append(active)
        revisions.append({
            "proposal_id": active["proposal_id"],
            "action_id": action_id,
            "status": "ACTIVE_RECOVERY_REVISION",
        })

    for rejection in integrity_rejections:
        if not isinstance(rejection, dict):
            continue
        action_id = str(rejection.get("action_id") or "")
        source_proposal_id = str(rejection.get("source_proposal_id") or "")
        action = actions_by_id.get(action_id)
        bound = bound_principle_for_action(action_id)
        override = next((
            x for x in overrides
            if str(x.get("action_id") or "") == action_id
            and str(x.get("source_proposal_id") or "") == source_proposal_id
        ), None)
        if action is None or not bound or override is None or not source_proposal_id:
            refusals.append({"action_id": action_id or None, "reason": "RECOVERY_CONTEXT_INCOMPLETE"})
            continue
        rollback = override.get("rollback_snapshot", {}) if isinstance(override, dict) else {}
        clean_snapshot = rollback.get("snapshot", {}) if isinstance(rollback, dict) else {}
        clean_hash = rollback.get("snapshot_hash") if isinstance(rollback, dict) else None
        current_snapshot = _research_action_snapshot(action)
        if (
            not isinstance(clean_snapshot, dict)
            or canonical_json_hash(clean_snapshot) != clean_hash
            or canonical_json_hash(current_snapshot) != clean_hash
        ):
            refusals.append({
                "action_id": action_id,
                "source_proposal_id": source_proposal_id,
                "reason": "CURRENT_ACTION_DOES_NOT_MATCH_VERIFIED_ROLLBACK_SNAPSHOT",
            })
            continue

        revision_id = _next_proposal_revision_id(source_proposal_id)
        note = (
            f"Scientific target integrity revalidated for {bound}; prior invalid "
            "cross-principle override remains quarantined and is not reused."
        )
        displaced = [x for x in proposals if str(x.get("target_action_id") or "") == action_id]
        for old in displaced:
            historical = deepcopy(old)
            historical["superseded_by_proposal_id"] = revision_id
            historical["supersession_reason"] = "SCIENTIFIC_TARGET_INTEGRITY_INCIDENT"
            superseded.append(historical)
        proposals = [x for x in proposals if str(x.get("target_action_id") or "") != action_id]
        revision = {
            "proposal_id": revision_id,
            "target_action_id": action_id,
            "target_action_title": action.title,
            "highest_priority": max(
                [str(x.get("highest_priority") or "MEDIUM") for x in displaced] or [str(action.urgency or "HIGH")],
                key=lambda value: {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(value, 0),
            ),
            "affected_principles": [bound],
            "affected_signals": ["scientific_target_integrity_recovery"],
            "source_recommendations": [],
            "patch_operations": [{
                "op": "append_unique",
                "field": "rationale",
                "current_value": action.rationale,
                "proposed_additions": [note],
            }],
            "proposed_title": action.title,
            "proposed_target_additions": [],
            "proposed_success_criteria": [],
            "proposed_rationale_extensions": [note],
            "application_status": "NOT_APPLIED",
            "requires_review": True,
            "automatic_application": False,
            "revision_kind": "SCIENTIFIC_TARGET_INTEGRITY_RECOVERY",
            "supersedes_proposal_id": source_proposal_id,
            "clean_snapshot_hash": clean_hash,
            "quarantined_application_id": override.get("application_id"),
        }
        proposals.append(revision)
        revisions.append({
            "proposal_id": revision_id,
            "action_id": action_id,
            "status": "PENDING_EXPLICIT_REVIEW",
            "supersedes_proposal_id": source_proposal_id,
        })

    # Deduplicate historical entries by proposal ID + superseding revision.
    seen = set()
    unique_superseded = []
    for item in superseded:
        key = (str(item.get("proposal_id") or ""), str(item.get("superseded_by_proposal_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique_superseded.append(item)

    bundle["proposals"] = proposals
    bundle["proposal_count"] = len(proposals)
    bundle["available"] = bool(proposals)
    if unique_superseded:
        bundle["superseded_proposals"] = unique_superseded
    if revisions or refusals:
        bundle["integrity_recovery"] = {
            "schema": "archon_scientific_target_integrity_recovery_v1",
            "revision_count": len(revisions),
            "revisions": revisions,
            "refusal_count": len(refusals),
            "refusals": refusals,
            "scientific_policy": {
                "prior_approval_reused": False,
                "explicit_new_review_required": True,
                "quarantined_override_replayed": False,
                "cross_principle_semantics_added": False,
            },
        }
    return bundle


def promote_redundant_ready_proposals_to_direct_execution(
    patch_bundle: Dict[str, Any],
    validation: Dict[str, Any],
    actions: List[ResearchAction],
    decisions: Dict[str, Any],
) -> Dict[str, Any]:
    """Preserve action continuity when a semantic patch is already satisfied.

    BRIDGE5.8.3 separates two different statements that previously collapsed
    into one REDUNDANT status:

    * the Consensus-derived *patch* is redundant because its requested text is
      already present in the current ResearchAction;
    * the underlying ResearchAction may still be canonical, execution-ready,
      and awaiting explicit human review.

    Only proposals with no persisted human decision are promoted.  Existing
    APPROVED/REJECTED/DEFERRED decisions are never reinterpreted under changed
    proposal semantics.  Promotion keeps the proposal ID stable for OL2
    continuity, replaces the no-op patch with a snapshot-protected direct-action
    activation, and records the discarded patch hash for provenance.
    """
    bundle = deepcopy(patch_bundle) if isinstance(patch_bundle, dict) else {}
    proposals = bundle.get("proposals", [])
    if not isinstance(proposals, list):
        proposals = []

    validations = {
        str(row.get("proposal_id")): row
        for row in (
            validation.get("validations", [])
            if isinstance(validation, dict)
            else []
        )
        if isinstance(row, dict) and row.get("proposal_id")
    }
    actions_by_id = {action.action_id: action for action in actions}
    decided_ids = {
        str(row.get("proposal_id"))
        for row in (
            decisions.get("records", [])
            if isinstance(decisions, dict)
            else []
        )
        if isinstance(row, dict)
        and row.get("proposal_id")
        and str(row.get("decision") or "").strip().upper()
        not in {"", "PENDING_REVIEW"}
    }

    promoted: List[Dict[str, Any]] = []
    output: List[Dict[str, Any]] = []
    benign_issue_types = {
        "already_satisfied",
        "duplicate_additions",
        "duplicate_field_operations",
    }

    for raw in proposals:
        if not isinstance(raw, dict):
            continue
        proposal = deepcopy(raw)
        proposal_id = str(proposal.get("proposal_id") or "")
        action_id = str(proposal.get("target_action_id") or "")
        row = validations.get(proposal_id, {})
        action = actions_by_id.get(action_id)
        issue_types = {
            str(issue.get("type") or "")
            for issue in (row.get("issues", []) if isinstance(row, dict) else [])
            if isinstance(issue, dict)
        }
        eligible = (
            action is not None
            and str(proposal.get("proposal_kind") or "PATCH")
            != DIRECT_ACTION_EXECUTION
            and str(row.get("status") or "").upper() == "REDUNDANT"
            and bool(issue_types)
            and issue_types.issubset(benign_issue_types)
            and str(action.execution_readiness or "UNKNOWN").upper() == "READY"
            and proposal_id not in decided_ids
        )
        if not eligible:
            output.append(proposal)
            continue

        direct = _direct_action_execution_proposal(action)
        direct["proposal_id"] = proposal_id
        direct["highest_priority"] = (
            proposal.get("highest_priority") or direct.get("highest_priority")
        )
        direct["source_recommendations"] = list(
            proposal.get("source_recommendations", []) or []
        )
        direct["affected_principles"] = list(
            proposal.get("affected_principles", []) or direct.get("affected_principles", [])
        )
        direct["affected_signals"] = list(
            proposal.get("affected_signals", []) or direct.get("affected_signals", [])
        )
        direct["semantic_patch_disposition"] = {
            "status": "ALREADY_SATISFIED",
            "source_proposal_hash": canonical_json_hash(proposal),
            "source_patch_operation_count": len(
                proposal.get("patch_operations", [])
                if isinstance(proposal.get("patch_operations"), list)
                else []
            ),
            "promotion_reason": (
                "Semantic refinement is already present, but the canonical "
                "ResearchAction remains execution-ready and still requires "
                "explicit human activation review."
            ),
        }
        output.append(direct)
        promoted.append({
            "proposal_id": proposal_id,
            "target_action_id": action_id,
            "source_proposal_hash": canonical_json_hash(proposal),
        })

    bundle["proposals"] = output
    bundle["proposal_count"] = len(output)
    if promoted:
        bundle["redundant_patch_execution_promotions"] = {
            "schema": "archon_redundant_patch_execution_promotion_v1",
            "count": len(promoted),
            "promotions": promoted,
            "scientific_policy": {
                "reuses_prior_human_decision": False,
                "changes_research_action": False,
                "changes_execution_readiness": False,
                "requires_explicit_review": True,
            },
        }
    return bundle

def validate_patch_proposals(
    patch_bundle: Dict[str, Any],
    actions: List[ResearchAction],
    recommendation_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate patch proposals and detect structural or semantic conflicts."""
    actions_by_id = {
        action.action_id: action
        for action in actions
    }
    recommendation_by_id = {
        str(item.get("recommendation_id")): item
        for item in (
            recommendation_bundle.get("recommendations", [])
            if isinstance(recommendation_bundle, dict)
            else []
        )
        if isinstance(item, dict) and item.get("recommendation_id")
    }

    proposals = (
        patch_bundle.get("proposals", [])
        if isinstance(patch_bundle, dict)
        else []
    )
    if not isinstance(proposals, list):
        proposals = []

    validation_rows: List[Dict[str, Any]] = []
    status_counts = {
        "VALID": 0,
        "REDUNDANT": 0,
        "CONFLICTING": 0,
        "BLOCKED": 0,
        "INVALID_TARGET": 0,
    }

    # Track cross-proposal operations with enough semantics to distinguish
    # merge-safe append_unique additions from true conflicting replacements.
    # The previous value-only set treated two different additive suggestions
    # as mutually exclusive, which stranded mergeable experiment proposals in
    # CONFLICTING/NEEDS_REVISION forever.
    seen_field_operations: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue

        proposal_id = str(proposal.get("proposal_id") or "UNKNOWN")
        action_id = str(proposal.get("target_action_id") or "")
        action = actions_by_id.get(action_id)

        issues: List[Dict[str, Any]] = []
        operations = proposal.get("patch_operations", [])
        if not isinstance(operations, list):
            operations = []
        proposal_kind = str(proposal.get("proposal_kind") or "PATCH")
        direct_action = proposal_kind == DIRECT_ACTION_EXECUTION

        if action is None:
            issues.append({
                "type": "invalid_target",
                "severity": "ERROR",
                "message": f"Target action {action_id or '-'} does not exist.",
            })
        else:
            readiness = str(action.execution_readiness or "UNKNOWN").upper()
            if readiness == "SUPERSEDED":
                issues.append({
                    "type": "action_superseded",
                    "severity": "INFO",
                    "superseded_by_action_id": action.superseded_by_action_id,
                    "message": (
                        action.execution_readiness_reason
                        or (
                            f"{action.action_id} is superseded by "
                            f"{action.superseded_by_action_id or 'a canonical action'}."
                        )
                    ),
                })
            elif readiness == "WAITING_FOR_TARGET":
                issues.append({
                    "type": "execution_target_unresolved",
                    "severity": "WARNING",
                    "message": (
                        action.execution_readiness_reason
                        or (
                            f"{action.action_id} has no concrete precommitted "
                            "target rules for materialization."
                        )
                    ),
                })
            elif readiness == "NEEDS_REVISION":
                issues.append({
                    "type": "execution_design_revision_required",
                    "severity": "WARNING",
                    "message": (
                        action.execution_readiness_reason
                        or (
                            f"{action.action_id} requires a revised ScientificTarget "
                            "before it can be materialized."
                        )
                    ),
                })
            issues.extend(validate_proposal_principles(
                action_id,
                proposal.get("affected_principles", []),
            ))
            if direct_action:
                snapshot = proposal.get("action_snapshot")
                snapshot_hash = proposal.get("action_snapshot_hash")
                actual_snapshot = _research_action_snapshot(action)
                if operations:
                    issues.append({
                        "type": "direct_action_has_patch_operations",
                        "severity": "ERROR",
                        "message": (
                            "A direct action execution proposal must not "
                            "contain semantic patch operations."
                        ),
                    })
                if (
                    not isinstance(snapshot, dict)
                    or canonical_json_hash(snapshot) != snapshot_hash
                    or snapshot != actual_snapshot
                ):
                    issues.append({
                        "type": "direct_action_snapshot_mismatch",
                        "severity": "ERROR",
                        "message": (
                            "The direct action proposal no longer matches the "
                            "current immutable ResearchAction snapshot."
                        ),
                    })
                missing = [
                    field_name
                    for field_name in (
                        "title",
                        "suggested_target",
                        "done_when",
                        "rationale",
                    )
                    if not str(actual_snapshot.get(field_name) or "").strip()
                ]
                if missing:
                    issues.append({
                        "type": "direct_action_incomplete",
                        "severity": "ERROR",
                        "fields": missing,
                        "message": (
                            "The Director action is visible but cannot enter "
                            "planner intake until its scientific intent is "
                            "complete."
                        ),
                    })

        source_ids = [
            str(x) for x in proposal.get("source_recommendations", [])
            if x
        ]
        source_recommendations = [
            recommendation_by_id[x]
            for x in source_ids
            if x in recommendation_by_id
        ]
        if source_ids and not source_recommendations:
            issues.append({
                "type": "missing_sources",
                "severity": "ERROR",
                "message": "No source recommendation IDs could be resolved.",
            })

        only_blocked = bool(source_recommendations) and all(
            str(item.get("reconciliation_status")) == "blocked"
            for item in source_recommendations
        )
        if only_blocked:
            issues.append({
                "type": "blocked_source_only",
                "severity": "WARNING",
                "message": (
                    "Proposal is based only on blocked Consensus signals and "
                    "must not be applied before dependencies are resolved."
                ),
            })

        field_ops: Dict[str, List[Dict[str, Any]]] = {}
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            field_name = str(operation.get("field") or "")
            field_ops.setdefault(field_name, []).append(operation)

        for field_name, ops in field_ops.items():
            if len(ops) > 1:
                normalized_values = set()
                for op in ops:
                    if op.get("op") == "replace":
                        normalized_values.add(str(op.get("proposed_value")))
                    else:
                        normalized_values.add(
                            "|".join(
                                sorted(
                                    str(x)
                                    for x in op.get("proposed_additions", [])
                                )
                            )
                        )
                if len(normalized_values) > 1:
                    issues.append({
                        "type": "conflicting_field_operations",
                        "severity": "ERROR",
                        "field": field_name,
                        "message": (
                            f"Multiple conflicting operations target {field_name}."
                        ),
                    })
                else:
                    issues.append({
                        "type": "duplicate_field_operations",
                        "severity": "WARNING",
                        "field": field_name,
                        "message": (
                            f"Duplicate equivalent operations target {field_name}."
                        ),
                    })

        if action is not None:
            current_values = {
                "title": action.title,
                "suggested_target": action.suggested_target or "",
                "done_when": action.done_when or "",
                "rationale": action.rationale,
            }
            proposed_values = dict(current_values)
            for operation in operations:
                if not isinstance(operation, dict):
                    continue
                field_name = str(operation.get("field") or "")
                if field_name not in proposed_values:
                    continue
                op_type = str(operation.get("op") or "")
                before_value = str(proposed_values.get(field_name, ""))
                if op_type == "replace":
                    proposed_values[field_name] = str(
                        operation.get("proposed_value") or ""
                    )
                elif op_type == "append_unique":
                    additions = [
                        str(x).strip()
                        for x in operation.get("proposed_additions", [])
                        if str(x).strip()
                    ]
                    new_items = [
                        item for item in additions
                        if item.lower() not in before_value.lower()
                    ]
                    separator = "\n" if before_value.strip() and new_items else ""
                    proposed_values[field_name] = (
                        before_value + separator + "\n".join(new_items)
                    )
            issues.extend(validate_snapshot_transition(
                action_id,
                current_values,
                proposed_values,
            ))

            for operation in operations:
                if not isinstance(operation, dict):
                    continue

                field_name = str(operation.get("field") or "")
                op_type = str(operation.get("op") or "")
                current = str(current_values.get(field_name, ""))

                if op_type == "replace":
                    proposed = str(operation.get("proposed_value") or "")
                    if proposed == current:
                        issues.append({
                            "type": "already_satisfied",
                            "severity": "INFO",
                            "field": field_name,
                            "message": (
                                f"Replacement for {field_name} already matches "
                                "the current value."
                            ),
                        })

                    key = (action_id, field_name)
                    seen_field_operations.setdefault(key, []).append({
                        "proposal_id": proposal_id,
                        "op": "replace",
                        "values": (proposed,),
                    })

                elif op_type == "append_unique":
                    additions = [
                        str(x).strip()
                        for x in operation.get("proposed_additions", [])
                        if str(x).strip()
                    ]
                    duplicates = [
                        item for item in additions
                        if item.lower() in current.lower()
                    ]
                    if duplicates:
                        issues.append({
                            "type": "already_satisfied",
                            "severity": "INFO",
                            "field": field_name,
                            "message": (
                                f"{len(duplicates)} proposed addition(s) are "
                                f"already present in {field_name}."
                            ),
                        })

                    normalized = [item.lower() for item in additions]
                    if len(normalized) != len(set(normalized)):
                        issues.append({
                            "type": "duplicate_additions",
                            "severity": "WARNING",
                            "field": field_name,
                            "message": (
                                f"Duplicate additions were proposed for {field_name}."
                            ),
                        })

                    key = (action_id, field_name)
                    seen_field_operations.setdefault(key, []).append({
                        "proposal_id": proposal_id,
                        "op": "append_unique",
                        "values": tuple(additions),
                    })

                else:
                    issues.append({
                        "type": "unsupported_operation",
                        "severity": "ERROR",
                        "field": field_name,
                        "message": f"Unsupported patch operation: {op_type or '-'}",
                    })

        severities = {str(item.get("severity")) for item in issues}
        issue_types = {str(item.get("type")) for item in issues}

        if "invalid_target" in issue_types:
            status = "INVALID_TARGET"
        elif "direct_action_incomplete" in issue_types:
            status = "BLOCKED"
        elif "ERROR" in severities:
            status = "CONFLICTING"
        elif "action_superseded" in issue_types:
            status = "REDUNDANT"
        elif "execution_target_unresolved" in issue_types:
            status = "BLOCKED"
        elif "execution_design_revision_required" in issue_types:
            status = "BLOCKED"
        elif only_blocked:
            status = "BLOCKED"
        elif issues and all(
            item.get("type") in {
                "already_satisfied",
                "duplicate_additions",
                "duplicate_field_operations",
            }
            for item in issues
        ):
            status = "REDUNDANT"
        else:
            status = "VALID"

        status_counts[status] += 1
        validation_rows.append({
            "proposal_id": proposal_id,
            "proposal_kind": proposal_kind,
            "target_action_id": action_id or None,
            "status": status,
            "issue_count": len(issues),
            "issues": issues,
            "source_recommendation_count": len(source_recommendations),
            "blocked_source_only": only_blocked,
            "validated_operation_count": len(operations),
            "application_allowed": status == "VALID",
            "requires_review": True,
            "execution_readiness": (
                str(action.execution_readiness or "UNKNOWN")
                if action is not None
                else "UNKNOWN"
            ),
            "superseded_by_action_id": (
                action.superseded_by_action_id
                if action is not None
                else None
            ),
        })

    # Detect only *semantic* cross-proposal conflicts.  Independent
    # append_unique operations are a set-union and are therefore merge-safe.
    # Different replace values remain conflicting, as does mixing replace and
    # append semantics across proposals because ordering would be ambiguous.
    cross_conflicts: List[Dict[str, Any]] = []
    for (action_id, field_name), records in seen_field_operations.items():
        proposal_ids = sorted({
            str(item.get("proposal_id") or "")
            for item in records
            if item.get("proposal_id")
        })
        if len(proposal_ids) < 2:
            continue
        op_types = {str(item.get("op") or "") for item in records}
        flattened_values = sorted({
            str(value)
            for item in records
            for value in item.get("values", ())
        })

        conflict_reason = None
        if op_types == {"append_unique"}:
            # Different additions can be unioned deterministically.
            continue
        if op_types == {"replace"}:
            if len(flattened_values) <= 1:
                continue
            conflict_reason = "DIFFERENT_REPLACEMENT_VALUES"
        else:
            conflict_reason = "MIXED_OPERATION_TYPES"

        cross_conflicts.append({
            "action_id": action_id,
            "field": field_name,
            "values": flattened_values,
            "proposal_ids": proposal_ids,
            "operation_types": sorted(op_types),
            "reason": conflict_reason,
            "message": (
                "Multiple proposals require mutually exclusive semantics for "
                f"{action_id}.{field_name}."
            ),
        })

    if cross_conflicts:
        affected_proposals = {
            proposal_id
            for item in cross_conflicts
            for proposal_id in item.get("proposal_ids", [])
        }
        conflict_fields_by_proposal: Dict[str, List[str]] = {}
        for item in cross_conflicts:
            for proposal_id in item.get("proposal_ids", []):
                conflict_fields_by_proposal.setdefault(proposal_id, []).append(
                    str(item.get("field") or "")
                )
        for row in validation_rows:
            proposal_id = str(row.get("proposal_id") or "")
            if proposal_id in affected_proposals and row.get("status") == "VALID":
                fields = sorted(set(conflict_fields_by_proposal.get(proposal_id, [])))
                row["status"] = "CONFLICTING"
                row["application_allowed"] = False
                row["issues"].append({
                    "type": "cross_proposal_conflict",
                    "severity": "ERROR",
                    "field": ",".join(fields) if fields else None,
                    "message": (
                        "Another proposal requires incompatible semantics for "
                        + (", ".join(fields) if fields else "the same action field")
                        + "."
                    ),
                })
                status_counts["VALID"] -= 1
                status_counts["CONFLICTING"] += 1

    return {
        "schema": "archon_patch_proposal_validation_v1",
        "available": bool(validation_rows),
        "proposal_count": len(validation_rows),
        "status_counts": status_counts,
        "cross_proposal_conflict_count": len(cross_conflicts),
        "cross_proposal_conflicts": cross_conflicts,
        "validations": validation_rows,
        "scientific_policy": {
            "validation_only": True,
            "automatic_application": False,
            "modifies_existing_actions": False,
            "creates_research_actions": False,
            "changes_director_priority": False,
            "changes_strategic_score": False,
            "requires_human_review": True,
        },
    }

def build_patch_conflict_resolution_plan(
    validation: Dict[str, Any],
    patch_bundle: Dict[str, Any],
    recommendation_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    """Explain conflicting/blocked proposals and propose safe resolutions."""
    proposals_by_id = {
        str(item.get("proposal_id")): item
        for item in (
            patch_bundle.get("proposals", [])
            if isinstance(patch_bundle, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }
    recommendations_by_id = {
        str(item.get("recommendation_id")): item
        for item in (
            recommendation_bundle.get("recommendations", [])
            if isinstance(recommendation_bundle, dict)
            else []
        )
        if isinstance(item, dict) and item.get("recommendation_id")
    }

    validations = (
        validation.get("validations", [])
        if isinstance(validation, dict)
        else []
    )
    if not isinstance(validations, list):
        validations = []

    plans: List[Dict[str, Any]] = []
    resolution_type_counts: Dict[str, int] = {}
    manual_decision_count = 0
    merge_possible_count = 0

    for row in validations:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "")
        if status not in {"CONFLICTING", "BLOCKED"}:
            continue

        proposal_id = str(row.get("proposal_id") or "")
        proposal = proposals_by_id.get(proposal_id, {})
        issues = row.get("issues", [])
        if not isinstance(issues, list):
            issues = []

        conflict_fields = sorted({
            str(issue.get("field"))
            for issue in issues
            if issue.get("field")
        })
        issue_types = sorted({
            str(issue.get("type"))
            for issue in issues
            if issue.get("type")
        })

        source_ids = [
            str(x)
            for x in proposal.get("source_recommendations", [])
            if x
        ]
        source_recommendations = [
            recommendations_by_id[x]
            for x in source_ids
            if x in recommendations_by_id
        ]

        blocked_dependencies: List[str] = []
        for item in source_recommendations:
            if str(item.get("reconciliation_status")) == "blocked":
                blocked_dependencies.append(
                    str(item.get("signal_type") or "unknown")
                )

        competing_values: Dict[str, List[str]] = {}
        for operation in proposal.get("patch_operations", []) or []:
            if not isinstance(operation, dict):
                continue
            field_name = str(operation.get("field") or "")
            if operation.get("op") == "replace":
                values = [str(operation.get("proposed_value") or "")]
            else:
                values = [
                    str(x)
                    for x in operation.get("proposed_additions", [])
                    if x
                ]
            if field_name:
                competing_values.setdefault(field_name, []).extend(values)

        for field_name, values in list(competing_values.items()):
            competing_values[field_name] = sorted(set(values))

        if status == "BLOCKED":
            resolution_type = "RESOLVE_DEPENDENCY_THEN_REVALIDATE"
            preferred_resolution = (
                "Keep the proposal unchanged but defer it until all blocked "
                "Consensus dependencies are resolved, then rerun validation."
            )
            merge_possible = False
            manual_decision_required = False
            post_resolution_status = "REVALIDATE"
        else:
            only_additive = bool(proposal.get("patch_operations")) and all(
                isinstance(op, dict)
                and op.get("op") == "append_unique"
                for op in proposal.get("patch_operations", [])
            )
            if only_additive and "cross_proposal_conflict" not in issue_types:
                resolution_type = "MERGE_DEDUPLICATE_ADDITIONS"
                preferred_resolution = (
                    "Merge additive values, remove duplicates, preserve source "
                    "recommendation provenance, then revalidate the proposal."
                )
                merge_possible = True
                manual_decision_required = False
                post_resolution_status = "REVALIDATE"
            elif only_additive:
                resolution_type = "MERGE_WITH_MANUAL_FIELD_REVIEW"
                preferred_resolution = (
                    "Merge non-conflicting additions, but manually review fields "
                    "that are also targeted by another proposal."
                )
                merge_possible = True
                manual_decision_required = True
                post_resolution_status = "MANUAL_REVIEW"
            else:
                resolution_type = "SELECT_PREFERRED_VALUE"
                preferred_resolution = (
                    "Choose one value per conflicting field using the highest-"
                    "priority source recommendation and discard competing values."
                )
                merge_possible = False
                manual_decision_required = True
                post_resolution_status = "MANUAL_REVIEW"

        if manual_decision_required:
            manual_decision_count += 1
        if merge_possible:
            merge_possible_count += 1
        resolution_type_counts[resolution_type] = (
            resolution_type_counts.get(resolution_type, 0) + 1
        )

        plans.append({
            "resolution_id": f"RPLAN-{proposal_id}",
            "proposal_id": proposal_id,
            "target_action_id": proposal.get("target_action_id"),
            "current_status": status,
            "issue_types": issue_types,
            "conflicting_fields": conflict_fields,
            "competing_proposed_values": competing_values,
            "source_recommendations": source_ids,
            "blocked_dependencies": sorted(set(blocked_dependencies)),
            "resolution_type": resolution_type,
            "preferred_resolution": preferred_resolution,
            "merge_possible": merge_possible,
            "manual_decision_required": manual_decision_required,
            "post_resolution_status": post_resolution_status,
            "automatic_resolution": False,
            "application_allowed": False,
        })

    plans.sort(
        key=lambda item: (
            str(item.get("current_status")) == "CONFLICTING",
            bool(item.get("manual_decision_required")),
            len(item.get("conflicting_fields", [])),
            str(item.get("proposal_id")),
        ),
        reverse=True,
    )

    return {
        "schema": "archon_patch_conflict_resolution_plan_v1",
        "available": bool(plans),
        "problem_proposal_count": len(plans),
        "manual_decision_count": manual_decision_count,
        "merge_possible_count": merge_possible_count,
        "resolution_type_counts": resolution_type_counts,
        "plans": plans,
        "scientific_policy": {
            "explanation_only": True,
            "automatic_resolution": False,
            "automatic_application": False,
            "modifies_existing_actions": False,
            "changes_director_priority": False,
            "changes_strategic_score": False,
            "requires_human_review_when_flagged": True,
        },
    }
