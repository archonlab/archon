"""EXPERIMENTS-FIX6 Stage 6.5 handoff with stale authorization recovery."""
from __future__ import annotations

from pathlib import Path

import Analyzer_next.adapters.observer.experiment_runtime_handoff as base
from Analyzer_next.adapters.observer.experiment_authorization_state import (
    AuthorizationStateError,
    retire_stale_active_authorization,
)
from Analyzer_next.adapters.observer.experiment_runtime_handoff import ExperimentRuntimeHandoffError
from Analyzer_next.adapters.observer.experiment_runtime_handoff_fix3 import AuditedExperimentRuntimeHandoffFix3


class AuditedExperimentRuntimeHandoffFix6(AuditedExperimentRuntimeHandoffFix3):
    """Retire rematerialization-stale receipts, then use unchanged Stage 6.5."""

    def authorize_runtime(self, runtime_id: str, *, requested_by: str = "observer_launcher_2"):
        runtime_id = str(runtime_id).strip()
        try:
            retired = retire_stale_active_authorization(
                self.project_root,
                self.experiments_root,
                runtime_id,
            )
        except AuthorizationStateError as exc:
            raise ExperimentRuntimeHandoffError(f"authorization state recovery refused: {exc}") from exc
        try:
            result = super().authorize_runtime(runtime_id, requested_by=requested_by)
        except ExperimentRuntimeHandoffError as exc:
            # Surface exact Stage 6.5 refusal reasons when available.  The
            # gateway itself remains the authority and is not modified here.
            payload = base._load(self.experiments_root / "launch_authorization_result.json", {})
            reasons = base._as_list(payload.get("reasons")) if isinstance(payload, dict) else []
            suffix = (" • reasons=" + ",".join(str(x) for x in reasons)) if reasons else ""
            raise ExperimentRuntimeHandoffError(str(exc) + suffix) from exc
        if retired and result.authorized:
            return type(result)(
                runtime_id=result.runtime_id,
                status=result.status,
                authorized=result.authorized,
                authorization_id=result.authorization_id,
                verification_status=result.verification_status,
                message=(
                    f"Retired stale authorization {retired} after runtime rematerialization; "
                    + result.message
                ),
            )
        return result


__all__ = ["AuditedExperimentRuntimeHandoffFix6"]
