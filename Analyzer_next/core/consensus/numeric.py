"""Small deterministic numeric, text, and clock helpers."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

def sf(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except (TypeError, ValueError):
        return default

def si(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default

def ss(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def mean(values: list[float]) -> float:
    values = [sf(v) for v in values if sf(v) > 0]
    if not values:
        return 0.0
    return sum(values) / len(values)

