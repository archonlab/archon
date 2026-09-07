"""Trajectory comparison, confidence grading, and effect interpretation."""
from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any

from .constants import CATEGORICAL_METRICS, NUMERIC_METRICS
from .feature_builder import index_rows_by_tick
from .utils import safe_float

def aligned_differences(
    baseline_rows: list[dict[str, str]],
    mutant_rows: list[dict[str, str]],
) -> dict[str, Any]:
    baseline_by_tick = index_rows_by_tick(baseline_rows)
    mutant_by_tick = index_rows_by_tick(mutant_rows)
    common_ticks = sorted(set(baseline_by_tick) & set(mutant_by_tick))

    if not common_ticks:
        return {
            "common_tick_count": 0,
            "tick_range": None,
            "last_common_tick": None,
            "mean_absolute_difference": {},
            "signed_mean_difference": {},
            "categorical_at_last_common_tick": {},
            "warning": "No exactly matching sample ticks.",
        }

    mad: dict[str, float] = {}
    signed: dict[str, float] = {}

    for metric in NUMERIC_METRICS:
        differences: list[float] = []
        for tick in common_ticks:
            before = safe_float(baseline_by_tick[tick].get(metric))
            after = safe_float(mutant_by_tick[tick].get(metric))
            if before is not None and after is not None:
                differences.append(after - before)
        if differences:
            mad[metric] = round(
                sum(abs(value) for value in differences) / len(differences),
                8,
            )
            signed[metric] = round(sum(differences) / len(differences), 8)

    last_common_tick = common_ticks[-1]
    base_last = baseline_by_tick[last_common_tick]
    mutant_last = mutant_by_tick[last_common_tick]
    categorical_common: dict[str, Any] = {}
    for metric in CATEGORICAL_METRICS:
        before = base_last.get(metric)
        after = mutant_last.get(metric)
        if before in {None, ""} and after in {None, ""}:
            continue
        categorical_common[metric] = {
            "baseline": before,
            "mutant": after,
            "changed": before != after,
        }

    return {
        "common_tick_count": len(common_ticks),
        "tick_range": [common_ticks[0], common_ticks[-1]],
        "last_common_tick": last_common_tick,
        "mean_absolute_difference": mad,
        "signed_mean_difference": signed,
        "categorical_at_last_common_tick": categorical_common,
        "warning": None,
    }


def comparison_confidence(
    baseline_match: dict[str, Any],
    baseline_rows: list[dict[str, str]],
    mutant_rows: list[dict[str, str]],
) -> dict[str, Any]:
    score = 0.20
    reasons: list[str] = []

    match_type = baseline_match.get("match_type")
    if match_type == "matched_experiment_control":
        score += 0.46
        reasons.append("authoritative matched experiment control")
    elif match_type == "required_control":
        score += 0.44
        reasons.append("required control explicitly linked")
    elif match_type == "exact_declared":
        score += 0.42
        reasons.append("baseline explicitly declared")
    elif match_type == "matched_seed_and_duration":
        score += 0.38
        reasons.append("same seed and sufficient duration")
    elif match_type == "matched_seed_partial_duration":
        score += 0.28
        reasons.append("same seed but partial duration")
    elif match_type == "matched_rule_and_duration":
        score += 0.22
        reasons.append("same canonical rule and sufficient duration")
    elif match_type == "approximate_rule_baseline":
        score += 0.10
        reasons.append("approximate canonical baseline")
    else:
        return {
            "score": 0.0,
            "grade": "MISSING",
            "reasons": ["baseline missing"],
        }

    if baseline_match.get("same_seed") is True:
        score += 0.10
        if match_type == "matched_experiment_control":
            reasons.append("same experiment seed verified from experiment registry")
        else:
            reasons.append("same experiment seed verified from rule snapshots")

    coverage = safe_float(baseline_match.get("coverage_ratio")) or 0.0
    score += 0.20 * min(1.0, coverage)
    reasons.append(f"duration coverage={coverage:.2f}")

    common_ticks = len(
        set(index_rows_by_tick(baseline_rows))
        & set(index_rows_by_tick(mutant_rows))
    )
    overlap_ratio = common_ticks / max(1, len(mutant_rows))
    score += 0.18 * min(1.0, overlap_ratio)
    reasons.append(f"exact tick overlap={overlap_ratio:.2f}")

    score = max(0.0, min(1.0, score))
    if score >= 0.85:
        grade = "VERY_HIGH"
    elif score >= 0.70:
        grade = "HIGH"
    elif score >= 0.50:
        grade = "MEDIUM"
    elif score > 0:
        grade = "LOW"
    else:
        grade = "MISSING"

    return {
        "score": round(score, 4),
        "grade": grade,
        "reasons": reasons,
    }


def effect_interpretation(
    baseline: dict[str, Any],
    mutant: dict[str, Any],
    delta: dict[str, Any],
    aligned: dict[str, Any],
    confidence: dict[str, Any],
    structural_extinction: dict[str, Any],
) -> dict[str, Any]:
    """
    Classify effects from the shared horizon, with collapse outcomes taking
    priority over categorical regime labels.
    """
    labels: list[str] = []
    evidence: list[str] = []

    if confidence.get("score", 0.0) < 0.50:
        return {
            "primary": "inconclusive",
            "labels": ["inconclusive"],
            "evidence": ["Comparison confidence below 0.50."],
            "basis": "shared_horizon_aligned_ticks",
        }

    base_alive = baseline.get("alive_at_end")
    mutant_alive = mutant.get("alive_at_end")

    baseline_extinct = (
        structural_extinction.get("baseline_structural_extinction_tick")
        is not None
    )
    mutant_extinct = (
        structural_extinction.get("mutant_structural_extinction_tick")
        is not None
    )

    if baseline_extinct and mutant_extinct:
        labels.append("structural_extinction_preserved")
        evidence.append(
            "Both canonical baseline and mutant reached persistent zero structure."
        )

        extinction_class = structural_extinction.get("classification")
        if extinction_class:
            labels.append(extinction_class)
            delta_tick = structural_extinction.get("tick_delta")
            if extinction_class == "structural_extinction_delayed":
                evidence.append(
                    f"Mutant structural extinction was delayed by "
                    f"{delta_tick} sampled ticks."
                )
            elif extinction_class == "structural_extinction_accelerated":
                evidence.append(
                    f"Mutant structural extinction was accelerated by "
                    f"{abs(delta_tick)} sampled ticks."
                )
            else:
                evidence.append(
                    "Structural-extinction timing remained within tolerance."
                )

        labels.append("mutation_no_structural_rescue")
        evidence.append(
            "Mutation did not preserve detectable structure through the horizon."
        )

    elif not baseline_extinct and mutant_extinct:
        labels.append("structural_extinction_induced")
        evidence.append(
            "Baseline retained detectable structure; mutant reached persistent "
            "zero structure."
        )
    elif baseline_extinct and not mutant_extinct:
        labels.append("structural_extinction_prevented")
        evidence.append(
            "Baseline reached persistent zero structure; mutant retained "
            "detectable structure."
        )

    signed = aligned.get("signed_mean_difference", {})
    normalized: dict[str, float] = {}
    for metric, signed_delta in signed.items():
        baseline_value = safe_float(
            baseline.get("tail_median", {}).get(metric)
        )
        if baseline_value is None or abs(baseline_value) < 1e-12:
            continue
        normalized[metric] = signed_delta / abs(baseline_value)

    beneficial = []
    harmful = []
    for metric in (
        "emergence_score",
        "feedback_score",
        "knowledge_score",
        "validation_quality",
        "stability_index",
        "total_living_mass",
    ):
        value = normalized.get(metric)
        if value is None:
            continue
        if value >= 0.10:
            beneficial.append((metric, value))
        elif value <= -0.10:
            harmful.append((metric, value))

    risk = normalized.get("evo_extinction_risk")
    if base_alive is not False or mutant_alive is not False:
        if risk is not None and risk >= 0.15:
            labels.append("destabilized")
            evidence.append(
                f"Aligned extinction risk increased by about {risk:.1%}."
            )
        elif risk is not None and risk <= -0.15:
            labels.append("stabilized")
            evidence.append(
                f"Aligned extinction risk decreased by about {abs(risk):.1%}."
            )

    both_extinct = baseline_extinct and mutant_extinct

    if len(beneficial) >= 2 and not harmful:
        labels.append(
            "pre_extinction_amplification"
            if both_extinct else "amplified"
        )
        evidence.append(
            "Multiple core aligned metrics increased before structural extinction."
            if both_extinct
            else "Multiple core aligned metrics increased by at least 10%."
        )
    elif len(harmful) >= 2 and not beneficial:
        labels.append(
            "pre_extinction_suppression"
            if both_extinct else "suppressed"
        )
        evidence.append(
            "Multiple core aligned metrics decreased before structural extinction."
            if both_extinct
            else "Multiple core aligned metrics decreased by at least 10%."
        )
    elif beneficial and harmful:
        labels.append(
            "extinction_path_redirected"
            if both_extinct else "redirected"
        )
        evidence.append(
            "Pre-extinction core metrics changed in opposing directions."
            if both_extinct
            else "Core aligned metrics changed in opposing directions."
        )

    transitions = aligned.get("categorical_at_last_common_tick", {})
    changed_categories = [
        key for key, item in transitions.items()
        if item.get("changed")
        and key in {
            "morphology_class",
            "feedback_regime",
            "emergence_confidence",
            "civ_stage",
            "ecosystem_phase",
            "growth_phase",
        }
    ]
    # Do not allow endpoint regime labels to overrule the shared collapse fact.
    if changed_categories and not both_extinct:
        labels.append("regime_transition")
        evidence.append(
            "Categorical transition at last common tick in: "
            + ", ".join(changed_categories)
        )

    drift = normalized.get("total_drift")
    morphology_rate = normalized.get("morphology_change_rate")
    if (
        (drift is not None and abs(drift) >= 0.15)
        or (morphology_rate is not None and abs(morphology_rate) >= 0.20)
    ):
        labels.append(
            "extinction_path_redirected"
            if both_extinct else "redirected"
        )
        evidence.append(
            "Pre-extinction spatial or morphological dynamics changed materially."
            if both_extinct
            else "Aligned spatial or morphological dynamics changed materially."
        )

    if not labels:
        labels.append("preserved")
        evidence.append(
            "No strong threshold-crossing effect detected on the shared horizon."
        )

    priority = [
        "structural_extinction_induced",
        "structural_extinction_prevented",
        "structural_extinction_preserved",
        "regime_transition",
        "destabilized",
        "stabilized",
        "extinction_path_redirected",
        "pre_extinction_amplification",
        "pre_extinction_suppression",
        "redirected",
        "amplified",
        "suppressed",
        "preserved",
    ]
    primary = next((label for label in priority if label in labels), labels[0])

    return {
        "primary": primary,
        "labels": list(dict.fromkeys(labels)),
        "evidence": evidence,
        "basis": "shared_horizon_aligned_ticks",
    }

