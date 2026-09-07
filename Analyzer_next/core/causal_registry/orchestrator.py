"""Compose deterministic registry projections entirely in memory."""
from __future__ import annotations

from Analyzer_next.core.causal_registry.contracts import (
    CausalRegistryInputs,
    CausalRegistryPaths,
    CausalRegistryRunResult,
)
from Analyzer_next.core.causal_registry.registry import (
    build_atomic_registry,
    build_composition_registry,
    build_report,
    build_rule_mechanism_map,
    collect_family_records,
)


class CausalRegistryOrchestrator:
    def run(
        self,
        paths: CausalRegistryPaths,
        inputs: CausalRegistryInputs,
    ) -> CausalRegistryRunResult:
        sources = inputs.sources
        records = collect_family_records(sources)
        atomic_registry = build_atomic_registry(records, paths.results_root)
        composition_registry = build_composition_registry(
            records, atomic_registry, paths.results_root
        )
        rule_map = build_rule_mechanism_map(
            sources,
            atomic_registry,
            composition_registry,
            paths.results_root,
        )
        report = build_report(
            atomic_registry,
            composition_registry,
            rule_map,
            paths.results_root,
        )
        return CausalRegistryRunResult(
            source_keys=tuple(sorted(sources)),
            atomic_registry=atomic_registry,
            composition_registry=composition_registry,
            rule_map=rule_map,
            report=report,
        )
