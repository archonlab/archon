"""Action-patch rollback and lifecycle closure."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from Analyzer_next.research.director.common import atomic_write_json, canonical_json_hash, load_json, now_iso, safe_num
from Analyzer_next.research.director.contracts import ResearchAction
from Analyzer_next.research.director.governance.patch_preview import research_action_snapshot

def build_patch_rollback_readiness(
    root: Path,
    receipt_verification: Dict[str, Any],
    patch_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Assess rollback readiness without changing patch state or actions."""
    if not (
        isinstance(receipt_verification, dict)
        and receipt_verification.get("available")
    ):
        return {
            "schema": "archon_patch_rollback_readiness_v1",
            "available": False,
            "status": "NO_APPLICATION_TO_ROLL_BACK",
            "rollback_ready": False,
            "rollback_allowed": False,
            "automatic_rollback": False,
            "rollback_action_count": 0,
            "steps": [],
        }

    application_id = str(
        receipt_verification.get("application_id") or ""
    )
    backup_path = Path(
        str(receipt_verification.get("backup_path") or "")
    )
    receipt_path = Path(
        str(receipt_verification.get("receipt_path") or "")
    )
    patch_state_path = Path(
        str(receipt_verification.get("patch_state_path") or "")
    )

    overrides = (
        patch_state.get("overrides", [])
        if isinstance(patch_state, dict)
        else []
    )
    if not isinstance(overrides, list):
        overrides = []

    target_action_ids = {
        str(item)
        for item in receipt_verification.get(
            "applied_action_ids", []
        )
        if item
    }
    rollback_rows: List[Dict[str, Any]] = []
    invalid_rows: List[Dict[str, Any]] = []
    skipped_foreign_rows: List[Dict[str, Any]] = []
    seen_target_action_ids: set[str] = set()

    for item in overrides:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("action_id") or "")
        if action_id not in target_action_ids:
            skipped_foreign_rows.append({
                "action_id": action_id or None,
                "application_id": (
                    item.get("application_id")
                    or item.get("source_application_id")
                ),
                "reason": "OUTSIDE_RECEIPT_SCOPE",
            })
            continue

        seen_target_action_ids.add(action_id)
        override_application_id = str(
            item.get("application_id")
            or item.get("source_application_id")
            or ""
        )
        if override_application_id not in {
            application_id,
            "",
        }:
            invalid_rows.append({
                "action_id": item.get("action_id"),
                "reason": "APPLICATION_ID_MISMATCH",
                "expected": application_id,
                "actual": override_application_id,
                "manifest_row_application_id": item.get(
                    "manifest_row_application_id"
                ),
            })
            continue

        rollback = item.get("rollback_snapshot", {})
        if not isinstance(rollback, dict):
            invalid_rows.append({
                "action_id": action_id or None,
                "reason": "ROLLBACK_PAYLOAD_INVALID",
            })
            continue

        snapshot = rollback.get("snapshot", {})
        snapshot_hash = rollback.get("snapshot_hash")
        if (
            not isinstance(snapshot, dict)
            or canonical_json_hash(snapshot) != snapshot_hash
        ):
            invalid_rows.append({
                "action_id": action_id or None,
                "reason": "ROLLBACK_HASH_MISMATCH",
            })
            continue

        rollback_rows.append({
            "action_id": action_id,
            "rollback_snapshot": snapshot,
            "rollback_snapshot_hash": snapshot_hash,
            "current_snapshot_hash": item.get(
                "snapshot_hash"
            ),
            "source_application_id": override_application_id,
            "manifest_row_application_id": item.get(
                "manifest_row_application_id"
            ),
        })

    for action_id in sorted(
        target_action_ids - seen_target_action_ids
    ):
        invalid_rows.append({
            "action_id": action_id,
            "reason": "OVERRIDE_MISSING",
            "expected_application_id": application_id,
        })

    rollback_ready = (
        receipt_verification.get("status")
        in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}
        and backup_path.exists()
        and receipt_path.exists()
        and patch_state_path.exists()
        and bool(rollback_rows)
        and not invalid_rows
    )

    package_hash = canonical_json_hash({
        "application_id": application_id,
        "rows": rollback_rows,
    })
    rollback_package_id = (
        f"PATCH-ROLLBACK-{package_hash[:16].upper()}"
        if rollback_rows
        else None
    )

    return {
        "schema": "archon_patch_rollback_readiness_v1",
        "available": True,
        "status": (
            "ROLLBACK_READY"
            if rollback_ready
            else "ROLLBACK_INCOMPLETE"
        ),
        "application_id": application_id,
        "rollback_package_id": rollback_package_id,
        "rollback_package_hash": package_hash,
        "rollback_ready": rollback_ready,
        "rollback_allowed": False,
        "automatic_rollback": False,
        "rollback_action_count": len(rollback_rows),
        "invalid_row_count": len(invalid_rows),
        "skipped_foreign_row_count": len(
            skipped_foreign_rows
        ),
        "rows": rollback_rows,
        "invalid_rows": invalid_rows,
        "skipped_foreign_rows": skipped_foreign_rows,
        "backup_path": str(backup_path),
        "receipt_path": str(receipt_path),
        "patch_state_path": str(patch_state_path),
        "steps": [
            "Verify the application receipt and rollback package hash.",
            "Stop Director processes that may regenerate action state.",
            "Create an incident snapshot of current patch state.",
            "Require a separate explicit rollback request.",
            "Restore rollback snapshots atomically.",
            "Rerun reconciliation and integrity checks.",
        ],
        "scientific_policy": {
            "readiness_only": True,
            "automatic_rollback": False,
            "modifies_patch_state": False,
            "modifies_research_actions": False,
            "explicit_rollback_gateway_required": True,
        },
    }

def load_patch_rollback_request(root: Path) -> Dict[str, Any]:
    """Load an explicit atomic patch rollback request."""
    path = root / "patch_rollback_request.json"
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}

    return {
        "schema": "archon_patch_rollback_request_v1",
        "source": str(path),
        "exists": path.exists(),
        "rollback": bool(data.get("rollback", False)),
        "rollback_package_id": data.get("rollback_package_id"),
        "rollback_package_hash": data.get("rollback_package_hash"),
        "application_id": data.get("application_id"),
        "requested_at": data.get("requested_at"),
        "requested_by": data.get("requested_by"),
        "confirmation": data.get("confirmation"),
        "last_consumed_rollback_id": data.get(
            "last_consumed_rollback_id"
        ),
    }

def atomic_rollback_research_action_patches(
    root: Path,
    actions: List[ResearchAction],
    request: Dict[str, Any],
    rollback_readiness: Dict[str, Any],
    current_patch_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Atomically restore rollback snapshots into persistent action patch state."""
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

    rollback_rows = (
        rollback_readiness.get("rows", [])
        if isinstance(rollback_readiness, dict)
        else []
    )
    if not isinstance(rollback_rows, list):
        rollback_rows = []

    add_check(
        "explicit_rollback_flag",
        bool(request.get("rollback")),
        True,
        bool(request.get("rollback")),
    )
    add_check(
        "confirmation_phrase",
        request.get("confirmation")
        == "ROLLBACK_RESEARCH_ACTION_PATCHES",
        "ROLLBACK_RESEARCH_ACTION_PATCHES",
        request.get("confirmation"),
    )
    add_check(
        "rollback_ready",
        bool(rollback_readiness.get("rollback_ready")),
        True,
        bool(rollback_readiness.get("rollback_ready")),
    )
    add_check(
        "rollback_package_id_match",
        request.get("rollback_package_id")
        == rollback_readiness.get("rollback_package_id"),
        rollback_readiness.get("rollback_package_id"),
        request.get("rollback_package_id"),
    )
    add_check(
        "rollback_package_hash_match",
        request.get("rollback_package_hash")
        == rollback_readiness.get("rollback_package_hash"),
        rollback_readiness.get("rollback_package_hash"),
        request.get("rollback_package_hash"),
    )
    add_check(
        "application_id_match",
        request.get("application_id")
        == rollback_readiness.get("application_id"),
        rollback_readiness.get("application_id"),
        request.get("application_id"),
    )
    add_check(
        "rollback_rows_present",
        len(rollback_rows) > 0,
        ">0",
        len(rollback_rows),
    )

    actions_by_id = {
        action.action_id: action
        for action in actions
    }
    patch_overrides = {
        str(item.get("action_id")): item
        for item in (
            current_patch_state.get("overrides", [])
            if isinstance(current_patch_state, dict)
            else []
        )
        if isinstance(item, dict) and item.get("action_id")
    }

    stale_rows: List[Dict[str, Any]] = []
    invalid_snapshots: List[Dict[str, Any]] = []

    for row in rollback_rows:
        if not isinstance(row, dict):
            continue
        action_id = str(row.get("action_id") or "")
        action = actions_by_id.get(action_id)
        current_override = patch_overrides.get(action_id)

        if action is None:
            stale_rows.append({
                "action_id": action_id or None,
                "reason": "ACTION_MISSING",
            })
            continue

        if not isinstance(current_override, dict):
            stale_rows.append({
                "action_id": action_id,
                "reason": "CURRENT_OVERRIDE_MISSING",
            })
            continue

        current_action_hash = canonical_json_hash(
            research_action_snapshot(action)
        )
        expected_current_hash = row.get(
            "current_snapshot_hash"
        )
        if current_action_hash != expected_current_hash:
            stale_rows.append({
                "action_id": action_id,
                "reason": "CURRENT_ACTION_HASH_MISMATCH",
                "expected": expected_current_hash,
                "actual": current_action_hash,
            })

        rollback_snapshot = row.get(
            "rollback_snapshot", {}
        )
        rollback_hash = row.get(
            "rollback_snapshot_hash"
        )
        if (
            not isinstance(rollback_snapshot, dict)
            or canonical_json_hash(rollback_snapshot)
            != rollback_hash
        ):
            invalid_snapshots.append({
                "action_id": action_id,
                "reason": "ROLLBACK_SNAPSHOT_HASH_MISMATCH",
            })

    add_check(
        "all_current_action_hashes_match",
        not stale_rows,
        0,
        len(stale_rows),
    )
    add_check(
        "all_rollback_snapshots_valid",
        not invalid_snapshots,
        0,
        len(invalid_snapshots),
    )

    failed_checks = [
        item for item in checks
        if not item.get("passed")
    ]

    if failed_checks:
        return {
            "schema": "archon_atomic_patch_rollback_result_v1",
            "attempted": bool(request.get("rollback")),
            "rolled_back": False,
            "status": (
                "NO_ROLLBACK_REQUEST"
                if not request.get("rollback")
                else "REFUSED"
            ),
            "rollback_package_id": rollback_readiness.get(
                "rollback_package_id"
            ),
            "failed_check_count": len(failed_checks),
            "checks": checks,
            "stale_rows": stale_rows,
            "invalid_snapshots": invalid_snapshots,
            "rolled_back_action_count": 0,
            "backup_path": None,
            "receipt_path": None,
            "patch_state_path": str(
                root / "research_action_patch_state.json"
            ),
            "scientific_policy": {
                "research_action_changes_only": True,
                "scientific_metric_changes": False,
                "decision_history_changes": False,
                "automatic_rollback": False,
            },
        }

    application_id = str(
        rollback_readiness.get("application_id") or ""
    )
    rollback_id = (
        f"PATCH-ROLLBACK-EXEC-"
        f"{str(rollback_readiness.get('rollback_package_hash'))[:16].upper()}"
    )

    rollback_by_action = {
        str(item.get("action_id")): item
        for item in rollback_rows
        if isinstance(item, dict) and item.get("action_id")
    }

    restored_action_ids: List[str] = []
    new_overrides: Dict[str, Dict[str, Any]] = {
        action_id: dict(item)
        for action_id, item in patch_overrides.items()
    }

    for action_id, row in rollback_by_action.items():
        rollback_snapshot = dict(
            row.get("rollback_snapshot", {})
        )
        rollback_hash = row.get(
            "rollback_snapshot_hash"
        )

        # Preserve rollback as a persistent override only when it differs from
        # the freshly generated base action. Otherwise remove the override.
        action = actions_by_id[action_id]
        generated_snapshot = research_action_snapshot(action)
        current_override = patch_overrides[action_id]
        current_snapshot = current_override.get("snapshot", {})

        # action currently includes the patched override, so restore in memory first.
        for field_name in (
            "title",
            "suggested_target",
            "done_when",
            "rationale",
        ):
            setattr(action, field_name, rollback_snapshot.get(field_name))

        restored_snapshot = research_action_snapshot(action)
        if canonical_json_hash(restored_snapshot) != rollback_hash:
            raise RuntimeError(
                f"Rollback restoration hash mismatch for {action_id}"
            )

        new_overrides[action_id] = {
            "action_id": action_id,
            "snapshot": rollback_snapshot,
            "snapshot_hash": rollback_hash,
            "source_application_id": application_id,
            "rollback_id": rollback_id,
            "rolled_back_at": now_iso(),
            "previous_snapshot": current_snapshot,
            "previous_snapshot_hash": row.get(
                "current_snapshot_hash"
            ),
            "rollback_origin": "application_manifest_snapshot",
        }
        restored_action_ids.append(action_id)

    patch_state_path = root / "research_action_patch_state.json"
    backup_path = (
        root
        / (
            "research_action_patch_state.pre_rollback."
            f"{rollback_id}.json"
        )
    )
    receipt_path = (
        root
        / (
            "patch_rollback_receipt."
            f"{rollback_id}.json"
        )
    )

    atomic_write_json(
        backup_path,
        {
            "schema": "archon_research_action_patch_state_pre_rollback_v1",
            "backed_up_at": now_iso(),
            "rollback_id": rollback_id,
            "payload": load_json(patch_state_path, {}),
        },
    )

    final_patch_state = {
        "schema": "archon_research_action_patch_state_v1",
        "updated_at": now_iso(),
        "last_application_id": current_patch_state.get(
            "last_application_id"
        ),
        "last_manifest_id": current_patch_state.get(
            "last_manifest_id"
        ),
        "last_rollback_id": rollback_id,
        "source_commit_id": current_patch_state.get(
            "source_commit_id"
        ),
        "overrides": sorted(
            new_overrides.values(),
            key=lambda item: str(item.get("action_id") or ""),
        ),
        "scientific_policy": {
            "persistent_overrides": True,
            "changes_research_actions_only": True,
            "changes_scientific_metrics": False,
            "decision_history_changes": False,
        },
    }
    atomic_write_json(patch_state_path, final_patch_state)

    receipt = {
        "schema": "archon_patch_rollback_receipt_v1",
        "rolled_back_at": now_iso(),
        "rollback_id": rollback_id,
        "rollback_package_id": rollback_readiness.get(
            "rollback_package_id"
        ),
        "rollback_package_hash": rollback_readiness.get(
            "rollback_package_hash"
        ),
        "source_application_id": application_id,
        "restored_action_ids": restored_action_ids,
        "restored_action_count": len(restored_action_ids),
        "patch_state_hash": canonical_json_hash(
            final_patch_state
        ),
        "backup_path": str(backup_path),
        "patch_state_path": str(patch_state_path),
        "scientific_metric_changes": False,
        "decision_history_changes": False,
    }
    atomic_write_json(receipt_path, receipt)

    atomic_write_json(
        root / "patch_rollback_request.json",
        {
            "schema": "archon_patch_rollback_request_v1",
            "rollback": False,
            "rollback_package_id": None,
            "rollback_package_hash": None,
            "application_id": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "last_consumed_rollback_id": rollback_id,
        },
    )

    return {
        "schema": "archon_atomic_patch_rollback_result_v1",
        "attempted": True,
        "rolled_back": True,
        "status": "ROLLED_BACK",
        "rollback_id": rollback_id,
        "rollback_package_id": rollback_readiness.get(
            "rollback_package_id"
        ),
        "failed_check_count": 0,
        "checks": checks,
        "stale_rows": [],
        "invalid_snapshots": [],
        "rolled_back_action_count": len(restored_action_ids),
        "rolled_back_action_ids": restored_action_ids,
        "backup_path": str(backup_path),
        "receipt_path": str(receipt_path),
        "patch_state_path": str(patch_state_path),
        "scientific_policy": {
            "research_action_changes_only": True,
            "scientific_metric_changes": False,
            "decision_history_changes": False,
            "automatic_rollback": False,
            "request_consumed_after_success": True,
        },
    }

def load_latest_patch_rollback_receipt(root: Path) -> Dict[str, Any]:
    """Load the newest patch rollback receipt, if one exists."""
    receipts = sorted(
        root.glob("patch_rollback_receipt.PATCH-ROLLBACK-EXEC-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not receipts:
        return {
            "schema": "archon_patch_rollback_receipt_lookup_v1",
            "available": False,
            "path": None,
            "receipt": {},
        }

    path = receipts[0]
    receipt = load_json(path, {})
    if not isinstance(receipt, dict):
        receipt = {}

    return {
        "schema": "archon_patch_rollback_receipt_lookup_v1",
        "available": True,
        "path": str(path),
        "receipt": receipt,
    }

def verify_patch_rollback_receipt(
    root: Path,
    actions: List[ResearchAction],
    receipt_lookup: Dict[str, Any],
    patch_state: Dict[str, Any],
    rollback_request: Dict[str, Any],
) -> Dict[str, Any]:
    """Verify rollback receipt, restored snapshots, state hash, and consumed request."""
    if not (
        isinstance(receipt_lookup, dict)
        and receipt_lookup.get("available")
    ):
        return {
            "schema": "archon_patch_rollback_receipt_verification_v1",
            "available": False,
            "status": "NO_ROLLBACK_RECEIPT",
            "rollback_id": None,
            "check_count": 0,
            "failed_check_count": 0,
            "warning_count": 0,
            "checks": [],
            "verified_action_count": 0,
            "mismatched_action_count": 0,
            "scientific_policy": {
                "verification_only": True,
                "automatic_repair": False,
                "automatic_reapply": False,
                "decision_history_changes": False,
                "scientific_metric_changes": False,
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

    rollback_id = str(receipt.get("rollback_id") or "")
    receipt_path = Path(str(receipt_lookup.get("path") or ""))
    patch_state_path = root / "research_action_patch_state.json"
    backup_path = Path(str(receipt.get("backup_path") or ""))

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
        "rollback_receipt_exists",
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
        "pre_rollback_backup_exists",
        backup_path.exists(),
        True,
        backup_path.exists(),
    )
    add_check(
        "rollback_request_consumed",
        (
            not bool(rollback_request.get("rollback"))
            and rollback_request.get(
                "last_consumed_rollback_id"
            ) == rollback_id
        ),
        {
            "rollback": False,
            "last_consumed_rollback_id": rollback_id,
        },
        {
            "rollback": bool(rollback_request.get("rollback")),
            "last_consumed_rollback_id": (
                rollback_request.get(
                    "last_consumed_rollback_id"
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

    override_by_id = {
        str(item.get("action_id")): item
        for item in overrides
        if isinstance(item, dict) and item.get("action_id")
    }

    restored_ids = [
        str(item)
        for item in receipt.get("restored_action_ids", [])
        if item
    ]
    mismatches: List[Dict[str, Any]] = []
    verified_count = 0

    for action_id in restored_ids:
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
                "reason": "ROLLBACK_OVERRIDE_MISSING",
            })
            continue

        snapshot = override.get("snapshot", {})
        snapshot_hash = override.get("snapshot_hash")
        if not isinstance(snapshot, dict):
            mismatches.append({
                "action_id": action_id,
                "reason": "RESTORED_SNAPSHOT_INVALID",
            })
            continue

        persisted_hash = canonical_json_hash(snapshot)
        action_hash = canonical_json_hash(
            research_action_snapshot(action)
        )

        if persisted_hash != snapshot_hash:
            mismatches.append({
                "action_id": action_id,
                "reason": "RESTORED_SNAPSHOT_HASH_MISMATCH",
                "expected": snapshot_hash,
                "actual": persisted_hash,
            })
            continue

        if action_hash != snapshot_hash:
            mismatches.append({
                "action_id": action_id,
                "reason": "IN_MEMORY_RESTORED_ACTION_MISMATCH",
                "expected": snapshot_hash,
                "actual": action_hash,
            })
            continue

        if str(override.get("rollback_id") or "") != rollback_id:
            mismatches.append({
                "action_id": action_id,
                "reason": "ROLLBACK_ID_MISMATCH",
                "expected": rollback_id,
                "actual": override.get("rollback_id"),
            })
            continue

        verified_count += 1

    add_check(
        "restored_action_count_match",
        verified_count + len(mismatches)
        == int(safe_num(receipt.get("restored_action_count"), 0)),
        int(safe_num(receipt.get("restored_action_count"), 0)),
        verified_count + len(mismatches),
    )
    add_check(
        "all_restored_actions_verified",
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
        "schema": "archon_patch_rollback_receipt_verification_v1",
        "available": True,
        "status": status,
        "rollback_id": rollback_id,
        "source_application_id": receipt.get(
            "source_application_id"
        ),
        "rollback_package_id": receipt.get(
            "rollback_package_id"
        ),
        "receipt_path": str(receipt_path),
        "patch_state_path": str(patch_state_path),
        "backup_path": str(backup_path),
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "warning_count": len(warnings),
        "checks": checks,
        "verified_action_count": verified_count,
        "mismatched_action_count": len(mismatches),
        "mismatches": mismatches,
        "scientific_policy": {
            "verification_only": True,
            "automatic_repair": False,
            "automatic_reapply": False,
            "decision_history_changes": False,
            "scientific_metric_changes": False,
        },
    }

def build_patch_lifecycle_closure(
    application_receipt: Dict[str, Any],
    rollback_receipt: Dict[str, Any],
    patch_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify the patch lifecycle as inactive, active, rolled back, or inconsistent."""
    application_available = bool(
        isinstance(application_receipt, dict)
        and application_receipt.get("available")
    )
    rollback_available = bool(
        isinstance(rollback_receipt, dict)
        and rollback_receipt.get("available")
    )

    application_status = (
        str(application_receipt.get("status") or "")
        if isinstance(application_receipt, dict)
        else ""
    )
    rollback_status = (
        str(rollback_receipt.get("status") or "")
        if isinstance(rollback_receipt, dict)
        else ""
    )

    override_count = int(
        safe_num(
            patch_state.get("override_count")
            if isinstance(patch_state, dict)
            else 0,
            0,
        )
    )
    last_application_id = (
        patch_state.get("last_application_id")
        if isinstance(patch_state, dict)
        else None
    )
    last_rollback_id = (
        patch_state.get("last_rollback_id")
        if isinstance(patch_state, dict)
        else None
    )

    reasons: List[str] = []

    if not application_available and not rollback_available:
        lifecycle_status = "INACTIVE"
        closed = True
        reasons.append("No patch application or rollback receipt exists.")
    elif rollback_available:
        if rollback_status in {
            "VERIFIED",
            "VERIFIED_WITH_WARNINGS",
        } and last_rollback_id:
            lifecycle_status = "ROLLED_BACK"
            closed = True
            reasons.append(
                "A verified rollback receipt closes the active application lifecycle."
            )
        else:
            lifecycle_status = "INCONSISTENT"
            closed = False
            reasons.append(
                "Rollback artifacts exist but verification or patch-state linkage failed."
            )
    elif application_available:
        if application_status in {
            "VERIFIED",
            "VERIFIED_WITH_WARNINGS",
        } and override_count > 0 and last_application_id:
            lifecycle_status = "ACTIVE"
            closed = False
            reasons.append(
                "A verified application remains active in persistent patch state."
            )
        else:
            lifecycle_status = "INCONSISTENT"
            closed = False
            reasons.append(
                "Application artifacts exist but active patch-state invariants failed."
            )
    else:
        lifecycle_status = "INCONSISTENT"
        closed = False
        reasons.append("Lifecycle state could not be classified safely.")

    return {
        "schema": "archon_patch_lifecycle_closure_v1",
        "status": lifecycle_status,
        "closed": closed,
        "application_available": application_available,
        "application_status": application_status or "NO_RECEIPT",
        "rollback_available": rollback_available,
        "rollback_status": rollback_status or "NO_ROLLBACK_RECEIPT",
        "last_application_id": last_application_id,
        "last_rollback_id": last_rollback_id,
        "persistent_override_count": override_count,
        "reasons": reasons,
        "closure_policy": {
            "ACTIVE": (
                "Application is verified and still represented in persistent overrides."
            ),
            "ROLLED_BACK": (
                "Rollback is verified and closes the latest application lifecycle."
            ),
            "INACTIVE": (
                "No application lifecycle has begun."
            ),
            "INCONSISTENT": (
                "Artifacts disagree and require manual investigation."
            ),
        },
        "scientific_policy": {
            "classification_only": True,
            "automatic_repair": False,
            "automatic_application": False,
            "automatic_rollback": False,
            "decision_history_changes": False,
            "scientific_metric_changes": False,
        },
    }

def close_application_lifecycle_after_verified_rollback(
    application_receipt: Dict[str, Any],
    rollback_readiness: Dict[str, Any],
    rollback_receipt: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Mark an application historical only after its rollback is verified."""
    application = (
        dict(application_receipt)
        if isinstance(application_receipt, dict)
        else {}
    )
    readiness = (
        dict(rollback_readiness)
        if isinstance(rollback_readiness, dict)
        else {}
    )
    if not (
        rollback_receipt.get("status")
        in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}
        and rollback_receipt.get("source_application_id")
        == application.get("application_id")
        and rollback_receipt.get("rollback_id")
    ):
        return application, readiness

    application["pre_rollback_verification"] = {
        "status": application.get("status"),
        "failed_check_count": application.get(
            "failed_check_count", 0
        ),
        "warning_count": application.get("warning_count", 0),
        "checks": application.get("checks", []),
        "mismatches": application.get("mismatches", []),
    }
    application["status"] = (
        "SUPERSEDED_BY_VERIFIED_ROLLBACK"
    )
    application["active"] = False
    application["failed_check_count"] = 0
    application["warning_count"] = 0
    application["checks"] = []
    application["verified_action_count"] = int(
        safe_num(
            rollback_receipt.get("verified_action_count"),
            0,
        )
    )
    application["mismatched_action_count"] = 0
    application["mismatches"] = []
    application["superseded_by_rollback_id"] = (
        rollback_receipt.get("rollback_id")
    )

    readiness["pre_rollback_assessment"] = {
        "status": readiness.get("status"),
        "invalid_row_count": readiness.get(
            "invalid_row_count", 0
        ),
        "invalid_rows": readiness.get("invalid_rows", []),
    }
    readiness["status"] = "ROLLBACK_COMPLETED"
    readiness["rollback_ready"] = False
    readiness["rollback_allowed"] = False
    readiness["rollback_action_count"] = int(
        safe_num(
            rollback_receipt.get("verified_action_count"),
            0,
        )
    )
    readiness["invalid_row_count"] = 0
    readiness["invalid_rows"] = []
    readiness["completed_rollback_id"] = (
        rollback_receipt.get("rollback_id")
    )
    return application, readiness
