#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VERSION = "1.0"
TITLE = "ARCHON Stage 7.2 Production Observer Binding"


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


def file_sha256(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
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


def int_value(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return default


def add_reason(
    reasons: List[Dict[str, Any]],
    code: str,
    message: str,
    path: str,
    actual: Any = None,
    expected: Any = None,
) -> None:
    reasons.append({
        "code": code,
        "message": message,
        "path": path,
        "actual": actual,
        "expected": expected,
    })


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_production_observer_binding_policy_v1",
        "version": VERSION,
        "binding_enabled": False,
        "require_validated_contract": True,
        "require_contract_hash_match": True,
        "require_observer_script_exists": True,
        "require_observer_script_hash_match": True,
        "require_python_executable_exists": True,
        "require_absolute_paths": True,
        "allow_extra_arguments": True,
        "allow_environment": False,
        "allowed_environment_keys": [],
        "supported_contract_schemas": [
            "archon_observer_execution_contract_v1",
        ],
        "supported_observer_adapters": [
            "PRODUCTION_OBSERVER",
        ],
        "argument_mapping": {
            "rule_source": "--rule-source",
            "rule_id": "--rule-id",
            "run_id": "--run-id",
            "experiment_id": "--experiment-id",
            "job_id": "--job-id",
            "task_id": "--task-id",
            "runtime_id": "--runtime-id",
            "field_width": "--field-width",
            "field_height": "--field-height",
            "topology": "--topology",
            "boundary_condition": "--boundary-condition",
            "ticks": "--ticks",
            "seed": "--seed",
            "execution_mode": "--execution-mode",
            "output_directory": "--output-directory",
            "telemetry_database": "--telemetry-database",
            "telemetry_backend": "--telemetry-backend",
            "telemetry_run_id": "--telemetry-run-id",
            "resume_run_id": "--resume-run-id",
            "checkpoint_path": "--checkpoint-path",
            "resume_tick": "--resume-tick",
            "perturbation_protocol_id": "--perturbation-protocol-id",
        },
        "updated_at": now_iso(),
    }


def default_request() -> Dict[str, Any]:
    return {
        "schema": "archon_production_observer_binding_request_v1",
        "bind": False,
        "binding_id": None,
        "expected_contract_hash": None,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_binding_id": None,
        "instructions": {
            "required_confirmation": "BIND_VALIDATED_OBSERVER_CONTRACT",
            "binding_does_not_execute_observer": True,
        },
    }


def append_arg(command: List[str], flag: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        if value:
            command.append(flag)
        return
    command.extend([flag, str(value)])


def verify_contract_hash(contract: Dict[str, Any]) -> str:
    normalized = {
        key: contract.get(key)
        for key in (
            "schema",
            "contract_version",
            "identity",
            "rule",
            "conditions",
            "observer",
            "outputs",
            "provenance",
            "success_criteria",
        )
    }
    return canonical_hash(normalized)


def build_binding(
    contract: Dict[str, Any],
    policy: Dict[str, Any],
    request: Dict[str, Any],
) -> Dict[str, Any]:
    reasons: List[Dict[str, Any]] = []

    if request.get("bind") is not True:
        return {
            "schema": "archon_production_observer_binding_result_v1",
            "version": VERSION,
            "status": "NO_BINDING_REQUEST",
            "bound": False,
            "binding_id": None,
            "reasons": [],
        }

    if policy.get("binding_enabled") is not True:
        add_reason(
            reasons,
            "BINDING_DISABLED",
            "Production Observer binding is disabled by policy.",
            "$.policy.binding_enabled",
            actual=policy.get("binding_enabled"),
            expected=True,
        )

    if request.get("confirmation") != "BIND_VALIDATED_OBSERVER_CONTRACT":
        add_reason(
            reasons,
            "CONFIRMATION_INVALID",
            "Binding confirmation is invalid.",
            "$.request.confirmation",
            actual=request.get("confirmation"),
            expected="BIND_VALIDATED_OBSERVER_CONTRACT",
        )

    binding_id = text(request.get("binding_id"))
    if not binding_id:
        add_reason(
            reasons,
            "BINDING_ID_MISSING",
            "binding_id is required.",
            "$.request.binding_id",
        )

    if contract.get("schema") not in as_list(
        policy.get("supported_contract_schemas")
    ):
        add_reason(
            reasons,
            "CONTRACT_SCHEMA_UNSUPPORTED",
            "Observer execution contract schema is unsupported.",
            "$.contract.schema",
            actual=contract.get("schema"),
            expected=policy.get("supported_contract_schemas"),
        )

    stored_contract_hash = text(contract.get("contract_hash"))
    computed_contract_hash = verify_contract_hash(contract)

    if policy.get("require_validated_contract") is True:
        if not stored_contract_hash:
            add_reason(
                reasons,
                "CONTRACT_HASH_MISSING",
                "Validated contract does not contain contract_hash.",
                "$.contract.contract_hash",
            )
        if not text(contract.get("validated_at")):
            add_reason(
                reasons,
                "CONTRACT_VALIDATION_TIMESTAMP_MISSING",
                "Validated contract does not contain validated_at.",
                "$.contract.validated_at",
            )

    if (
        policy.get("require_contract_hash_match") is True
        and stored_contract_hash
        and stored_contract_hash != computed_contract_hash
    ):
        add_reason(
            reasons,
            "CONTRACT_HASH_MISMATCH",
            "Stored contract_hash differs from normalized contract content.",
            "$.contract.contract_hash",
            actual=stored_contract_hash,
            expected=computed_contract_hash,
        )

    expected_contract_hash = text(request.get("expected_contract_hash"))
    if expected_contract_hash != stored_contract_hash:
        add_reason(
            reasons,
            "EXPECTED_CONTRACT_HASH_MISMATCH",
            "Binding request does not target the current contract hash.",
            "$.request.expected_contract_hash",
            actual=expected_contract_hash,
            expected=stored_contract_hash,
        )

    identity = as_dict(contract.get("identity"))
    rule = as_dict(contract.get("rule"))
    conditions = as_dict(contract.get("conditions"))
    observer = as_dict(contract.get("observer"))
    outputs = as_dict(contract.get("outputs"))
    field = as_dict(conditions.get("field"))
    seed = as_dict(conditions.get("seed"))
    resume = as_dict(conditions.get("resume"))
    perturbation = as_dict(conditions.get("perturbation"))
    telemetry = as_dict(outputs.get("telemetry_target"))

    if observer.get("adapter") not in as_list(
        policy.get("supported_observer_adapters")
    ):
        add_reason(
            reasons,
            "OBSERVER_ADAPTER_UNSUPPORTED",
            "Observer adapter is unsupported.",
            "$.contract.observer.adapter",
            actual=observer.get("adapter"),
            expected=policy.get("supported_observer_adapters"),
        )

    script_path_value = text(observer.get("script_path"))
    script_path = Path(script_path_value).expanduser() if script_path_value else None

    if script_path and not script_path.is_absolute():
        script_path = script_path.resolve()

    if policy.get("require_observer_script_exists") is True:
        if script_path is None or not script_path.exists():
            add_reason(
                reasons,
                "OBSERVER_SCRIPT_MISSING",
                "Observer script does not exist.",
                "$.contract.observer.script_path",
                actual=script_path_value,
            )

    actual_script_hash = file_sha256(script_path) if script_path else None
    expected_script_hash = text(observer.get("script_hash"))
    if (
        policy.get("require_observer_script_hash_match") is True
        and expected_script_hash != actual_script_hash
    ):
        add_reason(
            reasons,
            "OBSERVER_SCRIPT_HASH_MISMATCH",
            "Observer script hash does not match contract.",
            "$.contract.observer.script_hash",
            actual=actual_script_hash,
            expected=expected_script_hash,
        )

    python_value = text(observer.get("python_executable")) or sys.executable
    python_path = Path(python_value).expanduser()
    if not python_path.is_absolute():
        resolved = shutil_which(python_value)
        python_path = Path(resolved) if resolved else python_path.resolve()

    if (
        policy.get("require_python_executable_exists") is True
        and not python_path.exists()
    ):
        add_reason(
            reasons,
            "PYTHON_EXECUTABLE_MISSING",
            "Configured Python executable does not exist.",
            "$.contract.observer.python_executable",
            actual=str(python_path),
        )

    absolute_path_fields = {
        "$.contract.observer.script_path": script_path,
        "$.contract.outputs.output_directory": (
            Path(str(outputs.get("output_directory"))).expanduser()
            if text(outputs.get("output_directory")) else None
        ),
        "$.contract.outputs.telemetry_target.database_path": (
            Path(str(telemetry.get("database_path"))).expanduser()
            if text(telemetry.get("database_path")) else None
        ),
    }
    if policy.get("require_absolute_paths") is True:
        for path_name, path_value in absolute_path_fields.items():
            if path_value is None or not path_value.is_absolute():
                add_reason(
                    reasons,
                    "ABSOLUTE_PATH_REQUIRED",
                    "Binding requires an absolute path.",
                    path_name,
                    actual=str(path_value) if path_value else None,
                )

    extra_arguments = observer.get("extra_arguments")
    if not isinstance(extra_arguments, list):
        add_reason(
            reasons,
            "EXTRA_ARGUMENTS_INVALID",
            "Observer extra_arguments must be a list.",
            "$.contract.observer.extra_arguments",
            actual=type(extra_arguments).__name__,
        )
        extra_arguments = []

    if extra_arguments and policy.get("allow_extra_arguments") is not True:
        add_reason(
            reasons,
            "EXTRA_ARGUMENTS_FORBIDDEN",
            "Policy forbids Observer extra arguments.",
            "$.contract.observer.extra_arguments",
            actual=extra_arguments,
        )

    if reasons:
        return {
            "schema": "archon_production_observer_binding_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "bound": False,
            "binding_id": binding_id,
            "contract_hash": stored_contract_hash,
            "reasons": reasons,
        }

    mapping = as_dict(policy.get("argument_mapping"))
    command: List[str] = [str(python_path), str(script_path)]

    values = {
        "rule_source": rule.get("rule_source"),
        "rule_id": rule.get("rule_id"),
        "run_id": identity.get("run_id"),
        "experiment_id": identity.get("experiment_id"),
        "job_id": identity.get("job_id"),
        "task_id": identity.get("task_id"),
        "runtime_id": identity.get("runtime_id"),
        "field_width": field.get("width"),
        "field_height": field.get("height"),
        "topology": conditions.get("topology"),
        "boundary_condition": conditions.get("boundary_condition"),
        "ticks": conditions.get("ticks"),
        "execution_mode": conditions.get("execution_mode"),
        "output_directory": outputs.get("output_directory"),
        "telemetry_database": telemetry.get("database_path"),
        "telemetry_backend": telemetry.get("backend"),
        "telemetry_run_id": telemetry.get("run_id"),
    }

    if seed.get("mode") == "EXPLICIT":
        values["seed"] = seed.get("value")

    if conditions.get("execution_mode") == "RESUME":
        values.update({
            "resume_run_id": resume.get("source_run_id"),
            "checkpoint_path": resume.get("checkpoint_path"),
            "resume_tick": resume.get("resume_tick"),
        })

    if conditions.get("execution_mode") == "PERTURBATION":
        values["perturbation_protocol_id"] = perturbation.get(
            "protocol_id"
        )

    for key, value in values.items():
        flag = text(mapping.get(key))
        if flag:
            append_arg(command, flag, value)

    command.extend(str(item) for item in extra_arguments)

    environment: Dict[str, str] = {}
    environment_hash = canonical_hash(environment)
    command_hash = canonical_hash(command)

    manifest_core = {
        "schema": "archon_production_observer_execution_manifest_v1",
        "version": VERSION,
        "binding_id": binding_id,
        "contract_hash": stored_contract_hash,
        "identity": identity,
        "observer": {
            "adapter": observer.get("adapter"),
            "python_executable": str(python_path),
            "script_path": str(script_path),
            "script_hash": actual_script_hash,
            "timeout_seconds": observer.get("timeout_seconds"),
        },
        "command": command,
        "command_hash": command_hash,
        "command_preview": shlex.join(command),
        "environment": environment,
        "environment_hash": environment_hash,
        "working_directory": str(script_path.parent),
        "outputs": outputs,
        "success_criteria": as_dict(contract.get("success_criteria")),
        "execution_permitted": False,
        "binding_does_not_execute_observer": True,
    }
    manifest_hash = canonical_hash(manifest_core)

    return {
        "schema": "archon_production_observer_binding_result_v1",
        "version": VERSION,
        "status": "BOUND",
        "bound": True,
        "binding_id": binding_id,
        "contract_hash": stored_contract_hash,
        "manifest_hash": manifest_hash,
        "command_hash": command_hash,
        "observer_script_hash": actual_script_hash,
        "manifest": {
            **manifest_core,
            "manifest_hash": manifest_hash,
            "bound_at": now_iso(),
        },
        "reasons": [],
    }


def shutil_which(command: str) -> Optional[str]:
    paths = os.environ.get("PATH", "").split(os.pathsep)
    for directory in paths:
        candidate = Path(directory) / command
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{result.get('version')}**",
        f"- Status: **{result.get('status')}**",
        f"- Binding ID: `{result.get('binding_id') or '-'}`",
        f"- Contract hash: `{result.get('contract_hash') or '-'}`",
        f"- Manifest hash: `{result.get('manifest_hash') or '-'}`",
        f"- Command hash: `{result.get('command_hash') or '-'}`",
        "",
        "## Safety boundary",
        "",
        "- The binding validates and materializes an execution command.",
        "- The binding does not invoke Observer.",
        "- The generated manifest sets `execution_permitted` to `false`.",
        "",
    ]
    manifest = as_dict(result.get("manifest"))
    if manifest:
        lines.extend([
            "## Command preview",
            "",
            "```text",
            str(manifest.get("command_preview") or ""),
            "```",
            "",
        ])
    if result.get("reasons"):
        lines.extend(["## Refusal reasons", ""])
        for reason in result["reasons"]:
            lines.append(
                f"- `{reason.get('code')}` at `{reason.get('path')}`: "
                f"{reason.get('message')}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--contract", default=None)
    parser.add_argument("--request", default=None)
    args = parser.parse_args()

    analysis = Path(args.analysis_root).resolve()
    experiments = analysis / "Experiments"
    experiments.mkdir(parents=True, exist_ok=True)

    contract_path = (
        Path(args.contract).resolve()
        if args.contract
        else experiments / "observer_execution_contract.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments / "production_observer_binding_request.json"
    )
    policy_path = (
        experiments / "production_observer_binding_policy.json"
    )
    result_path = (
        experiments / "production_observer_binding_result.json"
    )
    manifest_path = (
        experiments / "production_observer_execution_manifest.json"
    )
    registry_path = (
        experiments / "production_observer_binding_registry.json"
    )
    receipt_dir = (
        experiments / "ProductionObserverBindingReceipts"
    )
    markdown_path = (
        experiments / "production_observer_binding.md"
    )

    policy = load_json(policy_path, {})
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    request = load_json(request_path, {})
    if not request:
        request = default_request()
        atomic_write_json(request_path, request)

    contract = load_json(contract_path, {})
    result = build_binding(contract, policy, request)

    registry = load_json(registry_path, {})
    bindings = [
        item for item in as_list(registry.get("bindings"))
        if isinstance(item, dict)
    ]

    if result.get("status") == "BOUND":
        manifest = as_dict(result.get("manifest"))
        atomic_write_json(manifest_path, manifest)

        binding_id = str(result.get("binding_id"))
        receipt_path = receipt_dir / f"{binding_id}.json"
        receipt = {
            "schema": "archon_production_observer_binding_receipt_v1",
            "version": VERSION,
            "status": "BOUND",
            "binding_id": binding_id,
            "contract_hash": result.get("contract_hash"),
            "manifest_hash": result.get("manifest_hash"),
            "command_hash": result.get("command_hash"),
            "observer_script_hash": result.get(
                "observer_script_hash"
            ),
            "manifest_path": str(manifest_path),
            "bound_at": manifest.get("bound_at"),
            "execution_permitted": False,
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        atomic_write_json(receipt_path, receipt)

        bindings.append({
            "binding_id": binding_id,
            "contract_hash": result.get("contract_hash"),
            "manifest_hash": result.get("manifest_hash"),
            "command_hash": result.get("command_hash"),
            "receipt_path": str(receipt_path),
            "manifest_path": str(manifest_path),
            "status": "BOUND",
            "bound_at": manifest.get("bound_at"),
        })

        unique = {
            str(item.get("binding_id")): item
            for item in bindings if item.get("binding_id")
        }
        ordered = sorted(
            unique.values(),
            key=lambda item: str(item.get("binding_id")),
        )
        registry = {
            "schema": "archon_production_observer_binding_registry_v1",
            "version": VERSION,
            "updated_at": now_iso(),
            "binding_count": len(ordered),
            "bindings": ordered,
        }
        registry["content_hash"] = canonical_hash(ordered)
        atomic_write_json(registry_path, registry)

        request = {
            "schema": "archon_production_observer_binding_request_v1",
            "bind": False,
            "binding_id": None,
            "expected_contract_hash": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "last_consumed_binding_id": binding_id,
        }
        atomic_write_json(request_path, request)

        result["receipt_path"] = str(receipt_path)
        result["manifest_path"] = str(manifest_path)

    atomic_write_json(result_path, result)
    markdown_path.write_text(
        render_markdown(result),
        encoding="utf-8",
    )

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Version:       {VERSION}")
    print(f"Status:        {result.get('status')}")
    print(f"Binding ID:    {result.get('binding_id') or '-'}")
    print(f"Contract hash: {result.get('contract_hash') or '-'}")
    print(f"Manifest hash: {result.get('manifest_hash') or '-'}")
    print(f"Command hash:  {result.get('command_hash') or '-'}")
    print(f"Policy:        {policy_path}")
    print(f"Request:       {request_path}")
    print(f"Result:        {result_path}")
    print(f"Manifest:      {manifest_path}")
    print(f"Registry:      {registry_path}")
    print(f"Markdown:      {markdown_path}")
    print("=" * 72)

    return 0 if result.get("status") not in {"REFUSED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
