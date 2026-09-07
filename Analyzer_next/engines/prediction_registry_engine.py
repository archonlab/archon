"""Composition root for persistent Prediction Engine v2."""
from __future__ import annotations

from Analyzer_next.adapters.prediction_registry.file_repository import (
    FilePredictionRegistryRepository,
)
from Analyzer_next.core.prediction_registry.contracts import (
    PredictionRegistryPaths,
    PredictionRegistryRepository,
    PredictionRegistryRunResult,
)
from Analyzer_next.core.prediction_registry.orchestrator import (
    PredictionRegistryOrchestrator,
)


class PredictionRegistryEngine:
    def __init__(
        self,
        repository: PredictionRegistryRepository | None = None,
        orchestrator: PredictionRegistryOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FilePredictionRegistryRepository()
        self._orchestrator = orchestrator or PredictionRegistryOrchestrator()

    def run(self, paths: PredictionRegistryPaths) -> PredictionRegistryRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(inputs)
        self._repository.save(paths, result)
        return result


__all__ = ["PredictionRegistryEngine"]
