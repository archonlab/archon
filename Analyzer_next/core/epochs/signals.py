"""Smoothed scientific signals used by broad epoch detection."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.epochs.numeric import (
    moving_average,
    normalized_series,
    safe_float,
    stdev,
)


def build_signal_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    count = len(rows)
    radius = max(2, min(20, count // 18))
    raw = {
        "mass": [safe_float(row.get("_total_living_mass"), 0.0) for row in rows],
        "objects": [safe_float(row.get("_objects"), 0.0) for row in rows],
        "largest": [safe_float(row.get("_largest"), 0.0) for row in rows],
        "mci": [safe_float(row.get("_mci"), 0.0) for row in rows],
        "branching": [safe_float(row.get("_morphology_branching"), 0.0) for row in rows],
        "edge": [safe_float(row.get("_morphology_edge_complexity"), 0.0) for row in rows],
        "change": [safe_float(row.get("_morphology_change_rate"), 0.0) for row in rows],
        "pressure": [safe_float(row.get("_evo_pressure"), 0.0) for row in rows],
        "risk": [safe_float(row.get("_evo_extinction_risk"), 0.0) for row in rows],
        "stability": [safe_float(row.get("_stability_index"), 0.0) for row in rows],
        "knowledge": [safe_float(row.get("_knowledge_score"), 0.0) for row in rows],
    }
    smooth = {key: moving_average(values, radius) for key, values in raw.items()}
    normalized = {key: normalized_series(values) for key, values in smooth.items()}
    signal_rows = []
    for index, row in enumerate(rows):
        previous_index = max(0, index - radius)
        next_index = min(count - 1, index + radius)

        def delta(key: str) -> float:
            return normalized[key][next_index] - normalized[key][previous_index]

        volatility_window = normalized["change"][
            max(0, index - radius):min(count, index + radius + 1)
        ]
        mci_window = normalized["mci"][
            max(0, index - radius):min(count, index + radius + 1)
        ]
        signal_rows.append({
            "index": index,
            "tick": row["_tick"],
            "morphology_class": row["_class"],
            "signals": {key: smooth[key][index] for key in smooth},
            "norm": {key: normalized[key][index] for key in normalized},
            "delta": {
                "mass": delta("mass"),
                "objects": delta("objects"),
                "mci": delta("mci"),
                "branching": delta("branching"),
                "edge": delta("edge"),
                "change": delta("change"),
                "pressure": delta("pressure"),
                "risk": delta("risk"),
                "stability": delta("stability"),
                "knowledge": delta("knowledge"),
            },
            "local_volatility": {
                "change": stdev(volatility_window),
                "mci": stdev(mci_window),
            },
        })
    return signal_rows


def change_scores(signal_rows: list[dict[str, Any]]) -> list[float]:
    scores = []
    for signal_row in signal_rows:
        delta = signal_row["delta"]
        volatility = signal_row["local_volatility"]
        scores.append(
            0.20 * abs(delta["mass"])
            + 0.14 * abs(delta["objects"])
            + 0.18 * abs(delta["mci"])
            + 0.12 * abs(delta["branching"])
            + 0.12 * abs(delta["edge"])
            + 0.10 * abs(delta["change"])
            + 0.07 * abs(delta["pressure"])
            + 0.07 * volatility["mci"]
        )
    return scores

