"""Explicit compatibility repair for legacy experiment runtime policy files."""
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


def inspect_runtime_policy(path: str | Path) -> RuntimePolicyRepairResult:
    policy_path = Path(path).expanduser().resolve()
    payload = _load(policy_path)
    if not payload:
        return RuntimePolicyRepairResult(False, "POLICY_MISSING", f"runtime policy missing: {policy_path}")
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    seed_policy = defaults.get("seed_policy") if isinstance(defaults.get("seed_policy"), dict) else {}
    mode = str(defaults.get("initial_state_mode") or "").upper() or None
    replicates = int(seed_policy.get("replicates") or 1)
    seed_mode = str(seed_policy.get("mode") or "").upper()
    if mode == "CANONICAL_SEED" and replicates > 1 and seed_mode == "DETERMINISTIC_SERIES":
        return RuntimePolicyRepairResult(
            False,
            "LEGACY_PSEUDOREPLICATION_POLICY",
            f"legacy runtime policy uses CANONICAL_SEED with {replicates} deterministic replicates",
            previous_initial_state_mode=mode,
            effective_initial_state_mode="RANDOM_SEED",
        )
    return RuntimePolicyRepairResult(
        False,
        "POLICY_COMPATIBLE",
        f"runtime policy compatible: initial_state_mode={mode or 'unspecified'} replicates={replicates}",
        previous_initial_state_mode=mode,
        effective_initial_state_mode=mode,
    )


def repair_runtime_policy(path: str | Path) -> RuntimePolicyRepairResult:
    """Repair only the known self-contradictory legacy default.

    No plan/runtime package is edited here.  Reconciliation must be run after
    this explicit policy update so canonical target conditions and derived
    runtime packages are regenerated from the same effective policy.
    """
    policy_path = Path(path).expanduser().resolve()
    payload = _load(policy_path)
    if not payload:
        return RuntimePolicyRepairResult(False, "POLICY_MISSING", f"runtime policy missing: {policy_path}")
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    seed_policy = defaults.get("seed_policy") if isinstance(defaults.get("seed_policy"), dict) else {}
    mode = str(defaults.get("initial_state_mode") or "").upper()
    replicates = int(seed_policy.get("replicates") or 1)
    seed_mode = str(seed_policy.get("mode") or "").upper()
    if not (mode == "CANONICAL_SEED" and replicates > 1 and seed_mode == "DETERMINISTIC_SERIES"):
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
    migration = {
        "id": "OL2-EXPERIMENTS-FIX3-RANDOM-SEED-REPLICATES",
        "applied_at": _now(),
        "from": "CANONICAL_SEED",
        "to": "RANDOM_SEED",
        "reason": "multiple deterministic replicate seeds must create independent initial states",
    }
    if not any(isinstance(row, dict) and row.get("id") == migration["id"] for row in history):
        history.append(migration)
    payload["compatibility_migrations"] = history
    _atomic_json(policy_path, payload)
    return RuntimePolicyRepairResult(
        True,
        "LEGACY_PSEUDOREPLICATION_POLICY_REPAIRED",
        f"runtime policy migrated CANONICAL_SEED → RANDOM_SEED for {replicates} deterministic replicates",
        previous_initial_state_mode="CANONICAL_SEED",
        effective_initial_state_mode="RANDOM_SEED",
    )


__all__ = ["RuntimePolicyRepairResult", "inspect_runtime_policy", "repair_runtime_policy"]
