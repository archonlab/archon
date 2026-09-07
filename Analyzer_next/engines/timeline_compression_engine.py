"""Composition root for the modular Timeline Compression Engine."""
from __future__ import annotations

from Analyzer_next.adapters.timeline_compression.file_repository import (
    FileTimelineCompressionRepository,
)
from Analyzer_next.core.timeline_compression.contracts import (
    TimelineCompressionPaths,
    TimelineCompressionRepository,
    TimelineCompressionRunResult,
)
from Analyzer_next.core.timeline_compression.orchestrator import (
    TimelineCompressionOrchestrator,
)


class TimelineCompressionEngine:
    def __init__(
        self,
        repository: TimelineCompressionRepository | None = None,
        orchestrator: TimelineCompressionOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileTimelineCompressionRepository()
        self._orchestrator = orchestrator or TimelineCompressionOrchestrator()

    def run(
        self,
        paths: TimelineCompressionPaths,
    ) -> TimelineCompressionRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result
