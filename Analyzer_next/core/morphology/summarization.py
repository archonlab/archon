"""Per-run summaries and the cross-run morphology report."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from Analyzer_next.core.morphology.behaviour import (
    behaviour_feature_vector,
    behaviour_signature,
)
from Analyzer_next.core.morphology.boundary import boundary_growth_summary
from Analyzer_next.core.morphology.numeric import entropy_from_counts, pearson, safe_float
from Analyzer_next.core.morphology.rows import infer_rule_id, normalize_rows
from Analyzer_next.core.morphology.segmentation import (
    build_segments,
    feature_summary,
    morphological_complexity_index,
    transition_matrix,
)
from Analyzer_next.core.morphology.trajectory import (
    dynamic_feature_vector,
    trajectory_signature,
)


def summarize_rows(
    path: Path,
    raw_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows = normalize_rows(raw_rows)
    if not rows:
        return None

    rule_id = infer_rule_id(path, rows)
    first_tick = rows[0]["_tick"]
    last_tick = rows[-1]["_tick"]
    total_ticks = max(1, last_tick - first_tick)

    class_counts = Counter(row["_class"] for row in rows)
    segments = build_segments(rows)
    transitions = transition_matrix(segments)

    duration_by_class = Counter()
    samples_by_class = Counter()
    for segment in segments:
        duration_by_class[segment["class"]] += int(segment["duration_ticks"])
        samples_by_class[segment["class"]] += int(segment["samples"])

    dominant_class = class_counts.most_common(1)[0][0] if class_counts else "NONE"
    dominant_share = class_counts[dominant_class] / max(1, len(rows))
    entropy = entropy_from_counts(class_counts)
    transition_count = max(0, len(segments) - 1)
    transition_rate = transition_count / total_ticks * 10000.0
    features = feature_summary(rows)
    complexity = morphological_complexity_index(features, entropy, transition_rate)

    trajectory = trajectory_signature(rows, segments, entropy)
    behaviour = behaviour_signature(rows, entropy)
    boundary_growth = boundary_growth_summary(rows)

    longest_segment = max(segments, key=lambda item: item.get("duration_ticks", 0)) if segments else None
    min_epoch_ticks = max(100, int(total_ticks * 0.01))
    major_epochs = [
        segment for segment in segments
        if segment["duration_ticks"] >= min_epoch_ticks or segment["samples"] >= 3
    ]

    correlations = {}
    targets = [
        "evo_stress", "evo_pressure", "evo_extinction_risk", "knowledge_score",
        "feedback_score", "emergence_score", "validation_quality", "stability_index",
        "objects", "total_living_mass", "largest",
    ]
    morph_series = {
        "change_rate": [safe_float(row.get("_morphology_change_rate"), 0.0) for row in rows],
        "branching": [safe_float(row.get("_morphology_branching"), 0.0) for row in rows],
        "edge_complexity": [safe_float(row.get("_morphology_edge_complexity"), 0.0) for row in rows],
        "lattice": [safe_float(row.get("_morphology_lattice_score"), 0.0) for row in rows],
        "filament": [safe_float(row.get("_morphology_filament_score"), 0.0) for row in rows],
    }
    for target in targets:
        key = f"_{target}"
        target_values = [safe_float(row.get(key), 0.0) for row in rows if key in row]
        if len(target_values) >= 3 and len(target_values) == len(rows):
            for morph_name, morph_values in morph_series.items():
                correlations[f"{morph_name}_vs_{target}"] = pearson(morph_values, target_values)

    return {
        "rule_id": rule_id,
        "source_csv": str(path),
        "first_tick": first_tick,
        "last_tick": last_tick,
        "observed_ticks": total_ticks,
        "samples": len(rows),
        "dominant_class": dominant_class,
        "dominant_share": dominant_share,
        "dominant_morphology_confidence": dominant_share,
        "morphological_complexity_index": complexity,
        "class_counts": dict(class_counts),
        "duration_by_class_ticks": dict(duration_by_class),
        "samples_by_class": dict(samples_by_class),
        "morphology_entropy": entropy,
        "transition_count": transition_count,
        "transition_rate_per_10k_ticks": transition_rate,
        "transition_matrix": transitions,
        "longest_segment": longest_segment,
        "major_epochs": major_epochs[:200],
        "feature_summary": features,
        "trajectory_signature": trajectory,
        "behaviour_signature": behaviour,
        "boundary_growth": boundary_growth,
        "dynamic_feature_vector": dynamic_feature_vector(trajectory),
        "behaviour_feature_vector": behaviour_feature_vector(behaviour),
        "correlations": correlations,
        "segments_count": len(segments),
    }


def merge_rule_summaries(items: list[dict[str, Any]]) -> dict[str, Any]:
    best = max(items, key=lambda item: (item.get("observed_ticks", 0), item.get("samples", 0)))
    return {
        "rule_id": best["rule_id"],
        "runs": items,
        "best_run": best,
        "run_count": len(items),
    }


def slim_rules(
    items: list[dict[str, Any]],
    metric: str,
    extra: str | None = None,
) -> list[dict[str, Any]]:
    output = []
    for rule in items:
        item = {
            "rule_id": rule.get("rule_id"),
            "dominant_class": rule.get("dominant_class"),
            "observed_ticks": rule.get("observed_ticks"),
            metric: rule.get(metric),
        }
        if extra:
            item[extra] = rule.get(extra)
        output.append(item)
    return output


def slim_dynamic_rules(items: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    output = []
    for rule in items:
        signature = rule.get("trajectory_signature", {})
        output.append({
            "rule_id": rule.get("rule_id"),
            "dominant_class": rule.get("dominant_class"),
            "observed_ticks": rule.get("observed_ticks"),
            metric: signature.get(metric),
            "trajectory": signature.get("class_trajectory_text"),
            "mci_delta": signature.get("drift", {}).get("mci_delta"),
        })
    return output


def slim_behaviour_rules(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for rule in items:
        behaviour = rule.get("behaviour_signature", {})
        scores = behaviour.get("scores", {})
        slopes = behaviour.get("feature_slopes", {})
        output.append({
            "rule_id": rule.get("rule_id"),
            "dominant_class": rule.get("dominant_class"),
            "observed_ticks": rule.get("observed_ticks"),
            "behaviour_label": behaviour.get("label"),
            "volatility": scores.get("behaviour_volatility"),
            "drift_strength": scores.get("behaviour_drift_strength"),
            "oscillation": scores.get("behaviour_oscillation"),
            "complexity_slope": slopes.get("behaviour_complexity_slope"),
            "branching_slope": slopes.get("behaviour_branching_slope"),
            "edge_slope": slopes.get("behaviour_edge_slope"),
        })
    return output


def build_report(
    results_dir: Path,
    summaries: list[dict[str, Any] | None],
    csv_files_found: int,
) -> dict[str, Any]:
    valid_summaries = [item for item in summaries if item]
    by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors = []
    for summary in valid_summaries:
        if "error" in summary:
            errors.append(summary)
        else:
            by_rule[summary["rule_id"]].append(summary)

    rules = [merge_rule_summaries(items) for _, items in sorted(by_rule.items())]
    best_runs = [rule["best_run"] for rule in rules if rule.get("best_run")]

    class_counter = Counter(rule.get("dominant_class", "NONE") for rule in best_runs)
    behaviour_counter = Counter(
        rule.get("behaviour_signature", {}).get("label", "UNKNOWN")
        for rule in best_runs
    )

    most_stable = sorted(best_runs, key=lambda rule: rule.get("transition_rate_per_10k_ticks", 0.0))[:10]
    most_variable = sorted(best_runs, key=lambda rule: rule.get("morphology_entropy", 0.0), reverse=True)[:10]
    longest_observed = sorted(best_runs, key=lambda rule: rule.get("observed_ticks", 0), reverse=True)[:10]
    most_complex = sorted(best_runs, key=lambda rule: rule.get("morphological_complexity_index", 0.0), reverse=True)[:10]
    most_dynamic = sorted(best_runs, key=lambda rule: rule.get("trajectory_signature", {}).get("trajectory_volatility", 0.0), reverse=True)[:10]
    most_mature = sorted(best_runs, key=lambda rule: rule.get("trajectory_signature", {}).get("trajectory_maturity", 0.0), reverse=True)[:10]
    strongest_behaviour = sorted(best_runs, key=lambda rule: rule.get("behaviour_signature", {}).get("scores", {}).get("behaviour_drift_strength", 0.0), reverse=True)[:10]
    most_oscillating = sorted(best_runs, key=lambda rule: rule.get("behaviour_signature", {}).get("scores", {}).get("behaviour_oscillation", 0.0), reverse=True)[:10]

    return {
        "schema": "universe_search_morphology_report_v23",
        "results_dir": str(results_dir),
        "csv_files_found": csv_files_found,
        "rules_with_morphology": len(rules),
        "errors": errors,
        "global": {
            "dominant_class_counts": dict(class_counter),
            "behaviour_label_counts": dict(behaviour_counter),
            "most_stable_rules": slim_rules(most_stable, "transition_rate_per_10k_ticks"),
            "most_variable_rules": slim_rules(most_variable, "morphology_entropy", extra="transition_count"),
            "longest_observed_rules": slim_rules(longest_observed, "samples"),
            "most_complex_rules": slim_rules(most_complex, "morphological_complexity_index", extra="morphology_entropy"),
            "most_dynamic_rules": slim_dynamic_rules(most_dynamic, "trajectory_volatility"),
            "most_mature_rules": slim_dynamic_rules(most_mature, "trajectory_maturity"),
            "strongest_behaviour_drift": slim_behaviour_rules(strongest_behaviour),
            "most_oscillating_rules": slim_behaviour_rules(most_oscillating),
        },
        "rules": rules,
    }
