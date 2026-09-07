"""Composition root for Research Notebook Engine v4."""
from __future__ import annotations

from Analyzer_next.adapters.research_notebook.file_repository import (
    FileResearchNotebookRepository,
)
from Analyzer_next.core.research_notebook.contracts import (
    ResearchNotebookPaths,
    ResearchNotebookRepository,
    ResearchNotebookSaveResult,
)
from Analyzer_next.core.research_notebook.orchestrator import (
    ResearchNotebookOrchestrator,
)


class ResearchNotebookEngine:
    def __init__(
        self,
        repository: ResearchNotebookRepository | None = None,
        orchestrator: ResearchNotebookOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileResearchNotebookRepository()
        self._orchestrator = orchestrator or ResearchNotebookOrchestrator()

    def run(self, paths: ResearchNotebookPaths) -> ResearchNotebookSaveResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(inputs)
        return self._repository.save(paths, result)


__all__ = ["ResearchNotebookEngine"]
