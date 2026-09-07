"""Boundary expansion and completion events derived from telemetry rows."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.morphology.numeric import mean, safe_float, safe_int


def boundary_growth_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required = ("_bbox_min_x", "_bbox_max_x", "_bbox_min_y", "_bbox_max_y")
    if not rows or not all(key in rows[0] for key in required):
        return {"available": False, "events": [], "event_count": 0}

    events = []
    last_completion_tick = None
    sides = ("top", "right", "bottom", "left")
    armed = {
        side: safe_float(rows[0].get(f"_{side}_edge_fill"), 0.0) < 0.90
        or safe_float(rows[0].get(f"_{side}_edge_run"), 0.0) < 0.90
        for side in sides
    }
    for previous, current in zip(rows, rows[1:]):
        tick = current["_tick"]
        changes = {
            "left": previous["_bbox_min_x"] - current["_bbox_min_x"],
            "right": current["_bbox_max_x"] - previous["_bbox_max_x"],
            "top": previous["_bbox_min_y"] - current["_bbox_min_y"],
            "bottom": current["_bbox_max_y"] - previous["_bbox_max_y"],
        }
        for side, amount in changes.items():
            if amount > 0:
                events.append({"tick": tick, "type": "BBOX_EXPANSION", "side": side, "amount": amount})
                armed[side] = True

        for side in sides:
            before_fill = safe_float(previous.get(f"_{side}_edge_fill"), 0.0)
            after_fill = safe_float(current.get(f"_{side}_edge_fill"), 0.0)
            before_run = safe_float(previous.get(f"_{side}_edge_run"), 0.0)
            after_run = safe_float(current.get(f"_{side}_edge_run"), 0.0)
            if after_fill < 0.90 or after_run < 0.90:
                armed[side] = True
            if armed[side] and after_fill >= 0.98 and after_run >= 0.98:
                interval = None if last_completion_tick is None else tick - last_completion_tick
                events.append({
                    "tick": tick, "type": "BOUNDARY_COMPLETION", "side": side,
                    "fill_before": before_fill, "fill_after": after_fill,
                    "run_before": before_run, "run_after": after_run,
                    "interval_since_previous": interval,
                    "bbox_width": safe_int(current.get("_bbox_width"), 0),
                    "bbox_height": safe_int(current.get("_bbox_height"), 0),
                })
                last_completion_tick = tick
                armed[side] = False

    intervals = [event["interval_since_previous"] for event in events if event.get("interval_since_previous") is not None]
    return {
        "available": True,
        "event_count": len(events),
        "bbox_expansion_count": sum(event["type"] == "BBOX_EXPANSION" for event in events),
        "boundary_completion_count": sum(event["type"] == "BOUNDARY_COMPLETION" for event in events),
        "mean_completion_interval": mean(intervals) if intervals else None,
        "events": events[:1000],
    }
