"""Atomic action-patch application lifecycle."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from Analyzer_next.research.director.common import atomic_write_json, canonical_json_hash, load_json, now_iso, safe_num
from Analyzer_next.research.director.contracts import ResearchAction
from Analyzer_next.research.director.governance.patch_preview import research_action_snapshot

def load_patch_application_request(root: Path) -> Dict[str, Any]:
    """Load an explicit atomic ResearchAction patch application request."""
    path = root / "patch_application_request.json"
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}

    return {
        "schema": "archon_patch_application_request_v1",
        "source": str(path),
        "exists": path.exists(),
        "apply": bool(data.get("apply", False)),
        "application_manifest_id": data.get(
            "application_manifest_id"
        ),
        "manifest_hash": data.get("manifest_hash"),
        "source_commit_id": data.get("source_commit_id"),
        "requested_at": data.get("requested_at"),
        "requested_by": data.get("requested_by"),
        "confirmation": data.get("confirmation"),
        "last_consumed_application_id": data.get(
            "last_consumed_application_id"
        ),
    }

def atomic_apply_research_action_patches(
    root: Path,
    actions: List[ResearchAction],
    request: Dict[str, Any],
    manifest: Dict[str, Any],
    current_patch_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Atomically persist and apply a verified ResearchAction patch manifest."""
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

    rows = (
        manifest.get("rows", [])
        if isinstance(manifest, dict)
        else []
    )
    if not isinstance(rows, list):
        rows = []

    add_check(
        "explicit_apply_flag",
        bool(request.get("apply")),
        True,
        bool(request.get("apply")),
    )
    add_check(
        "confirmation_phrase",
        request.get("confirmation")
        == "APPLY_RESEARCH_ACTION_PATCHES",
        "APPLY_RESEARCH_ACTION_PATCHES",
        request.get("confirmation"),
    )
    add_check(
        "manifest_final_ready",
        bool(manifest.get("final_ready")),
        True,
        bool(manifest.get("final_ready")),
    )
    add_check(
        "application_manifest_id_match",
        request.get("application_manifest_id")
        == manifest.get("application_manifest_id"),
        manifest.get("application_manifest_id"),
        request.get("application_manifest_id"),
    )
    add_check(
        "manifest_hash_match",
        request.get("manifest_hash")
        == manifest.get("manifest_hash"),
        manifest.get("manifest_hash"),
        request.get("manifest_hash"),
    )
    add_check(
        "source_commit_id_match",
        request.get("source_commit_id")
        == manifest.get("source_commit_id"),
        manifest.get("source_commit_id"),
        request.get("source_commit_id"),
    )
    add_check(
        "manifest_rows_present",
        len(rows) > 0,
        ">0",
        len(rows),
    )

    actions_by_id = {
        action.action_id: action
        for action in actions
    }

    stale_rows: List[Dict[str, Any]] = []
    missing_snapshots: List[str] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        action_id = str(row.get("target_action_id") or "")
        action = actions_by_id.get(action_id)

        if action is None:
            stale_rows.append({
                "action_id": action_id or None,
                "reason": "TARGET_ACTION_MISSING",
            })
            continue

        current_hash = canonical_json_hash(
            research_action_snapshot(action)
        )
        expected_hash = row.get("expected_action_hash")
        if current_hash != expected_hash:
            stale_rows.append({
                "action_id": action_id,
                "reason": "ACTION_HASH_MISMATCH",
                "expected": expected_hash,
                "actual": current_hash,
            })

        rollback_snapshot = row.get("rollback_snapshot", {})
        if (
            not isinstance(rollback_snapshot, dict)
            or not rollback_snapshot.get("snapshot")
            or rollback_snapshot.get("snapshot_hash")
            != expected_hash
        ):
            missing_snapshots.append(action_id)

    add_check(
        "all_action_hashes_match",
        not stale_rows,
        0,
        len(stale_rows),
    )
    add_check(
        "rollback_snapshots_valid",
        not missing_snapshots,
        0,
        len(missing_snapshots),
    )

    failed_checks = [
        item for item in checks
        if not item.get("passed")
    ]

    if failed_checks:
        return {
            "schema": "archon_atomic_research_action_patch_result_v1",
            "attempted": bool(request.get("apply")),
            "applied": False,
            "status": (
                "NO_APPLICATION_REQUEST"
                if not request.get("apply")
                else "REFUSED"
            ),
            "application_manifest_id": manifest.get(
                "application_manifest_id"
            ),
            "failed_check_count": len(failed_checks),
            "checks": checks,
            "stale_rows": stale_rows,
            "missing_rollback_snapshots": missing_snapshots,
            "applied_action_count": 0,
            "backup_path": None,
            "receipt_path": None,
            "patch_state_path": str(
                root / "research_action_patch_state.json"
            ),
            "scientific_policy": {
                "research_action_changes_only": True,
                "scientific_metric_changes": False,
                "automatic_application": False,
            },
        }

    existing_overrides = {
        str(item.get("action_id")): item
        for item in (
            current_patch_state.get("overrides", [])
            if isinstance(current_patch_state, dict)
            else []
        )
        if isinstance(item, dict) and item.get("action_id")
    }

    applied_action_ids: List[str] = []
    application_id = (
        f"PATCH-APPLICATION-"
        f"{str(manifest.get('manifest_hash'))[:16].upper()}"
    )

    for row in rows:
        if not isinstance(row, dict):
            continue
        action_id = str(row.get("target_action_id") or "")
        action = actions_by_id[action_id]

        after_snapshot = research_action_snapshot(action)
        for operation in row.get("operations", []):
            if not isinstance(operation, dict):
                continue
            field_name = str(operation.get("field") or "")
            if field_name in {
                "title",
                "suggested_target",
                "done_when",
                "rationale",
            }:
                after_snapshot[field_name] = operation.get("after")

        resulting_hash = canonical_json_hash(after_snapshot)
        if resulting_hash != row.get("resulting_action_hash"):
            return {
                "schema": "archon_atomic_research_action_patch_result_v1",
                "attempted": True,
                "applied": False,
                "status": "REFUSED",
                "application_manifest_id": manifest.get(
                    "application_manifest_id"
                ),
                "failed_check_count": 1,
                "checks": checks + [{
                    "name": "resulting_action_hash_match",
                    "passed": False,
                    "expected": row.get("resulting_action_hash"),
                    "actual": resulting_hash,
                }],
                "stale_rows": [],
                "missing_rollback_snapshots": [],
                "applied_action_count": 0,
                "backup_path": None,
                "receipt_path": None,
                "patch_state_path": str(
                    root / "research_action_patch_state.json"
                ),
            }

        existing_overrides[action_id] = {
            "action_id": action_id,
            "snapshot": after_snapshot,
            "snapshot_hash": resulting_hash,
            "source_proposal_id": row.get("proposal_id"),
            "source_proposal_kind": row.get("proposal_kind") or "PATCH",
            "application_mode": row.get("application_mode") or "SEMANTIC_PATCH",
            "source_review_id": row.get("review_id"),
            "source_commit_id": row.get("source_commit_id"),
            # Transaction-level ID links the override to the application receipt
            # and is the canonical key used by rollback readiness.
            "application_id": application_id,
            # Preserve the manifest row identifier separately for provenance.
            "manifest_row_application_id": row.get("application_id"),
            "applied_at": now_iso(),
            "rollback_snapshot": row.get("rollback_snapshot"),
        }
        applied_action_ids.append(action_id)

    patch_state_path = root / "research_action_patch_state.json"
    backup_path = (
        root
        / (
            "research_action_patch_state.backup."
            f"{application_id}.json"
        )
    )
    receipt_path = (
        root
        / (
            "patch_application_receipt."
            f"{application_id}.json"
        )
    )

    if patch_state_path.exists():
        atomic_write_json(
            backup_path,
            {
                "schema": "archon_research_action_patch_state_backup_v1",
                "backed_up_at": now_iso(),
                "application_id": application_id,
                "payload": load_json(patch_state_path, {}),
            },
        )
    else:
        atomic_write_json(
            backup_path,
            {
                "schema": "archon_research_action_patch_state_backup_v1",
                "backed_up_at": now_iso(),
                "application_id": application_id,
                "payload": {
                    "schema": "archon_research_action_patch_state_v1",
                    "overrides": [],
                },
            },
        )

    final_patch_state = {
        "schema": "archon_research_action_patch_state_v1",
        "updated_at": now_iso(),
        "last_application_id": application_id,
        "last_manifest_id": manifest.get(
            "application_manifest_id"
        ),
        "source_commit_id": manifest.get("source_commit_id"),
        "overrides": sorted(
            existing_overrides.values(),
            key=lambda item: str(item.get("action_id") or ""),
        ),
        "scientific_policy": {
            "persistent_overrides": True,
            "changes_research_actions_only": True,
            "changes_scientific_metrics": False,
        },
    }
    atomic_write_json(patch_state_path, final_patch_state)

    # Apply the committed snapshots to the current in-memory actions.
    for action_id in applied_action_ids:
        action = actions_by_id[action_id]
        snapshot = existing_overrides[action_id]["snapshot"]
        for field_name in (
            "title",
            "suggested_target",
            "done_when",
            "rationale",
        ):
            setattr(action, field_name, snapshot.get(field_name))

    receipt = {
        "schema": "archon_patch_application_receipt_v1",
        "applied_at": now_iso(),
        "application_id": application_id,
        "application_manifest_id": manifest.get(
            "application_manifest_id"
        ),
        "manifest_hash": manifest.get("manifest_hash"),
        "source_commit_id": manifest.get("source_commit_id"),
        "applied_action_ids": applied_action_ids,
        "applied_action_count": len(applied_action_ids),
        "semantic_change_count": sum(
            1
            for row in rows
            if isinstance(row, dict)
            and row.get("expected_action_hash")
            != row.get("resulting_action_hash")
        ),
        "direct_action_activation_count": sum(
            1
            for row in rows
            if isinstance(row, dict)
            and row.get("application_mode") == "DIRECT_ACTION_ACTIVATION"
        ),
        "patch_state_hash": canonical_json_hash(
            final_patch_state
        ),
        "backup_path": str(backup_path),
        "patch_state_path": str(patch_state_path),
        "scientific_metric_changes": False,
    }
    atomic_write_json(receipt_path, receipt)

    # Consume the request to prevent accidental replay.
    atomic_write_json(
        root / "patch_application_request.json",
        {
            "schema": "archon_patch_application_request_v1",
            "apply": False,
            "application_manifest_id": None,
            "manifest_hash": None,
            "source_commit_id": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "last_consumed_application_id": application_id,
        },
    )

    return {
        "schema": "archon_atomic_research_action_patch_result_v1",
        "attempted": True,
        "applied": True,
        "status": "APPLIED",
        "application_id": application_id,
        "application_manifest_id": manifest.get(
            "application_manifest_id"
        ),
        "failed_check_count": 0,
        "checks": checks,
        "stale_rows": [],
        "missing_rollback_snapshots": [],
        "applied_action_count": len(applied_action_ids),
        "applied_action_ids": applied_action_ids,
        "backup_path": str(backup_path),
        "receipt_path": str(receipt_path),
        "patch_state_path": str(patch_state_path),
        "scientific_policy": {
            "research_action_changes_only": True,
            "scientific_metric_changes": False,
            "automatic_application": False,
            "direct_action_activation_may_preserve_snapshot": True,
            "request_consumed_after_success": True,
        },
    }

def load_latest_patch_application_receipt(root: Path) -> Dict[str, Any]:
    """Load the newest ResearchAction patch application receipt."""
    receipts = sorted(
        root.glob("patch_application_receipt.PATCH-APPLICATION-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not receipts:
        return {
            "schema": "archon_patch_application_receipt_lookup_v1",
            "available": False,
            "path": None,
            "receipt": {},
        }

    path = receipts[0]
    receipt = load_json(path, {})
    if not isinstance(receipt, dict):
        receipt = {}

    return {
        "schema": "archon_patch_application_receipt_lookup_v1",
        "available": True,
        "path": str(path),
        "receipt": receipt,
    }

def verify_patch_application_receipt(
    root: Path,
    actions: List[ResearchAction],
    receipt_lookup: Dict[str, Any],
    patch_state: Dict[str, Any],
    application_request: Dict[str, Any],
) -> Dict[str, Any]:
    """Verify persisted action patches against receipt and in-memory actions."""
    if not (
        isinstance(receipt_lookup, dict)
        and receipt_lookup.get("available")
    ):
        return {
            "schema": "archon_patch_application_receipt_verification_v1",
            "available": False,
            "status": "NO_RECEIPT",
            "application_id": None,
            "check_count": 0,
            "failed_check_count": 0,
            "warning_count": 0,
            "checks": [],
            "verified_action_count": 0,
            "mismatched_action_count": 0,
            "scientific_policy": {
                "verification_only": True,
                "automatic_repair": False,
                "automatic_rollback": False,
            },
        }

    receipt = receipt_lookup.get("receipt", {})
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

    application_id = str(receipt.get("application_id") or "")
    receipt_path = Path(str(receipt_lookup.get("path") or ""))
    patch_state_path = root / "research_action_patch_state.json"
    backup_path = (
        root
        / f"research_action_patch_state.backup.{application_id}.json"
    )

    patch_state_payload = load_json(patch_state_path, {})
    if not isinstance(patch_state_payload, dict):
        patch_state_payload = {}

    current_patch_state_hash = canonical_json_hash(
        patch_state_payload
    )
    expected_patch_state_hash = receipt.get(
        "patch_state_hash"
    )

    add_check(
        "receipt_exists",
        receipt_path.exists(),
        True,
        receipt_path.exists(),
    )
    add_check(
        "patch_state_exists",
        patch_state_path.exists(),
        True,
        patch_state_path.exists(),
    )
    add_check(
        "patch_state_hash_match",
        current_patch_state_hash == expected_patch_state_hash,
        expected_patch_state_hash,
        current_patch_state_hash,
    )
    add_check(
        "backup_exists",
        backup_path.exists(),
        True,
        backup_path.exists(),
    )
    add_check(
        "request_consumed",
        (
            not bool(application_request.get("apply"))
            and application_request.get(
                "last_consumed_application_id"
            ) == application_id
        ),
        {
            "apply": False,
            "last_consumed_application_id": application_id,
        },
        {
            "apply": bool(application_request.get("apply")),
            "last_consumed_application_id": (
                application_request.get(
                    "last_consumed_application_id"
                )
            ),
        },
        severity="WARNING",
    )

    actions_by_id = {
        action.action_id: action
        for action in actions
    }
    overrides = (
        patch_state.get("overrides", [])
        if isinstance(patch_state, dict)
        else []
    )
    if not isinstance(overrides, list):
        overrides = []

    applied_ids = [
        str(item)
        for item in receipt.get("applied_action_ids", [])
        if item
    ]
    mismatches: List[Dict[str, Any]] = []
    verified_count = 0

    override_by_id = {
        str(item.get("action_id")): item
        for item in overrides
        if isinstance(item, dict) and item.get("action_id")
    }

    for action_id in applied_ids:
        action = actions_by_id.get(action_id)
        override = override_by_id.get(action_id)

        if action is None:
            mismatches.append({
                "action_id": action_id,
                "reason": "ACTION_MISSING",
            })
            continue
        if not isinstance(override, dict):
            mismatches.append({
                "action_id": action_id,
                "reason": "OVERRIDE_MISSING",
            })
            continue

        snapshot = override.get("snapshot", {})
        if not isinstance(snapshot, dict):
            mismatches.append({
                "action_id": action_id,
                "reason": "SNAPSHOT_INVALID",
            })
            continue

        action_hash = canonical_json_hash(
            research_action_snapshot(action)
        )
        expected_hash = override.get("snapshot_hash")
        snapshot_hash = canonical_json_hash(snapshot)

        if action_hash != expected_hash:
            mismatches.append({
                "action_id": action_id,
                "reason": "IN_MEMORY_ACTION_HASH_MISMATCH",
                "expected": expected_hash,
                "actual": action_hash,
            })
            continue

        if snapshot_hash != expected_hash:
            mismatches.append({
                "action_id": action_id,
                "reason": "PERSISTED_SNAPSHOT_HASH_MISMATCH",
                "expected": expected_hash,
                "actual": snapshot_hash,
            })
            continue

        rollback_snapshot = override.get(
            "rollback_snapshot", {}
        )
        if (
            not isinstance(rollback_snapshot, dict)
            or not rollback_snapshot.get("snapshot")
            or not rollback_snapshot.get("snapshot_hash")
        ):
            mismatches.append({
                "action_id": action_id,
                "reason": "ROLLBACK_SNAPSHOT_MISSING",
            })
            continue

        verified_count += 1

    add_check(
        "applied_action_count_match",
        verified_count + len(mismatches)
        == int(safe_num(receipt.get("applied_action_count"), 0)),
        int(safe_num(receipt.get("applied_action_count"), 0)),
        verified_count + len(mismatches),
    )
    add_check(
        "all_applied_actions_verified",
        not mismatches,
        0,
        len(mismatches),
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
        "schema": "archon_patch_application_receipt_verification_v1",
        "available": True,
        "status": status,
        "application_id": application_id,
        "application_manifest_id": receipt.get(
            "application_manifest_id"
        ),
        "receipt_path": str(receipt_path),
        "patch_state_path": str(patch_state_path),
        "backup_path": str(backup_path),
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "warning_count": len(warnings),
        "checks": checks,
        "verified_action_count": verified_count,
        "applied_action_ids": applied_ids,
        "mismatched_action_count": len(mismatches),
        "mismatches": mismatches,
        "scientific_policy": {
            "verification_only": True,
            "automatic_repair": False,
            "automatic_rollback": False,
            "research_action_changes": False,
        },
    }
