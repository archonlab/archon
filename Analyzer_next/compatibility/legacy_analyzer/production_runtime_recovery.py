#!/usr/bin/env python3
"""Reconcile stranded launch-authorized runtimes before production recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


VERSION = "1.4"
TITLE = "ARCHON Stage E.6.9 Runtime/Dispatch Consistency Recovery"
CONFIRMATION = "RECONCILE_STRANDED_PRODUCTION_RUNTIMES"
MUTATION_ADAPTER_ID = "ARCHON_MUTATION_RULE_FILE_V2"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


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


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def active_authorization(row: Dict[str, Any]) -> bool:
    return (
        row.get("verification_status") == "VERIFIED"
        and row.get("execution_started") is not True
        and row.get("lifecycle_status", "ACTIVE") == "ACTIVE"
        and row.get("superseded") is not True
    )


def current_runtime_contract(
    package: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    runtime = as_dict(package.get("runtime"))
    if not runtime:
        return False, ["RUNTIME_SPEC_MISSING"]
    if canonical_hash(runtime) != package.get("runtime_hash"):
        failures.append("RUNTIME_HASH_MISMATCH")
    if not as_dict(runtime.get("source_target_resolution")):
        failures.append("E3_TARGET_RESOLUTION_MISSING")

    rows = [
        row for row in as_list(runtime.get("run_matrix"))
        if isinstance(row, dict)
    ]
    if not rows:
        failures.append("RUN_MATRIX_EMPTY")
    for row in rows:
        for field in (
            "run_id",
            "role",
            "seed",
            "field_size",
            "topology",
            "boundary_condition",
            "duration_ticks",
            "output_directory",
            "experiment_id",
            "condition_id",
            "rule_id",
        ):
            if row.get(field) in (None, "", []):
                failures.append(f"RUN_MATRIX_FIELD_MISSING:{field}")

    if runtime.get("experiment_type") == "perturbation_recovery_test":
        protocol_source = as_dict(runtime.get("source_protocol_resolution"))
        perturbation = as_dict(runtime.get("perturbation"))
        if not protocol_source:
            failures.append("E4_PROTOCOL_RESOLUTION_MISSING")
        if not text(perturbation.get("protocol_id")):
            failures.append("E4_PROTOCOL_ID_MISSING")
        if not text(perturbation.get("protocol_hash")):
            failures.append("E4_PROTOCOL_HASH_MISSING")
        treatments = [
            row for row in rows
            if str(row.get("role") or "").upper() == "TREATMENT"
        ]
        baselines = [
            row for row in rows
            if str(row.get("role") or "").upper()
            in {"BASELINE", "BASELINE_CONTROL", "CONTROL"}
        ]
        if not baselines:
            failures.append("MATCHED_BASELINE_MISSING")
        if not treatments:
            failures.append("PERTURBATION_TREATMENTS_MISSING")
        for row in treatments:
            arm = as_dict(row.get("perturbation"))
            capability = as_dict(arm.get("execution_capability"))
            if not as_dict(arm.get("arm")):
                failures.append("E4_PROTOCOL_ARM_MISSING")
            if capability.get("required_adapter") != MUTATION_ADAPTER_ID:
                failures.append("E5_MUTATION_ADAPTER_ID_MISMATCH")
            if capability.get("available") is not True:
                failures.append("E5_MUTATION_ADAPTER_UNAVAILABLE")
    return not failures, sorted(set(failures))


def dispatch_runtime_contract(
    *,
    runtime_entry: Dict[str, Any],
    package: Dict[str, Any],
    dispatch: Dict[str, Any],
    job: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Verify that a queued job was built from the current immutable runtime."""
    failures: List[str] = []
    runtime = as_dict(package.get("runtime"))
    immutable = as_dict(job.get("job"))
    runtime_id = text(runtime_entry.get("runtime_id"))
    plan_id = text(runtime_entry.get("plan_id") or runtime.get("plan_id"))
    runtime_hash = text(runtime_entry.get("runtime_hash"))

    if text(dispatch.get("runtime_id")) != runtime_id:
        failures.append("DISPATCH_RUNTIME_ID_MISMATCH")
    if text(immutable.get("runtime_id")) != runtime_id:
        failures.append("JOB_RUNTIME_ID_MISMATCH")
    if text(immutable.get("plan_id")) != plan_id:
        failures.append("JOB_PLAN_ID_MISMATCH")
    if text(immutable.get("runtime_hash")) != runtime_hash:
        failures.append("JOB_RUNTIME_HASH_MISMATCH")
    if runtime_hash != text(package.get("runtime_hash")):
        failures.append("REGISTRY_PACKAGE_RUNTIME_HASH_MISMATCH")

    runtime_rows = {
        text(row.get("run_id")): row
        for row in as_list(runtime.get("run_matrix"))
        if isinstance(row, dict) and text(row.get("run_id"))
    }
    tasks = [
        task
        for task in as_list(immutable.get("tasks"))
        if isinstance(task, dict)
    ]
    if not tasks:
        failures.append("EXECUTION_JOB_TASKS_EMPTY")
    for task in tasks:
        run_id = text(task.get("run_id"))
        task_spec = as_dict(task.get("runtime_spec"))
        expected = runtime_rows.get(run_id)
        if expected is None:
            failures.append(f"JOB_RUN_NOT_IN_CURRENT_RUNTIME:{run_id or 'UNKNOWN'}")
            continue
        if canonical_hash(task_spec) != canonical_hash(expected):
            failures.append(f"JOB_RUNTIME_SPEC_STALE:{run_id}")

    if len(tasks) != len(runtime_rows):
        failures.append("JOB_RUNTIME_TASK_COUNT_MISMATCH")
    return not failures, sorted(set(failures))


def supersede_dispatch(
    row: Dict[str, Any],
    job_path: Path,
    job: Dict[str, Any],
    reasons: List[str],
) -> None:
    """Durably tombstone a pre-execution job without deleting provenance."""
    stamp = now_iso()
    job["status"] = "SUPERSEDED"
    job["updated_at"] = stamp
    job["supersession"] = {
        "superseded_at": stamp,
        "reason": sorted(set(reasons)),
        "replacement_required": True,
        "replacement_scope": "DISPATCH_ONLY",
        "contract": "ARCHON_E6_9",
    }
    atomic_write_json(job_path, job)
    row.update({
        "status": "SUPERSEDED",
        "job_file_hash": canonical_hash(job),
        "superseded_at": stamp,
        "superseded_reason": sorted(set(reasons)),
        "replacement_required": True,
        "replacement_scope": "DISPATCH_ONLY",
    })


def recompute_runtime_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    packages = as_list(registry.get("packages"))
    summary = dict(as_dict(registry.get("summary")))
    summary["launch_authorized_count"] = sum(
        1
        for row in packages
        if isinstance(row, dict)
        and row.get("status") == "LAUNCH_AUTHORIZED"
        and row.get("launch_authorized") is True
    )
    summary["superseded_count"] = sum(
        1
        for row in packages
        if isinstance(row, dict) and row.get("status") == "SUPERSEDED"
    )
    payload = dict(registry)
    payload["generated_at"] = now_iso()
    payload["summary"] = summary
    payload["packages"] = packages
    payload["content_hash"] = canonical_hash({
        "summary": summary,
        "packages": packages,
        "blocked_plans": as_list(registry.get("blocked_plans")),
        "source_registry": as_dict(registry.get("source_registry")),
    })
    return payload


def recompute_authorization_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    rows = as_list(registry.get("authorizations"))
    payload = dict(registry)
    payload["updated_at"] = now_iso()
    payload["authorization_count"] = len(rows)
    payload["active_authorization_count"] = sum(
        1 for row in rows
        if isinstance(row, dict) and active_authorization(row)
    )
    payload["authorizations"] = rows
    payload["content_hash"] = canonical_hash({
        "authorizations": rows,
        "policy": as_dict(registry.get("policy")),
    })
    return payload


def recompute_dispatch_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    rows = as_list(registry.get("jobs"))
    payload = dict(registry)
    payload["updated_at"] = now_iso()
    payload["job_count"] = len(rows)
    payload["queued_count"] = sum(
        1 for row in rows
        if isinstance(row, dict) and row.get("status") == "QUEUED"
    )
    payload["execution_started_count"] = sum(
        1 for row in rows
        if isinstance(row, dict) and row.get("execution_started") is True
    )
    payload["jobs"] = rows
    payload["content_hash"] = canonical_hash({
        "jobs": rows,
        "policy": as_dict(registry.get("policy")),
    })
    return payload


def recompute_worker_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    rows = [
        dict(row)
        for row in as_list(registry.get("claims"))
        if isinstance(row, dict)
    ]
    payload = dict(registry)
    payload["updated_at"] = now_iso()
    payload["claim_count"] = len(rows)
    payload["active_claim_count"] = sum(
        1
        for row in rows
        if row.get("status") in {"CLAIMED", "START_AUTHORIZED"}
        and row.get("released") is False
    )
    payload["start_authorized_count"] = sum(
        1 for row in rows if row.get("status") == "START_AUTHORIZED"
    )
    payload["execution_started_count"] = sum(
        1 for row in rows if row.get("execution_started") is True
    )
    payload["claims"] = rows
    payload["content_hash"] = canonical_hash({
        "claims": rows,
        "policy": as_dict(payload.get("policy")),
    })
    return payload


def recompute_start_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    rows = [
        dict(row)
        for row in as_list(registry.get("authorizations"))
        if isinstance(row, dict)
    ]
    payload = dict(registry)
    payload["updated_at"] = now_iso()
    payload["authorization_count"] = len(rows)
    payload["active_authorization_count"] = sum(
        1 for row in rows if row.get("status") == "START_AUTHORIZED"
    )
    payload["execution_started_count"] = sum(
        1 for row in rows if row.get("execution_started") is True
    )
    payload["authorizations"] = rows
    payload["content_hash"] = canonical_hash({
        "authorizations": rows,
        "policy": as_dict(payload.get("policy")),
    })
    return payload


def recover_start_authorized_handoff(
    *,
    experiments: Path,
    runtime_id: str,
    dispatch_rows: List[Dict[str, Any]],
    worker_registry: Dict[str, Any],
    start_registry: Dict[str, Any],
) -> Tuple[Optional[str], List[str]]:
    candidates = [
        row
        for row in dispatch_rows
        if (
            str(row.get("runtime_id") or "") == runtime_id
            and row.get("status") == "START_AUTHORIZED"
            and row.get("verification_status") == "VERIFIED"
            and row.get("execution_started") is False
            and row.get("observer_invoked") is False
        )
    ]
    if not candidates:
        return None, []
    if len(candidates) != 1:
        return None, ["START_AUTHORIZED_JOB_COUNT_INVALID"]

    dispatch = candidates[0]
    job_id = text(dispatch.get("job_id"))
    claim_id = text(dispatch.get("claim_id"))
    start_id = text(dispatch.get("start_authorization_id"))
    failures: List[str] = []
    if not job_id:
        failures.append("START_AUTHORIZED_JOB_ID_MISSING")
    if not claim_id:
        failures.append("START_AUTHORIZED_CLAIM_ID_MISSING")
    if not start_id:
        failures.append("START_AUTHORIZATION_ID_MISSING")

    claim_rows = [
        row
        for row in as_list(worker_registry.get("claims"))
        if (
            isinstance(row, dict)
            and text(row.get("claim_id")) == claim_id
        )
    ]
    start_rows = [
        row
        for row in as_list(start_registry.get("authorizations"))
        if (
            isinstance(row, dict)
            and text(row.get("start_authorization_id")) == start_id
        )
    ]
    if len(claim_rows) != 1:
        failures.append("WORKER_CLAIM_COUNT_INVALID")
    if len(start_rows) != 1:
        failures.append("START_AUTHORIZATION_COUNT_INVALID")
    claim = claim_rows[0] if len(claim_rows) == 1 else {}
    start = start_rows[0] if len(start_rows) == 1 else {}

    linkage = (
        ("CLAIM_JOB_MISMATCH", claim.get("job_id"), job_id),
        ("CLAIM_RUNTIME_MISMATCH", claim.get("runtime_id"), runtime_id),
        ("CLAIM_STATUS_INVALID", claim.get("status"), "START_AUTHORIZED"),
        ("CLAIM_VERIFICATION_INVALID", claim.get("verification_status"), "VERIFIED"),
        ("CLAIM_RELEASED", claim.get("released"), False),
        ("CLAIM_EXECUTION_STARTED", claim.get("execution_started"), False),
        ("CLAIM_OBSERVER_INVOKED", claim.get("observer_invoked"), False),
        (
            "CLAIM_START_AUTHORIZATION_MISMATCH",
            claim.get("start_authorization_id"),
            start_id,
        ),
        ("START_JOB_MISMATCH", start.get("job_id"), job_id),
        ("START_RUNTIME_MISMATCH", start.get("runtime_id"), runtime_id),
        ("START_CLAIM_MISMATCH", start.get("claim_id"), claim_id),
        ("START_STATUS_INVALID", start.get("status"), "START_AUTHORIZED"),
        (
            "START_VERIFICATION_INVALID",
            start.get("verification_status"),
            "VERIFIED",
        ),
        ("START_EXECUTION_STARTED", start.get("execution_started"), False),
        ("START_OBSERVER_INVOKED", start.get("observer_invoked"), False),
    )
    for reason, actual, expected in linkage:
        if actual != expected:
            failures.append(reason)

    adapter = as_dict(
        load_json(
            experiments / "observer_execution_adapter_registry.json",
            {},
        )
    )
    live = as_dict(
        load_json(
            experiments / "observer_live_execution_registry.json",
            {},
        )
    )
    if any(
        isinstance(row, dict) and text(row.get("job_id")) == job_id
        for row in as_list(adapter.get("manifests"))
    ):
        failures.append("OBSERVER_ADAPTER_ALREADY_PREPARED")
    if any(
        isinstance(row, dict) and text(row.get("job_id")) == job_id
        for row in as_list(live.get("executions"))
    ):
        failures.append("OBSERVER_EXECUTION_ALREADY_RECORDED")

    job_path = Path(str(dispatch.get("job_path") or ""))
    job = as_dict(load_json(job_path, {}))
    if not job:
        failures.append("EXECUTION_JOB_MISSING")
    elif canonical_hash(job) != dispatch.get("job_file_hash"):
        failures.append("EXECUTION_JOB_HASH_MISMATCH")
    if job:
        if job.get("status") != "START_AUTHORIZED":
            failures.append("EXECUTION_JOB_STATUS_INVALID")
        state = as_dict(job.get("execution_state"))
        if state.get("started") is not False:
            failures.append("EXECUTION_JOB_ALREADY_STARTED")
        if state.get("current_task_id") is not None:
            failures.append("EXECUTION_JOB_CURRENT_TASK_ASSIGNED")
        pending = [
            task
            for task in as_list(as_dict(job.get("job")).get("tasks"))
            if (
                isinstance(task, dict)
                and task.get("status") == "PENDING"
                and int(task.get("attempt_count") or 0) == 0
            )
        ]
        if not pending:
            failures.append("EXECUTION_JOB_HAS_NO_PENDING_TASK")
    else:
        pending = []

    if failures:
        return None, sorted(set(failures))

    stamp = now_iso()
    recovery_id = (
        "E68-HANDOFF-"
        + canonical_hash({
            "runtime_id": runtime_id,
            "job_id": job_id,
            "claim_id": claim_id,
            "start_authorization_id": start_id,
        })[:16].upper()
    )

    job["status"] = "QUEUED"
    job["updated_at"] = stamp
    job_claim = as_dict(job.get("worker_claim"))
    if job_claim:
        job_claim.update({
            "status": "RELEASED",
            "released": True,
            "released_at": stamp,
            "release_reason": "E6_8_PRODUCTION_OWNER_HANDOFF",
            "lease_expires_at": None,
        })
        job["worker_claim"] = job_claim
    job_start = as_dict(job.get("start_authorization"))
    if job_start:
        job_start.update({
            "status": "RELEASED_FOR_PRODUCTION_HANDOFF",
            "released_at": stamp,
            "release_reason": "E6_8_PRODUCTION_OWNER_HANDOFF",
        })
        job["start_authorization"] = job_start
    job_policy = as_dict(job.get("policy"))
    job_policy.update({
        "worker_claimed": False,
        "start_authorized": False,
        "execution_started": False,
        "observer_invoked": False,
    })
    job["policy"] = job_policy
    job["production_handoff_recovery"] = {
        "recovery_id": recovery_id,
        "released_claim_id": claim_id,
        "released_start_authorization_id": start_id,
        "recovered_at": stamp,
        "execution_started": False,
        "observer_invoked": False,
    }
    atomic_write_json(job_path, job)
    job_file_hash = canonical_hash(job)

    dispatch.update({
        "status": "QUEUED",
        "job_file_hash": job_file_hash,
        "completed_tasks": sum(
            task.get("status") == "COMPLETED"
            for task in as_list(as_dict(job.get("job")).get("tasks"))
            if isinstance(task, dict)
        ),
        "failed_tasks": sum(
            task.get("status") == "FAILED"
            for task in as_list(as_dict(job.get("job")).get("tasks"))
            if isinstance(task, dict)
        ),
        "pending_tasks": len(pending),
        "current_task_id": None,
        "claim_id": None,
        "worker_id": None,
        "lease_expires_at": None,
        "start_authorization_id": None,
        "start_authorization_hash": None,
        "updated_at": stamp,
        "recovery_id": recovery_id,
    })
    claim.update({
        "status": "RELEASED",
        "released": True,
        "released_at": stamp,
        "release_reason": "E6_8_PRODUCTION_OWNER_HANDOFF",
        "lease_expires_at": None,
        "job_file_hash": job_file_hash,
        "updated_at": stamp,
        "recovery_id": recovery_id,
    })
    start.update({
        "status": "RELEASED_FOR_PRODUCTION_HANDOFF",
        "released_at": stamp,
        "release_reason": "E6_8_PRODUCTION_OWNER_HANDOFF",
        "job_file_hash": job_file_hash,
        "updated_at": stamp,
        "recovery_id": recovery_id,
    })
    return recovery_id, []


def reconcile(
    experiments: Path,
    selected_plan_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    runtime_path = experiments / "experiment_runtime_registry.json"
    authorization_path = experiments / "launch_authorization_registry.json"
    dispatch_path = experiments / "execution_dispatch_registry.json"
    worker_path = experiments / "execution_worker_registry.json"
    start_path = (
        experiments / "execution_start_authorization_registry.json"
    )
    recovery_intent_path = (
        experiments / "production_runtime_recovery_intent.json"
    )
    runtime_registry = as_dict(load_json(runtime_path, {}))
    authorization_registry = as_dict(load_json(authorization_path, {}))
    dispatch_registry = as_dict(load_json(dispatch_path, {}))
    worker_registry = as_dict(load_json(worker_path, {}))
    start_registry = as_dict(load_json(start_path, {}))
    recovery_intent = as_dict(load_json(recovery_intent_path, {}))
    selected = {
        str(item).strip()
        for item in (selected_plan_ids or [])
        if str(item).strip()
    }

    runtime_rows = [
        dict(row) for row in as_list(runtime_registry.get("packages"))
        if isinstance(row, dict)
    ]
    authorization_rows = [
        dict(row)
        for row in as_list(authorization_registry.get("authorizations"))
        if isinstance(row, dict)
    ]
    dispatch_rows = [
        dict(row) for row in as_list(dispatch_registry.get("jobs"))
        if isinstance(row, dict)
    ]
    runtime_by_id = {
        str(row.get("runtime_id")): row
        for row in runtime_rows if row.get("runtime_id")
    }
    active_by_runtime = {
        str(row.get("runtime_id")): row
        for row in authorization_rows
        if row.get("runtime_id")
        and active_authorization(row)
        and (
            not selected
            or text(runtime_by_id.get(
                str(row.get("runtime_id")), {}
            ).get("plan_id")) in selected
        )
    }
    pending_plan_ids = {
        str(item).strip()
        for item in as_list(recovery_intent.get("pending_plan_ids"))
        if str(item).strip()
    }
    recovery_source_runtime_ids = {
        str(item).strip()
        for item in as_list(recovery_intent.get("source_runtime_ids"))
        if str(item).strip()
    }
    deferred_plan_ids: set[str] = set()

    # E.6.1 committed SUPERSEDED before downstream rematerialization.  Treat
    # those durable tombstones as retryable recovery intents so an interrupted
    # or refused resolver cannot make an authorized plan disappear forever.
    for row in runtime_rows:
        if row.get("status") != "SUPERSEDED":
            continue
        package_path = Path(str(row.get("package_path") or ""))
        package = as_dict(load_json(package_path, {}))
        supersession = as_dict(package.get("supersession"))
        if supersession.get("replacement_required") is not True:
            continue
        plan_id = text(
            row.get("plan_id")
            or as_dict(package.get("runtime")).get("plan_id")
        )
        runtime_id = text(row.get("runtime_id"))
        if plan_id:
            pending_plan_ids.add(plan_id)
        if runtime_id:
            recovery_source_runtime_ids.add(runtime_id)

    if selected:
        available_plan_ids = set(pending_plan_ids)
        available_plan_ids.update(
            text(runtime_by_id.get(runtime_id, {}).get("plan_id"))
            for runtime_id in active_by_runtime
        )
        available_plan_ids.discard(None)
        missing = sorted(selected - available_plan_ids)
        if missing:
            return {
                "schema": "archon_production_runtime_recovery_result_v1",
                "version": VERSION,
                "status": "REFUSED",
                "mode": "SELECTED_PLAN_NOT_RECOVERABLE",
                "recoverable_plan_ids": sorted(available_plan_ids),
                "selected_plan_ids": sorted(selected),
                "reasons": [
                    "SELECTED_PLAN_NOT_RECOVERABLE:" + ",".join(missing)
                ],
                "reconciled_at": now_iso(),
            }
        deferred_plan_ids = pending_plan_ids - selected
        pending_plan_ids.intersection_update(selected)

    current: List[str] = []
    stale: Dict[str, List[str]] = {}
    for runtime_id, authorization in active_by_runtime.items():
        runtime_entry = runtime_by_id.get(runtime_id)
        if runtime_entry is None:
            stale[runtime_id] = ["RUNTIME_REGISTRY_ENTRY_MISSING"]
            continue
        package_path = Path(str(runtime_entry.get("package_path") or ""))
        package = as_dict(load_json(package_path, {}))
        failures: List[str] = []
        if not package:
            failures.append("RUNTIME_PACKAGE_MISSING")
        else:
            valid, contract_failures = current_runtime_contract(package)
            if not valid:
                failures.extend(contract_failures)
            launch = as_dict(package.get("launch_authorization"))
            if launch.get("authorization_id") != authorization.get(
                "authorization_id"
            ):
                failures.append("AUTHORIZATION_ID_MISMATCH")
        if (
            runtime_entry.get("status") != "LAUNCH_AUTHORIZED"
            or runtime_entry.get("launch_authorized") is not True
        ):
            failures.append("RUNTIME_NOT_LAUNCH_AUTHORIZED")
        if failures:
            stale[runtime_id] = sorted(set(failures))
        else:
            current.append(runtime_id)

    current_plans = {
        text(runtime_by_id[runtime_id].get("plan_id"))
        for runtime_id in current
        if runtime_id in runtime_by_id
    }
    if len(current) > 1 and len(current_plans) > 1:
        return {
            "schema": "archon_production_runtime_recovery_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "mode": "AMBIGUOUS_ACTIVE_RUNTIMES",
            "current_runtime_ids": sorted(current),
            "stale_runtimes": stale,
            "recoverable_plan_ids": sorted(pending_plan_ids),
            "reasons": ["MULTIPLE_CURRENT_PLANS_REQUIRE_HUMAN_RESOLUTION"],
            "reconciled_at": now_iso(),
        }

    # Multiple authorizations for one deterministic plan are historical
    # duplicates. Keep the newest verified authorization only.
    if len(current) > 1:
        current.sort(
            key=lambda runtime_id: str(
                active_by_runtime[runtime_id].get("authorized_at") or ""
            )
        )
        for runtime_id in current[:-1]:
            stale[runtime_id] = ["SUPERSEDED_BY_NEWER_AUTHORIZATION"]
        current = current[-1:]

    active_dispatch_failures: List[str] = []
    superseded_dispatch_ids: List[str] = []
    for row in dispatch_rows:
        runtime_id = str(row.get("runtime_id") or "")
        if (
            runtime_id not in current
            or row.get("status") not in {"QUEUED", "PARTIALLY_COMPLETED"}
            or row.get("execution_started") is True
        ):
            continue
        job_path = Path(str(row.get("job_path") or ""))
        job = as_dict(load_json(job_path, {}))
        if not job:
            active_dispatch_failures.append(
                f"EXECUTION_JOB_MISSING:{row.get('job_id')}"
            )
            continue
        if canonical_hash(job) != row.get("job_file_hash"):
            active_dispatch_failures.append(
                f"EXECUTION_JOB_HASH_MISMATCH:{row.get('job_id')}"
            )
            continue
        runtime_entry = runtime_by_id.get(runtime_id, {})
        package = as_dict(
            load_json(Path(str(runtime_entry.get("package_path") or "")), {})
        )
        linked, linkage_failures = dispatch_runtime_contract(
            runtime_entry=runtime_entry,
            package=package,
            dispatch=row,
            job=job,
        )
        if not linked:
            # The runtime itself is current, but this queued job was generated
            # from an older materialization that reused the deterministic
            # runtime_id.  It is safe to supersede only the unstarted dispatch
            # and let Stage 6 create a fresh job from the current package.
            supersede_dispatch(row, job_path, job, linkage_failures)
            if row.get("job_id"):
                superseded_dispatch_ids.append(str(row.get("job_id")))
            continue
        tasks = [
            task
            for task in as_list(as_dict(job.get("job")).get("tasks"))
            if isinstance(task, dict)
        ]
        state = as_dict(job.get("execution_state"))
        row["completed_tasks"] = sum(
            1 for task in tasks if task.get("status") == "COMPLETED"
        )
        row["failed_tasks"] = sum(
            1 for task in tasks if task.get("status") == "FAILED"
        )
        row["pending_tasks"] = sum(
            1 for task in tasks if task.get("status") == "PENDING"
        )
        row["current_task_id"] = state.get("current_task_id")
        row.setdefault("claim_id", None)

    if active_dispatch_failures:
        return {
            "schema": "archon_production_runtime_recovery_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "mode": "ACTIVE_DISPATCH_INVALID",
            "current_runtime_ids": sorted(current),
            "stale_runtimes": stale,
            "reasons": sorted(set(active_dispatch_failures)),
            "reconciled_at": now_iso(),
        }

    recovered_start_job_id: Optional[str] = None
    start_handoff_recovery_id: Optional[str] = None
    if len(current) == 1:
        start_handoff_recovery_id, handoff_failures = (
            recover_start_authorized_handoff(
                experiments=experiments,
                runtime_id=current[0],
                dispatch_rows=dispatch_rows,
                worker_registry=worker_registry,
                start_registry=start_registry,
            )
        )
        if handoff_failures:
            return {
                "schema": "archon_production_runtime_recovery_result_v1",
                "version": VERSION,
                "status": "REFUSED",
                "mode": "START_AUTHORIZED_HANDOFF_INVALID",
                "current_runtime_ids": sorted(current),
                "stale_runtimes": stale,
                "reasons": handoff_failures,
                "reconciled_at": now_iso(),
            }
        if start_handoff_recovery_id:
            recovered = [
                row for row in dispatch_rows
                if row.get("recovery_id") == start_handoff_recovery_id
            ]
            recovered_start_job_id = (
                str(recovered[0].get("job_id"))
                if len(recovered) == 1
                else None
            )

    stamp = now_iso()
    for runtime_id in stale:
        entry = runtime_by_id.get(runtime_id)
        if entry is None:
            continue
        plan_id = text(entry.get("plan_id"))
        if plan_id:
            pending_plan_ids.add(plan_id)
        recovery_source_runtime_ids.add(runtime_id)

    for runtime_id, reasons in stale.items():
        entry = runtime_by_id.get(runtime_id)
        if entry is not None:
            entry["status"] = "SUPERSEDED"
            entry["launch_authorized"] = False
            entry["superseded_at"] = stamp
            entry["superseded_reason"] = reasons
            package_path = Path(str(entry.get("package_path") or ""))
            package = as_dict(load_json(package_path, {}))
            if package:
                package["status"] = "SUPERSEDED"
                package["updated_at"] = stamp
                package["supersession"] = {
                    "superseded_at": stamp,
                    "reason": reasons,
                    "replacement_required": True,
                    "contract": "ARCHON_E6_1",
                }
                as_dict(package.get("policy"))["launch_authorized"] = False
                atomic_write_json(package_path, package)
        for row in authorization_rows:
            if str(row.get("runtime_id") or "") == runtime_id:
                row["lifecycle_status"] = "SUPERSEDED"
                row["superseded"] = True
                row["superseded_at"] = stamp
                row["superseded_reason"] = reasons
        for row in dispatch_rows:
            if (
                str(row.get("runtime_id") or "") == runtime_id
                and row.get("execution_started") is not True
                and row.get("observer_invoked") is not True
                and row.get("status")
                in {"QUEUED", "PARTIALLY_COMPLETED", "PENDING"}
            ):
                row["status"] = "SUPERSEDED"
                row["superseded_at"] = stamp
                row["superseded_reason"] = reasons

    runtime_registry["packages"] = runtime_rows
    authorization_registry["authorizations"] = authorization_rows
    dispatch_registry["jobs"] = dispatch_rows
    runtime_registry = recompute_runtime_registry(runtime_registry)
    authorization_registry = recompute_authorization_registry(
        authorization_registry
    )
    dispatch_registry = recompute_dispatch_registry(dispatch_registry)
    if worker_registry:
        worker_registry = recompute_worker_registry(worker_registry)
    if start_registry:
        start_registry = recompute_start_registry(start_registry)
    atomic_write_json(runtime_path, runtime_registry)
    atomic_write_json(authorization_path, authorization_registry)
    atomic_write_json(dispatch_path, dispatch_registry)
    if worker_registry:
        atomic_write_json(worker_path, worker_registry)
    if start_registry:
        atomic_write_json(start_path, start_registry)

    active_runtime = current[0] if current else None
    active_plan_ids = {
        plan_id
        for runtime_id in current
        for plan_id in [text(runtime_by_id.get(runtime_id, {}).get("plan_id"))]
        if plan_id
    }

    # A current authorized replacement, including one that has already begun
    # execution, completes the rematerialization phase for its source plan.
    replacement_plan_ids = set(active_plan_ids)
    for row in authorization_rows:
        runtime_id = str(row.get("runtime_id") or "")
        if row.get("execution_started") is not True:
            continue
        runtime_entry = runtime_by_id.get(runtime_id)
        if runtime_entry is None:
            continue
        package = as_dict(
            load_json(Path(str(runtime_entry.get("package_path") or "")), {})
        )
        valid, _ = current_runtime_contract(package)
        if not valid:
            continue
        plan_id = text(runtime_entry.get("plan_id"))
        if plan_id:
            replacement_plan_ids.add(plan_id)
    pending_plan_ids.difference_update(replacement_plan_ids)

    durable_pending_plan_ids = pending_plan_ids | deferred_plan_ids
    intent_status = "PENDING" if durable_pending_plan_ids else (
        "COMPLETED" if recovery_source_runtime_ids else "EMPTY"
    )
    recovery_intent = {
        "schema": "archon_production_runtime_recovery_intent_v1",
        "version": VERSION,
        "status": intent_status,
        "pending_plan_ids": sorted(durable_pending_plan_ids),
        "replacement_plan_ids": sorted(replacement_plan_ids),
        "source_runtime_ids": sorted(recovery_source_runtime_ids),
        "updated_at": stamp,
        "policy": {
            "supersession_is_retryable_until_replacement": True,
            "resolver_scope_is_recoverable_plans_only": True,
            "multi_rule_parent_groups_supported": True,
            "explicit_plan_selection_supported": True,
        },
    }
    recovery_intent["content_hash"] = canonical_hash({
        "status": recovery_intent["status"],
        "pending_plan_ids": recovery_intent["pending_plan_ids"],
        "replacement_plan_ids": recovery_intent["replacement_plan_ids"],
        "source_runtime_ids": recovery_intent["source_runtime_ids"],
        "policy": recovery_intent["policy"],
    })
    atomic_write_json(recovery_intent_path, recovery_intent)

    active_jobs = [
        row
        for row in dispatch_rows
        if active_runtime
        and str(row.get("runtime_id") or "") == active_runtime
        and row.get("status") in {"QUEUED", "PARTIALLY_COMPLETED"}
        and row.get("execution_started") is not True
        and int(row.get("pending_tasks") or 0) > 0
    ]
    runtime_jobs = [
        row
        for row in dispatch_rows
        if active_runtime
        and str(row.get("runtime_id") or "") == active_runtime
        and row.get("status") != "SUPERSEDED"
    ]
    if len(active_jobs) > 1:
        status = "REFUSED"
        mode = "AMBIGUOUS_ACTIVE_DISPATCH"
        reasons = ["MULTIPLE_ACTIVE_JOBS_FOR_RUNTIME"]
    elif len(active_jobs) == 1:
        status = "READY"
        mode = "READY_TO_HANDOFF"
        reasons = []
    elif active_runtime:
        if runtime_jobs:
            status = "NO_RECOVERABLE_RUNTIME"
            mode = "ALREADY_DISPATCHED_TERMINAL"
        else:
            status = "READY"
            mode = "NEEDS_DISPATCH"
        reasons = []
    elif pending_plan_ids:
        status = "READY"
        mode = "NEEDS_REMATERIALIZATION"
        reasons = []
    else:
        status = "NO_RECOVERABLE_RUNTIME"
        mode = "NO_RECOVERABLE_RUNTIME"
        reasons = []

    return {
        "schema": "archon_production_runtime_recovery_result_v1",
        "version": VERSION,
        "status": status,
        "mode": mode,
        "runtime_id": active_runtime,
        "job_id": (
            active_jobs[0].get("job_id")
            if len(active_jobs) == 1
            else recovered_start_job_id
        ),
        "start_handoff_recovery_id": start_handoff_recovery_id,
        "superseded_count": len(stale),
        "superseded_dispatch_count": len(superseded_dispatch_ids),
        "superseded_dispatch_ids": sorted(superseded_dispatch_ids),
        "stale_runtimes": stale,
        "recoverable_plan_ids": sorted(pending_plan_ids),
        "selected_plan_ids": sorted(selected),
        "recovery_intent_path": str(recovery_intent_path),
        "recovery_intent_hash": recovery_intent.get("content_hash"),
        "reasons": reasons,
        "reconciled_at": stamp,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument(
        "--plan-id",
        action="append",
        default=[],
        help="Recover only this committed plan (repeatable).",
    )
    args = parser.parse_args()
    analysis = Path(args.analysis_root).expanduser().resolve()
    experiments = analysis / "Experiments"
    result_path = experiments / "production_runtime_recovery_result.json"
    if args.confirmation != CONFIRMATION:
        result = {
            "schema": "archon_production_runtime_recovery_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "mode": "CONFIRMATION_INVALID",
            "reasons": ["CONFIRMATION_INVALID"],
            "reconciled_at": now_iso(),
        }
    else:
        result = reconcile(experiments, args.plan_id)
    atomic_write_json(result_path, result)
    print(f"Status: {result.get('status')}")
    print(f"Mode:   {result.get('mode')}")
    print(f"Superseded: {result.get('superseded_count', 0)}")
    plans = as_list(result.get("recoverable_plan_ids"))
    print(
        "Recoverable plans: "
        + (", ".join(str(item) for item in plans) if plans else "-")
    )
    return 1 if result.get("status") == "REFUSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
