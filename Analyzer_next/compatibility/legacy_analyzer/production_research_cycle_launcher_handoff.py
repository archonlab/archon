#!/usr/bin/env python3
"""Prepare one verified Stage 6 task for the authoritative production owner."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from Analyzer_next.compatibility.legacy_analyzer.production_mutation_execution_adapter import (
    ADAPTER_ID as MUTATION_ADAPTER_ID,
    MutationAdapterError,
    materialize_protocol_arm,
)


VERSION = "1.0"
TITLE = "ARCHON Stage E.2 Launcher → Production Owner Handoff"
CONFIRMATION = "PREPARE_NEXT_PRODUCTION_RESEARCH_CYCLE"


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


def int_value(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_rule(value: Any) -> Tuple[Optional[str], Optional[int]]:
    raw = text(value)
    if not raw:
        return None, None
    digits = raw
    if raw.upper().startswith("RULE-"):
        digits = raw.split("-", 1)[1]
    numeric = int_value(digits)
    if numeric is None or numeric < 0:
        return None, None
    return f"RULE-{numeric:05d}", numeric


def normalize_topology(value: Any) -> Optional[str]:
    raw = (text(value) or "").upper()
    aliases = {
        "TORUS": "TORUS",
        "BOUNDED": "PLANE",
        "PLANE": "PLANE",
    }
    return aliases.get(raw)


def normalize_boundary(value: Any) -> Optional[str]:
    raw = (text(value) or "").upper()
    aliases = {
        "WRAP": "WRAP",
        "PERIODIC": "WRAP",
        "FIXED_DEAD": "FIXED_DEAD",
        "FIXED_ALIVE": "FIXED_ALIVE",
        "REFLECTIVE": "REFLECTIVE",
    }
    return aliases.get(raw)


def normalize_role(value: Any) -> str:
    raw = (text(value) or "BASELINE").upper()
    if raw in {"BASELINE", "BASELINE_CONTROL", "CONTROL", "CANONICAL"}:
        return "baseline"
    if raw in {"TREATMENT", "PERTURBATION"}:
        return "treatment"
    return raw.lower()


def telemetry_identity_issues(
    database: Path,
    *,
    experiment_id: Optional[str],
    condition_id: Optional[str],
) -> List[str]:
    if not database.is_file():
        return [f"TELEMETRY_DATABASE_INVALID:{database}"]
    issues: List[str] = []
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            if experiment_id:
                row = connection.execute(
                    "SELECT 1 FROM experiments WHERE experiment_id = ? LIMIT 1",
                    (experiment_id,),
                ).fetchone()
                if row is None:
                    issues.append(
                        f"EXPERIMENT_NOT_REGISTERED:{experiment_id}"
                    )
            if condition_id:
                row = connection.execute(
                    "SELECT 1 FROM experimental_conditions "
                    "WHERE condition_id = ? LIMIT 1",
                    (condition_id,),
                ).fetchone()
                if row is None:
                    issues.append(
                        f"CONDITION_NOT_REGISTERED:{condition_id}"
                    )
        finally:
            connection.close()
    except sqlite3.Error as exc:
        issues.append(f"TELEMETRY_IDENTITY_CHECK_FAILED:{exc}")
    return issues


def select_next_task(
    experiments: Path,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], List[str]]:
    dispatch = as_dict(
        load_json(experiments / "execution_dispatch_registry.json", {})
    )
    eligible: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    issues: List[str] = []
    for row in as_list(dispatch.get("jobs")):
        if not isinstance(row, dict):
            continue
        if row.get("status") not in {"QUEUED", "PARTIALLY_COMPLETED"}:
            continue
        if int(row.get("pending_tasks") or 0) <= 0:
            continue
        if row.get("claim_id") or row.get("current_task_id"):
            continue
        job_path_value = text(row.get("job_path"))
        job_path = Path(job_path_value).expanduser().resolve() if job_path_value else None
        job = as_dict(load_json(job_path, {})) if job_path else {}
        if not job:
            issues.append(f"EXECUTION_JOB_INVALID:{row.get('job_id')}")
            continue
        if canonical_hash(job) != row.get("job_file_hash"):
            issues.append(f"JOB_FILE_HASH_MISMATCH:{row.get('job_id')}")
            continue
        pending = [
            item
            for item in as_list(as_dict(job.get("job")).get("tasks"))
            if isinstance(item, dict) and item.get("status") == "PENDING"
        ]
        if not pending:
            issues.append(f"PENDING_TASK_MISSING:{row.get('job_id')}")
            continue
        pending.sort(key=lambda item: int(item.get("order") or 0))
        eligible.append((row, {"job": job, "task": pending[0]}))

    if issues:
        return None, None, sorted(set(issues))
    if not eligible:
        return None, None, []
    if len(eligible) != 1:
        return None, None, [f"ELIGIBLE_JOB_COUNT_INVALID:{len(eligible)}"]
    return eligible[0][0], eligible[0][1], []


def build_spec(
    *,
    dispatch_row: Dict[str, Any],
    job: Dict[str, Any],
    task: Dict[str, Any],
    observer_script: Path,
    telemetry_database: Path,
    requested_by: str,
    timeout_seconds: int,
    results_directory: Optional[Path] = None,
    world_atlas_directory: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str], Dict[str, Any]]:
    immutable = as_dict(job.get("job"))
    runtime = as_dict(task.get("runtime_spec"))
    perturbation = as_dict(runtime.get("perturbation"))
    missing: List[str] = []

    experiment_id = text(runtime.get("experiment_id"))
    condition_id = text(runtime.get("condition_id"))
    rule_id, numeric_rule = normalize_rule(
        runtime.get("rule_id", runtime.get("rule"))
    )
    field_size = runtime.get("field_size")
    width = height = None
    if isinstance(field_size, (list, tuple)) and len(field_size) == 2:
        width = int_value(field_size[0])
        height = int_value(field_size[1])
    topology = normalize_topology(runtime.get("topology"))
    boundary = normalize_boundary(runtime.get("boundary_condition"))
    ticks = int_value(runtime.get("duration_ticks"))
    seed = int_value(runtime.get("seed"))
    output_value = text(runtime.get("output_directory"))
    output_directory = (
        Path(output_value).expanduser().resolve() if output_value else None
    )

    required = {
        "EXPERIMENT_ID_UNRESOLVED": experiment_id,
        "CONDITION_ID_UNRESOLVED": condition_id,
        "RULE_ID_UNRESOLVED": rule_id,
        "FIELD_WIDTH_UNRESOLVED": width,
        "FIELD_HEIGHT_UNRESOLVED": height,
        "TOPOLOGY_UNRESOLVED": topology,
        "BOUNDARY_CONDITION_UNRESOLVED": boundary,
        "DURATION_TICKS_UNRESOLVED": ticks,
        "SEED_UNRESOLVED": seed,
        "OUTPUT_DIRECTORY_UNRESOLVED": output_directory,
    }
    for reason, value in required.items():
        if value is None:
            missing.append(reason)
    if width is not None and width <= 0:
        missing.append("FIELD_WIDTH_INVALID")
    if height is not None and height <= 0:
        missing.append("FIELD_HEIGHT_INVALID")
    if ticks is not None and ticks <= 0:
        missing.append("DURATION_TICKS_INVALID")
    if not observer_script.is_file():
        missing.append("OBSERVER_SCRIPT_INVALID")
    if not telemetry_database.parent.is_dir():
        missing.append("TELEMETRY_PARENT_INVALID")
    if output_directory is not None and output_directory.is_dir():
        try:
            if any(output_directory.iterdir()):
                missing.append("OUTPUT_DIRECTORY_NOT_EMPTY")
        except OSError:
            missing.append("OUTPUT_DIRECTORY_UNREADABLE")
    missing.extend(
        telemetry_identity_issues(
            telemetry_database,
            experiment_id=experiment_id,
            condition_id=condition_id,
        )
    )
    if perturbation:
        capability = as_dict(
            perturbation.get("execution_capability")
        )
        if capability.get("required_adapter") != MUTATION_ADAPTER_ID:
            missing.append("PRODUCTION_MUTATION_ADAPTER_ID_MISMATCH")
        if capability.get("available") is not True:
            missing.append("PRODUCTION_MUTATION_ADAPTER_UNAVAILABLE")
        if results_directory is None:
            missing.append("MUTATION_RESULTS_DIRECTORY_UNRESOLVED")
        if world_atlas_directory is None:
            missing.append("MUTATION_WORLD_ATLAS_UNRESOLVED")

    context = {
        "experiment_id": experiment_id,
        "condition_id": condition_id,
        "rule_id": rule_id,
        "numeric_rule": numeric_rule,
        "output_directory": str(output_directory) if output_directory else None,
        "pending_tasks": int(dispatch_row.get("pending_tasks") or 0),
    }
    if missing:
        return None, sorted(set(missing)), context

    assert output_directory is not None
    assert experiment_id is not None
    assert condition_id is not None
    assert rule_id is not None
    assert numeric_rule is not None
    assert width is not None
    assert height is not None
    assert topology is not None
    assert boundary is not None
    assert ticks is not None
    assert seed is not None

    run_id = text(task.get("run_id"))
    task_id = text(task.get("task_id"))
    job_id = text(dispatch_row.get("job_id"))
    runtime_id = text(dispatch_row.get("runtime_id"))
    if not all((run_id, task_id, job_id, runtime_id)):
        return None, ["STAGE6_IDENTITY_INCOMPLETE"], context

    mutation_materialization: Optional[Dict[str, Any]] = None
    if perturbation:
        assert results_directory is not None
        assert world_atlas_directory is not None
        try:
            mutation_materialization = materialize_protocol_arm(
                world_atlas_directory=world_atlas_directory,
                results_directory=results_directory,
                rule_id=numeric_rule,
                perturbation=perturbation,
                run_id=run_id,
                task_id=task_id,
                experiment_id=experiment_id,
                condition_id=condition_id,
                replicate_index=int(
                    runtime.get("replicate_index") or 0
                ),
                experiment_seed=seed,
                run_output_directory=output_directory,
            )
        except MutationAdapterError as exc:
            context["mutation_adapter_error"] = str(exc)
            return None, [
                f"PRODUCTION_MUTATION_ADAPTER_REFUSED:{exc}"
            ], context

    artifacts = [
        ("execution_receipt", "execution_receipt.json"),
        ("observer_stdout", "observer.stdout.log"),
        ("observer_stderr", "observer.stderr.log"),
        ("telemetry_reference", "telemetry_reference.json"),
        ("run_summary", "run_summary.json"),
    ]
    perturbation_enabled = bool(perturbation)
    plan_id = text(immutable.get("plan_id"))
    rule_source = (
        str(mutation_materialization["rule_file"])
        if mutation_materialization is not None
        else "stage6_runtime_spec"
    )
    rule_hash = (
        mutation_materialization["rule_file_sha256"]
        if mutation_materialization is not None
        else None
    )
    extra_arguments = (
        [
            "--mutation-manifest",
            str(mutation_materialization["manifest_file"]),
            "--mutation-rule-sha256",
            str(mutation_materialization["rule_file_sha256"]),
            "--mutation-manifest-sha256",
            str(mutation_materialization["manifest_file_sha256"]),
        ]
        if mutation_materialization is not None
        else []
    )
    spec = {
        "schema": "archon_observer_execution_spec_v1",
        "contract_version": "1.0",
        "identity": {
            "experiment_id": experiment_id,
            "job_id": job_id,
            "task_id": task_id,
            "run_id": run_id,
            "runtime_id": runtime_id,
            "plan_id": plan_id,
        },
        "rule": {
            "rule_id": rule_id,
            "rule_source": rule_source,
            "rule_hash": rule_hash,
            "rule_format": (
                "ARCHON_MUTATED_RULE_FILE_V2"
                if mutation_materialization is not None
                else "ARCHON_CANONICAL_RULE_ID"
            ),
        },
        "conditions": {
            "dimension": 2,
            "field": {"width": width, "height": height},
            "topology": topology,
            "boundary_condition": boundary,
            "ticks": ticks,
            "seed": {
                "mode": "EXPLICIT",
                "value": seed,
                "derivation": "stage6_runtime_spec",
            },
            "initial_state": {
                "mode": "GENERATED",
                "source_path": None,
                "source_hash": None,
            },
            "execution_mode": (
                "PERTURBATION" if perturbation_enabled else "FRESH"
            ),
            "resume": {
                "enabled": False,
                "source_run_id": None,
                "checkpoint_path": None,
                "checkpoint_hash": None,
                "resume_tick": None,
            },
            "perturbation": {
                "enabled": perturbation_enabled,
                "protocol_id": perturbation.get("protocol_id"),
                "protocol_hash": perturbation.get("protocol_hash"),
                "scheduled_events": as_list(
                    perturbation.get("scheduled_events")
                ),
            },
        },
        "observer": {
            "adapter": "PRODUCTION_OBSERVER",
            "script_path": str(observer_script),
            "script_hash": file_sha256(observer_script),
            "python_executable": sys.executable,
            "extra_arguments": extra_arguments,
            "timeout_seconds": timeout_seconds,
        },
        "outputs": {
            "output_directory": str(output_directory),
            "telemetry_target": {
                "backend": "SQLITE",
                "database_path": str(telemetry_database),
                "run_table": "runs",
                "run_id": run_id,
            },
            "artifacts": [
                {
                    "role": role,
                    "required": True,
                    "path": str(output_directory / filename),
                }
                for role, filename in artifacts
            ],
        },
        "provenance": {
            "requested_by": requested_by,
            "created_at": now_iso(),
            "source_action_id": immutable.get("intake_id"),
            "source_plan_id": plan_id,
            "source_task_hash": canonical_hash(task),
            "runtime_spec_hash": canonical_hash(runtime),
            "mutation_materialization": (
                {
                    "adapter_id": MUTATION_ADAPTER_ID,
                    "mutation_id": mutation_materialization.get(
                        "mutation_id"
                    ),
                    "manifest_file": str(
                        mutation_materialization["manifest_file"]
                    ),
                    "manifest_file_sha256": (
                        mutation_materialization[
                            "manifest_file_sha256"
                        ]
                    ),
                    "materialization_hash": as_dict(
                        mutation_materialization.get("manifest")
                    ).get("materialization_hash"),
                }
                if mutation_materialization is not None
                else None
            ),
        },
        "confirmation": "VALIDATE_OBSERVER_EXECUTION_CONTRACT",
        "last_validated_contract_hash": None,
    }
    context.update({
        "job_id": job_id,
        "task_id": task_id,
        "run_id": run_id,
        "runtime_id": runtime_id,
        "plan_id": plan_id,
        "mutation_id": (
            mutation_materialization.get("mutation_id")
            if mutation_materialization is not None
            else None
        ),
    })
    return spec, [], context


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--results-directory", required=True)
    parser.add_argument("--analyzer-entrypoint", required=True)
    parser.add_argument("--observer-script", required=True)
    parser.add_argument("--telemetry-database", required=True)
    parser.add_argument("--knowledge-atlas-directory", required=True)
    parser.add_argument("--world-atlas-directory", required=True)
    parser.add_argument("--requested-by", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    analysis = Path(args.analysis_root).expanduser().resolve()
    experiments = analysis / "Experiments"
    experiments.mkdir(parents=True, exist_ok=True)
    result_path = experiments / "production_launcher_handoff_result.json"
    spec_path = experiments / "observer_execution_spec.json"
    owner_request_path = (
        experiments / "production_research_cycle_request.json"
    )
    owner_policy_path = (
        experiments / "production_research_cycle_policy.json"
    )
    contract_policy_path = (
        experiments / "observer_execution_contract_policy.json"
    )

    if args.confirmation != CONFIRMATION:
        result = {
            "schema": "archon_production_launcher_handoff_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "reasons": ["CONFIRMATION_INVALID"],
            "prepared_at": now_iso(),
        }
        atomic_write_json(result_path, result)
        return 1

    paths = {
        "RESULTS_DIRECTORY_INVALID": Path(args.results_directory).resolve(),
        "ANALYZER_ENTRYPOINT_INVALID": Path(args.analyzer_entrypoint).resolve(),
        "OBSERVER_SCRIPT_INVALID": Path(args.observer_script).resolve(),
        "TELEMETRY_PARENT_INVALID": (
            Path(args.telemetry_database).resolve().parent
        ),
        "KNOWLEDGE_ATLAS_INVALID": (
            Path(args.knowledge_atlas_directory).resolve()
        ),
        "WORLD_ATLAS_INVALID": Path(args.world_atlas_directory).resolve(),
    }
    path_issues = []
    for reason, path in paths.items():
        if reason in {"ANALYZER_ENTRYPOINT_INVALID", "OBSERVER_SCRIPT_INVALID"}:
            valid = path.is_file()
        else:
            valid = path.is_dir()
        if not valid:
            path_issues.append(f"{reason}:{path}")
    if path_issues:
        atomic_write_json(result_path, {
            "schema": "archon_production_launcher_handoff_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "reasons": path_issues,
            "prepared_at": now_iso(),
        })
        return 1

    dispatch_row, selection, selection_issues = select_next_task(experiments)
    if selection_issues:
        atomic_write_json(result_path, {
            "schema": "archon_production_launcher_handoff_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "reasons": selection_issues,
            "prepared_at": now_iso(),
        })
        return 1
    if dispatch_row is None or selection is None:
        atomic_write_json(result_path, {
            "schema": "archon_production_launcher_handoff_result_v1",
            "version": VERSION,
            "status": "NO_ELIGIBLE_STAGE6_TASK",
            "reasons": [],
            "prepared_at": now_iso(),
        })
        return 0

    spec, spec_issues, context = build_spec(
        dispatch_row=dispatch_row,
        job=selection["job"],
        task=selection["task"],
        observer_script=Path(args.observer_script).resolve(),
        telemetry_database=Path(args.telemetry_database).resolve(),
        requested_by=args.requested_by,
        timeout_seconds=args.timeout_seconds,
        results_directory=Path(args.results_directory).resolve(),
        world_atlas_directory=Path(
            args.world_atlas_directory
        ).resolve(),
    )
    if spec_issues or spec is None:
        atomic_write_json(result_path, {
            "schema": "archon_production_launcher_handoff_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "job_id": context.get("job_id") or dispatch_row.get("job_id"),
            "task_id": context.get("task_id"),
            "reasons": spec_issues,
            "context": context,
            "prepared_at": now_iso(),
        })
        return 1

    job_will_complete = int(dispatch_row.get("pending_tasks") or 0) == 1
    cycle_id = (
        "CYCLE-"
        + canonical_hash({
            "job_id": context["job_id"],
            "task_id": context["task_id"],
            "job_file_hash": dispatch_row.get("job_file_hash"),
        })[:20].upper()
    )
    execution_request = {
        "schema": "archon_production_execution_cycle_request_v1",
        "run_cycle": True,
        "cycle_id": cycle_id,
        "results_directory": str(Path(args.results_directory).resolve()),
        "condition_id": context["condition_id"],
        "experiment_role": normalize_role(
            as_dict(selection["task"].get("runtime_spec")).get("role")
            or selection["task"].get("role")
        ),
        "replicate_index": int(
            as_dict(selection["task"].get("runtime_spec")).get(
                "replicate_index"
            )
            or 0
        ),
        "initial_state_mode": str(
            as_dict(selection["task"].get("runtime_spec")).get(
                "initial_state_mode"
            )
            or (
                "random_seed"
                if as_dict(selection["task"].get("runtime_spec")).get(
                    "seed"
                ) is not None
                else "canonical_seed"
            )
        ).lower(),
        "sample_every": 1,
        "pressure_every": 100,
        "autosave_every": 0,
        "cell": 8,
        "speed": 1000,
        "delay": 1,
        "timeout_seconds": args.timeout_seconds,
        "requested_at": now_iso(),
        "requested_by": args.requested_by,
        "confirmation": "RUN_PRODUCTION_EXECUTION_CYCLE_ONCE",
        "last_consumed_cycle_id": None,
    }
    owner_request = {
        "schema": "archon_production_research_cycle_request_v1",
        "run_cycle": True,
        "cycle_id": cycle_id,
        "execution_request": execution_request,
        "results_directory": str(Path(args.results_directory).resolve()),
        "analyzer_entrypoint": str(
            Path(args.analyzer_entrypoint).resolve()
        ),
        "knowledge_atlas_directory": str(
            Path(args.knowledge_atlas_directory).resolve()
        ),
        "world_atlas_directory": str(
            Path(args.world_atlas_directory).resolve()
        ),
        "analyzer_timeout_seconds": args.timeout_seconds,
        "force_profiles": True,
        "requested_at": now_iso(),
        "requested_by": args.requested_by,
        "confirmation": "RUN_FULL_PRODUCTION_RESEARCH_CYCLE",
        "last_consumed_cycle_id": None,
    }
    policy = as_dict(load_json(owner_policy_path, {}))
    policy.update({
        "schema": "archon_production_research_cycle_policy_v1",
        "version": "1.0",
        "research_cycle_enabled": True,
        "enable_stage_policies_automatically": True,
        "stop_on_first_failure": True,
        "require_browser_publication": True,
        "require_completed_cycle_record": job_will_complete,
        "default_analyzer_timeout_seconds": args.timeout_seconds,
        "maximum_analyzer_timeout_seconds": max(
            86400, args.timeout_seconds
        ),
        "updated_at": now_iso(),
    })
    contract_policy = as_dict(load_json(contract_policy_path, {}))
    contract_policy.update({
        "schema": "archon_observer_execution_contract_policy_v1",
        "version": "1.0",
        "contract_enabled": True,
        "supported_dimensions": [2],
        "supported_topologies": ["TORUS", "PLANE"],
        "supported_boundary_conditions": [
            "WRAP",
            "FIXED_DEAD",
            "FIXED_ALIVE",
            "REFLECTIVE",
        ],
        "supported_execution_modes": [
            "FRESH",
            "RESUME",
            "PERTURBATION",
        ],
        "supported_seed_modes": ["EXPLICIT", "DERIVED", "NONE"],
        "minimum_ticks": 1,
        "maximum_ticks": 10_000_000,
        "minimum_field_size": 4,
        "maximum_field_size": 16_384,
        "require_square_field": False,
        "require_explicit_topology": True,
        "require_explicit_boundary_condition": True,
        "require_output_directory": True,
        "require_telemetry_target": True,
        "require_rule_identity": True,
        "require_runtime_spec_hash": False,
        "require_resume_source_for_resume_mode": True,
        "require_perturbation_protocol_for_perturbation_mode": True,
        "required_artifact_roles": [
            "execution_receipt",
            "observer_stdout",
            "observer_stderr",
            "telemetry_reference",
            "run_summary",
        ],
        "success_criteria": {
            "allowed_exit_codes": [0],
            "require_process_completed": True,
            "require_telemetry_registered": True,
            "require_run_summary": True,
            "require_execution_receipt": True,
            "require_no_timeout": True,
        },
        "updated_at": now_iso(),
    })

    atomic_write_json(spec_path, spec)
    atomic_write_json(contract_policy_path, contract_policy)
    atomic_write_json(owner_policy_path, policy)
    atomic_write_json(owner_request_path, owner_request)
    result = {
        "schema": "archon_production_launcher_handoff_result_v1",
        "version": VERSION,
        "status": "READY",
        "cycle_id": cycle_id,
        "job_id": context["job_id"],
        "task_id": context["task_id"],
        "run_id": context["run_id"],
        "runtime_id": context["runtime_id"],
        "job_will_complete": job_will_complete,
        "observer_execution_spec_path": str(spec_path),
        "owner_request_path": str(owner_request_path),
        "owner_request_hash": canonical_hash(owner_request),
        "prepared_at": now_iso(),
    }
    atomic_write_json(result_path, result)
    print(f"{TITLE}: READY {cycle_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
