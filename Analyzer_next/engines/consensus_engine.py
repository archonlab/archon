"""Composition root for modular Consensus execution."""
from __future__ import annotations

from Analyzer_next.adapters.consensus.file_repository import FileConsensusRepository
from Analyzer_next.core.consensus.contracts import (
    ConsensusPaths,
    ConsensusRepository,
    ConsensusRunResult,
)
from Analyzer_next.core.consensus.orchestrator import ConsensusOrchestrator


class ConsensusEngine:
    def __init__(
        self,
        repository: ConsensusRepository | None = None,
        orchestrator: ConsensusOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileConsensusRepository()
        self._orchestrator = orchestrator or ConsensusOrchestrator()

    def run(self, paths: ConsensusPaths) -> ConsensusRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result
