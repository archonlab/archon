"""Contracts for the modular Knowledge Base engine."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from Analyzer_next.core.scientific_data.contracts import ScientificDataSnapshot


@dataclass(frozen=True)
class KnowledgeBasePaths:
    results_root: Path
    analysis_root: Path
    knowledge_root: Path
    atlas_path: Path
    output_json: Path
    output_markdown: Path
    integrity_json: Path
    pretty_json: bool = False


@dataclass(frozen=True)
class KnowledgeBaseInputs:
    scientific_data: ScientificDataSnapshot
    aliases: dict[str, str]
    predictions: dict[str, dict[str, Any]]
    validations: dict[str, dict[str, Any]]
    previous_knowledge_base: dict[str, Any]
    previous_integrity: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeBaseRunResult:
    knowledge_base: dict[str, Any]
    integrity: dict[str, Any]
    report_markdown: str


class KnowledgeBaseRepository(Protocol):
    def load(self, paths: KnowledgeBasePaths) -> KnowledgeBaseInputs:
        ...

    def save(
        self,
        paths: KnowledgeBasePaths,
        result: KnowledgeBaseRunResult,
    ) -> None:
        ...
