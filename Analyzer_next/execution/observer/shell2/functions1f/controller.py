"""Toolkit/process-independent state controller for OL2-FUNCTIONS1F."""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, Protocol

from .model import ExperimentPipelineResult, ExperimentPipelineSnapshot

ProgressCallback = Callable[[str, str], None]


class ExperimentPipelinePort(Protocol):
    def approve_and_materialize(
        self,
        proposal_id: str,
        *,
        decision_reason: str,
        progress: ProgressCallback | None = None,
    ) -> ExperimentPipelineResult: ...

    def record_review_decision(
        self,
        proposal_id: str,
        *,
        decision: str,
        reason: str,
        progress: ProgressCallback | None = None,
    ) -> ExperimentPipelineResult: ...

    def refresh_director(
        self,
        *,
        progress: ProgressCallback | None = None,
    ) -> ExperimentPipelineResult: ...

    def reconcile_existing(
        self,
        *,
        progress: ProgressCallback | None = None,
    ) -> ExperimentPipelineResult: ...


class ExperimentPipelineController:
    """Hold UI-facing pipeline state while all I/O remains behind a port."""

    def __init__(self, port: ExperimentPipelinePort) -> None:
        self.port = port
        self._snapshot = ExperimentPipelineSnapshot()

    @property
    def snapshot(self) -> ExperimentPipelineSnapshot:
        return self._snapshot

    def _publish(self, **changes) -> ExperimentPipelineSnapshot:
        self._snapshot = replace(
            self._snapshot,
            **changes,
            revision=self._snapshot.revision + 1,
        )
        return self._snapshot

    def begin(self, proposal_id: str, message: str) -> ExperimentPipelineSnapshot:
        proposal_id = str(proposal_id).strip()
        if not proposal_id:
            raise ValueError("proposal_id is required")
        if self._snapshot.busy:
            raise RuntimeError("experiment pipeline is already running")
        return self._publish(
            busy=True,
            proposal_id=proposal_id,
            stage="starting",
            message=message,
            result=None,
            error=None,
        )

    def progress(self, stage: str, message: str) -> ExperimentPipelineSnapshot:
        if not self._snapshot.busy:
            return self._snapshot
        return self._publish(stage=str(stage), message=str(message), error=None)

    def complete(self, result: ExperimentPipelineResult) -> ExperimentPipelineSnapshot:
        if self._snapshot.proposal_id and result.proposal_id != self._snapshot.proposal_id:
            raise ValueError("pipeline result proposal identity mismatch")
        return self._publish(
            busy=False,
            proposal_id=result.proposal_id,
            stage="completed",
            message=result.message or result.status,
            result=result,
            error=None,
        )

    def fail(self, error: BaseException | str) -> ExperimentPipelineSnapshot:
        text = str(error)
        return self._publish(
            busy=False,
            stage="failed",
            message=text,
            error=text,
        )


__all__ = [
    "ExperimentPipelineController",
    "ExperimentPipelinePort",
    "ProgressCallback",
]
