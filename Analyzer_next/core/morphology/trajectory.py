"""Time-phase morphology trajectories and their dynamic feature vectors."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.morphology.numeric import mean, safe_float, sparkline, stdev
from Analyzer_next.core.morphology.segmentation import local_mci


def split_phases(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not rows:
        return [], [], []
    count = len(rows)
    first = max(1, count // 3)
    second = max(first + 1, 2 * count // 3) if count >= 3 else count
    return rows[:first], rows[first:second], rows[second:]


def phase_stats(rows: list[dict[str, Any]], entropy_hint: float) -> dict[str, float]:
    if not rows:
        return {
            "mci": 0.0,
            "branching": 0.0,
            "edge": 0.0,
            "change_rate": 0.0,
            "filament": 0.0,
            "lattice": 0.0,
            "symmetry": 0.0,
        }
    return {
        "mci": mean(local_mci(row, entropy_hint) for row in rows),
        "branching": mean(safe_float(row.get("_morphology_branching"), 0.0) for row in rows),
        "edge": mean(safe_float(row.get("_morphology_edge_complexity"), 0.0) for row in rows),
        "change_rate": mean(safe_float(row.get("_morphology_change_rate"), 0.0) for row in rows),
        "filament": mean(safe_float(row.get("_morphology_filament_score"), 0.0) for row in rows),
        "lattice": mean(safe_float(row.get("_morphology_lattice_score"), 0.0) for row in rows),
        "symmetry": mean(safe_float(row.get("_morphology_symmetry"), 0.0) for row in rows),
    }


def class_trajectory(segments: list[dict[str, Any]], max_items: int = 18) -> list[str]:
    raw = [segment["class"] for segment in segments if segment.get("samples", 0) > 0]
    if not raw:
        return []
    compact = []
    for morphology_class in raw:
        if not compact or compact[-1] != morphology_class:
            compact.append(morphology_class)
    if len(compact) <= max_items:
        return compact
    step = len(compact) / max_items
    return [compact[int(index * step)] for index in range(max_items)]


def trajectory_signature(
    rows: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    entropy: float,
) -> dict[str, Any]:
    early, middle, late = split_phases(rows)
    early_stats = phase_stats(early, entropy)
    middle_stats = phase_stats(middle, entropy)
    late_stats = phase_stats(late, entropy)

    mci_values = [local_mci(row, entropy) for row in rows]
    change_values = [safe_float(row.get("_morphology_change_rate"), 0.0) for row in rows]
    class_path = class_trajectory(segments)

    first_class = class_path[0] if class_path else "NONE"
    last_class = class_path[-1] if class_path else "NONE"
    transition_count = max(0, len(class_path) - 1)

    persistence = 0.0
    if segments:
        longest = max(segment.get("samples", 0) for segment in segments)
        total = sum(segment.get("samples", 0) for segment in segments) or 1
        persistence = longest / total

    volatility = mean(change_values) + stdev(mci_values)
    volatility = min(1.0, volatility / 2.5)
    maturity = max(0.0, min(1.0, late_stats["mci"]))

    drift = {
        "mci_delta": late_stats["mci"] - early_stats["mci"],
        "branching_delta": late_stats["branching"] - early_stats["branching"],
        "edge_delta": late_stats["edge"] - early_stats["edge"],
        "change_rate_delta": late_stats["change_rate"] - early_stats["change_rate"],
        "filament_delta": late_stats["filament"] - early_stats["filament"],
        "lattice_delta": late_stats["lattice"] - early_stats["lattice"],
    }

    return {
        "class_trajectory": class_path,
        "class_trajectory_text": " -> ".join(class_path) if class_path else "NONE",
        "first_class": first_class,
        "last_class": last_class,
        "class_changed": first_class != last_class,
        "class_transition_count": transition_count,
        "mci_sparkline": sparkline(mci_values),
        "change_rate_sparkline": sparkline(change_values),
        "early": early_stats,
        "mid": middle_stats,
        "late": late_stats,
        "drift": drift,
        "trajectory_volatility": volatility,
        "trajectory_maturity": maturity,
        "trajectory_persistence": persistence,
    }


def dynamic_feature_vector(signature: dict[str, Any]) -> dict[str, float]:
    early = signature.get("early", {})
    middle = signature.get("mid", {})
    late = signature.get("late", {})
    drift = signature.get("drift", {})
    return {
        "early_mci": safe_float(early.get("mci")),
        "mid_mci": safe_float(middle.get("mci")),
        "late_mci": safe_float(late.get("mci")),
        "mci_delta": safe_float(drift.get("mci_delta")),
        "early_branching": safe_float(early.get("branching")),
        "late_branching": safe_float(late.get("branching")),
        "branching_delta": safe_float(drift.get("branching_delta")),
        "early_edge": safe_float(early.get("edge")),
        "late_edge": safe_float(late.get("edge")),
        "edge_delta": safe_float(drift.get("edge_delta")),
        "early_change_rate": safe_float(early.get("change_rate")),
        "late_change_rate": safe_float(late.get("change_rate")),
        "change_rate_delta": safe_float(drift.get("change_rate_delta")),
        "trajectory_volatility": safe_float(signature.get("trajectory_volatility")),
        "trajectory_maturity": safe_float(signature.get("trajectory_maturity")),
        "trajectory_persistence": safe_float(signature.get("trajectory_persistence")),
    }


def transition_edit_distance(a: list[str], b: list[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0

    n, m = len(a), len(b)
    matrix = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        matrix[i][0] = i
    for j in range(m + 1):
        matrix[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost,
            )
    return matrix[n][m] / max(n, m)
