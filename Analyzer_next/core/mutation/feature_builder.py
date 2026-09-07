"""Shared-horizon sample alignment and feature summaries."""
from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from .constants import CATEGORICAL_METRICS, NUMERIC_METRICS
from .utils import safe_float, safe_int

def index_rows_by_tick(rows: list[dict[str, str]]) -> dict[int, dict[str, str]]:
    indexed: dict[int, dict[str, str]] = {}
    for row in rows:
        tick = safe_int(row.get("tick"))
        if tick is not None:
            indexed[tick] = row
    return indexed


def nearest_row(
    rows_by_tick: dict[int, dict[str, str]],
    target_tick: int,
) -> dict[str, str] | None:
    if not rows_by_tick:
        return None
    if target_tick in rows_by_tick:
        return rows_by_tick[target_tick]
    tick = min(rows_by_tick, key=lambda value: abs(value - target_tick))
    return rows_by_tick[tick]


def median_tail(
    rows: list[dict[str, str]],
    metric: str,
    fraction: float = 0.20,
) -> float | None:
    if not rows:
        return None
    start = max(0, int(len(rows) * (1.0 - fraction)))
    values = [
        value
        for row in rows[start:]
        if (value := safe_float(row.get(metric))) is not None
    ]
    return statistics.median(values) if values else None


def truncate_rows_to_tick(
    rows: list[dict[str, str]],
    max_tick: int | None,
) -> list[dict[str, str]]:
    """Keep only samples from the shared observation horizon."""
    if max_tick is None:
        return list(rows)
    kept: list[dict[str, str]] = []
    for row in rows:
        tick = safe_int(row.get("tick"))
        if tick is not None and tick <= max_tick:
            kept.append(row)
    return kept


def summarize_samples(rows: list[dict[str, str]]) -> dict[str, Any]:
    if not rows:
        return {
            "row_count": 0,
            "final_tick": None,
            "alive_at_end": None,
            "final": {},
            "tail_median": {},
            "peak": {},
            "categorical_final": {},
        }

    last = rows[-1]
    numeric_final: dict[str, float] = {}
    tail_median: dict[str, float] = {}
    peak: dict[str, float] = {}

    for metric in NUMERIC_METRICS:
        final_value = safe_float(last.get(metric))
        if final_value is not None:
            numeric_final[metric] = round(final_value, 8)

        median_value = median_tail(rows, metric)
        if median_value is not None:
            tail_median[metric] = round(median_value, 8)

        values = [
            value
            for row in rows
            if (value := safe_float(row.get(metric))) is not None
        ]
        if values:
            peak[metric] = round(max(values), 8)

    categorical = {
        metric: last.get(metric)
        for metric in CATEGORICAL_METRICS
        if last.get(metric) not in {None, ""}
    }

    alive_text = str(last.get("alive", "")).strip().lower()
    alive = alive_text in {"true", "1", "yes"}

    return {
        "row_count": len(rows),
        "first_tick": safe_int(rows[0].get("tick")),
        "final_tick": safe_int(last.get("tick")),
        "alive_at_end": alive,
        "final": numeric_final,
        "tail_median": tail_median,
        "peak": peak,
        "categorical_final": categorical,
    }

