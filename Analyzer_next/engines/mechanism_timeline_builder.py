"""Composition root for the modular mechanism-timeline builder."""
from __future__ import annotations

import time
from collections.abc import Callable

from Analyzer_next.adapters.mechanism_timeline.file_repository import (
    FileMechanismTimelineRepository,
)
from Analyzer_next.core.mechanism_timeline.contracts import (
    MechanismTimelineExecution,
    MechanismTimelineOptions,
    MechanismTimelinePaths,
    MechanismTimelineProgress,
    MechanismTimelineRepository,
)
from Analyzer_next.core.mechanism_timeline.orchestrator import (
    MechanismTimelineOrchestrator,
)


class MechanismTimelineBuilder:
    def __init__(
        self,
        repository: MechanismTimelineRepository | None = None,
        orchestrator: MechanismTimelineOrchestrator | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._repository = repository or FileMechanismTimelineRepository()
        self._orchestrator = orchestrator or MechanismTimelineOrchestrator()
        self._clock = clock

    def run(
        self,
        paths: MechanismTimelinePaths,
        options: MechanismTimelineOptions | None = None,
        progress: MechanismTimelineProgress | None = None,
    ) -> MechanismTimelineExecution:
        effective_options = options or MechanismTimelineOptions()
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(paths, inputs, progress)
        write_started = self._clock()
        self._repository.save(paths, result, effective_options)
        write_elapsed = self._clock() - write_started
        return MechanismTimelineExecution(
            result=result,
            output_writing_seconds=write_elapsed,
        )

