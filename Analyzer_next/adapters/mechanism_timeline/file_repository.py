"""Filesystem boundary and legacy-compatible timeline rendering."""
from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from Analyzer_next.core.mechanism_timeline.analysis import timeline_node_label
from Analyzer_next.core.mechanism_timeline.contracts import (
    MechanismTimelineInputs,
    MechanismTimelineOptions,
    MechanismTimelinePaths,
    MechanismTimelineRunResult,
)


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def load_sources(results_dir: Path) -> MechanismTimelineInputs:
    required = {
        "fused": results_dir / "morphological_fused_events.json",
        "mechanism_registry": results_dir / "mechanism_registry.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required files:\n" + "\n".join(missing)
        )
    return MechanismTimelineInputs(
        fused=load_json_if_exists(required["fused"]),
        mechanism_registry=load_json_if_exists(
            required["mechanism_registry"]
        ),
        composition_templates=load_json_if_exists(
            results_dir / "composition_templates.json"
        ),
        composition_instances=load_json_if_exists(
            results_dir / "composition_instances.json"
        ),
        composition_registry=load_json_if_exists(
            results_dir / "composition_registry.json"
        ),
        causal_motifs=load_json_if_exists(
            results_dir / "causal_motifs.json"
        ),
        causal_mechanisms=load_json_if_exists(
            results_dir / "causal_mechanisms.json"
        ),
    )


def write_json(path: Path, data: Any, *, pretty: bool = False) -> None:
    """Write JSON atomically without constructing one giant string."""
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", dir=path.parent
    )
    try:
        with os.fdopen(
            file_descriptor, "w", encoding="utf-8"
        ) as handle:
            json.dump(
                data,
                handle,
                ensure_ascii=False,
                indent=2 if pretty else None,
                separators=None if pretty else (",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def write_events_csv(timeline: dict[str, Any], path: Path) -> None:
    fields = [
        "rule_id", "timeline_event_id", "kind",
        "start_tick", "center_tick", "end_tick", "duration_ticks",
        "mechanism_id", "mechanism_label", "mechanism_category",
        "template_id", "template_label",
        "composition_id", "composition_label",
        "family_transition",
        "source_fused_event_ids",
        "source_fused_event_types",
        "severity", "confidence",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rule_id, rule in sorted(timeline.get("rules", {}).items()):
            for event in rule.get("timeline_events", []):
                row = {key: event.get(key) for key in fields}
                row["source_fused_event_ids"] = "|".join(
                    str(value)
                    for value in event.get("source_fused_event_ids", [])
                )
                row["source_fused_event_types"] = "|".join(
                    str(value)
                    for value in event.get("source_fused_event_types", [])
                )
                writer.writerow(row)


def fmt_float(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.000"


def write_timeline_md(timeline: dict[str, Any], path: Path) -> None:
    lines = [
        "# Mechanism Timeline v1.0",
        "",
        f"Rules: **{timeline.get('rule_count', 0)}**",
        "Timeline events: "
        f"**{timeline.get('global_summary', {}).get('timeline_event_count', 0)}**",
        "",
    ]
    for rule_id, rule in sorted(timeline.get("rules", {}).items()):
        summary = rule["summary"]
        lines.extend([
            f"## Rule {rule_id}",
            "",
            f"- Fused events: **{rule['fused_event_count']}**",
            f"- Timeline events: **{rule['timeline_event_count']}**",
            f"- Atomic events: **{summary['atomic_event_count']}**",
            f"- Template events: **{summary['template_event_count']}**",
            f"- Dominant category: **{summary['dominant_category']}**",
            "- Mean transition delay: "
            f"**{fmt_float(summary['mean_transition_delay_ticks'])}** ticks",
            "",
            "| Tick | Kind | Label | Family transition | Duration | Confidence | Sources |",
            "|---:|---|---|---|---:|---:|---|",
        ])
        for event in rule.get("timeline_events", []):
            label = timeline_node_label(event)
            lines.append(
                f"| {event['center_tick']} | {event['kind']} | {label} | "
                f"{event.get('family_transition')} | {event['duration_ticks']} | "
                f"{fmt_float(event.get('confidence'))} | "
                f"{', '.join(str(value) for value in event.get('source_fused_event_ids', []))} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_transitions_md(timeline: dict[str, Any], path: Path) -> None:
    transitions = timeline.get("global_transitions", {})
    lines = [
        "# Mechanism Timeline Transitions v1.0",
        "",
        f"Nodes: **{transitions.get('node_count', 0)}**",
        f"Edges: **{transitions.get('edge_count', 0)}**",
        "",
        "## Top transitions",
        "",
        "| Source | Target | Count | Rules | P | Mean delay | Strength |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for edge in transitions.get("top_edges", [])[:30]:
        lines.append(
            f"| {edge['source']} | {edge['target']} | {edge['count']} | "
            f"{edge['rule_count']} | {fmt_float(edge['probability_from_source'])} | "
            f"{fmt_float(edge['mean_delay_ticks'])} | "
            f"{fmt_float(edge['transition_strength'])} |"
        )
    lines.extend([
        "",
        "## Top nodes",
        "",
        "| Node | Count | In | Out | In degree | Out degree | Centrality |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for node in transitions.get("top_nodes", [])[:30]:
        lines.append(
            f"| {node['node']} | {node['count']} | {node['incoming_count']} | "
            f"{node['outgoing_count']} | {node['in_degree']} | "
            f"{node['out_degree']} | {fmt_float(node['centrality_score'])} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report_md(report: dict[str, Any], path: Path) -> None:
    summary = report.get("global_summary", {})
    lines = [
        "# Mechanism Timeline Report v1.0",
        "",
        f"Rules: **{report.get('rule_count', 0)}**",
        f"Timeline events: **{summary.get('timeline_event_count', 0)}**",
        "Mean timeline events per rule: "
        f"**{fmt_float(summary.get('mean_timeline_events_per_rule'))}**",
        "Mean transition delay: "
        f"**{fmt_float(summary.get('mean_transition_delay_ticks'))}** ticks",
        "",
        "## Top mechanisms",
        "",
        "| Mechanism | Count |",
        "|---|---:|",
    ]
    for name, count in summary.get("top_mechanisms", [])[:12]:
        lines.append(f"| {name} | {count} |")
    lines.extend([
        "",
        "## Top templates",
        "",
        "| Template | Count |",
        "|---|---:|",
    ])
    for name, count in summary.get("top_templates", [])[:12]:
        lines.append(f"| {name} | {count} |")
    lines.extend([
        "",
        "## Strongest timeline transitions",
        "",
        "| Source | Target | Count | Rules | Mean delay | Strength |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for edge in report.get("top_transition_edges", [])[:12]:
        lines.append(
            f"| {edge['source']} | {edge['target']} | {edge['count']} | "
            f"{edge['rule_count']} | {fmt_float(edge['mean_delay_ticks'])} | "
            f"{fmt_float(edge['transition_strength'])} |"
        )
    lines.extend([
        "",
        "## Rule summaries",
        "",
        "| Rule | Events | Atomic | Templates | Dominant category | Mean delay | Density |",
        "|---:|---:|---:|---:|---|---:|---:|",
    ])
    for rule_id, rule_summary in sorted(
        report.get("rule_summaries", {}).items()
    ):
        event_count = (
            rule_summary.get("atomic_event_count", 0)
            + rule_summary.get("template_event_count", 0)
        )
        lines.append(
            f"| {rule_id} | {event_count} | "
            f"{rule_summary.get('atomic_event_count', 0)} | "
            f"{rule_summary.get('template_event_count', 0)} | "
            f"{rule_summary.get('dominant_category')} | "
            f"{fmt_float(rule_summary.get('mean_transition_delay_ticks'))} | "
            f"{fmt_float(rule_summary.get('timeline_density'))} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    result: MechanismTimelineRunResult,
    results_dir: Path,
    options: MechanismTimelineOptions,
) -> None:
    timeline = result.timeline
    write_json(
        results_dir / "mechanism_timeline.json",
        timeline,
        pretty=options.pretty_json,
    )
    if options.write_full_md:
        write_timeline_md(
            timeline, results_dir / "mechanism_timeline.md"
        )
    write_events_csv(timeline, results_dir / "mechanism_events.csv")
    transitions_payload = {
        "schema": "universe_search_mechanism_timeline_transitions_v10",
        "results_dir": str(results_dir),
        "global_transitions": timeline.get("global_transitions", {}),
        "rule_transitions": {
            rule_id: rule.get("transitions", [])
            for rule_id, rule in timeline.get("rules", {}).items()
        },
    }
    write_json(
        results_dir / "mechanism_transitions.json",
        transitions_payload,
        pretty=options.pretty_json,
    )
    write_transitions_md(
        timeline, results_dir / "mechanism_transitions.md"
    )
    write_json(
        results_dir / "mechanism_timeline_report.json",
        result.report,
        pretty=options.pretty_json,
    )
    write_report_md(
        result.report, results_dir / "mechanism_timeline_report.md"
    )


class FileMechanismTimelineRepository:
    def load(
        self,
        paths: MechanismTimelinePaths,
    ) -> MechanismTimelineInputs:
        return load_sources(paths.results_root)

    def save(
        self,
        paths: MechanismTimelinePaths,
        result: MechanismTimelineRunResult,
        options: MechanismTimelineOptions,
    ) -> None:
        write_outputs(result, paths.results_root, options)
