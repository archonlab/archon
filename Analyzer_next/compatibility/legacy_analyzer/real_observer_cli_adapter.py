#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VERSION = "1.0"
TITLE = "ARCHON Stage 7.3.2 Real Observer CLI Adapter"


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


def append_value(command: List[str], flag: str, value: Any) -> None:
    if value is not None and str(value) != "":
        command.extend([flag, str(value)])


def append_switch(command: List[str], flag: str, enabled: bool) -> None:
    if enabled:
        command.append(flag)


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_real_observer_cli_adapter_policy_v1",
        "version": VERSION,
        "adapter_enabled": False,
        "require_authorized": True,
        "require_unconsumed": True,
        "require_single_use": True,
        "require_execution_permitted": True,
        "require_authorization_hash_match": True,
        "require_observer_script_exists": True,
        "require_observer_script_hash_match": True,
        "require_results_directory_exists": True,
        "require_absolute_output_paths": True,
        "force_exit_at_max_ticks": True,
        "force_csv_outputs": True,
        "force_passport": True,
        "force_log": True,
        "force_sqlite": True,
        "supported_topologies": ["torus", "bounded"],
        "supported_boundary_modes": [
            "wrap",
            "fixed_dead",
            "fixed_alive",
            "reflective",
        ],
        "supported_initial_state_modes": [
            "canonical_seed",
            "random_seed",
            "saved_state",
        ],
        "updated_at": now_iso(),
    }


def default_request() -> Dict[str, Any]:
    return {
        "schema": "archon_real_observer_cli_adapter_request_v1",
        "adapt": False,
        "adapter_id": None,
        "expected_authorization_hash": None,
        "results_directory": None,
        "condition_id": None,
        "experiment_role": "baseline",
        "replicate_index": 0,
        "initial_state_mode": "canonical_seed",
        "sample_every": 1,
        "pressure_every": 100,
        "autosave_every": 0,
        "cell": 8,
        "speed": 1000,
        "delay": 1,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_adapter_id": None,
    }


def authorization_core(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: payload.get(key)
        for key in (
            "schema",
            "version",
            "status",
            "authorization_id",
            "binding_id",
            "manifest_hash",
            "command_hash",
            "contract_hash",
            "identity",
            "observer_script_hash",
            "command",
            "working_directory",
            "environment_hash",
            "outputs",
            "success_criteria",
            "issued_at",
            "ttl_seconds",
            "single_use",
            "consumed",
            "execution_permitted",
            "authorization_does_not_execute_observer",
        )
    }


def build_native_manifest(
    authorization: Dict[str, Any],
    policy: Dict[str, Any],
    request: Dict[str, Any],
) -> Dict[str, Any]:
    reasons: List[Dict[str, Any]] = []

    def refuse(code: str, message: str, path: str, actual: Any = None) -> None:
        reasons.append({
            "code": code,
            "message": message,
            "path": path,
            "actual": actual,
        })

    if request.get("adapt") is not True:
        return {
            "schema": "archon_real_observer_cli_adapter_result_v1",
            "version": VERSION,
            "status": "NO_ADAPTER_REQUEST",
            "adapted": False,
            "reasons": [],
        }

    if policy.get("adapter_enabled") is not True:
        refuse(
            "ADAPTER_DISABLED",
            "Real Observer CLI adapter is disabled by policy.",
            "$.policy.adapter_enabled",
            policy.get("adapter_enabled"),
        )

    if request.get("confirmation") != "ADAPT_AUTHORIZED_OBSERVER_LAUNCH":
        refuse(
            "CONFIRMATION_INVALID",
            "Adapter confirmation is invalid.",
            "$.request.confirmation",
            request.get("confirmation"),
        )

    adapter_id = text(request.get("adapter_id"))
    if not adapter_id:
        refuse(
            "ADAPTER_ID_MISSING",
            "adapter_id is required.",
            "$.request.adapter_id",
        )

    if (
        policy.get("require_authorized") is True
        and authorization.get("status") != "AUTHORIZED"
    ):
        refuse(
            "AUTHORIZATION_STATUS_INVALID",
            "Launch authorization must have AUTHORIZED status.",
            "$.authorization.status",
            authorization.get("status"),
        )

    if (
        policy.get("require_unconsumed") is True
        and authorization.get("consumed") is not False
    ):
        refuse(
            "AUTHORIZATION_ALREADY_CONSUMED",
            "Launch authorization has already been consumed.",
            "$.authorization.consumed",
            authorization.get("consumed"),
        )

    if (
        policy.get("require_single_use") is True
        and authorization.get("single_use") is not True
    ):
        refuse(
            "AUTHORIZATION_NOT_SINGLE_USE",
            "Launch authorization must be single-use.",
            "$.authorization.single_use",
            authorization.get("single_use"),
        )

    if (
        policy.get("require_execution_permitted") is True
        and authorization.get("execution_permitted") is not True
    ):
        refuse(
            "EXECUTION_NOT_PERMITTED",
            "Launch authorization does not permit execution.",
            "$.authorization.execution_permitted",
            authorization.get("execution_permitted"),
        )

    stored_auth_hash = text(authorization.get("authorization_hash"))
    computed_auth_hash = canonical_hash(authorization_core(authorization))
    if (
        policy.get("require_authorization_hash_match") is True
        and stored_auth_hash != computed_auth_hash
    ):
        refuse(
            "AUTHORIZATION_HASH_MISMATCH",
            "Authorization hash differs from authorization content.",
            "$.authorization.authorization_hash",
            stored_auth_hash,
        )

    if text(request.get("expected_authorization_hash")) != stored_auth_hash:
        refuse(
            "EXPECTED_AUTHORIZATION_HASH_MISMATCH",
            "Adapter request targets another authorization hash.",
            "$.request.expected_authorization_hash",
            request.get("expected_authorization_hash"),
        )

    old_command = as_list(authorization.get("command"))
    python_executable = text(old_command[0]) if len(old_command) > 0 else None
    observer_script_value = text(old_command[1]) if len(old_command) > 1 else None

    observer_script = (
        Path(observer_script_value).expanduser()
        if observer_script_value else None
    )
    if (
        policy.get("require_observer_script_exists") is True
        and (observer_script is None or not observer_script.is_file())
    ):
        refuse(
            "OBSERVER_SCRIPT_MISSING",
            "Production Observer script does not exist.",
            "$.authorization.command[1]",
            observer_script_value,
        )

    actual_script_hash = (
        file_sha256(observer_script) if observer_script is not None else None
    )
    expected_script_hash = text(authorization.get("observer_script_hash"))
    if (
        policy.get("require_observer_script_hash_match") is True
        and actual_script_hash != expected_script_hash
    ):
        refuse(
            "OBSERVER_SCRIPT_HASH_MISMATCH",
            "Production Observer script changed after authorization.",
            "$.authorization.observer_script_hash",
            actual_script_hash,
        )

    results_value = text(request.get("results_directory"))
    results_dir = Path(results_value).expanduser() if results_value else None
    if results_dir is not None and not results_dir.is_absolute():
        results_dir = results_dir.resolve()

    if (
        policy.get("require_results_directory_exists") is True
        and (results_dir is None or not results_dir.is_dir())
    ):
        refuse(
            "RESULTS_DIRECTORY_MISSING",
            "Universe Search results directory does not exist.",
            "$.request.results_directory",
            str(results_dir) if results_dir else None,
        )

    identity = as_dict(authorization.get("identity"))
    outputs = as_dict(authorization.get("outputs"))
    telemetry = as_dict(outputs.get("telemetry_target"))

    output_value = text(outputs.get("output_directory"))
    output_dir = Path(output_value).expanduser() if output_value else None
    telemetry_value = text(telemetry.get("database_path"))
    telemetry_path = (
        Path(telemetry_value).expanduser() if telemetry_value else None
    )

    if policy.get("require_absolute_output_paths") is True:
        for path_name, path_value in (
            ("$.authorization.outputs.output_directory", output_dir),
            (
                "$.authorization.outputs.telemetry_target.database_path",
                telemetry_path,
            ),
        ):
            if path_value is None or not path_value.is_absolute():
                refuse(
                    "ABSOLUTE_OUTPUT_PATH_REQUIRED",
                    "Observer outputs require absolute paths.",
                    path_name,
                    str(path_value) if path_value else None,
                )

    generic_command = as_list(authorization.get("command"))
    generic_flags: Dict[str, str] = {}
    index = 2
    while index < len(generic_command):
        item = str(generic_command[index])
        if item.startswith("--") and index + 1 < len(generic_command):
            nxt = str(generic_command[index + 1])
            if not nxt.startswith("--"):
                generic_flags[item] = nxt
                index += 2
                continue
        index += 1

    rule_id = (
        generic_flags.get("--rule-id")
        or text(identity.get("rule_id"))
    )
    if not rule_id:
        refuse(
            "RULE_ID_MISSING",
            "Rule selector cannot be resolved from authorization command.",
            "$.authorization.command",
            generic_command,
        )

    ticks = int_value(generic_flags.get("--ticks"))
    field_width = int_value(generic_flags.get("--field-width"))
    field_height = int_value(generic_flags.get("--field-height"))
    seed = int_value(generic_flags.get("--seed"))

    topology_map = {
        "TORUS": "torus",
        "PLANE": "bounded",
        "torus": "torus",
        "bounded": "bounded",
    }
    boundary_map = {
        "WRAP": "wrap",
        "FIXED_DEAD": "fixed_dead",
        "FIXED_ALIVE": "fixed_alive",
        "REFLECTIVE": "reflective",
        "wrap": "wrap",
        "fixed_dead": "fixed_dead",
        "fixed_alive": "fixed_alive",
        "reflective": "reflective",
    }
    topology = topology_map.get(generic_flags.get("--topology", ""))
    boundary = boundary_map.get(
        generic_flags.get("--boundary-condition", "")
    )

    if topology not in as_list(policy.get("supported_topologies")):
        refuse(
            "TOPOLOGY_MAPPING_FAILED",
            "Contract topology cannot be mapped to Observer topology.",
            "$.authorization.command",
            generic_flags.get("--topology"),
        )

    if boundary not in as_list(policy.get("supported_boundary_modes")):
        refuse(
            "BOUNDARY_MAPPING_FAILED",
            "Contract boundary cannot be mapped to Observer boundary mode.",
            "$.authorization.command",
            generic_flags.get("--boundary-condition"),
        )

    initial_state_mode = text(request.get("initial_state_mode"))
    if initial_state_mode not in as_list(
        policy.get("supported_initial_state_modes")
    ):
        refuse(
            "INITIAL_STATE_MODE_UNSUPPORTED",
            "Initial state mode is unsupported by Observer.",
            "$.request.initial_state_mode",
            initial_state_mode,
        )

    if reasons:
        return {
            "schema": "archon_real_observer_cli_adapter_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "adapted": False,
            "adapter_id": adapter_id,
            "authorization_hash": stored_auth_hash,
            "reasons": reasons,
        }

    command: List[str] = [
        str(python_executable or sys.executable),
        str(observer_script),
        str(results_dir),
        str(rule_id),
    ]

    rule_source = generic_flags.get("--rule-source")
    if rule_source:
        rule_path = Path(rule_source).expanduser()
        if rule_path.is_absolute() and rule_path.is_file():
            append_value(command, "--rule-file", rule_path)

    mutation_manifest = generic_flags.get("--mutation-manifest")
    mutation_rule_hash = generic_flags.get("--mutation-rule-sha256")
    mutation_manifest_hash = generic_flags.get(
        "--mutation-manifest-sha256"
    )
    perturbation_protocol_id = generic_flags.get(
        "--perturbation-protocol-id"
    )
    if perturbation_protocol_id:
        mutation_manifest_path = (
            Path(mutation_manifest).expanduser()
            if mutation_manifest else None
        )
        rule_path = (
            Path(rule_source).expanduser() if rule_source else None
        )
        mutation_failures = []
        if (
            mutation_manifest_path is None
            or not mutation_manifest_path.is_absolute()
            or not mutation_manifest_path.is_file()
        ):
            mutation_failures.append("MUTATION_MANIFEST_INVALID")
        if (
            rule_path is None
            or not rule_path.is_absolute()
            or not rule_path.is_file()
        ):
            mutation_failures.append("MUTATION_RULE_FILE_INVALID")
        if (
            rule_path is not None
            and rule_path.is_file()
            and file_sha256(rule_path) != mutation_rule_hash
        ):
            mutation_failures.append("MUTATION_RULE_HASH_MISMATCH")
        if (
            mutation_manifest_path is not None
            and mutation_manifest_path.is_file()
            and file_sha256(mutation_manifest_path)
            != mutation_manifest_hash
        ):
            mutation_failures.append("MUTATION_MANIFEST_HASH_MISMATCH")
        manifest_payload = (
            as_dict(load_json(mutation_manifest_path, {}))
            if mutation_manifest_path is not None
            and mutation_manifest_path.is_file()
            else {}
        )
        if (
            as_dict(manifest_payload.get("protocol")).get("protocol_id")
            != perturbation_protocol_id
        ):
            mutation_failures.append("MUTATION_PROTOCOL_ID_MISMATCH")
        if mutation_failures:
            return {
                "schema": "archon_real_observer_cli_adapter_result_v1",
                "version": VERSION,
                "status": "REFUSED",
                "adapted": False,
                "adapter_id": adapter_id,
                "authorization_hash": stored_auth_hash,
                "reasons": [
                    {
                        "code": code,
                        "message": (
                            "Mutation execution provenance failed "
                            "validation."
                        ),
                        "path": "$.authorization.command",
                    }
                    for code in sorted(set(mutation_failures))
                ],
            }
        append_value(
            command,
            "--mutation-manifest",
            mutation_manifest_path,
        )

    append_value(command, "--run-output-dir", output_dir)
    append_value(command, "--cell", int_value(request.get("cell"), 8))
    append_value(command, "--speed", int_value(request.get("speed"), 1000))
    append_value(command, "--delay", int_value(request.get("delay"), 1))
    append_value(command, "--max-ticks", ticks)
    append_switch(
        command,
        "--exit-at-max-ticks",
        policy.get("force_exit_at_max_ticks") is True,
    )
    append_value(
        command,
        "--autosave-every",
        int_value(request.get("autosave_every"), 0),
    )
    append_value(
        command,
        "--sample-every",
        int_value(request.get("sample_every"), 1),
    )
    append_value(
        command,
        "--pressure-timeline-every",
        int_value(request.get("pressure_every"), 100),
    )

    if policy.get("force_csv_outputs") is True:
        command.extend([
            "--samples-csv",
            "--events-csv",
            "--pressure-timeline-csv",
            "--chronicle-csv",
        ])
    append_switch(command, "--passport", policy.get("force_passport") is True)
    append_switch(command, "--log", policy.get("force_log") is True)

    if policy.get("force_sqlite") is True:
        command.append("--telemetry-sqlite")
        append_value(command, "--telemetry-db", telemetry_path)

    append_value(command, "--experiment-id", identity.get("experiment_id"))
    append_value(command, "--condition-id", request.get("condition_id"))
    append_value(command, "--experiment-role", request.get("experiment_role"))
    append_value(
        command,
        "--replicate-index",
        int_value(request.get("replicate_index"), 0),
    )
    append_value(command, "--field-width", field_width)
    append_value(command, "--field-height", field_height)
    append_value(command, "--topology", topology)
    append_value(command, "--boundary-mode", boundary)
    append_value(command, "--initial-state-mode", initial_state_mode)
    if seed is not None:
        append_value(command, "--experiment-seed", seed)

    adapter_core = {
        "schema": "archon_real_observer_launch_manifest_v1",
        "version": VERSION,
        "adapter_id": adapter_id,
        "authorization_id": authorization.get("authorization_id"),
        "authorization_hash": stored_auth_hash,
        "binding_id": authorization.get("binding_id"),
        "manifest_hash": authorization.get("manifest_hash"),
        "contract_hash": authorization.get("contract_hash"),
        "identity": identity,
        "command": command,
        "command_hash": canonical_hash(command),
        "command_preview": shlex.join(command),
        "working_directory": str(observer_script.parent.parent),
        "observer_script_path": str(observer_script),
        "observer_script_hash": actual_script_hash,
        "results_directory": str(results_dir),
        "outputs": outputs,
        "success_criteria": authorization.get("success_criteria"),
        "single_use": True,
        "consumed": False,
        "execution_permitted": True,
        "native_observer_cli": True,
        "adapter_does_not_execute_observer": True,
        "provenance_sidecar": {
            "job_id": identity.get("job_id"),
            "task_id": identity.get("task_id"),
            "runtime_id": identity.get("runtime_id"),
            "requested_run_id": identity.get("run_id"),
        },
    }
    adapter_hash = canonical_hash(adapter_core)

    return {
        "schema": "archon_real_observer_cli_adapter_result_v1",
        "version": VERSION,
        "status": "ADAPTED",
        "adapted": True,
        "adapter_id": adapter_id,
        "authorization_hash": stored_auth_hash,
        "native_command_hash": adapter_core["command_hash"],
        "adapter_hash": adapter_hash,
        "native_manifest": {
            **adapter_core,
            "adapter_hash": adapter_hash,
            "adapted_at": now_iso(),
        },
        "reasons": [],
    }


def render_markdown(result: Dict[str, Any]) -> str:
    manifest = as_dict(result.get("native_manifest"))
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{result.get('version')}**",
        f"- Status: **{result.get('status')}**",
        f"- Adapter ID: `{result.get('adapter_id') or '-'}`",
        f"- Authorization hash: `{result.get('authorization_hash') or '-'}`",
        f"- Native command hash: `{result.get('native_command_hash') or '-'}`",
        f"- Adapter hash: `{result.get('adapter_hash') or '-'}`",
        "",
        "## Safety boundary",
        "",
        "- Translates the authorized generic manifest to the real Observer CLI.",
        "- Does not execute Observer.",
        "- Keeps Stage 6 identity in a provenance sidecar.",
        "",
    ]
    if manifest:
        lines.extend([
            "## Native command",
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
    parser.add_argument("--authorization", default=None)
    parser.add_argument("--request", default=None)
    args = parser.parse_args()

    analysis = Path(args.analysis_root).resolve()
    experiments = analysis / "Experiments"
    experiments.mkdir(parents=True, exist_ok=True)

    authorization_path = (
        Path(args.authorization).resolve()
        if args.authorization
        else experiments / "production_observer_launch_authorization.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments / "real_observer_cli_adapter_request.json"
    )
    policy_path = experiments / "real_observer_cli_adapter_policy.json"
    result_path = experiments / "real_observer_cli_adapter_result.json"
    manifest_path = experiments / "real_observer_launch_manifest.json"
    registry_path = experiments / "real_observer_cli_adapter_registry.json"
    receipt_dir = experiments / "RealObserverCLIAdapterReceipts"
    markdown_path = experiments / "real_observer_cli_adapter.md"

    policy = load_json(policy_path, {})
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    request = load_json(request_path, {})
    if not request:
        request = default_request()
        atomic_write_json(request_path, request)

    authorization = load_json(authorization_path, {})
    result = build_native_manifest(authorization, policy, request)

    registry = load_json(registry_path, {})
    entries = [
        item for item in as_list(registry.get("adapters"))
        if isinstance(item, dict)
    ]

    if result.get("status") == "ADAPTED":
        manifest = as_dict(result.get("native_manifest"))
        atomic_write_json(manifest_path, manifest)

        adapter_id = str(result.get("adapter_id"))
        receipt_path = receipt_dir / f"{adapter_id}.json"
        receipt = {
            "schema": "archon_real_observer_cli_adapter_receipt_v1",
            "version": VERSION,
            "status": "ADAPTED",
            "adapter_id": adapter_id,
            "authorization_id": manifest.get("authorization_id"),
            "authorization_hash": result.get("authorization_hash"),
            "native_command_hash": result.get("native_command_hash"),
            "adapter_hash": result.get("adapter_hash"),
            "manifest_path": str(manifest_path),
            "adapted_at": manifest.get("adapted_at"),
            "execution_permitted": True,
            "adapter_does_not_execute_observer": True,
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        atomic_write_json(receipt_path, receipt)

        entries.append({
            "adapter_id": adapter_id,
            "authorization_id": manifest.get("authorization_id"),
            "authorization_hash": result.get("authorization_hash"),
            "native_command_hash": result.get("native_command_hash"),
            "adapter_hash": result.get("adapter_hash"),
            "manifest_path": str(manifest_path),
            "receipt_path": str(receipt_path),
            "status": "ADAPTED",
            "adapted_at": manifest.get("adapted_at"),
            "consumed": False,
        })
        unique = {
            str(item.get("adapter_id")): item
            for item in entries if item.get("adapter_id")
        }
        ordered = sorted(
            unique.values(),
            key=lambda item: str(item.get("adapter_id")),
        )
        registry = {
            "schema": "archon_real_observer_cli_adapter_registry_v1",
            "version": VERSION,
            "updated_at": now_iso(),
            "adapter_count": len(ordered),
            "active_adapter_count": sum(
                1 for item in ordered if item.get("consumed") is not True
            ),
            "adapters": ordered,
        }
        registry["content_hash"] = canonical_hash(ordered)
        atomic_write_json(registry_path, registry)

        request = {
            "schema": "archon_real_observer_cli_adapter_request_v1",
            "adapt": False,
            "adapter_id": None,
            "expected_authorization_hash": None,
            "results_directory": None,
            "condition_id": None,
            "experiment_role": None,
            "replicate_index": 0,
            "initial_state_mode": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "last_consumed_adapter_id": adapter_id,
        }
        atomic_write_json(request_path, request)

        result["manifest_path"] = str(manifest_path)
        result["receipt_path"] = str(receipt_path)

    atomic_write_json(result_path, result)
    markdown_path.write_text(render_markdown(result), encoding="utf-8")

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Version:             {VERSION}")
    print(f"Status:              {result.get('status')}")
    print(f"Adapter ID:          {result.get('adapter_id') or '-'}")
    print(
        f"Authorization hash:  "
        f"{result.get('authorization_hash') or '-'}"
    )
    print(
        f"Native command hash: "
        f"{result.get('native_command_hash') or '-'}"
    )
    print(f"Adapter hash:        {result.get('adapter_hash') or '-'}")
    print(f"Policy:              {policy_path}")
    print(f"Request:             {request_path}")
    print(f"Result:              {result_path}")
    print(f"Native manifest:     {manifest_path}")
    print(f"Registry:            {registry_path}")
    print(f"Markdown:            {markdown_path}")
    print("=" * 72)

    return 0 if result.get("status") != "REFUSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
