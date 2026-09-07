"""Composition root for modular Prediction Validation Engine v2.3."""
from __future__ import annotations

from Analyzer_next.adapters.prediction_validation.file_repository import (
    FilePredictionValidationRepository,
)
from Analyzer_next.core.prediction_validation.contracts import (
    PredictionValidationPaths,
    PredictionValidationRepository,
    PredictionValidationRunResult,
)
from Analyzer_next.core.prediction_validation.orchestrator import (
    PredictionValidationOrchestrator,
)


class PredictionValidationEngine:
    def __init__(
        self,
        repository: PredictionValidationRepository | None = None,
        orchestrator: PredictionValidationOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FilePredictionValidationRepository()
        self._orchestrator = orchestrator or PredictionValidationOrchestrator()

    def run(self, paths: PredictionValidationPaths) -> PredictionValidationRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(inputs)
        if inputs.predictions:
            self._repository.save(paths, result)
        return result


__all__ = ["PredictionValidationEngine"]
