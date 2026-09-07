"""Ports and immutable values for timeline compression."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class TimelineCompressionPaths:
    results_root: Path


@dataclass(frozen=True)
class TimelineCompressionInputs:
    mechanism_timeline: dict[str, Any]


@dataclass(frozen=True)
class TimelineCompressionRunResult:
    compression: dict[str, Any]
    report: dict[str, Any]


class TimelineCompressionRepository(Protocol):
    def load(
        self,
        paths: TimelineCompressionPaths,
    ) -> TimelineCompressionInputs: ...

    def save(
        self,
        paths: TimelineCompressionPaths,
        result: TimelineCompressionRunResult,
    ) -> None: ...
