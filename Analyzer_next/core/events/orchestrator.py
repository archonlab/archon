"""Aggregate per-run events and build the stage output bundle."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from Analyzer_next.core.events.contracts import (
    EventInputs,
    EventPaths,
    EventRunResult,
)
from Analyzer_next.core.events.reporting import render_artifacts


def slim_rules(items: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    output = []
    for rule in items:
        summary = rule["event_summary"]
        output.append({
            "rule_id": rule["rule_id"],
            "archetype": summary["event_archetype"],
            "observed_ticks": rule["observed_ticks"],
            metric: summary.get(metric),
            "total_events": summary["total_events"],
            "event_sequence": summary["event_sequence_text"],
        })
    return output


def build_report(paths: EventPaths, inputs: EventInputs) -> dict[str, Any]:
    items = [item for item in inputs.summaries if item]
    by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_rule[item["rule_id"]].append(item)
    rules = []
    for rule_id, runs in sorted(by_rule.items()):
        best = max(
            runs,
            key=lambda run: (run.get("observed_ticks", 0), run.get("samples", 0)),
        )
        rules.append({
            "rule_id": rule_id,
            "run_count": len(runs),
            "best_run": best,
            "runs": runs,
        })
    best_runs = [rule["best_run"] for rule in rules]
    archetypes = Counter(
        run["event_summary"]["event_archetype"] for run in best_runs
    )
    all_event_counts: Counter = Counter()
    all_family_counts: Counter = Counter()
    for run in best_runs:
        all_event_counts.update(run["event_summary"]["event_counts"])
        all_family_counts.update(run["event_summary"]["event_family_counts"])
    rankings = {
        "most_eventful_rules": (
            "total_events",
            sorted(
                best_runs,
                key=lambda run: run["event_summary"]["total_events"],
                reverse=True,
            )[:10],
        ),
        "most_intense_event_arcs": (
            "event_intensity",
            sorted(
                best_runs,
                key=lambda run: run["event_summary"]["event_intensity"],
                reverse=True,
            )[:10],
        ),
        "most_diverse_event_arcs": (
            "event_diversity",
            sorted(
                best_runs,
                key=lambda run: run["event_summary"]["event_diversity"],
                reverse=True,
            )[:10],
        ),
        "most_constructive_event_arcs": (
            "constructive_events",
            sorted(
                best_runs,
                key=lambda run: run["event_summary"]["constructive_events"],
                reverse=True,
            )[:10],
        ),
        "most_disruptive_event_arcs": (
            "destructive_events",
            sorted(
                best_runs,
                key=lambda run: run["event_summary"]["destructive_events"],
                reverse=True,
            )[:10],
        ),
        "most_reorganizational_event_arcs": (
            "reorganization_events",
            sorted(
                best_runs,
                key=lambda run: run["event_summary"]["reorganization_events"],
                reverse=True,
            )[:10],
        ),
    }
    global_report = {
        "event_archetype_counts": dict(archetypes),
        "event_counts": dict(all_event_counts),
        "event_family_counts": dict(all_family_counts),
    }
    for key, (metric, runs) in rankings.items():
        global_report[key] = slim_rules(runs, metric)
    return {
        "schema": "universe_search_morphological_event_report_v10",
        "results_dir": str(paths.results_dir),
        "csv_files_found": inputs.csv_files_found,
        "rules_analyzed": len(rules),
        "errors": inputs.errors,
        "global": global_report,
        "rules": rules,
    }


class EventOrchestrator:
    def run(self, paths: EventPaths, inputs: EventInputs) -> EventRunResult:
        report = build_report(paths, inputs)
        return EventRunResult(
            report=report,
            artifacts=render_artifacts(report),
            incremental=inputs.incremental,
            elapsed_seconds=inputs.elapsed_seconds,
        )

