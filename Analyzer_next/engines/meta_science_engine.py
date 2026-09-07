"""Composition root for modular Meta Science execution."""
from __future__ import annotations

from Analyzer_next.adapters.meta_science.file_repository import FileMetaScienceRepository
from Analyzer_next.core.meta_science.contracts import (
    MetaSciencePaths,
    MetaScienceRepository,
    MetaScienceRunResult,
)
from Analyzer_next.core.meta_science.orchestrator import MetaScienceOrchestrator


class MetaScienceEngine:
    def __init__(
        self,
        repository: MetaScienceRepository | None = None,
        orchestrator: MetaScienceOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileMetaScienceRepository()
        self._orchestrator = orchestrator or MetaScienceOrchestrator()

    def run(self, paths: MetaSciencePaths) -> MetaScienceRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result
