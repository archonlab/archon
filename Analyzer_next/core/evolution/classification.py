"""Life-stage classification and timeline segment construction."""
from __future__ import annotations

from collections import Counter
from typing import Any

from Analyzer_next.core.evolution.numeric import mean, safe_float


def classify_stage(
    metrics: dict[str, float],
    index: int,
    total: int,
    previous_stage: str | None,
) -> str:
    if not metrics:
        return "QUIET"
    mass = metrics.get("mass", 0.0)
    objects = metrics.get("objects", 0.0)
    change = metrics.get("change_rate", 0.0)
    pressure = metrics.get("pressure", 0.0)
    risk = metrics.get("risk", 0.0)
    stability = metrics.get("stability", 0.0)
    mass_slope = metrics.get("mass_slope", 0.0)
    objects_slope = metrics.get("objects_slope", 0.0)
    mci_slope = metrics.get("mci_slope", 0.0)
    branching_slope = metrics.get("branching_slope", 0.0)
    edge_slope = metrics.get("edge_slope", 0.0)
    change_volatility = metrics.get("change_volatility", 0.0)
    early = index < max(5, int(total * 0.12))
    if mass <= 2 and objects <= 1:
        return "COLLAPSE"
    if (
        previous_stage in ("COLLAPSE", "DECLINE")
        and mass_slope > 0.12
        and objects_slope >= 0.0
    ):
        return "REBIRTH"
    if early and (mass_slope >= 0 or objects_slope >= 0):
        return "BIRTH"
    if risk >= 0.55 or pressure >= 0.60 or mass_slope < -0.20:
        return "DECLINE"
    if mass_slope > 0.10 or objects_slope > 0.10:
        return "EXPANSION"
    if mci_slope > 0.06 or branching_slope > 0.18 or edge_slope > 0.10:
        return "ORGANIZATION"
    if change >= 0.55 or change_volatility >= 0.20:
        if abs(mci_slope) < 0.08 and abs(mass_slope) < 0.12:
            return "OSCILLATION"
        return "RECONFIGURATION"
    if stability >= 0.50 and change < 0.35 and abs(mci_slope) < 0.05:
        return "STABILIZATION"
    if abs(mass_slope) < 0.05 and abs(mci_slope) < 0.04 and change < 0.45:
        return "QUIET"
    return "RECONFIGURATION"


def make_segment(
    rows: list[dict[str, Any]],
    raw: list[dict[str, Any]],
    stage: str,
    start_index: int,
    end_index: int,
) -> dict[str, Any]:
    sub_rows = rows[start_index:end_index + 1]
    start_tick = sub_rows[0]["_tick"]
    end_tick = sub_rows[-1]["_tick"]
    mci = [safe_float(row.get("_mci"), 0.0) for row in sub_rows]
    mass = [safe_float(row.get("_total_living_mass"), 0.0) for row in sub_rows]
    change = [
        safe_float(row.get("_morphology_change_rate"), 0.0) for row in sub_rows
    ]
    classes = Counter(row.get("_class", "NONE") for row in sub_rows)
    return {
        "stage": stage,
        "start_tick": start_tick,
        "end_tick": end_tick,
        "start_index": start_index,
        "end_index": end_index,
        "duration_ticks": max(0, end_tick - start_tick),
        "samples": len(sub_rows),
        "dominant_morphology_class": (
            classes.most_common(1)[0][0] if classes else "NONE"
        ),
        "mean_mci": mean(mci),
        "mean_mass": mean(mass),
        "mean_change_rate": mean(change),
        "absorbed_stages": [],
    }


def compress_stages(
    rows: list[dict[str, Any]],
    raw: list[dict[str, Any]],
    min_samples: int = 3,
) -> list[dict[str, Any]]:
    if not raw:
        return []
    segments = []
    current = raw[0]["stage"]
    start_index = 0
    for index in range(1, len(raw)):
        if raw[index]["stage"] != current:
            segments.append(
                make_segment(rows, raw, current, start_index, index - 1)
            )
            current = raw[index]["stage"]
            start_index = index
    segments.append(
        make_segment(rows, raw, current, start_index, len(raw) - 1)
    )
    if len(segments) <= 1:
        return segments
    merged: list[dict[str, Any]] = []
    for segment in segments:
        if segment["samples"] < min_samples and merged:
            previous = merged[-1]
            previous["end_tick"] = segment["end_tick"]
            previous["end_index"] = segment["end_index"]
            previous["samples"] += segment["samples"]
            previous["duration_ticks"] = max(
                0, previous["end_tick"] - previous["start_tick"]
            )
            previous["absorbed_stages"].append(segment["stage"])
        else:
            merged.append(segment)
    if len(merged) > 1 and merged[0]["samples"] < min_samples:
        first = merged.pop(0)
        merged[0]["start_tick"] = first["start_tick"]
        merged[0]["start_index"] = first["start_index"]
        merged[0]["samples"] += first["samples"]
        merged[0]["duration_ticks"] = max(
            0, merged[0]["end_tick"] - merged[0]["start_tick"]
        )
        merged[0]["absorbed_stages"].insert(0, first["stage"])
    return merged

