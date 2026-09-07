"""Adaptive temporal clustering of raw morphological events."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.fusion.classification import event_importance


def cluster_events(
    events: list[dict[str, Any]], window_ticks: int | None = None
) -> list[list[dict[str, Any]]]:
    if not events:
        return []
    ordered = sorted(
        events,
        key=lambda event: (int(event.get("tick", 0)), -event_importance(event)),
    )
    ticks = [int(event.get("tick", 0)) for event in ordered]
    span = max(1, max(ticks) - min(ticks))
    if window_ticks is None:
        window_ticks = max(4, min(24, int(span * 0.055)))
    clusters: list[list[dict[str, Any]]] = []
    current = [ordered[0]]
    for event in ordered[1:]:
        previous_tick = int(current[-1].get("tick", 0))
        tick = int(event.get("tick", 0))
        current_start = int(current[0].get("tick", 0))
        if (
            tick - previous_tick <= window_ticks
            and tick - current_start <= window_ticks * 2
        ):
            current.append(event)
        else:
            clusters.append(current)
            current = [event]
    clusters.append(current)
    return clusters

