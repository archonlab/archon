"""Deterministic JSON and Markdown rendering for epoch artifacts."""
from __future__ import annotations

import json
from typing import Any

from Analyzer_next.core.epochs.numeric import fmt_float


def write_rank_section(
    lines: list[str],
    title: str,
    report: dict[str, Any],
    key: str,
    metric: str,
) -> None:
    lines.append(f"## {title}")
    lines.append("")
    lines.append("| Rule | Archetype | Ticks | Epochs | Score | Signature |")
    lines.append("|---:|---|---:|---:|---:|---|")
    for rule in report.get("global", {}).get(key, []):
        lines.append(
            f"| {rule['rule_id']} | {rule['archetype']} | {rule['observed_ticks']} | "
            f"{rule['epoch_count']} | {fmt_float(rule.get(metric))} | {rule['signature']} |"
        )
    lines.append("")


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphological Epoch Report v1.0")
    lines.append("")
    lines.append(f"Results folder: `{report.get('results_dir')}`")
    lines.append(f"CSV files found: **{report.get('csv_files_found', 0)}**")
    lines.append(f"Rules analyzed: **{report.get('rules_analyzed', 0)}**")
    lines.append("")
    lines.append("## Epoch archetypes")
    lines.append("")
    lines.append("| Archetype | Rules |")
    lines.append("|---|---:|")
    archetypes = report.get("global", {}).get("epoch_archetype_counts", {})
    for name, count in sorted(archetypes.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {name} | {count} |")
    lines.append("")
    write_rank_section(
        lines, "Most complex epoch arcs", report,
        "most_complex_epoch_arcs", "epoch_complexity",
    )
    write_rank_section(
        lines, "Most stable epoch arcs", report,
        "most_stable_epoch_arcs", "epoch_stability",
    )
    write_rank_section(
        lines, "Most reconfiguring epoch arcs", report,
        "most_reconfiguring_epoch_arcs", "epoch_reconfiguration_ratio",
    )
    write_rank_section(
        lines, "Strongest growth epoch arcs", report,
        "strongest_growth_epoch_arcs", "epoch_growth_ratio",
    )
    write_rank_section(
        lines, "Strongest decay epoch arcs", report,
        "strongest_decay_epoch_arcs", "epoch_decay_ratio",
    )
    lines.append("## Rule epoch biographies")
    lines.append("")
    for item in report.get("rules", []):
        rule = item["best_run"]
        indices = rule["indices"]
        lines.append(f"### Rule {rule['rule_id']} — {rule['epoch_archetype']}")
        lines.append("")
        lines.append(f"- Source: `{rule['source_csv']}`")
        lines.append(f"- Observed ticks: **{rule['observed_ticks']}**")
        lines.append(f"- Epoch signature: **{rule['epoch_signature_text']}**")
        lines.append(f"- Epoch count: **{indices.get('epoch_count')}**")
        lines.append(f"- Complexity: **{fmt_float(indices.get('epoch_complexity'))}**")
        lines.append(f"- Stability: **{fmt_float(indices.get('epoch_stability'))}**")
        lines.append(f"- Growth ratio: **{fmt_float(indices.get('epoch_growth_ratio'))}**")
        lines.append(
            f"- Reconfiguration ratio: **{fmt_float(indices.get('epoch_reconfiguration_ratio'))}**"
        )
        lines.append(f"- Decay ratio: **{fmt_float(indices.get('epoch_decay_ratio'))}**")
        lines.append(f"- Collapse resistance: **{fmt_float(indices.get('collapse_resistance'))}**")
        lines.append("")
        sparklines = rule.get("sparklines", {})
        lines.append("Sparklines:")
        lines.append("")
        lines.append(f"- MCI: `{sparklines.get('mci')}`")
        lines.append(f"- Mass: `{sparklines.get('mass')}`")
        lines.append(f"- Change rate: `{sparklines.get('change_rate')}`")
        lines.append(f"- Pressure: `{sparklines.get('pressure')}`")
        lines.append("")
        lines.append("Epoch timeline:")
        lines.append("")
        lines.append("| Epoch | Start | End | Duration | Samples | Morph | Mean MCI | Mean mass | ΔMCI | ΔMass |")
        lines.append("|---|---:|---:|---:|---:|---|---:|---:|---:|---:|")
        for epoch in rule.get("epochs", []):
            lines.append(
                f"| {epoch['epoch_type']} | {epoch['start_tick']} | {epoch['end_tick']} | "
                f"{epoch['duration_ticks']} | {epoch['samples']} | {epoch['dominant_morphology_class']} | "
                f"{fmt_float(epoch['mean']['mci'])} | {fmt_float(epoch['mean']['mass'])} | "
                f"{fmt_float(epoch['slopes']['mci'])} | {fmt_float(epoch['slopes']['mass'])} |"
            )
        lines.append("")
        cycles = rule.get("cycles", {})
        if cycles.get("has_cycle"):
            lines.append("Repeated epoch cycles:")
            for cycle in cycles.get("cycles", [])[:5]:
                lines.append(f"- {' -> '.join(cycle['pattern'])} ×{cycle['count']}")
            lines.append("")
    if report.get("errors"):
        lines.append("## Errors")
        lines.append("")
        for error in report["errors"]:
            lines.append(f"- `{error.get('source_csv')}`: `{error.get('error')}`")
        lines.append("")
    return "\n".join(lines)


def compact_epochs(report: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "schema": "universe_search_morphological_epochs_v10",
        "results_dir": report.get("results_dir"),
        "rules_analyzed": report.get("rules_analyzed"),
        "epochs": {},
    }
    for item in report.get("rules", []):
        rule = item["best_run"]
        compact["epochs"][rule["rule_id"]] = {
            "archetype": rule["epoch_archetype"],
            "signature": rule["epoch_signature"],
            "signature_text": rule["epoch_signature_text"],
            "indices": rule["indices"],
            "epochs": rule["epochs"],
            "cycles": rule["cycles"],
        }
    return compact


def render_compact_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphological Epochs")
    lines.append("")
    lines.append("| Rule | Archetype | Epoch signature | Complexity | Stability | Growth | Reconfig | Decay |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|")
    for item in report.get("rules", []):
        rule = item["best_run"]
        indices = rule["indices"]
        lines.append(
            f"| {rule['rule_id']} | {rule['epoch_archetype']} | {rule['epoch_signature_text']} | "
            f"{fmt_float(indices.get('epoch_complexity'))} | {fmt_float(indices.get('epoch_stability'))} | "
            f"{fmt_float(indices.get('epoch_growth_ratio'))} | "
            f"{fmt_float(indices.get('epoch_reconfiguration_ratio'))} | "
            f"{fmt_float(indices.get('epoch_decay_ratio'))} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_artifacts(report: dict[str, Any]) -> dict[str, str]:
    return {
        "morphological_epoch_report.json": json.dumps(
            report, ensure_ascii=False, indent=2
        ),
        "morphological_epoch_report.md": render_report_markdown(report),
        "morphological_epochs.json": json.dumps(
            compact_epochs(report), ensure_ascii=False, indent=2
        ),
        "morphological_epochs.md": render_compact_markdown(report),
    }

