"""Ports and immutable run contracts for morphological events."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol


EventProducer = Callable[[Path, list[dict[str, Any]]], dict[str, Any] | None]


@dataclass(frozen=True)
class EventPaths:
    results_dir: Path


@dataclass(frozen=True)
class EventInputs:
    summaries: list[dict[str, Any] | None]
    csv_files_found: int
    incremental: dict[str, int]
    errors: list[dict[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class EventRunResult:
    report: dict[str, Any]
    artifacts: dict[str, str]
    incremental: dict[str, int]
    elapsed_seconds: float = 0.0


class EventSource(Protocol):
    def collect(self, paths: EventPaths, producer: EventProducer) -> EventInputs:
        ...


class EventArtifactRepository(Protocol):
    def save(self, paths: EventPaths, result: EventRunResult) -> None:
        ...
