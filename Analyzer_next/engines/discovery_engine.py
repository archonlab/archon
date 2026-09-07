"""Composition root for the modular Discovery Engine."""
from __future__ import annotations

from Analyzer_next.adapters.discovery.file_repository import (
    FileDiscoveryRepository,
)
from Analyzer_next.core.discovery.contracts import (
    DiscoveryPaths,
    DiscoveryRepository,
    DiscoveryRunResult,
)
from Analyzer_next.core.discovery.orchestrator import DiscoveryOrchestrator


class DiscoveryEngine:
    def __init__(
        self,
        repository: DiscoveryRepository | None = None,
        orchestrator: DiscoveryOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileDiscoveryRepository()
        self._orchestrator = orchestrator or DiscoveryOrchestrator()

    def run(self, paths: DiscoveryPaths) -> DiscoveryRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(inputs)
        self._repository.save(paths, result)
        return result
