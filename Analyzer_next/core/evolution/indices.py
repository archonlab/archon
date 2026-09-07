"""Derived life-cycle indices for an observed morphology timeline."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from Analyzer_next.core.evolution.constants import STAGES
from Analyzer_next.core.evolution.cycles import detect_cycles, stage_signature
from Analyzer_next.core.evolution.numeric import clamp01, mean, safe_float, slope, stdev


def life_cycle_indices(
    segments: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> dict[str, float]:
    signature = stage_signature(segments)
    counts = Counter(signature)
    total = max(1, len(signature))
    diversity = 0.0
    if counts:
        entropy = 0.0
        for count in counts.values():
            probability = count / total
            entropy -= probability * math.log2(probability)
        diversity = (
            entropy / math.log2(max(1, len(STAGES))) if len(STAGES) > 1 else 0.0
        )
    transitions = max(0, len(signature) - 1)
    reconfiguration = counts.get("RECONFIGURATION", 0) + counts.get("OSCILLATION", 0)
    collapse = counts.get("COLLAPSE", 0) + counts.get("DECLINE", 0)
    recovery = counts.get("REBIRTH", 0)
    stable = counts.get("STABILIZATION", 0) + counts.get("QUIET", 0)
    growth = counts.get("EXPANSION", 0) + counts.get("ORGANIZATION", 0)
    mci = [safe_float(row.get("_mci"), 0.0) for row in rows]
    mass = [safe_float(row.get("_total_living_mass"), 0.0) for row in rows]
    change = [safe_float(row.get("_morphology_change_rate"), 0.0) for row in rows]
    cycle = detect_cycles(signature)
    collapse_resistance = 1.0 - clamp01(collapse / total)
    recovery_ability = clamp01(recovery / max(1, collapse))
    rhythm = cycle.get("cycle_score", 0.0)
    complexity = clamp01(
        0.45 * diversity
        + 0.25 * min(1.0, transitions / 10.0)
        + 0.30 * stdev(mci)
    )
    stability = clamp01(
        0.55 * (stable / total)
        + 0.45 * (1.0 - min(1.0, mean(change) / 1.2))
    )
    growth_persistence = clamp01(
        growth / total
        + max(0.0, slope(mass) / max(1.0, max(mass) if mass else 1.0))
    )
    return {
        "life_cycle_diversity": diversity,
        "life_cycle_complexity": complexity,
        "life_cycle_stability": stability,
        "reconfiguration_frequency": reconfiguration / total,
        "collapse_resistance": collapse_resistance,
        "recovery_ability": recovery_ability,
        "growth_persistence": growth_persistence,
        "evolution_rhythm": rhythm,
        "stage_transition_count": transitions,
    }

