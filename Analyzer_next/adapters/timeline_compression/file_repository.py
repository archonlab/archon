"""Legacy-compatible JSON and Markdown repository for timeline compression."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from Analyzer_next.core.timeline_compression.analysis import event_label
from Analyzer_next.core.timeline_compression.contracts import (
    TimelineCompressionInputs,
    TimelineCompressionPaths,
    TimelineCompressionRunResult,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _fmt_float(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.000"


def _write_compressed_timeline_md(
    compression: dict[str, Any],
    path: Path,
) -> None:
    lines = []
    lines.append("# Compressed Timeline v1.0")
    lines.append("")
    summary = compression["global_summary"]
    lines.append(
        f"Raw events: **{summary['raw_timeline_event_count']}**"
    )
    lines.append(
        "Compressed events: "
        f"**{summary['compressed_timeline_event_count']}**"
    )
    lines.append(
        "Compression ratio: "
        f"**{_fmt_float(summary['global_compression_ratio'])}**"
    )
    lines.append("")
    for rule_id, rule in sorted(compression["rules"].items()):
        item = rule["summary"]
        lines.append(f"## Rule {rule_id}")
        lines.append("")
        lines.append(f"- Raw: **{item['raw_timeline_event_count']}**")
        lines.append(
            f"- Canonical: **{item['compressed_timeline_event_count']}**"
        )
        lines.append(
            f"- Compressed away: **{item['compressed_away_count']}**"
        )
        lines.append(
            "- Compression ratio: "
            f"**{_fmt_float(item['compression_ratio'])}**"
        )
        lines.append(f"- Segments: **{item['segment_count']}**")
        lines.append("")
        lines.append(
            "| Tick | Label | Kind | Family | Duration | Children | Score |"
        )
        lines.append("|---:|---|---|---|---:|---:|---:|")
        for event in rule["canonical_timeline_events"]:
            lines.append(
                f"| {event.get('center_tick')} | {event_label(event)} | "
                f"{event.get('kind')} | {event.get('family_transition')} | "
                f"{event.get('duration_ticks')} | "
                f"{len(event.get('child_timeline_event_ids', []))} | "
                f"{_fmt_float(event.get('compression_score'))} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_segments_md(
    compression: dict[str, Any],
    path: Path,
) -> None:
    lines = []
    lines.append("# Timeline Segments v1.0")
    lines.append("")
    for rule_id, rule in sorted(compression["rules"].items()):
        lines.append(f"## Rule {rule_id}")
        lines.append("")
        lines.append(
            "| Segment | Start | End | Duration | Events | "
            "Dominant category | Sequence |"
        )
        lines.append("|---|---:|---:|---:|---:|---|---|")
        for segment in rule["segments"]:
            lines.append(
                f"| {segment['segment_id']} | {segment['start_tick']} | "
                f"{segment['end_tick']} | {segment['duration_ticks']} | "
                f"{segment['event_count']} | "
                f"{segment['dominant_category']} | "
                f"{segment['sequence_text']} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_transitions_md(
    compression: dict[str, Any],
    path: Path,
) -> None:
    lines = []
    lines.append("# Compressed Timeline Transitions v1.0")
    lines.append("")
    transitions = compression["global_transitions"]
    lines.append(f"Nodes: **{transitions['node_count']}**")
    lines.append(f"Edges: **{transitions['edge_count']}**")
    lines.append("")
    lines.append(
        "| Source | Target | Count | Rules | P | Mean delay | Strength |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for edge in transitions["top_edges"]:
        lines.append(
            f"| {edge['source']} | {edge['target']} | {edge['count']} | "
            f"{edge['rule_count']} | "
            f"{_fmt_float(edge['probability_from_source'])} | "
            f"{_fmt_float(edge['mean_delay_ticks'])} | "
            f"{_fmt_float(edge['transition_strength'])} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_report_md(report: dict[str, Any], path: Path) -> None:
    lines = []
    lines.append("# Timeline Compression Report v1.0")
    lines.append("")
    summary = report["global_summary"]
    lines.append(
        f"Raw events: **{summary['raw_timeline_event_count']}**"
    )
    lines.append(
        "Canonical events: "
        f"**{summary['compressed_timeline_event_count']}**"
    )
    lines.append(
        f"Compressed away: **{summary['compressed_away_count']}**"
    )
    lines.append(
        "Global compression ratio: "
        f"**{_fmt_float(summary['global_compression_ratio'])}**"
    )
    lines.append(f"Segments: **{summary['segment_count']}**")
    lines.append("")
    lines.append("## Rule summaries")
    lines.append("")
    lines.append(
        "| Rule | Raw | Canonical | Removed | Ratio | Segments | "
        "Transitions | Dominant segment category |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---|")
    for rule_id, item in sorted(report["rule_summaries"].items()):
        lines.append(
            f"| {rule_id} | {item['raw_timeline_event_count']} | "
            f"{item['compressed_timeline_event_count']} | "
            f"{item['compressed_away_count']} | "
            f"{_fmt_float(item['compression_ratio'])} | "
            f"{item['segment_count']} | {item['transition_count']} | "
            f"{item['dominant_segment_category']} |"
        )
    lines.append("")
    lines.append("## Top compressed transitions")
    lines.append("")
    lines.append(
        "| Source | Target | Count | Rules | Mean delay | Strength |"
    )
    lines.append("|---|---|---:|---:|---:|---:|")
    for edge in report["top_compressed_transitions"][:12]:
        lines.append(
            f"| {edge['source']} | {edge['target']} | {edge['count']} | "
            f"{edge['rule_count']} | "
            f"{_fmt_float(edge['mean_delay_ticks'])} | "
            f"{_fmt_float(edge['transition_strength'])} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


class FileTimelineCompressionRepository:
    def load(
        self,
        paths: TimelineCompressionPaths,
    ) -> TimelineCompressionInputs:
        source = paths.results_root / "mechanism_timeline.json"
        if not source.exists():
            raise FileNotFoundError(f"Missing required file: {source}")
        return TimelineCompressionInputs(
            mechanism_timeline=json.loads(source.read_text(encoding="utf-8"))
        )

    def save(
        self,
        paths: TimelineCompressionPaths,
        result: TimelineCompressionRunResult,
    ) -> None:
        results_dir = paths.results_root
        compression = result.compression
        _write_json(results_dir / "compressed_timeline.json", compression)
        _write_compressed_timeline_md(
            compression,
            results_dir / "compressed_timeline.md",
        )
        segments_payload = {
            "schema": "universe_search_timeline_segments_v10",
            "results_dir": str(results_dir),
            "segments": {
                rule_id: rule["segments"]
                for rule_id, rule in compression["rules"].items()
            },
        }
        _write_json(results_dir / "timeline_segments.json", segments_payload)
        _write_segments_md(
            compression,
            results_dir / "timeline_segments.md",
        )
        transitions_payload = {
            "schema": "universe_search_compressed_transitions_v10",
            "results_dir": str(results_dir),
            "global_transitions": compression["global_transitions"],
            "rule_transitions": {
                rule_id: rule["compressed_transitions"]
                for rule_id, rule in compression["rules"].items()
            },
        }
        _write_json(
            results_dir / "compressed_transitions.json",
            transitions_payload,
        )
        _write_transitions_md(
            compression,
            results_dir / "compressed_transitions.md",
        )
        _write_json(
            results_dir / "timeline_compression_report.json",
            result.report,
        )
        _write_report_md(
            result.report,
            results_dir / "timeline_compression_report.md",
        )
