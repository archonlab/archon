"""Scientific Health Index calculation."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.meta_science.numeric import clamp01, sf, si


def compute_scientific_health(
    laboratory_state: dict[str, Any],
    research_metrics: dict[str, Any],
) -> dict[str, Any]:
    health = laboratory_state.get("laboratory_health", {})
    coverage = laboratory_state.get("coverage", {})
    pipeline = laboratory_state.get("prediction_pipeline", {})
    debt = laboratory_state.get("research_debt", {})

    rule_count = max(1, si(health.get("rules")))
    predictions_total = max(1, si(pipeline.get("generated")))

    integrity_component = 1.0 if health.get("integrity_ok") else 0.0
    passport_component = clamp01(sf(coverage.get("passport_percent")) / 100.0)
    atlas_component = clamp01(sf(coverage.get("atlas_percent")) / 100.0)
    knowledge_coverage_component = 0.55 * passport_component + 0.45 * atlas_component
    mechanism_component = clamp01(sf(coverage.get("mechanism_percent")) / 100.0)
    discovery_component = clamp01(sf(coverage.get("discovery_percent")) / 100.0)

    resolved_predictions = (
        si(pipeline.get("confirmed"))
        + si(pipeline.get("rejected"))
        + si(pipeline.get("inconclusive"))
    )
    validation_resolution_component = clamp01(resolved_predictions / predictions_total)

    unresolved_predictions = si(debt.get("unresolved_predictions"))
    missing_mechanisms = si(debt.get("rules_without_mechanisms"))
    missing_core_records = (
        si(debt.get("rules_without_passports"))
        + si(debt.get("rules_without_atlas_records"))
    )
    debt_load = (
        0.45 * clamp01(missing_mechanisms / rule_count)
        + 0.30 * clamp01(unresolved_predictions / predictions_total)
        + 0.25 * clamp01(missing_core_records / (2 * rule_count))
    )
    debt_component = 1.0 - clamp01(debt_load)
    scientific_stability_component = clamp01(sf(research_metrics.get("scientific_stability_score")))

    components = {
        "integrity": round(integrity_component, 4),
        "knowledge_coverage": round(knowledge_coverage_component, 4),
        "mechanism_coverage": round(mechanism_component, 4),
        "discovery_coverage": round(discovery_component, 4),
        "validation_resolution": round(validation_resolution_component, 4),
        "research_debt_control": round(debt_component, 4),
        "scientific_stability": round(scientific_stability_component, 4),
    }
    weights = {
        "integrity": 0.20,
        "knowledge_coverage": 0.15,
        "mechanism_coverage": 0.15,
        "discovery_coverage": 0.10,
        "validation_resolution": 0.15,
        "research_debt_control": 0.10,
        "scientific_stability": 0.15,
    }
    weighted = {
        name: round(components[name] * weight, 4)
        for name, weight in weights.items()
    }
    index = clamp01(sum(weighted.values()))
    if index >= 0.85:
        grade = "Excellent"
    elif index >= 0.70:
        grade = "Healthy"
    elif index >= 0.55:
        grade = "Developing"
    elif index >= 0.40:
        grade = "Fragile"
    else:
        grade = "Critical"

    weakest = sorted(components.items(), key=lambda item: item[1])[:3]
    return {
        "index": round(index, 4),
        "percent": round(index * 100.0, 2),
        "grade": grade,
        "components": components,
        "weights": weights,
        "weighted_contributions": weighted,
        "weakest_components": [
            {"name": name, "score": score} for name, score in weakest
        ],
        "note": (
            "This index measures laboratory-process health, coverage, validation "
            "progress, integrity, and research debt. It is not a truth score."
        ),
    }
