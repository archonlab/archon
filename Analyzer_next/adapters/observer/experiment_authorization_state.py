"""EXPERIMENTS-FIX6 authorization/runtime reconciliation helpers.

The frozen Stage 6.4 materializer intentionally publishes *unauthorized*
runtime packages.  Re-running it after Stage 6.5 authorization therefore
resets package/registry launch flags while the durable authorization registry
remains ACTIVE.  These helpers keep the two registries coherent without
weakening authorization checks or editing scientific plan/runtime contents.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any


class AuthorizationStateError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {} if default is None else default
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizationStateError(f"cannot read {path}: {exc}") from exc


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _resolve_path(project_root: Path, raw: Any) -> Path:
    path = Path(str(raw or "")).expanduser()
    if not path.is_absolute():
        path = (project_root / path).resolve()
    return path


@dataclass(frozen=True, slots=True)
class AuthorizedRuntimeSnapshot:
    runtime_id: str
    runtime_hash: str
    authorization_id: str
    registry_entry: dict[str, Any]
    authorization_entry: dict[str, Any]
    package_path: Path
    package: dict[str, Any]
    receipt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AuthorizationReconcileResult:
    preserved: tuple[str, ...] = ()
    superseded: tuple[str, ...] = ()
    message: str = ""


def _active_authorizations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in _as_list(payload.get("authorizations"))
        if isinstance(row, dict)
        and row.get("lifecycle_status", "ACTIVE") == "ACTIVE"
        and row.get("superseded") is not True
    ]


def _validate_receipt_identity(auth: dict[str, Any], receipt: dict[str, Any]) -> None:
    if not receipt:
        raise AuthorizationStateError("active authorization receipt is missing or invalid")
    checks = (
        ("authorization_id", auth.get("authorization_id")),
        ("runtime_id", auth.get("runtime_id")),
        ("runtime_hash", auth.get("runtime_hash")),
    )
    for field, expected in checks:
        if receipt.get(field) != expected:
            raise AuthorizationStateError(f"active authorization receipt {field} mismatch")
    if receipt.get("execution_started") is not False:
        raise AuthorizationStateError("active authorization receipt says execution already started")
    if auth.get("execution_started") is not False:
        raise AuthorizationStateError("authorization registry says execution already started")
    if auth.get("verification_status") != "VERIFIED":
        raise AuthorizationStateError("active authorization registry row is not VERIFIED")


def _write_authorization_registry(path: Path, payload: dict[str, Any]) -> None:
    rows = [dict(row) for row in _as_list(payload.get("authorizations")) if isinstance(row, dict)]
    policy = _as_dict(payload.get("policy")) or {
        "authorization_does_not_execute": True,
        "execution_started": False,
        "separate_execution_stage_required": True,
    }
    payload = dict(payload)
    payload["updated_at"] = _now()
    payload["authorization_count"] = len(rows)
    payload["authorizations"] = rows
    payload["policy"] = policy
    payload["content_hash"] = _canonical_hash({"authorizations": rows, "policy": policy})
    _atomic_json(path, payload)


def _write_runtime_registry(path: Path, payload: dict[str, Any]) -> None:
    rows = [dict(row) for row in _as_list(payload.get("packages")) if isinstance(row, dict)]
    summary = dict(_as_dict(payload.get("summary")))
    summary["launch_authorized_count"] = sum(
        1 for row in rows if row.get("status") == "LAUNCH_AUTHORIZED" and row.get("launch_authorized") is True
    )
    summary["ready_for_launch_review_count"] = sum(
        1 for row in rows if row.get("status") == "READY_FOR_LAUNCH_REVIEW"
    )
    summary["needs_runtime_resolution_count"] = sum(
        1 for row in rows if row.get("status") == "NEEDS_RUNTIME_RESOLUTION"
    )
    payload = dict(payload)
    payload["generated_at"] = _now()
    payload["summary"] = summary
    payload["packages"] = rows
    payload["content_hash"] = _canonical_hash({
        "summary": summary,
        "packages": rows,
        "blocked_plans": _as_list(payload.get("blocked_plans")),
        "source_registry": _as_dict(payload.get("source_registry")),
    })
    _atomic_json(path, payload)


def capture_consistent_authorized_runtimes(project_root: Path, experiments_root: Path) -> dict[str, AuthorizedRuntimeSnapshot]:
    project_root = Path(project_root).resolve()
    experiments_root = Path(experiments_root).resolve()
    runtime_registry = _as_dict(_load(experiments_root / "experiment_runtime_registry.json", {}))
    authorization_registry = _as_dict(_load(experiments_root / "launch_authorization_registry.json", {}))
    runtime_rows = {
        str(row.get("runtime_id")): dict(row)
        for row in _as_list(runtime_registry.get("packages"))
        if isinstance(row, dict) and row.get("runtime_id")
    }
    snapshots: dict[str, AuthorizedRuntimeSnapshot] = {}
    for auth in _active_authorizations(authorization_registry):
        runtime_id = str(auth.get("runtime_id") or "")
        entry = runtime_rows.get(runtime_id)
        if not runtime_id or entry is None:
            continue
        if entry.get("status") != "LAUNCH_AUTHORIZED" or entry.get("launch_authorized") is not True:
            continue
        package_path = _resolve_path(project_root, entry.get("package_path"))
        package = _as_dict(_load(package_path, {}))
        if package.get("status") != "LAUNCH_AUTHORIZED":
            continue
        launch = _as_dict(package.get("launch_authorization"))
        if launch.get("authorized") is not True or launch.get("authorization_id") != auth.get("authorization_id"):
            continue
        if package.get("runtime_hash") != auth.get("runtime_hash") or entry.get("runtime_hash") != auth.get("runtime_hash"):
            continue
        receipt_path = _resolve_path(project_root, auth.get("receipt_path"))
        receipt = _as_dict(_load(receipt_path, {}))
        _validate_receipt_identity(auth, receipt)
        if receipt.get("package_hash") != _canonical_hash(package):
            raise AuthorizationStateError(f"authorized runtime {runtime_id} package no longer matches VERIFIED receipt")
        snapshots[runtime_id] = AuthorizedRuntimeSnapshot(
            runtime_id=runtime_id,
            runtime_hash=str(auth.get("runtime_hash")),
            authorization_id=str(auth.get("authorization_id")),
            registry_entry=entry,
            authorization_entry=auth,
            package_path=package_path,
            package=package,
            receipt=receipt,
        )
    return snapshots


def reconcile_after_materialization(
    project_root: Path,
    experiments_root: Path,
    snapshots: dict[str, AuthorizedRuntimeSnapshot],
) -> AuthorizationReconcileResult:
    """Restore unchanged authorized packages, supersede changed authorizations."""
    if not snapshots:
        return AuthorizationReconcileResult(message="no pre-existing consistent authorizations")
    project_root = Path(project_root).resolve()
    experiments_root = Path(experiments_root).resolve()
    runtime_path = experiments_root / "experiment_runtime_registry.json"
    auth_path = experiments_root / "launch_authorization_registry.json"
    runtime_registry = _as_dict(_load(runtime_path, {}))
    auth_registry = _as_dict(_load(auth_path, {}))
    runtime_rows = [dict(row) for row in _as_list(runtime_registry.get("packages")) if isinstance(row, dict)]
    auth_rows = [dict(row) for row in _as_list(auth_registry.get("authorizations")) if isinstance(row, dict)]
    runtime_by_id = {str(row.get("runtime_id") or ""): row for row in runtime_rows}
    auth_by_id = {str(row.get("authorization_id") or ""): row for row in auth_rows}
    preserved: list[str] = []
    superseded: list[str] = []
    now = _now()

    for runtime_id, snapshot in snapshots.items():
        current = runtime_by_id.get(runtime_id)
        auth = auth_by_id.get(snapshot.authorization_id)
        if auth is None:
            raise AuthorizationStateError(f"authorization {snapshot.authorization_id} disappeared during reconciliation")
        if current is not None and current.get("runtime_hash") == snapshot.runtime_hash:
            # Scientific runtime spec is unchanged. Restore the exact previously
            # VERIFIED authorized package bytes/data so receipt package_hash
            # remains valid, then restore the registry launch flags.
            _atomic_json(snapshot.package_path, snapshot.package)
            current["status"] = "LAUNCH_AUTHORIZED"
            current["launch_authorized"] = True
            current["updated_at"] = snapshot.registry_entry.get("updated_at") or now
            preserved.append(runtime_id)
            continue

        # Runtime identity/hash changed or disappeared. The old authorization
        # must not stay ACTIVE because it no longer authorizes the materialized
        # package. Preserve history, but retire it fail-closed.
        if auth.get("execution_started") is not False:
            raise AuthorizationStateError(
                f"cannot supersede authorization {snapshot.authorization_id}: execution_started is not false"
            )
        auth["lifecycle_status"] = "SUPERSEDED"
        auth["superseded"] = True
        auth["superseded_at"] = now
        auth["superseded_reason"] = "RUNTIME_REMATERIALIZED_HASH_CHANGED_OR_REMOVED"
        superseded.append(snapshot.authorization_id)

    runtime_registry["packages"] = runtime_rows
    auth_registry["authorizations"] = auth_rows
    _write_runtime_registry(runtime_path, runtime_registry)
    _write_authorization_registry(auth_path, auth_registry)
    return AuthorizationReconcileResult(
        preserved=tuple(preserved),
        superseded=tuple(superseded),
        message=(
            f"authorization state reconciled: preserved={len(preserved)} superseded={len(superseded)}"
        ),
    )


def retire_stale_active_authorization(
    project_root: Path,
    experiments_root: Path,
    runtime_id: str,
) -> str | None:
    """Retire a durable authorization whose runtime launch flags were reset.

    This recovery is intentionally narrow: exactly one ACTIVE VERIFIED receipt,
    execution must never have started, and the runtime package/registry must no
    longer claim LAUNCH_AUTHORIZED.  A consistent authorization is left alone.
    """
    project_root = Path(project_root).resolve()
    experiments_root = Path(experiments_root).resolve()
    runtime_id = str(runtime_id).strip()
    runtime_registry = _as_dict(_load(experiments_root / "experiment_runtime_registry.json", {}))
    auth_path = experiments_root / "launch_authorization_registry.json"
    auth_registry = _as_dict(_load(auth_path, {}))
    runtime_matches = [
        dict(row) for row in _as_list(runtime_registry.get("packages"))
        if isinstance(row, dict) and str(row.get("runtime_id") or "") == runtime_id
    ]
    if len(runtime_matches) != 1:
        raise AuthorizationStateError(f"runtime {runtime_id!r} is not uniquely registered")
    entry = runtime_matches[0]
    package_path = _resolve_path(project_root, entry.get("package_path"))
    package = _as_dict(_load(package_path, {}))
    active = [
        row for row in _active_authorizations(auth_registry)
        if str(row.get("runtime_id") or "") == runtime_id
    ]
    if not active:
        return None
    if len(active) != 1:
        raise AuthorizationStateError(f"runtime {runtime_id!r} has multiple ACTIVE authorizations")
    auth = active[0]

    package_consistent = (
        entry.get("status") == "LAUNCH_AUTHORIZED"
        and entry.get("launch_authorized") is True
        and package.get("status") == "LAUNCH_AUTHORIZED"
        and _as_dict(package.get("launch_authorization")).get("authorized") is True
        and _as_dict(package.get("launch_authorization")).get("authorization_id") == auth.get("authorization_id")
    )
    if package_consistent:
        return None

    receipt_path = _resolve_path(project_root, auth.get("receipt_path"))
    receipt = _as_dict(_load(receipt_path, {}))
    _validate_receipt_identity(auth, receipt)
    authorization_id = str(auth.get("authorization_id") or "")
    now = _now()
    rows = [dict(row) for row in _as_list(auth_registry.get("authorizations")) if isinstance(row, dict)]
    for row in rows:
        if str(row.get("authorization_id") or "") == authorization_id:
            row["lifecycle_status"] = "SUPERSEDED"
            row["superseded"] = True
            row["superseded_at"] = now
            row["superseded_reason"] = "RUNTIME_REMATERIALIZATION_RESET_LAUNCH_STATE"
            row["replacement_runtime_hash"] = package.get("runtime_hash")
    auth_registry["authorizations"] = rows
    _write_authorization_registry(auth_path, auth_registry)
    return authorization_id


__all__ = [
    "AuthorizationReconcileResult",
    "AuthorizationStateError",
    "AuthorizedRuntimeSnapshot",
    "capture_consistent_authorized_runtimes",
    "reconcile_after_materialization",
    "retire_stale_active_authorization",
]
