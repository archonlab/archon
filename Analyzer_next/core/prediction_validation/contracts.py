"""Ports and immutable values for Prediction Validation Engine v2.3."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class PredictionValidationPaths:
    atlas: Path
    predictions: Path
    output_markdown: Path
    output_json: Path


@dataclass(frozen=True)
class PredictionValidationInputs:
    atlas: dict[str, Any]
    predictions: list[dict[str, Any]]
    aliases: dict[str, str]
    generated: str


@dataclass(frozen=True)
class PredictionValidationRunResult:
    payload: dict[str, Any]
    markdown: str
    results: list[dict[str, Any]]


class PredictionValidationRepository(Protocol):
    def load(self, paths: PredictionValidationPaths) -> PredictionValidationInputs:
        ...

    def save(
        self,
        paths: PredictionValidationPaths,
        result: PredictionValidationRunResult,
    ) -> None:
        ...


__all__ = [
    "PredictionValidationInputs",
    "PredictionValidationPaths",
    "PredictionValidationRepository",
    "PredictionValidationRunResult",
]
