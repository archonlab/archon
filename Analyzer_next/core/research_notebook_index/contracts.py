"""Ports and immutable values for Research Notebook Index v1."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


Metric = int | float | str | None


@dataclass(frozen=True)
class ResearchNotebookIndexPaths:
    results_folder: Path


@dataclass(frozen=True)
class ResearchNotebookDocument:
    filename: str
    text: str


@dataclass(frozen=True)
class ResearchNotebookIndexInputs:
    generated_at: str
    documents: tuple[ResearchNotebookDocument, ...]


@dataclass(frozen=True)
class ResearchNotebookIndexItem:
    filename: str
    rule: str
    date: str
    status: str
    confidence: str
    classification: str
    lifetime: Metric
    dynamic: Metric
    breathing: Metric
    collapse: Metric
    questions: int
    discoveries: int
    mechanisms: int
    principles: int
    predictions: int


@dataclass(frozen=True)
class ResearchNotebookIndexArtifact:
    items: tuple[ResearchNotebookIndexItem, ...]
    markdown: str


@dataclass(frozen=True)
class ResearchNotebookIndexSaveResult:
    artifact: ResearchNotebookIndexArtifact
    notebook_dir: Path
    output_path: Path


class ResearchNotebookIndexRepository(Protocol):
    def load(
        self,
        paths: ResearchNotebookIndexPaths,
    ) -> ResearchNotebookIndexInputs:
        ...

    def save(
        self,
        paths: ResearchNotebookIndexPaths,
        artifact: ResearchNotebookIndexArtifact,
    ) -> ResearchNotebookIndexSaveResult:
        ...


__all__ = [
    "Metric",
    "ResearchNotebookDocument",
    "ResearchNotebookIndexArtifact",
    "ResearchNotebookIndexInputs",
    "ResearchNotebookIndexItem",
    "ResearchNotebookIndexPaths",
    "ResearchNotebookIndexRepository",
    "ResearchNotebookIndexSaveResult",
]
