"""OL2-FUNCTIONS1D experiment browser contracts."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExperimentRow:
    experiment_id: str
    title: str
    research_question: str | None
    status: str
    created_at_utc: str | None
    updated_at_utc: str | None
    run_count: int = 0


@dataclass(frozen=True, slots=True)
class ConditionRow:
    condition_id: str
    name: str
    field_width: int
    field_height: int
    topology: str
    boundary_mode: str
    initial_state_mode: str
    linked_run_count: int = 0


@dataclass(frozen=True, slots=True)
class ExperimentRunRow:
    experiment_run_id: str
    run_id: str
    condition_id: str
    rule_id: int | None
    role: str
    replicate_index: int
    treatment_arm: str
    created_at_utc: str | None


@dataclass(frozen=True, slots=True)
class ExperimentCatalogSnapshot:
    experiments: tuple[ExperimentRow, ...] = ()
    conditions: tuple[ConditionRow, ...] = ()
    selected_experiment_id: str | None = None
    selected_condition_id: str | None = None
    runs: tuple[ExperimentRunRow, ...] = ()
    query: str = ""
    status_filter: str = "All"
    error: str | None = None
    revision: int = 0

    @property
    def selected_experiment(self) -> ExperimentRow | None:
        return next(
            (row for row in self.experiments if row.experiment_id == self.selected_experiment_id),
            None,
        )

    @property
    def selected_condition(self) -> ConditionRow | None:
        return next(
            (row for row in self.conditions if row.condition_id == self.selected_condition_id),
            None,
        )

    @property
    def visible_experiments(self) -> tuple[ExperimentRow, ...]:
        query = self.query.strip().casefold()
        status = self.status_filter.strip().casefold()
        rows = self.experiments
        if status and status != "all":
            rows = tuple(row for row in rows if row.status.casefold() == status)
        if query:
            rows = tuple(
                row
                for row in rows
                if query in row.experiment_id.casefold()
                or query in row.title.casefold()
                or query in (row.research_question or "").casefold()
            )
        return rows


__all__ = [
    "ConditionRow",
    "ExperimentCatalogSnapshot",
    "ExperimentRow",
    "ExperimentRunRow",
]
