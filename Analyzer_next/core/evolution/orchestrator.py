"""Aggregate per-run life cycles and build the evolution output bundle."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from Analyzer_next.core.evolution.contracts import (
    EvolutionInputs,
    EvolutionPaths,
    EvolutionRunResult,
)
from Analyzer_next.core.evolution.reporting import render_artifacts


def slim_rules(
    items: list[dict[str, Any]], metric: str
) -> list[dict[str, Any]]:
    output = []
    for rule in items:
        output.append({
            "rule_id": rule["rule_id"],
            "archetype": rule["life_cycle_archetype"],
            "dominant_stage": rule["dominant_stage"],
            "observed_ticks": rule["observed_ticks"],
            metric: rule["indices"].get(metric),
            "signature": rule["life_cycle_signature_text"],
        })
    return output


def build_report(
    paths: EvolutionPaths, inputs: EvolutionInputs
) -> dict[str, Any]:
    items = [item for item in inputs.summaries if item]
    by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_rule[item["rule_id"]].append(item)
    rules = []
    for rule_id, runs in sorted(by_rule.items()):
        best = max(
            runs,
            key=lambda run: (
                run.get("observed_ticks", 0), run.get("samples", 0)
            ),
        )
        rules.append({
            "rule_id": rule_id,
            "run_count": len(runs),
            "best_run": best,
            "runs": runs,
        })
    best_runs = [rule["best_run"] for rule in rules]
    archetypes = Counter(
        rule["life_cycle_archetype"] for rule in best_runs
    )
    dominant_stages = Counter(rule["dominant_stage"] for rule in best_runs)
    rankings = {
        "most_stable_life_cycles": (
            "life_cycle_stability",
            sorted(
                best_runs,
                key=lambda rule: rule["indices"]["life_cycle_stability"],
                reverse=True,
            )[:10],
        ),
        "most_complex_life_cycles": (
            "life_cycle_complexity",
            sorted(
                best_runs,
                key=lambda rule: rule["indices"]["life_cycle_complexity"],
                reverse=True,
            )[:10],
        ),
        "most_collapse_resistant": (
            "collapse_resistance",
            sorted(
                best_runs,
                key=lambda rule: rule["indices"]["collapse_resistance"],
                reverse=True,
            )[:10],
        ),
        "most_reconfiguring": (
            "reconfiguration_frequency",
            sorted(
                best_runs,
                key=lambda rule: rule["indices"]["reconfiguration_frequency"],
                reverse=True,
            )[:10],
        ),
        "strongest_growth_persistence": (
            "growth_persistence",
            sorted(
                best_runs,
                key=lambda rule: rule["indices"]["growth_persistence"],
                reverse=True,
            )[:10],
        ),
    }
    global_report: dict[str, Any] = {
        "archetype_counts": dict(archetypes),
        "dominant_stage_counts": dict(dominant_stages),
    }
    for key, (metric, ranked) in rankings.items():
        global_report[key] = slim_rules(ranked, metric)
    return {
        "schema": "universe_search_morphological_evolution_report_v10",
        "results_dir": str(paths.results_dir),
        "csv_files_found": inputs.csv_files_found,
        "rules_analyzed": len(rules),
        "errors": inputs.errors,
        "global": global_report,
        "rules": rules,
    }


class EvolutionOrchestrator:
    def run(
        self, paths: EvolutionPaths, inputs: EvolutionInputs
    ) -> EvolutionRunResult:
        report = build_report(paths, inputs)
        return EvolutionRunResult(
            report=report,
            artifacts=render_artifacts(report),
            incremental=inputs.incremental,
            elapsed_seconds=inputs.elapsed_seconds,
        )

