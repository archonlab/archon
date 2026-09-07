"""Ports and immutable values for mechanism-timeline analysis."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class MechanismTimelinePaths:
    results_root: Path


@dataclass(frozen=True)
class MechanismTimelineInputs:
    fused: dict[str, Any]
    mechanism_registry: dict[str, Any]
    composition_templates: dict[str, Any]
    composition_instances: dict[str, Any]
    composition_registry: dict[str, Any]
    causal_motifs: dict[str, Any]
    causal_mechanisms: dict[str, Any]

    def as_sources(self) -> dict[str, dict[str, Any]]:
        return {
            "fused": self.fused,
            "mechanism_registry": self.mechanism_registry,
            "composition_templates": self.composition_templates,
            "composition_instances": self.composition_instances,
            "composition_registry": self.composition_registry,
            "causal_motifs": self.causal_motifs,
            "causal_mechanisms": self.causal_mechanisms,
        }


@dataclass(frozen=True)
class MechanismTimelineOptions:
    pretty_json: bool = False
    write_full_md: bool = True


@dataclass(frozen=True)
class MechanismTimelineRunResult:
    timeline: dict[str, Any]
    report: dict[str, Any]


@dataclass(frozen=True)
class MechanismTimelineExecution:
    result: MechanismTimelineRunResult
    output_writing_seconds: float


class MechanismTimelineProgress(Protocol):
    def __call__(
        self,
        index: int,
        total: int,
        rule_id: str,
        event_count: int,
        elapsed_seconds: float,
    ) -> None: ...


class MechanismTimelineRepository(Protocol):
    def load(
        self,
        paths: MechanismTimelinePaths,
    ) -> MechanismTimelineInputs: ...

    def save(
        self,
        paths: MechanismTimelinePaths,
        result: MechanismTimelineRunResult,
        options: MechanismTimelineOptions,
    ) -> None: ...

