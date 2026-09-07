"""Static, dynamic, and behaviour distance comparison between rules."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from Analyzer_next.core.morphology.constants import (
    BEHAVIOUR_FEATURES,
    DYNAMIC_FEATURES,
    NUMERIC_COLUMNS,
    STATIC_DISTANCE_FEATURES,
)
from Analyzer_next.core.morphology.numeric import mean, safe_float
from Analyzer_next.core.morphology.trajectory import transition_edit_distance


def normalize_vectors(
    raw: dict[str, dict[str, float]],
    features: list[str],
) -> dict[str, dict[str, float]]:
    normalized: dict[str, dict[str, float]] = {rule_id: {} for rule_id in raw}
    for feature in features:
        values = [safe_float(raw[rule_id].get(feature), 0.0) for rule_id in raw]
        low = min(values) if values else 0.0
        high = max(values) if values else 0.0
        span = high - low
        for rule_id in raw:
            if span <= 1e-12:
                normalized[rule_id][feature] = 0.0
            else:
                normalized[rule_id][feature] = (
                    safe_float(raw[rule_id].get(feature), 0.0) - low
                ) / span
    return normalized


def build_static_vectors(best_runs: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    raw: dict[str, dict[str, float]] = {}
    for rule in best_runs:
        rule_id = rule["rule_id"]
        feature_summary = rule.get("feature_summary", {})
        raw[rule_id] = {
            "dominant_share": safe_float(rule.get("dominant_share"), 0.0),
            "morphology_entropy": safe_float(rule.get("morphology_entropy"), 0.0),
            "transition_rate_per_10k_ticks": safe_float(rule.get("transition_rate_per_10k_ticks"), 0.0),
            "morphological_complexity_index": safe_float(rule.get("morphological_complexity_index"), 0.0),
        }
        for column in NUMERIC_COLUMNS:
            if column in feature_summary:
                raw[rule_id][f"{column}.mean"] = safe_float(feature_summary[column].get("mean"), 0.0)
    return normalize_vectors(raw, STATIC_DISTANCE_FEATURES)


def build_dynamic_vectors(best_runs: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    raw = {rule["rule_id"]: rule.get("dynamic_feature_vector", {}) for rule in best_runs}
    return normalize_vectors(raw, DYNAMIC_FEATURES)


def build_behaviour_vectors(best_runs: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    raw = {rule["rule_id"]: rule.get("behaviour_feature_vector", {}) for rule in best_runs}
    return normalize_vectors(raw, BEHAVIOUR_FEATURES)


def vector_distance(
    vector_a: dict[str, float],
    vector_b: dict[str, float],
    features: list[str],
) -> float:
    if not features:
        return 0.0
    total = 0.0
    for feature in features:
        difference = vector_a.get(feature, 0.0) - vector_b.get(feature, 0.0)
        total += difference * difference
    return math.sqrt(total / len(features))


def class_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    class_a = a.get("dominant_class", "NONE")
    class_b = b.get("dominant_class", "NONE")
    if class_a == class_b:
        return 0.0
    set_a = set((a.get("class_counts") or {}).keys())
    set_b = set((b.get("class_counts") or {}).keys())
    union = set_a | set_b
    intersection = set_a & set_b
    if not union:
        return 0.0
    return 1.0 - (len(intersection) / len(union))


def transition_signature_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    def pairs(item: dict[str, Any]) -> Counter:
        output = Counter()
        for source, destinations in (item.get("transition_matrix") or {}).items():
            for destination, count in (destinations or {}).items():
                output[f"{source}->{destination}"] += int(count)
        return output

    pairs_a = pairs(a)
    pairs_b = pairs(b)
    keys = set(pairs_a) | set(pairs_b)
    if not keys:
        return 0.0
    total_a = sum(pairs_a.values()) or 1
    total_b = sum(pairs_b.values()) or 1
    distance = 0.0
    for key in keys:
        distance += abs(pairs_a.get(key, 0) / total_a - pairs_b.get(key, 0) / total_b)
    return min(1.0, distance / 2.0)


def static_distance(
    a: dict[str, Any],
    b: dict[str, Any],
    vectors: dict[str, dict[str, float]],
) -> float:
    numeric = vector_distance(
        vectors[a["rule_id"]], vectors[b["rule_id"]], STATIC_DISTANCE_FEATURES
    )
    class_component = class_distance(a, b)
    transition_component = transition_signature_distance(a, b)
    return max(0.0, min(1.0, 0.74 * numeric + 0.16 * class_component + 0.10 * transition_component))


def dynamic_distance(
    a: dict[str, Any],
    b: dict[str, Any],
    vectors: dict[str, dict[str, float]],
) -> float:
    numeric = vector_distance(
        vectors[a["rule_id"]], vectors[b["rule_id"]], DYNAMIC_FEATURES
    )
    trajectory_a = a.get("trajectory_signature", {}).get("class_trajectory", [])
    trajectory_b = b.get("trajectory_signature", {}).get("class_trajectory", [])
    edit = transition_edit_distance(trajectory_a, trajectory_b)
    return max(0.0, min(1.0, 0.78 * numeric + 0.22 * edit))


def behaviour_label_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    label_a = a.get("behaviour_signature", {}).get("label")
    label_b = b.get("behaviour_signature", {}).get("label")
    return 0.0 if label_a == label_b else 1.0


def behaviour_distance(
    a: dict[str, Any],
    b: dict[str, Any],
    vectors: dict[str, dict[str, float]],
) -> float:
    numeric = vector_distance(
        vectors[a["rule_id"]], vectors[b["rule_id"]], BEHAVIOUR_FEATURES
    )
    label = behaviour_label_distance(a, b)
    return max(0.0, min(1.0, 0.85 * numeric + 0.15 * label))


def combined_distance(static_value: float, dynamic_value: float, behaviour_value: float) -> float:
    return max(0.0, min(1.0, 0.45 * static_value + 0.25 * dynamic_value + 0.30 * behaviour_value))


def build_comparison(report: dict[str, Any], top_n: int = 5) -> dict[str, Any]:
    best_runs = [rule["best_run"] for rule in report.get("rules", []) if rule.get("best_run")]
    best_runs = sorted(best_runs, key=lambda rule: rule["rule_id"])

    static_vectors = build_static_vectors(best_runs)
    dynamic_vectors = build_dynamic_vectors(best_runs)
    behaviour_vectors = build_behaviour_vectors(best_runs)

    static_matrix: dict[str, dict[str, float]] = {}
    dynamic_matrix: dict[str, dict[str, float]] = {}
    behaviour_matrix: dict[str, dict[str, float]] = {}
    combined_matrix: dict[str, dict[str, float]] = {}

    for rule_a in best_runs:
        rule_id_a = rule_a["rule_id"]
        static_matrix[rule_id_a] = {}
        dynamic_matrix[rule_id_a] = {}
        behaviour_matrix[rule_id_a] = {}
        combined_matrix[rule_id_a] = {}
        for rule_b in best_runs:
            rule_id_b = rule_b["rule_id"]
            if rule_id_a == rule_id_b:
                static_matrix[rule_id_a][rule_id_b] = 0.0
                dynamic_matrix[rule_id_a][rule_id_b] = 0.0
                behaviour_matrix[rule_id_a][rule_id_b] = 0.0
                combined_matrix[rule_id_a][rule_id_b] = 0.0
                continue
            static_value = static_distance(rule_a, rule_b, static_vectors)
            dynamic_value = dynamic_distance(rule_a, rule_b, dynamic_vectors)
            behaviour_value = behaviour_distance(rule_a, rule_b, behaviour_vectors)
            combined_value = combined_distance(static_value, dynamic_value, behaviour_value)
            static_matrix[rule_id_a][rule_id_b] = static_value
            dynamic_matrix[rule_id_a][rule_id_b] = dynamic_value
            behaviour_matrix[rule_id_a][rule_id_b] = behaviour_value
            combined_matrix[rule_id_a][rule_id_b] = combined_value

    similar_worlds = {}
    for rule_a in best_runs:
        rule_id_a = rule_a["rule_id"]
        pairs = [(rule_id_b, distance) for rule_id_b, distance in combined_matrix[rule_id_a].items() if rule_id_b != rule_id_a]
        pairs_sorted = sorted(pairs, key=lambda item: item[1])
        pairs_reverse = sorted(pairs, key=lambda item: item[1], reverse=True)
        similar_worlds[rule_id_a] = {
            "most_similar": [
                {
                    "rule_id": rule_id_b,
                    "combined_distance": distance,
                    "static_distance": static_matrix[rule_id_a][rule_id_b],
                    "dynamic_distance": dynamic_matrix[rule_id_a][rule_id_b],
                    "behaviour_distance": behaviour_matrix[rule_id_a][rule_id_b],
                }
                for rule_id_b, distance in pairs_sorted[:top_n]
            ],
            "most_different": [
                {
                    "rule_id": rule_id_b,
                    "combined_distance": distance,
                    "static_distance": static_matrix[rule_id_a][rule_id_b],
                    "dynamic_distance": dynamic_matrix[rule_id_a][rule_id_b],
                    "behaviour_distance": behaviour_matrix[rule_id_a][rule_id_b],
                }
                for rule_id_b, distance in pairs_reverse[:top_n]
            ],
        }

    all_distances = [
        distance
        for row in combined_matrix.values()
        for distance in row.values()
        if distance > 0
    ]
    if all_distances:
        threshold = min(0.35, max(0.12, mean(all_distances) * 0.75))
    else:
        threshold = 0.0

    visited = set()
    clusters = []
    for rule in best_runs:
        rule_id = rule["rule_id"]
        if rule_id in visited:
            continue
        stack = [rule_id]
        group = []
        visited.add(rule_id)
        while stack:
            current = stack.pop()
            group.append(current)
            for other, distance in combined_matrix[current].items():
                if other != current and other not in visited and distance <= threshold:
                    visited.add(other)
                    stack.append(other)
        clusters.append(sorted(group))

    clusters = sorted(clusters, key=lambda group: (-len(group), group[0]))

    trajectories = {}
    behaviours = {}
    for rule in best_runs:
        rule_id = rule["rule_id"]
        trajectory = rule.get("trajectory_signature", {})
        behaviour = rule.get("behaviour_signature", {})
        trajectories[rule_id] = {
            "trajectory": trajectory.get("class_trajectory_text"),
            "mci_sparkline": trajectory.get("mci_sparkline"),
            "change_rate_sparkline": trajectory.get("change_rate_sparkline"),
            "early": trajectory.get("early"),
            "mid": trajectory.get("mid"),
            "late": trajectory.get("late"),
            "drift": trajectory.get("drift"),
            "trajectory_volatility": trajectory.get("trajectory_volatility"),
            "trajectory_maturity": trajectory.get("trajectory_maturity"),
            "trajectory_persistence": trajectory.get("trajectory_persistence"),
        }
        behaviours[rule_id] = behaviour

    return {
        "schema": "universe_search_morphology_comparison_v23",
        "rule_count": len(best_runs),
        "static_distance_features": STATIC_DISTANCE_FEATURES,
        "dynamic_features": DYNAMIC_FEATURES,
        "behaviour_features": BEHAVIOUR_FEATURES,
        "static_distance_matrix": static_matrix,
        "dynamic_distance_matrix": dynamic_matrix,
        "behaviour_distance_matrix": behaviour_matrix,
        "combined_distance_matrix": combined_matrix,
        "similar_worlds": similar_worlds,
        "cluster_threshold": threshold,
        "family_candidates": [
            {
                "cluster_id": f"MORPH-{index + 1:03d}",
                "size": len(group),
                "rules": group,
            }
            for index, group in enumerate(clusters)
        ],
        "trajectories": trajectories,
        "behaviours": behaviours,
    }
