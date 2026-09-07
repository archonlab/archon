"""Pure orchestration for Research Notebook Index v1."""
from __future__ import annotations

from .contracts import (
    ResearchNotebookIndexArtifact,
    ResearchNotebookIndexInputs,
)
from .parsing import parse_notebook
from .reporting import render_index


class ResearchNotebookIndexOrchestrator:
    def run(
        self,
        inputs: ResearchNotebookIndexInputs,
    ) -> ResearchNotebookIndexArtifact:
        items = tuple(
            parse_notebook(document.filename, document.text)
            for document in inputs.documents
        )
        return ResearchNotebookIndexArtifact(
            items=items,
            markdown=render_index(list(items), inputs.generated_at),
        )


__all__ = ["ResearchNotebookIndexOrchestrator"]
