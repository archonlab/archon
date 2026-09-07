"""Authoritative matched-control resolution for production experiment mutations.

BRIDGE5.3 keeps legacy standalone-mutation semantics intact while recognizing
mutations materialized by ``ARCHON_MUTATION_RULE_FILE_V2`` for a controlled
Experiment runtime.  Those mutations must be compared with the matched
unperturbed experiment slot, never with an unrelated historical canonical
observation.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .utils import read_json, safe_int, write_json_atomic

PRODUCTION_MUTATION_SCHEMA = "archon_observer_mutation_run_v2"
PRODUCTION_MUTATION_ADAPTER = "ARCHON_MUTATION_RULE_FILE_V2"
INDIRECT_BINDING_METHOD = "TARGET_RULES_UNIQUE_PERTURBATION_PROGRAM_MATCH"
RESOLUTION_SCHEMA = "archon_experimental_mutation_resolution_v1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value in {None, ""}:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _existing_file(value: Any) -> Path | None:
    if value in {None, ""}:
        return None
    try:
        path = Path(str(value)).expanduser().resolve()
        return path if path.is_file() else None
    except OSError:
        return None


def is_production_experimental_mutation(manifest: dict[str, Any]) -> bool:
    run_identity = _as_dict(manifest.get("run_identity"))
    return bool(
        manifest.get("schema") == PRODUCTION_MUTATION_SCHEMA
        and manifest.get("adapter_id") == PRODUCTION_MUTATION_ADAPTER
        and run_identity.get("experiment_id")
        and run_identity.get("condition_id")
        and run_identity.get("replicate_index") is not None
        and run_identity.get("experiment_seed") is not None
    )


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
    except sqlite3.Error:
        return set()


def _row_payload(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["run_metadata"] = _json_object(data.pop("run_metadata_json", None))
    data["link_metadata"] = _json_object(data.pop("link_metadata_json", None))
    data["experiment_metadata"] = _json_object(
        data.pop("experiment_metadata_json", None)
    )
    return data


def _experiment_seed(row: dict[str, Any]) -> int | None:
    link = _as_dict(row.get("link_metadata"))
    run = _as_dict(row.get("run_metadata"))
    context = _as_dict(run.get("experimental_context"))
    for value in (
        link.get("experiment_seed"),
        context.get("experiment_seed"),
        context.get("seed"),
    ):
        resolved = safe_int(value)
        if resolved is not None:
            return resolved
    return None


def _samples_path(row: dict[str, Any]) -> Path | None:
    metadata = _as_dict(row.get("run_metadata"))
    return _existing_file(metadata.get("samples_csv"))


def _source_runtime_from_experiment_metadata(
    experiment_metadata: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    runtime_id = str(experiment_metadata.get("source_runtime_id") or "").strip()
    source_experiment_id = str(
        experiment_metadata.get("source_experiment_id") or ""
    ).strip()
    source_action_id = str(
        experiment_metadata.get("source_action_id") or ""
    ).strip()
    return (
        runtime_id or None,
        source_experiment_id or None,
        source_action_id or None,
    )


def _runtime_source_action(runtime_package: dict[str, Any]) -> str | None:
    runtime = _as_dict(runtime_package.get("runtime"))
    for candidate in (
        _as_dict(runtime.get("provenance")).get("source_action_id"),
        _as_dict(runtime_package.get("provenance")).get("source_action_id"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text

    source_plan = _as_dict(runtime.get("source_plan"))
    if not source_plan:
        source_plan = _as_dict(runtime_package.get("source_plan"))
    manifest_path = _existing_file(source_plan.get("manifest_path"))
    if manifest_path is not None:
        plan_manifest = read_json(manifest_path, {})
        plan = _as_dict(_as_dict(plan_manifest).get("plan"))
        text = str(_as_dict(plan.get("provenance")).get("source_action_id") or "").strip()
        if text:
            return text
    return None


def _protocol_resolution(
    *,
    analysis_root: Path,
    runtime_package: dict[str, Any],
) -> tuple[dict[str, Any], Path | None]:
    runtime = _as_dict(runtime_package.get("runtime"))
    source = _as_dict(runtime.get("source_protocol_resolution"))
    if not source:
        source = _as_dict(runtime_package.get("source_protocol_resolution"))
    resolution_id = str(source.get("resolution_id") or "").strip()
    if not resolution_id:
        return {}, None
    registry_path = (
        analysis_root
        / "Experiments"
        / "scientific_protocol_resolution_registry.json"
    )
    registry = read_json(registry_path, {})
    rows = (
        registry.get("resolutions", [])
        if isinstance(registry, dict)
        else []
    )
    if not isinstance(rows, list):
        rows = []
    matches = [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("resolution_id") or "") == resolution_id
    ]
    return (matches[0] if len(matches) == 1 else {}), (
        registry_path.resolve() if registry_path.is_file() else None
    )


def _evidence_claim_ids(runtime_package: dict[str, Any]) -> list[str]:
    runtime = _as_dict(runtime_package.get("runtime"))
    contract = _as_dict(runtime.get("evidence_contract"))
    if not contract:
        contract = _as_dict(runtime_package.get("evidence_contract"))
    values: list[str] = []
    for item in contract.get("success_criteria", []) if isinstance(contract.get("success_criteria"), list) else []:
        values.extend(re.findall(r"\bGP-\d+\b", str(item).upper()))
    return sorted(set(values))


def _scientific_scope(
    *,
    project_root: Path,
    experiment_metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[Path]]:
    analysis_root = project_root / "Results" / "Analysis"
    runtime_id, source_experiment_id, source_action_id = (
        _source_runtime_from_experiment_metadata(experiment_metadata)
    )
    dependencies: list[Path] = []
    if not runtime_id:
        return ({
            "status": "UNVERIFIED",
            "reason": "source_runtime_id_missing_from_execution_experiment",
            "direct_claim_eligible": False,
            "direct_claim_id": None,
            "binding_role": "unknown",
            "source_action_id": source_action_id,
            "source_experiment_id": source_experiment_id,
        }, dependencies)

    runtime_path = (
        analysis_root
        / "Experiments"
        / "RuntimePackages"
        / runtime_id
        / "runtime_package.json"
    )
    runtime_package = read_json(runtime_path, {})
    if not isinstance(runtime_package, dict) or not runtime_package:
        return ({
            "status": "UNVERIFIED",
            "reason": "source_runtime_package_missing",
            "direct_claim_eligible": False,
            "direct_claim_id": None,
            "binding_role": "unknown",
            "source_runtime_id": runtime_id,
            "source_action_id": source_action_id,
            "source_experiment_id": source_experiment_id,
        }, dependencies)
    dependencies.append(runtime_path.resolve())

    source_action_id = source_action_id or _runtime_source_action(runtime_package)
    resolution, registry_path = _protocol_resolution(
        analysis_root=analysis_root,
        runtime_package=runtime_package,
    )
    if registry_path is not None:
        dependencies.append(registry_path)
    protocol = _as_dict(resolution.get("protocol"))
    binding = _as_dict(protocol.get("claim_binding"))
    claim_id = str(protocol.get("claim_id") or binding.get("claim_id") or "").strip() or None
    program_id = str(protocol.get("program_id") or binding.get("program_id") or "").strip() or None
    method = str(binding.get("method") or "").strip() or None
    explicit_direct = binding.get("direct_claim_target")
    if explicit_direct is None:
        direct = bool(claim_id and method != INDIRECT_BINDING_METHOD)
    else:
        direct = explicit_direct is True
    binding_role = str(binding.get("binding_role") or "").strip()
    if not binding_role:
        binding_role = "direct_claim_target" if direct else "supporting_program"

    evidence_claim_ids = _evidence_claim_ids(runtime_package)
    status = "DIRECT_CLAIM_TARGET" if direct else "SUPPORTING_PROGRAM_CONTEXT"
    reason = None
    if not resolution:
        status = "UNVERIFIED"
        direct = False
        reason = "source_protocol_resolution_missing_or_ambiguous"
    elif claim_id and evidence_claim_ids and direct and claim_id not in evidence_claim_ids:
        # A direct claim target that contradicts the runtime evidence contract
        # is unsafe to ingest automatically.
        status = "CONFLICT"
        direct = False
        reason = "protocol_claim_conflicts_with_runtime_evidence_contract"

    return ({
        "status": status,
        "reason": reason,
        "direct_claim_eligible": bool(direct),
        "direct_claim_id": claim_id if direct else None,
        "program_claim_id": claim_id,
        "program_id": program_id,
        "binding_method": method,
        "binding_role": binding_role,
        "source_runtime_id": runtime_id,
        "source_experiment_id": source_experiment_id,
        "source_action_id": source_action_id,
        "evidence_contract_claim_ids": evidence_claim_ids,
        "scientific_policy": {
            "indirect_program_binding_is_direct_claim_evidence": False,
            "automatic_promotion": False,
            "fail_closed_on_scope_conflict": True,
        },
    }, dependencies)


def resolve_experimental_mutation(
    *,
    manifest: dict[str, Any],
    results_root: Path,
    run_dir: Path,
) -> dict[str, Any] | None:
    """Resolve authoritative treatment/baseline slots for one PROD mutation.

    ``None`` means this is not a BRIDGE5 production experiment mutation and
    legacy Mutation Analyzer behavior must remain untouched.
    """
    if not is_production_experimental_mutation(manifest):
        return None

    identity = _as_dict(manifest.get("run_identity"))
    protocol = _as_dict(manifest.get("protocol"))
    result: dict[str, Any] = {
        "schema": RESOLUTION_SCHEMA,
        "status": "UNRESOLVED",
        "reason": None,
        "experiment_id": str(identity.get("experiment_id") or ""),
        "condition_id": str(identity.get("condition_id") or ""),
        "rule_id": safe_int(manifest.get("canonical_parent_rule_id")),
        "replicate_index": safe_int(identity.get("replicate_index")),
        "experiment_seed": safe_int(identity.get("experiment_seed")),
        "treatment_arm": str(protocol.get("arm_id") or ""),
        "treatment_run_id": None,
        "baseline_run_id": None,
        "treatment_samples": None,
        "baseline_samples": None,
        "treatment_final_tick": None,
        "baseline_final_tick": None,
        "same_seed": False,
        "same_horizon": False,
        "match_type": "matched_experiment_control",
        "dependencies": [],
        "scientific_scope": {
            "status": "UNVERIFIED",
            "direct_claim_eligible": False,
            "direct_claim_id": None,
            "binding_role": "unknown",
        },
    }
    required_identity = (
        result["experiment_id"], result["condition_id"], result["rule_id"],
        result["replicate_index"], result["experiment_seed"], result["treatment_arm"],
    )
    if any(value in {None, ""} for value in required_identity):
        result["reason"] = "experimental_mutation_identity_incomplete"
        return result

    database = (
        Path(results_root).resolve()
        / "observation_logs"
        / "telemetry.sqlite"
    )
    if not database.is_file():
        result["reason"] = "canonical_experiment_registry_missing"
        return result

    project_root = Path(results_root).resolve().parent.parent
    try:
        connection = sqlite3.connect(str(database))
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        result["reason"] = f"canonical_experiment_registry_open_failed:{exc}"
        return result

    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not {"runs", "experiment_runs", "experiments"}.issubset(tables):
            result["reason"] = "canonical_experiment_registry_schema_missing"
            return result
        er_columns = _table_columns(connection, "experiment_runs")
        if "treatment_arm" not in er_columns:
            result["reason"] = "experiment_registry_missing_treatment_arm"
            return result

        query = """
            SELECT
                er.experiment_run_id,
                er.experiment_id,
                er.run_id,
                er.condition_id,
                er.rule_id,
                er.role,
                er.replicate_index,
                er.treatment_arm,
                er.parent_run_id,
                er.metadata_json AS link_metadata_json,
                r.status AS run_status,
                r.final_tick,
                r.source_path,
                r.metadata_json AS run_metadata_json,
                e.metadata_json AS experiment_metadata_json
            FROM experiment_runs er
            JOIN runs r ON r.run_id = er.run_id
            JOIN experiments e ON e.experiment_id = er.experiment_id
            WHERE er.experiment_id = ?
              AND er.condition_id = ?
              AND er.rule_id = ?
              AND er.replicate_index = ?
        """
        rows = [
            _row_payload(row)
            for row in connection.execute(
                query,
                (
                    result["experiment_id"],
                    result["condition_id"],
                    result["rule_id"],
                    result["replicate_index"],
                ),
            )
        ]
    except sqlite3.Error as exc:
        result["reason"] = f"canonical_experiment_registry_query_failed:{exc}"
        return result
    finally:
        connection.close()

    treatments = [
        row for row in rows
        if str(row.get("role") or "").lower() == "treatment"
        and str(row.get("treatment_arm") or "") == result["treatment_arm"]
    ]
    baselines = [
        row for row in rows
        if str(row.get("role") or "").lower() == "baseline"
        and not str(row.get("treatment_arm") or "")
    ]
    if len(treatments) != 1:
        result["reason"] = f"treatment_slot_count:{len(treatments)}"
        return result
    if len(baselines) != 1:
        result["reason"] = f"baseline_slot_count:{len(baselines)}"
        return result

    treatment = treatments[0]
    baseline = baselines[0]
    if str(treatment.get("run_status") or "").lower() != "completed":
        result["reason"] = "treatment_run_not_completed"
        return result
    if str(baseline.get("run_status") or "").lower() != "completed":
        result["reason"] = "baseline_run_not_completed"
        return result

    treatment_seed = _experiment_seed(treatment)
    baseline_seed = _experiment_seed(baseline)
    expected_seed = result["experiment_seed"]
    if treatment_seed != expected_seed or baseline_seed != expected_seed:
        result["reason"] = (
            "matched_experiment_seed_mismatch:"
            f"expected={expected_seed},treatment={treatment_seed},baseline={baseline_seed}"
        )
        return result

    treatment_samples = _samples_path(treatment)
    baseline_samples = _samples_path(baseline)
    if treatment_samples is None:
        result["reason"] = "authoritative_treatment_samples_missing"
        return result
    if baseline_samples is None:
        result["reason"] = "authoritative_baseline_samples_missing"
        return result

    declared_output = _existing_file(identity.get("run_output_directory"))
    # run_output_directory is a directory, so validate its containment without
    # requiring it to be a file.
    output_root: Path | None = None
    try:
        raw_output = Path(str(identity.get("run_output_directory") or "")).expanduser().resolve()
        if raw_output.is_dir():
            output_root = raw_output
    except OSError:
        output_root = None
    if output_root is not None:
        try:
            treatment_samples.relative_to(output_root)
        except ValueError:
            result["reason"] = "treatment_samples_outside_declared_execution_output"
            return result

    mutated_path = _existing_file(_as_dict(manifest.get("paths")).get("mutated_rule"))
    treatment_source = _existing_file(treatment.get("source_path"))
    if mutated_path is not None and treatment_source is not None:
        if mutated_path != treatment_source:
            result["reason"] = "treatment_source_path_does_not_match_mutated_rule"
            return result

    treatment_tick = safe_int(treatment.get("final_tick"))
    baseline_tick = safe_int(baseline.get("final_tick"))
    if treatment_tick is None or baseline_tick is None:
        result["reason"] = "matched_experiment_final_tick_missing"
        return result
    if treatment_tick != baseline_tick:
        result["reason"] = (
            f"matched_experiment_horizon_mismatch:{baseline_tick}!={treatment_tick}"
        )
        return result

    scope, scope_dependencies = _scientific_scope(
        project_root=project_root,
        experiment_metadata=_as_dict(treatment.get("experiment_metadata")),
    )
    dependencies = [treatment_samples, baseline_samples, *scope_dependencies]
    result.update({
        "status": "RESOLVED",
        "reason": None,
        "treatment_run_id": str(treatment.get("run_id") or ""),
        "baseline_run_id": str(baseline.get("run_id") or ""),
        "treatment_experiment_run_id": str(treatment.get("experiment_run_id") or ""),
        "baseline_experiment_run_id": str(baseline.get("experiment_run_id") or ""),
        "treatment_samples": str(treatment_samples),
        "baseline_samples": str(baseline_samples),
        "treatment_final_tick": treatment_tick,
        "baseline_final_tick": baseline_tick,
        "same_seed": True,
        "same_horizon": True,
        "scientific_scope": scope,
        "dependencies": [str(path) for path in dependencies if path.is_file()],
        "verification": {
            "experiment_slot": "verified",
            "same_rule": True,
            "same_condition": True,
            "same_replicate": True,
            "same_seed": True,
            "same_horizon": True,
            "treatment_arm": "verified",
            "treatment_samples_source": "runs.metadata_json:samples_csv",
            "baseline_samples_source": "runs.metadata_json:samples_csv",
        },
    })
    return result


def public_resolution(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        key: item
        for key, item in value.items()
        if key != "dependencies"
    }


def write_resolution_receipt(
    path: Path,
    resolution: dict[str, Any],
) -> Path:
    payload = public_resolution(resolution) or {}
    current = read_json(path, {})
    if current != payload:
        write_json_atomic(path, payload)
    return path.resolve()
