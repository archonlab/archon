"""Composition root for the modular Knowledge Base engine."""
from __future__ import annotations

from Analyzer_next.adapters.knowledge_base.file_repository import (
    FileKnowledgeBaseRepository,
)
from Analyzer_next.core.knowledge_base.contracts import (
    KnowledgeBasePaths,
    KnowledgeBaseRepository,
    KnowledgeBaseRunResult,
)
from Analyzer_next.core.knowledge_base.orchestrator import (
    KnowledgeBaseOrchestrator,
)


class KnowledgeBaseEngine:
    def __init__(
        self,
        repository: KnowledgeBaseRepository | None = None,
        orchestrator: KnowledgeBaseOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileKnowledgeBaseRepository()
        self._orchestrator = orchestrator or KnowledgeBaseOrchestrator()

    def run(self, paths: KnowledgeBasePaths) -> KnowledgeBaseRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result
