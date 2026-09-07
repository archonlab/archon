#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VERSION = "1.0"
TITLE = "ARCHON Stage 6.6 Execution Dispatch Gateway"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def normalize_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def build_request_template(
    runtime_registry: Dict[str, Any],
    authorization_registry: Dict[str, Any],
    existing_request: Dict[str, Any],
) -> Dict[str, Any]:
    auth_by_runtime = {
        str(item.get("runtime_id")): item
        for item in as_list(authorization_registry.get("authorizations"))
        if (
            isinstance(item, dict)
            and item.get("runtime_id")
            and item.get("lifecycle_status", "ACTIVE") == "ACTIVE"
            and item.get("superseded") is not True
        )
    }
    eligible = []
    for item in as_list(runtime_registry.get("packages")):
        if not isinstance(item, dict):
            continue
        runtime_id = str(item.get("runtime_id") or "")
        if (
            item.get("status") == "LAUNCH_AUTHORIZED"
            and item.get("launch_authorized") is True
            and runtime_id in auth_by_runtime
            and auth_by_runtime[runtime_id].get("verification_status")
            == "VERIFIED"
        ):
            eligible.append((item, auth_by_runtime[runtime_id]))

    selected = eligible[0] if len(eligible) == 1 else None
    runtime = selected[0] if selected else None
    authorization = selected[1] if selected else None

    return {
        "schema": "archon_execution_dispatch_request_v1",
        "dispatch": False,
        "dispatch_id": None,
        "runtime_id": runtime.get("runtime_id") if runtime else None,
        "authorization_id": (
            authorization.get("authorization_id")
            if authorization else None
        ),
        "expected_runtime_hash": (
            runtime.get("runtime_hash") if runtime else None
        ),
        "expected_runtime_registry_hash": runtime_registry.get("content_hash"),
        "expected_authorization_registry_hash": (
            authorization_registry.get("content_hash")
        ),
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_dispatch_id": existing_request.get(
            "last_consumed_dispatch_id"
        ),
        "instructions": {
            "required_confirmation": "QUEUE_EXPERIMENT_EXECUTION",
            "verified_launch_authorization_required": True,
            "dispatch_creates_queue_entry_only": True,
            "observer_launches_immediately": False,
            "manual_request_required": True,
            "inactive_template_auto_refresh": True,
        },
    }


def verify_authorized_runtime(
    runtime_entry: Dict[str, Any],
    authorization_entry: Dict[str, Any],
) -> tuple[Dict[str, Any], List[str]]:
    failures: List[str] = []
    package_path = Path(str(runtime_entry.get("package_path") or ""))
    package = load_json(package_path, {})

    if not package:
        return {}, ["RUNTIME_PACKAGE_MISSING_OR_INVALID"]

    if runtime_entry.get("status") != "LAUNCH_AUTHORIZED":
        failures.append("RUNTIME_REGISTRY_STATUS_INVALID")
    if runtime_entry.get("launch_authorized") is not True:
        failures.append("RUNTIME_REGISTRY_NOT_AUTHORIZED")
    if authorization_entry.get("verification_status") != "VERIFIED":
        failures.append("AUTHORIZATION_NOT_VERIFIED")
    if authorization_entry.get("execution_started") is not False:
        failures.append("AUTHORIZATION_ALREADY_EXECUTED")

    if package.get("status") != "LAUNCH_AUTHORIZED":
        failures.append("PACKAGE_STATUS_INVALID")
    launch = as_dict(package.get("launch_authorization"))
    if launch.get("authorized") is not True:
        failures.append("PACKAGE_NOT_AUTHORIZED")
    if launch.get("authorization_id") != authorization_entry.get(
        "authorization_id"
    ):
        failures.append("AUTHORIZATION_ID_MISMATCH")

    runtime = as_dict(package.get("runtime"))
    if canonical_hash(runtime) != package.get("runtime_hash"):
        failures.append("RUNTIME_HASH_MISMATCH")
    if package.get("runtime_hash") != runtime_entry.get("runtime_hash"):
        failures.append("REGISTRY_RUNTIME_HASH_MISMATCH")
    if canonical_hash(package) != authorization_entry.get("package_hash"):
        failures.append("AUTHORIZED_PACKAGE_HASH_MISMATCH")
    if not as_list(runtime.get("run_matrix")):
        failures.append("RUN_MATRIX_EMPTY")

    return package, sorted(set(failures))


def build_execution_job(
    dispatch_id: str,
    runtime_entry: Dict[str, Any],
    authorization_entry: Dict[str, Any],
    package: Dict[str, Any],
    requested_by: str,
) -> Dict[str, Any]:
    runtime = as_dict(package.get("runtime"))
    run_matrix = as_list(runtime.get("run_matrix"))
    job_id = (
        f"EXEC-JOB-"
        f"{canonical_hash({'dispatch_id': dispatch_id, 'runtime_id': runtime_entry.get('runtime_id')})[:16].upper()}"
    )

    tasks = []
    for order, row in enumerate(run_matrix, start=1):
        tasks.append({
            "task_id": f"{job_id}-T{order:03d}",
            "order": order,
            "run_id": row.get("run_id"),
            "role": row.get("role"),
            "status": "PENDING",
            "attempt_count": 0,
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "error": None,
            "runtime_spec": row,
        })

    immutable = {
        "job_id": job_id,
        "dispatch_id": dispatch_id,
        "runtime_id": runtime_entry.get("runtime_id"),
        "runtime_hash": runtime_entry.get("runtime_hash"),
        "authorization_id": authorization_entry.get("authorization_id"),
        "authorization_hash": authorization_entry.get("authorization_hash"),
        "plan_id": runtime.get("plan_id"),
        "commit_id": runtime.get("commit_id"),
        "draft_id": runtime.get("draft_id"),
        "intake_id": runtime.get("intake_id"),
        "queued_at": now_iso(),
        "queued_by": requested_by,
        "execution_mode": "QUEUE_ONLY",
        "tasks": tasks,
        "output_layout": as_dict(runtime.get("output_layout")),
        "resource_profile": as_dict(runtime.get("resource_profile")),
        "evidence_contract": as_dict(runtime.get("evidence_contract")),
        "provenance": {
            "runtime_package_path": runtime_entry.get("package_path"),
            "authorization_receipt_path": authorization_entry.get(
                "receipt_path"
            ),
            "source_plan_id": runtime.get("plan_id"),
            "source_commit_id": runtime.get("commit_id"),
        },
    }
    job_hash = canonical_hash(immutable)

    return {
        "schema": "archon_execution_job_v1",
        "version": VERSION,
        "job_id": job_id,
        "status": "QUEUED",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "job_hash": job_hash,
        "job": immutable,
        "execution_state": {
            "started": False,
            "started_at": None,
            "finished": False,
            "finished_at": None,
            "current_task_id": None,
            "completed_tasks": 0,
            "failed_tasks": 0,
        },
        "cancellation": {
            "requested": False,
            "requested_at": None,
            "requested_by": None,
            "reason": None,
        },
        "policy": {
            "queue_entry_only": True,
            "observer_invoked": False,
            "execution_started": False,
            "separate_worker_required": True,
            "job_definition_immutable": True,
            "cancellation_allowed_before_start": True,
        },
    }


def dispatch_execution(
    experiments_root: Path,
    runtime_registry: Dict[str, Any],
    authorization_registry: Dict[str, Any],
    dispatch_registry: Dict[str, Any],
    request: Dict[str, Any],
) -> Dict[str, Any]:
    if request.get("dispatch") is not True:
        return {
            "schema": "archon_execution_dispatch_result_v1",
            "status": "NO_DISPATCH_REQUEST",
            "dispatched": False,
            "reason": None,
        }

    dispatch_id = normalize_text(request.get("dispatch_id"))
    runtime_id = normalize_text(request.get("runtime_id"))
    authorization_id = normalize_text(request.get("authorization_id"))
    requested_by = normalize_text(request.get("requested_by"))
    confirmation = normalize_text(request.get("confirmation"))

    failures: List[str] = []
    if not dispatch_id:
        failures.append("DISPATCH_ID_MISSING")
    if not runtime_id:
        failures.append("RUNTIME_ID_MISSING")
    if not authorization_id:
        failures.append("AUTHORIZATION_ID_MISSING")
    if not requested_by:
        failures.append("REQUESTED_BY_MISSING")
    if confirmation != "QUEUE_EXPERIMENT_EXECUTION":
        failures.append("CONFIRMATION_INVALID")

    if request.get("expected_runtime_registry_hash") != runtime_registry.get(
        "content_hash"
    ):
        failures.append("RUNTIME_REGISTRY_HASH_MISMATCH")
    if request.get(
        "expected_authorization_registry_hash"
    ) != authorization_registry.get("content_hash"):
        failures.append("AUTHORIZATION_REGISTRY_HASH_MISMATCH")

    runtime_entries = {
        str(item.get("runtime_id")): item
        for item in as_list(runtime_registry.get("packages"))
        if isinstance(item, dict) and item.get("runtime_id")
    }
    authorization_entries = {
        str(item.get("authorization_id")): item
        for item in as_list(authorization_registry.get("authorizations"))
        if isinstance(item, dict) and item.get("authorization_id")
    }

    runtime_entry = runtime_entries.get(runtime_id or "")
    authorization_entry = authorization_entries.get(authorization_id or "")
    package: Dict[str, Any] = {}

    if runtime_entry is None:
        failures.append("RUNTIME_NOT_FOUND")
    else:
        if request.get("expected_runtime_hash") != runtime_entry.get(
            "runtime_hash"
        ):
            failures.append("EXPECTED_RUNTIME_HASH_MISMATCH")

    if authorization_entry is None:
        failures.append("AUTHORIZATION_NOT_FOUND")
    elif authorization_entry.get("runtime_id") != runtime_id:
        failures.append("AUTHORIZATION_RUNTIME_MISMATCH")

    if runtime_entry is not None and authorization_entry is not None:
        package, verify_failures = verify_authorized_runtime(
            runtime_entry,
            authorization_entry,
        )
        failures.extend(verify_failures)

    existing_dispatches = {
        str(item.get("dispatch_id")): item
        for item in as_list(dispatch_registry.get("jobs"))
        if isinstance(item, dict) and item.get("dispatch_id")
    }
    existing_by_runtime = {
        str(item.get("runtime_id")): item
        for item in as_list(dispatch_registry.get("jobs"))
        if (
            isinstance(item, dict)
            and item.get("runtime_id")
            and item.get("status") != "SUPERSEDED"
        )
    }
    if dispatch_id and dispatch_id in existing_dispatches:
        failures.append("DISPATCH_ID_REPLAY")
    if runtime_id and runtime_id in existing_by_runtime:
        failures.append("RUNTIME_ALREADY_DISPATCHED")

    if failures:
        return {
            "schema": "archon_execution_dispatch_result_v1",
            "status": "REFUSED",
            "dispatched": False,
            "dispatch_id": dispatch_id,
            "runtime_id": runtime_id,
            "authorization_id": authorization_id,
            "reasons": sorted(set(failures)),
        }

    assert runtime_entry is not None
    assert authorization_entry is not None

    execution_job = build_execution_job(
        dispatch_id,
        runtime_entry,
        authorization_entry,
        package,
        requested_by,
    )
    jobs_root = experiments_root / "ExecutionJobs"
    job_path = jobs_root / f"{execution_job['job_id']}.json"
    if job_path.exists():
        return {
            "schema": "archon_execution_dispatch_result_v1",
            "status": "REFUSED",
            "dispatched": False,
            "dispatch_id": dispatch_id,
            "runtime_id": runtime_id,
            "authorization_id": authorization_id,
            "reasons": ["EXECUTION_JOB_ALREADY_EXISTS"],
        }

    atomic_write_json(job_path, execution_job)

    receipt = {
        "schema": "archon_execution_dispatch_receipt_v1",
        "status": "QUEUED",
        "dispatch_id": dispatch_id,
        "job_id": execution_job["job_id"],
        "job_hash": execution_job["job_hash"],
        "job_file_hash": canonical_hash(execution_job),
        "job_path": str(job_path),
        "runtime_id": runtime_id,
        "runtime_hash": runtime_entry.get("runtime_hash"),
        "authorization_id": authorization_id,
        "queued_at": execution_job["job"]["queued_at"],
        "queued_by": requested_by,
        "execution_started": False,
        "observer_invoked": False,
    }
    receipt_path = (
        experiments_root
        / "ExecutionDispatchReceipts"
        / f"{dispatch_id}.json"
    )
    atomic_write_json(receipt_path, receipt)

    return {
        "schema": "archon_execution_dispatch_result_v1",
        "status": "QUEUED",
        "dispatched": True,
        "dispatch_id": dispatch_id,
        "job_id": execution_job["job_id"],
        "job_hash": execution_job["job_hash"],
        "job_file_hash": receipt["job_file_hash"],
        "job_path": str(job_path),
        "receipt_path": str(receipt_path),
        "runtime_id": runtime_id,
        "authorization_id": authorization_id,
        "execution_started": False,
        "observer_invoked": False,
    }


def verify_receipt(result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("status") != "QUEUED":
        return {
            "schema": "archon_execution_dispatch_receipt_verification_v1",
            "status": "NO_DISPATCH",
            "verified": False,
        }

    job_path = Path(str(result.get("job_path")))
    receipt_path = Path(str(result.get("receipt_path")))
    job = load_json(job_path, {})
    receipt = load_json(receipt_path, {})
    failures: List[str] = []

    if not job:
        failures.append("JOB_MISSING_OR_INVALID")
    if not receipt:
        failures.append("RECEIPT_MISSING_OR_INVALID")

    if job:
        if canonical_hash(job) != result.get("job_file_hash"):
            failures.append("JOB_FILE_HASH_MISMATCH")
        if canonical_hash(as_dict(job.get("job"))) != job.get("job_hash"):
            failures.append("JOB_CONTENT_HASH_MISMATCH")
        if job.get("job_hash") != result.get("job_hash"):
            failures.append("JOB_HASH_MISMATCH")
        if job.get("status") != "QUEUED":
            failures.append("JOB_STATUS_INVALID")
        if as_dict(job.get("execution_state")).get("started") is not False:
            failures.append("JOB_EXECUTION_STATE_INVALID")
        if as_dict(job.get("policy")).get("observer_invoked") is not False:
            failures.append("JOB_OBSERVER_STATE_INVALID")

    if receipt:
        if receipt.get("dispatch_id") != result.get("dispatch_id"):
            failures.append("RECEIPT_DISPATCH_ID_MISMATCH")
        if receipt.get("job_id") != result.get("job_id"):
            failures.append("RECEIPT_JOB_ID_MISMATCH")
        if receipt.get("job_hash") != result.get("job_hash"):
            failures.append("RECEIPT_JOB_HASH_MISMATCH")
        if receipt.get("execution_started") is not False:
            failures.append("RECEIPT_EXECUTION_STATE_INVALID")
        if receipt.get("observer_invoked") is not False:
            failures.append("RECEIPT_OBSERVER_STATE_INVALID")

    return {
        "schema": "archon_execution_dispatch_receipt_verification_v1",
        "status": "VERIFIED" if not failures else "FAILED",
        "verified": not failures,
        "failures": failures,
        "dispatch_id": result.get("dispatch_id"),
        "job_id": result.get("job_id"),
        "runtime_id": result.get("runtime_id"),
        "authorization_id": result.get("authorization_id"),
        "job_hash": result.get("job_hash"),
        "job_file_hash": result.get("job_file_hash"),
    }


def update_dispatch_registry(
    existing: Dict[str, Any],
    result: Dict[str, Any],
    verification: Dict[str, Any],
) -> Dict[str, Any]:
    rows = [
        item
        for item in as_list(existing.get("jobs"))
        if isinstance(item, dict)
    ]

    if result.get("status") == "QUEUED":
        execution_job = load_json(Path(str(result.get("job_path") or "")), {})
        tasks = as_list(as_dict(execution_job.get("job")).get("tasks"))
        rows.append({
            "dispatch_id": result.get("dispatch_id"),
            "job_id": result.get("job_id"),
            "job_hash": result.get("job_hash"),
            "job_file_hash": result.get("job_file_hash"),
            "job_path": result.get("job_path"),
            "receipt_path": result.get("receipt_path"),
            "runtime_id": result.get("runtime_id"),
            "authorization_id": result.get("authorization_id"),
            "status": "QUEUED",
            "verification_status": verification.get("status"),
            "execution_started": False,
            "observer_invoked": False,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "pending_tasks": len(tasks),
            "current_task_id": None,
            "claim_id": None,
            "queued_at": now_iso(),
        })

    unique: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        dispatch_id = str(item.get("dispatch_id") or "")
        if dispatch_id:
            unique[dispatch_id] = item

    ordered = sorted(unique.values(), key=lambda x: str(x.get("dispatch_id")))
    payload = {
        "schema": "archon_execution_dispatch_registry_v1",
        "version": VERSION,
        "updated_at": now_iso(),
        "job_count": len(ordered),
        "queued_count": sum(
            1 for item in ordered if item.get("status") == "QUEUED"
        ),
        "execution_started_count": sum(
            1 for item in ordered if item.get("execution_started") is True
        ),
        "jobs": ordered,
        "policy": {
            "dispatch_is_queue_only": True,
            "observer_invoked": False,
            "separate_worker_stage_required": True,
        },
    }
    payload["content_hash"] = canonical_hash({
        "jobs": ordered,
        "policy": payload["policy"],
    })
    return payload


def render_markdown(
    result: Dict[str, Any],
    verification: Dict[str, Any],
    registry: Dict[str, Any],
) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Status: **{result.get('status')}**",
        f"- Verification: **{verification.get('status')}**",
        f"- Dispatch ID: `{result.get('dispatch_id') or '-'}`",
        f"- Job ID: `{result.get('job_id') or '-'}`",
        f"- Runtime ID: `{result.get('runtime_id') or '-'}`",
        f"- Queue entries: **{registry.get('job_count', 0)}**",
        "- Execution started: **false**",
        "- Observer invoked: **false**",
        "",
        "## Safety boundary",
        "",
        "- Dispatch creates an immutable queue entry only.",
        "- No Observer process is started by this gateway.",
        "- A separate execution worker stage is required.",
        "- Duplicate dispatch IDs and runtimes are refused.",
        "- Authorization and runtime hashes are verified before queueing.",
        "",
    ]
    if result.get("reasons"):
        lines.extend(["## Refusal reasons", ""])
        for reason in result.get("reasons", []):
            lines.append(f"- `{reason}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument(
        "--analysis-root",
        required=True,
        help="Path to Results/Analysis",
    )
    parser.add_argument(
        "--request",
        default=None,
        help=(
            "Dispatch request JSON. Default: "
            "<analysis-root>/Experiments/execution_dispatch_request.json"
        ),
    )
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).resolve()
    experiments_root = analysis_root / "Experiments"
    runtime_registry_path = (
        experiments_root / "experiment_runtime_registry.json"
    )
    authorization_registry_path = (
        experiments_root / "launch_authorization_registry.json"
    )
    dispatch_registry_path = (
        experiments_root / "execution_dispatch_registry.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments_root / "execution_dispatch_request.json"
    )
    result_path = experiments_root / "execution_dispatch_result.json"
    verification_path = (
        experiments_root
        / "execution_dispatch_receipt_verification.json"
    )
    markdown_path = experiments_root / "execution_dispatch.md"

    runtime_registry = load_json(runtime_registry_path, {})
    authorization_registry = load_json(
        authorization_registry_path,
        {},
    )
    if not isinstance(runtime_registry, dict) or not runtime_registry:
        raise RuntimeError(
            f"Missing or invalid runtime registry: {runtime_registry_path}"
        )
    if (
        not isinstance(authorization_registry, dict)
        or not authorization_registry
    ):
        raise RuntimeError(
            "Missing or invalid authorization registry: "
            f"{authorization_registry_path}"
        )

    existing_request = load_json(request_path, {})
    if not isinstance(existing_request, dict):
        existing_request = {}

    if (
        not request_path.exists()
        or existing_request.get("dispatch") is not True
    ):
        atomic_write_json(
            request_path,
            build_request_template(
                runtime_registry,
                authorization_registry,
                existing_request,
            ),
        )

    request = load_json(request_path, {})
    if not isinstance(request, dict):
        request = {}

    existing_dispatch_registry = load_json(dispatch_registry_path, {})
    if not isinstance(existing_dispatch_registry, dict):
        existing_dispatch_registry = {}

    result = dispatch_execution(
        experiments_root,
        runtime_registry,
        authorization_registry,
        existing_dispatch_registry,
        request,
    )
    verification = verify_receipt(result)
    dispatch_registry = update_dispatch_registry(
        existing_dispatch_registry,
        result,
        verification,
    )

    atomic_write_json(result_path, result)
    atomic_write_json(verification_path, verification)
    atomic_write_json(dispatch_registry_path, dispatch_registry)
    markdown_path.write_text(
        render_markdown(result, verification, dispatch_registry),
        encoding="utf-8",
    )

    if result.get("status") == "QUEUED":
        atomic_write_json(
            request_path,
            {
                "schema": "archon_execution_dispatch_request_v1",
                "dispatch": False,
                "dispatch_id": None,
                "runtime_id": None,
                "authorization_id": None,
                "expected_runtime_hash": None,
                "expected_runtime_registry_hash": None,
                "expected_authorization_registry_hash": None,
                "requested_at": None,
                "requested_by": None,
                "confirmation": None,
                "last_consumed_dispatch_id": result.get("dispatch_id"),
                "instructions": {
                    "required_confirmation": (
                        "QUEUE_EXPERIMENT_EXECUTION"
                    ),
                    "verified_launch_authorization_required": True,
                    "dispatch_creates_queue_entry_only": True,
                    "observer_launches_immediately": False,
                    "manual_request_required": True,
                    "inactive_template_auto_refresh": True,
                },
            },
        )

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Status:       {result.get('status')}")
    print(f"Verification: {verification.get('status')}")
    print(f"Dispatch ID:  {result.get('dispatch_id') or '-'}")
    print(f"Job ID:       {result.get('job_id') or '-'}")
    print(f"Runtime ID:   {result.get('runtime_id') or '-'}")
    print(f"Queue:        {dispatch_registry.get('job_count', 0)} jobs")
    print("Execution:    NOT STARTED")
    print("Observer:     NOT INVOKED")
    print(f"Result JSON:  {result_path}")
    print(f"Registry:     {dispatch_registry_path}")
    print(f"Request:      {request_path}")
    print("=" * 72)

    return 0 if result.get("status") != "REFUSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
