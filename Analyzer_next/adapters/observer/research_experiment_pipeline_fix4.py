"""EXPERIMENTS-FIX4 pipeline: repair implicit legacy seed fallback before FIX3 flow."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from Analyzer_next.adapters.observer.experiment_runtime_policy_compat_fix4 import repair_runtime_policy
from Analyzer_next.adapters.observer.research_experiment_pipeline_fix3 import AuditedResearchExperimentPipelineFix3


class AuditedResearchExperimentPipelineFix4(AuditedResearchExperimentPipelineFix3):
    """Preserve FIX3 governance/planning while repairing missing legacy mode."""

    def __init__(self, project_root: Path, telemetry_database: Path, **kwargs: Any) -> None:
        super().__init__(project_root, telemetry_database, **kwargs)

    def _repair_fix4_policy(self, progress=None):
        repair = repair_runtime_policy(self.runtime_policy_path)
        self._emit(progress, "policy", repair.message)
        return repair

    def approve_and_materialize(self, proposal_id: str, *, decision_reason: str, progress=None):
        self._repair_fix4_policy(progress)
        return super().approve_and_materialize(
            proposal_id,
            decision_reason=decision_reason,
            progress=progress,
        )

    def reconcile_existing(self, *, progress=None):
        self._repair_fix4_policy(progress)
        return super().reconcile_existing(progress=progress)

    def rebuild_approved(self, proposal_id: str, *, progress=None):
        self._repair_fix4_policy(progress)
        return super().rebuild_approved(proposal_id, progress=progress)


__all__ = ["AuditedResearchExperimentPipelineFix4"]
