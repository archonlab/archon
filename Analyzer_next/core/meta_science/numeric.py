"""Tolerant numeric and status helpers preserved from Meta Science v34.2."""
from __future__ import annotations

import math
from typing import Any


def sf(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
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


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def mean(values: list[float]) -> float:
    valid = [sf(value) for value in values if sf(value) > 0]
    return sum(valid) / len(valid) if valid else 0.0


def status_bucket(status: str) -> str:
    normalized = status.upper().strip()
    allowed = {
        "FOUNDATIONAL", "CONSENSUS", "STRONG", "SUPPORTED",
        "PROMISING", "OBSERVATION", "DISPUTED", "NO_SIGNAL",
    }
    return normalized if normalized in allowed else "NO_SIGNAL"


def maturity_level(status: str) -> int:
    order = {
        "NO_SIGNAL": 0,
        "DISPUTED": 0,
        "OBSERVATION": 1,
        "PROMISING": 2,
        "SUPPORTED": 3,
        "STRONG": 4,
        "CONSENSUS": 5,
        "FOUNDATIONAL": 6,
    }
    return order.get(status_bucket(status), 0)
