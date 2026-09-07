"""Ports and immutable values for Experiment Planner Engine v4.4."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ExperimentPlannerPaths:
    knowledge_base: Path
    output_markdown: Path
    output_json: Path
    validation_report: Path
    prediction_database: Path
    cohort_targets: Path
    consensus_report: Path
    evidence_report: Path
    metric_independence_audit: Path


@dataclass(frozen=True)
class ExperimentPlannerInputs:
    paths: ExperimentPlannerPaths
    knowledge_base: dict[str, Any]
    validation_payload: dict[str, Any]
    prediction_payload: dict[str, Any]
    cohort_payload: dict[str, Any]
    consensus_payload: dict[str, Any]
    evidence_payload: dict[str, Any]
    metric_audit: dict[str, Any]
    existing_output: dict[str, Any]
    output_markdown_exists: bool
    generated: str


@dataclass(frozen=True)
class ExperimentPlannerArtifact:
    payload: dict[str, Any]
    markdown: str
    changed: bool
    validation_count: int


@dataclass(frozen=True)
class ExperimentPlannerSaveResult:
    artifact: ExperimentPlannerArtifact
    paths: ExperimentPlannerPaths


class ExperimentPlannerRepository(Protocol):
    def load(self, paths: ExperimentPlannerPaths) -> ExperimentPlannerInputs:
        ...

    def save(
        self,
        paths: ExperimentPlannerPaths,
        artifact: ExperimentPlannerArtifact,
    ) -> ExperimentPlannerSaveResult:
        ...


__all__ = [
    "ExperimentPlannerArtifact",
    "ExperimentPlannerInputs",
    "ExperimentPlannerPaths",
    "ExperimentPlannerRepository",
    "ExperimentPlannerSaveResult",
]
