"""Aggregate per-rule macro-events and build Fusion v1.0 reports."""
from __future__ import annotations

from collections import Counter
from typing import Any

from Analyzer_next.core.fusion.analysis import fuse_rule
from Analyzer_next.core.fusion.contracts import (
    FusionInputs,
    FusionPaths,
    FusionRunResult,
)
from Analyzer_next.core.fusion.reporting import render_artifacts


def slim_rules(
    items: list[dict[str, Any]], metric: str
) -> list[dict[str, Any]]:
    output = []
    for item in items:
        summary = item["summary"]
        output.append({
            "rule_id": item["rule_id"],
            "archetype": summary["fused_archetype"],
            metric: summary.get(metric),
            "raw_events": summary["raw_event_count"],
            "fused_events": summary["fused_event_count"],
            "sequence": summary["fused_sequence_text"],
        })
    return output


def build_report(paths: FusionPaths, inputs: FusionInputs) -> dict[str, Any]:
    source = inputs.event_source
    rules_payload = source.get("events", {})
    fused_rules = {
        rule_id: fuse_rule(rule_id, payload)
        for rule_id, payload in sorted(rules_payload.items())
    }
    all_counts: Counter = Counter()
    all_families: Counter = Counter()
    archetypes: Counter = Counter()
    for item in fused_rules.values():
        summary = item["summary"]
        all_counts.update(summary["fused_event_counts"])
        all_families.update(summary["fused_family_counts"])
        archetypes[summary["fused_archetype"]] += 1
    ranked = list(fused_rules.values())
    most_compressed = sorted(
        ranked, key=lambda item: item["summary"]["compression_ratio"]
    )[:10]
    most_fused = sorted(
        ranked,
        key=lambda item: item["summary"]["fused_event_count"],
        reverse=True,
    )[:10]
    most_severe = sorted(
        ranked,
        key=lambda item: item["summary"]["mean_fused_severity"],
        reverse=True,
    )[:10]
    most_constructive = sorted(
        ranked,
        key=lambda item: item["summary"]["constructive_fused_events"],
        reverse=True,
    )[:10]
    most_destructive = sorted(
        ranked,
        key=lambda item: item["summary"]["destructive_fused_events"],
        reverse=True,
    )[:10]
    most_reorganizational = sorted(
        ranked,
        key=lambda item: item["summary"]["reorganizational_fused_events"],
        reverse=True,
    )[:10]
    return {
        "schema": "universe_search_morphological_event_fusion_report_v10",
        "results_dir": str(paths.results_dir),
        "rules_analyzed": len(fused_rules),
        "source_schema": source.get("schema"),
        "global": {
            "fused_archetype_counts": dict(archetypes),
            "fused_event_counts": dict(all_counts),
            "fused_family_counts": dict(all_families),
            "most_compressed_rules": slim_rules(
                most_compressed, "compression_ratio"
            ),
            "most_fused_eventful_rules": slim_rules(
                most_fused, "fused_event_count"
            ),
            "most_severe_fused_arcs": slim_rules(
                most_severe, "mean_fused_severity"
            ),
            "most_constructive_fused_arcs": slim_rules(
                most_constructive, "constructive_fused_events"
            ),
            "most_destructive_fused_arcs": slim_rules(
                most_destructive, "destructive_fused_events"
            ),
            "most_reorganizational_fused_arcs": slim_rules(
                most_reorganizational, "reorganizational_fused_events"
            ),
        },
        "rules": fused_rules,
    }


class FusionOrchestrator:
    def run(self, paths: FusionPaths, inputs: FusionInputs) -> FusionRunResult:
        report = build_report(paths, inputs)
        return FusionRunResult(
            report=report,
            artifacts=render_artifacts(report),
        )

