"""Detect and merge local morphology events from prepared signals."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.events.numeric import clamp01, mean, safe_float, stdev
from Analyzer_next.core.events.signals import robust_threshold


def add_event(
    events: list[dict[str, Any]],
    event_type: str,
    row: dict[str, Any],
    index: int,
    severity: float,
    evidence: dict[str, Any],
    description: str,
    linked_signal: str,
) -> None:
    events.append({
        "event_type": event_type,
        "tick": row["_tick"],
        "index": index,
        "severity": clamp01(severity),
        "morphology_class": row.get("_class", "NONE"),
        "linked_signal": linked_signal,
        "evidence": evidence,
        "description": description,
    })


def detect_threshold_crossings(
    rows: list[dict[str, Any]], series: dict[str, list[float]]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    count = len(rows)
    if count < 4:
        return events
    mapping = (
        ("mass_d", "MASS_EXPLOSION", "MASS_COLLAPSE", "mass", 0.13),
        ("objects_d", "OBJECT_BURST", "OBJECT_DIEBACK", "objects", 0.14),
        ("mci_d", "COMPLEXITY_SURGE", "COMPLEXITY_DROP", "mci", 0.12),
        ("branching_d", "BRANCHING_BURST", None, "branching", 0.14),
        ("edge_d", "EDGE_COMPLEXITY_BURST", None, "edge", 0.14),
        ("filament_d", "FILAMENT_EMERGENCE", "FILAMENT_FADE", "filament", 0.13),
        ("lattice_d", "LATTICE_EMERGENCE", "LATTICE_FADE", "lattice", 0.13),
        ("symmetry_d", "SYMMETRY_RECOVERY", "SYMMETRY_BREAK", "symmetry", 0.12),
        ("pressure_d", "PRESSURE_SPIKE", None, "pressure", 0.12),
        ("risk_d", "RISK_SPIKE", None, "risk", 0.12),
        ("stability_d", "STABILITY_GAIN", "STABILITY_LOSS", "stability", 0.12),
    )
    for delta_key, positive, negative, signal, minimum in mapping:
        values = series.get(delta_key, [])
        if not values:
            continue
        threshold = robust_threshold(values, min_threshold=minimum, scale=1.5)
        for index, value in enumerate(values):
            if index == 0:
                continue
            if value >= threshold and positive:
                add_event(
                    events,
                    positive,
                    rows[index],
                    index,
                    min(1.0, abs(value) / max(threshold, 1e-9) / 2.0),
                    {
                        "delta": value,
                        "threshold": threshold,
                        "value": series.get(signal, [0.0] * count)[index],
                        "normalized": series.get(f"{signal}_n", [0.0] * count)[index],
                    },
                    f"{signal} rose sharply.",
                    signal,
                )
            elif value <= -threshold and negative:
                add_event(
                    events,
                    negative,
                    rows[index],
                    index,
                    min(1.0, abs(value) / max(threshold, 1e-9) / 2.0),
                    {
                        "delta": value,
                        "threshold": threshold,
                        "value": series.get(signal, [0.0] * count)[index],
                        "normalized": series.get(f"{signal}_n", [0.0] * count)[index],
                    },
                    f"{signal} dropped sharply.",
                    signal,
                )
    return events


def detect_state_events(
    rows: list[dict[str, Any]], series: dict[str, list[float]]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    count = len(rows)
    if count < 5:
        return events
    change = series.get("change_n", [0.0] * count)
    complexity = series.get("mci_n", [0.0] * count)
    mass = series.get("mass_n", [0.0] * count)
    stability = series.get("stability_n", [0.0] * count)
    pressure = series.get("pressure_n", [0.0] * count)
    dormancy = [change[i] < 0.22 and complexity[i] < 0.35 for i in range(count)]
    oscillation = []
    for index in range(count):
        start = max(0, index - 3)
        end = min(count, index + 4)
        oscillation.append(
            stdev(complexity[start:end]) > 0.15
            and mean(change[start:end]) > 0.28
        )
    reorganization = [
        change[i] > 0.65 or (pressure[i] > 0.65 and complexity[i] > 0.45)
        for i in range(count)
    ]
    revival = [
        mass[i] > 0.35
        and change[i] > 0.35
        and (i > 0 and mass[i - 1] < 0.25)
        for i in range(count)
    ]
    specifications = (
        (
            "DORMANCY",
            dormancy,
            "DORMANCY_START",
            "DORMANCY_END",
            "low change and low complexity",
        ),
        (
            "OSCILLATION",
            oscillation,
            "OSCILLATION_START",
            "OSCILLATION_END",
            "local morphology oscillation detected",
        ),
        (
            "REORGANIZATION",
            reorganization,
            "REORGANIZATION",
            None,
            "high change or pressure-driven reconfiguration",
        ),
        (
            "REVIVAL",
            revival,
            "REVIVAL",
            None,
            "mass returned after a low-mass period",
        ),
    )
    for state, flags, start_event, end_event, description in specifications:
        in_state = False
        start_index = None
        for index, flag in enumerate(flags):
            if flag and not in_state:
                in_state = True
                start_index = index
                add_event(
                    events,
                    start_event,
                    rows[index],
                    index,
                    0.65,
                    {
                        "mci_n": complexity[index],
                        "change_n": change[index],
                        "mass_n": mass[index],
                        "stability_n": stability[index],
                        "pressure_n": pressure[index],
                    },
                    f"{description} started.",
                    state.lower(),
                )
            elif not flag and in_state:
                in_state = False
                if (
                    end_event
                    and start_index is not None
                    and index - start_index >= 3
                ):
                    add_event(
                        events,
                        end_event,
                        rows[index],
                        index,
                        0.55,
                        {
                            "duration_samples": index - start_index,
                            "mci_n": complexity[index],
                            "change_n": change[index],
                            "mass_n": mass[index],
                        },
                        f"{description} ended.",
                        state.lower(),
                    )
                start_index = None
    return events


def detect_class_shift_events(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index in range(1, len(rows)):
        previous = rows[index - 1].get("_class", "NONE")
        current = rows[index].get("_class", "NONE")
        if current != previous:
            add_event(
                events,
                "MORPHOLOGY_CLASS_SHIFT",
                rows[index],
                index,
                0.55,
                {"from": previous, "to": current},
                f"Morphology class shifted from {previous} to {current}.",
                "morphology_class",
            )
    return events


def detect_boundary_events(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    required = ("_bbox_min_x", "_bbox_max_x", "_bbox_min_y", "_bbox_max_y")
    if not rows or not all(key in rows[0] for key in required):
        return []
    events: list[dict[str, Any]] = []
    last_completion_tick = None
    sides = ("top", "right", "bottom", "left")
    armed = {
        side: safe_float(rows[0].get(f"_{side}_edge_fill"), 0.0) < 0.90
        or safe_float(rows[0].get(f"_{side}_edge_run"), 0.0) < 0.90
        for side in sides
    }
    for index, (previous, current) in enumerate(zip(rows, rows[1:]), start=1):
        changes = {
            "left": previous["_bbox_min_x"] - current["_bbox_min_x"],
            "right": current["_bbox_max_x"] - previous["_bbox_max_x"],
            "top": previous["_bbox_min_y"] - current["_bbox_min_y"],
            "bottom": current["_bbox_max_y"] - previous["_bbox_max_y"],
        }
        for side, amount in changes.items():
            if amount > 0:
                armed[side] = True
                add_event(
                    events,
                    "BBOX_EXPANSION",
                    current,
                    index,
                    min(1.0, 0.55 + 0.15 * amount),
                    {
                        "amount": float(amount),
                        "bbox_width": current.get("_bbox_width", 0.0),
                        "bbox_height": current.get("_bbox_height", 0.0),
                    },
                    f"Occupied domain expanded {amount} cell(s) toward {side}.",
                    f"{side}_boundary",
                )
        for side in sides:
            before_fill = safe_float(previous.get(f"_{side}_edge_fill"), 0.0)
            after_fill = safe_float(current.get(f"_{side}_edge_fill"), 0.0)
            before_run = safe_float(previous.get(f"_{side}_edge_run"), 0.0)
            after_run = safe_float(current.get(f"_{side}_edge_run"), 0.0)
            if after_fill < 0.90 or after_run < 0.90:
                armed[side] = True
            if armed[side] and after_fill >= 0.98 and after_run >= 0.98:
                interval = (
                    0
                    if last_completion_tick is None
                    else current["_tick"] - last_completion_tick
                )
                add_event(
                    events,
                    "BOUNDARY_COMPLETION",
                    current,
                    index,
                    0.92,
                    {
                        "fill_before": before_fill,
                        "fill_after": after_fill,
                        "run_before": before_run,
                        "run_after": after_run,
                        "interval_ticks": float(interval),
                    },
                    f"{side.capitalize()} boundary line reached complete coverage.",
                    f"{side}_boundary",
                )
                last_completion_tick = current["_tick"]
                armed[side] = False
    return events


def merge_nearby_events(
    events: list[dict[str, Any]], min_gap: int = 3
) -> list[dict[str, Any]]:
    if not events:
        return []
    ordered = sorted(
        events,
        key=lambda event: (
            event["tick"],
            event["event_type"],
            -event["severity"],
        ),
    )
    merged: list[dict[str, Any]] = []
    for event in ordered:
        if (
            merged
            and merged[-1]["event_type"] == event["event_type"]
            and abs(merged[-1]["index"] - event["index"]) <= min_gap
        ):
            previous = merged[-1]
            if event["severity"] > previous["severity"]:
                event["merged_count"] = previous.get("merged_count", 1) + 1
                merged[-1] = event
            else:
                previous["merged_count"] = previous.get("merged_count", 1) + 1
        else:
            event["merged_count"] = 1
            merged.append(event)
    return merged
