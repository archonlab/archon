#!/usr/bin/env python3
"""Modular Experiment Runtime Materializer with BRIDGE2/BRIDGE3 integrity.

BRIDGE2 keeps fresh metric baselines as single-arm replications.
BRIDGE3 keeps cohort/counterexample work as Universe Search discovery programs
with a separate mutation branch.  It forbids synthetic Observer TREATMENT rows
for Search programs and pins the actual Search engine budget/config before any
launch review.

Frozen ``Analyzer/experiment_runtime_materializer.py`` remains unchanged.
"""
from __future__ import annotations

import copy
import importlib
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.observer.cohort_search_runtime import (  # noqa: E402
    BRIDGE_ID as COHORT_BRIDGE_ID,
    COHORT_SEARCH_TYPES,
    SEARCH_READY_STATUS,
    build_cohort_search_contract,
)
from Analyzer_next.core.experimental_evidence.targeting import (  # noqa: E402
    validate_scientific_target,
)

legacy = importlib.import_module(
    "Analyzer_next.compatibility.legacy_analyzer.experiment_runtime_materializer"
)
_original_materialize_runtime = legacy.materialize_runtime
_original_build_materialization = legacy.build_materialization

BASELINE_ONLY_EXPERIMENT_TYPES = frozenset({"metric_validation_baseline"})


def _runtime_id(manifest: dict[str, Any], prior: dict[str, Any]) -> str:
    plan = legacy.as_dict(manifest.get("plan"))
    return str(
        prior.get("runtime_id")
        or f"EXR-{legacy.canonical_hash({'plan_id': plan.get('plan_id')})[:16].upper()}"
    )


def _existing_runtime_package(output_root: Path, runtime_id: str) -> Path:
    return Path(output_root).resolve() / runtime_id / "runtime_package.json"


def _load_existing(path: Path) -> dict[str, Any]:
    payload = legacy.load_json(path, {})
    return payload if isinstance(payload, dict) else {}


def _execution_started(package: dict[str, Any]) -> bool:
    runtime = legacy.as_dict(package.get("runtime"))
    search = legacy.as_dict(runtime.get("search_execution"))
    search_launch = legacy.as_dict(package.get("search_launch_authorization"))
    search_state = legacy.as_dict(package.get("search_execution_state"))
    return bool(
        search.get("execution_started") is True
        or search_launch.get("authorized") is True
        or search_state.get("execution_started") is True
        or legacy.as_dict(package.get("launch_authorization")).get("authorized") is True
        or package.get("status") in {
            "LAUNCH_AUTHORIZED",
            "SEARCH_LAUNCH_AUTHORIZED",
            "SEARCH_EXECUTION_STARTED",
        }
    )


def _baseline_only_normalize(package: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(package)
    runtime = legacy.as_dict(normalized.get("runtime"))
    matrix = [row for row in legacy.as_list(runtime.get("run_matrix")) if isinstance(row, dict)]
    baseline = [
        row
        for row in matrix
        if str(row.get("role") or "").strip().upper()
        in {"BASELINE", "BASELINE_CONTROL", "CONTROL"}
    ]
    runtime["run_matrix"] = baseline
    runtime["design_mode"] = "single_arm_replication"
    runtime["control_mode"] = "REPLICATED_BASELINE"
    runtime["design_integrity_bridge"] = "BRIDGE2"
    normalized["runtime"] = runtime
    normalized["runtime_hash"] = legacy.canonical_hash(runtime)
    policy = dict(normalized.get("policy") or {})
    policy["baseline_only_design_materialized"] = True
    normalized["policy"] = policy
    return normalized


def _cohort_search_normalize(
    package: dict[str, Any],
    *,
    manifest: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    normalized = copy.deepcopy(package)
    plan = legacy.as_dict(manifest.get("plan"))
    runtime = legacy.as_dict(normalized.get("runtime"))

    search_execution, mutation_branch, bridge_unresolved = build_cohort_search_contract(
        plan=plan,
        runtime=runtime,
        output_root=Path(output_root),
    )

    # A cohort Search is not an Observer matched-arm experiment.  Reference
    # rules are Search seeds/controls; intervention work remains a distinct
    # mutation branch.
    runtime["run_matrix"] = []
    runtime["design_mode"] = "cohort_gap_search_program"
    runtime["execution_kind"] = "UNIVERSE_SEARCH"
    runtime["design_integrity_bridge"] = COHORT_BRIDGE_ID
    runtime["control_mode"] = "POSITIVE_REFERENCE_COHORT_INPUT"
    runtime["reference_rule_ids"] = list(search_execution.get("reference_rules") or [])
    runtime["search_execution"] = search_execution
    runtime["mutation_branch"] = mutation_branch
    runtime["search_budget"] = dict(search_execution.get("budget") or {})
    runtime["perturbation"] = None

    unresolved = [
        row
        for row in legacy.as_list(normalized.get("unresolved_fields"))
        if isinstance(row, dict)
        and not (
            str(row.get("field") or "") == "search_budget"
            and str(row.get("reason") or "") == "SEARCH_BUDGET_UNRESOLVED"
        )
    ]
    unresolved.extend(bridge_unresolved)
    # Stable de-duplication.
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in unresolved:
        key = (str(row.get("field") or ""), str(row.get("reason") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    normalized["runtime"] = runtime
    normalized["runtime_hash"] = legacy.canonical_hash(runtime)
    normalized["unresolved_fields"] = deduped
    normalized["status"] = (
        SEARCH_READY_STATUS if not deduped else "NEEDS_RUNTIME_RESOLUTION"
    )
    normalized["updated_at"] = legacy.now_iso()
    policy = dict(normalized.get("policy") or {})
    policy.update({
        "launch_authorized": False,
        "search_execution_materialized": True,
        "search_launch_authorized": False,
        "observer_run_matrix_materialized": False,
        "observer_treatment_rows_forbidden": True,
        "positive_reference_cohort_is_input_not_arm": True,
        "mutation_branch_separate_from_search": True,
        "separate_search_launch_authorization_required": True,
        "design_integrity_bridge": COHORT_BRIDGE_ID,
    })
    normalized["policy"] = policy
    return normalized


def _scientific_target_normalize(
    package: dict[str, Any],
    *,
    manifest: dict[str, Any],
    target_resolution: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = legacy.as_dict(manifest.get("plan"))
    target = plan.get("scientific_target")
    if not isinstance(target, dict):
        return package
    normalized = copy.deepcopy(package)
    runtime = legacy.as_dict(normalized.get("runtime"))
    unresolved = [
        row for row in legacy.as_list(normalized.get("unresolved_fields"))
        if isinstance(row, dict)
    ]
    valid, failures = validate_scientific_target(target)
    if plan.get("scientific_target_hash") != target.get("target_hash"):
        failures = tuple((*failures, "SCIENTIFIC_TARGET_REFERENCE_HASH_MISMATCH"))
        valid = False
    if not isinstance(target_resolution, dict) or target_resolution.get("status") != "RESOLVED":
        failures = tuple((*failures, "PHYSICAL_TARGET_RESOLUTION_NOT_VERIFIED"))
        valid = False
    if valid:
        runtime["scientific_target"] = copy.deepcopy(target)
        evidence_contract = legacy.as_dict(runtime.get("evidence_contract"))
        evidence_contract.update({
            "scientific_target_hash": target["target_hash"],
            "target_specific_interpretation_required": True,
            "intent_is_not_support": True,
        })
        runtime["evidence_contract"] = evidence_contract
        source_target = legacy.as_dict(runtime.get("source_target_resolution"))
        source_target["scientific_target_hash"] = target["target_hash"]
        runtime["source_target_resolution"] = source_target
    else:
        for reason in sorted(set(failures)):
            row = {
                "field": "scientific_target",
                "reason": reason,
            }
            if row not in unresolved:
                unresolved.append(row)
        normalized["status"] = "NEEDS_RUNTIME_RESOLUTION"
    normalized["runtime"] = runtime
    normalized["runtime_hash"] = legacy.canonical_hash(runtime)
    normalized["unresolved_fields"] = unresolved
    policy = legacy.as_dict(normalized.get("policy"))
    policy.update({
        "scientific_target_carried_unchanged": bool(valid),
        "target_intent_is_not_support": True,
        "target_specific_interpretation_required": bool(valid),
    })
    normalized["policy"] = policy
    return normalized


def materialize_runtime(
    manifest,
    policy,
    prior,
    output_root,
    target_resolution=None,
    target_failures=None,
    protocol_resolution=None,
    protocol_failures=None,
):
    runtime_id = _runtime_id(manifest, prior)
    existing_path = _existing_runtime_package(Path(output_root), runtime_id)
    existing_package = _load_existing(existing_path) if existing_path.is_file() else {}
    plan = legacy.as_dict(manifest.get("plan"))
    requested_type = str(plan.get("experiment_type") or "").strip()

    # Never rewrite a cohort/search package once launch authorization or
    # execution has started.  The current BRIDGE3 repair target is unresolved,
    # unlaunched materialization only.
    if requested_type in COHORT_SEARCH_TYPES and existing_package and _execution_started(existing_package):
        return existing_package

    historical_package = existing_path.is_file()
    package = _original_materialize_runtime(
        manifest,
        policy,
        prior,
        output_root,
        target_resolution=target_resolution,
        target_failures=target_failures,
        protocol_resolution=protocol_resolution,
        protocol_failures=protocol_failures,
    )
    experiment_type = str(
        legacy.as_dict(package.get("runtime")).get("experiment_type") or ""
    ).strip()
    if not historical_package and experiment_type in BASELINE_ONLY_EXPERIMENT_TYPES:
        package = _baseline_only_normalize(package)
    if experiment_type in COHORT_SEARCH_TYPES:
        package = _cohort_search_normalize(
            package,
            manifest=manifest,
            output_root=Path(output_root),
        )
    package = _scientific_target_normalize(
        package,
        manifest=manifest,
        target_resolution=target_resolution,
    )
    return package


def build_materialization(experiments_root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    payload = _original_build_materialization(experiments_root, policy)
    packages = [
        row for row in legacy.as_list(payload.get("packages"))
        if isinstance(row, dict)
    ]
    # BRIDGE4 Search authorization is intentionally outside the legacy Stage
    # 6.5 Observer registry. If materialization is rerun after explicit Search
    # authorization/start, preserve the package's immutable authorization state
    # instead of rewriting the registry row as launch_authorized=false.
    output_root = Path(experiments_root).resolve() / "RuntimePackages"
    for row in packages:
        runtime_id = str(row.get("runtime_id") or "").strip()
        if not runtime_id:
            continue
        package = _load_existing(output_root / runtime_id / "runtime_package.json")
        if not package:
            continue
        if package.get("status") in {"SEARCH_LAUNCH_AUTHORIZED", "SEARCH_EXECUTION_STARTED"}:
            search_launch = legacy.as_dict(package.get("search_launch_authorization"))
            if search_launch.get("authorized") is True:
                row["status"] = package.get("status")
                row["launch_authorized"] = True
                row["updated_at"] = package.get("updated_at") or row.get("updated_at")
    summary = dict(payload.get("summary") or {})
    summary["ready_for_search_launch_review_count"] = sum(
        1 for row in packages if row.get("status") == SEARCH_READY_STATUS
    )
    summary["search_launch_authorized_count"] = sum(
        1 for row in packages if row.get("status") in {"SEARCH_LAUNCH_AUTHORIZED", "SEARCH_EXECUTION_STARTED"}
    )
    summary["search_execution_started_count"] = sum(
        1 for row in packages if row.get("status") == "SEARCH_EXECUTION_STARTED"
    )
    payload["summary"] = summary
    payload["content_hash"] = legacy.canonical_hash({
        "summary": summary,
        "packages": packages,
        "blocked_plans": legacy.as_list(payload.get("blocked_plans")),
        "source_registry": legacy.as_dict(payload.get("source_registry")),
    })
    return payload


legacy.materialize_runtime = materialize_runtime
legacy.build_materialization = build_materialization
render_markdown = legacy.render_markdown
main = legacy.main


if __name__ == "__main__":
    raise SystemExit(main())
