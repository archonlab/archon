"""Composition root for Research Notebook Index v1."""
from __future__ import annotations

from Analyzer_next.adapters.research_notebook_index.file_repository import (
    FileResearchNotebookIndexRepository,
)
from Analyzer_next.core.research_notebook_index.contracts import (
    ResearchNotebookIndexPaths,
    ResearchNotebookIndexRepository,
    ResearchNotebookIndexSaveResult,
)
from Analyzer_next.core.research_notebook_index.orchestrator import (
    ResearchNotebookIndexOrchestrator,
)


class ResearchNotebookIndexEngine:
    def __init__(
        self,
        repository: ResearchNotebookIndexRepository | None = None,
        orchestrator: ResearchNotebookIndexOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileResearchNotebookIndexRepository()
        self._orchestrator = orchestrator or ResearchNotebookIndexOrchestrator()

    def run(
        self,
        paths: ResearchNotebookIndexPaths,
    ) -> ResearchNotebookIndexSaveResult:
        inputs = self._repository.load(paths)
        artifact = self._orchestrator.run(inputs)
        return self._repository.save(paths, artifact)


__all__ = ["ResearchNotebookIndexEngine"]
