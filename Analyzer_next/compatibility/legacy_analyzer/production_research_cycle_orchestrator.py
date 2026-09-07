#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Analyzer_next.compatibility.legacy_analyzer.research_cycle_record import (
    refresh_research_cycle_records,
)


VERSION = "1.0"
TITLE = "ARCHON Stage E Production Research Cycle Orchestrator"
CONFIRMATION = "RUN_FULL_PRODUCTION_RESEARCH_CYCLE"


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
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
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


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def verified_payload(path: Path, hash_field: str) -> Dict[str, Any]:
    payload = as_dict(load_json(path, {}))
    declared = text(payload.get(hash_field))
    core = {
        key: value
        for key, value in payload.items()
        if key != hash_field
    }
    if not declared or declared != canonical_hash(core):
        return {}
    return payload


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_production_research_cycle_policy_v1",
        "version": VERSION,
        "research_cycle_enabled": False,
        "enable_stage_policies_automatically": True,
        "stop_on_first_failure": True,
        "require_browser_publication": True,
        "require_completed_cycle_record": True,
        "default_analyzer_timeout_seconds": 1800,
        "maximum_analyzer_timeout_seconds": 86400,
        "updated_at": now_iso(),
    }


def default_request(last_consumed_cycle_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema": "archon_production_research_cycle_request_v1",
        "run_cycle": False,
        "cycle_id": None,
        "execution_request": {},
        "results_directory": None,
        "analyzer_entrypoint": None,
        "knowledge_atlas_directory": None,
        "world_atlas_directory": None,
        "analyzer_timeout_seconds": None,
        "force_profiles": True,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_cycle_id": last_consumed_cycle_id,
        "instructions": {
            "required_confirmation": CONFIRMATION,
            "production_policy_must_be_enabled": True,
            "one_owner_runs_all_production_boundaries": True,
            "child_stage_policies_remain_authoritative": True,
            "inactive_template_auto_refresh": True,
        },
    }


def run_module(
    python_executable: str,
    script: Path,
    analysis_root: Path,
    log_path: Path,
    *,
    modules_root: Optional[Path] = None,
    extra_args: Optional[List[str]] = None,
    allow_nonzero: bool = False,
) -> int:
    command = [
        python_executable,
        str(script),
        "--analysis-root",
        str(analysis_root),
    ]
    if modules_root is not None:
        command.extend(["--modules-root", str(modules_root)])
    if extra_args:
        command.extend(extra_args)
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0 and not allow_nonzero:
        raise RuntimeError(
            f"{script.name} exited with {completed.returncode}. See {log_path}"
        )
    return completed.returncode


def enable_policy(path: Path, **updates: Any) -> None:
    payload = as_dict(load_json(path, {}))
    payload.update(updates)
    payload["updated_at"] = now_iso()
    atomic_write_json(path, payload)


def result_step(
    steps: List[Dict[str, Any]],
    stage: str,
    status: Any,
    result_path: Path,
    log_path: Path,
) -> None:
    steps.append({
        "stage": stage,
        "status": status,
        "result_path": str(result_path),
        "log_path": str(log_path),
    })


def persist_result(
    result_path: Path,
    markdown_path: Path,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    core = {
        key: value
        for key, value in result.items()
        if key != "result_hash"
    }
    durable = {**core, "result_hash": canonical_hash(core)}
    atomic_write_json(result_path, durable)
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{durable.get('version')}**",
        f"- Status: **{durable.get('status')}**",
        f"- Cycle ID: `{durable.get('cycle_id') or '-'}`",
        f"- Failed stage: `{durable.get('failed_stage') or '-'}`",
        f"- Observer run ID: `{durable.get('observer_run_id') or '-'}`",
        f"- Publication ID: `{durable.get('publication_id') or '-'}`",
        "",
        "## Production boundaries",
        "",
    ]
    for step in as_list(durable.get("steps")):
        if isinstance(step, dict):
            lines.append(
                f"- `{step.get('stage')}`: **{step.get('status')}**"
            )
    lines.append("")
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return durable


def issue_receipt(
    receipt_path: Path,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    core = {
        "schema": "archon_production_research_cycle_receipt_v1",
        "version": VERSION,
        "status": result.get("status"),
        "cycle_id": result.get("cycle_id"),
        "failed_stage": result.get("failed_stage"),
        "observer_run_id": result.get("observer_run_id"),
        "bridge_id": result.get("bridge_id"),
        "reconciliation_id": result.get("reconciliation_id"),
        "finalization_id": result.get("finalization_id"),
        "publication_id": result.get("publication_id"),
        "result_hash": result.get("result_hash"),
        "result_path": result.get("result_path"),
        "issued_at": now_iso(),
    }
    receipt = {**core, "receipt_hash": canonical_hash(core)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def update_registry(
    registry_path: Path,
    result: Dict[str, Any],
    receipt: Dict[str, Any],
) -> None:
    registry = as_dict(load_json(registry_path, {}))
    rows = [
        item
        for item in as_list(registry.get("cycles"))
        if isinstance(item, dict)
        and item.get("cycle_id") != result.get("cycle_id")
    ]
    rows.append({
        "cycle_id": result.get("cycle_id"),
        "status": result.get("status"),
        "observer_run_id": result.get("observer_run_id"),
        "publication_id": result.get("publication_id"),
        "result_hash": result.get("result_hash"),
        "receipt_hash": receipt.get("receipt_hash"),
        "updated_at": now_iso(),
    })
    core = {
        "schema": "archon_production_research_cycle_registry_v1",
        "version": VERSION,
        "updated_at": now_iso(),
        "cycles": rows,
        "summary": {
            "cycle_count": len(rows),
            "completed_count": sum(
                item.get("status") in {"COMPLETED", "REUSED"}
                for item in rows
            ),
            "failed_count": sum(
                item.get("status") == "FAILED" for item in rows
            ),
        },
    }
    atomic_write_json(
        registry_path,
        {**core, "content_hash": canonical_hash(core)},
    )


def find_dispatch_job(
    dispatch: Dict[str, Any],
    job_id: str,
) -> Dict[str, Any]:
    rows = [
        item
        for item in as_list(dispatch.get("jobs"))
        if isinstance(item, dict) and text(item.get("job_id")) == job_id
    ]
    if len(rows) != 1:
        raise RuntimeError(
            f"Expected one dispatch row for {job_id}, found {len(rows)}"
        )
    return rows[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--modules-root", default=None)
    parser.add_argument("--request", default=None)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    analysis = Path(args.analysis_root).resolve()
    experiments = analysis / "Experiments"
    experiments.mkdir(parents=True, exist_ok=True)
    modules_root = (
        Path(args.modules_root).resolve()
        if args.modules_root
        else Path(__file__).resolve().parent
    )
    modules = {
        "execution": modules_root / "production_execution_cycle_orchestrator.py",
        "bridge": modules_root / "production_observer_analyzer_bridge.py",
        "reconciliation": (
            modules_root / "production_analyzer_completion_reconciliation.py"
        ),
        "finalization": (
            modules_root / "production_stage6_job_finalization.py"
        ),
        "publication": modules_root / "production_browser_publication.py",
    }
    missing_modules = [
        str(path) for path in modules.values() if not path.is_file()
    ]
    if missing_modules:
        raise FileNotFoundError(
            "Missing production modules: " + ", ".join(missing_modules)
        )

    policy_path = experiments / "production_research_cycle_policy.json"
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments / "production_research_cycle_request.json"
    )
    result_path = experiments / "production_research_cycle_result.json"
    registry_path = experiments / "production_research_cycle_registry.json"
    markdown_path = experiments / "production_research_cycle.md"
    receipts_dir = experiments / "ProductionResearchCycleReceipts"
    logs_dir = experiments / "ProductionResearchCycleLogs"

    policy = as_dict(load_json(policy_path, {}))
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    request = as_dict(load_json(request_path, {}))
    if not request or request.get("run_cycle") is not True:
        last_consumed = text(request.get("last_consumed_cycle_id"))
        atomic_write_json(request_path, default_request(last_consumed))
        result = {
            "schema": "archon_production_research_cycle_result_v1",
            "version": VERSION,
            "status": "NO_RESEARCH_CYCLE_REQUEST",
            "cycle_id": None,
            "failed_stage": None,
            "steps": [],
            "finished_at": now_iso(),
        }
        durable = persist_result(result_path, markdown_path, result)
        print(f"{TITLE}: {durable['status']}")
        return 0

    cycle_id = text(request.get("cycle_id"))
    receipt_path = receipts_dir / f"{cycle_id}.json" if cycle_id else None
    existing_receipt = (
        verified_payload(receipt_path, "receipt_hash")
        if receipt_path and receipt_path.is_file()
        else {}
    )
    if existing_receipt.get("status") == "COMPLETED":
        atomic_write_json(
            request_path,
            default_request(cycle_id),
        )
        reused = {
            "schema": "archon_production_research_cycle_result_v1",
            "version": VERSION,
            "status": "REUSED",
            "cycle_id": cycle_id,
            "failed_stage": None,
            "observer_run_id": existing_receipt.get("observer_run_id"),
            "bridge_id": existing_receipt.get("bridge_id"),
            "reconciliation_id": existing_receipt.get("reconciliation_id"),
            "finalization_id": existing_receipt.get("finalization_id"),
            "publication_id": existing_receipt.get("publication_id"),
            "receipt_path": str(receipt_path),
            "receipt_hash": existing_receipt.get("receipt_hash"),
            "steps": [],
            "finished_at": now_iso(),
        }
        persist_result(result_path, markdown_path, reused)
        print(f"{TITLE}: REUSED {cycle_id}")
        return 0

    failures: List[str] = []
    if policy.get("research_cycle_enabled") is not True:
        failures.append("RESEARCH_CYCLE_DISABLED")
    if not cycle_id:
        failures.append("CYCLE_ID_MISSING")
    if request.get("confirmation") != CONFIRMATION:
        failures.append("CONFIRMATION_INVALID")
    if not text(request.get("requested_by")):
        failures.append("REQUESTED_BY_MISSING")

    execution_request = as_dict(request.get("execution_request"))
    if text(execution_request.get("cycle_id")) != cycle_id:
        failures.append("EXECUTION_CYCLE_ID_MISMATCH")
    if execution_request.get("run_cycle") is not True:
        failures.append("EXECUTION_REQUEST_INACTIVE")

    required_paths = {
        "RESULTS_DIRECTORY_MISSING": text(request.get("results_directory")),
        "ANALYZER_ENTRYPOINT_MISSING": text(
            request.get("analyzer_entrypoint")
        ),
        "KNOWLEDGE_ATLAS_DIRECTORY_MISSING": text(
            request.get("knowledge_atlas_directory")
        ),
        "WORLD_ATLAS_DIRECTORY_MISSING": text(
            request.get("world_atlas_directory")
        ),
    }
    for reason, value in required_paths.items():
        if not value:
            failures.append(reason)

    requested_timeout = int(
        request.get("analyzer_timeout_seconds")
        or policy.get("default_analyzer_timeout_seconds")
        or 1800
    )
    maximum_timeout = int(
        policy.get("maximum_analyzer_timeout_seconds") or 86400
    )
    if requested_timeout <= 0 or requested_timeout > maximum_timeout:
        failures.append("ANALYZER_TIMEOUT_INVALID")

    if failures:
        atomic_write_json(request_path, default_request(cycle_id))
        result = {
            "schema": "archon_production_research_cycle_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "cycle_id": cycle_id,
            "failed_stage": "VALIDATION",
            "reasons": failures,
            "steps": [],
            "finished_at": now_iso(),
        }
        durable = persist_result(result_path, markdown_path, result)
        print(f"{TITLE}: REFUSED {'; '.join(failures)}")
        return 1

    results_directory = Path(
        str(request["results_directory"])
    ).expanduser().resolve()
    analyzer_entrypoint = Path(
        str(request["analyzer_entrypoint"])
    ).expanduser().resolve()
    knowledge_atlas = Path(
        str(request["knowledge_atlas_directory"])
    ).expanduser().resolve()
    world_atlas = Path(
        str(request["world_atlas_directory"])
    ).expanduser().resolve()
    path_failures = []
    if not results_directory.is_dir():
        path_failures.append(f"RESULTS_DIRECTORY_INVALID:{results_directory}")
    if not analyzer_entrypoint.is_file():
        path_failures.append(f"ANALYZER_ENTRYPOINT_INVALID:{analyzer_entrypoint}")
    if not knowledge_atlas.is_dir():
        path_failures.append(f"KNOWLEDGE_ATLAS_INVALID:{knowledge_atlas}")
    if not world_atlas.is_dir():
        path_failures.append(f"WORLD_ATLAS_INVALID:{world_atlas}")
    if path_failures:
        atomic_write_json(request_path, default_request(cycle_id))
        result = {
            "schema": "archon_production_research_cycle_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "cycle_id": cycle_id,
            "failed_stage": "PATH_VALIDATION",
            "reasons": path_failures,
            "steps": [],
            "finished_at": now_iso(),
        }
        persist_result(result_path, markdown_path, result)
        print(f"{TITLE}: REFUSED {'; '.join(path_failures)}")
        return 1

    requested_by = str(request["requested_by"])
    ids = {
        "bridge": text(request.get("bridge_id")) or f"{cycle_id}-BRIDGE",
        "reconciliation": (
            text(request.get("reconciliation_id")) or f"{cycle_id}-RECON"
        ),
        "finalization": (
            text(request.get("finalization_id")) or f"{cycle_id}-FINAL"
        ),
        "publication": (
            text(request.get("publication_id")) or f"{cycle_id}-PUB"
        ),
    }
    steps: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {
        "schema": "archon_production_research_cycle_result_v1",
        "version": VERSION,
        "status": "RUNNING",
        "cycle_id": cycle_id,
        "failed_stage": None,
        "observer_run_id": None,
        "bridge_id": ids["bridge"],
        "reconciliation_id": ids["reconciliation"],
        "finalization_id": ids["finalization"],
        "publication_id": ids["publication"],
        "steps": steps,
        "started_at": now_iso(),
        "finished_at": None,
    }
    failed_stage = "EXECUTION"

    try:
        child_auto = (
            policy.get("enable_stage_policies_automatically") is True
        )

        execution_log = logs_dir / f"{cycle_id}_01_execution.log"
        execution_policy_path = (
            experiments / "production_execution_cycle_policy.json"
        )
        execution_request_path = (
            experiments / "production_execution_cycle_request.json"
        )
        run_module(
            args.python,
            modules["execution"],
            analysis,
            logs_dir / f"{cycle_id}_00_execution_template.log",
            modules_root=modules_root,
        )
        if child_auto:
            enable_policy(
                execution_policy_path,
                cycle_enabled=True,
                enable_stage_policies_automatically=True,
                require_accepted_intake=True,
            )
        atomic_write_json(execution_request_path, execution_request)
        run_module(
            args.python,
            modules["execution"],
            analysis,
            execution_log,
            modules_root=modules_root,
        )
        execution_result_path = (
            experiments / "production_execution_cycle_result.json"
        )
        execution_result = as_dict(load_json(execution_result_path, {}))
        if execution_result.get("status") != "COMPLETED":
            raise RuntimeError(
                f"Execution cycle status is {execution_result.get('status')}"
            )
        observer_run_id = text(execution_result.get("observer_run_id"))
        if not observer_run_id:
            raise RuntimeError("Execution cycle has no Observer run ID")
        result["observer_run_id"] = observer_run_id
        result_step(
            steps,
            "EXECUTION",
            execution_result.get("status"),
            execution_result_path,
            execution_log,
        )

        failed_stage = "ANALYZER_BRIDGE"
        intake_result_path = (
            experiments / "production_observer_result_intake_result.json"
        )
        bridge_policy_path = (
            experiments / "production_observer_analyzer_bridge_policy.json"
        )
        bridge_request_path = (
            experiments / "production_observer_analyzer_bridge_request.json"
        )
        bridge_result_path = (
            experiments / "production_observer_analyzer_bridge_result.json"
        )
        run_module(
            args.python,
            modules["bridge"],
            analysis,
            logs_dir / f"{cycle_id}_02_bridge_template.log",
        )
        if child_auto:
            enable_policy(bridge_policy_path, bridge_enabled=True)
        atomic_write_json(bridge_request_path, {
            "schema": "archon_production_observer_analyzer_bridge_request_v1",
            "bridge": True,
            "bridge_id": ids["bridge"],
            "intake_result_path": str(intake_result_path),
            "results_directory": str(results_directory),
            "analyzer_entrypoint": str(analyzer_entrypoint),
            "knowledge_atlas_directory": str(knowledge_atlas),
            "world_atlas_directory": str(world_atlas),
            "timeout_seconds": requested_timeout,
            "force_profiles": request.get("force_profiles") is not False,
            "requested_at": now_iso(),
            "requested_by": requested_by,
            "confirmation": "BRIDGE_ACCEPTED_OBSERVER_RESULT_TO_ANALYZER",
            "last_consumed_bridge_id": None,
        })
        bridge_log = logs_dir / f"{cycle_id}_03_bridge.log"
        run_module(
            args.python,
            modules["bridge"],
            analysis,
            bridge_log,
        )
        bridge_result = as_dict(load_json(bridge_result_path, {}))
        if bridge_result.get("status") not in {"COMPLETED", "REUSED"}:
            raise RuntimeError(
                f"Analyzer bridge status is {bridge_result.get('status')}"
            )
        if text(bridge_result.get("observer_run_id")) != observer_run_id:
            raise RuntimeError("Analyzer bridge resolved a different Observer run")
        result["scientific_refresh_receipt_path"] = (
            bridge_result.get("scientific_refresh_receipt_path")
        )
        result["scientific_refresh_receipt_hash"] = (
            bridge_result.get("scientific_refresh_receipt_hash")
        )
        result_step(
            steps,
            "ANALYZER_BRIDGE",
            bridge_result.get("status"),
            bridge_result_path,
            bridge_log,
        )

        failed_stage = "ANALYZER_RECONCILIATION"
        reconciliation_policy_path = (
            experiments
            / "production_analyzer_completion_reconciliation_policy.json"
        )
        reconciliation_request_path = (
            experiments
            / "production_analyzer_completion_reconciliation_request.json"
        )
        reconciliation_result_path = (
            experiments
            / "production_analyzer_completion_reconciliation_result.json"
        )
        run_module(
            args.python,
            modules["reconciliation"],
            analysis,
            logs_dir / f"{cycle_id}_04_reconciliation_template.log",
        )
        if child_auto:
            enable_policy(
                reconciliation_policy_path,
                reconciliation_enabled=True,
            )
        atomic_write_json(reconciliation_request_path, {
            "schema": (
                "archon_production_analyzer_completion_"
                "reconciliation_request_v1"
            ),
            "reconcile": True,
            "reconciliation_id": ids["reconciliation"],
            "bridge_result_path": str(bridge_result_path),
            "requested_at": now_iso(),
            "requested_by": requested_by,
            "confirmation": "RECONCILE_COMPLETED_ANALYZER_RESULT",
            "last_consumed_reconciliation_id": None,
        })
        reconciliation_log = logs_dir / f"{cycle_id}_05_reconciliation.log"
        run_module(
            args.python,
            modules["reconciliation"],
            analysis,
            reconciliation_log,
        )
        reconciliation_result = as_dict(
            load_json(reconciliation_result_path, {})
        )
        if reconciliation_result.get("status") not in {
            "ANALYSIS_COMPLETED",
            "RECONCILIATION_REUSED",
        }:
            raise RuntimeError(
                "Analyzer reconciliation status is "
                f"{reconciliation_result.get('status')}"
            )
        job_id = text(reconciliation_result.get("job_id"))
        if not job_id:
            raise RuntimeError("Analyzer reconciliation has no Stage 6 job ID")
        result_step(
            steps,
            "ANALYZER_RECONCILIATION",
            reconciliation_result.get("status"),
            reconciliation_result_path,
            reconciliation_log,
        )

        failed_stage = "STAGE6_FINALIZATION"
        dispatch_path = experiments / "execution_dispatch_registry.json"
        dispatch = as_dict(load_json(dispatch_path, {}))
        dispatch_row = find_dispatch_job(dispatch, job_id)
        finalization_policy_path = (
            experiments / "production_stage6_job_finalization_policy.json"
        )
        finalization_request_path = (
            experiments / "production_stage6_job_finalization_request.json"
        )
        finalization_result_path = (
            experiments / "production_stage6_job_finalization_result.json"
        )
        run_module(
            args.python,
            modules["finalization"],
            analysis,
            logs_dir / f"{cycle_id}_06_finalization_template.log",
        )
        if child_auto:
            enable_policy(
                finalization_policy_path,
                finalization_enabled=True,
            )
        atomic_write_json(finalization_request_path, {
            "schema": "archon_production_stage6_job_finalization_request_v1",
            "finalize": True,
            "finalization_id": ids["finalization"],
            "analyzer_reconciliation_result_path": str(
                reconciliation_result_path
            ),
            "expected_dispatch_registry_hash": dispatch.get("content_hash"),
            "expected_job_file_hash": dispatch_row.get("job_file_hash"),
            "requested_at": now_iso(),
            "requested_by": requested_by,
            "confirmation": "FINALIZE_STAGE6_TASK_AFTER_ANALYSIS",
            "last_consumed_finalization_id": None,
        })
        finalization_log = logs_dir / f"{cycle_id}_07_finalization.log"
        run_module(
            args.python,
            modules["finalization"],
            analysis,
            finalization_log,
        )
        finalization_result = as_dict(load_json(finalization_result_path, {}))
        if finalization_result.get("status") not in {
            "FINALIZED",
            "FINALIZATION_REUSED",
        }:
            raise RuntimeError(
                f"Stage 6 finalization status is "
                f"{finalization_result.get('status')}"
            )
        result_step(
            steps,
            "STAGE6_FINALIZATION",
            finalization_result.get("status"),
            finalization_result_path,
            finalization_log,
        )

        failed_stage = "BROWSER_PUBLICATION"
        publication_result_path = experiments / "browser_publication_result.json"
        publication_log = logs_dir / f"{cycle_id}_08_publication.log"
        run_module(
            args.python,
            modules["publication"],
            analysis,
            publication_log,
            extra_args=[
                "--cycle-id",
                cycle_id,
                "--observer-run-id",
                observer_run_id,
                "--publication-id",
                ids["publication"],
            ],
        )
        publication_result = as_dict(load_json(publication_result_path, {}))
        if publication_result.get("status") not in {
            "PUBLISHED",
            "PUBLICATION_REUSED",
        }:
            raise RuntimeError(
                f"Browser publication status is "
                f"{publication_result.get('status')}"
            )
        result["publication_artifact_path"] = (
            publication_result.get("artifact_path")
        )
        result_step(
            steps,
            "BROWSER_PUBLICATION",
            publication_result.get("status"),
            publication_result_path,
            publication_log,
        )

        failed_stage = "RESEARCH_CYCLE_RECORD"
        refresh_research_cycle_records(analysis)
        cycle_record_path = (
            experiments / "ResearchCycleRecords" / "records"
            / f"{cycle_id}.json"
        )
        cycle_record = as_dict(load_json(cycle_record_path, {}))
        if policy.get("require_completed_cycle_record") is True:
            required = {
                "current_stage": "COMPLETED",
                "next_required_action": "NONE",
                "browser_publish_status": "PUBLISHED",
                "receipt_integrity": "OK",
            }
            mismatches = {
                key: {
                    "expected": expected,
                    "actual": cycle_record.get(key),
                }
                for key, expected in required.items()
                if cycle_record.get(key) != expected
            }
            if mismatches or as_list(cycle_record.get("blockers")):
                raise RuntimeError(
                    f"Research Cycle Record is incomplete: {mismatches}; "
                    f"blockers={cycle_record.get('blockers')}"
                )
        result["research_cycle_record_path"] = str(cycle_record_path)
        result["final_job_status"] = finalization_result.get("job_status")
        result_step(
            steps,
            "RESEARCH_CYCLE_RECORD",
            cycle_record.get("current_stage"),
            cycle_record_path,
            logs_dir / f"{cycle_id}_09_record_refresh.log",
        )

        result["status"] = "COMPLETED"
        result["finished_at"] = now_iso()
    except Exception as exc:
        result["status"] = "FAILED"
        result["failed_stage"] = failed_stage
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        result["finished_at"] = now_iso()
    finally:
        atomic_write_json(request_path, default_request(cycle_id))

    result["result_path"] = str(result_path)
    result["receipt_path"] = str(receipts_dir / f"{cycle_id}.json")
    durable = persist_result(result_path, markdown_path, result)
    receipt = issue_receipt(
        receipts_dir / f"{cycle_id}.json",
        durable,
    )
    update_registry(registry_path, durable, receipt)

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Status:              {durable.get('status')}")
    print(f"Cycle ID:            {cycle_id}")
    print(f"Observer run ID:     {durable.get('observer_run_id') or '-'}")
    print(f"Bridge ID:           {durable.get('bridge_id') or '-'}")
    print(f"Reconciliation ID:   {durable.get('reconciliation_id') or '-'}")
    print(f"Finalization ID:     {durable.get('finalization_id') or '-'}")
    print(f"Publication ID:      {durable.get('publication_id') or '-'}")
    print(f"Failed stage:        {durable.get('failed_stage') or '-'}")
    print(f"Result:              {result_path}")
    print(f"Receipt:             {receipts_dir / f'{cycle_id}.json'}")
    if durable.get("error"):
        print(f"Error:               {durable.get('error')}")
    print("=" * 72)
    return 0 if durable.get("status") == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
