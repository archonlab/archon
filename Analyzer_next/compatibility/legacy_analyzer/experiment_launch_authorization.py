#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


VERSION = "1.0"
TITLE = "ARCHON Stage 6.5 Launch Authorization Gateway"


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
    existing_request: Dict[str, Any],
) -> Dict[str, Any]:
    eligible = [
        item
        for item in as_list(runtime_registry.get("packages"))
        if isinstance(item, dict)
        and item.get("status") == "READY_FOR_LAUNCH_REVIEW"
        and item.get("launch_authorized") is False
    ]
    selected = eligible[0] if len(eligible) == 1 else None

    return {
        "schema": "archon_launch_authorization_request_v1",
        "authorize": False,
        "authorization_id": None,
        "runtime_id": selected.get("runtime_id") if selected else None,
        "expected_runtime_hash": (
            selected.get("runtime_hash") if selected else None
        ),
        "expected_runtime_registry_hash": runtime_registry.get("content_hash"),
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_authorization_id": existing_request.get(
            "last_consumed_authorization_id"
        ),
        "instructions": {
            "required_confirmation": "AUTHORIZE_EXPERIMENT_LAUNCH",
            "ready_runtime_required": True,
            "authorization_does_not_execute": True,
            "manual_request_required": True,
            "inactive_template_auto_refresh": True,
        },
    }


def validate_runtime_package(
    package: Dict[str, Any],
    index_entry: Dict[str, Any],
) -> List[str]:
    failures: List[str] = []

    if package.get("status") != "READY_FOR_LAUNCH_REVIEW":
        failures.append("RUNTIME_NOT_READY_FOR_LAUNCH_REVIEW")

    if as_list(package.get("unresolved_fields")):
        failures.append("RUNTIME_HAS_UNRESOLVED_FIELDS")

    runtime = as_dict(package.get("runtime"))
    if not runtime:
        failures.append("RUNTIME_SPEC_MISSING")
    else:
        if canonical_hash(runtime) != package.get("runtime_hash"):
            failures.append("RUNTIME_HASH_MISMATCH")

    if package.get("runtime_id") != index_entry.get("runtime_id"):
        failures.append("RUNTIME_ID_MISMATCH")

    if package.get("runtime_hash") != index_entry.get("runtime_hash"):
        failures.append("REGISTRY_RUNTIME_HASH_MISMATCH")

    if index_entry.get("status") != "READY_FOR_LAUNCH_REVIEW":
        failures.append("REGISTRY_RUNTIME_NOT_READY")

    if index_entry.get("launch_authorized") is not False:
        failures.append("REGISTRY_ALREADY_AUTHORIZED")

    if as_dict(package.get("launch_authorization")).get(
        "authorized"
    ) is not False:
        failures.append("PACKAGE_ALREADY_AUTHORIZED")

    if as_dict(package.get("policy")).get("launch_authorized") is not False:
        failures.append("PACKAGE_POLICY_ALREADY_AUTHORIZED")

    run_matrix = as_list(runtime.get("run_matrix"))
    if not run_matrix:
        failures.append("RUN_MATRIX_EMPTY")

    for row in run_matrix:
        if not isinstance(row, dict):
            failures.append("RUN_MATRIX_ROW_INVALID")
            continue
        for field in (
            "run_id",
            "role",
            "seed",
            "field_size",
            "topology",
            "boundary_condition",
            "duration_ticks",
            "output_directory",
        ):
            if row.get(field) in (None, "", []):
                failures.append(f"RUN_MATRIX_FIELD_MISSING:{field}")

    return sorted(set(failures))


def authorize_runtime(
    experiments_root: Path,
    runtime_registry: Dict[str, Any],
    request: Dict[str, Any],
    existing_registry: Dict[str, Any],
) -> Dict[str, Any]:
    if request.get("authorize") is not True:
        return {
            "schema": "archon_launch_authorization_result_v1",
            "status": "NO_AUTHORIZATION_REQUEST",
            "authorized": False,
            "reason": None,
        }

    authorization_id = normalize_text(request.get("authorization_id"))
    runtime_id = normalize_text(request.get("runtime_id"))
    requested_by = normalize_text(request.get("requested_by"))
    confirmation = normalize_text(request.get("confirmation"))

    failures: List[str] = []
    if not authorization_id:
        failures.append("AUTHORIZATION_ID_MISSING")
    if not runtime_id:
        failures.append("RUNTIME_ID_MISSING")
    if not requested_by:
        failures.append("REQUESTED_BY_MISSING")
    if confirmation != "AUTHORIZE_EXPERIMENT_LAUNCH":
        failures.append("CONFIRMATION_INVALID")

    if request.get("expected_runtime_registry_hash") != runtime_registry.get(
        "content_hash"
    ):
        failures.append("RUNTIME_REGISTRY_HASH_MISMATCH")

    packages = {
        str(item.get("runtime_id")): item
        for item in as_list(runtime_registry.get("packages"))
        if isinstance(item, dict) and item.get("runtime_id")
    }
    index_entry = packages.get(runtime_id or "")
    package: Dict[str, Any] = {}

    if index_entry is None:
        failures.append("RUNTIME_NOT_FOUND")
    else:
        package_path = Path(str(index_entry.get("package_path")))
        package = load_json(package_path, {})
        if not isinstance(package, dict) or not package:
            failures.append("RUNTIME_PACKAGE_MISSING_OR_INVALID")
        else:
            if request.get("expected_runtime_hash") != package.get(
                "runtime_hash"
            ):
                failures.append("EXPECTED_RUNTIME_HASH_MISMATCH")
            failures.extend(validate_runtime_package(package, index_entry))

    existing_authorizations = {
        str(item.get("authorization_id")): item
        for item in as_list(existing_registry.get("authorizations"))
        if isinstance(item, dict) and item.get("authorization_id")
    }
    existing_by_runtime = {
        str(item.get("runtime_id")): item
        for item in as_list(existing_registry.get("authorizations"))
        if (
            isinstance(item, dict)
            and item.get("runtime_id")
            and item.get("lifecycle_status", "ACTIVE") == "ACTIVE"
            and item.get("superseded") is not True
        )
    }

    if authorization_id and authorization_id in existing_authorizations:
        failures.append("AUTHORIZATION_ID_REPLAY")
    if runtime_id and runtime_id in existing_by_runtime:
        failures.append("RUNTIME_ALREADY_AUTHORIZED")

    if failures:
        return {
            "schema": "archon_launch_authorization_result_v1",
            "status": "REFUSED",
            "authorized": False,
            "authorization_id": authorization_id,
            "runtime_id": runtime_id,
            "reasons": sorted(set(failures)),
        }

    assert index_entry is not None
    package_path = Path(str(index_entry.get("package_path")))

    package["launch_authorization"] = {
        "authorized": True,
        "authorization_id": authorization_id,
        "authorized_at": now_iso(),
        "authorized_by": requested_by,
        "confirmation": confirmation,
    }
    package["policy"]["launch_authorized"] = True
    package["policy"]["materialized_not_executed"] = True
    package["policy"]["separate_execution_stage_required"] = True
    package["status"] = "LAUNCH_AUTHORIZED"
    package["updated_at"] = now_iso()

    authorization_snapshot = {
        "runtime_id": runtime_id,
        "runtime_hash": package.get("runtime_hash"),
        "authorization_id": authorization_id,
        "authorized_at": package["launch_authorization"]["authorized_at"],
        "authorized_by": requested_by,
        "run_count": len(
            as_list(as_dict(package.get("runtime")).get("run_matrix"))
        ),
        "plan_id": as_dict(package.get("runtime")).get("plan_id"),
        "commit_id": as_dict(package.get("runtime")).get("commit_id"),
    }
    authorization_hash = canonical_hash(authorization_snapshot)

    atomic_write_json(package_path, package)

    receipt = {
        "schema": "archon_launch_authorization_receipt_v1",
        "status": "AUTHORIZED",
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "runtime_id": runtime_id,
        "runtime_hash": package.get("runtime_hash"),
        "package_hash": canonical_hash(package),
        "package_path": str(package_path),
        "authorized_at": authorization_snapshot["authorized_at"],
        "authorized_by": requested_by,
        "execution_started": False,
        "execution_authorized": True,
    }
    receipt_path = (
        experiments_root
        / "LaunchAuthorizationReceipts"
        / f"{authorization_id}.json"
    )
    atomic_write_json(receipt_path, receipt)

    return {
        "schema": "archon_launch_authorization_result_v1",
        "status": "AUTHORIZED",
        "authorized": True,
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "runtime_id": runtime_id,
        "runtime_hash": package.get("runtime_hash"),
        "package_hash": receipt["package_hash"],
        "package_path": str(package_path),
        "receipt_path": str(receipt_path),
        "execution_started": False,
        "execution_authorized": True,
    }


def verify_receipt(result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("status") != "AUTHORIZED":
        return {
            "schema": "archon_launch_authorization_receipt_verification_v1",
            "status": "NO_AUTHORIZATION",
            "verified": False,
        }

    package_path = Path(str(result.get("package_path")))
    receipt_path = Path(str(result.get("receipt_path")))
    package = load_json(package_path, {})
    receipt = load_json(receipt_path, {})
    failures: List[str] = []

    if not package:
        failures.append("PACKAGE_MISSING_OR_INVALID")
    if not receipt:
        failures.append("RECEIPT_MISSING_OR_INVALID")

    if package:
        if canonical_hash(package) != result.get("package_hash"):
            failures.append("PACKAGE_HASH_MISMATCH")
        launch = as_dict(package.get("launch_authorization"))
        if launch.get("authorized") is not True:
            failures.append("PACKAGE_NOT_AUTHORIZED")
        if launch.get("authorization_id") != result.get(
            "authorization_id"
        ):
            failures.append("PACKAGE_AUTHORIZATION_ID_MISMATCH")
        if package.get("status") != "LAUNCH_AUTHORIZED":
            failures.append("PACKAGE_STATUS_INVALID")
        if as_dict(package.get("policy")).get(
            "materialized_not_executed"
        ) is not True:
            failures.append("PACKAGE_EXECUTION_BOUNDARY_INVALID")

    if receipt:
        if receipt.get("authorization_id") != result.get(
            "authorization_id"
        ):
            failures.append("RECEIPT_AUTHORIZATION_ID_MISMATCH")
        if receipt.get("runtime_id") != result.get("runtime_id"):
            failures.append("RECEIPT_RUNTIME_ID_MISMATCH")
        if receipt.get("runtime_hash") != result.get("runtime_hash"):
            failures.append("RECEIPT_RUNTIME_HASH_MISMATCH")
        if receipt.get("package_hash") != result.get("package_hash"):
            failures.append("RECEIPT_PACKAGE_HASH_MISMATCH")
        if receipt.get("execution_started") is not False:
            failures.append("RECEIPT_EXECUTION_STATE_INVALID")

    return {
        "schema": "archon_launch_authorization_receipt_verification_v1",
        "status": "VERIFIED" if not failures else "FAILED",
        "verified": not failures,
        "failures": failures,
        "authorization_id": result.get("authorization_id"),
        "runtime_id": result.get("runtime_id"),
        "runtime_hash": result.get("runtime_hash"),
        "package_hash": result.get("package_hash"),
    }


def update_runtime_registry(
    runtime_registry: Dict[str, Any],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    packages = [
        dict(item)
        for item in as_list(runtime_registry.get("packages"))
        if isinstance(item, dict)
    ]

    if result.get("status") == "AUTHORIZED":
        for item in packages:
            if item.get("runtime_id") == result.get("runtime_id"):
                item["status"] = "LAUNCH_AUTHORIZED"
                item["launch_authorized"] = True
                item["updated_at"] = now_iso()

    summary = as_dict(runtime_registry.get("summary"))
    summary["launch_authorized_count"] = sum(
        1 for item in packages if item.get("launch_authorized") is True
    )
    summary["ready_for_launch_review_count"] = sum(
        1
        for item in packages
        if item.get("status") == "READY_FOR_LAUNCH_REVIEW"
    )

    payload = dict(runtime_registry)
    payload["generated_at"] = now_iso()
    payload["summary"] = summary
    payload["packages"] = packages
    payload["content_hash"] = canonical_hash({
        "summary": summary,
        "packages": packages,
        "blocked_plans": as_list(runtime_registry.get("blocked_plans")),
        "source_registry": as_dict(runtime_registry.get("source_registry")),
    })
    return payload


def update_authorization_registry(
    existing: Dict[str, Any],
    result: Dict[str, Any],
    verification: Dict[str, Any],
) -> Dict[str, Any]:
    rows = [
        item
        for item in as_list(existing.get("authorizations"))
        if isinstance(item, dict)
    ]

    if result.get("status") == "AUTHORIZED":
        rows.append({
            "authorization_id": result.get("authorization_id"),
            "authorization_hash": result.get("authorization_hash"),
            "runtime_id": result.get("runtime_id"),
            "runtime_hash": result.get("runtime_hash"),
            "package_hash": result.get("package_hash"),
            "package_path": result.get("package_path"),
            "receipt_path": result.get("receipt_path"),
            "verification_status": verification.get("status"),
            "authorized_at": now_iso(),
            "execution_started": False,
            "lifecycle_status": "ACTIVE",
            "superseded": False,
        })

    unique: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        authorization_id = str(item.get("authorization_id") or "")
        if authorization_id:
            unique[authorization_id] = item

    ordered = sorted(unique.values(), key=lambda x: str(x.get("authorization_id")))
    payload = {
        "schema": "archon_launch_authorization_registry_v1",
        "version": VERSION,
        "updated_at": now_iso(),
        "authorization_count": len(ordered),
        "authorizations": ordered,
        "policy": {
            "authorization_does_not_execute": True,
            "execution_started": False,
            "separate_execution_stage_required": True,
        },
    }
    payload["content_hash"] = canonical_hash({
        "authorizations": ordered,
        "policy": payload["policy"],
    })
    return payload


def render_markdown(
    result: Dict[str, Any],
    verification: Dict[str, Any],
    authorization_registry: Dict[str, Any],
) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Status: **{result.get('status')}**",
        f"- Verification: **{verification.get('status')}**",
        f"- Authorization ID: `{result.get('authorization_id') or '-'}`",
        f"- Runtime ID: `{result.get('runtime_id') or '-'}`",
        (
            "- Authorization registry count: "
            f"**{authorization_registry.get('authorization_count', 0)}**"
        ),
        "- Execution started: **false**",
        "",
        "## Safety boundary",
        "",
        "- Authorization does not execute the experiment.",
        "- Runtime and registry hashes are verified before authorization.",
        "- A separate execution stage is still required.",
        "- Replay and duplicate runtime authorization are refused.",
        "- Scientific results are not created by this gateway.",
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
            "Authorization request JSON. Default: "
            "<analysis-root>/Experiments/launch_authorization_request.json"
        ),
    )
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).resolve()
    experiments_root = analysis_root / "Experiments"

    runtime_registry_path = (
        experiments_root / "experiment_runtime_registry.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments_root / "launch_authorization_request.json"
    )
    result_path = experiments_root / "launch_authorization_result.json"
    verification_path = (
        experiments_root
        / "launch_authorization_receipt_verification.json"
    )
    authorization_registry_path = (
        experiments_root / "launch_authorization_registry.json"
    )
    markdown_path = experiments_root / "launch_authorization.md"

    runtime_registry = load_json(runtime_registry_path, {})
    if not isinstance(runtime_registry, dict) or not runtime_registry:
        raise RuntimeError(
            f"Missing or invalid runtime registry: {runtime_registry_path}"
        )

    existing_request = load_json(request_path, {})
    if not isinstance(existing_request, dict):
        existing_request = {}

    if (
        not request_path.exists()
        or existing_request.get("authorize") is not True
    ):
        atomic_write_json(
            request_path,
            build_request_template(runtime_registry, existing_request),
        )

    request = load_json(request_path, {})
    if not isinstance(request, dict):
        request = {}

    existing_authorization_registry = load_json(
        authorization_registry_path,
        {},
    )
    if not isinstance(existing_authorization_registry, dict):
        existing_authorization_registry = {}

    result = authorize_runtime(
        experiments_root,
        runtime_registry,
        request,
        existing_authorization_registry,
    )
    verification = verify_receipt(result)
    updated_runtime_registry = update_runtime_registry(
        runtime_registry,
        result,
    )
    authorization_registry = update_authorization_registry(
        existing_authorization_registry,
        result,
        verification,
    )

    atomic_write_json(result_path, result)
    atomic_write_json(verification_path, verification)
    atomic_write_json(runtime_registry_path, updated_runtime_registry)
    atomic_write_json(
        authorization_registry_path,
        authorization_registry,
    )
    markdown_path.write_text(
        render_markdown(result, verification, authorization_registry),
        encoding="utf-8",
    )

    if result.get("status") == "AUTHORIZED":
        atomic_write_json(
            request_path,
            {
                "schema": "archon_launch_authorization_request_v1",
                "authorize": False,
                "authorization_id": None,
                "runtime_id": None,
                "expected_runtime_hash": None,
                "expected_runtime_registry_hash": None,
                "requested_at": None,
                "requested_by": None,
                "confirmation": None,
                "last_consumed_authorization_id": result.get(
                    "authorization_id"
                ),
                "instructions": {
                    "required_confirmation": (
                        "AUTHORIZE_EXPERIMENT_LAUNCH"
                    ),
                    "ready_runtime_required": True,
                    "authorization_does_not_execute": True,
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
    print(
        f"Authorization: {result.get('authorization_id') or '-'}"
    )
    print(f"Runtime ID:   {result.get('runtime_id') or '-'}")
    print(
        f"Registry:     "
        f"{authorization_registry.get('authorization_count', 0)} authorized"
    )
    print("Execution:    NOT STARTED")
    print(f"Result JSON:  {result_path}")
    print(f"Registry:     {authorization_registry_path}")
    print(f"Request:      {request_path}")
    print("=" * 72)

    return 0 if result.get("status") != "REFUSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
