"""Ports and immutable values for Causal Graph Builder."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class CausalGraphPaths:
    results_root: Path


@dataclass(frozen=True)
class CausalGraphInputs:
    fused_events: dict[str, Any]


@dataclass(frozen=True)
class CausalGraphRunResult:
    report: dict[str, Any]


class CausalGraphRepository(Protocol):
    def load(self, paths: CausalGraphPaths) -> CausalGraphInputs: ...

    def save(
        self,
        paths: CausalGraphPaths,
        result: CausalGraphRunResult,
    ) -> None: ...
