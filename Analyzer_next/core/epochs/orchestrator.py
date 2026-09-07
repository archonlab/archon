"""Aggregate per-run epochs and render the stage output bundle."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from Analyzer_next.core.epochs.contracts import (
    EpochInputs,
    EpochPaths,
    EpochRunResult,
)
from Analyzer_next.core.epochs.reporting import render_artifacts


def slim_rules(items: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    output = []
    for rule in items:
        output.append({
            "rule_id": rule["rule_id"],
            "archetype": rule["epoch_archetype"],
            "observed_ticks": rule["observed_ticks"],
            metric: rule["indices"].get(metric),
            "epoch_count": rule["indices"].get("epoch_count"),
            "signature": rule["epoch_signature_text"],
        })
    return output


def build_report(paths: EpochPaths, inputs: EpochInputs) -> dict[str, Any]:
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
    archetypes = Counter(run["epoch_archetype"] for run in best_runs)
    most_complex = sorted(
        best_runs,
        key=lambda run: run["indices"]["epoch_complexity"],
        reverse=True,
    )[:10]
    most_stable = sorted(
        best_runs,
        key=lambda run: run["indices"]["epoch_stability"],
        reverse=True,
    )[:10]
    most_reconfiguring = sorted(
        best_runs,
        key=lambda run: run["indices"]["epoch_reconfiguration_ratio"],
        reverse=True,
    )[:10]
    strongest_growth = sorted(
        best_runs,
        key=lambda run: run["indices"]["epoch_growth_ratio"],
        reverse=True,
    )[:10]
    strongest_decay = sorted(
        best_runs,
        key=lambda run: run["indices"]["epoch_decay_ratio"],
        reverse=True,
    )[:10]
    return {
        "schema": "universe_search_morphological_epoch_report_v10",
        "results_dir": str(paths.results_dir),
        "csv_files_found": inputs.csv_files_found,
        "rules_analyzed": len(rules),
        "errors": inputs.errors,
        "global": {
            "epoch_archetype_counts": dict(archetypes),
            "most_complex_epoch_arcs": slim_rules(most_complex, "epoch_complexity"),
            "most_stable_epoch_arcs": slim_rules(most_stable, "epoch_stability"),
            "most_reconfiguring_epoch_arcs": slim_rules(
                most_reconfiguring, "epoch_reconfiguration_ratio"
            ),
            "strongest_growth_epoch_arcs": slim_rules(
                strongest_growth, "epoch_growth_ratio"
            ),
            "strongest_decay_epoch_arcs": slim_rules(
                strongest_decay, "epoch_decay_ratio"
            ),
        },
        "rules": rules,
    }


class EpochOrchestrator:
    def run(self, paths: EpochPaths, inputs: EpochInputs) -> EpochRunResult:
        report = build_report(paths, inputs)
        return EpochRunResult(
            report=report,
            artifacts=render_artifacts(report),
            incremental=inputs.incremental,
            elapsed_seconds=inputs.elapsed_seconds,
        )

