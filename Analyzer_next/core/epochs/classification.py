"""Epoch classification, biographies, cycles, and derived indices."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from Analyzer_next.core.epochs.constants import EPOCH_TYPES
from Analyzer_next.core.epochs.numeric import clamp01, mean, slope, sparkline, stdev


def classify_epoch(
    signal_rows: list[dict[str, Any]],
    start: int,
    end: int,
    epoch_index: int,
    epoch_count: int,
    previous_type: str | None,
) -> str:
    del epoch_count
    chunk = signal_rows[start:end + 1]
    if not chunk:
        return "TRANSITION_EPOCH"

    def values(key: str) -> list[float]:
        return [row["norm"][key] for row in chunk]

    mass = values("mass")
    objects = values("objects")
    mci = values("mci")
    branching = values("branching")
    edge = values("edge")
    change = values("change")
    pressure = values("pressure")
    risk = values("risk")
    stability = values("stability")
    mass_slope = slope(mass)
    object_slope = slope(objects)
    mci_slope = slope(mci)
    branching_slope = slope(branching)
    edge_slope = slope(edge)
    change_mean = mean(change)
    risk_mean = mean(risk)
    pressure_mean = mean(pressure)
    stability_mean = mean(stability)
    mci_volatility = stdev(mci)
    change_volatility = stdev(change)
    early = epoch_index == 0
    low_mass = mean(mass) < 0.10 and mean(objects) < 0.10
    if low_mass and risk_mean > 0.45:
        return "COLLAPSE_EPOCH"
    if previous_type in ("COLLAPSE_EPOCH", "DECAY_EPOCH") and (
        mass_slope > 0.15 or object_slope > 0.15
    ):
        return "RECOVERY_EPOCH"
    if early:
        return "FORMATION"
    if mass_slope > 0.18 or object_slope > 0.18:
        return "RAPID_EXPANSION"
    if mci_slope > 0.12 or branching_slope > 0.14 or edge_slope > 0.12:
        return "STRUCTURAL_ORGANIZATION"
    if risk_mean > 0.60 or mass_slope < -0.18 or object_slope < -0.18:
        return "DECAY_EPOCH"
    if change_mean > 0.50 or pressure_mean > 0.55:
        return "RECONFIGURATION_EPOCH"
    if (
        (mci_volatility > 0.16 or change_volatility > 0.16)
        and abs(mass_slope) < 0.18
    ):
        return "STABLE_OSCILLATION"
    if stability_mean > 0.45 or (
        abs(mass_slope) < 0.08
        and abs(mci_slope) < 0.08
        and change_mean < 0.45
    ):
        return "QUIET_PLATEAU"
    return "TRANSITION_EPOCH"


def make_epoch(
    rows: list[dict[str, Any]],
    signal_rows: list[dict[str, Any]],
    start: int,
    end: int,
    epoch_type: str,
) -> dict[str, Any]:
    del rows
    chunk = signal_rows[start:end + 1]
    ticks = [row["tick"] for row in chunk]
    classes = Counter(row["morphology_class"] for row in chunk)

    def signal_values(key: str) -> list[float]:
        return [row["signals"][key] for row in chunk]

    def normalized_values(key: str) -> list[float]:
        return [row["norm"][key] for row in chunk]

    mci = signal_values("mci")
    mass = signal_values("mass")
    objects = signal_values("objects")
    change = signal_values("change")
    pressure = signal_values("pressure")
    risk = signal_values("risk")
    stability = signal_values("stability")
    branching = signal_values("branching")
    edge = signal_values("edge")
    return {
        "epoch_type": epoch_type,
        "start_tick": ticks[0],
        "end_tick": ticks[-1],
        "start_index": start,
        "end_index": end,
        "duration_ticks": max(0, ticks[-1] - ticks[0]),
        "samples": len(chunk),
        "dominant_morphology_class": classes.most_common(1)[0][0] if classes else "NONE",
        "mean": {
            "mci": mean(mci),
            "mass": mean(mass),
            "objects": mean(objects),
            "change_rate": mean(change),
            "pressure": mean(pressure),
            "risk": mean(risk),
            "stability": mean(stability),
            "branching": mean(branching),
            "edge": mean(edge),
        },
        "slopes": {
            "mci": slope(normalized_values("mci")),
            "mass": slope(normalized_values("mass")),
            "objects": slope(normalized_values("objects")),
            "change": slope(normalized_values("change")),
            "pressure": slope(normalized_values("pressure")),
            "risk": slope(normalized_values("risk")),
            "stability": slope(normalized_values("stability")),
            "branching": slope(normalized_values("branching")),
            "edge": slope(normalized_values("edge")),
        },
        "sparklines": {
            "mci": sparkline(mci, width=18),
            "mass": sparkline(mass, width=18),
            "change_rate": sparkline(change, width=18),
        },
    }


def merge_same_type_epochs(
    epochs: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    signal_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not epochs:
        return []
    merged = []
    for epoch in epochs:
        if merged and merged[-1]["epoch_type"] == epoch["epoch_type"]:
            start = merged[-1]["start_index"]
            end = epoch["end_index"]
            merged[-1] = make_epoch(rows, signal_rows, start, end, epoch["epoch_type"])
        else:
            merged.append(epoch)
    return merged


def epoch_signature(epochs: list[dict[str, Any]]) -> list[str]:
    signature = []
    for epoch in epochs:
        epoch_type = epoch["epoch_type"]
        if not signature or signature[-1] != epoch_type:
            signature.append(epoch_type)
    return signature


def detect_epoch_cycles(signature: list[str]) -> dict[str, Any]:
    if len(signature) < 4:
        return {"has_cycle": False, "cycles": [], "cycle_score": 0.0}
    cycles = []
    for size in range(2, min(5, len(signature) // 2 + 1)):
        seen = Counter()
        for index in range(len(signature) - size + 1):
            seen[tuple(signature[index:index + size])] += 1
        for pattern, count in seen.items():
            if count >= 2:
                cycles.append({"pattern": list(pattern), "count": count, "length": size})
    cycles = sorted(
        cycles,
        key=lambda cycle: (-cycle["count"], cycle["length"], cycle["pattern"]),
    )
    score = 0.0
    if cycles:
        best = cycles[0]
        score = clamp01(
            (best["count"] - 1) * best["length"] / max(1, len(signature))
        )
    return {"has_cycle": bool(cycles), "cycles": cycles[:10], "cycle_score": score}


def epoch_indices(epochs: list[dict[str, Any]]) -> dict[str, float]:
    signature = epoch_signature(epochs)
    counts = Counter(signature)
    total = max(1, len(signature))
    diversity = 0.0
    if counts:
        entropy = 0.0
        for count in counts.values():
            probability = count / total
            entropy -= probability * math.log2(probability)
        diversity = entropy / math.log2(max(2, len(EPOCH_TYPES)))
    reconfiguration = counts.get("RECONFIGURATION_EPOCH", 0) + counts.get("STABLE_OSCILLATION", 0)
    decay = counts.get("DECAY_EPOCH", 0) + counts.get("COLLAPSE_EPOCH", 0)
    growth = counts.get("RAPID_EXPANSION", 0) + counts.get("STRUCTURAL_ORGANIZATION", 0)
    stable = counts.get("QUIET_PLATEAU", 0) + counts.get("STABLE_OSCILLATION", 0)
    cycles = detect_epoch_cycles(signature)
    return {
        "epoch_count": len(epochs),
        "epoch_diversity": diversity,
        "epoch_complexity": clamp01(
            0.45 * diversity
            + 0.35 * min(1.0, len(epochs) / 8.0)
            + 0.20 * cycles["cycle_score"]
        ),
        "epoch_stability": clamp01(stable / total),
        "epoch_reconfiguration_ratio": clamp01(reconfiguration / total),
        "epoch_growth_ratio": clamp01(growth / total),
        "epoch_decay_ratio": clamp01(decay / total),
        "epoch_cycle_score": cycles["cycle_score"],
        "collapse_resistance": clamp01(1.0 - decay / total),
    }


def archetype_from_epochs(
    epochs: list[dict[str, Any]], indices: dict[str, float]
) -> str:
    counts = Counter(epoch_signature(epochs))
    if counts.get("COLLAPSE_EPOCH", 0) > 0:
        return "collapse-marked epochal arc"
    if indices["epoch_cycle_score"] >= 0.25:
        return "cyclic epochal arc"
    if indices["epoch_growth_ratio"] >= 0.45:
        return "growth epochal arc"
    if indices["epoch_reconfiguration_ratio"] >= 0.40:
        return "reconfiguration epochal arc"
    if indices["epoch_stability"] >= 0.45:
        return "stable plateau arc"
    if indices["epoch_decay_ratio"] >= 0.30:
        return "decay-heavy arc"
    return "transitional epochal arc"

