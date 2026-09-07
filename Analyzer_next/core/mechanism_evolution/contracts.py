"""Ports and immutable values for mechanism-evolution analysis."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class MechanismEvolutionPaths:
    results_root: Path


@dataclass(frozen=True)
class MechanismEvolutionInputs:
    mechanism_registry: dict[str, Any]
    template_registry: dict[str, Any]
    instance_registry: dict[str, Any]
    template_rule_map: dict[str, Any]


@dataclass(frozen=True)
class MechanismEvolutionRunResult:
    evolution_graph: dict[str, Any]
    report: dict[str, Any]


class MechanismEvolutionRepository(Protocol):
    def load(
        self,
        paths: MechanismEvolutionPaths,
    ) -> MechanismEvolutionInputs: ...

    def save(
        self,
        paths: MechanismEvolutionPaths,
        result: MechanismEvolutionRunResult,
    ) -> None: ...
