"""EXPERIMENTS-FIX4 compatibility repair for legacy implicit seed policy.

Older runtime policy files may omit ``defaults.initial_state_mode`` entirely.
The frozen legacy materializer interprets that omission as CANONICAL_SEED. With
multiple deterministic replicates this is the same pseudoreplication hazard as
an explicit CANONICAL_SEED value, so FIX4 makes the effective mode explicit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimePolicyRepairResult:
    changed: bool
    code: str
    message: str
    previous_initial_state_mode: str | None = None
    effective_initial_state_mode: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"runtime policy must be a JSON object: {path}")
    return payload


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _state(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str | None, int, str]:
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    seed_policy = defaults.get("seed_policy") if isinstance(defaults.get("seed_policy"), dict) else {}
    raw = defaults.get("initial_state_mode")
    explicit_mode = str(raw or "").strip().upper() or None
    replicates = int(seed_policy.get("replicates") or 1)
    seed_mode = str(seed_policy.get("mode") or "").strip().upper()
    return defaults, seed_policy, explicit_mode, replicates, seed_mode


def inspect_runtime_policy(path: str | Path) -> RuntimePolicyRepairResult:
    policy_path = Path(path).expanduser().resolve()
    payload = _load(policy_path)
    if not payload:
        return RuntimePolicyRepairResult(False, "POLICY_MISSING", f"runtime policy missing: {policy_path}")

    _defaults, _seed_policy, explicit_mode, replicates, seed_mode = _state(payload)
    deterministic_multi = replicates > 1 and seed_mode == "DETERMINISTIC_SERIES"

    # Important: the frozen materializer falls back to CANONICAL_SEED when the
    # key is absent.  Treat that implicit value exactly like an explicit one.
    if explicit_mode is None and deterministic_multi:
        return RuntimePolicyRepairResult(
            False,
            "LEGACY_IMPLICIT_CANONICAL_SEED_POLICY",
            (
                "legacy runtime policy omits initial_state_mode; frozen materializer "
                f"therefore falls back to CANONICAL_SEED for {replicates} deterministic replicates"
            ),
            previous_initial_state_mode=None,
            effective_initial_state_mode="RANDOM_SEED",
        )
    if explicit_mode == "CANONICAL_SEED" and deterministic_multi:
        return RuntimePolicyRepairResult(
            False,
            "LEGACY_PSEUDOREPLICATION_POLICY",
            f"legacy runtime policy uses CANONICAL_SEED with {replicates} deterministic replicates",
            previous_initial_state_mode=explicit_mode,
            effective_initial_state_mode="RANDOM_SEED",
        )
    return RuntimePolicyRepairResult(
        False,
        "POLICY_COMPATIBLE",
        f"runtime policy compatible: initial_state_mode={explicit_mode or 'unspecified'} replicates={replicates}",
        previous_initial_state_mode=explicit_mode,
        effective_initial_state_mode=explicit_mode,
    )


def repair_runtime_policy(path: str | Path) -> RuntimePolicyRepairResult:
    """Repair only the known legacy multi-replicate canonical-seed cases.

    This function never edits committed plan/runtime packages.  It updates the
    explicit launcher-owned runtime policy, after which normal full
    reconciliation regenerates derived runtime packages from frozen plans.
    """
    policy_path = Path(path).expanduser().resolve()
    payload = _load(policy_path)
    if not payload:
        return RuntimePolicyRepairResult(False, "POLICY_MISSING", f"runtime policy missing: {policy_path}")

    defaults, _seed_policy, explicit_mode, replicates, seed_mode = _state(payload)
    deterministic_multi = replicates > 1 and seed_mode == "DETERMINISTIC_SERIES"
    repairable = deterministic_multi and explicit_mode in {None, "CANONICAL_SEED"}
    if not repairable:
        inspected = inspect_runtime_policy(policy_path)
        return RuntimePolicyRepairResult(
            False,
            inspected.code,
            inspected.message,
            inspected.previous_initial_state_mode,
            inspected.effective_initial_state_mode,
        )

    defaults = dict(defaults)
    defaults["initial_state_mode"] = "RANDOM_SEED"
    payload["defaults"] = defaults

    history = payload.get("compatibility_migrations")
    if not isinstance(history, list):
        history = []
    migration_id = "OL2-EXPERIMENTS-FIX4-EXPLICIT-RANDOM-SEED-MULTIREPLICATE"
    migration = {
        "id": migration_id,
        "applied_at": _now(),
        "from": explicit_mode or "IMPLICIT_CANONICAL_SEED_FALLBACK",
        "to": "RANDOM_SEED",
        "reason": "multiple deterministic replicate seeds must create independent initial states",
    }
    if not any(isinstance(row, dict) and row.get("id") == migration_id for row in history):
        history.append(migration)
    payload["compatibility_migrations"] = history
    _atomic_json(policy_path, payload)

    code = (
        "LEGACY_IMPLICIT_CANONICAL_SEED_POLICY_REPAIRED"
        if explicit_mode is None
        else "LEGACY_PSEUDOREPLICATION_POLICY_REPAIRED"
    )
    origin = explicit_mode or "implicit CANONICAL_SEED fallback"
    return RuntimePolicyRepairResult(
        True,
        code,
        f"runtime policy migrated {origin} → RANDOM_SEED for {replicates} deterministic replicates",
        previous_initial_state_mode=explicit_mode,
        effective_initial_state_mode="RANDOM_SEED",
    )


__all__ = ["RuntimePolicyRepairResult", "inspect_runtime_policy", "repair_runtime_policy"]
