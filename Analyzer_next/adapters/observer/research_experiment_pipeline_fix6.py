"""EXPERIMENTS-FIX6 preserve Stage 6.5 state across runtime reconciliation."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from Analyzer_next.adapters.observer.experiment_authorization_state import (
    AuthorizationStateError,
    capture_consistent_authorized_runtimes,
    reconcile_after_materialization,
)
from Analyzer_next.adapters.observer.research_experiment_pipeline import ResearchExperimentPipelineError
from Analyzer_next.adapters.observer.research_experiment_pipeline_fix4 import AuditedResearchExperimentPipelineFix4


class AuditedResearchExperimentPipelineFix6(AuditedResearchExperimentPipelineFix4):
    """Keep VERIFIED authorizations when a full rebuild leaves runtime_hash unchanged."""

    def __init__(self, project_root: Path, telemetry_database: Path, **kwargs: Any) -> None:
        super().__init__(project_root, telemetry_database, **kwargs)
        self.authoritative_cycle_tracking_enabled = True

    def _capture_authorizations(self):
        try:
            return capture_consistent_authorized_runtimes(self.project_root, self.experiments_root)
        except AuthorizationStateError as exc:
            raise ResearchExperimentPipelineError(f"cannot snapshot launch authorization state: {exc}") from exc

    def _restore_authorizations(self, snapshots, result):
        try:
            reconciled = reconcile_after_materialization(
                self.project_root,
                self.experiments_root,
                snapshots,
            )
        except AuthorizationStateError as exc:
            raise ResearchExperimentPipelineError(f"cannot reconcile launch authorization state: {exc}") from exc
        if not snapshots:
            return result
        return replace(
            result,
            message=result.message + " • " + reconciled.message,
        )

    def reconcile_existing(self, *, progress=None):
        snapshots = self._capture_authorizations()
        result = super().reconcile_existing(progress=progress)
        result = self._restore_authorizations(snapshots, result)
        self._emit(progress, "authorization", result.message)
        return result

    def approve_and_materialize(self, proposal_id: str, *, decision_reason: str, progress=None):
        snapshots = self._capture_authorizations()
        result = super().approve_and_materialize(
            proposal_id,
            decision_reason=decision_reason,
            progress=progress,
        )
        return self._restore_authorizations(snapshots, result)

    def rebuild_approved(self, proposal_id: str, *, progress=None):
        snapshots = self._capture_authorizations()
        result = super().rebuild_approved(proposal_id, progress=progress)
        return self._restore_authorizations(snapshots, result)


__all__ = ["AuditedResearchExperimentPipelineFix6"]
