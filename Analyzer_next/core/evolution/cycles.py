"""Compressed stage signatures and repeated-cycle detection."""
from __future__ import annotations

from collections import Counter
from typing import Any

from Analyzer_next.core.evolution.numeric import clamp01


def stage_signature(
    segments: list[dict[str, Any]], max_items: int = 24
) -> list[str]:
    compact: list[str] = []
    for stage in (segment["stage"] for segment in segments):
        if not compact or compact[-1] != stage:
            compact.append(stage)
    if len(compact) <= max_items:
        return compact
    step = len(compact) / max_items
    return [compact[int(index * step)] for index in range(max_items)]


def detect_cycles(signature: list[str]) -> dict[str, Any]:
    if len(signature) < 4:
        return {
            "has_repeated_cycle": False,
            "cycles": [],
            "cycle_score": 0.0,
        }
    cycles = []
    for size in range(2, min(6, len(signature) // 2 + 1)):
        seen: Counter = Counter()
        for index in range(0, len(signature) - size + 1):
            seen[tuple(signature[index:index + size])] += 1
        for pattern, count in seen.items():
            if count >= 2:
                cycles.append({
                    "pattern": list(pattern),
                    "count": count,
                    "length": size,
                })
    cycles = sorted(
        cycles,
        key=lambda cycle: (
            -cycle["count"], cycle["length"], cycle["pattern"]
        ),
    )
    score = 0.0
    if cycles:
        best = cycles[0]
        score = clamp01(
            (best["count"] - 1) * best["length"] / max(1, len(signature))
        )
    return {
        "has_repeated_cycle": bool(cycles),
        "cycles": cycles[:12],
        "cycle_score": score,
    }

