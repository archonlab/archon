#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VERSION = "1.0"
TITLE = "ARCHON Stage 7.4 Production Observer Launch"


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
        "schema": "archon_production_observer_launch_policy_v1",
        "version": VERSION,
        "launch_enabled": False,
        "require_native_manifest": True,
        "require_adapter_hash_match": True,
        "require_command_hash_match": True,
        "require_script_hash_match": True,
        "require_single_use": True,
        "require_unconsumed": True,
        "require_execution_permitted": True,
        "require_native_cli_marker": True,
        "require_non_executing_adapter_marker": True,
        "require_absolute_command_paths": True,
        "consume_before_process_start": True,
        "terminate_grace_seconds": 10,
        "default_timeout_seconds": 900,
        "maximum_timeout_seconds": 86_400,
        "allowed_exit_codes": [0],
        "updated_at": now_iso(),
    }


def default_request() -> Dict[str, Any]:
    return {
        "schema": "archon_production_observer_launch_request_v1",
        "launch": False,
        "launch_id": None,
        "expected_adapter_hash": None,
        "expected_native_command_hash": None,
        "requested_at": None,
        "requested_by": None,
        "timeout_seconds": None,
        "confirmation": None,
        "last_consumed_launch_id": None,
        "instructions": {
            "required_confirmation": "LAUNCH_AUTHORIZED_OBSERVER_ONCE",
            "launch_executes_observer": True,
        },
    }


def native_manifest_core(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: manifest.get(key)
        for key in (
            "schema",
            "version",
            "adapter_id",
            "authorization_id",
            "authorization_hash",
            "binding_id",
            "manifest_hash",
            "contract_hash",
            "identity",
            "command",
            "command_hash",
            "command_preview",
            "working_directory",
            "observer_script_path",
            "observer_script_hash",
            "results_directory",
            "outputs",
            "success_criteria",
            "single_use",
            "consumed",
            "execution_permitted",
            "native_observer_cli",
            "adapter_does_not_execute_observer",
            "provenance_sidecar",
        )
    }


def verify_preflight(
    manifest: Dict[str, Any],
    policy: Dict[str, Any],
    request: Dict[str, Any],
    prior_launch_ids: set[str],
) -> Dict[str, Any]:
    reasons: List[Dict[str, Any]] = []

    if request.get("launch") is not True:
        return {
            "status": "NO_LAUNCH_REQUEST",
            "launchable": False,
            "reasons": [],
        }

    if policy.get("launch_enabled") is not True:
        add_reason(
            reasons,
            "LAUNCH_DISABLED",
            "Production Observer launch is disabled by policy.",
            "$.policy.launch_enabled",
            actual=policy.get("launch_enabled"),
            expected=True,
        )

    if request.get("confirmation") != "LAUNCH_AUTHORIZED_OBSERVER_ONCE":
        add_reason(
            reasons,
            "CONFIRMATION_INVALID",
            "Launch confirmation is invalid.",
            "$.request.confirmation",
            actual=request.get("confirmation"),
            expected="LAUNCH_AUTHORIZED_OBSERVER_ONCE",
        )

    launch_id = text(request.get("launch_id"))
    if not launch_id:
        add_reason(
            reasons,
            "LAUNCH_ID_MISSING",
            "launch_id is required.",
            "$.request.launch_id",
        )
    elif launch_id in prior_launch_ids:
        add_reason(
            reasons,
            "LAUNCH_ID_REPLAY",
            "launch_id has already been used.",
            "$.request.launch_id",
            actual=launch_id,
        )

    if (
        policy.get("require_native_manifest") is True
        and manifest.get("schema") != "archon_real_observer_launch_manifest_v1"
    ):
        add_reason(
            reasons,
            "NATIVE_MANIFEST_SCHEMA_INVALID",
            "Real Observer launch manifest schema is invalid.",
            "$.manifest.schema",
            actual=manifest.get("schema"),
            expected="archon_real_observer_launch_manifest_v1",
        )

    stored_adapter_hash = text(manifest.get("adapter_hash"))
    computed_adapter_hash = canonical_hash(native_manifest_core(manifest))
    if (
        policy.get("require_adapter_hash_match") is True
        and stored_adapter_hash != computed_adapter_hash
    ):
        add_reason(
            reasons,
            "ADAPTER_HASH_MISMATCH",
            "Stored adapter_hash differs from native manifest content.",
            "$.manifest.adapter_hash",
            actual=stored_adapter_hash,
            expected=computed_adapter_hash,
        )

    if text(request.get("expected_adapter_hash")) != stored_adapter_hash:
        add_reason(
            reasons,
            "EXPECTED_ADAPTER_HASH_MISMATCH",
            "Launch request targets another adapter hash.",
            "$.request.expected_adapter_hash",
            actual=request.get("expected_adapter_hash"),
            expected=stored_adapter_hash,
        )

    command = manifest.get("command")
    if not isinstance(command, list) or not command:
        add_reason(
            reasons,
            "COMMAND_MISSING",
            "Native Observer command must be a non-empty list.",
            "$.manifest.command",
            actual=command,
        )
        command = []

    stored_command_hash = text(manifest.get("command_hash"))
    computed_command_hash = canonical_hash(command)
    if (
        policy.get("require_command_hash_match") is True
        and stored_command_hash != computed_command_hash
    ):
        add_reason(
            reasons,
            "COMMAND_HASH_MISMATCH",
            "Stored command_hash differs from native command.",
            "$.manifest.command_hash",
            actual=stored_command_hash,
            expected=computed_command_hash,
        )

    if text(request.get("expected_native_command_hash")) != stored_command_hash:
        add_reason(
            reasons,
            "EXPECTED_COMMAND_HASH_MISMATCH",
            "Launch request targets another native command hash.",
            "$.request.expected_native_command_hash",
            actual=request.get("expected_native_command_hash"),
            expected=stored_command_hash,
        )

    if (
        policy.get("require_single_use") is True
        and manifest.get("single_use") is not True
    ):
        add_reason(
            reasons,
            "MANIFEST_NOT_SINGLE_USE",
            "Native launch manifest must be single-use.",
            "$.manifest.single_use",
            actual=manifest.get("single_use"),
            expected=True,
        )

    if (
        policy.get("require_unconsumed") is True
        and manifest.get("consumed") is not False
    ):
        add_reason(
            reasons,
            "MANIFEST_ALREADY_CONSUMED",
            "Native launch manifest has already been consumed.",
            "$.manifest.consumed",
            actual=manifest.get("consumed"),
            expected=False,
        )

    if (
        policy.get("require_execution_permitted") is True
        and manifest.get("execution_permitted") is not True
    ):
        add_reason(
            reasons,
            "EXECUTION_NOT_PERMITTED",
            "Native launch manifest does not permit execution.",
            "$.manifest.execution_permitted",
            actual=manifest.get("execution_permitted"),
            expected=True,
        )

    if (
        policy.get("require_native_cli_marker") is True
        and manifest.get("native_observer_cli") is not True
    ):
        add_reason(
            reasons,
            "NATIVE_CLI_MARKER_MISSING",
            "Manifest is not marked as a native Observer CLI command.",
            "$.manifest.native_observer_cli",
            actual=manifest.get("native_observer_cli"),
            expected=True,
        )

    if (
        policy.get("require_non_executing_adapter_marker") is True
        and manifest.get("adapter_does_not_execute_observer") is not True
    ):
        add_reason(
            reasons,
            "ADAPTER_SAFETY_MARKER_MISSING",
            "Native manifest lacks the adapter safety marker.",
            "$.manifest.adapter_does_not_execute_observer",
            actual=manifest.get("adapter_does_not_execute_observer"),
            expected=True,
        )

    script_value = text(manifest.get("observer_script_path"))
    script_path = Path(script_value).expanduser() if script_value else None
    actual_script_hash = file_sha256(script_path) if script_path else None
    expected_script_hash = text(manifest.get("observer_script_hash"))

    if (
        policy.get("require_script_hash_match") is True
        and actual_script_hash != expected_script_hash
    ):
        add_reason(
            reasons,
            "OBSERVER_SCRIPT_HASH_MISMATCH",
            "Observer script changed after native adaptation.",
            "$.manifest.observer_script_hash",
            actual=actual_script_hash,
            expected=expected_script_hash,
        )

    if policy.get("require_absolute_command_paths") is True and command:
        for index in (0, 1):
            if index >= len(command):
                break
            value = text(command[index])
            if not value or not Path(value).is_absolute():
                add_reason(
                    reasons,
                    "COMMAND_PATH_NOT_ABSOLUTE",
                    "Python executable and Observer script must be absolute.",
                    f"$.manifest.command[{index}]",
                    actual=value,
                )

    work_value = text(manifest.get("working_directory"))
    work_dir = Path(work_value).expanduser() if work_value else None
    if work_dir is None or not work_dir.is_dir():
        add_reason(
            reasons,
            "WORKING_DIRECTORY_MISSING",
            "Observer working directory does not exist.",
            "$.manifest.working_directory",
            actual=str(work_dir) if work_dir else None,
        )

    timeout = int_value(
        request.get("timeout_seconds"),
        int_value(policy.get("default_timeout_seconds"), 900),
    )
    max_timeout = int_value(policy.get("maximum_timeout_seconds"), 86_400)
    if timeout is None or timeout <= 0:
        add_reason(
            reasons,
            "TIMEOUT_INVALID",
            "Launch timeout must be positive.",
            "$.request.timeout_seconds",
            actual=timeout,
        )
    elif max_timeout is not None and timeout > max_timeout:
        add_reason(
            reasons,
            "TIMEOUT_EXCEEDS_POLICY",
            "Launch timeout exceeds policy maximum.",
            "$.request.timeout_seconds",
            actual=timeout,
            expected=max_timeout,
        )

    return {
        "status": "READY" if not reasons else "REFUSED",
        "launchable": not reasons,
        "launch_id": launch_id,
        "adapter_hash": stored_adapter_hash,
        "command_hash": stored_command_hash,
        "contract_hash": manifest.get("contract_hash"),
        "authorization_id": manifest.get("authorization_id"),
        "adapter_id": manifest.get("adapter_id"),
        "timeout_seconds": timeout,
        "command": command,
        "working_directory": str(work_dir) if work_dir else None,
        "reasons": reasons,
    }


def update_registry_consumption(
    path: Path,
    collection_key: str,
    id_key: str,
    target_id: str,
    consumed_at: str,
    launch_id: str,
) -> bool:
    payload = load_json(path, {})
    rows = [
        item for item in as_list(payload.get(collection_key))
        if isinstance(item, dict)
    ]
    changed = False

    for item in rows:
        if str(item.get(id_key)) == target_id:
            item["consumed"] = True
            item["consumed_at"] = consumed_at
            item["consumed_by_launch_id"] = launch_id
            if item.get("status") in {"AUTHORIZED", "ADAPTED"}:
                item["status"] = "CONSUMED"
            changed = True

    if not changed:
        return False

    payload[collection_key] = rows
    if collection_key == "authorizations":
        payload["active_authorization_count"] = sum(
            1 for item in rows if item.get("consumed") is not True
        )
    if collection_key == "adapters":
        payload["active_adapter_count"] = sum(
            1 for item in rows if item.get("consumed") is not True
        )
    payload["updated_at"] = now_iso()
    payload["content_hash"] = canonical_hash(rows)
    atomic_write_json(path, payload)
    return True


def terminate_process_group(
    process: subprocess.Popen[Any],
    grace_seconds: int,
) -> Dict[str, Any]:
    details = {
        "termination_requested": False,
        "kill_requested": False,
    }
    if process.poll() is not None:
        return details

    details["termination_requested"] = True
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return details

    try:
        process.wait(timeout=max(1, grace_seconds))
        return details
    except subprocess.TimeoutExpired:
        pass

    details["kill_requested"] = True
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return details

    try:
        process.wait(timeout=max(1, grace_seconds))
    except subprocess.TimeoutExpired:
        pass
    return details


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{result.get('version')}**",
        f"- Status: **{result.get('status')}**",
        f"- Launch ID: `{result.get('launch_id') or '-'}`",
        f"- Adapter hash: `{result.get('adapter_hash') or '-'}`",
        f"- Command hash: `{result.get('command_hash') or '-'}`",
        f"- Exit code: `{result.get('exit_code')}`",
        f"- Timed out: `{result.get('timed_out')}`",
        f"- Duration seconds: `{result.get('duration_seconds')}`",
        "",
        "## Execution boundary",
        "",
        "- Authorization and native adapter state are consumed before process start.",
        "- Observer runs in its own process group.",
        "- stdout and stderr are captured separately.",
        "- Timeout termination targets the complete process group.",
        "- A consumed launch cannot be replayed.",
        "",
    ]
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
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--request", default=None)
    args = parser.parse_args()

    analysis = Path(args.analysis_root).resolve()
    experiments = analysis / "Experiments"
    experiments.mkdir(parents=True, exist_ok=True)

    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else experiments / "real_observer_launch_manifest.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments / "production_observer_launch_request.json"
    )
    policy_path = experiments / "production_observer_launch_policy.json"
    result_path = experiments / "production_observer_launch_result.json"
    registry_path = experiments / "production_observer_launch_registry.json"
    receipt_dir = experiments / "ProductionObserverLaunchReceipts"
    markdown_path = experiments / "production_observer_launch.md"

    authorization_path = (
        experiments / "production_observer_launch_authorization.json"
    )
    authorization_registry_path = (
        experiments
        / "production_observer_launch_authorization_registry.json"
    )
    adapter_registry_path = (
        experiments / "real_observer_cli_adapter_registry.json"
    )

    policy = load_json(policy_path, {})
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    request = load_json(request_path, {})
    if not request:
        request = default_request()
        atomic_write_json(request_path, request)

    manifest = load_json(manifest_path, {})
    registry = load_json(registry_path, {})
    launches = [
        item for item in as_list(registry.get("launches"))
        if isinstance(item, dict)
    ]
    prior_launch_ids = {
        str(item.get("launch_id"))
        for item in launches if item.get("launch_id")
    }

    preflight = verify_preflight(
        manifest,
        policy,
        request,
        prior_launch_ids,
    )

    if preflight.get("status") == "NO_LAUNCH_REQUEST":
        result = {
            "schema": "archon_production_observer_launch_result_v1",
            "version": VERSION,
            "status": "NO_LAUNCH_REQUEST",
            "launched": False,
            "launch_id": None,
            "reasons": [],
        }
        atomic_write_json(result_path, result)
        markdown_path.write_text(render_markdown(result), encoding="utf-8")
        print("=" * 72)
        print(TITLE)
        print("=" * 72)
        print(f"Version:        {VERSION}")
        print("Status:         NO_LAUNCH_REQUEST")
        print("Launch ID:      -")
        print("Exit code:      -")
        print(f"Policy:         {policy_path}")
        print(f"Request:        {request_path}")
        print(f"Result:         {result_path}")
        print(f"Registry:       {registry_path}")
        print(f"Markdown:       {markdown_path}")
        print("=" * 72)
        return 0

    if preflight.get("status") == "REFUSED":
        result = {
            "schema": "archon_production_observer_launch_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "launched": False,
            "launch_id": preflight.get("launch_id"),
            "adapter_hash": preflight.get("adapter_hash"),
            "command_hash": preflight.get("command_hash"),
            "reasons": preflight.get("reasons", []),
        }
        atomic_write_json(result_path, result)
        markdown_path.write_text(render_markdown(result), encoding="utf-8")
        print("=" * 72)
        print(TITLE)
        print("=" * 72)
        print(f"Version:        {VERSION}")
        print("Status:         REFUSED")
        print(f"Launch ID:      {result.get('launch_id') or '-'}")
        print(f"Policy:         {policy_path}")
        print(f"Request:        {request_path}")
        print(f"Result:         {result_path}")
        print(f"Registry:       {registry_path}")
        print(f"Markdown:       {markdown_path}")
        print("=" * 72)
        return 1

    launch_id = str(preflight["launch_id"])
    adapter_id = str(preflight.get("adapter_id") or "")
    authorization_id = str(preflight.get("authorization_id") or "")
    consumed_at = now_iso()

    output_root_value = text(
        as_dict(manifest.get("outputs")).get("output_directory")
    )
    output_root = (
        Path(output_root_value).expanduser()
        if output_root_value else experiments / "ObserverLaunchOutputs"
    )
    output_root.mkdir(parents=True, exist_ok=True)

    stdout_path = output_root / "observer.stdout.log"
    stderr_path = output_root / "observer.stderr.log"
    execution_receipt_path = output_root / "execution_receipt.json"
    run_summary_path = output_root / "run_summary.json"
    provenance_path = output_root / "execution_provenance.json"

    if policy.get("consume_before_process_start") is True:
        manifest["consumed"] = True
        manifest["consumed_at"] = consumed_at
        manifest["consumed_by_launch_id"] = launch_id
        atomic_write_json(manifest_path, manifest)

        authorization = load_json(authorization_path, {})
        if authorization:
            authorization["consumed"] = True
            authorization["consumed_at"] = consumed_at
            authorization["consumed_by_launch_id"] = launch_id
            authorization["status"] = "CONSUMED"
            atomic_write_json(authorization_path, authorization)

        update_registry_consumption(
            authorization_registry_path,
            "authorizations",
            "authorization_id",
            authorization_id,
            consumed_at,
            launch_id,
        )
        update_registry_consumption(
            adapter_registry_path,
            "adapters",
            "adapter_id",
            adapter_id,
            consumed_at,
            launch_id,
        )

    started_at = now_iso()
    monotonic_start = time.monotonic()
    command = [str(item) for item in preflight["command"]]
    timeout = int(preflight["timeout_seconds"])
    grace = int_value(policy.get("terminate_grace_seconds"), 10) or 10

    timed_out = False
    launch_error: Optional[str] = None
    termination = {
        "termination_requested": False,
        "kill_requested": False,
    }
    exit_code: Optional[int] = None
    process_id: Optional[int] = None

    provenance = {
        "schema": "archon_production_observer_execution_provenance_v1",
        "version": VERSION,
        "launch_id": launch_id,
        "adapter_id": adapter_id,
        "authorization_id": authorization_id,
        "adapter_hash": preflight.get("adapter_hash"),
        "command_hash": preflight.get("command_hash"),
        "contract_hash": preflight.get("contract_hash"),
        "identity": manifest.get("identity"),
        "provenance_sidecar": manifest.get("provenance_sidecar"),
        "command": command,
        "working_directory": preflight.get("working_directory"),
        "manifest_path": str(manifest_path),
        "request_path": str(request_path),
        "consumed_at": consumed_at,
        "started_at": started_at,
    }
    provenance["provenance_hash"] = canonical_hash(provenance)
    atomic_write_json(provenance_path, provenance)

    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, \
             stderr_path.open("w", encoding="utf-8") as stderr_handle:
            process = subprocess.Popen(
                command,
                cwd=preflight["working_directory"],
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                start_new_session=True,
            )
            process_id = process.pid
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                termination = terminate_process_group(process, grace)
                exit_code = process.returncode
    except Exception as exc:
        launch_error = f"{type(exc).__name__}: {exc}"

    finished_at = now_iso()
    duration = round(time.monotonic() - monotonic_start, 6)
    allowed_exit_codes = [
        int(item) for item in as_list(policy.get("allowed_exit_codes"))
    ]

    process_completed = (
        launch_error is None
        and not timed_out
        and exit_code in allowed_exit_codes
    )
    status = "COMPLETED" if process_completed else (
        "TIMED_OUT" if timed_out else "FAILED"
    )

    result_core = {
        "schema": "archon_production_observer_launch_result_v1",
        "version": VERSION,
        "status": status,
        "launched": process_id is not None,
        "launch_id": launch_id,
        "adapter_id": adapter_id,
        "authorization_id": authorization_id,
        "adapter_hash": preflight.get("adapter_hash"),
        "command_hash": preflight.get("command_hash"),
        "contract_hash": preflight.get("contract_hash"),
        "process_id": process_id,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "launch_error": launch_error,
        "termination": termination,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "timeout_seconds": timeout,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "provenance_path": str(provenance_path),
        "manifest_consumed": True,
        "authorization_consumed": True,
        "adapter_consumed": True,
        "replay_permitted": False,
        "reasons": [],
    }
    execution_hash = canonical_hash(result_core)
    result = {
        **result_core,
        "execution_hash": execution_hash,
    }
    atomic_write_json(result_path, result)

    receipt = {
        "schema": "archon_production_observer_execution_receipt_v1",
        "version": VERSION,
        "status": status,
        "launch_id": launch_id,
        "adapter_id": adapter_id,
        "authorization_id": authorization_id,
        "adapter_hash": preflight.get("adapter_hash"),
        "command_hash": preflight.get("command_hash"),
        "contract_hash": preflight.get("contract_hash"),
        "execution_hash": execution_hash,
        "process_id": process_id,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "provenance_path": str(provenance_path),
        "single_use_consumed": True,
        "replay_permitted": False,
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    atomic_write_json(execution_receipt_path, receipt)

    run_summary = {
        "schema": "archon_production_observer_run_summary_v1",
        "version": VERSION,
        "status": status,
        "launch_id": launch_id,
        "identity": manifest.get("identity"),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "process_completed": process_completed,
        "execution_receipt_path": str(execution_receipt_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "telemetry_target": as_dict(
            as_dict(manifest.get("outputs")).get("telemetry_target")
        ),
        "success_criteria": manifest.get("success_criteria"),
    }
    run_summary["summary_hash"] = canonical_hash(run_summary)
    atomic_write_json(run_summary_path, run_summary)

    receipt_dir.mkdir(parents=True, exist_ok=True)
    durable_receipt_path = receipt_dir / f"{launch_id}.json"
    atomic_write_json(durable_receipt_path, receipt)

    launches.append({
        "launch_id": launch_id,
        "adapter_id": adapter_id,
        "authorization_id": authorization_id,
        "adapter_hash": preflight.get("adapter_hash"),
        "command_hash": preflight.get("command_hash"),
        "contract_hash": preflight.get("contract_hash"),
        "execution_hash": execution_hash,
        "receipt_path": str(durable_receipt_path),
        "output_receipt_path": str(execution_receipt_path),
        "run_summary_path": str(run_summary_path),
        "status": status,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "started_at": started_at,
        "finished_at": finished_at,
        "consumed": True,
    })
    unique = {
        str(item.get("launch_id")): item
        for item in launches if item.get("launch_id")
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: str(item.get("launch_id")),
    )
    registry = {
        "schema": "archon_production_observer_launch_registry_v1",
        "version": VERSION,
        "updated_at": now_iso(),
        "launch_count": len(ordered),
        "completed_count": sum(
            1 for item in ordered if item.get("status") == "COMPLETED"
        ),
        "failed_count": sum(
            1 for item in ordered
            if item.get("status") in {"FAILED", "TIMED_OUT"}
        ),
        "launches": ordered,
    }
    registry["content_hash"] = canonical_hash(ordered)
    atomic_write_json(registry_path, registry)

    consumed_request = {
        "schema": "archon_production_observer_launch_request_v1",
        "launch": False,
        "launch_id": None,
        "expected_adapter_hash": None,
        "expected_native_command_hash": None,
        "requested_at": None,
        "requested_by": None,
        "timeout_seconds": None,
        "confirmation": None,
        "last_consumed_launch_id": launch_id,
    }
    atomic_write_json(request_path, consumed_request)

    markdown_path.write_text(render_markdown(result), encoding="utf-8")

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Version:        {VERSION}")
    print(f"Status:         {status}")
    print(f"Launch ID:      {launch_id}")
    print(f"Adapter hash:   {preflight.get('adapter_hash') or '-'}")
    print(f"Command hash:   {preflight.get('command_hash') or '-'}")
    print(f"Process ID:     {process_id or '-'}")
    print(f"Exit code:      {exit_code}")
    print(f"Timed out:      {timed_out}")
    print(f"Duration:       {duration:.3f}s")
    print(f"stdout:         {stdout_path}")
    print(f"stderr:         {stderr_path}")
    print(f"Receipt:        {execution_receipt_path}")
    print(f"Run summary:    {run_summary_path}")
    print(f"Result:         {result_path}")
    print(f"Registry:       {registry_path}")
    print("=" * 72)

    return 0 if status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
