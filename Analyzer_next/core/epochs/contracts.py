"""Ports and immutable run contracts for morphological epochs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol


EpochProducer = Callable[[Path, list[dict[str, Any]]], dict[str, Any] | None]


@dataclass(frozen=True)
class EpochPaths:
    results_dir: Path


@dataclass(frozen=True)
class EpochInputs:
    summaries: list[dict[str, Any] | None]
    csv_files_found: int
    incremental: dict[str, int]
    errors: list[dict[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class EpochRunResult:
    report: dict[str, Any]
    artifacts: dict[str, str]
    incremental: dict[str, int]
    elapsed_seconds: float = 0.0


class EpochSource(Protocol):
    def collect(self, paths: EpochPaths, producer: EpochProducer) -> EpochInputs:
        ...


class EpochArtifactRepository(Protocol):
    def save(self, paths: EpochPaths, result: EpochRunResult) -> None:
        ...

