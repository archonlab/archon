"""Compose pure per-rule fusion analysis."""
from __future__ import annotations

from collections import Counter
from typing import Any

from Analyzer_next.core.fusion.classification import fuse_cluster
from Analyzer_next.core.fusion.clustering import cluster_events
from Analyzer_next.core.fusion.cycles import detect_cycles, fused_sequence


def fuse_rule(rule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw_events = payload.get("events", [])
    clusters = cluster_events(raw_events)
    fused = [
        fuse_cluster(cluster, index + 1)
        for index, cluster in enumerate(clusters)
    ]
    if len(fused) > 4:
        fused = [
            event for event in fused
            if event["confidence"] >= 0.38
            or event["severity"] >= 0.45
            or event["raw_event_count"] >= 2
        ]
    sequence = fused_sequence(fused)
    cycles = detect_cycles(sequence)
    counts = Counter(event["fused_event_type"] for event in fused)
    families = Counter(event["family"] for event in fused)
    constructive = sum(families[key] for key in ("growth", "recovery", "ordering"))
    destructive = sum(families[key] for key in ("collapse", "fragmentation"))
    reorganizational = families.get("reorganization", 0)
    if destructive > constructive and destructive >= reorganizational:
        archetype = "collapse-driven fused arc"
    elif constructive > destructive and constructive >= reorganizational:
        archetype = "constructive fused arc"
    elif (
        reorganizational >= constructive
        and reorganizational >= destructive
        and reorganizational > 0
    ):
        archetype = "reorganization-driven fused arc"
    elif families.get("dormancy", 0) > 0:
        archetype = "dormancy-shaped fused arc"
    else:
        archetype = "mixed fused arc"
    compression_ratio = len(fused) / max(1, len(raw_events))
    summary = {
        "raw_event_count": len(raw_events),
        "fused_event_count": len(fused),
        "compression_ratio": compression_ratio,
        "events_reduced_by": len(raw_events) - len(fused),
        "fused_event_counts": dict(counts),
        "fused_family_counts": dict(families),
        "constructive_fused_events": constructive,
        "destructive_fused_events": destructive,
        "reorganizational_fused_events": reorganizational,
        "fused_archetype": archetype,
        "fused_sequence": sequence,
        "fused_sequence_text": " -> ".join(sequence) if sequence else "NONE",
        "cycles": cycles,
        "mean_fused_severity": (
            sum(event["severity"] for event in fused) / max(1, len(fused))
        ),
        "mean_fused_confidence": (
            sum(event["confidence"] for event in fused) / max(1, len(fused))
        ),
    }
    return {
        "rule_id": rule_id,
        "summary": summary,
        "fused_events": fused,
        "source_event_summary": payload.get("summary", {}),
        "sparklines": payload.get("sparklines", {}),
    }

