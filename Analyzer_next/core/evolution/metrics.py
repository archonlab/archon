"""Smoothed local metrics used to label life-cycle stages."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.evolution.numeric import mean, safe_float, slope, stdev


def window_rows(
    rows: list[dict[str, Any]], index: int, radius: int
) -> list[dict[str, Any]]:
    start = max(0, index - radius)
    end = min(len(rows), index + radius + 1)
    return rows[start:end]


def row_metrics(window: list[dict[str, Any]]) -> dict[str, float]:
    if not window:
        return {}
    mass = [safe_float(row.get("_total_living_mass"), 0.0) for row in window]
    objects = [safe_float(row.get("_objects"), 0.0) for row in window]
    largest = [safe_float(row.get("_largest"), 0.0) for row in window]
    mci = [safe_float(row.get("_mci"), 0.0) for row in window]
    branching = [safe_float(row.get("_morphology_branching"), 0.0) for row in window]
    edge = [safe_float(row.get("_morphology_edge_complexity"), 0.0) for row in window]
    change = [safe_float(row.get("_morphology_change_rate"), 0.0) for row in window]
    pressure = [safe_float(row.get("_evo_pressure"), 0.0) for row in window]
    risk = [safe_float(row.get("_evo_extinction_risk"), 0.0) for row in window]
    stability = [safe_float(row.get("_stability_index"), 0.0) for row in window]
    return {
        "mass": mean(mass),
        "objects": mean(objects),
        "largest": mean(largest),
        "mci": mean(mci),
        "branching": mean(branching),
        "edge": mean(edge),
        "change_rate": mean(change),
        "pressure": mean(pressure),
        "risk": mean(risk),
        "stability": mean(stability),
        "mass_slope": slope(mass) / max(1.0, max(mass) if mass else 1.0),
        "objects_slope": slope(objects) / max(1.0, max(objects) if objects else 1.0),
        "mci_slope": slope(mci),
        "branching_slope": slope(branching),
        "edge_slope": slope(edge) / 40.0,
        "change_slope": slope(change),
        "mci_volatility": stdev(mci),
        "change_volatility": stdev(change),
    }

