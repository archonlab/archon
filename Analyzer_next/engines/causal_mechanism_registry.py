"""Composition root for the modular causal-mechanism registry."""
from __future__ import annotations

from Analyzer_next.adapters.causal_registry.file_repository import (
    FileCausalRegistryRepository,
)
from Analyzer_next.core.causal_registry.contracts import (
    CausalRegistryPaths,
    CausalRegistryRepository,
    CausalRegistryRunResult,
)
from Analyzer_next.core.causal_registry.orchestrator import (
    CausalRegistryOrchestrator,
)


class CausalMechanismRegistry:
    def __init__(
        self,
        repository: CausalRegistryRepository | None = None,
        orchestrator: CausalRegistryOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileCausalRegistryRepository()
        self._orchestrator = orchestrator or CausalRegistryOrchestrator()

    def run(self, paths: CausalRegistryPaths) -> CausalRegistryRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result
