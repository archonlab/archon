"""Render all Event Detector artifacts without filesystem access."""
from __future__ import annotations

import json
from typing import Any

from Analyzer_next.core.events.numeric import fmt_float


def write_rank_section(
    lines: list[str],
    title: str,
    report: dict[str, Any],
    key: str,
    metric: str,
) -> None:
    lines.append(f"## {title}")
    lines.append("")
    lines.append("| Rule | Archetype | Ticks | Score | Events | Sequence |")
    lines.append("|---:|---|---:|---:|---:|---|")
    for rule in report.get("global", {}).get(key, []):
        lines.append(
            f"| {rule['rule_id']} | {rule['archetype']} | {rule['observed_ticks']} | "
            f"{fmt_float(rule.get(metric))} | {rule['total_events']} | {rule['event_sequence']} |"
        )
    lines.append("")


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphological Event Report v1.0")
    lines.append("")
    lines.append(f"Results folder: `{report.get('results_dir')}`")
    lines.append(f"CSV files found: **{report.get('csv_files_found', 0)}**")
    lines.append(f"Rules analyzed: **{report.get('rules_analyzed', 0)}**")
    lines.append("")
    lines.append("## Event archetypes")
    lines.append("")
    lines.append("| Archetype | Rules |")
    lines.append("|---|---:|")
    archetypes = report.get("global", {}).get("event_archetype_counts", {})
    for name, count in sorted(archetypes.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {name} | {count} |")
    lines.append("")
    lines.append("## Global event families")
    lines.append("")
    lines.append("| Family | Events |")
    lines.append("|---|---:|")
    families = report.get("global", {}).get("event_family_counts", {})
    for name, count in sorted(families.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {name} | {count} |")
    lines.append("")
    lines.append("## Global event types")
    lines.append("")
    lines.append("| Event type | Count |")
    lines.append("|---|---:|")
    event_counts = report.get("global", {}).get("event_counts", {})
    for name, count in sorted(event_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {name} | {count} |")
    lines.append("")
    write_rank_section(
        lines, "Most eventful rules", report,
        "most_eventful_rules", "total_events",
    )
    write_rank_section(
        lines, "Most intense event arcs", report,
        "most_intense_event_arcs", "event_intensity",
    )
    write_rank_section(
        lines, "Most diverse event arcs", report,
        "most_diverse_event_arcs", "event_diversity",
    )
    write_rank_section(
        lines, "Most constructive event arcs", report,
        "most_constructive_event_arcs", "constructive_events",
    )
    write_rank_section(
        lines, "Most disruptive event arcs", report,
        "most_disruptive_event_arcs", "destructive_events",
    )
    write_rank_section(
        lines, "Most reorganizational event arcs", report,
        "most_reorganizational_event_arcs", "reorganization_events",
    )
    lines.append("## Rule event biographies")
    lines.append("")
    for item in report.get("rules", []):
        rule = item["best_run"]
        summary = rule["event_summary"]
        lines.append(f"### Rule {rule['rule_id']} — {summary['event_archetype']}")
        lines.append("")
        lines.append(f"- Source: `{rule['source_csv']}`")
        lines.append(f"- Observed ticks: **{rule['observed_ticks']}**")
        lines.append(f"- Total events: **{summary['total_events']}**")
        lines.append(
            f"- High-importance events: **{summary['high_importance_events']}**"
        )
        lines.append(
            f"- Event intensity: **{fmt_float(summary['event_intensity'])}**"
        )
        lines.append(
            f"- Event diversity: **{fmt_float(summary['event_diversity'])}**"
        )
        lines.append(
            f"- Event rate / 1k ticks: **{fmt_float(summary['event_rate_per_1k_ticks'])}**"
        )
        lines.append(
            "- Constructive / destructive / reorg: "
            f"**{summary['constructive_events']} / {summary['destructive_events']} / "
            f"{summary['reorganization_events']}**"
        )
        lines.append(f"- Event sequence: **{summary['event_sequence_text']}**")
        lines.append("")
        sparklines = rule.get("sparklines", {})
        lines.append("Sparklines:")
        lines.append("")
        lines.append(f"- MCI: `{sparklines.get('mci')}`")
        lines.append(f"- Mass: `{sparklines.get('mass')}`")
        lines.append(f"- Objects: `{sparklines.get('objects')}`")
        lines.append(f"- Branching: `{sparklines.get('branching')}`")
        lines.append(f"- Edge: `{sparklines.get('edge')}`")
        lines.append(f"- Change rate: `{sparklines.get('change_rate')}`")
        lines.append(f"- Pressure: `{sparklines.get('pressure')}`")
        lines.append(f"- Risk: `{sparklines.get('risk')}`")
        lines.append("")
        cycles = summary.get("cycles", {})
        if cycles.get("has_cycle"):
            lines.append("Repeated event cycles:")
            for cycle in cycles.get("cycles", [])[:5]:
                lines.append(f"- {' -> '.join(cycle['pattern'])} ×{cycle['count']}")
            lines.append("")
        lines.append("Top events:")
        lines.append("")
        lines.append("| Tick | Event | Importance | Severity | Morph | Signal | Description |")
        lines.append("|---:|---|---:|---:|---|---|---|")
        for event in summary.get("top_events", [])[:12]:
            lines.append(
                f"| {event['tick']} | {event['event_type']} | "
                f"{fmt_float(event.get('importance'))} | {fmt_float(event.get('severity'))} | "
                f"{event.get('morphology_class')} | {event.get('linked_signal')} | "
                f"{event.get('description')} |"
            )
        lines.append("")
        lines.append("Timeline events:")
        lines.append("")
        lines.append("| Tick | Event | Importance | Signal |")
        lines.append("|---:|---|---:|---|")
        for event in rule.get("events", [])[:80]:
            lines.append(
                f"| {event['tick']} | {event['event_type']} | "
                f"{fmt_float(event.get('importance'))} | {event.get('linked_signal')} |"
            )
        lines.append("")
    if report.get("errors"):
        lines.append("## Errors")
        lines.append("")
        for error in report["errors"]:
            lines.append(f"- `{error.get('source_csv')}`: `{error.get('error')}`")
        lines.append("")
    return "\n".join(lines)


def compact_events(report: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "schema": "universe_search_morphological_events_v10",
        "results_dir": report.get("results_dir"),
        "rules_analyzed": report.get("rules_analyzed"),
        "events": {},
    }
    for item in report.get("rules", []):
        rule = item["best_run"]
        compact["events"][rule["rule_id"]] = {
            "summary": rule["event_summary"],
            "events": rule["events"],
            "sparklines": rule["sparklines"],
        }
    return compact


def render_compact_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# Morphological Events")
    lines.append("")
    lines.append(
        "| Rule | Archetype | Total events | Intensity | Diversity | "
        "Constructive | Destructive | Reorg | Sequence |"
    )
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---|")
    for item in report.get("rules", []):
        rule = item["best_run"]
        summary = rule["event_summary"]
        lines.append(
            f"| {rule['rule_id']} | {summary['event_archetype']} | "
            f"{summary['total_events']} | {fmt_float(summary['event_intensity'])} | "
            f"{fmt_float(summary['event_diversity'])} | {summary['constructive_events']} | "
            f"{summary['destructive_events']} | {summary['reorganization_events']} | "
            f"{summary['event_sequence_text']} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_artifacts(report: dict[str, Any]) -> dict[str, str]:
    return {
        "morphological_event_report.json": json.dumps(
            report, ensure_ascii=False, indent=2
        ),
        "morphological_event_report.md": render_report_markdown(report),
        "morphological_events.json": json.dumps(
            compact_events(report), ensure_ascii=False, indent=2
        ),
        "morphological_events.md": render_compact_markdown(report),
    }
