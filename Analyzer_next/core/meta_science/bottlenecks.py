"""Operational bottleneck ranking derived from Scientific Health."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.meta_science.numeric import clamp01, sf, si


COMPONENT_POLICIES = {
    "mechanism_coverage": {
        "types": {"infrastructure_upgrade", "mechanism", "matched_control_study"},
        "title": "Mechanism coverage",
        "why": "Too few rules have mechanism reports for reliable causal comparison.",
    },
    "validation_resolution": {
        "types": {
            "perturbation_test", "matched_control_study", "cross_family_replication",
            "negative_cohort_search", "prediction_followup",
        },
        "title": "Validation resolution",
        "why": "Open or testing predictions still lack decisive experiments.",
    },
    "research_debt_control": {
        "types": {"infrastructure_upgrade", "benchmark_control"},
        "title": "Research debt",
        "why": "Missing analyses and unresolved hypotheses are accumulating.",
    },
    "knowledge_coverage": {
        "types": {"replication_set", "long_run_replication"},
        "title": "Knowledge coverage",
        "why": "Some rules still lack complete core records.",
    },
    "discovery_coverage": {
        "types": {"explore", "cluster_replication"},
        "title": "Discovery coverage",
        "why": "A portion of known rules has no discovery-level interpretation.",
    },
    "integrity": {
        "types": {"integrity_repair"},
        "title": "Knowledge integrity",
        "why": "Broken or duplicate links undermine every downstream engine.",
    },
    "scientific_stability": {
        "types": {"counterexample_set", "benchmark_control"},
        "title": "Scientific stability",
        "why": "The evidence base may be insufficiently challenged by controls.",
    },
}


def compute_bottlenecks(
    laboratory_state: dict[str, Any],
    scientific_health: dict[str, Any],
) -> dict[str, Any]:
    components = scientific_health.get("components", {})
    weights = scientific_health.get("weights", {})
    queue = laboratory_state.get("experiment_queue", {})
    debt = laboratory_state.get("research_debt", {})
    pipeline = laboratory_state.get("prediction_pipeline", {})
    health = laboratory_state.get("laboratory_health", {})
    queue_items = queue.get("items", []) if isinstance(queue, dict) else []
    if not isinstance(queue_items, list):
        queue_items = []

    blocked_by_type: dict[str, int] = {}
    blocked_predictions: dict[str, list[str]] = {}
    for component, spec in COMPONENT_POLICIES.items():
        count = 0
        predictions: list[str] = []
        for item in queue_items:
            if not isinstance(item, dict):
                continue
            if str(item.get("type")) in spec["types"]:
                count += 1
                prediction_id = item.get("based_on_prediction")
                if prediction_id:
                    predictions.append(str(prediction_id))
        blocked_by_type[component] = count
        blocked_predictions[component] = sorted(set(predictions))

    candidates = []
    current_index = sf(scientific_health.get("index"))
    for component, score_value in components.items():
        score = clamp01(sf(score_value))
        weight = sf(weights.get(component))
        gap = 1.0 - score
        blocked = blocked_by_type.get(component, 0)
        severity = clamp01(
            0.60 * gap
            + 0.25 * clamp01(weight / 0.20)
            + 0.15 * clamp01(blocked / 4.0)
        )
        max_index_gain = max(0.0, weight * gap)
        spec = COMPONENT_POLICIES.get(component, {
            "title": component.replace("_", " ").title(),
            "why": "Component is below its desired level.",
        })
        candidates.append({
            "component": component,
            "title": spec["title"],
            "score": round(score, 4),
            "gap": round(gap, 4),
            "weight": round(weight, 4),
            "severity": round(severity, 4),
            "blocked_experiments": blocked,
            "blocked_predictions": blocked_predictions.get(component, []),
            "max_index_gain": round(max_index_gain, 4),
            "projected_index_if_fixed": round(clamp01(current_index + max_index_gain), 4),
            "why": spec["why"],
        })

    candidates.sort(
        key=lambda item: (
            item["severity"], item["max_index_gain"], item["blocked_experiments"]
        ),
        reverse=True,
    )
    signals = []
    unresolved = si(debt.get("unresolved_predictions"))
    missing_mechanisms = si(debt.get("rules_without_mechanisms"))
    if not bool(health.get("integrity_ok")):
        signals.append("Knowledge integrity must be repaired before scientific expansion.")
    if missing_mechanisms > 0:
        signals.append(f"{missing_mechanisms} rules lack mechanism reports.")
    if unresolved > 0:
        signals.append(f"{unresolved} predictions remain unresolved.")
    if si(pipeline.get("testing")) > 0:
        signals.append(f"{si(pipeline.get('testing'))} predictions are waiting for decisive tests.")

    return {
        "primary": candidates[0] if candidates else None,
        "secondary": candidates[1] if len(candidates) > 1 else None,
        "ranking": candidates,
        "signals": signals,
        "method": (
            "Severity combines component deficit, Scientific Health weight, "
            "and the number of blocked planned experiments."
        ),
    }
