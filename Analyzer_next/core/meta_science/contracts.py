"""Requests, results, and the repository port for Meta Science."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class MetaSciencePaths:
    results: Path
    root: Path
    knowledge_root: Path
    report_json: Path
    report_markdown: Path
    history: Path


@dataclass(frozen=True)
class MetaScienceInputs:
    consensus: dict[str, Any]
    consensus_database: dict[str, Any]
    evidence: dict[str, Any]
    general_principles: dict[str, Any]
    research_atlas: dict[str, Any]
    theory_report: str
    profiles: dict[str, Any]
    knowledge_base: dict[str, Any]
    prediction_database: dict[str, Any]
    validation_report: dict[str, Any]
    experiment_plan: dict[str, Any]
    knowledge_integrity: dict[str, Any]
    reference_controls: dict[str, Any]
    history: dict[str, Any]


@dataclass(frozen=True)
class MetaScienceRunResult:
    report: dict[str, Any]
    history: dict[str, Any]
    report_markdown: str


class MetaScienceRepository(Protocol):
    def load(self, paths: MetaSciencePaths) -> MetaScienceInputs:
        ...

    def save(self, paths: MetaSciencePaths, result: MetaScienceRunResult) -> None:
        ...
