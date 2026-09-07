#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


VERSION = "1.0"
TITLE = "ARCHON Stage 6.4 Committed Plan → Runtime Materialization"


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


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_runtime_materialization_policy_v1",
        "version": VERSION,
        "defaults": {
            "field_size": [256, 256],
            "topology": "TORUS",
            "boundary_condition": "PERIODIC",
            # Three default replicates must correspond to three actual initial
            # states.  Observer ignores experiment_seed in canonical mode.
            "initial_state_mode": "RANDOM_SEED",
            "duration_ticks": 50000,
            "sample_interval": 10,
            "checkpoint_interval": 5000,
            "seed_policy": {
                "mode": "DETERMINISTIC_SERIES",
                "base_seed": 1000,
                "replicates": 3,
            },
            "resource_profile": {
                "device": "AUTO",
                "max_workers": 1,
                "memory_limit_mb": None,
                "timeout_seconds": None,
            },
        },
        "experiment_type_defaults": {
            "perturbation_recovery_test": {
                "duration_ticks": 100000,
                "initial_state_mode": "RANDOM_SEED",
                "perturbation": {
                    "type": "UNRESOLVED",
                    "strength": None,
                    "tick": 50000,
                    "recovery_window": 50000,
                },
                "control_mode": "MATCHED_UNPERTURBED",
            },
            "matched_control_study": {
                "duration_ticks": 50000,
                "control_mode": "MATCHED_CONTROL",
            },
            "cross_family_replication": {
                "duration_ticks": 50000,
                "control_mode": "WITHIN_FAMILY_REFERENCE",
            },
            "counterexample_search": {
                "duration_ticks": 50000,
                "search_budget": None,
                "control_mode": "POSITIVE_REFERENCE_COHORT",
            },
            "scope_condition_test": {
                "duration_ticks": 50000,
                "control_mode": "CANONICAL_CONDITION",
            },
            "controlled_action_validation": {
                "duration_ticks": 50000,
                "control_mode": "MATCHED_BASELINE",
            },
        },
        "policy": {
            "launch_authorized": False,
            "manual_resolution_required_for_unresolved_fields": True,
            "materialization_does_not_execute": True,
        },
    }


def merge_dict(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def verify_registry_entry(
    entry: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    failures: List[str] = []
    manifest_path_text = normalize_text(entry.get("manifest_path"))
    if not manifest_path_text:
        return None, ["MANIFEST_PATH_MISSING"]

    manifest_path = Path(manifest_path_text)
    manifest = load_json(manifest_path, {})
    if not isinstance(manifest, dict) or not manifest:
        return None, ["MANIFEST_MISSING_OR_INVALID"]

    if canonical_hash(manifest) != entry.get("manifest_hash"):
        failures.append("MANIFEST_HASH_MISMATCH")

    plan = as_dict(manifest.get("plan"))
    if not plan:
        failures.append("PLAN_MISSING")
    else:
        if canonical_hash(plan) != manifest.get("plan_hash"):
            failures.append("PLAN_CONTENT_HASH_MISMATCH")
        if manifest.get("plan_hash") != entry.get("plan_hash"):
            failures.append("REGISTRY_PLAN_HASH_MISMATCH")

    if manifest.get("commit_id") != entry.get("commit_id"):
        failures.append("COMMIT_ID_MISMATCH")
    if plan.get("draft_id") != entry.get("draft_id"):
        failures.append("DRAFT_ID_MISMATCH")
    if plan.get("plan_id") != entry.get("plan_id"):
        failures.append("PLAN_ID_MISMATCH")

    if entry.get("verification_status") != "VERIFIED":
        failures.append("COMMIT_RECEIPT_NOT_VERIFIED")

    if as_dict(manifest.get("policy")).get("execution_authorized") is not False:
        failures.append("MANIFEST_EXECUTION_BOUNDARY_INVALID")
    if as_dict(plan.get("execution_policy")).get(
        "execution_authorized"
    ) is not False:
        failures.append("PLAN_EXECUTION_BOUNDARY_INVALID")

    return manifest, failures


def extract_variable_defaults(plan: Dict[str, Any]) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for variable in as_list(plan.get("variables")):
        if not isinstance(variable, dict):
            continue
        name = normalize_text(variable.get("name"))
        if not name:
            continue
        if "value" in variable:
            values[name] = variable.get("value")
        elif "default" in variable:
            values[name] = variable.get("default")
        elif "values" in variable:
            values[name] = variable.get("values")
    return values


def verified_target_resolution(
    manifest: Dict[str, Any],
    target_registry: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    if target_registry is None:
        return None, []

    plan = as_dict(manifest.get("plan"))
    plan_id = str(plan.get("plan_id") or "")
    matches = [
        item
        for item in as_list(target_registry.get("resolutions"))
        if isinstance(item, dict) and item.get("plan_id") == plan_id
    ]
    if len(matches) != 1:
        return None, [f"TARGET_RESOLUTION_COUNT_INVALID:{len(matches)}"]

    resolution = matches[0]
    failures: List[str] = []
    if resolution.get("status") != "RESOLVED":
        failures.append("SCIENTIFIC_TARGET_NOT_RESOLVED")
    if resolution.get("plan_hash") != manifest.get("plan_hash"):
        failures.append("TARGET_PLAN_HASH_MISMATCH")
    if resolution.get("manifest_hash") != canonical_hash(manifest):
        failures.append("TARGET_MANIFEST_HASH_MISMATCH")

    immutable = {
        "plan_id": resolution.get("plan_id"),
        "plan_hash": resolution.get("plan_hash"),
        "manifest_hash": resolution.get("manifest_hash"),
        "source_action_id": resolution.get("source_action_id"),
        "canonical_plan_entry_hash": resolution.get(
            "canonical_plan_entry_hash"
        ),
        "target_evidence": as_list(resolution.get("target_evidence")),
        "identities": as_dict(resolution.get("identities")) or None,
        "condition_definition": (
            as_dict(resolution.get("condition_definition")) or None
        ),
    }
    if canonical_hash(immutable) != resolution.get("resolution_hash"):
        failures.append("TARGET_RESOLUTION_HASH_MISMATCH")

    identities = as_dict(resolution.get("identities"))
    for field in ("experiment_id", "condition_id"):
        if identities.get(field) in (None, ""):
            failures.append(f"TARGET_IDENTITY_MISSING:{field}")
    rule_ids = [
        item
        for item in as_list(identities.get("rule_ids"))
        if item not in (None, "")
    ]
    if not rule_ids and identities.get("rule_id") in (None, ""):
        failures.append("TARGET_IDENTITY_MISSING:rule_ids")
    return (resolution if not failures else None), failures


def verified_protocol_resolution(
    manifest: Dict[str, Any],
    target_resolution: Optional[Dict[str, Any]],
    protocol_registry: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    plan = as_dict(manifest.get("plan"))
    requires_protocol = (
        plan.get("experiment_type") == "perturbation_recovery_test"
    )
    if protocol_registry is None:
        return (
            None,
            ["SCIENTIFIC_PROTOCOL_REGISTRY_MISSING"]
            if requires_protocol
            else [],
        )

    plan_id = str(plan.get("plan_id") or "")
    matches = [
        item
        for item in as_list(protocol_registry.get("resolutions"))
        if isinstance(item, dict) and item.get("plan_id") == plan_id
    ]
    if len(matches) != 1:
        return None, [
            f"PROTOCOL_RESOLUTION_COUNT_INVALID:{len(matches)}"
        ]

    resolution = matches[0]
    failures: List[str] = []
    expected_status = "RESOLVED" if requires_protocol else "NOT_REQUIRED"
    if resolution.get("status") != expected_status:
        failures.append("SCIENTIFIC_PROTOCOL_NOT_RESOLVED")
    if resolution.get("plan_hash") != manifest.get("plan_hash"):
        failures.append("PROTOCOL_PLAN_HASH_MISMATCH")
    if resolution.get("manifest_hash") != canonical_hash(manifest):
        failures.append("PROTOCOL_MANIFEST_HASH_MISMATCH")
    if target_resolution is not None:
        if resolution.get("target_resolution_id") != (
            target_resolution.get("resolution_id")
        ):
            failures.append("PROTOCOL_TARGET_RESOLUTION_ID_MISMATCH")
        if resolution.get("target_resolution_hash") != (
            target_resolution.get("resolution_hash")
        ):
            failures.append("PROTOCOL_TARGET_RESOLUTION_HASH_MISMATCH")

    immutable = {
        "plan_id": resolution.get("plan_id"),
        "plan_hash": resolution.get("plan_hash"),
        "manifest_hash": resolution.get("manifest_hash"),
        "target_resolution_id": resolution.get(
            "target_resolution_id"
        ),
        "target_resolution_hash": resolution.get(
            "target_resolution_hash"
        ),
        "protocol": resolution.get("protocol"),
        "evidence": as_dict(resolution.get("evidence")),
    }
    if canonical_hash(immutable) != resolution.get("resolution_hash"):
        failures.append("PROTOCOL_RESOLUTION_HASH_MISMATCH")

    protocol = as_dict(resolution.get("protocol"))
    if requires_protocol:
        if not protocol:
            failures.append("SCIENTIFIC_PROTOCOL_MISSING")
        else:
            protocol_core = {
                key: value
                for key, value in protocol.items()
                if key not in {"protocol_id", "protocol_hash"}
            }
            protocol_hash = canonical_hash(protocol_core)
            if protocol.get("protocol_hash") != protocol_hash:
                failures.append("SCIENTIFIC_PROTOCOL_HASH_MISMATCH")
            if protocol.get("protocol_id") != (
                f"PROTO-{protocol_hash[:20].upper()}"
            ):
                failures.append("SCIENTIFIC_PROTOCOL_ID_MISMATCH")
    return (resolution if not failures else None), failures


def materialize_runtime(
    manifest: Dict[str, Any],
    policy: Dict[str, Any],
    prior: Dict[str, Any],
    output_root: Path,
    target_resolution: Optional[Dict[str, Any]] = None,
    target_failures: Optional[List[str]] = None,
    protocol_resolution: Optional[Dict[str, Any]] = None,
    protocol_failures: Optional[List[str]] = None,
) -> Dict[str, Any]:
    plan = as_dict(manifest.get("plan"))
    experiment_type = str(
        plan.get("experiment_type") or "controlled_action_validation"
    )

    defaults = as_dict(policy.get("defaults"))
    type_defaults = as_dict(
        as_dict(policy.get("experiment_type_defaults")).get(
            experiment_type
        )
    )
    runtime_defaults = merge_dict(defaults, type_defaults)
    variable_values = extract_variable_defaults(plan)

    field_size = variable_values.get(
        "field_size",
        runtime_defaults.get("field_size"),
    )
    topology = variable_values.get(
        "topology",
        runtime_defaults.get("topology"),
    )
    boundary_condition = variable_values.get(
        "boundary_condition",
        runtime_defaults.get("boundary_condition"),
    )
    duration_ticks = variable_values.get(
        "duration_ticks",
        runtime_defaults.get("duration_ticks"),
    )
    initial_state_mode = str(
        variable_values.get(
            "initial_state_mode",
            runtime_defaults.get("initial_state_mode", "CANONICAL_SEED"),
        )
    ).upper()

    seed_policy = merge_dict(
        as_dict(runtime_defaults.get("seed_policy")),
        as_dict(variable_values.get("seed_policy")),
    )
    replicates = int(seed_policy.get("replicates") or 1)
    base_seed = int(seed_policy.get("base_seed") or 0)
    seed_mode = str(seed_policy.get("mode") or "DETERMINISTIC_SERIES")
    seeds = (
        [base_seed + index for index in range(replicates)]
        if seed_mode == "DETERMINISTIC_SERIES"
        else []
    )

    runtime_id = (
        prior.get("runtime_id")
        or f"EXR-{canonical_hash({'plan_id': plan.get('plan_id')})[:16].upper()}"
    )
    runtime_dir = output_root / runtime_id

    controls = as_list(plan.get("controls"))
    protocol = as_dict(
        as_dict(protocol_resolution).get("protocol")
    )
    perturbation = (
        {
            "protocol_id": protocol.get("protocol_id"),
            "protocol_hash": protocol.get("protocol_hash"),
            "kind": protocol.get("intervention_kind"),
            "phase": protocol.get("phase"),
            "arms": as_list(protocol.get("arms")),
            "execution_capability": as_dict(
                protocol.get("execution_capability")
            ),
        }
        if protocol
        else as_dict(runtime_defaults.get("perturbation"))
    )
    control_mode = runtime_defaults.get("control_mode")
    identities = as_dict(
        as_dict(target_resolution).get("identities")
    )
    experiment_id = normalize_text(identities.get("experiment_id"))
    condition_id = normalize_text(identities.get("condition_id"))
    rule_ids: List[int] = []
    raw_rule_ids = as_list(identities.get("rule_ids"))
    if not raw_rule_ids and identities.get("rule_id") not in (None, ""):
        raw_rule_ids = [identities.get("rule_id")]
    for raw_rule_id in raw_rule_ids:
        try:
            numeric_rule = int(raw_rule_id)
        except (TypeError, ValueError):
            continue
        if numeric_rule > 0 and numeric_rule not in rule_ids:
            rule_ids.append(numeric_rule)
    rule_ids.sort()
    rule_id = rule_ids[0] if len(rule_ids) == 1 else None

    run_matrix: List[Dict[str, Any]] = []
    multi_rule = len(rule_ids) > 1
    for parent_rule_id in rule_ids:
        rule_segment = (
            f"-RULE-{parent_rule_id:05d}" if multi_rule else ""
        )
        for replicate_index, seed in enumerate(seeds, start=1):
            baseline_run_id = (
                f"{runtime_id}{rule_segment}-BASE-R{replicate_index:03d}"
            )
            run_matrix.append({
                "run_id": baseline_run_id,
                "role": "BASELINE_CONTROL",
                "replicate_index": replicate_index,
                "seed": seed,
                "field_size": field_size,
                "topology": topology,
                "boundary_condition": boundary_condition,
                "duration_ticks": duration_ticks,
                "initial_state_mode": initial_state_mode,
                "perturbation": None,
                "experiment_id": experiment_id,
                "condition_id": condition_id,
                "rule_id": parent_rule_id,
                "parent_rule_index": rule_ids.index(parent_rule_id) + 1,
                "output_directory": str(
                    runtime_dir / "runs" / baseline_run_id
                ),
            })

            if experiment_type == "perturbation_recovery_test":
                for arm_index, arm in enumerate(
                    as_list(perturbation.get("arms")), start=1
                ):
                    treatment_run_id = (
                        f"{runtime_id}{rule_segment}"
                        f"-PERT-A{arm_index:02d}"
                        f"-R{replicate_index:03d}"
                    )
                    run_matrix.append({
                        "run_id": treatment_run_id,
                        "role": "TREATMENT",
                        "replicate_index": replicate_index,
                        "seed": seed,
                        "field_size": field_size,
                        "topology": topology,
                        "boundary_condition": boundary_condition,
                        "duration_ticks": duration_ticks,
                        "initial_state_mode": initial_state_mode,
                        "perturbation": {
                            "protocol_id": perturbation.get("protocol_id"),
                            "protocol_hash": perturbation.get(
                                "protocol_hash"
                            ),
                            "kind": perturbation.get("kind"),
                            "phase": perturbation.get("phase"),
                            "arm": arm,
                            "execution_capability": perturbation.get(
                                "execution_capability"
                            ),
                        },
                        "experiment_id": experiment_id,
                        "condition_id": condition_id,
                        "rule_id": parent_rule_id,
                        "parent_rule_index": (
                            rule_ids.index(parent_rule_id) + 1
                        ),
                        "output_directory": str(
                            runtime_dir / "runs" / treatment_run_id
                        ),
                    })
            elif controls:
                treatment_run_id = (
                    f"{runtime_id}{rule_segment}"
                    f"-TEST-R{replicate_index:03d}"
                )
                run_matrix.append({
                    "run_id": treatment_run_id,
                    "role": "TREATMENT",
                    "replicate_index": replicate_index,
                    "seed": seed,
                    "field_size": field_size,
                    "topology": topology,
                    "boundary_condition": boundary_condition,
                    "duration_ticks": duration_ticks,
                    "initial_state_mode": initial_state_mode,
                    "perturbation": None,
                    "experiment_id": experiment_id,
                    "condition_id": condition_id,
                    "rule_id": parent_rule_id,
                    "parent_rule_index": rule_ids.index(parent_rule_id) + 1,
                    "output_directory": str(
                        runtime_dir / "runs" / treatment_run_id
                    ),
                })

    unresolved: List[Dict[str, Any]] = []
    for reason in target_failures or []:
        unresolved.append({
            "field": "scientific_target_resolution",
            "reason": reason,
        })
    for reason in protocol_failures or []:
        unresolved.append({
            "field": "scientific_protocol_resolution",
            "reason": reason,
        })
    if target_resolution is not None:
        if not experiment_id:
            unresolved.append({
                "field": "experiment_id",
                "reason": "SCIENTIFIC_TARGET_IDENTITY_MISSING",
            })
        if not condition_id:
            unresolved.append({
                "field": "condition_id",
                "reason": "SCIENTIFIC_TARGET_IDENTITY_MISSING",
            })
        if not rule_ids:
            unresolved.append({
                "field": "rule_ids",
                "reason": "SCIENTIFIC_TARGET_IDENTITY_MISSING",
            })
    if not field_size:
        unresolved.append({
            "field": "field_size",
            "reason": "REQUIRED_RUNTIME_FIELD_MISSING",
        })
    if not topology:
        unresolved.append({
            "field": "topology",
            "reason": "REQUIRED_RUNTIME_FIELD_MISSING",
        })
    if not boundary_condition:
        unresolved.append({
            "field": "boundary_condition",
            "reason": "REQUIRED_RUNTIME_FIELD_MISSING",
        })
    if not duration_ticks:
        unresolved.append({
            "field": "duration_ticks",
            "reason": "REQUIRED_RUNTIME_FIELD_MISSING",
        })
    if initial_state_mode not in {
        "CANONICAL_SEED",
        "RANDOM_SEED",
    }:
        unresolved.append({
            "field": "initial_state_mode",
            "reason": "INITIAL_STATE_MODE_UNSUPPORTED",
        })
    if not seeds:
        unresolved.append({
            "field": "seed_policy",
            "reason": "NO_MATERIALIZED_SEEDS",
        })
    if replicates > 1 and initial_state_mode == "CANONICAL_SEED":
        unresolved.append({
            "field": "seed_policy",
            "reason": (
                "PSEUDOREPLICATION_CANONICAL_SEED_IGNORES_REPLICATE_SEEDS"
            ),
        })

    if experiment_type == "perturbation_recovery_test":
        if not protocol:
            unresolved.append({
                "field": "scientific_protocol_resolution",
                "reason": "PERTURBATION_PROTOCOL_UNRESOLVED",
            })
        elif not as_list(protocol.get("arms")):
            unresolved.append({
                "field": "perturbation.arms",
                "reason": "PERTURBATION_PROTOCOL_HAS_NO_ARMS",
            })
        if (
            as_dict(protocol.get("execution_capability")).get("available")
            is not True
        ):
            unresolved.append({
                "field": "perturbation.execution_capability",
                "reason": "PRODUCTION_MUTATION_ADAPTER_UNAVAILABLE",
            })

    if experiment_type == "counterexample_search":
        if runtime_defaults.get("search_budget") in (None, 0):
            unresolved.append({
                "field": "search_budget",
                "reason": "SEARCH_BUDGET_UNRESOLVED",
            })

    runtime_spec = {
        "runtime_id": runtime_id,
        "plan_id": plan.get("plan_id"),
        "commit_id": manifest.get("commit_id"),
        "draft_id": plan.get("draft_id"),
        "intake_id": plan.get("intake_id"),
        "experiment_id": experiment_id,
        "condition_id": condition_id,
        "rule_id": rule_id,
        "rule_ids": rule_ids,
        "parent_rule_count": len(rule_ids),
        "experiment_type": experiment_type,
        "field_size": field_size,
        "topology": topology,
        "boundary_condition": boundary_condition,
        "duration_ticks": duration_ticks,
        "initial_state_mode": initial_state_mode,
        "sample_interval": runtime_defaults.get("sample_interval"),
        "checkpoint_interval": runtime_defaults.get(
            "checkpoint_interval"
        ),
        "seed_policy": {
            **seed_policy,
            "materialized_seeds": seeds,
        },
        "control_mode": control_mode,
        "declared_controls": controls,
        "perturbation": (
            perturbation
            if experiment_type == "perturbation_recovery_test"
            else None
        ),
        "run_matrix": run_matrix,
        "resource_profile": as_dict(
            runtime_defaults.get("resource_profile")
        ),
        "output_layout": {
            "runtime_root": str(runtime_dir),
            "runs_root": str(runtime_dir / "runs"),
            "logs_root": str(runtime_dir / "logs"),
            "artifacts_root": str(runtime_dir / "artifacts"),
            "runtime_manifest": str(
                runtime_dir / "runtime_package.json"
            ),
        },
        "evidence_contract": {
            "required_channels": as_list(
                plan.get("evidence_channels")
            ),
            "success_criteria": as_list(
                plan.get("success_criteria")
            ),
            "provenance_required": True,
        },
        "source_plan": {
            "plan_hash": manifest.get("plan_hash"),
            "manifest_hash": canonical_hash(manifest),
            "manifest_path": prior.get("source_manifest_path"),
        },
        "source_target_resolution": (
            {
                "resolution_id": target_resolution.get("resolution_id"),
                "resolution_hash": target_resolution.get(
                    "resolution_hash"
                ),
                "registry_hash": prior.get(
                    "target_resolution_registry_hash"
                ),
            }
            if target_resolution is not None
            else None
        ),
        "source_protocol_resolution": (
            {
                "resolution_id": protocol_resolution.get(
                    "resolution_id"
                ),
                "resolution_hash": protocol_resolution.get(
                    "resolution_hash"
                ),
                "registry_hash": prior.get(
                    "protocol_resolution_registry_hash"
                ),
            }
            if protocol_resolution is not None
            else None
        ),
    }

    runtime_hash = canonical_hash(runtime_spec)
    status = (
        "READY_FOR_LAUNCH_REVIEW"
        if not unresolved
        else "NEEDS_RUNTIME_RESOLUTION"
    )

    return {
        "schema": "archon_experiment_runtime_package_v1",
        "version": VERSION,
        "runtime_id": runtime_id,
        "status": status,
        "created_at": prior.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "runtime_hash": runtime_hash,
        "runtime": runtime_spec,
        "unresolved_fields": unresolved,
        "launch_authorization": {
            "authorized": False,
            "authorization_id": None,
            "authorized_at": None,
            "authorized_by": None,
            "confirmation": None,
        },
        "policy": {
            "materialized_not_executed": True,
            "launch_authorized": False,
            "separate_launch_authorization_required": True,
            "runtime_fields_editable_before_authorization": True,
            "source_plan_immutable": True,
            "does_not_change_governance_state": True,
            "does_not_change_scientific_metrics": True,
        },
    }


def build_materialization(
    experiments_root: Path,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    registry_path = experiments_root / "experiment_plan_registry.json"
    registry = load_json(registry_path, {})
    if not isinstance(registry, dict) or not registry:
        raise RuntimeError(
            f"Missing or invalid experiment plan registry: {registry_path}"
        )

    output_root = experiments_root / "RuntimePackages"
    index_path = experiments_root / "experiment_runtime_registry.json"
    existing_index = load_json(index_path, {})
    target_registry_path = (
        experiments_root / "scientific_target_resolution_registry.json"
    )
    target_registry = (
        as_dict(load_json(target_registry_path, {}))
        if target_registry_path.is_file()
        else None
    )
    protocol_registry_path = (
        experiments_root / "scientific_protocol_resolution_registry.json"
    )
    protocol_registry = (
        as_dict(load_json(protocol_registry_path, {}))
        if protocol_registry_path.is_file()
        else None
    )
    existing_by_plan = {
        str(item.get("plan_id")): item
        for item in as_list(existing_index.get("packages"))
        if isinstance(item, dict) and item.get("plan_id")
    }

    packages: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []

    for entry in as_list(registry.get("commits")):
        if not isinstance(entry, dict):
            continue

        manifest, failures = verify_registry_entry(entry)
        if failures:
            blocked.append({
                "commit_id": entry.get("commit_id"),
                "plan_id": entry.get("plan_id"),
                "reasons": failures,
            })
            continue

        assert manifest is not None
        plan = as_dict(manifest.get("plan"))
        plan_id = str(plan.get("plan_id"))
        prior = existing_by_plan.get(plan_id, {})
        prior = dict(prior)
        prior["source_manifest_path"] = entry.get("manifest_path")
        if target_registry is not None:
            prior["target_resolution_registry_hash"] = (
                target_registry.get("content_hash")
            )
        if protocol_registry is not None:
            prior["protocol_resolution_registry_hash"] = (
                protocol_registry.get("content_hash")
            )
        target_resolution, target_failures = verified_target_resolution(
            manifest,
            target_registry,
        )
        protocol_resolution, protocol_failures = (
            verified_protocol_resolution(
                manifest,
                target_resolution,
                protocol_registry,
            )
        )

        package = materialize_runtime(
            manifest,
            policy,
            prior,
            output_root,
            target_resolution=target_resolution,
            target_failures=target_failures,
            protocol_resolution=protocol_resolution,
            protocol_failures=protocol_failures,
        )
        runtime_id = str(package.get("runtime_id"))
        runtime_dir = output_root / runtime_id
        runtime_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            runtime_dir / "runtime_package.json",
            package,
        )

        packages.append({
            "runtime_id": runtime_id,
            "plan_id": plan_id,
            "commit_id": manifest.get("commit_id"),
            "status": package.get("status"),
            "runtime_hash": package.get("runtime_hash"),
            "package_path": str(
                runtime_dir / "runtime_package.json"
            ),
            "unresolved_count": len(
                as_list(package.get("unresolved_fields"))
            ),
            "run_count": len(
                as_list(as_dict(package.get("runtime")).get("run_matrix"))
            ),
            "launch_authorized": False,
            "created_at": package.get("created_at"),
            "updated_at": package.get("updated_at"),
        })

    packages = sorted(packages, key=lambda x: str(x.get("runtime_id")))
    summary = {
        "committed_plan_count": len(
            as_list(registry.get("commits"))
        ),
        "materialized_count": len(packages),
        "blocked_count": len(blocked),
        "ready_for_launch_review_count": sum(
            1
            for item in packages
            if item.get("status") == "READY_FOR_LAUNCH_REVIEW"
        ),
        "needs_runtime_resolution_count": sum(
            1
            for item in packages
            if item.get("status") == "NEEDS_RUNTIME_RESOLUTION"
        ),
        "launch_authorized_count": 0,
    }

    payload = {
        "schema": "archon_experiment_runtime_registry_v1",
        "version": VERSION,
        "generated_at": now_iso(),
        "mode": "MATERIALIZATION_ONLY",
        "summary": summary,
        "packages": packages,
        "blocked_plans": blocked,
        "source_registry": {
            "path": str(registry_path),
            "content_hash": registry.get("content_hash"),
        },
        "policy": {
            "materialization_does_not_execute": True,
            "launch_authorized": False,
            "separate_launch_authorization_required": True,
            "verified_committed_plans_only": True,
        },
    }
    payload["content_hash"] = canonical_hash({
        "summary": summary,
        "packages": packages,
        "blocked_plans": blocked,
        "source_registry": payload["source_registry"],
    })
    return payload


def render_markdown(payload: Dict[str, Any]) -> str:
    summary = as_dict(payload.get("summary"))
    lines = [
        f"# {TITLE}",
        "",
        f"- Generated: `{payload.get('generated_at')}`",
        f"- Mode: **{payload.get('mode')}**",
        f"- Committed plans: **{summary.get('committed_plan_count', 0)}**",
        f"- Materialized: **{summary.get('materialized_count', 0)}**",
        f"- Blocked: **{summary.get('blocked_count', 0)}**",
        (
            "- Ready for launch review: "
            f"**{summary.get('ready_for_launch_review_count', 0)}**"
        ),
        (
            "- Needs runtime resolution: "
            f"**{summary.get('needs_runtime_resolution_count', 0)}**"
        ),
        "- Launch authorized: **0**",
        "",
        "## Runtime packages",
        "",
    ]

    packages = as_list(payload.get("packages"))
    if not packages:
        lines.append("No committed plans were materialized.")
    else:
        lines.extend([
            "| Runtime | Plan | Status | Runs | Unresolved |",
            "| --- | --- | --- | ---: | ---: |",
        ])
        for item in packages:
            lines.append(
                f"| `{item.get('runtime_id')}` | "
                f"`{item.get('plan_id')}` | "
                f"{item.get('status')} | "
                f"{item.get('run_count', 0)} | "
                f"{item.get('unresolved_count', 0)} |"
            )

    blocked = as_list(payload.get("blocked_plans"))
    if blocked:
        lines.extend([
            "",
            "## Blocked plans",
            "",
        ])
        for item in blocked:
            lines.append(
                f"- `{item.get('plan_id') or '-'}`: "
                f"{', '.join(str(x) for x in item.get('reasons', []))}"
            )

    lines.extend([
        "",
        "## Safety boundary",
        "",
        "- Runtime packages are materialized but not executed.",
        "- Launch authorization remains false.",
        "- Unresolved runtime fields require explicit resolution.",
        "- Source experiment plans remain immutable.",
        "- A separate launch authorization stage is required.",
        "",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument(
        "--analysis-root",
        required=True,
        help="Path to Results/Analysis",
    )
    parser.add_argument(
        "--policy",
        default=None,
        help=(
            "Runtime materialization policy JSON. Default: "
            "<analysis-root>/Experiments/runtime_materialization_policy.json"
        ),
    )
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).resolve()
    experiments_root = analysis_root / "Experiments"
    policy_path = (
        Path(args.policy).resolve()
        if args.policy
        else experiments_root / "runtime_materialization_policy.json"
    )
    registry_path = experiments_root / "experiment_runtime_registry.json"
    markdown_path = experiments_root / "experiment_runtime_registry.md"

    if not policy_path.exists():
        atomic_write_json(policy_path, default_policy())

    policy = load_json(policy_path, {})
    if not isinstance(policy, dict) or not policy:
        raise RuntimeError(
            f"Missing or invalid runtime materialization policy: {policy_path}"
        )

    payload = build_materialization(experiments_root, policy)
    atomic_write_json(registry_path, payload)
    markdown_path.write_text(
        render_markdown(payload),
        encoding="utf-8",
    )

    summary = as_dict(payload.get("summary"))
    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(
        f"Plans:        {summary.get('committed_plan_count', 0)} committed | "
        f"{summary.get('materialized_count', 0)} materialized | "
        f"{summary.get('blocked_count', 0)} blocked"
    )
    print(
        f"Runtime:      {summary.get('ready_for_launch_review_count', 0)} ready | "
        f"{summary.get('needs_runtime_resolution_count', 0)} unresolved"
    )
    print("Launch:       NOT AUTHORIZED")
    print(f"Registry:     {registry_path}")
    print(f"Policy:       {policy_path}")
    print(f"Output MD:    {markdown_path}")
    print("=" * 72)

    return 0 if summary.get("blocked_count", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
