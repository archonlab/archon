#!/usr/bin/env python3
"""Modular guardrail entrypoint for Experiment Analyzer v1.4.

BRIDGE1 added profile/runtime provenance and fail-closed treatment contrast
checks. BRIDGE2 completes the experiment-analysis bridge by:

* reconciling completed experiment lifecycle metadata before read-only analysis;
* repairing unique auto-condition labels from canonical ``source_plan_id``;
* evaluating categorical reproducibility by matched rule/replicate/seed pairs;
* using replication-specific warnings for replication-only designs.
"""
from __future__ import annotations

import importlib
from collections import Counter
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.observer.experiment_analysis_runtime_guard import (  # noqa: E402
    audit_runtime_contrast,
)
from Analyzer_next.adapters.observer.experiment_metadata_reconcile import (  # noqa: E402
    reconcile_experiment_metadata,
)
from Analyzer_next.adapters.observer.experimental_target_context import (  # noqa: E402
    resolve_experimental_target,
)
from Analyzer_next.core.experimental_evidence.interpretation import (  # noqa: E402
    TARGET_INTERPRETATION_STATUSES,
    build_target_interpretation,
)
from Analyzer_next.core.experimental_evidence.contract import (  # noqa: E402
    build_experiment_evidence_contract,
    validate_evidence_contract,
)
from Analyzer_next.core.experimental_evidence.targeting import (  # noqa: E402
    canonical_hash,
    validate_scientific_target,
)

legacy = importlib.import_module(
    "Analyzer_next.compatibility.legacy_analyzer.experiment_analyzer"
)
_original_analyze_experiment = legacy.analyze_experiment
_original_audit_knowledge = legacy.audit_experiment_knowledge
_original_build_knowledge = legacy.build_experiment_knowledge_payload


def _zero_claim_summary() -> dict[str, Any]:
    return {
        "total": 0,
        "supported": 0,
        "mixed": 0,
        "not_supported": 0,
        "by_type": {},
    }


def _role(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"baseline", "baseline_control", "control"}:
        return "baseline"
    if text in {"treatment", "test"}:
        return "treatment"
    return text


def _pair_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        legacy.normalize_rule_id(row.get("rule_id")),
        row.get("replicate_index"),
        row.get("experiment_seed"),
    )


def _paired_categorical_reproducibility(
    result: dict[str, Any],
    rows: list[dict[str, Any]],
    profile_index: dict[str, dict[str, tuple[dict[str, Any], str]]],
) -> None:
    """Replace dominant-category preservation with matched-pair preservation."""
    baseline_rows = [row for row in rows if _role(row.get("role")) == "baseline"]
    treatment_rows = [row for row in rows if _role(row.get("role")) == "treatment"]
    baseline_by_key = {_pair_key(row): row for row in baseline_rows}

    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for treatment in treatment_rows:
        baseline = baseline_by_key.get(_pair_key(treatment))
        if baseline is None:
            continue
        base_profile, _ = legacy.match_profile(baseline.get("run_id"), profile_index)
        test_profile, _ = legacy.match_profile(treatment.get("run_id"), profile_index)
        if isinstance(base_profile, dict) and isinstance(test_profile, dict):
            pairs.append((base_profile, test_profile))

    for outcome in result.get("outcomes", []):
        if outcome.get("outcome_type") != "categorical_state":
            continue
        metric = str(outcome.get("metric") or "")
        comparable = [
            (base.get(metric), test.get(metric))
            for base, test in pairs
            if base.get(metric) not in (None, "") and test.get(metric) not in (None, "")
        ]
        preserved = sum(str(base) == str(test) for base, test in comparable)
        total = len(comparable)
        ratio = preserved / total if total else None
        if total == 0:
            status = "unavailable"
        elif preserved == total:
            status = "preserved"
        elif preserved > 0:
            status = "mixed"
        else:
            status = "transitioned"
        outcome["status"] = status
        outcome["preserved_count"] = preserved
        outcome["preservation_ratio"] = ratio
        outcome["paired_n"] = total
        outcome["pairing_policy"] = "rule_replicate_seed"
        outcome["interpretation_policy"] = "paired_categorical_reproducibility_v1"

    summary = result.get("outcome_summary")
    if isinstance(summary, dict):
        outcomes = result.get("outcomes", [])
        summary["preserved_categorical"] = sum(
            item.get("outcome_type") == "categorical_state" and item.get("status") == "preserved"
            for item in outcomes
        )
        summary["mixed_categorical"] = sum(
            item.get("outcome_type") == "categorical_state" and item.get("status") == "mixed"
            for item in outcomes
        )
        summary["transitioned_categorical"] = sum(
            item.get("outcome_type") == "categorical_state" and item.get("status") == "transitioned"
            for item in outcomes
        )


def analyze_experiment(experiment_id, rows, profile_index):
    result = _original_analyze_experiment(experiment_id, rows, profile_index)
    result_metadata = (
        result.get("experiment_metadata")
        if isinstance(result.get("experiment_metadata"), dict)
        else {}
    )
    audit = audit_runtime_contrast(
        PROJECT_ROOT,
        str(experiment_id),
        source_runtime_id=str(
            result_metadata.get("source_runtime_id") or ""
        ).strip() or None,
    )
    result["runtime_contrast_audit"] = audit.to_dict()

    if not result.get("experiment_type") and audit.experiment_type:
        result["experiment_type"] = audit.experiment_type
        metadata = dict(result.get("experiment_metadata") or {})
        metadata["experiment_type"] = audit.experiment_type
        metadata["experiment_type_source"] = "runtime_package"
        result["experiment_metadata"] = metadata
        result["limitations"] = [
            item
            for item in result.get("limitations", [])
            if item != "experiment_type_not_declared"
        ]

    warnings = list(result.get("warnings", []))
    limitations = list(result.get("limitations", []))

    if audit.status == "REPLICATION_ONLY":
        warnings.append("baseline_and_treatment_runtime_configuration_identical")
        warnings = [item for item in warnings if item != "small_treatment_sample"]
        if audit.paired_rows < 5:
            warnings.append("small_replication_sample")
        limitations.append("replication_only_design")
        result["analysis_mode"] = "reproducibility_only"
        _paired_categorical_reproducibility(result, rows, profile_index)
        for outcome in result.get("outcomes", []):
            outcome["interpretation_scope"] = "paired_reproducibility_only"
        result["claims"] = []
        result["claim_summary"] = _zero_claim_summary()
    elif audit.status == "INVALID_TREATMENT_CONTRAST":
        warnings.append("treatment_not_distinct_from_baseline")
        limitations.append("invalid_treatment_contrast")
        result["analysis_mode"] = "invalid_treatment_contrast"
        result["analysis_confidence"] = "NONE"
        for outcome in result.get("outcomes", []):
            outcome["confidence"] = "NONE"
            outcome["interpretation_scope"] = "invalid_treatment_contrast"
        result["claims"] = []
        result["claim_summary"] = _zero_claim_summary()
    elif audit.status == "DISTINCT_TREATMENT_CONTRAST":
        result["analysis_mode"] = "controlled_comparison"
    elif audit.status == "NO_TREATMENT_ARM":
        warnings = [item for item in warnings if item != "small_treatment_sample"]
        if audit.experiment_type == "metric_validation_baseline":
            result["analysis_mode"] = "replication_baseline"
            limitations.append("replication_baseline_design")
            if audit.baseline_rows < 5:
                warnings.append("small_replication_sample")
        else:
            result["analysis_mode"] = "single_arm"
    else:
        warnings.append("runtime_contrast_not_verified")
        result["analysis_mode"] = "runtime_contrast_unverified"

    result["warnings"] = sorted(set(warnings))
    result["limitations"] = sorted(set(limitations))
    experiment_metadata = result.get("experiment_metadata")
    if not isinstance(experiment_metadata, dict):
        experiment_metadata = {}
    target_context = resolve_experimental_target(
        project_root=PROJECT_ROOT,
        experiment_id=str(experiment_id),
        rows=rows,
        experiment_metadata=experiment_metadata,
    )
    if target_context.status != "NOT_TARGETED":
        result["scientific_target_resolution"] = {
            "status": target_context.status,
            "source_runtime_id": target_context.source_runtime_id,
            "runtime_path": target_context.runtime_path,
            "reasons": list(target_context.reasons),
        }
        if target_context.recovery is not None:
            result["scientific_target_resolution"]["recovery"] = dict(
                target_context.recovery
            )
    if target_context.target is not None:
        profile_rows: list[dict[str, Any]] = []
        for row in rows:
            profile, match_method = legacy.match_profile(
                row.get("run_id"), profile_index
            )
            context = row.get("experimental_context")
            context = context if isinstance(context, dict) else {}
            profile_rows.append({
                "run_id": row.get("run_id"),
                "role": row.get("role"),
                "treatment_arm": (
                    row.get("treatment_arm")
                    or context.get("treatment_arm")
                ),
                "profile": profile,
                "profile_match_method": match_method,
            })
        interpretation = build_target_interpretation(
            target=target_context.target,
            experiment_result=result,
            profile_rows=profile_rows,
            runtime_package=target_context.runtime_package,
            target_recovery=target_context.recovery,
        )
        result["scientific_target"] = target_context.target
        result["target_interpretation"] = interpretation
        for outcome in result.get("outcomes", []):
            outcome["interpretation_level"] = "OBSERVED_EFFECT"
            outcome["scientific_target_ref"] = {
                "target_id": target_context.target["target_id"],
                "target_hash": target_context.target["target_hash"],
            }
        for claim in result.get("claims", []):
            claim["interpretation_level"] = "CLAIM_SIGNAL"
            claim["scientific_target_ref"] = {
                "target_id": target_context.target["target_id"],
                "target_hash": target_context.target["target_hash"],
                "target_interpretation_id": interpretation[
                    "interpretation_id"
                ],
                "intent_is_not_support": True,
            }
    return result


def build_experiment_knowledge_payload(
    analysis_payload: dict[str, Any],
) -> dict[str, Any]:
    payload = _original_build_knowledge(analysis_payload)
    targeted = [
        experiment
        for experiment in analysis_payload.get("experiments", [])
        if isinstance(experiment, dict)
        and isinstance(experiment.get("scientific_target"), dict)
        and isinstance(experiment.get("target_interpretation"), dict)
    ]
    targets: dict[str, dict[str, Any]] = {}
    interpretations: dict[str, dict[str, Any]] = {}
    observed_effects: dict[str, dict[str, Any]] = {}
    relations = payload.get("relations")
    if not isinstance(relations, dict):
        relations = {}
        payload["relations"] = relations
    relations.setdefault("experiment_targets", [])
    relations.setdefault("target_interpretations", [])
    relations.setdefault("interpretation_effects", [])

    for experiment in targeted:
        experiment_id = str(experiment.get("experiment_id"))
        target = dict(experiment["scientific_target"])
        interpretation = dict(experiment["target_interpretation"])
        target_hash = str(target["target_hash"])
        interpretation_id = str(interpretation["interpretation_id"])
        targets[target_hash] = target
        interpretations[interpretation_id] = interpretation
        for effect in interpretation.get("observed_effects", []):
            if isinstance(effect, dict) and effect.get("effect_id"):
                observed_effects[str(effect["effect_id"])] = dict(effect)

        stored_experiment = payload["experiments"].get(experiment_id, {})
        stored_experiment["scientific_target_ref"] = {
            "target_id": target.get("target_id"),
            "target_hash": target_hash,
        }
        stored_experiment["target_interpretation_id"] = interpretation_id
        payload["experiments"][experiment_id] = stored_experiment
        relations["experiment_targets"].append({
            "experiment_id": experiment_id,
            "target_id": target.get("target_id"),
            "target_hash": target_hash,
        })
        relations["target_interpretations"].append({
            "target_hash": target_hash,
            "interpretation_id": interpretation_id,
        })
        for effect_id in interpretation.get("observed_effect_ids", []):
            relations["interpretation_effects"].append({
                "interpretation_id": interpretation_id,
                "effect_id": str(effect_id),
            })

        for claim_id in stored_experiment.get("claim_ids", []):
            claim = payload["claims"].get(str(claim_id))
            if not isinstance(claim, dict):
                continue
            claim.setdefault("interpretation_level", "CLAIM_SIGNAL")
            claim["scientific_target_ref"] = {
                "target_id": target.get("target_id"),
                "target_hash": target_hash,
                "target_interpretation_id": interpretation_id,
                "intent_is_not_support": True,
            }

    # Preserve the runtime comparison decision in Experiment Knowledge so the
    # producer can normalize matched-control and replication status once.
    for experiment in analysis_payload.get("experiments", []):
        if not isinstance(experiment, dict):
            continue
        experiment_id = str(experiment.get("experiment_id") or "")
        stored = payload.get("experiments", {}).get(experiment_id)
        if not isinstance(stored, dict):
            continue
        stored["analysis_mode"] = experiment.get("analysis_mode")
        audit = experiment.get("runtime_contrast_audit")
        if isinstance(audit, dict):
            stored["runtime_contrast_audit"] = dict(audit)

    payload["schema"] = "archon_experiment_knowledge_v3"
    payload["scientific_targets"] = targets
    payload["target_interpretations"] = interpretations
    payload["observed_effects"] = observed_effects
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    summary.update({
        "targeted_experiments": len(targeted),
        "scientific_targets": len(targets),
        "target_interpretations": len(interpretations),
        "target_interpretation_statuses": dict(
            Counter(
                item.get("status") for item in interpretations.values()
            )
        ),
    })
    payload["summary"] = summary
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        policy = {}
    policy.update({
        "interpretation_levels_separated": True,
        "target_intent_is_not_support": True,
        "target_specific_interpretation_required": True,
        "experimental_evidence_contract_required": True,
        "evidence_consumer_reads_raw_claims": False,
        "adjacent_evidence_lineage_required": True,
        "evidence_level_skipping_forbidden": True,
    })
    payload["policy"] = policy
    payload["experimental_evidence_contract"] = (
        build_experiment_evidence_contract(payload)
    )
    summary["experimental_evidence_records"] = payload[
        "experimental_evidence_contract"
    ]["record_count"]
    summary["experimental_evidence_normalization_rejections"] = len(
        payload["experimental_evidence_contract"].get(
            "normalization_rejections", []
        )
    )
    return payload


def audit_experiment_knowledge(payload):
    report = _original_audit_knowledge(payload)
    semantic_issues: list[dict[str, Any]] = []
    semantic_warnings: list[dict[str, Any]] = []

    for experiment_id, experiment in (payload.get("experiments") or {}).items():
        warnings = set(experiment.get("warnings") or [])
        experiment_status = str(
            experiment.get("experiment_status") or "unknown"
        ).strip().lower()
        outcomes = [
            (payload.get("outcomes") or {}).get(outcome_id, {})
            for outcome_id in experiment.get("outcome_ids", [])
        ]
        if outcomes and all(item.get("status") == "unavailable" for item in outcomes):
            semantic_issues.append({
                "code": "all_outcomes_unavailable",
                "experiment_id": experiment_id,
            })
        if "baseline_and_treatment_runtime_configuration_identical" in warnings:
            semantic_issues.append({
                "code": "replication_only_no_treatment_contrast",
                "experiment_id": experiment_id,
            })
        if "treatment_not_distinct_from_baseline" in warnings:
            semantic_issues.append({
                "code": "treatment_not_distinct_from_baseline",
                "experiment_id": experiment_id,
            })
        if "profile_records_missing_for_some_runs" in warnings:
            record = {
                "code": "incomplete_experiment_profile_coverage",
                "experiment_id": experiment_id,
                "experiment_status": experiment_status,
            }
            if experiment_status == "completed":
                semantic_issues.append(record)
            else:
                # Planned/running/failed/cancelled experiments are not
                # evidence-bearing completed results. Missing profiles remain
                # visible as a warning, but must not poison global scientific
                # integrity for completed Experiment Knowledge.
                semantic_warnings.append(record)

    targets = payload.get("scientific_targets") or {}
    interpretations = payload.get("target_interpretations") or {}
    if isinstance(targets, dict) and isinstance(interpretations, dict):
        for target_hash, target in targets.items():
            valid, failures = validate_scientific_target(target)
            if not valid or target_hash != target.get("target_hash"):
                semantic_issues.append({
                    "code": "scientific_target_integrity_failure",
                    "target_hash": target_hash,
                    "reasons": list(failures),
                })
        for interpretation_id, interpretation in interpretations.items():
            if interpretation.get("status") not in TARGET_INTERPRETATION_STATUSES:
                semantic_issues.append({
                    "code": "target_interpretation_status_invalid",
                    "interpretation_id": interpretation_id,
                })
            target_hash = str(interpretation.get("target_hash") or "")
            if target_hash not in targets:
                semantic_issues.append({
                    "code": "target_interpretation_unknown_target",
                    "interpretation_id": interpretation_id,
                    "target_hash": target_hash,
                })
            recovery = interpretation.get("target_recovery")
            if isinstance(recovery, dict):
                immutable_recovery = {
                    key: value
                    for key, value in recovery.items()
                    if key != "recovery_hash"
                }
                if (
                    recovery.get("schema")
                    != "archon_historical_target_recovery_v1"
                    or recovery.get("status") != "RECOVERED"
                    or recovery.get("target_hash") != target_hash
                    or recovery.get("recovery_hash")
                    != canonical_hash(immutable_recovery)
                ):
                    semantic_issues.append({
                        "code": "historical_target_recovery_integrity_failure",
                        "interpretation_id": interpretation_id,
                    })

    contract = payload.get("experimental_evidence_contract")
    contract_valid, contract_failures = validate_evidence_contract(contract)
    if not contract_valid:
        semantic_issues.append({
            "code": "experimental_evidence_contract_integrity_failure",
            "reasons": list(contract_failures),
        })
    elif isinstance(contract, dict):
        expected_interpretations = (
            len(interpretations) if isinstance(interpretations, dict) else 0
        )
        expected_levels = {
            "OBSERVED_EFFECT": (
                len(payload.get("outcomes") or {})
                + len(payload.get("observed_effects") or {})
                + expected_interpretations
            ),
            "CLAIM_SIGNAL": (
                len(payload.get("claims") or {}) + expected_interpretations
            ),
            "PRINCIPLE_SIGNAL": expected_interpretations,
        }
        actual_levels = (
            contract.get("summary", {}).get("interpretation_levels", {})
        )
        if actual_levels != {
            key: value for key, value in expected_levels.items() if value
        }:
            semantic_issues.append({
                "code": "experimental_evidence_contract_coverage_failure",
                "expected_interpretation_levels": expected_levels,
                "actual_interpretation_levels": actual_levels,
            })
        if contract.get("normalization_rejections"):
            semantic_issues.append({
                "code": "experimental_evidence_contract_normalization_rejections",
                "rejections": list(contract.get("normalization_rejections", [])),
            })

    report["structural_ok"] = bool(report.get("ok"))
    report["scientific_ok"] = not semantic_issues
    report["semantic_issue_count"] = len(semantic_issues)
    report["semantic_issues"] = semantic_issues
    report["semantic_warning_count"] = len(semantic_warnings)
    report["semantic_warnings"] = semantic_warnings
    return report


def _argument_value(argv: list[str], name: str) -> str | None:
    try:
        index = argv.index(name)
    except ValueError:
        return None
    if index + 1 >= len(argv):
        return None
    return argv[index + 1]


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    database_text = _argument_value(arguments, "--telemetry-db")
    if database_text:
        report = reconcile_experiment_metadata(Path(database_text))
        print(
            "[BRIDGE2] experiment metadata reconciliation: "
            f"status={report.status_updates} "
            f"condition_names={report.condition_name_updates} "
            f"shared_skips={report.shared_condition_skips}"
        )
    return legacy.main(arguments)


legacy.analyze_experiment = analyze_experiment
legacy.audit_experiment_knowledge = audit_experiment_knowledge
legacy.build_experiment_knowledge_payload = build_experiment_knowledge_payload


if __name__ == "__main__":
    raise SystemExit(main())
