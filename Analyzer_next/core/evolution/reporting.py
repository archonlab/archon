"""Pure JSON and Markdown projections for evolution artifacts."""
from __future__ import annotations

import json
from typing import Any

from Analyzer_next.core.evolution.numeric import fmt_float


def write_rank_section(
    lines: list[str],
    title: str,
    report: dict[str, Any],
    key: str,
    metric: str,
) -> None:
    lines.append(f"## {title}")
    lines.append("")
    lines.append(
        "| Rule | Archetype | Dominant stage | Ticks | Score | Signature |"
    )
    lines.append("|---:|---|---|---:|---:|---|")
    for rule in report.get("global", {}).get(key, []):
        lines.append(
            f"| {rule['rule_id']} | {rule['archetype']} | "
            f"{rule['dominant_stage']} | {rule['observed_ticks']} | "
            f"{fmt_float(rule.get(metric))} | {rule['signature']} |"
        )
    lines.append("")


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphological Evolution Report v1.0")
    lines.append("")
    lines.append(f"Results folder: `{report.get('results_dir')}`")
    lines.append(f"CSV files found: **{report.get('csv_files_found', 0)}**")
    lines.append(f"Rules analyzed: **{report.get('rules_analyzed', 0)}**")
    lines.append("")
    lines.append("## Life-cycle archetypes")
    lines.append("")
    lines.append("| Archetype | Rules |")
    lines.append("|---|---:|")
    for name, count in sorted(
        report.get("global", {}).get("archetype_counts", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {name} | {count} |")
    lines.append("")
    lines.append("## Dominant stages")
    lines.append("")
    lines.append("| Stage | Rules |")
    lines.append("|---|---:|")
    for name, count in sorted(
        report.get("global", {}).get("dominant_stage_counts", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {name} | {count} |")
    lines.append("")
    write_rank_section(
        lines,
        "Most stable life cycles",
        report,
        "most_stable_life_cycles",
        "life_cycle_stability",
    )
    write_rank_section(
        lines,
        "Most complex life cycles",
        report,
        "most_complex_life_cycles",
        "life_cycle_complexity",
    )
    write_rank_section(
        lines,
        "Most reconfiguring",
        report,
        "most_reconfiguring",
        "reconfiguration_frequency",
    )
    write_rank_section(
        lines,
        "Strongest growth persistence",
        report,
        "strongest_growth_persistence",
        "growth_persistence",
    )
    lines.append("## Rule life-cycle biographies")
    lines.append("")
    for item in report.get("rules", []):
        rule = item["best_run"]
        indices = rule["indices"]
        lines.append(
            f"### Rule {rule['rule_id']} — {rule['life_cycle_archetype']}"
        )
        lines.append("")
        lines.append(f"- Source: `{rule['source_csv']}`")
        lines.append(f"- Observed ticks: **{rule['observed_ticks']}**")
        lines.append(f"- Dominant stage: **{rule['dominant_stage']}**")
        lines.append(
            f"- Life-cycle signature: **{rule['life_cycle_signature_text']}**"
        )
        lines.append(
            f"- Stability: **{fmt_float(indices.get('life_cycle_stability'))}**"
        )
        lines.append(
            f"- Diversity: **{fmt_float(indices.get('life_cycle_diversity'))}**"
        )
        lines.append(
            f"- Complexity: **{fmt_float(indices.get('life_cycle_complexity'))}**"
        )
        lines.append(
            f"- Collapse resistance: **{fmt_float(indices.get('collapse_resistance'))}**"
        )
        lines.append(
            f"- Recovery ability: **{fmt_float(indices.get('recovery_ability'))}**"
        )
        lines.append(
            "- Reconfiguration frequency: "
            f"**{fmt_float(indices.get('reconfiguration_frequency'))}**"
        )
        lines.append(
            f"- Growth persistence: **{fmt_float(indices.get('growth_persistence'))}**"
        )
        lines.append(
            f"- Evolution rhythm: **{fmt_float(indices.get('evolution_rhythm'))}**"
        )
        lines.append("")
        lines.append("Sparklines:")
        lines.append("")
        sparklines = rule["sparklines"]
        lines.append(f"- MCI: `{sparklines.get('mci')}`")
        lines.append(f"- Mass: `{sparklines.get('mass')}`")
        lines.append(f"- Objects: `{sparklines.get('objects')}`")
        lines.append(f"- Change rate: `{sparklines.get('change_rate')}`")
        lines.append(f"- Pressure: `{sparklines.get('pressure')}`")
        lines.append("")
        lines.append("Timeline:")
        lines.append("")
        lines.append(
            "| Stage | Start | End | Duration | Samples | Dominant morph | "
            "Mean MCI | Mean mass |"
        )
        lines.append("|---|---:|---:|---:|---:|---|---:|---:|")
        for segment in rule.get("segments", []):
            absorbed = ""
            if segment.get("absorbed_stages"):
                absorbed = " +" + ",".join(segment["absorbed_stages"])
            lines.append(
                f"| {segment['stage']}{absorbed} | {segment['start_tick']} | "
                f"{segment['end_tick']} | {segment['duration_ticks']} | "
                f"{segment['samples']} | {segment['dominant_morphology_class']} | "
                f"{fmt_float(segment['mean_mci'])} | "
                f"{fmt_float(segment['mean_mass'])} |"
            )
        lines.append("")
        cycles = rule.get("cycles", {})
        if cycles.get("has_repeated_cycle"):
            lines.append("Repeated cycles:")
            for cycle in cycles.get("cycles", [])[:5]:
                lines.append(
                    f"- {' -> '.join(cycle['pattern'])} ×{cycle['count']}"
                )
            lines.append("")
    if report.get("errors"):
        lines.append("## Errors")
        lines.append("")
        for error in report["errors"]:
            lines.append(
                f"- `{error.get('source_csv')}`: `{error.get('error')}`"
            )
        lines.append("")
    return "\n".join(lines)


def compact_life_cycles(report: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "schema": "universe_search_morphological_life_cycles_v10",
        "results_dir": report.get("results_dir"),
        "rules_analyzed": report.get("rules_analyzed"),
        "life_cycles": {},
    }
    for item in report.get("rules", []):
        rule = item["best_run"]
        compact["life_cycles"][rule["rule_id"]] = {
            "archetype": rule["life_cycle_archetype"],
            "dominant_stage": rule["dominant_stage"],
            "signature": rule["life_cycle_signature"],
            "signature_text": rule["life_cycle_signature_text"],
            "indices": rule["indices"],
            "segments": rule["segments"],
            "cycles": rule["cycles"],
        }
    return compact


def render_life_cycles_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphological Life Cycles")
    lines.append("")
    lines.append(
        "| Rule | Archetype | Signature | Stability | Complexity | "
        "Collapse resistance |"
    )
    lines.append("|---:|---|---|---:|---:|---:|")
    for item in report.get("rules", []):
        rule = item["best_run"]
        indices = rule["indices"]
        lines.append(
            f"| {rule['rule_id']} | {rule['life_cycle_archetype']} | "
            f"{rule['life_cycle_signature_text']} | "
            f"{fmt_float(indices.get('life_cycle_stability'))} | "
            f"{fmt_float(indices.get('life_cycle_complexity'))} | "
            f"{fmt_float(indices.get('collapse_resistance'))} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_artifacts(report: dict[str, Any]) -> dict[str, str]:
    return {
        "morphological_evolution_report.json": json.dumps(
            report, ensure_ascii=False, indent=2
        ),
        "morphological_evolution_report.md": render_report_markdown(report),
        "morphological_life_cycles.json": json.dumps(
            compact_life_cycles(report), ensure_ascii=False, indent=2
        ),
        "morphological_life_cycles.md": render_life_cycles_markdown(report),
    }

