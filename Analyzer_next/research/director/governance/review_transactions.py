"""Atomic human-review commit lifecycle."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from Analyzer_next.research.director.common import atomic_write_json, canonical_json_hash, load_json, now_iso, safe_num

def build_review_commit_manifest(
    import_candidate: Dict[str, Any],
    import_preview: Dict[str, Any],
    decisions: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a dry-run commit manifest for importable review decisions."""
    candidate_rows = (
        import_candidate.get("rows", [])
        if isinstance(import_candidate, dict)
        else []
    )
    if not isinstance(candidate_rows, list):
        candidate_rows = []

    preview_rows = (
        import_preview.get("rows", [])
        if isinstance(import_preview, dict)
        else []
    )
    if not isinstance(preview_rows, list):
        preview_rows = []

    candidate_by_proposal = {
        str(item.get("proposal_id")): item
        for item in candidate_rows
        if isinstance(item, dict) and item.get("proposal_id")
    }

    manifest_rows: List[Dict[str, Any]] = []
    skipped_rows: List[Dict[str, Any]] = []

    for preview in preview_rows:
        if not isinstance(preview, dict):
            continue

        proposal_id = str(preview.get("proposal_id") or "")
        category = str(preview.get("category") or "")
        candidate = candidate_by_proposal.get(proposal_id, {})

        if not preview.get("eligible_for_import"):
            skipped_rows.append({
                "proposal_id": proposal_id or None,
                "review_id": preview.get("review_id"),
                "category": category,
                "reason": (
                    "Preview row is not eligible for import."
                ),
                "issue_count": preview.get("issue_count", 0),
            })
            continue

        manifest_rows.append({
            "review_id": (
                candidate.get("review_id")
                or preview.get("review_id")
            ),
            "proposal_id": proposal_id,
            "decision": str(
                candidate.get(
                    "current_decision",
                    candidate.get(
                        "decision",
                        preview.get("proposed_decision"),
                    ),
                )
            ).upper(),
            "decision_reason": candidate.get(
                "decision_reason", ""
            ),
            "reviewed_at": candidate.get("reviewed_at"),
            "reviewed_by": candidate.get("reviewed_by"),
            "selected_resolution": candidate.get(
                "selected_resolution"
            ),
            "revision_notes": candidate.get(
                "revision_notes", ""
            ),
            "source_category": category,
            "expected_operation": (
                "INSERT"
                if category == "NEW_RECORD"
                else "UPDATE"
            ),
            "patch_application_status": "NOT_APPLIED",
        })

    candidate_hash = canonical_json_hash({
        "rows": candidate_rows,
    })
    decision_store_payload = {
        "records": (
            decisions.get("records", [])
            if isinstance(decisions, dict)
            else []
        )
    }
    decision_store_hash = canonical_json_hash(
        decision_store_payload
    )
    manifest_payload_hash = canonical_json_hash({
        "rows": manifest_rows,
        "candidate_hash": candidate_hash,
        "expected_decision_store_hash": decision_store_hash,
    })

    commit_id = (
        f"HR-COMMIT-{manifest_payload_hash[:16].upper()}"
        if manifest_rows
        else None
    )

    return {
        "schema": "archon_review_commit_manifest_v1",
        "generated_at": now_iso(),
        "available": bool(manifest_rows),
        "commit_id": commit_id,
        "candidate_hash": candidate_hash,
        "expected_decision_store_hash": decision_store_hash,
        "manifest_hash": manifest_payload_hash,
        "importable_row_count": len(manifest_rows),
        "skipped_row_count": len(skipped_rows),
        "rows": manifest_rows,
        "skipped_rows": skipped_rows,
        "commit_preconditions": {
            "candidate_hash_must_match": candidate_hash,
            "decision_store_hash_must_match": decision_store_hash,
            "preview_blocked_count_must_equal": 0,
            "manifest_row_count_must_equal": len(manifest_rows),
        },
        "stale_commit_detection": {
            "enabled": True,
            "candidate_changed": False,
            "decision_store_changed": False,
            "stale": False,
            "reason": None,
        },
        "scientific_policy": {
            "manifest_only": True,
            "automatic_import": False,
            "automatic_decision_write": False,
            "automatic_patch_application": False,
            "requires_explicit_commit_step": True,
            "requires_hash_match": True,
        },
    }

def load_review_commit_request(root: Path) -> Dict[str, Any]:
    """Load an explicit human commit request."""
    path = root / "human_review_commit_request.json"
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}

    return {
        "schema": "archon_review_commit_request_v1",
        "source": str(path),
        "exists": path.exists(),
        "commit": bool(data.get("commit", False)),
        "commit_id": data.get("commit_id"),
        "candidate_hash": data.get("candidate_hash"),
        "expected_decision_store_hash": data.get(
            "expected_decision_store_hash"
        ),
        "requested_at": data.get("requested_at"),
        "requested_by": data.get("requested_by"),
        "confirmation": data.get("confirmation"),
        "last_consumed_commit_id": data.get(
            "last_consumed_commit_id"
        ),
    }

def commit_human_review_decisions(
    root: Path,
    request: Dict[str, Any],
    manifest: Dict[str, Any],
    import_candidate: Dict[str, Any],
    import_preview: Dict[str, Any],
    current_decisions: Dict[str, Any],
) -> Dict[str, Any]:
    """Atomically commit review decisions after all dry-run checks pass."""
    checks: List[Dict[str, Any]] = []

    def add_check(
        name: str,
        passed: bool,
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        checks.append({
            "name": name,
            "passed": bool(passed),
            "expected": expected,
            "actual": actual,
        })

    manifest_rows = (
        manifest.get("rows", [])
        if isinstance(manifest, dict)
        else []
    )
    if not isinstance(manifest_rows, list):
        manifest_rows = []

    candidate_rows = (
        import_candidate.get("rows", [])
        if isinstance(import_candidate, dict)
        else []
    )
    if not isinstance(candidate_rows, list):
        candidate_rows = []

    current_records = (
        current_decisions.get("records", [])
        if isinstance(current_decisions, dict)
        else []
    )
    if not isinstance(current_records, list):
        current_records = []

    current_candidate_hash = canonical_json_hash({
        "rows": candidate_rows,
    })
    current_store_hash = canonical_json_hash({
        "records": current_records,
    })

    add_check(
        "explicit_commit_flag",
        bool(request.get("commit")),
        True,
        bool(request.get("commit")),
    )
    add_check(
        "confirmation_phrase",
        request.get("confirmation") == "COMMIT_REVIEW_DECISIONS",
        "COMMIT_REVIEW_DECISIONS",
        request.get("confirmation"),
    )
    add_check(
        "manifest_available",
        bool(manifest.get("available")),
        True,
        bool(manifest.get("available")),
    )
    add_check(
        "commit_id_match",
        request.get("commit_id") == manifest.get("commit_id"),
        manifest.get("commit_id"),
        request.get("commit_id"),
    )
    add_check(
        "candidate_hash_match",
        (
            request.get("candidate_hash")
            == manifest.get("candidate_hash")
            == current_candidate_hash
        ),
        manifest.get("candidate_hash"),
        current_candidate_hash,
    )
    add_check(
        "decision_store_hash_match",
        (
            request.get("expected_decision_store_hash")
            == manifest.get("expected_decision_store_hash")
            == current_store_hash
        ),
        manifest.get("expected_decision_store_hash"),
        current_store_hash,
    )
    add_check(
        "preview_blocked_count_zero",
        int(safe_num(import_preview.get("blocked_count"), 0)) == 0,
        0,
        int(safe_num(import_preview.get("blocked_count"), 0)),
    )
    add_check(
        "manifest_rows_present",
        len(manifest_rows) > 0,
        ">0",
        len(manifest_rows),
    )
    add_check(
        "all_manifest_rows_importable",
        len(manifest_rows)
        == int(safe_num(manifest.get("importable_row_count"), 0)),
        int(safe_num(manifest.get("importable_row_count"), 0)),
        len(manifest_rows),
    )

    failed_checks = [
        item for item in checks
        if not item.get("passed")
    ]

    if failed_checks:
        return {
            "schema": "archon_review_atomic_commit_result_v1",
            "attempted": bool(request.get("commit")),
            "committed": False,
            "status": (
                "NO_COMMIT_REQUEST"
                if not request.get("commit")
                else "REFUSED"
            ),
            "commit_id": manifest.get("commit_id"),
            "check_count": len(checks),
            "failed_check_count": len(failed_checks),
            "checks": checks,
            "written_record_count": 0,
            "inserted_count": 0,
            "updated_count": 0,
            "backup_path": None,
            "receipt_path": None,
            "scientific_policy": {
                "decision_store_only": True,
                "patch_application": False,
                "research_action_modification": False,
            },
        }

    records_by_proposal = {
        str(item.get("proposal_id")): dict(item)
        for item in current_records
        if isinstance(item, dict) and item.get("proposal_id")
    }

    inserted_count = 0
    updated_count = 0

    for row in manifest_rows:
        if not isinstance(row, dict):
            continue
        proposal_id = str(row.get("proposal_id") or "")
        if not proposal_id:
            continue

        new_record = {
            "review_id": row.get("review_id"),
            "proposal_id": proposal_id,
            "decision": row.get("decision"),
            "decision_reason": row.get("decision_reason"),
            "reviewed_at": row.get("reviewed_at"),
            "reviewed_by": row.get("reviewed_by"),
            "selected_resolution": row.get(
                "selected_resolution"
            ),
            "revision_notes": row.get("revision_notes"),
            "application_status": "NOT_APPLIED",
        }

        if proposal_id in records_by_proposal:
            updated_count += 1
        else:
            inserted_count += 1
        records_by_proposal[proposal_id] = new_record

    final_records = sorted(
        records_by_proposal.values(),
        key=lambda item: str(item.get("proposal_id") or ""),
    )
    final_payload = {
        "schema": "archon_human_review_decisions_v1",
        "records": final_records,
        "scientific_policy": {
            "approval_does_not_apply_patch": True,
            "automatic_application": False,
        },
    }

    decisions_path = root / "human_review_decisions.json"
    backup_path = (
        root
        / (
            "human_review_decisions.backup."
            f"{manifest.get('commit_id')}.json"
        )
    )
    receipt_path = (
        root
        / (
            "human_review_commit_receipt."
            f"{manifest.get('commit_id')}.json"
        )
    )

    if decisions_path.exists():
        atomic_write_json(
            backup_path,
            {
                "schema": "archon_human_review_decisions_backup_v1",
                "backed_up_at": now_iso(),
                "source": str(decisions_path),
                "commit_id": manifest.get("commit_id"),
                "payload": load_json(decisions_path, {}),
            },
        )

    atomic_write_json(decisions_path, final_payload)

    final_store_hash = canonical_json_hash({
        "records": final_records,
    })
    receipt = {
        "schema": "archon_review_commit_receipt_v1",
        "committed_at": now_iso(),
        "commit_id": manifest.get("commit_id"),
        "candidate_hash": current_candidate_hash,
        "previous_decision_store_hash": current_store_hash,
        "new_decision_store_hash": final_store_hash,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "written_record_count": len(final_records),
        "requested_at": request.get("requested_at"),
        "requested_by": request.get("requested_by"),
        "patch_application_status": "NOT_APPLIED",
    }
    atomic_write_json(receipt_path, receipt)

    # Consume the successful request so restarts cannot replay the commit.
    atomic_write_json(
        root / "human_review_commit_request.json",
        {
            "schema": "archon_review_commit_request_v1",
            "commit": False,
            "commit_id": None,
            "candidate_hash": None,
            "expected_decision_store_hash": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "last_consumed_commit_id": manifest.get("commit_id"),
        },
    )

    return {
        "schema": "archon_review_atomic_commit_result_v1",
        "attempted": True,
        "committed": True,
        "status": "COMMITTED",
        "commit_id": manifest.get("commit_id"),
        "check_count": len(checks),
        "failed_check_count": 0,
        "checks": checks,
        "written_record_count": len(final_records),
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "previous_decision_store_hash": current_store_hash,
        "new_decision_store_hash": final_store_hash,
        "backup_path": str(backup_path),
        "receipt_path": str(receipt_path),
        "scientific_policy": {
            "decision_store_only": True,
            "patch_application": False,
            "research_action_modification": False,
            "approval_does_not_apply_patch": True,
            "request_consumed_after_success": True,
        },
    }

def load_latest_review_commit_receipt(root: Path) -> Dict[str, Any]:
    """Load the most recent review commit receipt, if any."""
    receipts = sorted(
        root.glob("human_review_commit_receipt.HR-COMMIT-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not receipts:
        return {
            "schema": "archon_review_commit_receipt_lookup_v1",
            "available": False,
            "path": None,
            "receipt": {},
        }

    path = receipts[0]
    receipt = load_json(path, {})
    if not isinstance(receipt, dict):
        receipt = {}

    return {
        "schema": "archon_review_commit_receipt_lookup_v1",
        "available": True,
        "path": str(path),
        "receipt": receipt,
    }

def verify_review_commit_receipt(
    root: Path,
    receipt_lookup: Dict[str, Any],
    decisions: Dict[str, Any],
    audit_trail: Dict[str, Any],
) -> Dict[str, Any]:
    """Verify receipt consistency against decision store, backup, and audit."""
    receipt = (
        receipt_lookup.get("receipt", {})
        if isinstance(receipt_lookup, dict)
        else {}
    )
    if not isinstance(receipt, dict):
        receipt = {}

    checks: List[Dict[str, Any]] = []

    def add_check(
        name: str,
        passed: bool,
        expected: Any = None,
        actual: Any = None,
        severity: str = "ERROR",
    ) -> None:
        checks.append({
            "name": name,
            "passed": bool(passed),
            "expected": expected,
            "actual": actual,
            "severity": severity,
        })

    available = bool(
        receipt_lookup.get("available")
        if isinstance(receipt_lookup, dict)
        else False
    )

    if not available:
        return {
            "schema": "archon_review_commit_receipt_verification_v1",
            "available": False,
            "status": "NO_RECEIPT",
            "commit_id": None,
            "check_count": 0,
            "failed_check_count": 0,
            "checks": [],
            "verified_record_count": 0,
            "missing_record_count": 0,
            "audit_match_count": 0,
            "scientific_policy": {
                "verification_only": True,
                "automatic_repair": False,
                "automatic_rollback": False,
                "patch_application": False,
            },
        }

    commit_id = str(receipt.get("commit_id") or "")
    current_records = (
        decisions.get("records", [])
        if isinstance(decisions, dict)
        else []
    )
    if not isinstance(current_records, list):
        current_records = []

    current_store_hash = canonical_json_hash({
        "records": current_records,
    })
    expected_store_hash = receipt.get(
        "new_decision_store_hash"
    )
    add_check(
        "decision_store_hash_match",
        current_store_hash == expected_store_hash,
        expected_store_hash,
        current_store_hash,
    )

    backup_path = (
        root
        / f"human_review_decisions.backup.{commit_id}.json"
    )
    add_check(
        "backup_exists",
        backup_path.exists(),
        True,
        backup_path.exists(),
    )

    receipt_path = Path(
        str(receipt_lookup.get("path") or "")
    )
    add_check(
        "receipt_exists",
        receipt_path.exists(),
        True,
        receipt_path.exists(),
    )

    expected_written = int(
        safe_num(receipt.get("written_record_count"), 0)
    )
    add_check(
        "written_record_count_match",
        len(current_records) == expected_written,
        expected_written,
        len(current_records),
    )

    inserted_count = int(
        safe_num(receipt.get("inserted_count"), 0)
    )
    updated_count = int(
        safe_num(receipt.get("updated_count"), 0)
    )
    add_check(
        "operation_counts_non_negative",
        inserted_count >= 0 and updated_count >= 0,
        ">=0",
        {
            "inserted": inserted_count,
            "updated": updated_count,
        },
    )

    audit_events = (
        audit_trail.get("events", [])
        if isinstance(audit_trail, dict)
        else []
    )
    if not isinstance(audit_events, list):
        audit_events = []

    audit_matches = [
        event for event in audit_events
        if isinstance(event, dict)
        and str(event.get("commit_id") or "") == commit_id
    ]

    # Older audit events may not contain commit_id. Fall back to store decisions.
    if not audit_matches:
        committed_proposals = {
            str(item.get("proposal_id") or "")
            for item in current_records
            if isinstance(item, dict)
            and item.get("proposal_id")
        }
        audit_matches = [
            event for event in audit_events
            if isinstance(event, dict)
            and str(event.get("proposal_id") or "")
            in committed_proposals
        ]

    add_check(
        "audit_events_present",
        len(audit_matches) >= (
            inserted_count + updated_count
        ),
        inserted_count + updated_count,
        len(audit_matches),
        severity="WARNING",
    )

    failed = [
        item for item in checks
        if not item.get("passed")
        and item.get("severity") == "ERROR"
    ]
    warnings = [
        item for item in checks
        if not item.get("passed")
        and item.get("severity") == "WARNING"
    ]

    status = (
        "VERIFIED"
        if not failed and not warnings
        else "VERIFIED_WITH_WARNINGS"
        if not failed
        else "FAILED"
    )

    return {
        "schema": "archon_review_commit_receipt_verification_v1",
        "available": True,
        "status": status,
        "commit_id": commit_id,
        "receipt_path": str(receipt_path),
        "backup_path": str(backup_path),
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "warning_count": len(warnings),
        "checks": checks,
        "verified_record_count": len(current_records),
        "missing_record_count": 0,
        "audit_match_count": len(audit_matches),
        "scientific_policy": {
            "verification_only": True,
            "automatic_repair": False,
            "automatic_rollback": False,
            "patch_application": False,
        },
    }

def build_review_recovery_check(
    receipt_verification: Dict[str, Any],
    decisions: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a recovery-readiness report without performing rollback."""
    available = bool(
        receipt_verification.get("available")
        if isinstance(receipt_verification, dict)
        else False
    )
    if not available:
        return {
            "schema": "archon_review_recovery_check_v1",
            "available": False,
            "status": "NO_COMMIT_TO_RECOVER",
            "recovery_ready": False,
            "rollback_allowed": False,
            "automatic_rollback": False,
            "steps": [],
        }

    backup_path = Path(
        str(receipt_verification.get("backup_path") or "")
    )
    receipt_path = Path(
        str(receipt_verification.get("receipt_path") or "")
    )
    current_records = (
        decisions.get("records", [])
        if isinstance(decisions, dict)
        else []
    )
    if not isinstance(current_records, list):
        current_records = []

    backup_payload = (
        load_json(backup_path, {})
        if backup_path.exists()
        else {}
    )
    if not isinstance(backup_payload, dict):
        backup_payload = {}

    backup_decisions = backup_payload.get("payload", {})
    if not isinstance(backup_decisions, dict):
        backup_decisions = {}
    backup_records = backup_decisions.get("records", [])
    if not isinstance(backup_records, list):
        backup_records = []

    backup_hash = canonical_json_hash({
        "records": backup_records,
    })
    current_hash = canonical_json_hash({
        "records": current_records,
    })

    recovery_ready = (
        backup_path.exists()
        and receipt_path.exists()
        and bool(receipt_verification.get("commit_id"))
    )

    return {
        "schema": "archon_review_recovery_check_v1",
        "available": True,
        "status": (
            "RECOVERY_READY"
            if recovery_ready
            else "RECOVERY_INCOMPLETE"
        ),
        "commit_id": receipt_verification.get(
            "commit_id"
        ),
        "recovery_ready": recovery_ready,
        "rollback_allowed": False,
        "automatic_rollback": False,
        "backup_path": str(backup_path),
        "receipt_path": str(receipt_path),
        "backup_record_count": len(backup_records),
        "current_record_count": len(current_records),
        "backup_hash": backup_hash,
        "current_hash": current_hash,
        "steps": [
            "Verify receipt and backup integrity.",
            "Stop automated Director runs.",
            "Copy current decision store to a separate incident snapshot.",
            "Restore backup manually only after explicit human approval.",
            "Rerun review validation and audit checks.",
        ],
        "scientific_policy": {
            "check_only": True,
            "automatic_rollback": False,
            "automatic_repair": False,
            "modifies_decision_store": False,
            "modifies_research_actions": False,
        },
    }
