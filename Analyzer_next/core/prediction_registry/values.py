"""Value normalization shared by prediction generation and reporting."""
from __future__ import annotations

from datetime import datetime
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def stars(score: int) -> str:
    score = max(1, min(5, int(score)))
    return "★" * score + "☆" * (5 - score)


def normalize_status(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "confirmed": "Confirmed",
        "passed": "Confirmed",
        "supported": "Confirmed",
        "rejected": "Rejected",
        "failed": "Rejected",
        "falsified": "Rejected",
        "inconclusive": "Inconclusive",
        "unclear": "Inconclusive",
        "testing": "Testing",
        "in_progress": "Testing",
        "open": "Open",
        "planned": "Open",
    }
    return aliases.get(raw, str(value or "Open").strip() or "Open")


def confidence_value(label: Any) -> float:
    raw = str(label or "").upper().replace("_", "-")
    return {
        "NONE": 0.10,
        "LOW": 0.30,
        "LOW-MEDIUM": 0.45,
        "MEDIUM": 0.60,
        "MEDIUM-HIGH": 0.72,
        "HIGH": 0.82,
        "VERY-HIGH": 0.93,
        "VERY_HIGH": 0.93,
    }.get(raw, 0.50)


def confidence_label(value: float) -> str:
    value = max(0.0, min(1.0, float(value)))
    if value >= 0.90:
        return "VERY_HIGH"
    if value >= 0.78:
        return "HIGH"
    if value >= 0.66:
        return "MEDIUM-HIGH"
    if value >= 0.52:
        return "MEDIUM"
    if value >= 0.38:
        return "LOW-MEDIUM"
    if value > 0.15:
        return "LOW"
    return "NONE"


__all__ = [
    "confidence_label",
    "confidence_value",
    "normalize_status",
    "now_iso",
    "stars",
]
