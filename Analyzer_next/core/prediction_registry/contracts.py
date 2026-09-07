"""Requests, inputs, results, and repository port for Prediction Engine v2."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class PredictionRegistryPaths:
    atlas: Path
    principles: Path | None
    analysis_root: Path
    knowledge_base: Path
    database_json: Path
    database_markdown: Path
    output_json: Path
    output_markdown: Path


@dataclass(frozen=True)
class PredictionRegistryInputs:
    atlas: dict[str, Any]
    knowledge_base: dict[str, Any]
    principles: dict[str, dict[str, Any]]
    validations: dict[str, dict[str, Any]]
    database: dict[str, Any]


@dataclass(frozen=True)
class PredictionRegistryRunResult:
    database: dict[str, Any]
    compatibility: dict[str, Any]
    database_markdown: str
    output_markdown: str
    principle_count: int
    candidate_count: int
    validation_count: int


class PredictionRegistryRepository(Protocol):
    def load(self, paths: PredictionRegistryPaths) -> PredictionRegistryInputs:
        ...

    def save(
        self,
        paths: PredictionRegistryPaths,
        result: PredictionRegistryRunResult,
    ) -> None:
        ...


__all__ = [
    "PredictionRegistryInputs",
    "PredictionRegistryPaths",
    "PredictionRegistryRepository",
    "PredictionRegistryRunResult",
]
