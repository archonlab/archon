"""Classify raw-event clusters as macro-events without external state."""
from __future__ import annotations

from collections import Counter
from typing import Any

from Analyzer_next.core.fusion.constants import EVENT_TO_FUSION, FUSION_TYPES
from Analyzer_next.core.fusion.numeric import clamp01, safe_float


def event_importance(event: dict[str, Any]) -> float:
    return safe_float(
        event.get("importance"), safe_float(event.get("severity"), 0.0)
    )


def score_fusion_type(
    cluster: list[dict[str, Any]], fusion_type: str
) -> float:
    allowed = FUSION_TYPES[fusion_type]["events"]
    total_weight = 0.0
    matched_weight = 0.0
    unique_matched = set()
    for event in cluster:
        importance = event_importance(event)
        total_weight += importance
        if event.get("event_type") in allowed:
            matched_weight += importance
            unique_matched.add(event.get("event_type"))
    if total_weight <= 1e-12:
        return 0.0
    coverage = matched_weight / total_weight
    diversity_bonus = min(0.30, len(unique_matched) * 0.055)
    key_bonus = 0.0
    event_types = {event.get("event_type") for event in cluster}
    if fusion_type == "COLLAPSE_EVENT" and {
        "MASS_COLLAPSE", "COMPLEXITY_DROP"
    } & event_types:
        key_bonus += 0.16
    if fusion_type == "STRUCTURAL_EXPANSION_EVENT" and {
        "COMPLEXITY_SURGE", "BRANCHING_BURST", "EDGE_COMPLEXITY_BURST"
    } & event_types:
        key_bonus += 0.16
    if fusion_type == "REORGANIZATION_EVENT" and {
        "REORGANIZATION", "MORPHOLOGY_CLASS_SHIFT"
    } & event_types:
        key_bonus += 0.18
    if fusion_type == "DORMANCY_TRANSITION" and "DORMANCY_START" in event_types:
        key_bonus += 0.20
    if fusion_type == "REVIVAL_EVENT" and {
        "REVIVAL", "DORMANCY_END"
    } & event_types:
        key_bonus += 0.20
    if fusion_type == "ORDERING_EVENT" and {
        "LATTICE_EMERGENCE", "SYMMETRY_RECOVERY"
    } & event_types:
        key_bonus += 0.14
    if fusion_type == "FRAGMENTATION_EVENT" and {
        "SYMMETRY_BREAK", "LATTICE_FADE", "FILAMENT_FADE"
    } & event_types:
        key_bonus += 0.14
    return clamp01(coverage + diversity_bonus + key_bonus)


def choose_fusion_type(
    cluster: list[dict[str, Any]],
) -> tuple[str, float, dict[str, float]]:
    scores = {
        fusion_type: score_fusion_type(cluster, fusion_type)
        for fusion_type in FUSION_TYPES
    }
    best_type, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < 0.42:
        event_types = Counter(event.get("event_type") for event in cluster)
        if event_types:
            most_common = event_types.most_common(1)[0][0]
            if most_common in EVENT_TO_FUSION:
                best_type = EVENT_TO_FUSION[most_common][0]
                best_score = max(best_score, 0.38)
            else:
                best_type = "MIXED_SIGNAL_EVENT"
                best_score = 0.35
        else:
            best_type = "MIXED_SIGNAL_EVENT"
            best_score = 0.0
    return best_type, best_score, scores


def describe_fused_event(
    fusion_type: str, event_types: Counter, signals: Counter
) -> str:
    common = ", ".join(name for name, _ in event_types.most_common(4))
    signal_text = ", ".join(name for name, _ in signals.most_common(3))
    descriptions = {
        "COLLAPSE_EVENT": "Multiple decay signals fused into one collapse-like transition.",
        "STRUCTURAL_EXPANSION_EVENT": "Growth and structural complexity signals fused into one expansion event.",
        "REORGANIZATION_EVENT": "Class, oscillation, pressure, or high-change signals fused into one reorganization.",
        "DORMANCY_TRANSITION": "Low-change and settling signals fused into a dormancy transition.",
        "REVIVAL_EVENT": "Recovery signals fused into a revival event.",
        "ORDERING_EVENT": "Lattice, symmetry, or stability signals fused into an ordering event.",
        "FRAGMENTATION_EVENT": "Symmetry loss and fading structure signals fused into fragmentation.",
        "MIXED_SIGNAL_EVENT": "Nearby raw events fused into a mixed signal event.",
    }
    base = descriptions.get(
        fusion_type, "Nearby raw events fused into a macro-event."
    )
    return f"{base} Raw signals: {common}. Main channels: {signal_text}."


def fuse_cluster(
    cluster: list[dict[str, Any]], cluster_id: int
) -> dict[str, Any]:
    fusion_type, confidence, scores = choose_fusion_type(cluster)
    ticks = [int(event.get("tick", 0)) for event in cluster]
    importances = [event_importance(event) for event in cluster]
    event_types = Counter(event.get("event_type") for event in cluster)
    signals = Counter(event.get("linked_signal", "unknown") for event in cluster)
    morphologies = Counter(
        event.get("morphology_class", "NONE") for event in cluster
    )
    ordered = sorted(cluster, key=event_importance, reverse=True)
    primary = ordered[0] if ordered else {}
    severity = clamp01(
        0.52 * (max(importances) if importances else 0.0)
        + 0.28 * (sum(importances) / max(1, len(importances)))
        + 0.20 * min(1.0, len(cluster) / 7.0)
    )
    return {
        "fused_event_id": f"FE-{cluster_id:04d}",
        "fused_event_type": fusion_type,
        "family": FUSION_TYPES.get(fusion_type, {}).get("family", "mixed"),
        "start_tick": min(ticks) if ticks else 0,
        "end_tick": max(ticks) if ticks else 0,
        "center_tick": int(round(sum(ticks) / len(ticks))) if ticks else 0,
        "duration_ticks": (max(ticks) - min(ticks)) if ticks else 0,
        "raw_event_count": len(cluster),
        "confidence": confidence,
        "severity": severity,
        "dominant_morphology_class": (
            morphologies.most_common(1)[0][0] if morphologies else "NONE"
        ),
        "primary_raw_event": primary.get("event_type"),
        "primary_signal": primary.get("linked_signal"),
        "raw_event_counts": dict(event_types),
        "signal_counts": dict(signals),
        "fusion_scores": scores,
        "description": describe_fused_event(fusion_type, event_types, signals),
        "raw_events": cluster,
    }

