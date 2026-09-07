"""Composition root for modular morphological event detection."""
from __future__ import annotations

import gc

from Analyzer_next.adapters.events.file_repository import (
    FileEventArtifactRepository,
    FileEventSource,
)
from Analyzer_next.core.events.analysis import analyze_rows
from Analyzer_next.core.events.contracts import (
    EventArtifactRepository,
    EventPaths,
    EventRunResult,
    EventSource,
)
from Analyzer_next.core.events.orchestrator import EventOrchestrator


class EventEngine:
    def __init__(
        self,
        source: EventSource | None = None,
        repository: EventArtifactRepository | None = None,
        orchestrator: EventOrchestrator | None = None,
    ) -> None:
        self._source = source or FileEventSource()
        self._repository = repository or FileEventArtifactRepository()
        self._orchestrator = orchestrator or EventOrchestrator()

    def run(self, paths: EventPaths) -> EventRunResult:
        inputs = self._source.collect(paths, analyze_rows)
        if not inputs.errors:
            print(
                "[incremental] "
                f"new={inputs.incremental['new']} changed={inputs.incremental['changed']} "
                f"reused={inputs.incremental['reused']} removed={inputs.incremental['removed']} "
                f"elapsed={inputs.elapsed_seconds:.2f}s",
                flush=True,
            )
        gc.collect()
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result

