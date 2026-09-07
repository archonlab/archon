"""Composition root for modular mutation analysis."""
from __future__ import annotations

from Analyzer_next.adapters.ontology.lifecycle_adapter import ScientificOntologyLifecycleAdapter
from Analyzer_next.core.mutation.contracts import LifecycleReconciler, MutationRequest, MutationRunResult
from Analyzer_next.core.mutation.orchestrator import MutationOrchestrator


class MutationEngine:
    def __init__(self, lifecycle_reconciler: LifecycleReconciler | None = None) -> None:
        self._lifecycle_reconciler = lifecycle_reconciler or ScientificOntologyLifecycleAdapter()

    def run(self, request: MutationRequest) -> MutationRunResult:
        return MutationOrchestrator(self._lifecycle_reconciler).run(request)

