"""Score event importance and summarize event biographies."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from Analyzer_next.core.events.numeric import clamp01, mean


def event_importance(event: dict[str, Any]) -> float:
    type_weight = {
        "MASS_EXPLOSION": 0.95,
        "MASS_COLLAPSE": 0.95,
        "COMPLEXITY_SURGE": 0.88,
        "COMPLEXITY_DROP": 0.86,
        "BRANCHING_BURST": 0.82,
        "EDGE_COMPLEXITY_BURST": 0.82,
        "REORGANIZATION": 0.90,
        "REVIVAL": 0.90,
        "OSCILLATION_START": 0.76,
        "OSCILLATION_END": 0.65,
        "DORMANCY_START": 0.70,
        "DORMANCY_END": 0.65,
        "MORPHOLOGY_CLASS_SHIFT": 0.80,
        "BBOX_EXPANSION": 0.92,
        "BOUNDARY_COMPLETION": 0.98,
        "PRESSURE_SPIKE": 0.72,
        "RISK_SPIKE": 0.74,
        "STABILITY_GAIN": 0.70,
        "STABILITY_LOSS": 0.72,
    }.get(event["event_type"], 0.60)
    return clamp01(0.65 * event.get("severity", 0.0) + 0.35 * type_weight)


def event_sequence(
    events: list[dict[str, Any]], max_items: int = 24
) -> list[str]:
    important = sorted(events, key=lambda event: (event["tick"], -event_importance(event)))
    sequence: list[str] = []
    for event in important:
        if event_importance(event) < 0.38:
            continue
        event_type = event["event_type"]
        if not sequence or sequence[-1] != event_type:
            sequence.append(event_type)
    if len(sequence) <= max_items:
        return sequence
    step = len(sequence) / max_items
    return [sequence[int(index * step)] for index in range(max_items)]


def detect_event_cycles(sequence: list[str]) -> dict[str, Any]:
    if len(sequence) < 4:
        return {"has_cycle": False, "cycles": [], "cycle_score": 0.0}
    cycles = []
    for size in range(2, min(6, len(sequence) // 2 + 1)):
        seen: Counter = Counter()
        for index in range(len(sequence) - size + 1):
            pattern = tuple(sequence[index:index + size])
            seen[pattern] += 1
        for pattern, count in seen.items():
            if count >= 2:
                cycles.append({
                    "pattern": list(pattern),
                    "count": count,
                    "length": size,
                })
    cycles = sorted(
        cycles,
        key=lambda cycle: (-cycle["count"], cycle["length"], cycle["pattern"]),
    )
    score = 0.0
    if cycles:
        best = cycles[0]
        score = clamp01(
            (best["count"] - 1) * best["length"] / max(1, len(sequence))
        )
    return {"has_cycle": bool(cycles), "cycles": cycles[:10], "cycle_score": score}


def normalized_entropy(counts: Counter) -> float:
    total = sum(counts.values())
    if total <= 0 or len(counts) <= 1:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)
    return entropy / math.log2(len(counts))


def event_family(event_type: str) -> str:
    if event_type in {
        "MASS_EXPLOSION",
        "OBJECT_BURST",
        "BRANCHING_BURST",
        "EDGE_COMPLEXITY_BURST",
        "COMPLEXITY_SURGE",
        "FILAMENT_EMERGENCE",
        "LATTICE_EMERGENCE",
    }:
        return "growth"
    if event_type in {
        "MASS_COLLAPSE",
        "OBJECT_DIEBACK",
        "COMPLEXITY_DROP",
        "FILAMENT_FADE",
        "LATTICE_FADE",
        "SYMMETRY_BREAK",
        "RISK_SPIKE",
        "STABILITY_LOSS",
    }:
        return "decay"
    if event_type in {
        "REORGANIZATION",
        "OSCILLATION_START",
        "OSCILLATION_END",
        "MORPHOLOGY_CLASS_SHIFT",
    }:
        return "reconfiguration"
    if event_type in {"DORMANCY_START", "DORMANCY_END"}:
        return "dormancy"
    if event_type in {"REVIVAL", "STABILITY_GAIN", "SYMMETRY_RECOVERY"}:
        return "recovery"
    if event_type == "PRESSURE_SPIKE":
        return "pressure"
    return "other"


def summarize_events(
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    sequence: list[str],
) -> dict[str, Any]:
    counts = Counter(event["event_type"] for event in events)
    family_counts = Counter(event_family(event["event_type"]) for event in events)
    high = [event for event in events if event_importance(event) >= 0.65]
    severe = sorted(events, key=event_importance, reverse=True)[:10]
    ticks = max(1, rows[-1]["_tick"] - rows[0]["_tick"]) if rows else 1
    rate_per_1k = len(events) / ticks * 1000.0
    constructive = sum(counts[event_type] for event_type in (
        "MASS_EXPLOSION",
        "OBJECT_BURST",
        "BRANCHING_BURST",
        "EDGE_COMPLEXITY_BURST",
        "COMPLEXITY_SURGE",
        "FILAMENT_EMERGENCE",
        "LATTICE_EMERGENCE",
        "REVIVAL",
        "STABILITY_GAIN",
        "SYMMETRY_RECOVERY",
    ))
    destructive = sum(counts[event_type] for event_type in (
        "MASS_COLLAPSE",
        "OBJECT_DIEBACK",
        "COMPLEXITY_DROP",
        "FILAMENT_FADE",
        "LATTICE_FADE",
        "SYMMETRY_BREAK",
        "RISK_SPIKE",
        "STABILITY_LOSS",
    ))
    reorganization = sum(counts[event_type] for event_type in (
        "REORGANIZATION",
        "OSCILLATION_START",
        "OSCILLATION_END",
        "MORPHOLOGY_CLASS_SHIFT",
    ))
    if destructive > constructive and destructive >= reorganization:
        archetype = "disruptive event arc"
    elif constructive > destructive and constructive >= reorganization:
        archetype = "constructive event arc"
    elif reorganization >= constructive and reorganization >= destructive and reorganization > 0:
        archetype = "reorganizational event arc"
    elif len(events) == 0:
        archetype = "quiet event arc"
    else:
        archetype = "mixed event arc"
    return {
        "event_counts": dict(counts),
        "event_family_counts": dict(family_counts),
        "total_events": len(events),
        "high_importance_events": len(high),
        "event_rate_per_1k_ticks": rate_per_1k,
        "constructive_events": constructive,
        "destructive_events": destructive,
        "reorganization_events": reorganization,
        "event_archetype": archetype,
        "top_events": severe,
        "event_sequence": sequence,
        "event_sequence_text": " -> ".join(sequence) if sequence else "NONE",
        "cycles": detect_event_cycles(sequence),
        "event_intensity": clamp01(
            mean([event_importance(event) for event in events]) if events else 0.0
        ),
        "event_diversity": normalized_entropy(counts),
    }

