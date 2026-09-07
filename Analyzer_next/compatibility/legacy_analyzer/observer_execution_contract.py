#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VERSION = "1.0"
TITLE = "ARCHON Stage 7.1 Observer Execution Contract"


ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


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


def int_value(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return default


def bool_value(value: Any) -> bool:
    return value is True


def add_issue(
    issues: List[Dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    path: str,
    actual: Any = None,
    expected: Any = None,
) -> None:
    issues.append({
        "severity": severity,
        "code": code,
        "message": message,
        "path": path,
        "actual": actual,
        "expected": expected,
    })


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_observer_execution_contract_policy_v1",
        "version": VERSION,
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
        "supported_seed_modes": [
            "EXPLICIT",
            "DERIVED",
            "NONE",
        ],
        "minimum_ticks": 1,
        "maximum_ticks": 10_000_000,
        "minimum_field_size": 4,
        "maximum_field_size": 16_384,
        "require_square_field": True,
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
    }


def template_contract() -> Dict[str, Any]:
    return {
        "schema": "archon_observer_execution_spec_v1",
        "contract_version": VERSION,
        "identity": {
            "experiment_id": None,
            "job_id": None,
            "task_id": None,
            "run_id": None,
            "runtime_id": None,
            "plan_id": None,
        },
        "rule": {
            "rule_id": None,
            "rule_source": None,
            "rule_hash": None,
            "rule_format": None,
        },
        "conditions": {
            "dimension": 2,
            "field": {
                "width": None,
                "height": None,
            },
            "topology": None,
            "boundary_condition": None,
            "ticks": None,
            "seed": {
                "mode": "NONE",
                "value": None,
                "derivation": None,
            },
            "initial_state": {
                "mode": "GENERATED",
                "source_path": None,
                "source_hash": None,
            },
            "execution_mode": "FRESH",
            "resume": {
                "enabled": False,
                "source_run_id": None,
                "checkpoint_path": None,
                "checkpoint_hash": None,
                "resume_tick": None,
            },
            "perturbation": {
                "enabled": False,
                "protocol_id": None,
                "protocol_hash": None,
                "scheduled_events": [],
            },
        },
        "observer": {
            "adapter": "PRODUCTION_OBSERVER",
            "script_path": None,
            "script_hash": None,
            "python_executable": None,
            "extra_arguments": [],
            "timeout_seconds": None,
        },
        "outputs": {
            "output_directory": None,
            "telemetry_target": {
                "backend": "SQLITE",
                "database_path": None,
                "run_table": None,
                "run_id": None,
            },
            "artifacts": [
                {
                    "role": "execution_receipt",
                    "required": True,
                    "path": None,
                },
                {
                    "role": "observer_stdout",
                    "required": True,
                    "path": None,
                },
                {
                    "role": "observer_stderr",
                    "required": True,
                    "path": None,
                },
                {
                    "role": "telemetry_reference",
                    "required": True,
                    "path": None,
                },
                {
                    "role": "run_summary",
                    "required": True,
                    "path": None,
                },
            ],
        },
        "provenance": {
            "requested_by": None,
            "created_at": None,
            "source_action_id": None,
            "source_plan_id": None,
            "source_task_hash": None,
            "runtime_spec_hash": None,
        },
        "confirmation": None,
        "last_validated_contract_hash": None,
    }


def validate_id(
    issues: List[Dict[str, Any]],
    value: Any,
    path: str,
    required: bool = True,
) -> None:
    resolved = text(value)
    if not resolved:
        if required:
            add_issue(
                issues, "ERROR", "REQUIRED_ID_MISSING",
                "Required identifier is missing.",
                path, actual=value,
            )
        return
    if not ID_PATTERN.match(resolved):
        add_issue(
            issues, "ERROR", "ID_FORMAT_INVALID",
            "Identifier contains unsupported characters or length.",
            path, actual=resolved,
            expected=ID_PATTERN.pattern,
        )


def validate_sha256(
    issues: List[Dict[str, Any]],
    value: Any,
    path: str,
    required: bool = False,
) -> None:
    resolved = text(value)
    if not resolved:
        if required:
            add_issue(
                issues, "ERROR", "SHA256_MISSING",
                "Required SHA-256 value is missing.",
                path,
            )
        return
    if not SHA256_PATTERN.match(resolved):
        add_issue(
            issues, "ERROR", "SHA256_FORMAT_INVALID",
            "Hash must be a lowercase 64-character SHA-256 string.",
            path, actual=resolved,
        )


def validate_contract(
    spec: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []

    if policy.get("contract_enabled") is not True:
        add_issue(
            issues, "ERROR", "CONTRACT_DISABLED",
            "Observer execution contract validation is disabled.",
            "$.policy.contract_enabled",
            actual=policy.get("contract_enabled"),
            expected=True,
        )

    if spec.get("schema") != "archon_observer_execution_spec_v1":
        add_issue(
            issues, "ERROR", "SPEC_SCHEMA_INVALID",
            "Execution specification schema is invalid.",
            "$.schema",
            actual=spec.get("schema"),
            expected="archon_observer_execution_spec_v1",
        )

    identity = as_dict(spec.get("identity"))
    for key in ("experiment_id", "job_id", "task_id", "run_id", "runtime_id"):
        validate_id(issues, identity.get(key), f"$.identity.{key}")
    validate_id(
        issues,
        identity.get("plan_id"),
        "$.identity.plan_id",
        required=False,
    )

    rule = as_dict(spec.get("rule"))
    if policy.get("require_rule_identity") is True:
        validate_id(issues, rule.get("rule_id"), "$.rule.rule_id")
    if not text(rule.get("rule_source")):
        add_issue(
            issues, "ERROR", "RULE_SOURCE_MISSING",
            "Rule source is required.",
            "$.rule.rule_source",
        )
    validate_sha256(
        issues,
        rule.get("rule_hash"),
        "$.rule.rule_hash",
        required=False,
    )
    if not text(rule.get("rule_format")):
        add_issue(
            issues, "ERROR", "RULE_FORMAT_MISSING",
            "Rule format must be declared.",
            "$.rule.rule_format",
        )

    conditions = as_dict(spec.get("conditions"))
    dimension = int_value(conditions.get("dimension"))
    supported_dimensions = as_list(policy.get("supported_dimensions"))
    if dimension not in supported_dimensions:
        add_issue(
            issues, "ERROR", "DIMENSION_UNSUPPORTED",
            "Requested cellular automaton dimension is unsupported.",
            "$.conditions.dimension",
            actual=dimension,
            expected=supported_dimensions,
        )

    field = as_dict(conditions.get("field"))
    width = int_value(field.get("width"))
    height = int_value(field.get("height"))
    min_size = int_value(policy.get("minimum_field_size"), 4) or 4
    max_size = int_value(policy.get("maximum_field_size"), 16384) or 16384

    for name, value in (("width", width), ("height", height)):
        if value is None:
            add_issue(
                issues, "ERROR", "FIELD_SIZE_MISSING",
                "Field dimension is missing.",
                f"$.conditions.field.{name}",
            )
        elif value < min_size or value > max_size:
            add_issue(
                issues, "ERROR", "FIELD_SIZE_OUT_OF_RANGE",
                "Field dimension is outside policy bounds.",
                f"$.conditions.field.{name}",
                actual=value,
                expected={"minimum": min_size, "maximum": max_size},
            )

    if (
        policy.get("require_square_field") is True
        and width is not None
        and height is not None
        and width != height
    ):
        add_issue(
            issues, "ERROR", "FIELD_NOT_SQUARE",
            "Current policy requires a square field.",
            "$.conditions.field",
            actual={"width": width, "height": height},
        )

    topology = text(conditions.get("topology"))
    if policy.get("require_explicit_topology") is True and not topology:
        add_issue(
            issues, "ERROR", "TOPOLOGY_MISSING",
            "Topology must be explicit.",
            "$.conditions.topology",
        )
    elif topology and topology not in as_list(
        policy.get("supported_topologies")
    ):
        add_issue(
            issues, "ERROR", "TOPOLOGY_UNSUPPORTED",
            "Topology is not allowed by policy.",
            "$.conditions.topology",
            actual=topology,
            expected=policy.get("supported_topologies"),
        )

    boundary = text(conditions.get("boundary_condition"))
    if (
        policy.get("require_explicit_boundary_condition") is True
        and not boundary
    ):
        add_issue(
            issues, "ERROR", "BOUNDARY_CONDITION_MISSING",
            "Boundary condition must be explicit.",
            "$.conditions.boundary_condition",
        )
    elif boundary and boundary not in as_list(
        policy.get("supported_boundary_conditions")
    ):
        add_issue(
            issues, "ERROR", "BOUNDARY_CONDITION_UNSUPPORTED",
            "Boundary condition is not allowed by policy.",
            "$.conditions.boundary_condition",
            actual=boundary,
            expected=policy.get("supported_boundary_conditions"),
        )

    ticks = int_value(conditions.get("ticks"))
    min_ticks = int_value(policy.get("minimum_ticks"), 1) or 1
    max_ticks = int_value(policy.get("maximum_ticks"), 10_000_000) or 10_000_000
    if ticks is None:
        add_issue(
            issues, "ERROR", "TICKS_MISSING",
            "Requested tick count is missing.",
            "$.conditions.ticks",
        )
    elif ticks < min_ticks or ticks > max_ticks:
        add_issue(
            issues, "ERROR", "TICKS_OUT_OF_RANGE",
            "Requested tick count is outside policy bounds.",
            "$.conditions.ticks",
            actual=ticks,
            expected={"minimum": min_ticks, "maximum": max_ticks},
        )

    execution_mode = text(conditions.get("execution_mode"))
    if execution_mode not in as_list(
        policy.get("supported_execution_modes")
    ):
        add_issue(
            issues, "ERROR", "EXECUTION_MODE_UNSUPPORTED",
            "Execution mode is unsupported.",
            "$.conditions.execution_mode",
            actual=execution_mode,
            expected=policy.get("supported_execution_modes"),
        )

    seed = as_dict(conditions.get("seed"))
    seed_mode = text(seed.get("mode"))
    if seed_mode not in as_list(policy.get("supported_seed_modes")):
        add_issue(
            issues, "ERROR", "SEED_MODE_UNSUPPORTED",
            "Seed mode is unsupported.",
            "$.conditions.seed.mode",
            actual=seed_mode,
            expected=policy.get("supported_seed_modes"),
        )
    if seed_mode == "EXPLICIT" and int_value(seed.get("value")) is None:
        add_issue(
            issues, "ERROR", "EXPLICIT_SEED_MISSING",
            "Explicit seed mode requires an integer seed.",
            "$.conditions.seed.value",
        )
    if seed_mode == "DERIVED" and not text(seed.get("derivation")):
        add_issue(
            issues, "ERROR", "SEED_DERIVATION_MISSING",
            "Derived seed mode requires a derivation description.",
            "$.conditions.seed.derivation",
        )

    resume = as_dict(conditions.get("resume"))
    if execution_mode == "RESUME":
        if resume.get("enabled") is not True:
            add_issue(
                issues, "ERROR", "RESUME_NOT_ENABLED",
                "RESUME execution mode requires resume.enabled=true.",
                "$.conditions.resume.enabled",
            )
        if policy.get("require_resume_source_for_resume_mode") is True:
            if not text(resume.get("source_run_id")):
                add_issue(
                    issues, "ERROR", "RESUME_SOURCE_RUN_MISSING",
                    "Resume mode requires source_run_id.",
                    "$.conditions.resume.source_run_id",
                )
            if not text(resume.get("checkpoint_path")):
                add_issue(
                    issues, "ERROR", "RESUME_CHECKPOINT_MISSING",
                    "Resume mode requires checkpoint_path.",
                    "$.conditions.resume.checkpoint_path",
                )
            validate_sha256(
                issues,
                resume.get("checkpoint_hash"),
                "$.conditions.resume.checkpoint_hash",
                required=False,
            )
            if int_value(resume.get("resume_tick")) is None:
                add_issue(
                    issues, "ERROR", "RESUME_TICK_MISSING",
                    "Resume mode requires resume_tick.",
                    "$.conditions.resume.resume_tick",
                )
    elif resume.get("enabled") is True:
        add_issue(
            issues, "ERROR", "RESUME_MODE_CONFLICT",
            "resume.enabled=true conflicts with non-RESUME execution mode.",
            "$.conditions.resume.enabled",
            actual=True,
            expected=False,
        )

    perturbation = as_dict(conditions.get("perturbation"))
    if execution_mode == "PERTURBATION":
        if perturbation.get("enabled") is not True:
            add_issue(
                issues, "ERROR", "PERTURBATION_NOT_ENABLED",
                "PERTURBATION mode requires perturbation.enabled=true.",
                "$.conditions.perturbation.enabled",
            )
        if (
            policy.get(
                "require_perturbation_protocol_for_perturbation_mode"
            )
            is True
            and not text(perturbation.get("protocol_id"))
        ):
            add_issue(
                issues, "ERROR", "PERTURBATION_PROTOCOL_MISSING",
                "Perturbation mode requires protocol_id.",
                "$.conditions.perturbation.protocol_id",
            )
        validate_sha256(
            issues,
            perturbation.get("protocol_hash"),
            "$.conditions.perturbation.protocol_hash",
            required=False,
        )
    elif perturbation.get("enabled") is True:
        add_issue(
            issues, "ERROR", "PERTURBATION_MODE_CONFLICT",
            "perturbation.enabled=true conflicts with execution mode.",
            "$.conditions.perturbation.enabled",
            actual=True,
            expected=False,
        )

    observer = as_dict(spec.get("observer"))
    if not text(observer.get("script_path")):
        add_issue(
            issues, "ERROR", "OBSERVER_SCRIPT_MISSING",
            "Observer script path is required.",
            "$.observer.script_path",
        )
    validate_sha256(
        issues,
        observer.get("script_hash"),
        "$.observer.script_hash",
        required=False,
    )
    timeout = int_value(observer.get("timeout_seconds"))
    if timeout is not None and timeout <= 0:
        add_issue(
            issues, "ERROR", "OBSERVER_TIMEOUT_INVALID",
            "Observer timeout must be positive.",
            "$.observer.timeout_seconds",
            actual=timeout,
        )
    extra_arguments = observer.get("extra_arguments")
    if not isinstance(extra_arguments, list):
        add_issue(
            issues, "ERROR", "OBSERVER_EXTRA_ARGUMENTS_INVALID",
            "extra_arguments must be a list.",
            "$.observer.extra_arguments",
            actual=type(extra_arguments).__name__,
        )

    outputs = as_dict(spec.get("outputs"))
    output_directory = text(outputs.get("output_directory"))
    if (
        policy.get("require_output_directory") is True
        and not output_directory
    ):
        add_issue(
            issues, "ERROR", "OUTPUT_DIRECTORY_MISSING",
            "Output directory is required.",
            "$.outputs.output_directory",
        )

    telemetry = as_dict(outputs.get("telemetry_target"))
    if policy.get("require_telemetry_target") is True:
        if not text(telemetry.get("backend")):
            add_issue(
                issues, "ERROR", "TELEMETRY_BACKEND_MISSING",
                "Telemetry backend is required.",
                "$.outputs.telemetry_target.backend",
            )
        if not text(telemetry.get("database_path")):
            add_issue(
                issues, "ERROR", "TELEMETRY_DATABASE_MISSING",
                "Telemetry database path is required.",
                "$.outputs.telemetry_target.database_path",
            )
        if not text(telemetry.get("run_id")):
            add_issue(
                issues, "ERROR", "TELEMETRY_RUN_ID_MISSING",
                "Telemetry target run_id is required.",
                "$.outputs.telemetry_target.run_id",
            )
        elif telemetry.get("run_id") != identity.get("run_id"):
            add_issue(
                issues, "ERROR", "TELEMETRY_RUN_ID_MISMATCH",
                "Telemetry run_id must equal identity.run_id.",
                "$.outputs.telemetry_target.run_id",
                actual=telemetry.get("run_id"),
                expected=identity.get("run_id"),
            )

    artifacts = [
        item for item in as_list(outputs.get("artifacts"))
        if isinstance(item, dict)
    ]
    artifact_roles = [text(item.get("role")) for item in artifacts]
    required_roles = as_list(policy.get("required_artifact_roles"))
    for role in required_roles:
        if role not in artifact_roles:
            add_issue(
                issues, "ERROR", "REQUIRED_ARTIFACT_ROLE_MISSING",
                "Required artifact role is absent.",
                "$.outputs.artifacts",
                actual=artifact_roles,
                expected=role,
            )

    for index, artifact in enumerate(artifacts):
        role = text(artifact.get("role"))
        if not role:
            add_issue(
                issues, "ERROR", "ARTIFACT_ROLE_MISSING",
                "Artifact role is missing.",
                f"$.outputs.artifacts[{index}].role",
            )
        if artifact.get("required") is True and not text(
            artifact.get("path")
        ):
            add_issue(
                issues, "ERROR", "REQUIRED_ARTIFACT_PATH_MISSING",
                "Required artifact must declare a path.",
                f"$.outputs.artifacts[{index}].path",
                expected=role,
            )

    provenance = as_dict(spec.get("provenance"))
    if not text(provenance.get("requested_by")):
        add_issue(
            issues, "ERROR", "REQUESTED_BY_MISSING",
            "Provenance requested_by is required.",
            "$.provenance.requested_by",
        )
    if not text(provenance.get("created_at")):
        add_issue(
            issues, "ERROR", "CREATED_AT_MISSING",
            "Provenance created_at is required.",
            "$.provenance.created_at",
        )
    validate_sha256(
        issues,
        provenance.get("source_task_hash"),
        "$.provenance.source_task_hash",
        required=False,
    )
    validate_sha256(
        issues,
        provenance.get("runtime_spec_hash"),
        "$.provenance.runtime_spec_hash",
        required=policy.get("require_runtime_spec_hash") is True,
    )

    if spec.get("confirmation") != "VALIDATE_OBSERVER_EXECUTION_CONTRACT":
        add_issue(
            issues, "ERROR", "CONFIRMATION_INVALID",
            "Execution contract confirmation is invalid.",
            "$.confirmation",
            actual=spec.get("confirmation"),
            expected="VALIDATE_OBSERVER_EXECUTION_CONTRACT",
        )

    error_count = sum(
        1 for issue in issues if issue["severity"] == "ERROR"
    )
    warning_count = sum(
        1 for issue in issues if issue["severity"] == "WARNING"
    )

    normalized = {
        "schema": "archon_observer_execution_contract_v1",
        "contract_version": VERSION,
        "identity": identity,
        "rule": rule,
        "conditions": conditions,
        "observer": observer,
        "outputs": outputs,
        "provenance": provenance,
        "success_criteria": as_dict(policy.get("success_criteria")),
    }
    contract_hash = canonical_hash(normalized)

    return {
        "schema": "archon_observer_execution_contract_validation_v1",
        "version": VERSION,
        "status": "VALID" if error_count == 0 else "INVALID",
        "validated": error_count == 0,
        "validated_at": now_iso(),
        "contract_hash": contract_hash,
        "summary": {
            "errors": error_count,
            "warnings": warning_count,
            "issues": len(issues),
        },
        "normalized_contract": normalized,
        "issues": issues,
    }


def render_markdown(
    validation: Dict[str, Any],
    policy_path: Path,
    spec_path: Path,
) -> str:
    summary = validation["summary"]
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{validation.get('version')}**",
        f"- Status: **{validation.get('status')}**",
        f"- Contract hash: `{validation.get('contract_hash')}`",
        f"- Errors: **{summary.get('errors')}**",
        f"- Warnings: **{summary.get('warnings')}**",
        f"- Policy: `{policy_path}`",
        f"- Specification: `{spec_path}`",
        "",
        "## Contract layers",
        "",
        "1. Identity: experiment, job, task, run, and runtime identifiers.",
        "2. Rule: rule identity, source, format, and optional content hash.",
        "3. Conditions: field, topology, boundaries, ticks, seed, resume, and perturbation.",
        "4. Observer binding: executable path, script hash, timeout, and arguments.",
        "5. Evidence: output directory, telemetry target, artifacts, and success criteria.",
        "",
        "## Issues",
        "",
    ]
    if not validation.get("issues"):
        lines.append("- No contract issues.")
    else:
        for issue in validation["issues"]:
            lines.append(
                f"- **{issue['severity']}** `{issue['code']}` "
                f"at `{issue['path']}`: {issue['message']}"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--spec", default=None)
    args = parser.parse_args()

    analysis = Path(args.analysis_root).resolve()
    experiments = analysis / "Experiments"
    experiments.mkdir(parents=True, exist_ok=True)

    policy_path = (
        experiments / "observer_execution_contract_policy.json"
    )
    spec_path = (
        Path(args.spec).resolve()
        if args.spec
        else experiments / "observer_execution_spec.json"
    )
    validation_path = (
        experiments / "observer_execution_contract_validation.json"
    )
    contract_path = (
        experiments / "observer_execution_contract.json"
    )
    markdown_path = (
        experiments / "observer_execution_contract.md"
    )

    policy = load_json(policy_path, {})
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    spec = load_json(spec_path, {})
    if not spec:
        spec = template_contract()
        atomic_write_json(spec_path, spec)

    validation = validate_contract(spec, policy)
    atomic_write_json(validation_path, validation)

    if validation.get("validated") is True:
        contract = {
            **validation["normalized_contract"],
            "contract_hash": validation["contract_hash"],
            "validated_at": validation["validated_at"],
            "validation_path": str(validation_path),
        }
        atomic_write_json(contract_path, contract)

        spec["last_validated_contract_hash"] = validation[
            "contract_hash"
        ]
        atomic_write_json(spec_path, spec)

    markdown_path.write_text(
        render_markdown(validation, policy_path, spec_path),
        encoding="utf-8",
    )

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Version:       {VERSION}")
    print(f"Status:        {validation.get('status')}")
    print(
        f"Issues:        {validation['summary']['errors']} errors | "
        f"{validation['summary']['warnings']} warnings"
    )
    print(f"Contract hash: {validation.get('contract_hash')}")
    print(f"Policy:        {policy_path}")
    print(f"Spec:          {spec_path}")
    print(f"Validation:    {validation_path}")
    print(f"Contract:      {contract_path}")
    print(f"Markdown:      {markdown_path}")
    print("=" * 72)

    return 0 if validation.get("validated") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
