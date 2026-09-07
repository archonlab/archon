"""Render all Fusion v1.0 artifacts without filesystem access."""
from __future__ import annotations

import json
from typing import Any

from Analyzer_next.core.fusion.numeric import fmt_float


def write_rank_section(
    lines: list[str],
    title: str,
    report: dict[str, Any],
    key: str,
    metric: str,
) -> None:
    lines.append(f"## {title}")
    lines.append("")
    lines.append("| Rule | Archetype | Score | Raw | Fused | Sequence |")
    lines.append("|---:|---|---:|---:|---:|---|")
    for rule in report["global"].get(key, []):
        lines.append(
            f"| {rule['rule_id']} | {rule['archetype']} | "
            f"{fmt_float(rule.get(metric))} | {rule['raw_events']} | "
            f"{rule['fused_events']} | {rule['sequence']} |"
        )
    lines.append("")


def render_report_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Morphological Event Fusion Report v1.0")
    lines.append("")
    lines.append(f"Results folder: `{report.get('results_dir')}`")
    lines.append(f"Rules analyzed: **{report.get('rules_analyzed', 0)}**")
    lines.append("")
    lines.append("## Fused archetypes")
    lines.append("")
    lines.append("| Archetype | Rules |")
    lines.append("|---|---:|")
    for name, count in sorted(
        report["global"]["fused_archetype_counts"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {name} | {count} |")
    lines.append("")
    lines.append("## Fused event families")
    lines.append("")
    lines.append("| Family | Count |")
    lines.append("|---|---:|")
    for name, count in sorted(
        report["global"]["fused_family_counts"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {name} | {count} |")
    lines.append("")
    lines.append("## Fused event types")
    lines.append("")
    lines.append("| Type | Count |")
    lines.append("|---|---:|")
    for name, count in sorted(
        report["global"]["fused_event_counts"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"| {name} | {count} |")
    lines.append("")
    write_rank_section(
        lines, "Most compressed rules", report,
        "most_compressed_rules", "compression_ratio",
    )
    write_rank_section(
        lines, "Most fused-eventful rules", report,
        "most_fused_eventful_rules", "fused_event_count",
    )
    write_rank_section(
        lines, "Most severe fused arcs", report,
        "most_severe_fused_arcs", "mean_fused_severity",
    )
    write_rank_section(
        lines, "Most constructive fused arcs", report,
        "most_constructive_fused_arcs", "constructive_fused_events",
    )
    write_rank_section(
        lines, "Most destructive fused arcs", report,
        "most_destructive_fused_arcs", "destructive_fused_events",
    )
    write_rank_section(
        lines, "Most reorganizational fused arcs", report,
        "most_reorganizational_fused_arcs", "reorganizational_fused_events",
    )
    lines.append("## Rule fused biographies")
    lines.append("")
    for rule_id, item in sorted(report["rules"].items()):
        summary = item["summary"]
        lines.append(f"### Rule {rule_id} — {summary['fused_archetype']}")
        lines.append("")
        lines.append(f"- Raw events: **{summary['raw_event_count']}**")
        lines.append(f"- Fused events: **{summary['fused_event_count']}**")
        lines.append(
            f"- Compression ratio: **{fmt_float(summary['compression_ratio'])}**"
        )
        lines.append(f"- Events reduced by: **{summary['events_reduced_by']}**")
        lines.append(
            f"- Mean severity: **{fmt_float(summary['mean_fused_severity'])}**"
        )
        lines.append(
            f"- Mean confidence: **{fmt_float(summary['mean_fused_confidence'])}**"
        )
        lines.append(
            "- Constructive / destructive / reorg: "
            f"**{summary['constructive_fused_events']} / "
            f"{summary['destructive_fused_events']} / "
            f"{summary['reorganizational_fused_events']}**"
        )
        lines.append(f"- Fused sequence: **{summary['fused_sequence_text']}**")
        lines.append("")
        cycles = summary.get("cycles", {})
        if cycles.get("has_cycle"):
            lines.append("Repeated fused cycles:")
            for cycle in cycles.get("cycles", [])[:5]:
                lines.append(
                    f"- {' -> '.join(cycle['pattern'])} ×{cycle['count']}"
                )
            lines.append("")
        lines.append("Fused event timeline:")
        lines.append("")
        lines.append(
            "| Center tick | Fused event | Raw events | Severity | "
            "Confidence | Family | Primary | Description |"
        )
        lines.append("|---:|---|---:|---:|---:|---|---|---|")
        for event in item.get("fused_events", []):
            lines.append(
                f"| {event['center_tick']} | {event['fused_event_type']} | "
                f"{event['raw_event_count']} | {fmt_float(event['severity'])} | "
                f"{fmt_float(event['confidence'])} | {event['family']} | "
                f"{event.get('primary_raw_event')} | {event['description']} |"
            )
        lines.append("")
    return "\n".join(lines)


def compact_events(report: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "schema": "universe_search_morphological_fused_events_v10",
        "results_dir": report.get("results_dir"),
        "rules_analyzed": report.get("rules_analyzed"),
        "fused_events": {},
    }
    for rule_id, item in report.get("rules", {}).items():
        compact["fused_events"][rule_id] = {
            "summary": item["summary"],
            "fused_events": item["fused_events"],
        }
    return compact


def render_compact_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Morphological Fused Events")
    lines.append("")
    lines.append(
        "| Rule | Archetype | Raw | Fused | Compression | Severity | "
        "Confidence | Sequence |"
    )
    lines.append("|---:|---|---:|---:|---:|---:|---:|---|")
    for rule_id, item in sorted(report.get("rules", {}).items()):
        summary = item["summary"]
        lines.append(
            f"| {rule_id} | {summary['fused_archetype']} | "
            f"{summary['raw_event_count']} | {summary['fused_event_count']} | "
            f"{fmt_float(summary['compression_ratio'])} | "
            f"{fmt_float(summary['mean_fused_severity'])} | "
            f"{fmt_float(summary['mean_fused_confidence'])} | "
            f"{summary['fused_sequence_text']} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_artifacts(report: dict[str, Any]) -> dict[str, str]:
    return {
        "morphological_event_fusion_report.json": json.dumps(
            report, ensure_ascii=False, indent=2
        ),
        "morphological_event_fusion_report.md": render_report_markdown(report),
        "morphological_fused_events.json": json.dumps(
            compact_events(report), ensure_ascii=False, indent=2
        ),
        "morphological_fused_events.md": render_compact_markdown(report),
    }

