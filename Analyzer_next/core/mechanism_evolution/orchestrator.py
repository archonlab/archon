"""Compose deterministic mechanism-evolution projections in memory."""
from __future__ import annotations

from Analyzer_next.core.mechanism_evolution.analysis import (
    build_compact_report,
    build_evolution_report,
)
from Analyzer_next.core.mechanism_evolution.contracts import (
    MechanismEvolutionInputs,
    MechanismEvolutionPaths,
    MechanismEvolutionRunResult,
)


class MechanismEvolutionOrchestrator:
    def run(
        self,
        paths: MechanismEvolutionPaths,
        inputs: MechanismEvolutionInputs,
    ) -> MechanismEvolutionRunResult:
        evolution_graph = build_evolution_report(
            inputs.mechanism_registry,
            inputs.template_registry,
            inputs.instance_registry,
            inputs.template_rule_map,
            paths.results_root,
        )
        report = build_compact_report(evolution_graph, paths.results_root)
        return MechanismEvolutionRunResult(
            evolution_graph=evolution_graph,
            report=report,
        )
