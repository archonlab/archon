"""Compressed macro-event sequences and repeated-cycle detection."""
from __future__ import annotations

from collections import Counter
from typing import Any

from Analyzer_next.core.fusion.numeric import clamp01


def fused_sequence(
    fused: list[dict[str, Any]], max_items: int = 24
) -> list[str]:
    sequence: list[str] = []
    for event in sorted(
        fused, key=lambda item: (item["center_tick"], -item["severity"])
    ):
        event_type = event["fused_event_type"]
        if not sequence or sequence[-1] != event_type:
            sequence.append(event_type)
    if len(sequence) <= max_items:
        return sequence
    step = len(sequence) / max_items
    return [sequence[int(index * step)] for index in range(max_items)]


def detect_cycles(sequence: list[str]) -> dict[str, Any]:
    if len(sequence) < 4:
        return {"has_cycle": False, "cycles": [], "cycle_score": 0.0}
    cycles = []
    for size in range(2, min(6, len(sequence) // 2 + 1)):
        seen: Counter = Counter()
        for index in range(len(sequence) - size + 1):
            pattern = tuple(sequence[index:index + size])
            seen[pattern] += 1
        for pattern, count in seen.items():
            if count >= 2:
                cycles.append({
                    "pattern": list(pattern),
                    "count": count,
                    "length": size,
                })
    cycles = sorted(
        cycles,
        key=lambda cycle: (-cycle["count"], cycle["length"], cycle["pattern"]),
    )
    score = 0.0
    if cycles:
        best = cycles[0]
        score = clamp01(
            (best["count"] - 1) * best["length"] / max(1, len(sequence))
        )
    return {"has_cycle": bool(cycles), "cycles": cycles[:10], "cycle_score": score}

