"""Ports and immutable run contracts for morphological event fusion."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class FusionPaths:
    results_dir: Path


@dataclass(frozen=True)
class FusionInputs:
    event_source: dict[str, Any]


@dataclass(frozen=True)
class FusionRunResult:
    report: dict[str, Any]
    artifacts: dict[str, str]


class FusionSource(Protocol):
    def load(self, paths: FusionPaths) -> FusionInputs:
        ...


class FusionArtifactRepository(Protocol):
    def save(self, paths: FusionPaths, result: FusionRunResult) -> None:
        ...

