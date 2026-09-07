#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Analyzer_next.compatibility.legacy_analyzer.research_cycle_record import (
    refresh_research_cycle_records,
)


VERSION = "1.1"
TITLE = "ARCHON Stage 7.9 Stage 6 Job Finalization"


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
            default=str,
        ) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


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


def file_sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_production_stage6_job_finalization_policy_v1",
        "version": VERSION,
        "finalization_enabled": False,
        "required_analysis_statuses": [
            "ANALYSIS_COMPLETED",
            "ANALYSIS_REUSED",
        ],
        "require_scientific_analysis_complete": True,
        "required_task_status_before": "PENDING",
        "required_attempt_count_before": 0,
        "task_status_after": "COMPLETED",
        "increment_attempt_count_once": True,
        "require_zero_failed_tasks_for_job_completion": True,
        "clear_active_execution_fields": True,
        "allow_idempotent_reuse": True,
        "manual_request_required": True,
        "updated_at": now_iso(),
    }


def default_request() -> Dict[str, Any]:
    return {
        "schema": "archon_production_stage6_job_finalization_request_v1",
        "finalize": False,
        "finalization_id": None,
        "analyzer_reconciliation_result_path": None,
        "expected_dispatch_registry_hash": None,
        "expected_job_file_hash": None,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_finalization_id": None,
    }


def update_dispatch_registry(
    registry: Dict[str, Any],
    *,
    job_id: str,
    job_status: str,
    job_file_hash: str,
    completed_tasks: int,
    failed_tasks: int,
    pending_tasks: int,
    finalized_at: str,
) -> Dict[str, Any]:
    rows = [
        dict(item)
        for item in as_list(registry.get("jobs"))
        if isinstance(item, dict)
    ]

    for item in rows:
        if item.get("job_id") != job_id:
            continue
        item["status"] = job_status
        item["job_file_hash"] = job_file_hash
        item["execution_started"] = True
        item["observer_invoked"] = True
        item["completed_tasks"] = completed_tasks
        item["failed_tasks"] = failed_tasks
        item["pending_tasks"] = pending_tasks
        item["current_task_id"] = None
        item["claim_id"] = None
        item["worker_id"] = None
        item["lease_expires_at"] = None
        item["start_authorization_id"] = None
        item["updated_at"] = finalized_at

    payload = dict(registry)
    payload["updated_at"] = finalized_at
    payload["jobs"] = rows
    payload["queued_count"] = sum(
        item.get("status") == "QUEUED" for item in rows
    )
    payload["claimed_count"] = sum(
        item.get("status") == "CLAIMED" for item in rows
    )
    payload["start_authorized_count"] = sum(
        item.get("status") == "START_AUTHORIZED"
        for item in rows
    )
    payload["partially_completed_count"] = sum(
        item.get("status") == "PARTIALLY_COMPLETED"
        for item in rows
    )
    payload["completed_count"] = sum(
        item.get("status") == "COMPLETED" for item in rows
    )
    payload["failed_count"] = sum(
        item.get("status") in {"FAILED", "PARTIALLY_FAILED"}
        for item in rows
    )
    payload["execution_started_count"] = sum(
        item.get("execution_started") is True for item in rows
    )
    payload["content_hash"] = canonical_hash({
        "jobs": rows,
        "policy": as_dict(payload.get("policy")),
    })
    return payload


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{result.get('version')}**",
        f"- Status: **{result.get('status')}**",
        f"- Finalization ID: `{result.get('finalization_id') or '-'}`",
        f"- Job ID: `{result.get('job_id') or '-'}`",
        f"- Task ID: `{result.get('task_id') or '-'}`",
        f"- Observer run ID: `{result.get('observer_run_id') or '-'}`",
        f"- Job status: **{result.get('job_status') or '-'}**",
        "",
        "## Completion gate",
        "",
        "- Analyzer reconciliation must be scientifically complete.",
        "- The matching Stage 6 task must still be PENDING with zero attempts.",
        "- Task, job file and dispatch registry are updated as one finalization.",
        "- Job becomes COMPLETED only with zero pending and zero failed tasks.",
        "",
    ]
    if result.get("issues"):
        lines.extend(["## Issues", ""])
        for item in result["issues"]:
            lines.append(
                f"- `{item.get('code')}` at `{item.get('path')}`: "
                f"{item.get('message')}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--request", default=None)
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).resolve()
    experiments = analysis_root / "Experiments"
    experiments.mkdir(parents=True, exist_ok=True)

    dispatch_path = experiments / "execution_dispatch_registry.json"
    policy_path = (
        experiments / "production_stage6_job_finalization_policy.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments
        / "production_stage6_job_finalization_request.json"
    )
    result_path = (
        experiments / "production_stage6_job_finalization_result.json"
    )
    registry_path = (
        experiments / "production_stage6_job_finalization_registry.json"
    )
    markdown_path = (
        experiments / "production_stage6_job_finalization.md"
    )
    receipt_dir = (
        experiments / "ProductionStage6JobFinalizationReceipts"
    )

    policy = load_json(policy_path, {})
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    request = load_json(request_path, {})
    if not request:
        request = default_request()
        atomic_write_json(request_path, request)

    if request.get("finalize") is not True:
        result = {
            "schema": "archon_production_stage6_job_finalization_result_v1",
            "version": VERSION,
            "status": "NO_FINALIZATION_REQUEST",
            "finalization_id": None,
            "issues": [],
        }
        atomic_write_json(result_path, result)
        markdown_path.write_text(
            render_markdown(result),
            encoding="utf-8",
        )
        print("=" * 72)
        print(TITLE)
        print("=" * 72)
        print(f"Version:          {VERSION}")
        print("Status:           NO_FINALIZATION_REQUEST")
        print("Finalization ID:  -")
        print(f"Policy:           {policy_path}")
        print(f"Request:          {request_path}")
        print(f"Result:           {result_path}")
        print(f"Registry:         {registry_path}")
        print(f"Markdown:         {markdown_path}")
        print("=" * 72)
        return 0

    issues: List[Dict[str, Any]] = []

    def issue(
        code: str,
        message: str,
        path: str,
        actual: Any = None,
    ) -> None:
        issues.append({
            "code": code,
            "message": message,
            "path": path,
            "actual": actual,
        })

    finalization_id = text(request.get("finalization_id"))
    if not finalization_id:
        issue(
            "FINALIZATION_ID_MISSING",
            "finalization_id is required.",
            "$.request.finalization_id",
        )

    if policy.get("finalization_enabled") is not True:
        issue(
            "FINALIZATION_DISABLED",
            "Stage 6 job finalization is disabled by policy.",
            "$.policy.finalization_enabled",
            policy.get("finalization_enabled"),
        )

    if request.get("confirmation") != "FINALIZE_STAGE6_TASK_AFTER_ANALYSIS":
        issue(
            "CONFIRMATION_INVALID",
            "Finalization confirmation is invalid.",
            "$.request.confirmation",
            request.get("confirmation"),
        )

    reconciliation_value = text(
        request.get("analyzer_reconciliation_result_path")
    )
    reconciliation_path = (
        Path(reconciliation_value).expanduser().resolve()
        if reconciliation_value else None
    )
    reconciliation = (
        load_json(reconciliation_path, {})
        if reconciliation_path else {}
    )
    if not reconciliation:
        issue(
            "ANALYZER_RECONCILIATION_MISSING",
            "Analyzer reconciliation result is missing or unreadable.",
            "$.request.analyzer_reconciliation_result_path",
            reconciliation_value,
        )

    analysis_status = text(reconciliation.get("status"))
    allowed_statuses = {
        str(value)
        for value in as_list(policy.get("required_analysis_statuses"))
    }
    if analysis_status not in allowed_statuses:
        issue(
            "ANALYSIS_STATUS_NOT_FINALIZABLE",
            "Analyzer reconciliation status does not permit finalization.",
            "$.analyzer_reconciliation.status",
            analysis_status,
        )

    if (
        policy.get("require_scientific_analysis_complete") is True
        and reconciliation.get("scientific_analysis_complete") is not True
    ):
        issue(
            "SCIENTIFIC_ANALYSIS_INCOMPLETE",
            "Scientific analysis is not complete.",
            "$.analyzer_reconciliation.scientific_analysis_complete",
            reconciliation.get("scientific_analysis_complete"),
        )

    job_id = text(reconciliation.get("job_id"))
    task_id = text(reconciliation.get("task_id"))
    observer_run_id = text(reconciliation.get("observer_run_id"))
    requested_run_id = text(reconciliation.get("requested_run_id"))
    reconciliation_id = text(reconciliation.get("reconciliation_id"))
    reconciliation_hash = text(
        reconciliation.get("reconciliation_hash")
    )

    if not job_id:
        issue(
            "JOB_ID_MISSING",
            "Analyzer reconciliation does not identify a Stage 6 job.",
            "$.analyzer_reconciliation.job_id",
        )
    if not task_id:
        issue(
            "TASK_ID_MISSING",
            "Analyzer reconciliation does not identify a Stage 6 task.",
            "$.analyzer_reconciliation.task_id",
        )
    if not observer_run_id:
        issue(
            "OBSERVER_RUN_ID_MISSING",
            "Analyzer reconciliation does not identify the actual run.",
            "$.analyzer_reconciliation.observer_run_id",
        )

    dispatch = load_json(dispatch_path, {})
    if not dispatch:
        issue(
            "DISPATCH_REGISTRY_MISSING",
            "Stage 6 execution dispatch registry is missing.",
            "$.stage6.execution_dispatch_registry",
            str(dispatch_path),
        )

    if (
        dispatch
        and request.get("expected_dispatch_registry_hash")
        != dispatch.get("content_hash")
    ):
        issue(
            "DISPATCH_REGISTRY_HASH_MISMATCH",
            "Stage 6 dispatch registry changed after authorization.",
            "$.request.expected_dispatch_registry_hash",
            {
                "expected": request.get(
                    "expected_dispatch_registry_hash"
                ),
                "actual": dispatch.get("content_hash"),
            },
        )

    dispatch_entry: Optional[Dict[str, Any]] = None
    if dispatch and job_id:
        matches = [
            item
            for item in as_list(dispatch.get("jobs"))
            if isinstance(item, dict)
            and text(item.get("job_id")) == job_id
        ]
        if len(matches) != 1:
            issue(
                "DISPATCH_JOB_NOT_FOUND_OR_DUPLICATED",
                "Exactly one Stage 6 dispatch job is required.",
                "$.stage6.execution_dispatch_registry.jobs",
                len(matches),
            )
        else:
            dispatch_entry = matches[0]

    job_path: Optional[Path] = None
    job: Dict[str, Any] = {}
    if dispatch_entry is not None:
        job_value = text(dispatch_entry.get("job_path"))
        job_path = (
            Path(job_value).expanduser().resolve()
            if job_value else None
        )
        if job_path is None or not job_path.is_file():
            issue(
                "EXECUTION_JOB_MISSING",
                "Stage 6 execution job file is missing.",
                "$.stage6.dispatch_job.job_path",
                job_value,
            )
        else:
            job = load_json(job_path, {})
            if not job:
                issue(
                    "EXECUTION_JOB_INVALID",
                    "Stage 6 execution job is unreadable.",
                    "$.stage6.execution_job",
                    str(job_path),
                )

    if job and dispatch_entry:
        actual_job_hash = canonical_hash(job)
        if actual_job_hash != dispatch_entry.get("job_file_hash"):
            issue(
                "JOB_FILE_HASH_MISMATCH",
                "Stage 6 job file differs from its dispatch registry hash.",
                "$.stage6.dispatch_job.job_file_hash",
                {
                    "registry": dispatch_entry.get("job_file_hash"),
                    "actual": actual_job_hash,
                },
            )
        if (
            request.get("expected_job_file_hash")
            != dispatch_entry.get("job_file_hash")
        ):
            issue(
                "EXPECTED_JOB_HASH_MISMATCH",
                "Stage 6 job changed after finalization request creation.",
                "$.request.expected_job_file_hash",
                {
                    "expected": request.get("expected_job_file_hash"),
                    "actual": dispatch_entry.get("job_file_hash"),
                },
            )

    tasks: List[Dict[str, Any]] = []
    task_before: Optional[Dict[str, Any]] = None
    if job and task_id:
        tasks = [
            dict(item)
            for item in as_list(as_dict(job.get("job")).get("tasks"))
            if isinstance(item, dict)
        ]
        matches = [
            item for item in tasks
            if text(item.get("task_id")) == task_id
        ]
        if len(matches) != 1:
            issue(
                "TASK_NOT_FOUND_OR_DUPLICATED",
                "Exactly one matching Stage 6 task is required.",
                "$.stage6.execution_job.job.tasks",
                len(matches),
            )
        else:
            task_before = matches[0]

    registry = load_json(registry_path, {})
    previous = None
    for item in as_list(registry.get("finalizations")):
        if not isinstance(item, dict):
            continue
        if (
            text(item.get("task_id")) == task_id
            and text(item.get("reconciliation_hash"))
            == reconciliation_hash
            and item.get("status") == "FINALIZED"
        ):
            previous = item
            break

    if (
        previous
        and policy.get("allow_idempotent_reuse") is True
        and not issues
    ):
        result = {
            "schema": "archon_production_stage6_job_finalization_result_v1",
            "version": VERSION,
            "status": "FINALIZATION_REUSED",
            "finalization_id": finalization_id,
            "job_id": job_id,
            "task_id": task_id,
            "observer_run_id": observer_run_id,
            "reused_finalization_id": previous.get("finalization_id"),
            "job_status": previous.get("job_status"),
            "receipt_path": previous.get("receipt_path"),
            "issues": [],
            "completed_at": now_iso(),
        }
        atomic_write_json(result_path, result)
        atomic_write_json(
            request_path,
            {
                **default_request(),
                "last_consumed_finalization_id": finalization_id,
            },
        )
        markdown_path.write_text(
            render_markdown(result),
            encoding="utf-8",
        )
        print("=" * 72)
        print(TITLE)
        print("=" * 72)
        print("Status:           FINALIZATION_REUSED")
        print(f"Finalization ID:  {finalization_id}")
        print(f"Job ID:           {job_id}")
        print(f"Task ID:          {task_id}")
        print(
            f"Previous:         "
            f"{previous.get('finalization_id')}"
        )
        print(f"Result:           {result_path}")
        print("=" * 72)
        return 0

    if task_before is not None:
        if (
            task_before.get("status")
            != policy.get("required_task_status_before")
        ):
            issue(
                "TASK_STATUS_INVALID",
                "Stage 6 task is not in the required pre-finalization state.",
                "$.stage6.task.status",
                task_before.get("status"),
            )
        if int(task_before.get("attempt_count") or 0) != int(
            policy.get("required_attempt_count_before") or 0
        ):
            issue(
                "TASK_ATTEMPT_COUNT_INVALID",
                "Stage 6 task attempt count is not finalizable.",
                "$.stage6.task.attempt_count",
                task_before.get("attempt_count"),
            )
        task_run_id = text(task_before.get("run_id"))
        if (
            requested_run_id
            and task_run_id
            and requested_run_id != task_run_id
        ):
            issue(
                "REQUESTED_RUN_ID_MISMATCH",
                "Analyzer evidence belongs to a different requested run.",
                "$.identity.requested_run_id",
                {
                    "stage6_task_run_id": task_run_id,
                    "analyzer_requested_run_id": requested_run_id,
                },
            )

    finalized_at = now_iso()
    job_status: Optional[str] = None
    completed_count = 0
    failed_count = 0
    pending_count = 0
    job_file_hash: Optional[str] = None
    receipt_path: Optional[Path] = None

    if not issues:
        assert task_before is not None
        assert job_path is not None
        assert dispatch_entry is not None

        for item in tasks:
            if item.get("task_id") != task_id:
                continue
            item["status"] = policy.get("task_status_after")
            item["attempt_count"] = (
                int(item.get("attempt_count") or 0) + 1
            )
            item["started_at"] = (
                item.get("started_at")
                or reconciliation.get("completed_at")
                or finalized_at
            )
            item["finished_at"] = finalized_at
            item["exit_code"] = 0
            item["error"] = None
            item["observer_run_id"] = observer_run_id
            item["requested_run_id"] = requested_run_id
            item["analyzer_bridge_id"] = reconciliation.get("bridge_id")
            item["analyzer_reconciliation_id"] = reconciliation_id
            item["analyzer_reconciliation_hash"] = reconciliation_hash
            item["analysis_status"] = analysis_status
            item["scientific_analysis_complete"] = True
            item["finalization_id"] = finalization_id
            item["finalized_at"] = finalized_at
            item["finalized_by"] = request.get("requested_by")

        completed_count = sum(
            item.get("status") == "COMPLETED" for item in tasks
        )
        failed_count = sum(
            item.get("status") == "FAILED" for item in tasks
        )
        pending_count = sum(
            item.get("status") == "PENDING" for item in tasks
        )

        if failed_count:
            job_status = (
                "FAILED"
                if pending_count == 0 else "PARTIALLY_FAILED"
            )
        elif pending_count:
            job_status = "PARTIALLY_COMPLETED"
        else:
            job_status = "COMPLETED"

        if (
            job_status == "COMPLETED"
            and policy.get(
                "require_zero_failed_tasks_for_job_completion"
            ) is True
            and failed_count != 0
        ):
            issue(
                "JOB_COMPLETION_WITH_FAILED_TASKS",
                "A completed job cannot contain failed tasks.",
                "$.stage6.execution_job.job.tasks",
                failed_count,
            )

    if not issues:
        job_block = as_dict(job.get("job"))
        job_block["tasks"] = tasks
        job["job"] = job_block
        job["status"] = job_status
        job["updated_at"] = finalized_at

        state = as_dict(job.get("execution_state"))
        state["started"] = True
        state["started_at"] = (
            state.get("started_at")
            or reconciliation.get("completed_at")
            or finalized_at
        )
        state["finished"] = pending_count == 0
        state["finished_at"] = (
            finalized_at if pending_count == 0 else None
        )
        state["current_task_id"] = None
        state["completed_tasks"] = completed_count
        state["failed_tasks"] = failed_count
        state["pending_tasks"] = pending_count
        state["last_completed_task_id"] = task_id
        state["last_observer_run_id"] = observer_run_id
        state["last_analysis_reconciliation_id"] = reconciliation_id
        state["last_finalization_id"] = finalization_id
        state["finalized_at"] = finalized_at
        job["execution_state"] = state

        job_policy = as_dict(job.get("policy"))
        job_policy["execution_started"] = True
        job_policy["observer_invoked"] = True
        job_policy["worker_claimed"] = False
        job_policy["start_authorized"] = False
        job["policy"] = job_policy

        if policy.get("clear_active_execution_fields") is True:
            claim = as_dict(job.get("worker_claim"))
            if claim:
                claim["released"] = True
                claim["status"] = "RELEASED"
                claim["released_at"] = finalized_at
                claim["release_reason"] = (
                    "PRODUCTION_ANALYSIS_FINALIZED"
                )
                job["worker_claim"] = claim

            authorization = as_dict(
                job.get("start_authorization")
            )
            if authorization:
                authorization["status"] = "CONSUMED"
                authorization["consumed_at"] = finalized_at
                authorization["finalization_id"] = finalization_id
                job["start_authorization"] = authorization

        job["production_analysis_finalization"] = {
            "finalization_id": finalization_id,
            "analyzer_reconciliation_id": reconciliation_id,
            "analyzer_reconciliation_hash": reconciliation_hash,
            "analysis_status": analysis_status,
            "observer_run_id": observer_run_id,
            "requested_run_id": requested_run_id,
            "task_id": task_id,
            "finalized_at": finalized_at,
            "finalized_by": request.get("requested_by"),
        }

        atomic_write_json(job_path, job)
        job_file_hash = canonical_hash(job)

        updated_dispatch = update_dispatch_registry(
            dispatch,
            job_id=str(job_id),
            job_status=str(job_status),
            job_file_hash=job_file_hash,
            completed_tasks=completed_count,
            failed_tasks=failed_count,
            pending_tasks=pending_count,
            finalized_at=finalized_at,
        )
        atomic_write_json(dispatch_path, updated_dispatch)
        dispatch = updated_dispatch

    status = "FINALIZED" if not issues else "FINALIZATION_REFUSED"

    result_core = {
        "schema": "archon_production_stage6_job_finalization_result_v1",
        "version": VERSION,
        "status": status,
        "finalization_id": finalization_id,
        "analyzer_reconciliation_result_path": (
            str(reconciliation_path)
            if reconciliation_path else None
        ),
        "analyzer_reconciliation_id": reconciliation_id,
        "analyzer_reconciliation_hash": reconciliation_hash,
        "analysis_status": analysis_status,
        "job_id": job_id,
        "job_path": str(job_path) if job_path else None,
        "job_file_hash": job_file_hash,
        "task_id": task_id,
        "observer_run_id": observer_run_id,
        "requested_run_id": requested_run_id,
        "job_status": job_status,
        "completed_tasks": completed_count,
        "failed_tasks": failed_count,
        "pending_tasks": pending_count,
        "task_transitioned": status == "FINALIZED",
        "scientific_analysis_complete": (
            reconciliation.get("scientific_analysis_complete") is True
        ),
        "issues": issues,
        "finalized_at": finalized_at if status == "FINALIZED" else None,
        "refused_at": now_iso() if status != "FINALIZED" else None,
    }
    result = {
        **result_core,
        "finalization_hash": canonical_hash(result_core),
    }
    atomic_write_json(result_path, result)

    if status == "FINALIZED":
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / f"{finalization_id}.json"
        receipt = {
            "schema": (
                "archon_production_stage6_job_finalization_receipt_v1"
            ),
            "version": VERSION,
            "status": "FINALIZED",
            "finalization_id": finalization_id,
            "finalization_hash": result["finalization_hash"],
            "job_id": job_id,
            "job_file_hash": job_file_hash,
            "task_id": task_id,
            "observer_run_id": observer_run_id,
            "analyzer_reconciliation_id": reconciliation_id,
            "analyzer_reconciliation_hash": reconciliation_hash,
            "job_status": job_status,
            "completed_tasks": completed_count,
            "failed_tasks": failed_count,
            "pending_tasks": pending_count,
            "scientific_analysis_complete": True,
            "result_path": str(result_path),
            "issued_at": now_iso(),
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        atomic_write_json(receipt_path, receipt)

    rows = [
        item
        for item in as_list(registry.get("finalizations"))
        if isinstance(item, dict)
    ]
    rows.append({
        "finalization_id": finalization_id,
        "status": status,
        "finalization_hash": result.get("finalization_hash"),
        "receipt_path": str(receipt_path) if receipt_path else None,
        "analyzer_reconciliation_id": reconciliation_id,
        "reconciliation_hash": reconciliation_hash,
        "job_id": job_id,
        "job_file_hash": job_file_hash,
        "task_id": task_id,
        "observer_run_id": observer_run_id,
        "job_status": job_status,
        "completed_tasks": completed_count,
        "failed_tasks": failed_count,
        "pending_tasks": pending_count,
        "recorded_at": now_iso(),
    })
    unique = {
        str(item.get("finalization_id")): item
        for item in rows
        if item.get("finalization_id")
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: str(item.get("finalization_id")),
    )
    registry_payload = {
        "schema": "archon_production_stage6_job_finalization_registry_v1",
        "version": VERSION,
        "updated_at": now_iso(),
        "finalization_count": len(ordered),
        "finalized_count": sum(
            item.get("status") == "FINALIZED"
            for item in ordered
        ),
        "reused_count": sum(
            item.get("status") == "FINALIZATION_REUSED"
            for item in ordered
        ),
        "refused_count": sum(
            item.get("status") == "FINALIZATION_REFUSED"
            for item in ordered
        ),
        "finalizations": ordered,
    }
    registry_payload["content_hash"] = canonical_hash(ordered)
    atomic_write_json(registry_path, registry_payload)

    atomic_write_json(
        request_path,
        {
            **default_request(),
            "last_consumed_finalization_id": finalization_id,
        },
    )
    markdown_path.write_text(
        render_markdown(result),
        encoding="utf-8",
    )
    refresh_research_cycle_records(analysis_root)

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Version:                    {VERSION}")
    print(f"Status:                     {status}")
    print(f"Finalization ID:            {finalization_id or '-'}")
    print(f"Analyzer reconciliation:    {reconciliation_id or '-'}")
    print(f"Job ID:                     {job_id or '-'}")
    print(f"Task ID:                    {task_id or '-'}")
    print(f"Observer run ID:            {observer_run_id or '-'}")
    print(f"Job status:                 {job_status or '-'}")
    print(
        f"Tasks:                      "
        f"{completed_count} completed | "
        f"{pending_count} pending | "
        f"{failed_count} failed"
    )
    print(f"Issues:                     {len(issues)}")
    print(f"Result:                     {result_path}")
    print(
        f"Receipt:                    "
        f"{str(receipt_path) if receipt_path else '-'}"
    )
    print(f"Registry:                   {registry_path}")
    print(f"Dispatch registry:          {dispatch_path}")
    print(f"Markdown:                   {markdown_path}")
    print("=" * 72)

    return 0 if status in {"FINALIZED", "FINALIZATION_REUSED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
