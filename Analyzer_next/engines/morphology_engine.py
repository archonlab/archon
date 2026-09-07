"""Composition root for modular morphology analysis."""
from __future__ import annotations

import gc

from Analyzer_next.adapters.morphology.file_repository import (
    FileMorphologyArtifactRepository,
    FileMorphologySource,
)
from Analyzer_next.core.morphology.contracts import (
    MorphologyArtifactRepository,
    MorphologyPaths,
    MorphologyRunResult,
    MorphologySource,
)
from Analyzer_next.core.morphology.orchestrator import MorphologyOrchestrator
from Analyzer_next.core.morphology.summarization import summarize_rows


class MorphologyEngine:
    def __init__(
        self,
        source: MorphologySource | None = None,
        repository: MorphologyArtifactRepository | None = None,
        orchestrator: MorphologyOrchestrator | None = None,
    ) -> None:
        self._source = source or FileMorphologySource()
        self._repository = repository or FileMorphologyArtifactRepository()
        self._orchestrator = orchestrator or MorphologyOrchestrator()

    def run(self, paths: MorphologyPaths, *, top_n: int = 5) -> MorphologyRunResult:
        inputs = self._source.collect(paths, summarize_rows)
        print(
            "[incremental] "
            f"new={inputs.incremental['new']} changed={inputs.incremental['changed']} "
            f"reused={inputs.incremental['reused']} removed={inputs.incremental['removed']} "
            f"elapsed={inputs.elapsed_seconds:.2f}s",
            flush=True,
        )
        gc.collect()
        result = self._orchestrator.run(paths, inputs, top_n=top_n)
        self._repository.save(paths, result)
        return result
