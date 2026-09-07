"""Composition root for modular morphological event fusion."""
from __future__ import annotations

from Analyzer_next.adapters.fusion.file_repository import (
    FileFusionArtifactRepository,
    FileFusionSource,
)
from Analyzer_next.core.fusion.contracts import (
    FusionArtifactRepository,
    FusionPaths,
    FusionRunResult,
    FusionSource,
)
from Analyzer_next.core.fusion.orchestrator import FusionOrchestrator


class FusionEngine:
    def __init__(
        self,
        source: FusionSource | None = None,
        repository: FusionArtifactRepository | None = None,
        orchestrator: FusionOrchestrator | None = None,
    ) -> None:
        self._source = source or FileFusionSource()
        self._repository = repository or FileFusionArtifactRepository()
        self._orchestrator = orchestrator or FusionOrchestrator()

    def run(self, paths: FusionPaths) -> FusionRunResult:
        inputs = self._source.load(paths)
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result

