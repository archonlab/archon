"""Composition root for the modular Causal Graph Builder."""
from __future__ import annotations

from Analyzer_next.adapters.causal_graph.file_repository import (
    FileCausalGraphRepository,
)
from Analyzer_next.core.causal_graph.contracts import (
    CausalGraphPaths,
    CausalGraphRepository,
    CausalGraphRunResult,
)
from Analyzer_next.core.causal_graph.orchestrator import (
    CausalGraphOrchestrator,
)


class CausalGraphBuilder:
    def __init__(
        self,
        repository: CausalGraphRepository | None = None,
        orchestrator: CausalGraphOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileCausalGraphRepository()
        self._orchestrator = orchestrator or CausalGraphOrchestrator()

    def run(self, paths: CausalGraphPaths) -> CausalGraphRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result
