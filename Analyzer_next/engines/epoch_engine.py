"""Composition root for modular morphological epoch detection."""
from __future__ import annotations

import gc

from Analyzer_next.adapters.epochs.file_repository import (
    FileEpochArtifactRepository,
    FileEpochSource,
)
from Analyzer_next.core.epochs.analysis import analyze_rows
from Analyzer_next.core.epochs.contracts import (
    EpochArtifactRepository,
    EpochPaths,
    EpochRunResult,
    EpochSource,
)
from Analyzer_next.core.epochs.orchestrator import EpochOrchestrator


class EpochEngine:
    def __init__(
        self,
        source: EpochSource | None = None,
        repository: EpochArtifactRepository | None = None,
        orchestrator: EpochOrchestrator | None = None,
    ) -> None:
        self._source = source or FileEpochSource()
        self._repository = repository or FileEpochArtifactRepository()
        self._orchestrator = orchestrator or EpochOrchestrator()

    def run(self, paths: EpochPaths) -> EpochRunResult:
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

