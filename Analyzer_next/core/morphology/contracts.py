"""Ports and immutable run contracts for morphology analysis."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


SummaryProducer = Callable[[Path, list[dict[str, Any]]], dict[str, Any] | None]


@dataclass(frozen=True)
class MorphologyPaths:
    results_dir: Path


@dataclass(frozen=True)
class MorphologyInputs:
    summaries: list[dict[str, Any] | None]
    csv_files_found: int
    incremental: dict[str, int]
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class MorphologyRunResult:
    report: dict[str, Any]
    comparison: dict[str, Any]
    artifacts: dict[str, str]
    incremental: dict[str, int]
    elapsed_seconds: float = 0.0


class MorphologySource(Protocol):
    def collect(
        self,
        paths: MorphologyPaths,
        producer: SummaryProducer,
    ) -> MorphologyInputs:
        ...


class MorphologyArtifactRepository(Protocol):
    def save(self, paths: MorphologyPaths, result: MorphologyRunResult) -> None:
        ...
