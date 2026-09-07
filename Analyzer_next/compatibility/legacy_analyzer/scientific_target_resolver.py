#!/usr/bin/env python3
"""Resolve committed ARCHON plans into launchable scientific identities.

The resolver is deliberately conservative:

* only verified committed plan manifests are considered;
* rule targets must be explicitly declared in the plan or canonical
  ``experiment_plan.json``;
* one or more explicitly declared independent parent rules are supported;
* experiment and condition identities are registered transactionally;
* ambiguous or missing targets remain unresolved and never reach Observer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Storage.sqlite_schema import initialize_database  # noqa: E402
from Analyzer_next.compatibility.legacy_analyzer.experiment_runtime_materializer import (  # noqa: E402
    default_policy,
    extract_variable_defaults,
    merge_dict,
)


VERSION = "1.1"
TITLE = "ARCHON Scientific Target Resolver"
CONFIRMATION = "RESOLVE_SCIENTIFIC_TARGETS"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


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


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def normalize_text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def normalize_rule(value: Any) -> Optional[int]:
    raw = normalize_text(value)
    if not raw:
        return None
    upper = raw.upper()
    if upper.startswith("RULE-"):
        raw = raw.split("-", 1)[1]
    try:
        numeric = int(raw)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None


def normalize_topology(value: Any) -> Optional[str]:
    return {
        "TORUS": "torus",
        "BOUNDED": "bounded",
        "PLANE": "bounded",
    }.get((normalize_text(value) or "").upper())


def normalize_boundary(value: Any) -> Optional[str]:
    return {
        "WRAP": "wrap",
        "PERIODIC": "wrap",
        "FIXED_DEAD": "fixed_dead",
        "FIXED_ALIVE": "fixed_alive",
        "REFLECTIVE": "reflective",
    }.get((normalize_text(value) or "").upper())


def verified_manifest(
    entry: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    failures: List[str] = []
    manifest_path = Path(str(entry.get("manifest_path") or ""))
    manifest = as_dict(load_json(manifest_path, {}))
    if not manifest:
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
        if plan.get("plan_id") != entry.get("plan_id"):
            failures.append("PLAN_ID_MISMATCH")
    if entry.get("verification_status") != "VERIFIED":
        failures.append("COMMIT_RECEIPT_NOT_VERIFIED")
    return (manifest if not failures else None), failures


def declared_rule_candidates(
    plan: Dict[str, Any],
    canonical_plan_entry: Dict[str, Any],
) -> Tuple[List[int], List[Dict[str, Any]]]:
    candidates: List[int] = []
    evidence: List[Dict[str, Any]] = []

    variables = extract_variable_defaults(plan)
    for name in ("rule_id", "rule", "target_rule", "target_rules"):
        value = variables.get(name)
        values = value if isinstance(value, list) else [value]
        normalized = [
            rule for rule in (normalize_rule(item) for item in values)
            if rule is not None
        ]
        if normalized:
            candidates.extend(normalized)
            evidence.append({
                "source": "committed_plan.variables",
                "field": name,
                "values": normalized,
            })

    for field in ("rule_id", "rule", "target_rule", "target_rules"):
        value = plan.get(field)
        values = value if isinstance(value, list) else [value]
        normalized = [
            rule for rule in (normalize_rule(item) for item in values)
            if rule is not None
        ]
        if normalized:
            candidates.extend(normalized)
            evidence.append({
                "source": "committed_plan",
                "field": field,
                "values": normalized,
            })

    target_rules = as_list(canonical_plan_entry.get("target_rules"))
    normalized_targets = [
        rule
        for rule in (normalize_rule(item) for item in target_rules)
        if rule is not None
    ]
    if normalized_targets:
        candidates.extend(normalized_targets)
        evidence.append({
            "source": "experiment_plan.json",
            "field": "target_rules",
            "plan_entry_id": canonical_plan_entry.get("id"),
            "values": normalized_targets,
        })

    return sorted(set(candidates)), evidence


def condition_definition(
    plan: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    experiment_type = str(
        plan.get("experiment_type") or "controlled_action_validation"
    )
    defaults = as_dict(policy.get("defaults"))
    type_defaults = as_dict(
        as_dict(policy.get("experiment_type_defaults")).get(experiment_type)
    )
    runtime_defaults = merge_dict(defaults, type_defaults)
    variables = extract_variable_defaults(plan)

    field_size = variables.get(
        "field_size", runtime_defaults.get("field_size")
    )
    width = height = None
    if isinstance(field_size, (list, tuple)) and len(field_size) == 2:
        try:
            width = int(field_size[0])
            height = int(field_size[1])
        except (TypeError, ValueError):
            pass
    topology = normalize_topology(
        variables.get("topology", runtime_defaults.get("topology"))
    )
    boundary = normalize_boundary(
        variables.get(
            "boundary_condition",
            runtime_defaults.get("boundary_condition"),
        )
    )
    initial_state_mode = str(
        variables.get("initial_state_mode")
        or runtime_defaults.get("initial_state_mode")
        or "canonical_seed"
    ).lower()

    failures: List[str] = []
    if width is None or width <= 0:
        failures.append("FIELD_WIDTH_UNRESOLVED")
    if height is None or height <= 0:
        failures.append("FIELD_HEIGHT_UNRESOLVED")
    if topology is None:
        failures.append("TOPOLOGY_UNRESOLVED")
    if boundary is None:
        failures.append("BOUNDARY_CONDITION_UNRESOLVED")
    if initial_state_mode not in {
        "canonical_seed",
        "random_seed",
        "saved_state",
        "deterministic_regenerated",
    }:
        failures.append("INITIAL_STATE_MODE_INVALID")
    if failures:
        return None, failures

    assert width is not None
    assert height is not None
    assert topology is not None
    assert boundary is not None
    payload = {
        "field_width": width,
        "field_height": height,
        "topology": topology,
        "boundary_mode": boundary,
        "initial_state_mode": initial_state_mode,
        "parameters": {},
        "schema_version": 1,
    }
    payload["condition_hash"] = canonical_hash({
        key: value for key, value in payload.items()
        if key != "condition_hash"
    })
    return payload, []


def register_identities(
    database: Path,
    *,
    plan: Dict[str, Any],
    plan_hash: str,
    rule_ids: List[int],
    condition: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    initialize_database(database)
    plan_id = str(plan.get("plan_id"))
    experiment_id = (
        "EXP-AUTO-"
        + canonical_hash({"plan_id": plan_id, "plan_hash": plan_hash})[
            :16
        ].upper()
    )
    condition_id = (
        "COND-AUTO-" + str(condition["condition_hash"])[:16].upper()
    )
    timestamp = now_iso()
    metadata = {
        "source": "scientific_target_resolver",
        "source_plan_id": plan_id,
        "source_plan_hash": plan_hash,
        "source_action_id": as_dict(plan.get("provenance")).get(
            "source_action_id"
        ),
        "rule_ids": rule_ids,
    }
    failures: List[str] = []
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")

        existing_condition = connection.execute(
            "SELECT * FROM experimental_conditions "
            "WHERE condition_hash = ?",
            (condition["condition_hash"],),
        ).fetchone()
        if existing_condition is not None:
            condition_id = str(existing_condition["condition_id"])
        else:
            collision = connection.execute(
                "SELECT condition_hash FROM experimental_conditions "
                "WHERE condition_id = ?",
                (condition_id,),
            ).fetchone()
            if collision is not None:
                failures.append("CONDITION_ID_COLLISION")
            else:
                connection.execute(
                    """
                    INSERT INTO experimental_conditions (
                        condition_id, name, field_width, field_height,
                        topology, boundary_mode, initial_state_mode,
                        condition_hash, parameters_json, schema_version,
                        created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        condition_id,
                        f"Auto condition for {plan_id}",
                        condition["field_width"],
                        condition["field_height"],
                        condition["topology"],
                        condition["boundary_mode"],
                        condition["initial_state_mode"],
                        condition["condition_hash"],
                        json.dumps(
                            condition["parameters"],
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        condition["schema_version"],
                        timestamp,
                        timestamp,
                    ),
                )

        existing_experiment = connection.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        if existing_experiment is not None:
            existing_metadata = as_dict(
                json.loads(existing_experiment["metadata_json"])
            )
            if (
                existing_metadata.get("source_plan_id") != plan_id
                or existing_metadata.get("source_plan_hash") != plan_hash
            ):
                failures.append("EXPERIMENT_ID_COLLISION")
        else:
            connection.execute(
                """
                INSERT INTO experiments (
                    experiment_id, title, research_question, status,
                    metadata_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, 'planned', ?, ?, ?)
                """,
                (
                    experiment_id,
                    str(plan.get("title") or plan_id),
                    normalize_text(plan.get("hypothesis")),
                    json.dumps(
                        metadata, ensure_ascii=False, sort_keys=True
                    ),
                    timestamp,
                    timestamp,
                ),
            )

        if failures:
            connection.rollback()
            return None, failures
        connection.commit()
    except (sqlite3.Error, ValueError, TypeError) as exc:
        connection.rollback()
        return None, [f"IDENTITY_REGISTRATION_FAILED:{exc}"]
    finally:
        connection.close()

    return {
        "experiment_id": experiment_id,
        "condition_id": condition_id,
        "rule_id": rule_ids[0] if len(rule_ids) == 1 else None,
        "rule_ids": rule_ids,
    }, []


def build_registry(
    analysis_root: Path,
    database: Path,
    policy: Dict[str, Any],
    selected_plan_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    experiments_root = analysis_root / "Experiments"
    plan_registry_path = experiments_root / "experiment_plan_registry.json"
    canonical_plan_path = analysis_root / "experiment_plan.json"
    plan_registry = as_dict(load_json(plan_registry_path, {}))
    canonical_plan = as_dict(load_json(canonical_plan_path, {}))
    canonical_by_id = {
        str(item.get("id")): item
        for item in as_list(canonical_plan.get("plan"))
        if isinstance(item, dict) and item.get("id")
    }

    selected = {
        str(item).strip()
        for item in (selected_plan_ids or [])
        if str(item).strip()
    }
    resolutions: List[Dict[str, Any]] = []
    for entry in as_list(plan_registry.get("commits")):
        if not isinstance(entry, dict):
            continue
        entry_plan_id = str(entry.get("plan_id") or "")
        if selected and entry_plan_id not in selected:
            continue
        manifest, failures = verified_manifest(entry)
        if manifest is None:
            resolutions.append({
                "plan_id": entry.get("plan_id"),
                "status": "REFUSED",
                "reasons": failures,
            })
            continue
        plan = as_dict(manifest.get("plan"))
        plan_id = str(plan.get("plan_id") or "")
        action_id = str(
            as_dict(plan.get("provenance")).get("source_action_id") or ""
        )
        canonical_entry = canonical_by_id.get(action_id, {})
        candidates, evidence = declared_rule_candidates(
            plan, canonical_entry
        )
        reasons: List[str] = []
        if not action_id:
            reasons.append("SOURCE_ACTION_ID_MISSING")
        if not canonical_entry and not any(
            item.get("source") != "experiment_plan.json"
            for item in evidence
        ):
            reasons.append("CANONICAL_PLAN_ENTRY_MISSING")
        if not candidates:
            reasons.append("RULE_TARGET_UNRESOLVED")

        condition, condition_failures = condition_definition(plan, policy)
        reasons.extend(condition_failures)
        identities: Optional[Dict[str, Any]] = None
        if not reasons and condition is not None:
            identities, identity_failures = register_identities(
                database,
                plan=plan,
                plan_hash=str(manifest.get("plan_hash")),
                rule_ids=candidates,
                condition=condition,
            )
            reasons.extend(identity_failures)

        immutable = {
            "plan_id": plan_id,
            "plan_hash": manifest.get("plan_hash"),
            "manifest_hash": canonical_hash(manifest),
            "source_action_id": action_id or None,
            "canonical_plan_entry_hash": (
                canonical_hash(canonical_entry)
                if canonical_entry else None
            ),
            "target_evidence": evidence,
            "identities": identities,
            "condition_definition": condition,
        }
        resolutions.append({
            "resolution_id": (
                "TARGET-"
                + canonical_hash(immutable)[:20].upper()
            ),
            "status": "RESOLVED" if not reasons else "NEEDS_HUMAN_RESOLUTION",
            **immutable,
            "reasons": sorted(set(reasons)),
            "resolution_hash": canonical_hash(immutable),
            "resolved_at": now_iso(),
        })

    resolutions.sort(key=lambda item: str(item.get("plan_id") or ""))
    summary = {
        "committed_plan_count": len(resolutions),
        "resolved_count": sum(
            1 for item in resolutions if item.get("status") == "RESOLVED"
        ),
        "needs_human_resolution_count": sum(
            1
            for item in resolutions
            if item.get("status") == "NEEDS_HUMAN_RESOLUTION"
        ),
        "refused_count": sum(
            1 for item in resolutions if item.get("status") == "REFUSED"
        ),
    }
    payload = {
        "schema": "archon_scientific_target_resolution_registry_v1",
        "version": VERSION,
        "generated_at": now_iso(),
        "status": (
            "RESOLVED"
            if resolutions
            and summary["resolved_count"] == len(resolutions)
            else "NEEDS_HUMAN_RESOLUTION"
        ),
        "summary": summary,
        "resolutions": resolutions,
        "sources": {
            "plan_registry_path": str(plan_registry_path),
            "plan_registry_hash": canonical_hash(plan_registry),
            "canonical_plan_path": str(canonical_plan_path),
            "canonical_plan_hash": canonical_hash(canonical_plan),
            "telemetry_database": str(database),
            "materialization_policy_hash": canonical_hash(policy),
            "selected_plan_ids": sorted(selected),
        },
        "policy": {
            "explicit_targets_only": True,
            "single_or_multi_rule_runtime_supported": True,
            "independent_parent_groups_required": True,
            "ambiguous_targets_fail_closed": True,
            "registered_identities_required": True,
            "does_not_launch_observer": True,
            "scoped_resolution_supported": True,
        },
    }
    payload["content_hash"] = canonical_hash({
        "summary": summary,
        "resolutions": resolutions,
        "sources": payload["sources"],
        "policy": payload["policy"],
    })
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--telemetry-database", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument(
        "--plan-id",
        action="append",
        default=[],
        help="Resolve only this committed plan (repeatable).",
    )
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).expanduser().resolve()
    experiments_root = analysis_root / "Experiments"
    experiments_root.mkdir(parents=True, exist_ok=True)
    registry_path = (
        experiments_root / "scientific_target_resolution_registry.json"
    )
    result_path = (
        experiments_root / "scientific_target_resolution_result.json"
    )
    policy_path = experiments_root / "runtime_materialization_policy.json"

    if args.confirmation != CONFIRMATION:
        result = {
            "schema": "archon_scientific_target_resolution_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "reasons": ["CONFIRMATION_INVALID"],
            "resolved_at": now_iso(),
        }
        atomic_write_json(result_path, result)
        return 1

    plan_registry_path = experiments_root / "experiment_plan_registry.json"
    if not plan_registry_path.is_file():
        result = {
            "schema": "archon_scientific_target_resolution_result_v1",
            "version": VERSION,
            "status": "REFUSED",
            "reasons": ["PLAN_REGISTRY_MISSING"],
            "resolved_at": now_iso(),
        }
        atomic_write_json(result_path, result)
        return 1

    if not policy_path.is_file():
        atomic_write_json(policy_path, default_policy())
    policy = as_dict(load_json(policy_path, {}))
    if not policy:
        raise RuntimeError(f"Invalid runtime policy: {policy_path}")

    database = Path(args.telemetry_database).expanduser().resolve()
    registry = build_registry(
        analysis_root,
        database,
        policy,
        selected_plan_ids=args.plan_id,
    )
    atomic_write_json(registry_path, registry)
    result = {
        "schema": "archon_scientific_target_resolution_result_v1",
        "version": VERSION,
        "status": registry.get("status"),
        "summary": registry.get("summary"),
        "registry_path": str(registry_path),
        "registry_hash": registry.get("content_hash"),
        "reasons": sorted({
            reason
            for item in as_list(registry.get("resolutions"))
            for reason in as_list(as_dict(item).get("reasons"))
        }),
        "resolved_at": now_iso(),
    }
    atomic_write_json(result_path, result)
    summary = as_dict(registry.get("summary"))
    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(
        f"Plans: {summary.get('committed_plan_count', 0)} | "
        f"resolved={summary.get('resolved_count', 0)} | "
        "human="
        f"{summary.get('needs_human_resolution_count', 0)} | "
        f"refused={summary.get('refused_count', 0)}"
    )
    print(f"Status: {registry.get('status')}")
    print(f"Registry: {registry_path}")
    print("=" * 72)
    return 0 if registry.get("status") == "RESOLVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
