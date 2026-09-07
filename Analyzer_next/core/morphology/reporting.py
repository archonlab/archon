"""Pure JSON, CSV, and Markdown rendering for morphology artifacts."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from Analyzer_next.core.morphology.numeric import fmt_float


def render_matrix_csv(matrix: dict[str, dict[str, float]]) -> str:
    rules = sorted(matrix.keys())
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["rule_id"] + rules)
    for rule_id in rules:
        writer.writerow(
            [rule_id] + [fmt_float(matrix[rule_id].get(other, 0.0), 6) for other in rules]
        )
    return output.getvalue()


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphology Analyzer Report v2.3")
    lines.append("")
    lines.append(f"Results folder: `{report.get('results_dir')}`")
    lines.append(f"CSV files found: **{report.get('csv_files_found', 0)}**")
    lines.append(f"Rules with morphology: **{report.get('rules_with_morphology', 0)}**")
    lines.append("")

    lines.append("## Dominant morphology classes")
    lines.append("")
    lines.append("| Class | Rules |")
    lines.append("|---|---:|")
    for morphology_class, count in sorted(
        report.get("global", {}).get("dominant_class_counts", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {morphology_class} | {count} |")
    lines.append("")

    lines.append("## Behaviour labels")
    lines.append("")
    lines.append("| Behaviour | Rules |")
    lines.append("|---|---:|")
    for label, count in sorted(
        report.get("global", {}).get("behaviour_label_counts", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {label} | {count} |")
    lines.append("")

    lines.append("## Strongest behaviour drift")
    lines.append("")
    lines.append("| Rule | Behaviour | Drift | Oscillation | Complexity slope | Branching slope |")
    lines.append("|---:|---|---:|---:|---:|---:|")
    for rule in report.get("global", {}).get("strongest_behaviour_drift", []):
        lines.append(
            f"| {rule['rule_id']} | {rule['behaviour_label']} | {fmt_float(rule.get('drift_strength'))} | "
            f"{fmt_float(rule.get('oscillation'))} | {fmt_float(rule.get('complexity_slope'))} | {fmt_float(rule.get('branching_slope'))} |"
        )
    lines.append("")

    lines.append("## Rule details")
    lines.append("")
    for item in report.get("rules", []):
        rule = item.get("best_run", {})
        trajectory = rule.get("trajectory_signature", {})
        behaviour = rule.get("behaviour_signature", {})
        lines.append(f"### Rule {rule.get('rule_id', 'unknown')}")
        lines.append("")
        lines.append(f"- Source: `{rule.get('source_csv')}`")
        lines.append(f"- Dominant class: **{rule.get('dominant_class')}** ({fmt_float(rule.get('dominant_share'), 2)})")
        lines.append(f"- Behaviour: **{behaviour.get('label')}**")
        lines.append(f"- Behaviour description: {behaviour.get('description')}")
        lines.append(f"- Morphological Complexity Index: **{fmt_float(rule.get('morphological_complexity_index'))}**")
        lines.append(f"- Trajectory: **{trajectory.get('class_trajectory_text', 'NONE')}**")
        lines.append(f"- MCI sparkline: `{trajectory.get('mci_sparkline', '')}`")
        lines.append(f"- Branching sparkline: `{behaviour.get('sparklines', {}).get('branching', '')}`")
        lines.append(f"- Edge sparkline: `{behaviour.get('sparklines', {}).get('edge', '')}`")
        lines.append(f"- Filament sparkline: `{behaviour.get('sparklines', {}).get('filament', '')}`")
        lines.append(f"- Volatility: **{fmt_float(trajectory.get('trajectory_volatility'))}**")
        lines.append(f"- Behaviour drift: **{fmt_float(behaviour.get('scores', {}).get('behaviour_drift_strength'))}**")
        lines.append(f"- Oscillation: **{fmt_float(behaviour.get('scores', {}).get('behaviour_oscillation'))}**")
        lines.append(f"- Complexity slope: **{fmt_float(behaviour.get('feature_slopes', {}).get('behaviour_complexity_slope'))}**")
        lines.append(f"- Branching slope: **{fmt_float(behaviour.get('feature_slopes', {}).get('behaviour_branching_slope'))}**")
        lines.append(f"- Edge slope: **{fmt_float(behaviour.get('feature_slopes', {}).get('behaviour_edge_slope'))}**")
        lines.append(f"- Transitions: **{rule.get('transition_count')}**")
        lines.append("")

    return "\n".join(lines)


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphology Comparison v2.3")
    lines.append("")
    lines.append(f"Rules compared: **{comparison.get('rule_count', 0)}**")
    lines.append(f"Cluster threshold: **{fmt_float(comparison.get('cluster_threshold', 0.0))}**")
    lines.append("")

    lines.append("## Family candidates")
    lines.append("")
    lines.append("| Cluster | Size | Rules |")
    lines.append("|---|---:|---|")
    for cluster in comparison.get("family_candidates", []):
        lines.append(f"| {cluster['cluster_id']} | {cluster['size']} | {', '.join(cluster['rules'])} |")
    lines.append("")

    lines.append("## Similar worlds, combined distance")
    lines.append("")
    for rule_id, data in sorted(comparison.get("similar_worlds", {}).items()):
        lines.append(f"### Rule {rule_id}")
        lines.append("")
        lines.append("Most similar:")
        for item in data.get("most_similar", []):
            lines.append(
                f"- {item['rule_id']}: combined {fmt_float(item['combined_distance'])}, "
                f"static {fmt_float(item['static_distance'])}, dynamic {fmt_float(item['dynamic_distance'])}, "
                f"behaviour {fmt_float(item['behaviour_distance'])}"
            )
        lines.append("")
        lines.append("Most different:")
        for item in data.get("most_different", []):
            lines.append(
                f"- {item['rule_id']}: combined {fmt_float(item['combined_distance'])}, "
                f"static {fmt_float(item['static_distance'])}, dynamic {fmt_float(item['dynamic_distance'])}, "
                f"behaviour {fmt_float(item['behaviour_distance'])}"
            )
        lines.append("")

    lines.append("## Combined distance matrix")
    lines.append("")
    matrix = comparison.get("combined_distance_matrix", {})
    rules = sorted(matrix.keys())
    if rules:
        lines.append("| Rule | " + " | ".join(rules) + " |")
        lines.append("|---|" + "|".join(["---:"] * len(rules)) + "|")
        for rule_id in rules:
            lines.append("| " + rule_id + " | " + " | ".join(fmt_float(matrix[rule_id].get(other, 0.0)) for other in rules) + " |")
    lines.append("")
    return "\n".join(lines)


def render_trajectory_markdown(comparison: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphology Trajectory Report v2.3")
    lines.append("")
    lines.append("This report compares not only what each rule looks like, but how its morphology changes through observation time.")
    lines.append("")

    lines.append("## Trajectories")
    lines.append("")
    lines.append("| Rule | Trajectory | Volatility | Maturity | Persistence | MCI sparkline | Change sparkline |")
    lines.append("|---:|---|---:|---:|---:|---|---|")
    for rule_id, trajectory in sorted(comparison.get("trajectories", {}).items()):
        lines.append(
            f"| {rule_id} | {trajectory.get('trajectory')} | {fmt_float(trajectory.get('trajectory_volatility'))} | "
            f"{fmt_float(trajectory.get('trajectory_maturity'))} | {fmt_float(trajectory.get('trajectory_persistence'))} | "
            f"`{trajectory.get('mci_sparkline')}` | `{trajectory.get('change_rate_sparkline')}` |"
        )
    lines.append("")

    lines.append("## Dynamic distance matrix")
    lines.append("")
    matrix = comparison.get("dynamic_distance_matrix", {})
    rules = sorted(matrix.keys())
    if rules:
        lines.append("| Rule | " + " | ".join(rules) + " |")
        lines.append("|---|" + "|".join(["---:"] * len(rules)) + "|")
        for rule_id in rules:
            lines.append("| " + rule_id + " | " + " | ".join(fmt_float(matrix[rule_id].get(other, 0.0)) for other in rules) + " |")
    lines.append("")
    return "\n".join(lines)


def render_behaviour_markdown(comparison: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphology Behaviour Report v2.3")
    lines.append("")
    lines.append("This report tracks how morphology feature vectors behave even when the class label stays the same.")
    lines.append("")

    lines.append("## Behaviour summary")
    lines.append("")
    lines.append("| Rule | Label | Drift | Volatility | Oscillation | MCI slope | Branching slope | Edge slope |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|")
    for rule_id, behaviour in sorted(comparison.get("behaviours", {}).items()):
        scores = behaviour.get("scores", {})
        slopes = behaviour.get("feature_slopes", {})
        lines.append(
            f"| {rule_id} | {behaviour.get('label')} | {fmt_float(scores.get('behaviour_drift_strength'))} | "
            f"{fmt_float(scores.get('behaviour_volatility'))} | {fmt_float(scores.get('behaviour_oscillation'))} | "
            f"{fmt_float(slopes.get('behaviour_complexity_slope'))} | "
            f"{fmt_float(slopes.get('behaviour_branching_slope'))} | "
            f"{fmt_float(slopes.get('behaviour_edge_slope'))} |"
        )
    lines.append("")

    lines.append("## Feature sparklines")
    lines.append("")
    for rule_id, behaviour in sorted(comparison.get("behaviours", {}).items()):
        sparklines = behaviour.get("sparklines", {})
        lines.append(f"### Rule {rule_id} — {behaviour.get('label')}")
        lines.append("")
        lines.append(f"- Description: {behaviour.get('description')}")
        lines.append(f"- MCI: `{sparklines.get('mci', '')}`")
        lines.append(f"- Branching: `{sparklines.get('branching', '')}`")
        lines.append(f"- Edge: `{sparklines.get('edge', '')}`")
        lines.append(f"- Filament: `{sparklines.get('filament', '')}`")
        lines.append(f"- Lattice: `{sparklines.get('lattice', '')}`")
        lines.append(f"- Change rate: `{sparklines.get('change_rate', '')}`")
        lines.append("")

    lines.append("## Behaviour distance matrix")
    lines.append("")
    matrix = comparison.get("behaviour_distance_matrix", {})
    rules = sorted(matrix.keys())
    if rules:
        lines.append("| Rule | " + " | ".join(rules) + " |")
        lines.append("|---|" + "|".join(["---:"] * len(rules)) + "|")
        for rule_id in rules:
            lines.append("| " + rule_id + " | " + " | ".join(fmt_float(matrix[rule_id].get(other, 0.0)) for other in rules) + " |")
    lines.append("")
    return "\n".join(lines)


def render_artifacts(
    report: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, str]:
    return {
        "morphology_report.json": json.dumps(report, ensure_ascii=False, indent=2),
        "morphology_report.md": render_report_markdown(report),
        "morphology_static_distance_matrix.json": json.dumps({
            "schema": comparison["schema"],
            "matrix_type": "static",
            "features": comparison["static_distance_features"],
            "distance_matrix": comparison["static_distance_matrix"],
        }, ensure_ascii=False, indent=2),
        "morphology_dynamic_distance_matrix.json": json.dumps({
            "schema": comparison["schema"],
            "matrix_type": "dynamic",
            "features": comparison["dynamic_features"],
            "distance_matrix": comparison["dynamic_distance_matrix"],
        }, ensure_ascii=False, indent=2),
        "morphology_behaviour_distance_matrix.json": json.dumps({
            "schema": comparison["schema"],
            "matrix_type": "behaviour",
            "features": comparison["behaviour_features"],
            "distance_matrix": comparison["behaviour_distance_matrix"],
        }, ensure_ascii=False, indent=2),
        "morphology_distance_matrix.json": json.dumps({
            "schema": comparison["schema"],
            "matrix_type": "combined",
            "static_weight": 0.45,
            "dynamic_weight": 0.25,
            "behaviour_weight": 0.30,
            "distance_matrix": comparison["combined_distance_matrix"],
        }, ensure_ascii=False, indent=2),
        "morphology_distance_matrix.csv": render_matrix_csv(comparison["combined_distance_matrix"]),
        "similar_worlds.json": json.dumps({
            "schema": comparison["schema"],
            "similar_worlds": comparison["similar_worlds"],
            "family_candidates": comparison["family_candidates"],
            "cluster_threshold": comparison["cluster_threshold"],
        }, ensure_ascii=False, indent=2),
        "morphology_comparison.md": render_comparison_markdown(comparison),
        "morphology_trajectory_report.json": json.dumps({
            "schema": comparison["schema"],
            "trajectories": comparison["trajectories"],
            "dynamic_distance_matrix": comparison["dynamic_distance_matrix"],
        }, ensure_ascii=False, indent=2),
        "morphology_trajectory_report.md": render_trajectory_markdown(comparison),
        "morphology_behaviour_report.json": json.dumps({
            "schema": comparison["schema"],
            "behaviours": comparison["behaviours"],
            "behaviour_distance_matrix": comparison["behaviour_distance_matrix"],
        }, ensure_ascii=False, indent=2),
        "morphology_behaviour_report.md": render_behaviour_markdown(comparison),
    }
