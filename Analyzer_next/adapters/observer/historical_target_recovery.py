"""Fail-closed ScientificTarget recovery for pre-BRIDGE5.3 experiments.

Historical recovery is intentionally narrower than ordinary target resolution.
It accepts only an explicit ``EXP-PERT-GP-NNN`` action that is bound to one
verified immutable plan manifest and one hash-matching runtime package.  No
experiment outcome, claim text, or post-run report participates in recovery.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping

from Analyzer_next.core.experimental_evidence.targeting import (
    build_scientific_target,
    canonical_hash,
    validate_scientific_target,
)


SCHEMA = "archon_historical_target_recovery_v1"
_ACTION_PATTERN = re.compile(r"^EXP-PERT-(GP-\d{3})$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class HistoricalTargetRecovery:
    target: dict[str, Any] | None
    recovery: dict[str, Any] | None
    status: str
    reasons: tuple[str, ...] = ()


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _refused(*reasons: str) -> HistoricalTargetRecovery:
    return HistoricalTargetRecovery(
        target=None,
        recovery=None,
        status="REFUSED",
        reasons=tuple(sorted(set(reason for reason in reasons if reason))),
    )


def recover_historical_target(
    *,
    project_root: Path,
    experiment_id: str,
    experiment_metadata: Mapping[str, Any],
    runtime_package: Mapping[str, Any],
) -> HistoricalTargetRecovery:
    """Recover pre-run target intent without interpreting experiment results."""
    metadata = _as_dict(experiment_metadata)
    action_id = str(metadata.get("source_action_id") or "").strip().upper()
    action_match = _ACTION_PATTERN.fullmatch(action_id)
    if action_match is None:
        return HistoricalTargetRecovery(None, None, "NOT_APPLICABLE")
    expected_target_id = action_match.group(1).upper()

    plan_id = str(metadata.get("source_plan_id") or "").strip()
    plan_hash = str(metadata.get("source_plan_hash") or "").strip()
    runtime_id = str(metadata.get("source_runtime_id") or "").strip()
    runtime_hash = str(metadata.get("source_runtime_hash") or "").strip()
    missing = [
        code
        for value, code in (
            (plan_id, "HISTORICAL_SOURCE_PLAN_ID_MISSING"),
            (plan_hash, "HISTORICAL_SOURCE_PLAN_HASH_MISSING"),
            (runtime_id, "HISTORICAL_SOURCE_RUNTIME_ID_MISSING"),
            (runtime_hash, "HISTORICAL_SOURCE_RUNTIME_HASH_MISSING"),
        )
        if not value
    ]
    if missing:
        return _refused(*missing)

    package = _as_dict(runtime_package)
    runtime = _as_dict(package.get("runtime"))
    runtime_source_plan = _as_dict(runtime.get("source_plan"))
    runtime_failures: list[str] = []
    if not package or not runtime:
        runtime_failures.append("HISTORICAL_RUNTIME_PACKAGE_MISSING")
    if str(package.get("runtime_id") or runtime.get("runtime_id") or "") != runtime_id:
        runtime_failures.append("HISTORICAL_RUNTIME_ID_MISMATCH")
    if str(package.get("runtime_hash") or "") != runtime_hash:
        runtime_failures.append("HISTORICAL_RUNTIME_REFERENCE_HASH_MISMATCH")
    if package and canonical_hash(runtime) != package.get("runtime_hash"):
        runtime_failures.append("HISTORICAL_RUNTIME_CONTENT_HASH_MISMATCH")
    if str(runtime.get("plan_id") or "") != plan_id:
        runtime_failures.append("HISTORICAL_RUNTIME_PLAN_ID_MISMATCH")
    if str(runtime_source_plan.get("plan_hash") or "") != plan_hash:
        runtime_failures.append("HISTORICAL_RUNTIME_PLAN_HASH_MISMATCH")
    if runtime_failures:
        return _refused(*runtime_failures)

    experiments_root = (
        Path(project_root).resolve()
        / "Results"
        / "Analysis"
        / "Experiments"
    )
    registry_path = experiments_root / "experiment_plan_registry.json"
    registry = _load(registry_path)
    entries = [
        dict(item)
        for item in _as_list(registry.get("commits"))
        if isinstance(item, Mapping)
        and str(item.get("plan_id") or "") == plan_id
    ]
    if len(entries) != 1:
        return _refused(
            "HISTORICAL_PLAN_REGISTRY_ENTRY_MISSING"
            if not entries
            else "HISTORICAL_PLAN_REGISTRY_ENTRY_AMBIGUOUS"
        )
    entry = entries[0]
    entry_failures: list[str] = []
    if str(entry.get("verification_status") or "").upper() != "VERIFIED":
        entry_failures.append("HISTORICAL_PLAN_NOT_VERIFIED")
    if str(entry.get("plan_hash") or "") != plan_hash:
        entry_failures.append("HISTORICAL_REGISTRY_PLAN_HASH_MISMATCH")

    # The canonical project-local path prevents a registry from making the
    # Analyzer read an arbitrary external manifest path.
    manifest_path = experiments_root / "PlanManifests" / f"{plan_id}.json"
    manifest = _load(manifest_path)
    plan = _as_dict(manifest.get("plan"))
    if not manifest or not plan:
        entry_failures.append("HISTORICAL_PLAN_MANIFEST_MISSING")
    if manifest.get("schema") != "archon_experiment_plan_manifest_v1":
        entry_failures.append("HISTORICAL_PLAN_MANIFEST_SCHEMA_INVALID")
    if str(plan.get("plan_id") or "") != plan_id:
        entry_failures.append("HISTORICAL_MANIFEST_PLAN_ID_MISMATCH")
    if str(manifest.get("plan_hash") or "") != plan_hash:
        entry_failures.append("HISTORICAL_MANIFEST_PLAN_HASH_MISMATCH")
    if plan and canonical_hash(plan) != plan_hash:
        entry_failures.append("HISTORICAL_MANIFEST_CONTENT_HASH_MISMATCH")
    manifest_hash = canonical_hash(manifest) if manifest else ""
    if entry.get("manifest_hash") and entry.get("manifest_hash") != manifest_hash:
        entry_failures.append("HISTORICAL_MANIFEST_REGISTRY_HASH_MISMATCH")
    if str(runtime_source_plan.get("manifest_hash") or "") != manifest_hash:
        entry_failures.append("HISTORICAL_RUNTIME_MANIFEST_HASH_MISMATCH")
    provenance = _as_dict(plan.get("provenance"))
    if str(provenance.get("source_action_id") or "").strip().upper() != action_id:
        entry_failures.append("HISTORICAL_SOURCE_ACTION_MISMATCH")
    metadata_type = str(metadata.get("experiment_type") or "").strip()
    if metadata_type and metadata_type != str(plan.get("experiment_type") or "").strip():
        entry_failures.append("HISTORICAL_EXPERIMENT_TYPE_MISMATCH")
    if entry_failures:
        return _refused(*entry_failures)

    precommitted_target = plan.get("scientific_target")
    mode = "VERIFIED_PLAN_TARGET"
    metrics_precommitted = True
    if isinstance(precommitted_target, Mapping):
        target = dict(precommitted_target)
        valid, failures = validate_scientific_target(target)
        if plan.get("scientific_target_hash") != target.get("target_hash"):
            failures = tuple((*failures, "HISTORICAL_PLAN_TARGET_HASH_MISMATCH"))
            valid = False
        if not valid:
            return _refused(*failures)
    else:
        mode = "VERIFIED_PLAN_INTENT_ONLY"
        metrics_precommitted = False
        target = build_scientific_target(
            action={
                "action_id": action_id,
                "kind": plan.get("experiment_type"),
                "done_when": _as_list(plan.get("success_criteria")),
                "suggested_target": plan.get("target_description"),
            },
            experiment_intent={
                "experiment_type": plan.get("experiment_type"),
                "hypothesis_prompt": plan.get("hypothesis"),
                "target_description": plan.get("target_description"),
                "success_criteria": _as_list(plan.get("success_criteria")),
            },
            provenance={
                **provenance,
                "source_action_id": action_id,
                "source_principle_ids": [expected_target_id],
            },
        )
        if target is None:
            return _refused("HISTORICAL_TARGET_INTENT_NOT_RECOVERABLE")

    if target.get("target_id") != expected_target_id:
        return _refused("HISTORICAL_TARGET_ID_MISMATCH")
    valid, failures = validate_scientific_target(target)
    if not valid:
        return _refused(*failures)

    recovery: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "RECOVERED",
        "mode": mode,
        "experiment_id": str(experiment_id),
        "target_id": expected_target_id,
        "target_hash": target.get("target_hash"),
        "source_action_id": action_id,
        "source_plan_id": plan_id,
        "source_plan_hash": plan_hash,
        "source_manifest_hash": manifest_hash,
        "source_runtime_id": runtime_id,
        "source_runtime_hash": runtime_hash,
        "target_was_carried_at_execution": False,
        "target_metrics_precommitted": metrics_precommitted,
        "post_run_results_used_for_recovery": False,
        "scientific_policy": {
            "pre_run_provenance_only": True,
            "intent_is_not_support": True,
            "fail_closed": True,
            "automatic_principle_promotion": False,
        },
    }
    recovery["recovery_hash"] = canonical_hash(recovery)
    return HistoricalTargetRecovery(
        target=target,
        recovery=recovery,
        status="RECOVERED",
    )


__all__ = [
    "HistoricalTargetRecovery",
    "SCHEMA",
    "recover_historical_target",
]
