"""Human-review queue, validation, and editing models."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from Analyzer_next.research.director.common import load_json, now_iso

VALID_REVIEW_DECISIONS = {
    "PENDING_REVIEW",
    "APPROVED",
    "REJECTED",
    "DEFERRED",
    "NEEDS_REVISION",
}

VALID_REVIEW_TRANSITIONS = {
    "PENDING_REVIEW": {
        "APPROVED",
        "REJECTED",
        "DEFERRED",
        "NEEDS_REVISION",
        "PENDING_REVIEW",
    },
    "NEEDS_REVISION": {
        "PENDING_REVIEW",
        "APPROVED",
        "REJECTED",
        "DEFERRED",
        "NEEDS_REVISION",
    },
    "DEFERRED": {
        "PENDING_REVIEW",
        "APPROVED",
        "REJECTED",
        "NEEDS_REVISION",
        "DEFERRED",
    },
    "APPROVED": {
        "APPROVED",
        "NEEDS_REVISION",
        "REJECTED",
    },
    "REJECTED": {
        "REJECTED",
        "PENDING_REVIEW",
        "NEEDS_REVISION",
    },
}

IMMUTABLE_REVIEW_FIELDS = {
    "review_id",
    "proposal_id",
    "review_priority",
    "validation_status",
    "preferred_resolution",
}

EDITABLE_REVIEW_FIELDS = {
    "current_decision",
    "decision_reason",
    "reviewed_at",
    "reviewed_by",
    "selected_resolution",
    "revision_notes",
}

def load_human_review_decisions(root: Path) -> Dict[str, Any]:
    """Load persistent human review decisions if present."""
    data = load_json(root / "human_review_decisions.json", {})
    if not isinstance(data, dict):
        data = {}

    records = data.get("records", [])
    if not isinstance(records, list):
        records = []

    normalized: List[Dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        decision = str(
            item.get("decision") or "PENDING_REVIEW"
        ).upper()
        if decision not in VALID_REVIEW_DECISIONS:
            decision = "PENDING_REVIEW"

        normalized.append({
            "review_id": str(item.get("review_id") or ""),
            "proposal_id": str(item.get("proposal_id") or ""),
            "decision": decision,
            "decision_reason": str(
                item.get("decision_reason") or ""
            ),
            "reviewed_at": item.get("reviewed_at"),
            "reviewed_by": item.get("reviewed_by"),
            "selected_resolution": item.get(
                "selected_resolution"
            ),
            "revision_notes": item.get("revision_notes"),
            "application_status": "NOT_APPLIED",
        })

    return {
        "schema": "archon_human_review_decisions_v1",
        "source": str(root / "human_review_decisions.json"),
        "record_count": len(normalized),
        "records": normalized,
        "scientific_policy": {
            "approval_does_not_apply_patch": True,
            "automatic_application": False,
        },
    }

def build_human_review_queue(
    patch_bundle: Dict[str, Any],
    validation: Dict[str, Any],
    resolution_plan: Dict[str, Any],
    decisions: Dict[str, Any],
    invalidated_proposal_ids: set[str] | None = None,
) -> Dict[str, Any]:
    """Build a review queue and merge any existing human decisions."""
    proposals_by_id = {
        str(item.get("proposal_id")): item
        for item in (
            patch_bundle.get("proposals", [])
            if isinstance(patch_bundle, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }
    validations_by_id = {
        str(item.get("proposal_id")): item
        for item in (
            validation.get("validations", [])
            if isinstance(validation, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }
    resolutions_by_id = {
        str(item.get("proposal_id")): item
        for item in (
            resolution_plan.get("plans", [])
            if isinstance(resolution_plan, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }
    decisions_by_proposal = {
        str(item.get("proposal_id")): item
        for item in (
            decisions.get("records", [])
            if isinstance(decisions, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }

    invalidated = {
        str(x) for x in (invalidated_proposal_ids or set()) if str(x)
    }

    queue: List[Dict[str, Any]] = []
    decision_counts = {
        "PENDING_REVIEW": 0,
        "APPROVED": 0,
        "REJECTED": 0,
        "DEFERRED": 0,
        "NEEDS_REVISION": 0,
    }

    for proposal_id, proposal in proposals_by_id.items():
        validation_row = validations_by_id.get(proposal_id, {})
        resolution_row = resolutions_by_id.get(proposal_id, {})
        decision_row = decisions_by_proposal.get(proposal_id)

        validation_status = str(
            validation_row.get("status") or "UNKNOWN"
        )

        decision_reuse_blocked = proposal_id in invalidated
        if decision_reuse_blocked:
            # Keep the persisted historical decision untouched, but require a
            # fresh explicit review for the corrected proposal semantics.
            decision = "NEEDS_REVISION"
        elif decision_row:
            decision = str(
                decision_row.get("decision")
                or "PENDING_REVIEW"
            )
        else:
            decision = "PENDING_REVIEW"

        decision_counts[decision] = (
            decision_counts.get(decision, 0) + 1
        )

        review_priority = str(
            proposal.get("highest_priority") or "MEDIUM"
        )
        if validation_status in {
            "CONFLICTING",
            "INVALID_TARGET",
        }:
            review_priority = "CRITICAL"
        elif validation_status == "BLOCKED":
            review_priority = "HIGH"

        queue.append({
            "review_id": f"HRQ-{proposal_id}",
            "proposal_id": proposal_id,
            "target_action_id": proposal.get(
                "target_action_id"
            ),
            "target_action_title": proposal.get(
                "target_action_title"
            ),
            "review_priority": review_priority,
            "validation_status": validation_status,
            "issue_count": validation_row.get(
                "issue_count", 0
            ),
            "resolution_type": resolution_row.get(
                "resolution_type"
            ),
            "preferred_resolution": resolution_row.get(
                "preferred_resolution"
            ),
            "merge_possible": resolution_row.get(
                "merge_possible", False
            ),
            "manual_decision_required": (
                resolution_row.get(
                    "manual_decision_required", False
                )
            ),
            "decision": decision,
            "decision_reason": (
                "Prior approval is not reusable because the persisted patch "
                "violated scientific principle-target integrity; explicit "
                "re-review is required."
                if decision_reuse_blocked
                else decision_row.get("decision_reason")
                if decision_row
                else ""
            ),
            "decision_reuse_blocked": decision_reuse_blocked,
            "decision_reuse_reason": (
                "SCIENTIFIC_TARGET_INTEGRITY_INCIDENT"
                if decision_reuse_blocked
                else None
            ),
            "reviewed_at": (
                decision_row.get("reviewed_at")
                if decision_row
                else None
            ),
            "reviewed_by": (
                decision_row.get("reviewed_by")
                if decision_row
                else None
            ),
            "selected_resolution": (
                decision_row.get("selected_resolution")
                if decision_row
                else None
            ),
            "revision_notes": (
                decision_row.get("revision_notes")
                if decision_row
                else None
            ),
            "application_status": "NOT_APPLIED",
            "application_allowed": False,
        })

    priority_order = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }
    decision_order = {
        "PENDING_REVIEW": 5,
        "NEEDS_REVISION": 4,
        "DEFERRED": 3,
        "APPROVED": 2,
        "REJECTED": 1,
    }
    queue.sort(
        key=lambda item: (
            decision_order.get(
                str(item.get("decision")), 0
            ),
            priority_order.get(
                str(item.get("review_priority")), 0
            ),
            str(item.get("proposal_id")),
        ),
        reverse=True,
    )

    return {
        "schema": "archon_human_review_queue_v1",
        "available": bool(queue),
        "queue_count": len(queue),
        "decision_counts": decision_counts,
        "pending_count": decision_counts.get(
            "PENDING_REVIEW", 0
        ),
        "queue": queue,
        "scientific_policy": {
            "human_review_required": True,
            "approval_does_not_apply_patch": True,
            "automatic_application": False,
            "modifies_existing_actions": False,
            "changes_director_priority": False,
            "changes_strategic_score": False,
        },
    }

def load_human_review_audit_trail(root: Path) -> Dict[str, Any]:
    data = load_json(root / "human_review_audit_trail.json", {})
    if not isinstance(data, dict):
        data = {}
    events = data.get("events", [])
    if not isinstance(events, list):
        events = []
    normalized = [
        item for item in events
        if isinstance(item, dict)
    ]
    return {
        "schema": "archon_human_review_audit_trail_v1",
        "source": str(root / "human_review_audit_trail.json"),
        "event_count": len(normalized),
        "events": normalized,
        "scientific_policy": {
            "append_only": True,
            "automatic_decision_changes": False,
            "patch_application": False,
        },
    }

def validate_human_review_records(
    decisions: Dict[str, Any],
    patch_bundle: Dict[str, Any],
    audit_trail: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate review records against known proposals and prior decisions."""
    current_proposals = (
        patch_bundle.get("proposals", [])
        if isinstance(patch_bundle, dict)
        else []
    )
    historical_proposals = (
        patch_bundle.get("superseded_proposals", [])
        if isinstance(patch_bundle, dict)
        else []
    )
    known_proposals = {
        str(item.get("proposal_id"))
        for item in list(current_proposals or []) + list(historical_proposals or [])
        if isinstance(item, dict) and item.get("proposal_id")
    }

    records = (
        decisions.get("records", [])
        if isinstance(decisions, dict)
        else []
    )
    if not isinstance(records, list):
        records = []

    prior_events = (
        audit_trail.get("events", [])
        if isinstance(audit_trail, dict)
        else []
    )
    if not isinstance(prior_events, list):
        prior_events = []

    prior_latest: Dict[str, str] = {}
    for event in prior_events:
        if not isinstance(event, dict):
            continue
        proposal_id = str(event.get("proposal_id") or "")
        decision = str(event.get("decision") or "")
        if proposal_id and decision in VALID_REVIEW_DECISIONS:
            prior_latest[proposal_id] = decision

    seen_review_ids: set[str] = set()
    seen_proposal_ids: set[str] = set()
    validations: List[Dict[str, Any]] = []
    status_counts = {
        "VALID": 0,
        "DUPLICATE": 0,
        "INVALID_PROPOSAL": 0,
        "INVALID_DECISION": 0,
        "INVALID_TRANSITION": 0,
        "INCOMPLETE": 0,
    }

    for item in records:
        if not isinstance(item, dict):
            continue

        review_id = str(item.get("review_id") or "")
        proposal_id = str(item.get("proposal_id") or "")
        decision = str(item.get("decision") or "").upper()
        issues: List[Dict[str, Any]] = []

        if not review_id or not proposal_id:
            issues.append({
                "type": "incomplete_record",
                "severity": "ERROR",
                "message": "review_id and proposal_id are required.",
            })

        if review_id in seen_review_ids or proposal_id in seen_proposal_ids:
            issues.append({
                "type": "duplicate_record",
                "severity": "ERROR",
                "message": (
                    "Duplicate review_id or multiple current records for the "
                    "same proposal were found."
                ),
            })

        seen_review_ids.add(review_id)
        seen_proposal_ids.add(proposal_id)

        if proposal_id and proposal_id not in known_proposals:
            issues.append({
                "type": "unknown_proposal",
                "severity": "ERROR",
                "message": f"Proposal {proposal_id} does not exist.",
            })

        if decision not in VALID_REVIEW_DECISIONS:
            issues.append({
                "type": "invalid_decision",
                "severity": "ERROR",
                "message": f"Unsupported review decision: {decision or '-'}",
            })

        previous_decision = prior_latest.get(
            proposal_id,
            "PENDING_REVIEW",
        )
        allowed = VALID_REVIEW_TRANSITIONS.get(
            previous_decision,
            {"PENDING_REVIEW"},
        )
        if (
            decision in VALID_REVIEW_DECISIONS
            and decision not in allowed
        ):
            issues.append({
                "type": "invalid_transition",
                "severity": "ERROR",
                "message": (
                    f"Transition {previous_decision} -> {decision} "
                    "is not allowed."
                ),
            })

        if decision in {
            "APPROVED",
            "REJECTED",
            "DEFERRED",
            "NEEDS_REVISION",
        } and not str(item.get("decision_reason") or "").strip():
            issues.append({
                "type": "missing_reason",
                "severity": "ERROR",
                "message": (
                    "A non-pending decision requires decision_reason."
                ),
            })

        issue_types = {
            str(issue.get("type"))
            for issue in issues
        }
        if "duplicate_record" in issue_types:
            status = "DUPLICATE"
        elif "unknown_proposal" in issue_types:
            status = "INVALID_PROPOSAL"
        elif "invalid_decision" in issue_types:
            status = "INVALID_DECISION"
        elif "invalid_transition" in issue_types:
            status = "INVALID_TRANSITION"
        elif issues:
            status = "INCOMPLETE"
        else:
            status = "VALID"

        status_counts[status] += 1
        validations.append({
            "review_id": review_id or None,
            "proposal_id": proposal_id or None,
            "decision": decision or None,
            "previous_decision": previous_decision,
            "status": status,
            "issue_count": len(issues),
            "issues": issues,
            "eligible_for_audit_append": status == "VALID",
            "patch_application_allowed": False,
        })

    return {
        "schema": "archon_human_review_record_validation_v1",
        "available": bool(records),
        "record_count": len(validations),
        "status_counts": status_counts,
        "valid_record_count": status_counts.get("VALID", 0),
        "invalid_record_count": len(validations) - status_counts.get("VALID", 0),
        "validations": validations,
        "scientific_policy": {
            "validation_only": True,
            "automatic_decision_changes": False,
            "automatic_patch_application": False,
            "requires_valid_transition": True,
            "requires_reason_for_terminal_decisions": True,
        },
    }

def build_human_review_audit_update(
    decisions: Dict[str, Any],
    validation: Dict[str, Any],
    existing_audit: Dict[str, Any],
) -> Dict[str, Any]:
    """Build append-only audit events for valid, unseen decision records."""
    existing_events = (
        existing_audit.get("events", [])
        if isinstance(existing_audit, dict)
        else []
    )
    if not isinstance(existing_events, list):
        existing_events = []

    existing_keys = {
        (
            str(item.get("review_id") or ""),
            str(item.get("proposal_id") or ""),
            str(item.get("decision") or ""),
            str(item.get("reviewed_at") or ""),
        )
        for item in existing_events
        if isinstance(item, dict)
    }

    validation_by_review = {
        str(item.get("review_id")): item
        for item in (
            validation.get("validations", [])
            if isinstance(validation, dict)
            else []
        )
        if isinstance(item, dict) and item.get("review_id")
    }

    appended_events: List[Dict[str, Any]] = []

    for record in (
        decisions.get("records", [])
        if isinstance(decisions, dict)
        else []
    ):
        if not isinstance(record, dict):
            continue

        review_id = str(record.get("review_id") or "")
        validation_row = validation_by_review.get(review_id, {})
        if validation_row.get("status") != "VALID":
            continue

        event_key = (
            review_id,
            str(record.get("proposal_id") or ""),
            str(record.get("decision") or ""),
            str(record.get("reviewed_at") or ""),
        )
        if event_key in existing_keys:
            continue

        appended_events.append({
            "event_id": (
                f"HRA-{review_id}-"
                f"{len(existing_events) + len(appended_events) + 1:04d}"
            ),
            "recorded_at": now_iso(),
            "review_id": review_id,
            "proposal_id": record.get("proposal_id"),
            "decision": record.get("decision"),
            "decision_reason": record.get("decision_reason"),
            "reviewed_at": record.get("reviewed_at"),
            "reviewed_by": record.get("reviewed_by"),
            "selected_resolution": record.get(
                "selected_resolution"
            ),
            "revision_notes": record.get("revision_notes"),
            "previous_decision": validation_row.get(
                "previous_decision"
            ),
            "patch_application_status": "NOT_APPLIED",
        })

    combined_events = list(existing_events) + appended_events

    return {
        "schema": "archon_human_review_audit_trail_v1",
        "event_count": len(combined_events),
        "appended_event_count": len(appended_events),
        "events": combined_events,
        "new_events": appended_events,
        "scientific_policy": {
            "append_only": True,
            "automatic_decision_changes": False,
            "automatic_patch_application": False,
            "history_preserved": True,
        },
    }

def build_human_review_decision_template(
    review_queue: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a non-authoritative template for editing review decisions."""
    queue = (
        review_queue.get("queue", [])
        if isinstance(review_queue, dict)
        else []
    )
    if not isinstance(queue, list):
        queue = []

    records: List[Dict[str, Any]] = []
    for item in queue:
        if not isinstance(item, dict):
            continue
        proposal_id = str(item.get("proposal_id") or "")
        records.append({
            "review_id": str(
                item.get("review_id")
                or f"HRQ-{proposal_id}"
            ),
            "proposal_id": proposal_id,
            "decision": "PENDING_REVIEW",
            "decision_reason": "",
            "reviewed_at": None,
            "reviewed_by": None,
            "selected_resolution": (
                item.get("resolution_type")
                if item.get("resolution_type")
                else None
            ),
            "revision_notes": "",
            "validation_status": item.get(
                "validation_status"
            ),
            "review_priority": item.get(
                "review_priority"
            ),
            "preferred_resolution": item.get(
                "preferred_resolution"
            ),
            "template_only": True,
            "application_status": "NOT_APPLIED",
        })

    return {
        "schema": "archon_human_review_decision_template_v1",
        "generated_at": now_iso(),
        "record_count": len(records),
        "records": records,
        "instructions": {
            "editable_fields": [
                "decision",
                "decision_reason",
                "reviewed_at",
                "reviewed_by",
                "selected_resolution",
                "revision_notes",
            ],
            "allowed_decisions": sorted(
                VALID_REVIEW_DECISIONS
            ),
            "required_for_non_pending": [
                "decision_reason",
                "reviewed_at",
                "reviewed_by",
            ],
            "workflow": [
                "Copy selected template records into human_review_decisions.json.",
                "Edit only documented fields.",
                "Run Research Director again.",
                "Inspect review validation and audit trail.",
            ],
        },
        "scientific_policy": {
            "template_only": True,
            "authoritative_decisions": False,
            "automatic_import": False,
            "automatic_application": False,
            "modifies_existing_actions": False,
        },
    }

def build_safe_review_editing_interface(
    review_queue: Dict[str, Any],
    decision_template: Dict[str, Any],
    decisions: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a safe, human-editable review worksheet."""
    existing_by_proposal = {
        str(item.get("proposal_id")): item
        for item in (
            decisions.get("records", [])
            if isinstance(decisions, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }

    rows: List[Dict[str, Any]] = []
    template_records = (
        decision_template.get("records", [])
        if isinstance(decision_template, dict)
        else []
    )
    if not isinstance(template_records, list):
        template_records = []

    for template in template_records:
        if not isinstance(template, dict):
            continue
        proposal_id = str(
            template.get("proposal_id") or ""
        )
        existing = existing_by_proposal.get(proposal_id)

        rows.append({
            "review_id": template.get("review_id"),
            "proposal_id": proposal_id,
            "review_priority": template.get(
                "review_priority"
            ),
            "validation_status": template.get(
                "validation_status"
            ),
            "preferred_resolution": template.get(
                "preferred_resolution"
            ),
            "current_decision": (
                existing.get("decision")
                if existing
                else "PENDING_REVIEW"
            ),
            "decision_reason": (
                existing.get("decision_reason")
                if existing
                else ""
            ),
            "reviewed_at": (
                existing.get("reviewed_at")
                if existing
                else None
            ),
            "reviewed_by": (
                existing.get("reviewed_by")
                if existing
                else None
            ),
            "selected_resolution": (
                existing.get("selected_resolution")
                if existing
                else template.get(
                    "selected_resolution"
                )
            ),
            "revision_notes": (
                existing.get("revision_notes")
                if existing
                else ""
            ),
            "record_exists": bool(existing),
            "safe_to_edit": True,
            "authoritative": False,
        })

    return {
        "schema": "archon_safe_review_editing_interface_v1",
        "generated_at": now_iso(),
        "row_count": len(rows),
        "rows": rows,
        "editing_rules": {
            "do_not_edit": [
                "review_id",
                "proposal_id",
                "review_priority",
                "validation_status",
                "preferred_resolution",
            ],
            "editable": [
                "current_decision",
                "decision_reason",
                "reviewed_at",
                "reviewed_by",
                "selected_resolution",
                "revision_notes",
            ],
            "save_target": "human_review_decisions.json",
            "automatic_import": False,
            "automatic_application": False,
        },
        "scientific_policy": {
            "editing_interface_only": True,
            "authoritative_decisions": False,
            "automatic_import": False,
            "automatic_application": False,
            "modifies_existing_actions": False,
        },
    }

def load_review_import_candidate(root: Path) -> Dict[str, Any]:
    """Load optional human-edited import candidate without applying it."""
    path = root / "human_review_import_candidate.json"
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}

    rows = data.get("rows", data.get("records", []))
    if not isinstance(rows, list):
        rows = []

    return {
        "schema": "archon_review_import_candidate_v1",
        "source": str(path),
        "exists": path.exists(),
        "row_count": len(rows),
        "rows": [
            item for item in rows
            if isinstance(item, dict)
        ],
    }

def build_review_import_preview(
    import_candidate: Dict[str, Any],
    editing_interface: Dict[str, Any],
    decisions: Dict[str, Any],
) -> Dict[str, Any]:
    """Preview candidate review edits and compute a non-applying diff."""
    baseline_rows = {
        str(item.get("proposal_id")): item
        for item in (
            editing_interface.get("rows", [])
            if isinstance(editing_interface, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }
    current_decisions = {
        str(item.get("proposal_id")): item
        for item in (
            decisions.get("records", [])
            if isinstance(decisions, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }

    candidate_rows = (
        import_candidate.get("rows", [])
        if isinstance(import_candidate, dict)
        else []
    )
    if not isinstance(candidate_rows, list):
        candidate_rows = []

    preview_rows: List[Dict[str, Any]] = []
    category_counts = {
        "NEW_RECORD": 0,
        "CHANGED_DECISION": 0,
        "UNCHANGED": 0,
        "INVALID_EDIT": 0,
        "IMMUTABLE_FIELD_CHANGE": 0,
    }

    seen_proposals: set[str] = set()

    for candidate in candidate_rows:
        if not isinstance(candidate, dict):
            continue

        proposal_id = str(candidate.get("proposal_id") or "")
        baseline = baseline_rows.get(proposal_id)
        current = current_decisions.get(proposal_id)
        issues: List[Dict[str, Any]] = []
        diffs: List[Dict[str, Any]] = []

        if not proposal_id or baseline is None:
            issues.append({
                "type": "unknown_proposal",
                "severity": "ERROR",
                "message": (
                    "Candidate row does not reference a known review proposal."
                ),
            })

        if proposal_id in seen_proposals:
            issues.append({
                "type": "duplicate_candidate",
                "severity": "ERROR",
                "message": (
                    "Candidate contains multiple rows for the same proposal."
                ),
            })
        seen_proposals.add(proposal_id)

        if baseline is not None:
            for field_name in IMMUTABLE_REVIEW_FIELDS:
                if field_name not in candidate:
                    continue
                baseline_value = baseline.get(field_name)
                candidate_value = candidate.get(field_name)
                if candidate_value != baseline_value:
                    issues.append({
                        "type": "immutable_field_change",
                        "severity": "ERROR",
                        "field": field_name,
                        "baseline": baseline_value,
                        "candidate": candidate_value,
                        "message": (
                            f"Immutable field {field_name} was modified."
                        ),
                    })

        decision = str(
            candidate.get(
                "current_decision",
                candidate.get("decision", "PENDING_REVIEW"),
            )
            or "PENDING_REVIEW"
        ).upper()

        if decision not in VALID_REVIEW_DECISIONS:
            issues.append({
                "type": "invalid_decision",
                "severity": "ERROR",
                "field": "current_decision",
                "message": f"Unsupported decision: {decision}",
            })

        if (
            decision in {
                "APPROVED",
                "REJECTED",
                "DEFERRED",
                "NEEDS_REVISION",
            }
            and not str(candidate.get("decision_reason") or "").strip()
        ):
            issues.append({
                "type": "missing_reason",
                "severity": "ERROR",
                "field": "decision_reason",
                "message": (
                    "Non-pending decisions require decision_reason."
                ),
            })

        if (
            decision in {
                "APPROVED",
                "REJECTED",
                "DEFERRED",
                "NEEDS_REVISION",
            }
            and not candidate.get("reviewed_at")
        ):
            issues.append({
                "type": "missing_reviewed_at",
                "severity": "ERROR",
                "field": "reviewed_at",
                "message": (
                    "Non-pending decisions require reviewed_at."
                ),
            })

        if (
            decision in {
                "APPROVED",
                "REJECTED",
                "DEFERRED",
                "NEEDS_REVISION",
            }
            and not str(candidate.get("reviewed_by") or "").strip()
        ):
            issues.append({
                "type": "missing_reviewer",
                "severity": "ERROR",
                "field": "reviewed_by",
                "message": (
                    "Non-pending decisions require reviewed_by."
                ),
            })

        reference = current or {}
        field_map = {
            "decision": decision,
            "decision_reason": candidate.get("decision_reason", ""),
            "reviewed_at": candidate.get("reviewed_at"),
            "reviewed_by": candidate.get("reviewed_by"),
            "selected_resolution": candidate.get("selected_resolution"),
            "revision_notes": candidate.get("revision_notes", ""),
        }

        for field_name, candidate_value in field_map.items():
            current_value = reference.get(field_name)
            if current_value != candidate_value:
                diffs.append({
                    "field": field_name,
                    "before": current_value,
                    "after": candidate_value,
                })

        issue_types = {
            str(issue.get("type"))
            for issue in issues
        }
        if "immutable_field_change" in issue_types:
            category = "IMMUTABLE_FIELD_CHANGE"
        elif issues:
            category = "INVALID_EDIT"
        elif current is None:
            category = "NEW_RECORD"
        elif diffs:
            category = "CHANGED_DECISION"
        else:
            category = "UNCHANGED"

        category_counts[category] += 1

        preview_rows.append({
            "proposal_id": proposal_id or None,
            "review_id": (
                candidate.get("review_id")
                if candidate.get("review_id")
                else (
                    baseline.get("review_id")
                    if baseline
                    else None
                )
            ),
            "category": category,
            "current_decision": (
                current.get("decision")
                if current
                else None
            ),
            "proposed_decision": decision,
            "diff_count": len(diffs),
            "diffs": diffs,
            "issue_count": len(issues),
            "issues": issues,
            "eligible_for_import": category in {
                "NEW_RECORD",
                "CHANGED_DECISION",
            },
            "automatic_import": False,
            "patch_application_allowed": False,
        })

    return {
        "schema": "archon_review_decision_import_preview_v1",
        "available": bool(candidate_rows),
        "candidate_exists": bool(
            import_candidate.get("exists")
        ),
        "candidate_row_count": len(candidate_rows),
        "category_counts": category_counts,
        "importable_count": (
            category_counts.get("NEW_RECORD", 0)
            + category_counts.get("CHANGED_DECISION", 0)
        ),
        "blocked_count": (
            category_counts.get("INVALID_EDIT", 0)
            + category_counts.get(
                "IMMUTABLE_FIELD_CHANGE", 0
            )
        ),
        "unchanged_count": category_counts.get(
            "UNCHANGED", 0
        ),
        "rows": preview_rows,
        "scientific_policy": {
            "preview_only": True,
            "automatic_import": False,
            "automatic_decision_write": False,
            "automatic_patch_application": False,
            "immutable_fields_enforced": True,
            "requires_explicit_import_step": True,
        },
    }
