"""Composition root for the modular mechanism-evolution graph."""
from __future__ import annotations

from Analyzer_next.adapters.mechanism_evolution.file_repository import (
    FileMechanismEvolutionRepository,
)
from Analyzer_next.core.mechanism_evolution.contracts import (
    MechanismEvolutionPaths,
    MechanismEvolutionRepository,
    MechanismEvolutionRunResult,
)
from Analyzer_next.core.mechanism_evolution.orchestrator import (
    MechanismEvolutionOrchestrator,
)


class MechanismEvolutionGraph:
    def __init__(
        self,
        repository: MechanismEvolutionRepository | None = None,
        orchestrator: MechanismEvolutionOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileMechanismEvolutionRepository()
        self._orchestrator = orchestrator or MechanismEvolutionOrchestrator()

    def run(
        self,
        paths: MechanismEvolutionPaths,
    ) -> MechanismEvolutionRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result
