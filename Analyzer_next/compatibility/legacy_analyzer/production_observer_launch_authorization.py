#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VERSION = "1.0"
TITLE = "ARCHON Stage 7.3 Production Observer Launch Authorization"


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
        "schema": "archon_production_observer_launch_authorization_policy_v1",
        "version": VERSION,
        "authorization_enabled": False,
        "require_bound_manifest": True,
        "require_manifest_hash_match": True,
        "require_command_hash_match": True,
        "require_contract_hash": True,
        "require_script_hash_match": True,
        "require_execution_permitted_false": True,
        "require_non_executing_binding_marker": True,
        "require_absolute_command_paths": True,
        "require_unconsumed_authorization_id": True,
        "authorization_ttl_seconds": 900,
        "allowed_manifest_schemas": [
            "archon_production_observer_execution_manifest_v1",
        ],
        "updated_at": now_iso(),
    }


def default_request() -> Dict[str, Any]:
    return {
        "schema": "archon_production_observer_launch_authorization_request_v1",
        "authorize": False,
        "authorization_id": None,
        "expected_manifest_hash": None,
        "expected_command_hash": None,
        "expected_contract_hash": None,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_authorization_id": None,
        "instructions": {
            "required_confirmation": "AUTHORIZE_SINGLE_OBSERVER_LAUNCH",
            "authorization_does_not_execute_observer": True,
        },
    }


def manifest_core(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: manifest.get(key)
        for key in (
            "schema",
            "version",
            "binding_id",
            "contract_hash",
            "identity",
            "observer",
            "command",
            "command_hash",
            "command_preview",
            "environment",
            "environment_hash",
            "working_directory",
            "outputs",
            "success_criteria",
            "execution_permitted",
            "binding_does_not_execute_observer",
        )
    }


def compute_manifest_hash(manifest: Dict[str, Any]) -> str:
    return canonical_hash(manifest_core(manifest))


def build_authorization(
    manifest: Dict[str, Any],
    policy: Dict[str, Any],
    request: Dict[str, Any],
    prior_authorization_ids: set[str],
) -> Dict[str, Any]:
    reasons: List[Dict[str, Any]] = []

    if request.get("authorize") is not True:
        return {
            "schema": "archon_production_observer_launch_authorization_result_v1",
            "version": VERSION,
            "status": "NO_AUTHORIZATION_REQUEST",
            "authorized": False,
            "authorization_id": None,
            "reasons": [],
        }

    if policy.get("authorization_enabled") is not True:
        add_reason(
            reasons,
            "AUTHORIZATION_DISABLED",
            "Production Observer launch authorization is disabled by policy.",
            "$.policy.authorization_enabled",
            actual=policy.get("authorization_enabled"),
            expected=True,
        )

    if request.get("confirmation") != "AUTHORIZE_SINGLE_OBSERVER_LAUNCH":
        add_reason(
            reasons,
            "CONFIRMATION_INVALID",
            "Launch authorization confirmation is invalid.",
            "$.request.confirmation",
            actual=request.get("confirmation"),
            expected="AUTHORIZE_SINGLE_OBSERVER_LAUNCH",
        )

    authorization_id = text(request.get("authorization_id"))
    if not authorization_id:
        add_reason(
            reasons,
            "AUTHORIZATION_ID_MISSING",
            "authorization_id is required.",
            "$.request.authorization_id",
        )
    elif (
        policy.get("require_unconsumed_authorization_id") is True
        and authorization_id in prior_authorization_ids
    ):
        add_reason(
            reasons,
            "AUTHORIZATION_ID_REPLAY",
            "authorization_id has already been issued.",
            "$.request.authorization_id",
            actual=authorization_id,
        )

    if manifest.get("schema") not in as_list(
        policy.get("allowed_manifest_schemas")
    ):
        add_reason(
            reasons,
            "MANIFEST_SCHEMA_UNSUPPORTED",
            "Observer execution manifest schema is unsupported.",
            "$.manifest.schema",
            actual=manifest.get("schema"),
            expected=policy.get("allowed_manifest_schemas"),
        )

    stored_manifest_hash = text(manifest.get("manifest_hash"))
    computed_manifest_hash = compute_manifest_hash(manifest)
    if (
        policy.get("require_manifest_hash_match") is True
        and stored_manifest_hash != computed_manifest_hash
    ):
        add_reason(
            reasons,
            "MANIFEST_HASH_MISMATCH",
            "Stored manifest_hash differs from manifest content.",
            "$.manifest.manifest_hash",
            actual=stored_manifest_hash,
            expected=computed_manifest_hash,
        )

    expected_manifest_hash = text(request.get("expected_manifest_hash"))
    if expected_manifest_hash != stored_manifest_hash:
        add_reason(
            reasons,
            "EXPECTED_MANIFEST_HASH_MISMATCH",
            "Authorization request targets a different manifest hash.",
            "$.request.expected_manifest_hash",
            actual=expected_manifest_hash,
            expected=stored_manifest_hash,
        )

    command = manifest.get("command")
    if not isinstance(command, list) or not command:
        add_reason(
            reasons,
            "COMMAND_MISSING",
            "Manifest command must be a non-empty list.",
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
            "Stored command_hash differs from command content.",
            "$.manifest.command_hash",
            actual=stored_command_hash,
            expected=computed_command_hash,
        )

    expected_command_hash = text(request.get("expected_command_hash"))
    if expected_command_hash != stored_command_hash:
        add_reason(
            reasons,
            "EXPECTED_COMMAND_HASH_MISMATCH",
            "Authorization request targets a different command hash.",
            "$.request.expected_command_hash",
            actual=expected_command_hash,
            expected=stored_command_hash,
        )

    contract_hash = text(manifest.get("contract_hash"))
    expected_contract_hash = text(request.get("expected_contract_hash"))
    if policy.get("require_contract_hash") is True and not contract_hash:
        add_reason(
            reasons,
            "CONTRACT_HASH_MISSING",
            "Manifest does not contain contract_hash.",
            "$.manifest.contract_hash",
        )
    if expected_contract_hash != contract_hash:
        add_reason(
            reasons,
            "EXPECTED_CONTRACT_HASH_MISMATCH",
            "Authorization request targets a different contract hash.",
            "$.request.expected_contract_hash",
            actual=expected_contract_hash,
            expected=contract_hash,
        )

    if (
        policy.get("require_execution_permitted_false") is True
        and manifest.get("execution_permitted") is not False
    ):
        add_reason(
            reasons,
            "BINDING_EXECUTION_FLAG_INVALID",
            "Binding manifest must not already permit execution.",
            "$.manifest.execution_permitted",
            actual=manifest.get("execution_permitted"),
            expected=False,
        )

    if (
        policy.get("require_non_executing_binding_marker") is True
        and manifest.get("binding_does_not_execute_observer") is not True
    ):
        add_reason(
            reasons,
            "NON_EXECUTING_BINDING_MARKER_MISSING",
            "Manifest lacks the non-executing binding marker.",
            "$.manifest.binding_does_not_execute_observer",
            actual=manifest.get("binding_does_not_execute_observer"),
            expected=True,
        )

    observer = as_dict(manifest.get("observer"))
    script_path_value = text(observer.get("script_path"))
    script_path = Path(script_path_value).expanduser() if script_path_value else None
    actual_script_hash = file_sha256(script_path) if script_path else None
    expected_script_hash = text(observer.get("script_hash"))

    if (
        policy.get("require_script_hash_match") is True
        and actual_script_hash != expected_script_hash
    ):
        add_reason(
            reasons,
            "OBSERVER_SCRIPT_HASH_MISMATCH",
            "Observer script changed after binding.",
            "$.manifest.observer.script_hash",
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
                    "Python executable and Observer script paths must be absolute.",
                    f"$.manifest.command[{index}]",
                    actual=value,
                )

    if reasons:
        return {
            "schema": "archon_production_observer_launch_authorization_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "authorized": False,
            "authorization_id": authorization_id,
            "manifest_hash": stored_manifest_hash,
            "command_hash": stored_command_hash,
            "contract_hash": contract_hash,
            "reasons": reasons,
        }

    ttl = int(policy.get("authorization_ttl_seconds") or 900)
    issued_at = now_iso()

    authorization_core = {
        "schema": "archon_production_observer_launch_authorization_v1",
        "version": VERSION,
        "status": "AUTHORIZED",
        "authorization_id": authorization_id,
        "binding_id": manifest.get("binding_id"),
        "manifest_hash": stored_manifest_hash,
        "command_hash": stored_command_hash,
        "contract_hash": contract_hash,
        "identity": as_dict(manifest.get("identity")),
        "observer_script_hash": actual_script_hash,
        "command": command,
        "working_directory": manifest.get("working_directory"),
        "environment_hash": manifest.get("environment_hash"),
        "outputs": manifest.get("outputs"),
        "success_criteria": manifest.get("success_criteria"),
        "issued_at": issued_at,
        "ttl_seconds": ttl,
        "single_use": True,
        "consumed": False,
        "execution_permitted": True,
        "authorization_does_not_execute_observer": True,
    }
    authorization_hash = canonical_hash(authorization_core)

    return {
        "schema": "archon_production_observer_launch_authorization_result_v1",
        "version": VERSION,
        "status": "AUTHORIZED",
        "authorized": True,
        "authorization_id": authorization_id,
        "manifest_hash": stored_manifest_hash,
        "command_hash": stored_command_hash,
        "contract_hash": contract_hash,
        "authorization_hash": authorization_hash,
        "authorization": {
            **authorization_core,
            "authorization_hash": authorization_hash,
        },
        "reasons": [],
    }


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{result.get('version')}**",
        f"- Status: **{result.get('status')}**",
        f"- Authorization ID: `{result.get('authorization_id') or '-'}`",
        f"- Manifest hash: `{result.get('manifest_hash') or '-'}`",
        f"- Command hash: `{result.get('command_hash') or '-'}`",
        f"- Contract hash: `{result.get('contract_hash') or '-'}`",
        f"- Authorization hash: `{result.get('authorization_hash') or '-'}`",
        "",
        "## Safety boundary",
        "",
        "- Authorization is single-use.",
        "- Authorization is bound to one manifest, command, contract, and script hash.",
        "- This module does not invoke Observer.",
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
        else experiments / "production_observer_execution_manifest.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments
        / "production_observer_launch_authorization_request.json"
    )
    policy_path = (
        experiments
        / "production_observer_launch_authorization_policy.json"
    )
    result_path = (
        experiments
        / "production_observer_launch_authorization_result.json"
    )
    authorization_path = (
        experiments / "production_observer_launch_authorization.json"
    )
    registry_path = (
        experiments
        / "production_observer_launch_authorization_registry.json"
    )
    receipt_dir = (
        experiments / "ProductionObserverLaunchAuthorizationReceipts"
    )
    markdown_path = (
        experiments / "production_observer_launch_authorization.md"
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
    authorizations = [
        item for item in as_list(registry.get("authorizations"))
        if isinstance(item, dict)
    ]
    prior_ids = {
        str(item.get("authorization_id"))
        for item in authorizations
        if item.get("authorization_id")
    }

    result = build_authorization(
        manifest,
        policy,
        request,
        prior_ids,
    )

    if result.get("status") == "AUTHORIZED":
        authorization = as_dict(result.get("authorization"))
        atomic_write_json(authorization_path, authorization)

        authorization_id = str(result.get("authorization_id"))
        receipt_path = receipt_dir / f"{authorization_id}.json"
        receipt = {
            "schema": "archon_production_observer_launch_authorization_receipt_v1",
            "version": VERSION,
            "status": "AUTHORIZED",
            "authorization_id": authorization_id,
            "binding_id": authorization.get("binding_id"),
            "manifest_hash": result.get("manifest_hash"),
            "command_hash": result.get("command_hash"),
            "contract_hash": result.get("contract_hash"),
            "authorization_hash": result.get("authorization_hash"),
            "issued_at": authorization.get("issued_at"),
            "single_use": True,
            "consumed": False,
            "execution_permitted": True,
            "authorization_does_not_execute_observer": True,
            "authorization_path": str(authorization_path),
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        atomic_write_json(receipt_path, receipt)

        authorizations.append({
            "authorization_id": authorization_id,
            "binding_id": authorization.get("binding_id"),
            "manifest_hash": result.get("manifest_hash"),
            "command_hash": result.get("command_hash"),
            "contract_hash": result.get("contract_hash"),
            "authorization_hash": result.get("authorization_hash"),
            "authorization_path": str(authorization_path),
            "receipt_path": str(receipt_path),
            "status": "AUTHORIZED",
            "issued_at": authorization.get("issued_at"),
            "single_use": True,
            "consumed": False,
        })

        unique = {
            str(item.get("authorization_id")): item
            for item in authorizations
            if item.get("authorization_id")
        }
        ordered = sorted(
            unique.values(),
            key=lambda item: str(item.get("authorization_id")),
        )
        registry = {
            "schema": (
                "archon_production_observer_launch_authorization_registry_v1"
            ),
            "version": VERSION,
            "updated_at": now_iso(),
            "authorization_count": len(ordered),
            "active_authorization_count": sum(
                1 for item in ordered
                if item.get("consumed") is not True
            ),
            "authorizations": ordered,
        }
        registry["content_hash"] = canonical_hash(ordered)
        atomic_write_json(registry_path, registry)

        request = {
            "schema": (
                "archon_production_observer_launch_authorization_request_v1"
            ),
            "authorize": False,
            "authorization_id": None,
            "expected_manifest_hash": None,
            "expected_command_hash": None,
            "expected_contract_hash": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "last_consumed_authorization_id": authorization_id,
        }
        atomic_write_json(request_path, request)

        result["authorization_path"] = str(authorization_path)
        result["receipt_path"] = str(receipt_path)

    atomic_write_json(result_path, result)
    markdown_path.write_text(
        render_markdown(result),
        encoding="utf-8",
    )

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Version:           {VERSION}")
    print(f"Status:            {result.get('status')}")
    print(
        f"Authorization ID:  "
        f"{result.get('authorization_id') or '-'}"
    )
    print(f"Manifest hash:     {result.get('manifest_hash') or '-'}")
    print(f"Command hash:      {result.get('command_hash') or '-'}")
    print(f"Contract hash:     {result.get('contract_hash') or '-'}")
    print(
        f"Authorization hash:"
        f" {result.get('authorization_hash') or '-'}"
    )
    print(f"Policy:            {policy_path}")
    print(f"Request:           {request_path}")
    print(f"Result:            {result_path}")
    print(f"Authorization:     {authorization_path}")
    print(f"Registry:          {registry_path}")
    print(f"Markdown:          {markdown_path}")
    print("=" * 72)

    return 0 if result.get("status") != "REFUSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
