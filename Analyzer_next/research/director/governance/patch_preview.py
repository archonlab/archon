"""Action patch previews, manifests, and persisted overrides."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from Analyzer_next.research.director.common import canonical_json_hash, load_json, now_iso, safe_num
from Analyzer_next.research.director.contracts import ResearchAction
from Analyzer_next.research.director.governance.target_integrity import (
    validate_persisted_override,
    validate_snapshot_transition,
)


DIRECT_ACTION_EXECUTION = "DIRECT_ACTION_EXECUTION"

def build_approved_patch_application_preview(
    actions: List[ResearchAction],
    patch_bundle: Dict[str, Any],
    validation: Dict[str, Any],
    decisions: Dict[str, Any],
    receipt_verification: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a dry-run preview for approved, valid patch proposals."""
    actions_by_id = {
        action.action_id: action
        for action in actions
    }
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
    decisions_by_proposal = {
        str(item.get("proposal_id")): item
        for item in (
            decisions.get("records", [])
            if isinstance(decisions, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }

    receipt_status = str(
        receipt_verification.get("status") or ""
        if isinstance(receipt_verification, dict)
        else ""
    )
    receipt_verified = receipt_status in {
        "VERIFIED",
        "VERIFIED_WITH_WARNINGS",
    }

    rows: List[Dict[str, Any]] = []
    status_counts = {
        "ELIGIBLE": 0,
        "NOT_APPROVED": 0,
        "INVALID_PROPOSAL": 0,
        "RECEIPT_UNVERIFIED": 0,
        "TARGET_MISSING": 0,
        "CONFLICTING": 0,
        "ALREADY_APPLIED": 0,
        "NO_EFFECT": 0,
    }

    for proposal_id, proposal in proposals_by_id.items():
        decision = decisions_by_proposal.get(proposal_id, {})
        validation_row = validations_by_id.get(proposal_id, {})
        action_id = str(proposal.get("target_action_id") or "")
        action = actions_by_id.get(action_id)
        proposal_kind = str(proposal.get("proposal_kind") or "PATCH")
        direct_action = proposal_kind == DIRECT_ACTION_EXECUTION

        decision_status = str(
            decision.get("decision") or "PENDING_REVIEW"
        )
        validation_status = str(
            validation_row.get("status") or "UNKNOWN"
        )

        issues: List[Dict[str, Any]] = []
        diffs: List[Dict[str, Any]] = []
        operation_results: List[Dict[str, Any]] = []

        if decision_status != "APPROVED":
            status = "NOT_APPROVED"
        elif validation_status != "VALID":
            status = "INVALID_PROPOSAL"
            issues.append({
                "type": "proposal_not_valid",
                "message": (
                    f"Validation status is {validation_status}, not VALID."
                ),
            })
        elif not receipt_verified:
            status = "RECEIPT_UNVERIFIED"
            issues.append({
                "type": "receipt_not_verified",
                "message": (
                    "The approving decision is not protected by a verified "
                    "commit receipt."
                ),
            })
        elif action is None:
            status = "TARGET_MISSING"
            issues.append({
                "type": "missing_target_action",
                "message": f"Target action {action_id or '-'} does not exist.",
            })
        else:
            current_values = {
                "title": action.title,
                "suggested_target": action.suggested_target or "",
                "done_when": action.done_when or "",
                "rationale": action.rationale,
            }
            resulting_values = dict(current_values)

            if direct_action:
                proposal_snapshot = proposal.get("action_snapshot")
                proposal_snapshot_hash = proposal.get(
                    "action_snapshot_hash"
                )
                current_snapshot = research_action_snapshot(action)
                if (
                    not isinstance(proposal_snapshot, dict)
                    or canonical_json_hash(proposal_snapshot)
                    != proposal_snapshot_hash
                    or proposal_snapshot != current_snapshot
                ):
                    issues.append({
                        "type": "direct_action_snapshot_mismatch",
                        "message": (
                            "The reviewed direct action snapshot no longer "
                            "matches the current ResearchAction."
                        ),
                    })

            operations = proposal.get("patch_operations", [])
            if not isinstance(operations, list):
                operations = []

            for operation in operations:
                if not isinstance(operation, dict):
                    continue
                field_name = str(operation.get("field") or "")
                op_type = str(operation.get("op") or "")
                before = str(resulting_values.get(field_name, ""))

                if field_name not in resulting_values:
                    issues.append({
                        "type": "unsupported_field",
                        "field": field_name,
                        "message": f"Unsupported action field: {field_name}",
                    })
                    operation_results.append({
                        "field": field_name,
                        "operation": op_type,
                        "status": "CONFLICTING",
                    })
                    continue

                if op_type == "replace":
                    after = str(operation.get("proposed_value") or "")
                    op_status = (
                        "ALREADY_APPLIED"
                        if after == before
                        else "WOULD_CHANGE"
                    )
                elif op_type == "append_unique":
                    additions = [
                        str(x).strip()
                        for x in operation.get("proposed_additions", [])
                        if str(x).strip()
                    ]
                    new_items = [
                        item for item in additions
                        if item.lower() not in before.lower()
                    ]
                    if not new_items:
                        after = before
                        op_status = "ALREADY_APPLIED"
                    else:
                        separator = "\n" if before.strip() else ""
                        after = (
                            before
                            + separator
                            + "\n".join(new_items)
                        )
                        op_status = "WOULD_CHANGE"
                else:
                    issues.append({
                        "type": "unsupported_operation",
                        "field": field_name,
                        "message": f"Unsupported operation: {op_type or '-'}",
                    })
                    operation_results.append({
                        "field": field_name,
                        "operation": op_type,
                        "status": "CONFLICTING",
                    })
                    continue

                resulting_values[field_name] = after
                operation_results.append({
                    "field": field_name,
                    "operation": op_type,
                    "status": op_status,
                    "before": before,
                    "after": after,
                })
                if after != before:
                    diffs.append({
                        "field": field_name,
                        "before": before,
                        "after": after,
                    })

            has_conflict = any(
                item.get("status") == "CONFLICTING"
                for item in operation_results
            )
            all_already = bool(operation_results) and all(
                item.get("status") == "ALREADY_APPLIED"
                for item in operation_results
            )

            if has_conflict or issues:
                status = "CONFLICTING"
            elif all_already:
                status = "ALREADY_APPLIED"
            elif direct_action and not operation_results:
                status = "ELIGIBLE"
            elif not diffs:
                status = "NO_EFFECT"
            else:
                status = "ELIGIBLE"

        status_counts[status] += 1
        rows.append({
            "application_preview_id": f"APPLY-PREVIEW-{proposal_id}",
            "proposal_id": proposal_id,
            "proposal_kind": proposal_kind,
            "application_mode": (
                "DIRECT_ACTION_ACTIVATION"
                if direct_action
                else "SEMANTIC_PATCH"
            ),
            "review_id": decision.get("review_id"),
            "target_action_id": action_id or None,
            "decision": decision_status,
            "validation_status": validation_status,
            "receipt_status": receipt_status or "NO_RECEIPT",
            "status": status,
            "issue_count": len(issues),
            "issues": issues,
            "diff_count": len(diffs),
            "diffs": diffs,
            "operation_results": operation_results,
            "application_eligible": status == "ELIGIBLE",
            "application_performed": False,
        })

    rows.sort(
        key=lambda item: (
            item.get("status") == "ELIGIBLE",
            item.get("decision") == "APPROVED",
            str(item.get("proposal_id")),
        ),
        reverse=True,
    )

    return {
        "schema": "archon_approved_patch_application_preview_v1",
        "available": bool(rows),
        "proposal_count": len(rows),
        "status_counts": status_counts,
        "eligible_count": status_counts.get("ELIGIBLE", 0),
        "blocked_count": len(rows) - status_counts.get("ELIGIBLE", 0),
        "rows": rows,
        "scientific_policy": {
            "preview_only": True,
            "automatic_application": False,
            "modifies_research_actions": False,
            "requires_approved_decision": True,
            "requires_valid_proposal": True,
            "requires_verified_receipt": True,
            "requires_explicit_application_step": True,
        },
    }

def research_action_snapshot(action: ResearchAction) -> Dict[str, Any]:
    """Return the patchable ResearchAction state used for hash checks."""
    return {
        "action_id": action.action_id,
        "title": action.title,
        "suggested_target": action.suggested_target or "",
        "done_when": action.done_when or "",
        "rationale": action.rationale,
    }

def build_patch_application_manifest(
    actions: List[ResearchAction],
    application_preview: Dict[str, Any],
    patch_bundle: Dict[str, Any],
    receipt_verification: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a final, non-applying manifest for eligible ResearchAction patches."""
    actions_by_id = {
        action.action_id: action
        for action in actions
    }
    proposals_by_id = {
        str(item.get("proposal_id")): item
        for item in (
            patch_bundle.get("proposals", [])
            if isinstance(patch_bundle, dict)
            else []
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }

    preview_rows = (
        application_preview.get("rows", [])
        if isinstance(application_preview, dict)
        else []
    )
    if not isinstance(preview_rows, list):
        preview_rows = []

    receipt_status = str(
        receipt_verification.get("status") or ""
        if isinstance(receipt_verification, dict)
        else ""
    )
    source_commit_id = (
        receipt_verification.get("commit_id")
        if isinstance(receipt_verification, dict)
        else None
    )

    manifest_rows: List[Dict[str, Any]] = []
    skipped_rows: List[Dict[str, Any]] = []
    global_checks: List[Dict[str, Any]] = []

    def add_global_check(
        name: str,
        passed: bool,
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        global_checks.append({
            "name": name,
            "passed": bool(passed),
            "expected": expected,
            "actual": actual,
        })

    add_global_check(
        "receipt_verified",
        receipt_status in {"VERIFIED", "VERIFIED_WITH_WARNINGS"},
        "VERIFIED or VERIFIED_WITH_WARNINGS",
        receipt_status or "NO_RECEIPT",
    )
    add_global_check(
        "source_commit_id_present",
        bool(source_commit_id),
        True,
        bool(source_commit_id),
    )

    for preview in preview_rows:
        if not isinstance(preview, dict):
            continue

        proposal_id = str(preview.get("proposal_id") or "")
        action_id = str(preview.get("target_action_id") or "")
        proposal = proposals_by_id.get(proposal_id, {})
        action = actions_by_id.get(action_id)
        proposal_kind = str(proposal.get("proposal_kind") or "PATCH")
        direct_action = proposal_kind == DIRECT_ACTION_EXECUTION

        if preview.get("status") != "ELIGIBLE":
            skipped_rows.append({
                "proposal_id": proposal_id or None,
                "target_action_id": action_id or None,
                "preview_status": preview.get("status"),
                "reason": "Application preview row is not ELIGIBLE.",
            })
            continue

        row_checks: List[Dict[str, Any]] = []

        def add_row_check(
            name: str,
            passed: bool,
            expected: Any = None,
            actual: Any = None,
        ) -> None:
            row_checks.append({
                "name": name,
                "passed": bool(passed),
                "expected": expected,
                "actual": actual,
            })

        add_row_check(
            "target_action_exists",
            action is not None,
            True,
            action is not None,
        )
        add_row_check(
            "proposal_exists",
            bool(proposal),
            True,
            bool(proposal),
        )
        add_row_check(
            "preview_has_diffs",
            (
                int(safe_num(preview.get("diff_count"), 0)) == 0
                if direct_action
                else int(safe_num(preview.get("diff_count"), 0)) > 0
            ),
            "0" if direct_action else ">0",
            int(safe_num(preview.get("diff_count"), 0)),
        )
        add_row_check(
            "preview_application_not_performed",
            not bool(preview.get("application_performed")),
            False,
            bool(preview.get("application_performed")),
        )

        if action is None or not proposal:
            skipped_rows.append({
                "proposal_id": proposal_id or None,
                "target_action_id": action_id or None,
                "preview_status": preview.get("status"),
                "reason": "Target action or proposal is missing.",
                "safety_checks": row_checks,
            })
            continue

        before_snapshot = research_action_snapshot(action)
        after_snapshot = dict(before_snapshot)

        operations = proposal.get("patch_operations", [])
        if not isinstance(operations, list):
            operations = []

        normalized_operations: List[Dict[str, Any]] = []
        operation_conflicts: List[Dict[str, Any]] = []

        for operation in operations:
            if not isinstance(operation, dict):
                continue

            field_name = str(operation.get("field") or "")
            op_type = str(operation.get("op") or "")
            before_value = str(after_snapshot.get(field_name, ""))

            if field_name not in {
                "title",
                "suggested_target",
                "done_when",
                "rationale",
            }:
                operation_conflicts.append({
                    "type": "unsupported_field",
                    "field": field_name,
                    "operation": op_type,
                })
                continue

            if op_type == "replace":
                after_value = str(
                    operation.get("proposed_value") or ""
                )
            elif op_type == "append_unique":
                additions = [
                    str(item).strip()
                    for item in operation.get("proposed_additions", [])
                    if str(item).strip()
                ]
                new_items = [
                    item for item in additions
                    if item.lower() not in before_value.lower()
                ]
                separator = "\n" if before_value.strip() and new_items else ""
                after_value = (
                    before_value
                    + separator
                    + "\n".join(new_items)
                )
            else:
                operation_conflicts.append({
                    "type": "unsupported_operation",
                    "field": field_name,
                    "operation": op_type,
                })
                continue

            after_snapshot[field_name] = after_value
            normalized_operations.append({
                "field": field_name,
                "operation": op_type,
                "before": before_value,
                "after": after_value,
                "changed": before_value != after_value,
            })

        target_integrity_issues = validate_snapshot_transition(
            action_id,
            before_snapshot,
            after_snapshot,
        )
        operation_conflicts.extend(target_integrity_issues)

        expected_action_hash = canonical_json_hash(before_snapshot)
        resulting_action_hash = canonical_json_hash(after_snapshot)
        rollback_snapshot = {
            "action_id": action.action_id,
            "snapshot": before_snapshot,
            "snapshot_hash": expected_action_hash,
        }

        add_row_check(
            "no_operation_conflicts",
            not operation_conflicts,
            0,
            len(operation_conflicts),
        )
        add_row_check(
            "result_hash_differs",
            (
                expected_action_hash == resulting_action_hash
                if direct_action
                else expected_action_hash != resulting_action_hash
            ),
            not direct_action,
            expected_action_hash != resulting_action_hash,
        )
        add_row_check(
            "all_operations_normalized",
            len(normalized_operations) == len(operations),
            len(operations),
            len(normalized_operations),
        )

        row_safe = all(
            item.get("passed")
            for item in row_checks
        )

        if not row_safe:
            skipped_rows.append({
                "proposal_id": proposal_id,
                "target_action_id": action_id,
                "preview_status": preview.get("status"),
                "reason": "Final safety checks failed.",
                "safety_checks": row_checks,
                "operation_conflicts": operation_conflicts,
            })
            continue

        manifest_rows.append({
            "application_id": (
                f"PATCH-APPLY-{proposal_id}-"
                f"{resulting_action_hash[:12].upper()}"
            ),
            "source_commit_id": source_commit_id,
            "proposal_id": proposal_id,
            "proposal_kind": proposal_kind,
            "application_mode": (
                "DIRECT_ACTION_ACTIVATION"
                if direct_action
                else "SEMANTIC_PATCH"
            ),
            "review_id": preview.get("review_id"),
            "target_action_id": action_id,
            "expected_action_hash": expected_action_hash,
            "resulting_action_hash": resulting_action_hash,
            "operations": normalized_operations,
            "rollback_snapshot": rollback_snapshot,
            "safety_checks": row_checks,
            "eligible_for_atomic_application": True,
            "application_performed": False,
        })

    manifest_payload = {
        "source_commit_id": source_commit_id,
        "rows": manifest_rows,
        "receipt_status": receipt_status,
    }
    manifest_hash = canonical_json_hash(manifest_payload)
    application_manifest_id = (
        f"PATCH-MANIFEST-{manifest_hash[:16].upper()}"
        if manifest_rows
        else None
    )

    global_safe = all(
        item.get("passed")
        for item in global_checks
    )
    final_ready = global_safe and bool(manifest_rows)

    return {
        "schema": "archon_patch_application_manifest_v1",
        "generated_at": now_iso(),
        "available": bool(manifest_rows),
        "application_manifest_id": application_manifest_id,
        "source_commit_id": source_commit_id,
        "receipt_status": receipt_status or "NO_RECEIPT",
        "manifest_hash": manifest_hash,
        "eligible_row_count": len(manifest_rows),
        "skipped_row_count": len(skipped_rows),
        "global_checks": global_checks,
        "global_safe": global_safe,
        "final_ready": final_ready,
        "rows": manifest_rows,
        "skipped_rows": skipped_rows,
        "application_preconditions": {
            "manifest_hash_must_match": manifest_hash,
            "source_commit_id_must_match": source_commit_id,
            "all_expected_action_hashes_must_match": True,
            "receipt_status_must_be_verified": True,
            "explicit_application_request_required": True,
        },
        "scientific_policy": {
            "manifest_only": True,
            "automatic_application": False,
            "modifies_research_actions": False,
            "rollback_snapshot_required": True,
            "requires_final_safety_checks": True,
            "requires_explicit_atomic_application_step": True,
        },
    }

def load_research_action_patch_state(root: Path) -> Dict[str, Any]:
    """Load persistent ResearchAction overrides created by atomic application."""
    path = root / "research_action_patch_state.json"
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}

    overrides = data.get("overrides", [])
    if not isinstance(overrides, list):
        overrides = []

    return {
        "schema": "archon_research_action_patch_state_v1",
        "source": str(path),
        "exists": path.exists(),
        "override_count": len(overrides),
        "overrides": [
            item for item in overrides
            if isinstance(item, dict)
        ],
        "last_application_id": data.get("last_application_id"),
        "last_manifest_id": data.get("last_manifest_id"),
        "last_rollback_id": data.get("last_rollback_id"),
        "source_commit_id": data.get("source_commit_id"),
        "updated_at": data.get("updated_at"),
        "scientific_policy": {
            "persistent_overrides": True,
            "changes_research_actions_only": True,
            "changes_scientific_metrics": False,
        },
    }

def apply_persisted_research_action_patches(
    actions: List[ResearchAction],
    patch_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply persisted action snapshots before downstream reconciliation."""
    actions_by_id = {
        action.action_id: action
        for action in actions
    }
    applied: List[str] = []
    missing: List[str] = []
    invalid: List[str] = []
    principle_integrity_rejections: List[Dict[str, Any]] = []

    for item in (
        patch_state.get("overrides", [])
        if isinstance(patch_state, dict)
        else []
    ):
        if not isinstance(item, dict):
            continue

        action_id = str(item.get("action_id") or "")
        snapshot = item.get("snapshot", {})
        if not isinstance(snapshot, dict):
            invalid.append(action_id or "UNKNOWN")
            continue

        action = actions_by_id.get(action_id)
        if action is None:
            missing.append(action_id or "UNKNOWN")
            continue

        integrity_issues = validate_persisted_override(action_id, item)
        if integrity_issues:
            invalid.append(action_id or "UNKNOWN")
            principle_integrity_rejections.append({
                "action_id": action_id or None,
                "source_proposal_id": item.get("source_proposal_id"),
                "issue_count": len(integrity_issues),
                "issues": integrity_issues,
            })
            continue

        for field_name in (
            "title",
            "suggested_target",
            "done_when",
            "rationale",
        ):
            if field_name in snapshot:
                setattr(action, field_name, snapshot.get(field_name))
        applied.append(action_id)

    result = {
        "schema": "archon_research_action_patch_state_apply_v1",
        "applied_count": len(applied),
        "missing_count": len(missing),
        "invalid_count": len(invalid),
        "applied_action_ids": applied,
        "missing_action_ids": missing,
        "invalid_action_ids": invalid,
    }
    # Preserve legacy/parity output when no target-integrity incident exists.
    # Incident detail is emitted only when the new fail-closed guard fires.
    if principle_integrity_rejections:
        result["principle_integrity_rejection_count"] = len(
            principle_integrity_rejections
        )
        result["principle_integrity_rejections"] = principle_integrity_rejections
        result["scientific_policy"] = {
            "cross_principle_target_rewrites_fail_closed": True,
            "invalid_overrides_are_not_applied": True,
            "persistent_state_is_not_modified_automatically": True,
        }
    return result
