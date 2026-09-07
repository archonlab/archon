"""Deterministic Observed Effect -> Claim Signal -> Principle Signal layer."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import statistics
from typing import Any, Iterable, Mapping

from Analyzer_next.core.scientific_claims import (
    CLAIM_SPECS,
    missing_required_fields,
)

from .targeting import canonical_hash, validate_scientific_target


TARGET_INTERPRETATION_STATUSES = frozenset({
    "SUPPORTED",
    "CONTRADICTED",
    "MIXED",
    "NON_DIAGNOSTIC",
    "INSUFFICIENT_DATA",
})


def _role(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"baseline", "baseline_control", "control"}:
        return "baseline"
    if text in {"treatment", "test"}:
        return "treatment"
    return text


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _aggregate(values: Iterable[Any]) -> Any:
    materialized = [
        value for value in values
        if value is not None and value != ""
    ]
    numeric = [
        number for value in materialized
        if (number := _finite_number(value)) is not None
    ]
    if materialized and len(numeric) == len(materialized):
        return statistics.fmean(numeric)
    if not materialized:
        return None
    counts = Counter(str(value) for value in materialized)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _arm_profiles(
    profile_rows: Iterable[Mapping[str, Any]],
    metrics: list[str],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in profile_rows:
        profile = row.get("profile")
        if not isinstance(profile, Mapping):
            continue
        role = _role(row.get("role"))
        arm = str(row.get("treatment_arm") or "").strip()
        key = "baseline" if role == "baseline" else (arm or "treatment")
        grouped[key].append(profile)
    result: dict[str, dict[str, Any]] = {}
    for arm, profiles in sorted(grouped.items()):
        result[arm] = {
            metric: _aggregate(profile.get(metric) for profile in profiles)
            for metric in metrics
        }
        result[arm]["profile_count"] = len(profiles)
    return result


def _observed_effects(
    experiment_id: str,
    target_id: str,
    baseline: Mapping[str, Any],
    treatments: Mapping[str, Mapping[str, Any]],
    metrics: list[str],
) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for arm, profile in sorted(treatments.items()):
        for metric in metrics:
            before = baseline.get(metric)
            after = profile.get(metric)
            b = _finite_number(before)
            a = _finite_number(after)
            if b is not None and a is not None:
                absolute = a - b
                relative = absolute / abs(b) if b != 0 else None
                direction = (
                    "increased" if relative is not None and relative > 0.05
                    else "decreased" if relative is not None and relative < -0.05
                    else "approximately_stable"
                )
            else:
                absolute = None
                relative = None
                direction = (
                    "preserved" if before not in {None, ""} and before == after
                    else "changed" if before not in {None, ""} and after not in {None, ""}
                    else "unavailable"
                )
            effect = {
                "schema": "archon_observed_effect_v1",
                "interpretation_level": "OBSERVED_EFFECT",
                "experiment_id": experiment_id,
                "target_id": target_id,
                "treatment_arm": arm,
                "metric": metric,
                "baseline_value": before,
                "treatment_value": after,
                "absolute_effect": absolute,
                "relative_effect": relative,
                "direction": direction,
            }
            effect["effect_id"] = (
                "OEF-" + canonical_hash(effect)[:20].upper()
            )
            effects.append(effect)
    return effects


def _design_status(runtime_package: Mapping[str, Any]) -> tuple[str, str]:
    runtime = runtime_package.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    rows = [
        row for row in runtime.get("run_matrix", [])
        if isinstance(row, Mapping)
    ]
    baseline = [row for row in rows if _role(row.get("role")) == "baseline"]
    treatment = [row for row in rows if _role(row.get("role")) == "treatment"]
    interventions = sum(
        row.get("perturbation") not in (None, {}, [], (), "")
        for row in treatment
    )
    if not rows:
        return "UNVERIFIED", "runtime run_matrix unavailable"
    if not baseline:
        return "NO_MATCHED_CONTROL", "runtime has no baseline control arm"
    if not treatment:
        return "NO_TREATMENT", "runtime has no treatment arm"
    if interventions == 0:
        return "NO_EXPLICIT_INTERVENTION", "treatment arm has no explicit intervention"
    return "MATCHED_CONTROLLED_INTERVENTION", "matched control and explicit intervention are present"


def _confidence(result: Mapping[str, Any], design_status: str) -> str:
    raw = str(
        result.get("analysis_confidence")
        or result.get("design_confidence")
        or "NONE"
    ).upper()
    if design_status != "MATCHED_CONTROLLED_INTERVENTION":
        return "NONE" if raw == "NONE" else "LOW"
    return raw if raw in {"LOW", "PRELIMINARY", "MEDIUM", "HIGH", "VERY_HIGH"} else "NONE"


def build_target_interpretation(
    *,
    target: Mapping[str, Any],
    experiment_result: Mapping[str, Any],
    profile_rows: Iterable[Mapping[str, Any]],
    runtime_package: Mapping[str, Any] | None = None,
    target_recovery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Interpret one controlled experiment against its immutable target."""
    valid, failures = validate_scientific_target(target)
    experiment_id = str(experiment_result.get("experiment_id") or "")
    target_id = str(target.get("target_id") or "")
    metrics = [str(value) for value in target.get("target_metrics", [])]
    runtime_package = runtime_package or {}
    design_status, design_reason = _design_status(runtime_package)
    arms = _arm_profiles(profile_rows, metrics)
    baseline = arms.get("baseline", {})
    treatments = {
        key: value for key, value in arms.items() if key != "baseline"
    }
    effects = _observed_effects(
        experiment_id,
        target_id,
        baseline,
        treatments,
        metrics,
    ) if baseline and treatments else []

    limitations: list[str] = []
    reason_codes: list[str] = []
    arm_evaluations: list[dict[str, Any]] = []
    spec = CLAIM_SPECS.get(target_id)
    question_type = str(target.get("question_type") or "")
    recovery = (
        dict(target_recovery)
        if isinstance(target_recovery, Mapping)
        else {}
    )
    recovery_mode = str(recovery.get("mode") or "")
    if recovery:
        limitations.extend([
            "historical_target_recovery",
            "target_not_carried_at_execution",
        ])

    if not valid:
        status = "NON_DIAGNOSTIC"
        reason_codes.extend(failures)
    elif spec is None:
        status = "NON_DIAGNOSTIC"
        reason_codes.append("TARGET_CLAIM_SPEC_UNAVAILABLE")
    elif recovery_mode == "VERIFIED_PLAN_INTENT_ONLY":
        # The principle intent existed before execution, but target metrics
        # were selected only during historical recovery.  Those measurements
        # may be described, never promoted into a post-hoc principle verdict.
        status = "NON_DIAGNOSTIC"
        reason_codes.append("HISTORICAL_TARGET_METRICS_NOT_PRECOMMITTED")
        limitations.extend([
            "target_metrics_not_precommitted",
        ])
        if design_status != "MATCHED_CONTROLLED_INTERVENTION":
            reason_codes.append(design_status)
    elif question_type == "metric_validation":
        status = "NON_DIAGNOSTIC"
        reason_codes.append("METRIC_VALIDATION_DOES_NOT_TEST_PRINCIPLE")
        limitations.append("measurement_readiness_only")
    elif design_status != "MATCHED_CONTROLLED_INTERVENTION":
        status = "NON_DIAGNOSTIC"
        reason_codes.append(design_status)
    elif not baseline or not treatments:
        status = "INSUFFICIENT_DATA"
        reason_codes.append("MATCHED_ARM_PROFILES_MISSING")
    else:
        baseline_missing = missing_required_fields(spec, dict(baseline))
        if baseline_missing:
            baseline_state = "unavailable"
            baseline_strength = 0.0
            baseline_reason = "missing required measurements: " + ", ".join(baseline_missing)
        else:
            baseline_state, baseline_strength, baseline_reason = spec.test(dict(baseline))
        unavailable_arms = 0
        treatment_states: list[str] = []
        for arm, profile in sorted(treatments.items()):
            missing = missing_required_fields(spec, dict(profile))
            if missing:
                state, strength, reason = (
                    "unavailable",
                    0.0,
                    "missing required measurements: " + ", ".join(missing),
                )
                unavailable_arms += 1
            else:
                state, strength, reason = spec.test(dict(profile))
            treatment_states.append(state)
            arm_evaluations.append({
                "arm": arm,
                "claim_state": state,
                "claim_strength": round(float(strength), 6),
                "reason": reason,
                "missing_metrics": list(missing),
            })
        arm_evaluations.insert(0, {
            "arm": "baseline",
            "claim_state": baseline_state,
            "claim_strength": round(float(baseline_strength), 6),
            "reason": baseline_reason,
            "missing_metrics": list(baseline_missing),
        })

        informative = [state for state in treatment_states if state != "unavailable"]
        states = set(informative)
        if not informative:
            status = "INSUFFICIENT_DATA"
            reason_codes.append("TARGET_METRICS_UNAVAILABLE_IN_TREATMENT")
        elif "support" in states and "counterexample" in states:
            status = "MIXED"
            reason_codes.append("TREATMENT_ARMS_DISAGREE")
        elif states == {"counterexample"}:
            status = "CONTRADICTED"
            reason_codes.append("TARGET_COUNTEREXAMPLE_OBSERVED")
        elif states == {"support"}:
            status = "SUPPORTED"
            reason_codes.append(
                "SUPPORT_PRESERVED_UNDER_INTERVENTION"
                if baseline_state == "support"
                else "TARGET_SUPPORT_OBSERVED_IN_TREATMENT"
            )
        elif "support" in states or "counterexample" in states:
            status = "MIXED"
            reason_codes.append("INFORMATIVE_AND_NEUTRAL_ARMS")
        else:
            status = "NON_DIAGNOSTIC"
            reason_codes.append("TARGET_CLASSIFIER_NEUTRAL")
        if unavailable_arms:
            limitations.append("incomplete_target_metric_coverage")

    if status not in TARGET_INTERPRETATION_STATUSES:
        raise AssertionError(f"invalid target interpretation status: {status}")
    if not effects:
        limitations.append("observed_effects_unavailable")
    confidence = _confidence(experiment_result, design_status)
    supporting_metrics = metrics if status == "SUPPORTED" else []
    contradicting_metrics = metrics if status == "CONTRADICTED" else []
    interpretation = {
        "schema": "archon_target_specific_interpretation_v1",
        "version": "1.0",
        "interpretation_level": "PRINCIPLE_SIGNAL",
        "experiment_id": experiment_id,
        "target_type": target.get("target_type"),
        "target_id": target_id,
        "target_hash": target.get("target_hash"),
        "action_id": target.get("action_id"),
        "question_type": question_type,
        "status": status,
        "confidence": confidence,
        "reason_codes": sorted(set(reason_codes)),
        "design": {
            "status": design_status,
            "reason": design_reason,
            "matched_control_status": (
                "AUTHORITATIVE_MATCHED_CONTROL"
                if design_status == "MATCHED_CONTROLLED_INTERVENTION"
                else design_status
            ),
        },
        "target_metrics": metrics,
        "supporting_metrics": supporting_metrics,
        "contradicting_metrics": contradicting_metrics,
        "observed_effect_ids": [effect["effect_id"] for effect in effects],
        "observed_effects": effects,
        "arm_evaluations": arm_evaluations,
        "limitations": sorted(set(limitations)),
        "scientific_effect": {
            "observational_counts_changed": False,
            "principle_confidence_changed": False,
            "automatic_promotion": False,
            "consensus_effect": False,
        },
    }
    if recovery:
        interpretation["target_recovery"] = recovery
    provenance = {
        "experiment_id": experiment_id,
        "target_hash": target.get("target_hash"),
        "run_ids": sorted(str(value) for value in experiment_result.get("run_ids", [])),
        "observed_effect_ids": interpretation["observed_effect_ids"],
        "design_status": design_status,
    }
    if recovery:
        provenance["target_recovery_hash"] = recovery.get("recovery_hash")
    interpretation["provenance_hash"] = canonical_hash(provenance)
    interpretation["interpretation_id"] = (
        "TSI-" + canonical_hash({
            "target_hash": target.get("target_hash"),
            "provenance_hash": interpretation["provenance_hash"],
            "status": status,
        })[:20].upper()
    )
    return interpretation


__all__ = [
    "TARGET_INTERPRETATION_STATUSES",
    "build_target_interpretation",
]
