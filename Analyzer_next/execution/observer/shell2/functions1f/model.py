"""Value objects for OL2-FUNCTIONS1F audited proposal materialization."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExperimentPipelineResult:
    proposal_id: str
    status: str
    plan_ids: tuple[str, ...] = ()
    experiment_ids: tuple[str, ...] = ()
    runtime_ids: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class ExperimentPipelineSnapshot:
    busy: bool = False
    proposal_id: str | None = None
    stage: str = "idle"
    message: str = "Ready"
    result: ExperimentPipelineResult | None = None
    error: str | None = None
    revision: int = 0


__all__ = ["ExperimentPipelineResult", "ExperimentPipelineSnapshot"]
