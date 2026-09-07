"""Small deterministic numeric helpers used across morphology stages."""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from typing import Any


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
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
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def stdev(values: Iterable[float]) -> float:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return 0.0
    average = mean(vals)
    return math.sqrt(sum((v - average) ** 2 for v in vals) / (len(vals) - 1))


def pearson(xs: list[float], ys: list[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    xs = xs[:n]
    ys = ys[:n]
    mx = mean(xs)
    my = mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx <= 1e-12 or sy <= 1e-12:
        return 0.0
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (sx * sy)


def slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = (n - 1) / 2.0
    my = mean(values)
    denominator = sum((x - mx) ** 2 for x in xs)
    if denominator <= 1e-12:
        return 0.0
    raw = sum((xs[i] - mx) * (values[i] - my) for i in range(n)) / denominator
    return raw * (n - 1)


def oscillation_score(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    signs = []
    for delta in diffs:
        if abs(delta) < 1e-9:
            continue
        signs.append(1 if delta > 0 else -1)
    if len(signs) < 3:
        return 0.0
    flips = sum(1 for a, b in zip(signs, signs[1:]) if a != b)
    return flips / max(1, len(signs) - 1)


def entropy_from_counts(counts: Counter) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        if count <= 0:
            continue
        probability = count / total
        entropy -= probability * math.log2(probability)
    maximum = math.log2(max(1, len(counts)))
    return entropy / maximum if maximum > 0 else 0.0


def sparkline(values: list[float], width: int = 24) -> str:
    if not values:
        return "." * width
    vals = values[:]
    if len(vals) > width:
        step = len(vals) / width
        vals = [
            mean(vals[int(i * step): max(int((i + 1) * step), int(i * step) + 1)])
            for i in range(width)
        ]
    chars = "._-~=+#@"
    low = min(vals)
    high = max(vals)
    span = high - low
    out = []
    for value in vals:
        normalized = 0.0 if span <= 1e-12 else (value - low) / span
        out.append(chars[min(len(chars) - 1, int(round(normalized * (len(chars) - 1))))])
    return "".join(out).ljust(width, ".")


def fmt_float(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.000"
