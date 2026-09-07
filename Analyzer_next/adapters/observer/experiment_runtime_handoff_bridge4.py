"""BRIDGE4 mixed runtime handoff: Observer Queue or explicit Universe Search."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Analyzer_next.adapters.observer.cohort_search_execution_handoff import (
    CohortSearchExecutionError,
    CohortSearchExecutionHandoff,
    SEARCH_AUTHORIZED_STATUS,
    SEARCH_STARTED_STATUS,
)
from Analyzer_next.adapters.observer.experiment_runtime_handoff import (
    ExperimentRuntimeHandoffError,
    _as_dict,
    _as_list,
)
from Analyzer_next.adapters.observer.experiment_runtime_handoff_fix7 import (
    AuditedExperimentRuntimeHandoffFix7,
)


class AuditedExperimentRuntimeHandoffBridge4(AuditedExperimentRuntimeHandoffFix7):
    """Preserve Observer Stage 6.5 while adding Search-only authorization/dispatch."""

    def __init__(
        self,
        project_root: Path,
        *args,
        search_runner=None,
        search_launcher_runner=None,
        **kwargs,
    ) -> None:
        super().__init__(project_root, *args, **kwargs)
        self.search_handoff = CohortSearchExecutionHandoff(
            self.project_root,
            experiments_root=self.experiments_root,
            runner=search_runner,
            launcher_runner=search_launcher_runner,
        )

    def _is_search_runtime(self, runtime_id: str) -> bool:
        entry = self._index_entry(str(runtime_id).strip())
        _path, package = self._package_for_entry(entry)
        runtime = _as_dict(package.get("runtime"))
        return runtime.get("execution_kind") == "UNIVERSE_SEARCH"

    def list_runtimes(self, experiment_id: str | None = None):
        rows = list(super().list_runtimes(experiment_id))
        enriched = []
        for row in rows:
            try:
                entry = self._index_entry(row.runtime_id)
                _path, package = self._package_for_entry(entry)
            except Exception:
                enriched.append(row)
                continue
            runtime = _as_dict(package.get("runtime"))
            search = _as_dict(runtime.get("search_execution"))
            if runtime.get("execution_kind") != "UNIVERSE_SEARCH":
                enriched.append(row)
                continue
            budget = _as_dict(search.get("budget"))
            auth = self.search_handoff.authorization_for_runtime(row.runtime_id) or {}
            state = _as_dict(package.get("search_execution_state"))
            launch = _as_dict(package.get("search_launch_authorization"))
            enriched.append(replace(
                row,
                execution_kind="UNIVERSE_SEARCH",
                design_mode=(str(runtime.get("design_mode")) if runtime.get("design_mode") else None),
                search_job_id=(str(search.get("search_job_id")) if search.get("search_job_id") else None),
                target_regime=(str(search.get("target_regime")) if search.get("target_regime") else None),
                reference_rule_count=len(_as_list(search.get("reference_rules"))),
                population=(int(budget["population"]) if budget.get("population") is not None else None),
                generations=(int(budget["generations"]) if budget.get("generations") is not None else None),
                candidate_slots=(int(budget["candidate_evaluation_slots"]) if budget.get("candidate_evaluation_slots") is not None else None),
                launch_authorized=bool(entry.get("launch_authorized") is True and launch.get("authorized") is True),
                search_authorization_id=(str(auth.get("authorization_id")) if auth.get("authorization_id") else None),
                search_verification_status=(str(auth.get("verification_status")) if auth.get("verification_status") else None),
                search_execution_started=bool(auth.get("execution_started") is True or state.get("execution_started") is True or row.status == SEARCH_STARTED_STATUS),
                search_pid=(int(auth["pid"]) if auth.get("pid") is not None else (int(state["pid"]) if state.get("pid") is not None else None)),
            ))
        return tuple(enriched)

    def authorize_runtime(self, runtime_id: str, *, requested_by: str = "observer_launcher_2"):
        if self._is_search_runtime(runtime_id):
            try:
                return self.search_handoff.authorize_runtime(runtime_id, requested_by=requested_by)
            except CohortSearchExecutionError as exc:
                raise ExperimentRuntimeHandoffError(str(exc)) from exc
        return super().authorize_runtime(runtime_id, requested_by=requested_by)

    def prepare_authorized_runtime(
        self,
        runtime_id: str,
        *,
        execution_horizon: int | None = None,
        autosave_every: int | None = None,
    ):
        if self._is_search_runtime(runtime_id):
            raise ExperimentRuntimeHandoffError(
                "UNIVERSE_SEARCH_MUST_NOT_USE_OBSERVER_QUEUE: use explicit Search start after VERIFIED Search authorization"
            )
        return super().prepare_authorized_runtime(
            runtime_id,
            execution_horizon=execution_horizon,
            autosave_every=autosave_every,
        )


    def open_authorized_search_launcher(
        self, runtime_id: str, *, requested_by: str = "observer_launcher_2"
    ):
        if not self._is_search_runtime(runtime_id):
            raise ExperimentRuntimeHandoffError(
                "OBSERVER_RUNTIME_MUST_NOT_USE_UNIVERSE_SEARCH_LAUNCHER"
            )
        try:
            return self.search_handoff.open_authorized_search_launcher(
                runtime_id, requested_by=requested_by
            )
        except CohortSearchExecutionError as exc:
            raise ExperimentRuntimeHandoffError(str(exc)) from exc

    def start_authorized_search(self, runtime_id: str, *, requested_by: str = "observer_launcher_2"):
        if not self._is_search_runtime(runtime_id):
            raise ExperimentRuntimeHandoffError(
                "OBSERVER_RUNTIME_MUST_NOT_USE_UNIVERSE_SEARCH_DISPATCH"
            )
        try:
            return self.search_handoff.start_authorized_search(runtime_id, requested_by=requested_by)
        except CohortSearchExecutionError as exc:
            raise ExperimentRuntimeHandoffError(str(exc)) from exc


__all__ = ["AuditedExperimentRuntimeHandoffBridge4"]
