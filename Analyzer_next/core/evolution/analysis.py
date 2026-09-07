"""Pure per-run morphological life-cycle analysis."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from Analyzer_next.core.evolution.classification import (
    classify_stage,
    compress_stages,
)
from Analyzer_next.core.evolution.cycles import detect_cycles, stage_signature
from Analyzer_next.core.evolution.indices import life_cycle_indices
from Analyzer_next.core.evolution.metrics import row_metrics, window_rows
from Analyzer_next.core.evolution.numeric import mean, safe_float, slope, sparkline
from Analyzer_next.core.evolution.rows import infer_rule_id, normalize_rows


def select_archetype(indices: dict[str, float]) -> str:
    if indices["collapse_resistance"] < 0.55:
        return "fragile life cycle"
    if indices["life_cycle_stability"] >= 0.60:
        return "stable life cycle"
    if indices["reconfiguration_frequency"] >= 0.35:
        return "reconfiguring life cycle"
    if indices["growth_persistence"] >= 0.45:
        return "growth-oriented life cycle"
    if indices["evolution_rhythm"] >= 0.25:
        return "rhythmic life cycle"
    return "transitional life cycle"


def analyze_rows(
    path: Path, raw_rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    rows = normalize_rows(raw_rows)
    if not rows:
        return None
    rule_id = infer_rule_id(path, rows)
    radius = max(2, min(12, len(rows) // 20))
    raw_stages = []
    previous_stage = None
    for index, _row in enumerate(rows):
        metrics = row_metrics(window_rows(rows, index, radius))
        stage = classify_stage(metrics, index, len(rows), previous_stage)
        raw_stages.append({
            "index": index,
            "tick": rows[index]["_tick"],
            "stage": stage,
            "metrics": metrics,
        })
        previous_stage = stage
    segments = compress_stages(
        rows,
        raw_stages,
        min_samples=max(2, min(5, len(rows) // 30)),
    )
    signature = stage_signature(segments)
    cycles = detect_cycles(signature)
    indices = life_cycle_indices(segments, rows)
    mci = [safe_float(row.get("_mci"), 0.0) for row in rows]
    mass = [safe_float(row.get("_total_living_mass"), 0.0) for row in rows]
    objects = [safe_float(row.get("_objects"), 0.0) for row in rows]
    change = [safe_float(row.get("_morphology_change_rate"), 0.0) for row in rows]
    pressure = [safe_float(row.get("_evo_pressure"), 0.0) for row in rows]
    dominant_stage = (
        Counter(stage["stage"] for stage in raw_stages).most_common(1)[0][0]
        if raw_stages
        else "QUIET"
    )
    stage_counts = Counter(stage["stage"] for stage in raw_stages)
    return {
        "rule_id": rule_id,
        "source_csv": str(path),
        "first_tick": rows[0]["_tick"],
        "last_tick": rows[-1]["_tick"],
        "observed_ticks": max(1, rows[-1]["_tick"] - rows[0]["_tick"]),
        "samples": len(rows),
        "dominant_stage": dominant_stage,
        "stage_counts": dict(stage_counts),
        "life_cycle_signature": signature,
        "life_cycle_signature_text": " -> ".join(signature) if signature else "NONE",
        "life_cycle_archetype": select_archetype(indices),
        "segments": segments,
        "cycles": cycles,
        "indices": indices,
        "sparklines": {
            "mci": sparkline(mci),
            "mass": sparkline(mass),
            "objects": sparkline(objects),
            "change_rate": sparkline(change),
            "pressure": sparkline(pressure),
        },
        "summary_stats": {
            "mean_mci": mean(mci),
            "mci_slope": slope(mci),
            "mean_mass": mean(mass),
            "mass_slope_norm": slope(mass)
            / max(1.0, max(mass) if mass else 1.0),
            "mean_change_rate": mean(change),
            "mean_pressure": mean(pressure),
        },
    }

