"""Ports and immutable values for Research Notebook Engine v4."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ResearchNotebookPaths:
    results_folder: Path
    analysis_root: Path


@dataclass(frozen=True)
class ResearchNotebookInputs:
    passport_source_name: str
    passport_text: str
    generated_date: str
    results_folder_display: str
    questions_text: str
    discoveries_text: str
    mechanism_reports: dict[str, str]
    fallback_mechanism_text: str
    principles_text: str
    predictions_text: str


@dataclass(frozen=True)
class ResearchNotebookArtifact:
    notebook: dict[str, Any]
    markdown: str


@dataclass(frozen=True)
class ResearchNotebookRunResult:
    artifacts: tuple[ResearchNotebookArtifact, ...]
    passport_source_name: str


@dataclass(frozen=True)
class ResearchNotebookSavedArtifact:
    notebook: dict[str, Any]
    path: Path


@dataclass(frozen=True)
class ResearchNotebookSaveResult:
    outputs: tuple[ResearchNotebookSavedArtifact, ...]
    manifest_path: Path
    source_path: Path


class ResearchNotebookRepository(Protocol):
    def load(self, paths: ResearchNotebookPaths) -> ResearchNotebookInputs:
        ...

    def save(
        self,
        paths: ResearchNotebookPaths,
        result: ResearchNotebookRunResult,
    ) -> ResearchNotebookSaveResult:
        ...


__all__ = [
    "ResearchNotebookArtifact",
    "ResearchNotebookInputs",
    "ResearchNotebookPaths",
    "ResearchNotebookRepository",
    "ResearchNotebookRunResult",
    "ResearchNotebookSaveResult",
    "ResearchNotebookSavedArtifact",
]
