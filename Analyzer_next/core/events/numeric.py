"""Deterministic numeric helpers for morphological event detection."""
from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any


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


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    middle = len(items) // 2
    if len(items) % 2:
        return items[middle]
    return (items[middle - 1] + items[middle]) / 2.0


def mad(values: list[float]) -> float:
    if not values:
        return 0.0
    middle = median(values)
    return median([abs(value - middle) for value in values])


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def moving_average(values: list[float], radius: int) -> list[float]:
    if not values:
        return []
    prefix = [0.0]
    total = 0.0
    for value in values:
        total += value
        prefix.append(total)
    count = len(values)
    output = [0.0] * count
    for index in range(count):
        start = max(0, index - radius)
        end = min(count, index + radius + 1)
        output[index] = (prefix[end] - prefix[start]) / max(1, end - start)
    return output


def normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    span = high - low
    if span <= 1e-12:
        return [0.0 for _ in values]
    return [(value - low) / span for value in values]


def diff(values: list[float]) -> list[float]:
    if not values:
        return []
    output = [0.0]
    for before, after in zip(values, values[1:]):
        output.append(after - before)
    return output


def sparkline(values: list[float], width: int = 36) -> str:
    if not values:
        return "." * width
    items = values[:]
    if len(items) > width:
        step = len(items) / width
        items = [
            mean(items[int(i * step):max(int((i + 1) * step), int(i * step) + 1)])
            for i in range(width)
        ]
    chars = "._-~=+#@"
    low = min(items)
    high = max(items)
    span = high - low
    output = []
    for value in items:
        scaled = 0.0 if span <= 1e-12 else (value - low) / span
        output.append(
            chars[min(len(chars) - 1, int(round(scaled * (len(chars) - 1))))]
        )
    return "".join(output).ljust(width, ".")


def fmt_float(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.000"

