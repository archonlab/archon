"""Ports and immutable values for the atomic mechanism registry."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class CausalRegistryPaths:
    results_root: Path


@dataclass(frozen=True)
class CausalRegistryInputs:
    sources: dict[str, Any]


@dataclass(frozen=True)
class CausalRegistryRunResult:
    source_keys: tuple[str, ...]
    atomic_registry: dict[str, Any]
    composition_registry: dict[str, Any]
    rule_map: dict[str, Any]
    report: dict[str, Any]


class CausalRegistryRepository(Protocol):
    def load(self, paths: CausalRegistryPaths) -> CausalRegistryInputs: ...

    def save(
        self,
        paths: CausalRegistryPaths,
        result: CausalRegistryRunResult,
    ) -> None: ...
