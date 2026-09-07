"""Composition root for Experiment Planner Engine v4.4."""
from __future__ import annotations

from Analyzer_next.adapters.experiment_planner.file_repository import (
    FileExperimentPlannerRepository,
)
from Analyzer_next.core.experiment_planner.contracts import (
    ExperimentPlannerPaths,
    ExperimentPlannerRepository,
    ExperimentPlannerSaveResult,
)
from Analyzer_next.core.experiment_planner.orchestrator import (
    ExperimentPlannerOrchestrator,
)


class ExperimentPlannerEngine:
    def __init__(
        self,
        repository: ExperimentPlannerRepository | None = None,
        orchestrator: ExperimentPlannerOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileExperimentPlannerRepository()
        self._orchestrator = orchestrator or ExperimentPlannerOrchestrator()

    def run(self, paths: ExperimentPlannerPaths) -> ExperimentPlannerSaveResult:
        inputs = self._repository.load(paths)
        artifact = self._orchestrator.run(inputs)
        return self._repository.save(paths, artifact)


__all__ = ["ExperimentPlannerEngine"]
