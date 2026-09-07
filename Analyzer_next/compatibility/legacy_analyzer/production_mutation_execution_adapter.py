#!/usr/bin/env python3
"""Materialize one verified protocol arm as an isolated Observer rule file.

This adapter is deliberately narrow.  It supports only the pre-run,
single-parameter mutation contract emitted by the Scientific Protocol
Resolver.  Canonical Atlas files are read-only inputs; every derived rule and
its provenance are written beneath the mutation-runs tree.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Observer.observer_mutation_engine import (
    atomic_json,
    capture_baseline_provenance,
    diff_payload,
    mutate_single_parameter,
    stable_payload_hash,
)


VERSION = "1.0"
ADAPTER_ID = "ARCHON_MUTATION_RULE_FILE_V2"
SUPPORTED_APPLICATION = "PRE_RUN_RULE_MUTATION"
SUPPORTED_MODE = "single_parameter"


class MutationAdapterError(RuntimeError):
    """Fail-closed mutation materialization error."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MutationAdapterError(
            f"JSON_INVALID:{path}:{type(exc).__name__}"
        ) from exc
    if not isinstance(payload, dict):
        raise MutationAdapterError(f"JSON_OBJECT_REQUIRED:{path}")
    return payload


def normalized_rule(payload: Dict[str, Any]) -> Dict[str, Any]:
    rule = as_dict(payload.get("rule")) or payload
    return copy.deepcopy(rule)


def resolve_canonical_rule(
    world_atlas_directory: Path,
    rule_id: int,
) -> Tuple[Dict[str, Any], Path, str]:
    root = world_atlas_directory.expanduser().resolve()
    if not root.is_dir():
        raise MutationAdapterError(f"WORLD_ATLAS_INVALID:{root}")

    token = f"{int(rule_id):05d}"
    paths = set(root.rglob(f"rule_{token}_*/rule.json"))
    paths.update(root.rglob(f"rule_{token}.json"))
    candidates: List[Tuple[Path, Dict[str, Any], str]] = []
    for path in sorted(paths):
        try:
            rule = normalized_rule(read_json(path))
            candidate_id = int(rule.get("rule_id"))
        except (MutationAdapterError, TypeError, ValueError):
            continue
        if candidate_id != int(rule_id):
            continue
        candidates.append((path.resolve(), rule, stable_payload_hash(rule)))

    if not candidates:
        raise MutationAdapterError(
            f"CANONICAL_RULE_NOT_FOUND:RULE-{int(rule_id):05d}"
        )
    hashes = {item[2] for item in candidates}
    if len(hashes) != 1:
        detail = ",".join(sorted(hashes))
        raise MutationAdapterError(
            f"CANONICAL_RULE_AMBIGUOUS:RULE-{int(rule_id):05d}:{detail}"
        )
    chosen = candidates[0]
    return chosen[1], chosen[0], chosen[2]


def validate_protocol_arm(
    perturbation: Dict[str, Any],
) -> Tuple[str, str, Dict[str, Any], str, float]:
    protocol_id = text(perturbation.get("protocol_id"))
    protocol_hash = text(perturbation.get("protocol_hash"))
    arm = as_dict(perturbation.get("arm"))
    capability = as_dict(perturbation.get("execution_capability"))

    failures: List[str] = []
    if not protocol_id:
        failures.append("PROTOCOL_ID_MISSING")
    if not protocol_hash or len(protocol_hash) != 64:
        failures.append("PROTOCOL_HASH_INVALID")
    if capability.get("required_adapter") != ADAPTER_ID:
        failures.append("MUTATION_ADAPTER_ID_MISMATCH")
    if capability.get("available") is not True:
        failures.append("MUTATION_ADAPTER_NOT_AVAILABLE")
    if arm.get("mode") != SUPPORTED_MODE:
        failures.append("MUTATION_MODE_UNSUPPORTED")
    if arm.get("application") != SUPPORTED_APPLICATION:
        failures.append("MUTATION_APPLICATION_UNSUPPORTED")

    parameter = text(arm.get("parameter"))
    if not parameter:
        failures.append("MUTATION_PARAMETER_MISSING")
    try:
        intensity = float(arm.get("intensity"))
    except (TypeError, ValueError):
        intensity = 0.0
    if intensity <= 0:
        failures.append("MUTATION_INTENSITY_INVALID")
    if failures:
        raise MutationAdapterError(";".join(sorted(set(failures))))
    assert protocol_id is not None
    assert protocol_hash is not None
    assert parameter is not None
    return protocol_id, protocol_hash, arm, parameter, intensity


def mutation_seed(
    *,
    protocol_hash: str,
    arm_id: str,
    run_id: str,
    experiment_seed: int,
    attempt: int,
) -> int:
    material = {
        "protocol_hash": protocol_hash,
        "arm_id": arm_id,
        "run_id": run_id,
        "experiment_seed": int(experiment_seed),
        "attempt": int(attempt),
    }
    return int(canonical_hash(material)[:15], 16)


def immutable_manifest_core(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: manifest.get(key)
        for key in (
            "schema",
            "version",
            "adapter_id",
            "mutation_id",
            "canonical_parent_rule_id",
            "canonical_parent_hash",
            "canonical_parent_source",
            "mutated_hash",
            "mutation_mode",
            "mutation_parameter",
            "mutation_intensity",
            "mutation_seed",
            "change_count",
            "changes",
            "protocol",
            "run_identity",
            "canonical_promotion",
            "baseline_provenance",
            "execution_control",
        )
    }


def verify_existing(
    *,
    run_dir: Path,
    expected_materialization_hash: str,
) -> Dict[str, Any]:
    manifest_path = run_dir / "mutation_manifest.json"
    original_path = run_dir / "original_rule.json"
    mutated_path = run_dir / "mutated_rule.json"
    diff_path = run_dir / "mutation_diff.json"
    required = (manifest_path, original_path, mutated_path, diff_path)
    if not all(path.is_file() for path in required):
        raise MutationAdapterError(
            f"MUTATION_MATERIALIZATION_INCOMPLETE:{run_dir}"
        )
    manifest = read_json(manifest_path)
    if manifest.get("materialization_hash") != expected_materialization_hash:
        raise MutationAdapterError(
            f"MUTATION_MATERIALIZATION_ID_COLLISION:{run_dir.name}"
        )
    if canonical_hash(immutable_manifest_core(manifest)) != (
        expected_materialization_hash
    ):
        raise MutationAdapterError(
            f"MUTATION_MANIFEST_HASH_MISMATCH:{run_dir.name}"
        )
    original = read_json(original_path)
    mutated = read_json(mutated_path)
    if stable_payload_hash(original) != manifest.get(
        "canonical_parent_hash"
    ):
        raise MutationAdapterError(
            f"MUTATION_PARENT_FILE_HASH_MISMATCH:{run_dir.name}"
        )
    if stable_payload_hash(mutated) != manifest.get("mutated_hash"):
        raise MutationAdapterError(
            f"MUTATED_RULE_FILE_HASH_MISMATCH:{run_dir.name}"
        )
    if not as_list(manifest.get("changes")):
        raise MutationAdapterError(
            f"MUTATION_HAS_NO_CHANGES:{run_dir.name}"
        )
    return {
        "status": "REUSED",
        "mutation_id": manifest.get("mutation_id"),
        "run_dir": run_dir,
        "rule_file": mutated_path,
        "rule_file_sha256": file_sha256(mutated_path),
        "manifest_file": manifest_path,
        "manifest_file_sha256": file_sha256(manifest_path),
        "manifest": manifest,
    }


def materialize_protocol_arm(
    *,
    world_atlas_directory: Path,
    results_directory: Path,
    rule_id: int,
    perturbation: Dict[str, Any],
    run_id: str,
    task_id: str,
    experiment_id: str,
    condition_id: str,
    replicate_index: int,
    experiment_seed: int,
    run_output_directory: Path,
) -> Dict[str, Any]:
    (
        protocol_id,
        protocol_hash,
        arm,
        parameter,
        intensity,
    ) = validate_protocol_arm(perturbation)
    arm_id = text(arm.get("arm_id"))
    if not arm_id:
        raise MutationAdapterError("MUTATION_ARM_ID_MISSING")

    original, parent_source, parent_hash = resolve_canonical_rule(
        world_atlas_directory,
        int(rule_id),
    )
    mutated: Optional[Dict[str, Any]] = None
    chosen_seed: Optional[int] = None
    changes: List[Dict[str, Any]] = []
    for attempt in range(32):
        candidate_seed = mutation_seed(
            protocol_hash=protocol_hash,
            arm_id=arm_id,
            run_id=run_id,
            experiment_seed=experiment_seed,
            attempt=attempt,
        )
        import random

        candidate = mutate_single_parameter(
            original,
            parameter,
            intensity,
            random.Random(candidate_seed),
        )
        candidate_changes = diff_payload(original, candidate)
        if candidate_changes:
            mutated = candidate
            chosen_seed = candidate_seed
            changes = candidate_changes
            break
    if mutated is None or chosen_seed is None:
        raise MutationAdapterError(
            f"MUTATION_COULD_NOT_CHANGE_PARAMETER:{parameter}"
        )

    mutated_hash = stable_payload_hash(mutated)
    if mutated_hash == parent_hash:
        raise MutationAdapterError("MUTATED_RULE_EQUALS_CANONICAL_PARENT")
    baseline = capture_baseline_provenance(
        original_rule=original,
        results_root=results_directory,
    )
    manifest = {
        "schema": "archon_observer_mutation_run_v2",
        "version": VERSION,
        "adapter_id": ADAPTER_ID,
        "mutation_id": None,
        "canonical_parent_rule_id": int(rule_id),
        "canonical_parent_hash": parent_hash,
        "canonical_parent_source": str(parent_source),
        "mutated_hash": mutated_hash,
        "mutation_mode": SUPPORTED_MODE,
        "mutation_parameter": parameter,
        "mutation_intensity": intensity,
        "mutation_seed": chosen_seed,
        "change_count": len(changes),
        "changes": changes,
        "protocol": {
            "protocol_id": protocol_id,
            "protocol_hash": protocol_hash,
            "arm_id": arm_id,
            "arm_hash": canonical_hash(arm),
            "application": arm.get("application"),
        },
        "run_identity": {
            "run_id": run_id,
            "task_id": task_id,
            "experiment_id": experiment_id,
            "condition_id": condition_id,
            "replicate_index": int(replicate_index),
            "experiment_seed": int(experiment_seed),
            "run_output_directory": str(
                run_output_directory.expanduser().resolve()
            ),
        },
        "canonical_promotion": False,
        "baseline_provenance": baseline,
        "execution_control": {
            "policy": "matched_protocol_arm",
            "target_final_tick": None,
            "comparison_reference_tick": (
                baseline.get("samples_final_tick")
                if baseline.get("status") == "resolved"
                else None
            ),
            "disable_auto_stop": False,
            "canonical_promotion": False,
        },
    }
    identity_hash = canonical_hash({
        "adapter_id": ADAPTER_ID,
        "protocol_hash": protocol_hash,
        "arm_id": arm_id,
        "run_id": run_id,
        "task_id": task_id,
        "parent_hash": parent_hash,
        "mutated_hash": mutated_hash,
    })
    mutation_id = (
        f"MUT-{int(rule_id):05d}-PROD-{identity_hash[:16].upper()}"
    )
    manifest["mutation_id"] = mutation_id
    materialization_hash = canonical_hash(immutable_manifest_core(manifest))
    manifest["materialization_hash"] = materialization_hash

    root = (
        results_directory.expanduser().resolve()
        / "mutation_runs"
        / f"rule_{int(rule_id):05d}"
    )
    run_dir = root / mutation_id
    if run_dir.exists():
        return verify_existing(
            run_dir=run_dir,
            expected_materialization_hash=materialization_hash,
        )

    run_dir.mkdir(parents=True, exist_ok=False)
    manifest["created_at"] = now_iso()
    manifest["status"] = "prepared"
    manifest["paths"] = {
        "run_dir": str(run_dir),
        "original_rule": str(run_dir / "original_rule.json"),
        "mutated_rule": str(run_dir / "mutated_rule.json"),
        "mutation_diff": str(run_dir / "mutation_diff.json"),
        "mutation_manifest": str(run_dir / "mutation_manifest.json"),
        "run_output_directory": str(
            run_output_directory.expanduser().resolve()
        ),
    }
    atomic_json(run_dir / "original_rule.json", original)
    atomic_json(run_dir / "mutated_rule.json", mutated)
    atomic_json(run_dir / "mutation_diff.json", changes)
    atomic_json(run_dir / "mutation_manifest.json", manifest)
    return {
        "status": "MATERIALIZED",
        "mutation_id": mutation_id,
        "run_dir": run_dir,
        "rule_file": run_dir / "mutated_rule.json",
        "rule_file_sha256": file_sha256(run_dir / "mutated_rule.json"),
        "manifest_file": run_dir / "mutation_manifest.json",
        "manifest_file_sha256": file_sha256(
            run_dir / "mutation_manifest.json"
        ),
        "manifest": manifest,
    }
