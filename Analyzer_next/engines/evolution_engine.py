"""Composition root for modular morphological evolution analysis."""
from __future__ import annotations

import gc

from Analyzer_next.adapters.evolution.file_repository import (
    FileEvolutionArtifactRepository,
    FileEvolutionSource,
)
from Analyzer_next.core.evolution.analysis import analyze_rows
from Analyzer_next.core.evolution.contracts import (
    EvolutionArtifactRepository,
    EvolutionPaths,
    EvolutionRunResult,
    EvolutionSource,
)
from Analyzer_next.core.evolution.orchestrator import EvolutionOrchestrator


class EvolutionEngine:
    def __init__(
        self,
        source: EvolutionSource | None = None,
        repository: EvolutionArtifactRepository | None = None,
        orchestrator: EvolutionOrchestrator | None = None,
    ) -> None:
        self._source = source or FileEvolutionSource()
        self._repository = repository or FileEvolutionArtifactRepository()
        self._orchestrator = orchestrator or EvolutionOrchestrator()

    def run(self, paths: EvolutionPaths) -> EvolutionRunResult:
        inputs = self._source.collect(paths, analyze_rows)
        if not inputs.errors:
            print(
                "[incremental] "
                f"new={inputs.incremental['new']} "
                f"changed={inputs.incremental['changed']} "
                f"reused={inputs.incremental['reused']} "
                f"removed={inputs.incremental['removed']} "
                f"elapsed={inputs.elapsed_seconds:.2f}s",
                flush=True,
            )
        gc.collect()
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result

