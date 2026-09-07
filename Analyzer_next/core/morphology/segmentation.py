"""Class segmentation, transition statistics, and local complexity."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from Analyzer_next.core.morphology.constants import NUMERIC_COLUMNS
from Analyzer_next.core.morphology.numeric import mean, safe_float, stdev


def build_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    segments = []
    current_class = rows[0]["_class"]
    start_tick = rows[0]["_tick"]
    last_tick = start_tick
    sample_count = 0

    for row in rows:
        morphology_class = row["_class"]
        tick = row["_tick"]
        if morphology_class != current_class:
            segments.append({
                "class": current_class,
                "start_tick": start_tick,
                "end_tick": last_tick,
                "duration_ticks": max(0, last_tick - start_tick),
                "samples": sample_count,
            })
            current_class = morphology_class
            start_tick = tick
            sample_count = 1
        else:
            sample_count += 1
        last_tick = tick

    segments.append({
        "class": current_class,
        "start_tick": start_tick,
        "end_tick": last_tick,
        "duration_ticks": max(0, last_tick - start_tick),
        "samples": sample_count,
    })
    return segments


def transition_matrix(segments: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for before, after in zip(segments, segments[1:]):
        if before["class"] != after["class"]:
            matrix[before["class"]][after["class"]] += 1
    return {source: dict(destinations) for source, destinations in matrix.items()}


def feature_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    output = {}
    for column in NUMERIC_COLUMNS:
        key = f"_{column}"
        values = [safe_float(row.get(key), 0.0) for row in rows if key in row]
        if values:
            output[column] = {
                "mean": mean(values),
                "stdev": stdev(values),
                "min": min(values),
                "max": max(values),
            }
    return output


def local_mci(row: dict[str, Any], entropy_hint: float = 0.0) -> float:
    edge = safe_float(row.get("_morphology_edge_complexity"), 0.0)
    branching = safe_float(row.get("_morphology_branching"), 0.0)
    change = safe_float(row.get("_morphology_change_rate"), 0.0)
    filament = safe_float(row.get("_morphology_filament_score"), 0.0)
    lattice = safe_float(row.get("_morphology_lattice_score"), 0.0)
    symmetry = safe_float(row.get("_morphology_symmetry"), 0.0)

    edge_n = min(1.0, edge / 40.0)
    branching_n = min(1.0, branching / 2.0)
    change_n = min(1.0, change / 2.0)
    form_n = max(filament, lattice)

    return max(0.0, min(1.0,
        0.26 * edge_n +
        0.22 * branching_n +
        0.16 * change_n +
        0.12 * form_n +
        0.10 * symmetry +
        0.14 * entropy_hint
    ))


def morphological_complexity_index(
    summary: dict[str, dict[str, float]],
    entropy: float,
    transition_rate: float,
) -> float:
    fake_row = {
        "_morphology_edge_complexity": summary.get("morphology_edge_complexity", {}).get("mean", 0.0),
        "_morphology_branching": summary.get("morphology_branching", {}).get("mean", 0.0),
        "_morphology_change_rate": summary.get("morphology_change_rate", {}).get("mean", 0.0),
        "_morphology_filament_score": summary.get("morphology_filament_score", {}).get("mean", 0.0),
        "_morphology_lattice_score": summary.get("morphology_lattice_score", {}).get("mean", 0.0),
        "_morphology_symmetry": summary.get("morphology_symmetry", {}).get("mean", 0.0),
    }
    base = local_mci(fake_row, entropy)
    transition_n = min(1.0, transition_rate / 250.0)
    return max(0.0, min(1.0, 0.86 * base + 0.14 * transition_n))
