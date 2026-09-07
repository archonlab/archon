"""Filesystem repository for Research Notebook Index v1."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from Analyzer_next.core.research_notebook_index.contracts import (
    ResearchNotebookDocument,
    ResearchNotebookIndexArtifact,
    ResearchNotebookIndexInputs,
    ResearchNotebookIndexPaths,
    ResearchNotebookIndexSaveResult,
)


class ResearchNotebookIndexInputError(RuntimeError):
    """Expected input is missing from the ResearchNotebook directory."""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class FileResearchNotebookIndexRepository:
    def load(
        self,
        paths: ResearchNotebookIndexPaths,
    ) -> ResearchNotebookIndexInputs:
        notebook_dir = paths.results_folder / "ResearchNotebook"
        if not notebook_dir.exists():
            raise ResearchNotebookIndexInputError(
                f"ResearchNotebook folder not found: {notebook_dir}"
            )
        files = sorted(notebook_dir.glob("experiment_*.md"))
        if not files:
            raise ResearchNotebookIndexInputError(
                f"No experiment_*.md files found in {notebook_dir}"
            )
        return ResearchNotebookIndexInputs(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            documents=tuple(
                ResearchNotebookDocument(
                    filename=path.name,
                    text=read_text(path),
                )
                for path in files
            ),
        )

    def save(
        self,
        paths: ResearchNotebookIndexPaths,
        artifact: ResearchNotebookIndexArtifact,
    ) -> ResearchNotebookIndexSaveResult:
        notebook_dir = paths.results_folder / "ResearchNotebook"
        output_path = notebook_dir / "index.md"
        output_path.write_text(artifact.markdown, encoding="utf-8")
        return ResearchNotebookIndexSaveResult(
            artifact=artifact,
            notebook_dir=notebook_dir,
            output_path=output_path,
        )


__all__ = [
    "FileResearchNotebookIndexRepository",
    "ResearchNotebookIndexInputError",
    "read_text",
]
