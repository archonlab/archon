"""Value objects for OL2-FUNCTIONS1G/BRIDGE4 runtime execution handoff."""
from __future__ import annotations

from dataclasses import dataclass

from Analyzer_next.execution.observer.shell2.config1.model import PreparedConfiguration


@dataclass(frozen=True, slots=True)
class ExperimentRuntimeRow:
    runtime_id: str
    experiment_id: str | None
    plan_id: str | None
    status: str
    run_count: int
    unresolved_count: int
    launch_authorized: bool
    authorization_id: str | None = None
    verification_status: str | None = None
    updated_at: str | None = None
    execution_kind: str = "OBSERVER"
    design_mode: str | None = None
    search_job_id: str | None = None
    target_regime: str | None = None
    reference_rule_count: int = 0
    population: int | None = None
    generations: int | None = None
    candidate_slots: int | None = None
    search_authorization_id: str | None = None
    search_verification_status: str | None = None
    search_execution_started: bool = False
    search_pid: int | None = None
    experiment_type: str | None = None
    planned_horizon: int | None = None
    checkpoint_interval: int | None = None

    @property
    def is_search(self) -> bool:
        return self.execution_kind == "UNIVERSE_SEARCH"

    @property
    def can_authorize(self) -> bool:
        return (
            not self.is_search
            and self.status == "READY_FOR_LAUNCH_REVIEW"
            and not self.launch_authorized
            and self.unresolved_count == 0
        )

    @property
    def can_queue(self) -> bool:
        return (
            not self.is_search
            and self.status == "LAUNCH_AUTHORIZED"
            and self.launch_authorized
            and self.verification_status == "VERIFIED"
        )

    @property
    def can_authorize_search(self) -> bool:
        return (
            self.is_search
            and self.status == "READY_FOR_SEARCH_LAUNCH_REVIEW"
            and not self.launch_authorized
            and self.unresolved_count == 0
            and not self.search_execution_started
        )

    @property
    def can_start_search(self) -> bool:
        return (
            self.is_search
            and self.status == "SEARCH_LAUNCH_AUTHORIZED"
            and self.launch_authorized
            and self.search_verification_status == "VERIFIED"
            and not self.search_execution_started
        )


@dataclass(frozen=True, slots=True)
class RuntimeAuthorizationResult:
    runtime_id: str
    status: str
    authorized: bool
    authorization_id: str | None = None
    verification_status: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeQueuePreparation:
    runtime_id: str
    authorization_id: str
    prepared: tuple[PreparedConfiguration, ...]
    message: str = ""
    execution_attempt_id: str | None = None
    execution_experiment_id: str | None = None


@dataclass(frozen=True, slots=True)
class SearchDispatchResult:
    runtime_id: str
    dispatch_id: str
    started: bool
    pid: int | None = None
    log_path: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class SearchLauncherOpenResult:
    runtime_id: str
    opened: bool
    launcher_pid: int | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeHandoffSnapshot:
    runtimes: tuple[ExperimentRuntimeRow, ...] = ()
    selected_runtime_id: str | None = None
    experiment_id: str | None = None
    busy: bool = False
    stage: str = "idle"
    message: str = "Select a materialized runtime."
    error: str | None = None
    revision: int = 0

    @property
    def selected(self) -> ExperimentRuntimeRow | None:
        return next(
            (row for row in self.runtimes if row.runtime_id == self.selected_runtime_id),
            None,
        )


__all__ = [
    "ExperimentRuntimeRow",
    "RuntimeAuthorizationResult",
    "RuntimeHandoffSnapshot",
    "RuntimeQueuePreparation",
    "SearchDispatchResult",
    "SearchLauncherOpenResult",
]
