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


VERSION = "1.1"
TITLE = "ARCHON Stage 7.6 Production Execution Cycle Orchestrator"


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


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def int_value(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return default


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_production_execution_cycle_policy_v1",
        "version": VERSION,
        "cycle_enabled": False,
        "enable_stage_policies_automatically": True,
        "stop_on_first_failure": True,
        "require_accepted_intake": True,
        "default_timeout_seconds": 900,
        "maximum_timeout_seconds": 86400,
        "updated_at": now_iso(),
    }


def default_request() -> Dict[str, Any]:
    return {
        "schema": "archon_production_execution_cycle_request_v1",
        "run_cycle": False,
        "cycle_id": None,
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
        "timeout_seconds": None,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_cycle_id": None,
    }


def run_module(
    python_executable: str,
    module_path: Path,
    analysis_root: Path,
    log_path: Path,
) -> Dict[str, Any]:
    completed = subprocess.run(
        [
            python_executable,
            str(module_path),
            "--analysis-root",
            str(analysis_root),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(completed.stdout, encoding="utf-8")
    return {
        "returncode": completed.returncode,
        "log_path": str(log_path),
        "stdout_tail": completed.stdout[-4000:],
    }


def enable_policy(path: Path, key: str) -> None:
    payload = load_json(path, {})
    payload[key] = True
    atomic_write_json(path, payload)


def fail_result(
    cycle_id: Optional[str],
    stage: str,
    message: str,
    steps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "schema": "archon_production_execution_cycle_result_v1",
        "version": VERSION,
        "status": "FAILED",
        "cycle_id": cycle_id,
        "failed_stage": stage,
        "message": message,
        "steps": steps,
        "cycle_does_not_bypass_stage_policies": True,
        "finished_at": now_iso(),
    }


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{result.get('version')}**",
        f"- Status: **{result.get('status')}**",
        f"- Cycle ID: `{result.get('cycle_id') or '-'}`",
        f"- Failed stage: `{result.get('failed_stage') or '-'}`",
        f"- Observer run ID: `{result.get('observer_run_id') or '-'}`",
        "",
        "## Cycle",
        "",
        "```text",
        "contract → binding → authorization → native adapter → launch → intake",
        "```",
        "",
    ]
    for step in result.get("steps", []):
        lines.append(
            f"- `{step.get('stage')}`: **{step.get('status')}** "
            f"(return code `{step.get('returncode')}`)"
        )
    lines.append("")
    return "\n".join(lines)


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
        "contract": modules_root / "observer_execution_contract.py",
        "binding": modules_root / "production_observer_binding.py",
        "authorization": (
            modules_root / "production_observer_launch_authorization.py"
        ),
        "adapter": modules_root / "real_observer_cli_adapter.py",
        "launch": modules_root / "production_observer_launch.py",
        "intake": modules_root / "production_observer_result_intake.py",
    }

    policy_path = experiments / "production_execution_cycle_policy.json"
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments / "production_execution_cycle_request.json"
    )
    result_path = experiments / "production_execution_cycle_result.json"
    registry_path = experiments / "production_execution_cycle_registry.json"
    markdown_path = experiments / "production_execution_cycle.md"
    receipt_dir = experiments / "ProductionExecutionCycleReceipts"
    terminal_result_dir = (
        experiments / "ProductionExecutionCycleResults"
    )
    logs_dir = experiments / "ProductionExecutionCycleLogs"

    policy = load_json(policy_path, {})
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    request = load_json(request_path, {})
    if not request:
        request = default_request()
        atomic_write_json(request_path, request)

    def consume_request(consumed_cycle_id: Optional[str]) -> None:
        consumed = default_request()
        consumed["last_consumed_cycle_id"] = consumed_cycle_id
        atomic_write_json(request_path, consumed)

    def persist_failed_cycle(result: Dict[str, Any]) -> None:
        cycle_id_value = text(result.get("cycle_id"))
        result_core = {
            key: value
            for key, value in result.items()
            if key != "cycle_hash"
        }
        durable_result = {
            **result_core,
            "cycle_hash": canonical_hash(result_core),
        }
        atomic_write_json(result_path, durable_result)
        markdown_path.write_text(
            render_markdown(durable_result),
            encoding="utf-8",
        )
        if not cycle_id_value:
            return

        terminal_result_path = (
            terminal_result_dir / f"{cycle_id_value}.json"
        )
        atomic_write_json(terminal_result_path, durable_result)

        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / f"{cycle_id_value}.json"
        terminal_receipt = {
            "schema": "archon_production_execution_cycle_receipt_v1",
            "version": VERSION,
            "status": "FAILED",
            "cycle_id": cycle_id_value,
            "failed_stage": durable_result.get("failed_stage"),
            "observer_run_id": durable_result.get("observer_run_id"),
            "cycle_hash": durable_result["cycle_hash"],
            "result_path": str(terminal_result_path),
            "issued_at": now_iso(),
        }
        terminal_receipt["receipt_hash"] = canonical_hash(
            terminal_receipt
        )
        atomic_write_json(receipt_path, terminal_receipt)

        registry = load_json(registry_path, {})
        rows = [
            item
            for item in registry.get("cycles", [])
            if isinstance(item, dict)
        ]
        rows.append(
            {
                "cycle_id": cycle_id_value,
                "status": "FAILED",
                "failed_stage": durable_result.get("failed_stage"),
                "observer_run_id": durable_result.get(
                    "observer_run_id"
                ),
                "receipt_path": str(receipt_path),
                "result_path": str(terminal_result_path),
                "finished_at": durable_result.get("finished_at"),
            }
        )
        unique = {
            str(item.get("cycle_id")): item
            for item in rows
            if item.get("cycle_id")
        }
        ordered = sorted(
            unique.values(),
            key=lambda item: str(item.get("cycle_id")),
        )
        registry_payload = {
            "schema": "archon_production_execution_cycle_registry_v1",
            "version": VERSION,
            "updated_at": now_iso(),
            "cycle_count": len(ordered),
            "completed_count": sum(
                1
                for item in ordered
                if item.get("status") == "COMPLETED"
            ),
            "failed_count": sum(
                1
                for item in ordered
                if item.get("status") == "FAILED"
            ),
            "cycles": ordered,
        }
        registry_payload["content_hash"] = canonical_hash(ordered)
        atomic_write_json(registry_path, registry_payload)
        consume_request(cycle_id_value)
        refresh_research_cycle_records(analysis)

    if request.get("run_cycle") is not True:
        result = {
            "schema": "archon_production_execution_cycle_result_v1",
            "version": VERSION,
            "status": "NO_CYCLE_REQUEST",
            "cycle_id": None,
            "steps": [],
        }
        atomic_write_json(result_path, result)
        markdown_path.write_text(render_markdown(result), encoding="utf-8")
        print("=" * 72)
        print(TITLE)
        print("=" * 72)
        print(f"Version:       {VERSION}")
        print("Status:        NO_CYCLE_REQUEST")
        print("Cycle ID:      -")
        print(f"Policy:        {policy_path}")
        print(f"Request:       {request_path}")
        print(f"Result:        {result_path}")
        print(f"Registry:      {registry_path}")
        print(f"Markdown:      {markdown_path}")
        print("=" * 72)
        return 0

    cycle_id = text(request.get("cycle_id"))
    steps: List[Dict[str, Any]] = []

    existing_terminal_receipt = (
        receipt_dir / f"{cycle_id}.json"
        if cycle_id
        else None
    )
    if (
        existing_terminal_receipt is not None
        and existing_terminal_receipt.is_file()
    ):
        result = fail_result(
            cycle_id,
            "cycle_preflight",
            "cycle_id already has a terminal receipt; replay refused.",
            steps,
        )
        result["replay_refused"] = True
        result["existing_receipt_path"] = str(
            existing_terminal_receipt
        )
        atomic_write_json(result_path, result)
        markdown_path.write_text(
            render_markdown(result),
            encoding="utf-8",
        )
        consume_request(cycle_id)
        refresh_research_cycle_records(analysis)
        return 1

    if policy.get("cycle_enabled") is not True:
        result = fail_result(
            cycle_id,
            "cycle_preflight",
            "Production execution cycle is disabled by policy.",
            steps,
        )
        persist_failed_cycle(result)
        return 1

    if request.get("confirmation") != "RUN_PRODUCTION_EXECUTION_CYCLE_ONCE":
        result = fail_result(
            cycle_id,
            "cycle_preflight",
            "Cycle confirmation is invalid.",
            steps,
        )
        persist_failed_cycle(result)
        return 1

    if not cycle_id:
        result = fail_result(
            cycle_id,
            "cycle_preflight",
            "cycle_id is required.",
            steps,
        )
        persist_failed_cycle(result)
        return 1

    for name, path in modules.items():
        if not path.is_file():
            result = fail_result(
                cycle_id,
                "cycle_preflight",
                f"Required module missing: {name}: {path}",
                steps,
            )
            persist_failed_cycle(result)
            return 1

    timeout = int_value(
        request.get("timeout_seconds"),
        int_value(policy.get("default_timeout_seconds"), 900),
    )
    max_timeout = int_value(policy.get("maximum_timeout_seconds"), 86400)
    if timeout is None or timeout <= 0 or (
        max_timeout is not None and timeout > max_timeout
    ):
        result = fail_result(
            cycle_id,
            "cycle_preflight",
            "Cycle timeout is invalid.",
            steps,
        )
        persist_failed_cycle(result)
        return 1

    contract_path = experiments / "observer_execution_contract.json"
    generic_manifest_path = (
        experiments / "production_observer_execution_manifest.json"
    )
    authorization_path = (
        experiments / "production_observer_launch_authorization.json"
    )
    native_manifest_path = (
        experiments / "real_observer_launch_manifest.json"
    )
    launch_result_path = (
        experiments / "production_observer_launch_result.json"
    )
    intake_result_path = (
        experiments / "production_observer_result_intake_result.json"
    )

    if policy.get("enable_stage_policies_automatically") is True:
        stage_policy_keys = {
            "production_observer_binding_policy.json": "binding_enabled",
            "production_observer_launch_authorization_policy.json": (
                "authorization_enabled"
            ),
            "real_observer_cli_adapter_policy.json": "adapter_enabled",
            "production_observer_launch_policy.json": "launch_enabled",
            "production_observer_result_intake_policy.json": "intake_enabled",
        }
        for filename, key in stage_policy_keys.items():
            path = experiments / filename
            if not path.exists():
                run_module(
                    args.python,
                    modules[
                        {
                            "production_observer_binding_policy.json": "binding",
                            "production_observer_launch_authorization_policy.json": "authorization",
                            "real_observer_cli_adapter_policy.json": "adapter",
                            "production_observer_launch_policy.json": "launch",
                            "production_observer_result_intake_policy.json": "intake",
                        }[filename]
                    ],
                    analysis,
                    logs_dir / f"{cycle_id}_policy_{key}.log",
                )
            enable_policy(path, key)

    def execute(stage: str) -> Dict[str, Any]:
        outcome = run_module(
            args.python,
            modules[stage],
            analysis,
            logs_dir / f"{cycle_id}_{stage}.log",
        )
        step = {
            "stage": stage,
            "returncode": outcome["returncode"],
            "log_path": outcome["log_path"],
            "status": "PASS" if outcome["returncode"] == 0 else "FAIL",
        }
        steps.append(step)
        return outcome

    # 1. Contract
    contract_outcome = execute("contract")
    contract = load_json(contract_path, {})
    contract_hash = text(contract.get("contract_hash"))
    if contract_outcome["returncode"] != 0 or not contract_hash:
        result = fail_result(
            cycle_id,
            "contract",
            "Observer execution contract validation failed.",
            steps,
        )
        persist_failed_cycle(result)
        return 1

    # 2. Binding
    binding_id = f"OBSERVER-BIND-{cycle_id}"
    atomic_write_json(
        experiments / "production_observer_binding_request.json",
        {
            "schema": "archon_production_observer_binding_request_v1",
            "bind": True,
            "binding_id": binding_id,
            "expected_contract_hash": contract_hash,
            "requested_at": now_iso(),
            "requested_by": request.get("requested_by"),
            "confirmation": "BIND_VALIDATED_OBSERVER_CONTRACT",
            "last_consumed_binding_id": None,
        },
    )
    binding_outcome = execute("binding")
    generic_manifest = load_json(generic_manifest_path, {})
    if (
        binding_outcome["returncode"] != 0
        or not generic_manifest.get("manifest_hash")
        or not generic_manifest.get("command_hash")
    ):
        result = fail_result(
            cycle_id,
            "binding",
            "Production Observer binding failed.",
            steps,
        )
        persist_failed_cycle(result)
        return 1

    # 3. Authorization
    authorization_id = f"OBSERVER-AUTH-{cycle_id}"
    atomic_write_json(
        experiments
        / "production_observer_launch_authorization_request.json",
        {
            "schema": (
                "archon_production_observer_launch_authorization_request_v1"
            ),
            "authorize": True,
            "authorization_id": authorization_id,
            "expected_manifest_hash": generic_manifest["manifest_hash"],
            "expected_command_hash": generic_manifest["command_hash"],
            "expected_contract_hash": contract_hash,
            "requested_at": now_iso(),
            "requested_by": request.get("requested_by"),
            "confirmation": "AUTHORIZE_SINGLE_OBSERVER_LAUNCH",
            "last_consumed_authorization_id": None,
        },
    )
    auth_outcome = execute("authorization")
    authorization = load_json(authorization_path, {})
    authorization_hash = text(authorization.get("authorization_hash"))
    if auth_outcome["returncode"] != 0 or not authorization_hash:
        result = fail_result(
            cycle_id,
            "authorization",
            "Production launch authorization failed.",
            steps,
        )
        persist_failed_cycle(result)
        return 1

    # 4. Native CLI adapter
    adapter_id = f"OBSERVER-ADAPTER-{cycle_id}"
    atomic_write_json(
        experiments / "real_observer_cli_adapter_request.json",
        {
            "schema": "archon_real_observer_cli_adapter_request_v1",
            "adapt": True,
            "adapter_id": adapter_id,
            "expected_authorization_hash": authorization_hash,
            "results_directory": request.get("results_directory"),
            "condition_id": request.get("condition_id"),
            "experiment_role": request.get("experiment_role"),
            "replicate_index": request.get("replicate_index"),
            "initial_state_mode": request.get("initial_state_mode"),
            "sample_every": request.get("sample_every"),
            "pressure_every": request.get("pressure_every"),
            "autosave_every": request.get("autosave_every"),
            "cell": request.get("cell"),
            "speed": request.get("speed"),
            "delay": request.get("delay"),
            "requested_at": now_iso(),
            "requested_by": request.get("requested_by"),
            "confirmation": "ADAPT_AUTHORIZED_OBSERVER_LAUNCH",
            "last_consumed_adapter_id": None,
        },
    )
    adapter_outcome = execute("adapter")
    native_manifest = load_json(native_manifest_path, {})
    adapter_hash = text(native_manifest.get("adapter_hash"))
    native_command_hash = text(native_manifest.get("command_hash"))
    if (
        adapter_outcome["returncode"] != 0
        or not adapter_hash
        or not native_command_hash
    ):
        result = fail_result(
            cycle_id,
            "adapter",
            "Real Observer CLI adaptation failed.",
            steps,
        )
        persist_failed_cycle(result)
        return 1

    # 5. Launch
    launch_id = f"OBSERVER-LAUNCH-{cycle_id}"
    atomic_write_json(
        experiments / "production_observer_launch_request.json",
        {
            "schema": "archon_production_observer_launch_request_v1",
            "launch": True,
            "launch_id": launch_id,
            "expected_adapter_hash": adapter_hash,
            "expected_native_command_hash": native_command_hash,
            "requested_at": now_iso(),
            "requested_by": request.get("requested_by"),
            "timeout_seconds": timeout,
            "confirmation": "LAUNCH_AUTHORIZED_OBSERVER_ONCE",
            "last_consumed_launch_id": None,
        },
    )
    launch_outcome = execute("launch")
    launch_result = load_json(launch_result_path, {})
    if (
        launch_outcome["returncode"] != 0
        or launch_result.get("status") != "COMPLETED"
    ):
        result = fail_result(
            cycle_id,
            "launch",
            "Production Observer launch failed.",
            steps,
        )
        result["launch_result"] = launch_result
        persist_failed_cycle(result)
        return 1

    output_dir = text(
        as_dict(native_manifest.get("outputs")).get("output_directory")
    )
    if not output_dir:
        result = fail_result(
            cycle_id,
            "intake_preflight",
            "Native manifest does not define output_directory.",
            steps,
        )
        persist_failed_cycle(result)
        return 1

    # Use immutable per-launch receipt for intake.
    durable_launch_receipt = (
        experiments
        / "ProductionObserverLaunchReceipts"
        / f"{launch_id}.json"
    )
    launch_evidence_path = (
        durable_launch_receipt
        if durable_launch_receipt.is_file()
        else launch_result_path
    )

    # 6. Result intake
    intake_id = f"OBSERVER-INTAKE-{cycle_id}"
    atomic_write_json(
        experiments / "production_observer_result_intake_request.json",
        {
            "schema": (
                "archon_production_observer_result_intake_request_v1"
            ),
            "intake": True,
            "intake_id": intake_id,
            "launch_result_path": str(launch_evidence_path),
            "output_directory": output_dir,
            "expected_launch_id": launch_id,
            "expected_contract_hash": contract_hash,
            "requested_at": now_iso(),
            "requested_by": request.get("requested_by"),
            "confirmation": "INTAKE_COMPLETED_OBSERVER_RESULT",
            "last_consumed_intake_id": None,
        },
    )
    intake_outcome = execute("intake")
    intake_result = load_json(intake_result_path, {})
    if (
        intake_outcome["returncode"] != 0
        or (
            policy.get("require_accepted_intake") is True
            and intake_result.get("status") != "ACCEPTED"
        )
    ):
        result = fail_result(
            cycle_id,
            "intake",
            "Production Observer result intake failed.",
            steps,
        )
        result["intake_result"] = intake_result
        persist_failed_cycle(result)
        return 1

    result_core = {
        "schema": "archon_production_execution_cycle_result_v1",
        "version": VERSION,
        "status": "COMPLETED",
        "cycle_id": cycle_id,
        "contract_hash": contract_hash,
        "binding_id": binding_id,
        "authorization_id": authorization_id,
        "adapter_id": adapter_id,
        "launch_id": launch_id,
        "intake_id": intake_id,
        "requested_run_id": intake_result.get("requested_run_id"),
        "observer_run_id": intake_result.get("observer_run_id"),
        "final_tick": intake_result.get("final_tick"),
        "target_tick": intake_result.get("target_tick"),
        "scientific_complete": intake_result.get("scientific_complete"),
        "steps": steps,
        "cycle_does_not_bypass_stage_policies": True,
        "completed_at": now_iso(),
    }
    result = {
        **result_core,
        "cycle_hash": canonical_hash(result_core),
    }
    atomic_write_json(result_path, result)

    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{cycle_id}.json"
    receipt = {
        "schema": "archon_production_execution_cycle_receipt_v1",
        "version": VERSION,
        "status": "COMPLETED",
        "cycle_id": cycle_id,
        "contract_hash": contract_hash,
        "launch_id": launch_id,
        "intake_id": intake_id,
        "observer_run_id": intake_result.get("observer_run_id"),
        "cycle_hash": result["cycle_hash"],
        "result_path": str(result_path),
        "issued_at": now_iso(),
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    atomic_write_json(receipt_path, receipt)

    registry = load_json(registry_path, {})
    rows = [
        item
        for item in registry.get("cycles", [])
        if isinstance(item, dict)
    ]
    rows.append({
        "cycle_id": cycle_id,
        "status": "COMPLETED",
        "contract_hash": contract_hash,
        "launch_id": launch_id,
        "intake_id": intake_id,
        "observer_run_id": intake_result.get("observer_run_id"),
        "scientific_complete": intake_result.get("scientific_complete"),
        "receipt_path": str(receipt_path),
        "result_path": str(result_path),
        "completed_at": now_iso(),
    })
    unique = {
        str(item.get("cycle_id")): item
        for item in rows if item.get("cycle_id")
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: str(item.get("cycle_id")),
    )
    registry = {
        "schema": "archon_production_execution_cycle_registry_v1",
        "version": VERSION,
        "updated_at": now_iso(),
        "cycle_count": len(ordered),
        "completed_count": sum(
            1 for item in ordered if item.get("status") == "COMPLETED"
        ),
        "failed_count": sum(
            1 for item in ordered if item.get("status") == "FAILED"
        ),
        "cycles": ordered,
    }
    registry["content_hash"] = canonical_hash(ordered)
    atomic_write_json(registry_path, registry)

    atomic_write_json(
        request_path,
        {
            "schema": "archon_production_execution_cycle_request_v1",
            "run_cycle": False,
            "cycle_id": None,
            "results_directory": None,
            "condition_id": None,
            "experiment_role": None,
            "replicate_index": 0,
            "initial_state_mode": None,
            "sample_every": None,
            "pressure_every": None,
            "autosave_every": None,
            "cell": None,
            "speed": None,
            "delay": None,
            "timeout_seconds": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "last_consumed_cycle_id": cycle_id,
        },
    )
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    refresh_research_cycle_records(analysis)

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Version:           {VERSION}")
    print("Status:            COMPLETED")
    print(f"Cycle ID:          {cycle_id}")
    print(f"Contract hash:     {contract_hash}")
    print(f"Launch ID:         {launch_id}")
    print(f"Intake ID:         {intake_id}")
    print(
        f"Observer run ID:   "
        f"{intake_result.get('observer_run_id') or '-'}"
    )
    print(
        f"Final/target tick: "
        f"{intake_result.get('final_tick')} / "
        f"{intake_result.get('target_tick')}"
    )
    print(f"Result:            {result_path}")
    print(f"Receipt:           {receipt_path}")
    print(f"Registry:          {registry_path}")
    print(f"Markdown:          {markdown_path}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
