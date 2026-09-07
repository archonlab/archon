"""Deterministic numeric helpers used by evolution analysis and reports."""
from __future__ import annotations

import math
from typing import Any, Iterable


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def mean(values: Iterable[float]) -> float:
    items = [value for value in values if value is not None]
    return sum(items) / len(items) if items else 0.0


def stdev(values: Iterable[float]) -> float:
    items = [value for value in values if value is not None]
    if len(items) < 2:
        return 0.0
    average = mean(items)
    return math.sqrt(
        sum((value - average) ** 2 for value in items) / (len(items) - 1)
    )


def slope(values: list[float]) -> float:
    count = len(values)
    if count < 2:
        return 0.0
    midpoint_x = (count - 1) / 2.0
    midpoint_y = mean(values)
    denominator = sum((index - midpoint_x) ** 2 for index in range(count))
    if denominator <= 1e-12:
        return 0.0
    raw = sum(
        (index - midpoint_x) * (values[index] - midpoint_y)
        for index in range(count)
    ) / denominator
    return raw * (count - 1)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def sparkline(values: list[float], width: int = 32) -> str:
    if not values:
        return "." * width
    items = values[:]
    if len(items) > width:
        step = len(items) / width
        items = [
            mean(
                items[
                    int(index * step):
                    max(int((index + 1) * step), int(index * step) + 1)
                ]
            )
            for index in range(width)
        ]
    characters = "._-~=+#@"
    low = min(items)
    high = max(items)
    span = high - low
    output = []
    for value in items:
        normalized = 0.0 if span <= 1e-12 else (value - low) / span
        output.append(
            characters[
                min(
                    len(characters) - 1,
                    int(round(normalized * (len(characters) - 1))),
                )
            ]
        )
    return "".join(output).ljust(width, ".")


def fmt_float(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.000"

