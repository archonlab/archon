"""Compose pure per-run morphology event analysis."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from Analyzer_next.core.events.detection import (
    detect_boundary_events,
    detect_class_shift_events,
    detect_state_events,
    detect_threshold_crossings,
    merge_nearby_events,
)
from Analyzer_next.core.events.numeric import sparkline
from Analyzer_next.core.events.rows import infer_rule_id, normalize_rows
from Analyzer_next.core.events.signals import build_series
from Analyzer_next.core.events.summary import (
    event_importance,
    event_sequence,
    summarize_events,
)


def analyze_rows(
    path: Path, raw_rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    rows = normalize_rows(raw_rows)
    if not rows:
        return None
    rule_id = infer_rule_id(path, rows)
    series = build_series(rows)
    events: list[dict[str, Any]] = []
    events.extend(detect_threshold_crossings(rows, series))
    events.extend(detect_state_events(rows, series))
    events.extend(detect_class_shift_events(rows))
    events.extend(detect_boundary_events(rows))
    min_gap = max(2, min(8, len(rows) // 40))
    events = merge_nearby_events(events, min_gap=min_gap)
    for event in events:
        event["importance"] = event_importance(event)
    events = sorted(events, key=lambda event: (event["tick"], -event["importance"]))
    sequence = event_sequence(events)
    summary = summarize_events(rows, events, sequence)
    return {
        "rule_id": rule_id,
        "source_csv": str(path),
        "first_tick": rows[0]["_tick"],
        "last_tick": rows[-1]["_tick"],
        "observed_ticks": max(1, rows[-1]["_tick"] - rows[0]["_tick"]),
        "samples": len(rows),
        "event_summary": summary,
        "events": events,
        "sparklines": {
            "mci": sparkline(series["mci"]),
            "mass": sparkline(series["mass"]),
            "objects": sparkline(series["objects"]),
            "branching": sparkline(series["branching"]),
            "edge": sparkline(series["edge"]),
            "filament": sparkline(series["filament"]),
            "lattice": sparkline(series["lattice"]),
            "change_rate": sparkline(series["change"]),
            "pressure": sparkline(series["pressure"]),
            "risk": sparkline(series["risk"]),
            "stability": sparkline(series["stability"]),
        },
    }
