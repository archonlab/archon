"""Ports and immutable run contracts for morphological evolution."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol


EvolutionProducer = Callable[
    [Path, list[dict[str, Any]]], dict[str, Any] | None
]


@dataclass(frozen=True)
class EvolutionPaths:
    results_dir: Path


@dataclass(frozen=True)
class EvolutionInputs:
    summaries: list[dict[str, Any] | None]
    csv_files_found: int
    incremental: dict[str, int]
    errors: list[dict[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class EvolutionRunResult:
    report: dict[str, Any]
    artifacts: dict[str, str]
    incremental: dict[str, int]
    elapsed_seconds: float = 0.0


class EvolutionSource(Protocol):
    def collect(
        self, paths: EvolutionPaths, producer: EvolutionProducer
    ) -> EvolutionInputs:
        ...


class EvolutionArtifactRepository(Protocol):
    def save(
        self, paths: EvolutionPaths, result: EvolutionRunResult
    ) -> None:
        ...

