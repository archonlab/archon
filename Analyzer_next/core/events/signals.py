"""Build smoothed, normalized, and differenced event signals."""
from __future__ import annotations

from Analyzer_next.core.events.numeric import (
    diff,
    mad,
    median,
    moving_average,
    normalize,
    safe_float,
)


def build_series(rows: list[dict]) -> dict[str, list[float]]:
    count = len(rows)
    radius = max(1, min(12, count // 24))
    raw = {
        "mass": [safe_float(row.get("_total_living_mass"), 0.0) for row in rows],
        "objects": [safe_float(row.get("_objects"), 0.0) for row in rows],
        "largest": [safe_float(row.get("_largest"), 0.0) for row in rows],
        "mci": [safe_float(row.get("_mci"), 0.0) for row in rows],
        "branching": [safe_float(row.get("_morphology_branching"), 0.0) for row in rows],
        "edge": [safe_float(row.get("_morphology_edge_complexity"), 0.0) for row in rows],
        "filament": [safe_float(row.get("_morphology_filament_score"), 0.0) for row in rows],
        "lattice": [safe_float(row.get("_morphology_lattice_score"), 0.0) for row in rows],
        "symmetry": [safe_float(row.get("_morphology_symmetry"), 0.0) for row in rows],
        "change": [safe_float(row.get("_morphology_change_rate"), 0.0) for row in rows],
        "pressure": [safe_float(row.get("_evo_pressure"), 0.0) for row in rows],
        "risk": [safe_float(row.get("_evo_extinction_risk"), 0.0) for row in rows],
        "stability": [safe_float(row.get("_stability_index"), 0.0) for row in rows],
        "knowledge": [safe_float(row.get("_knowledge_score"), 0.0) for row in rows],
    }
    smooth = {key: moving_average(values, radius) for key, values in raw.items()}
    normalized = {f"{key}_n": normalize(values) for key, values in smooth.items()}
    deltas = {f"{key}_d": diff(normalized[f"{key}_n"]) for key in raw}
    output: dict[str, list[float]] = {}
    output.update(raw)
    output.update(smooth)
    output.update(normalized)
    output.update(deltas)
    return output


def robust_threshold(
    values: list[float], min_threshold: float = 0.08, scale: float = 2.0
) -> float:
    magnitudes = [abs(value) for value in values]
    if not magnitudes:
        return min_threshold
    return max(min_threshold, median(magnitudes) + scale * mad(magnitudes))

