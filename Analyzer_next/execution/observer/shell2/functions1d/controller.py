"""Storage/toolkit-independent experiment browser controller for OL2-FUNCTIONS1D."""
from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .model import ConditionRow, ExperimentCatalogSnapshot, ExperimentRow, ExperimentRunRow


class ExperimentCatalogPort(Protocol):
    def list_experiments(self) -> tuple[ExperimentRow, ...]: ...
    def list_conditions(self) -> tuple[ConditionRow, ...]: ...
    def list_experiment_runs(self, experiment_id: str) -> tuple[ExperimentRunRow, ...]: ...


class ExperimentCatalogController:
    def __init__(self, port: ExperimentCatalogPort) -> None:
        self.port = port
        self._snapshot = ExperimentCatalogSnapshot()

    @property
    def snapshot(self) -> ExperimentCatalogSnapshot:
        return self._snapshot

    def _publish(self, **changes) -> ExperimentCatalogSnapshot:
        self._snapshot = replace(
            self._snapshot,
            **changes,
            revision=self._snapshot.revision + 1,
        )
        return self._snapshot

    def refresh(self) -> ExperimentCatalogSnapshot:
        try:
            experiments = self.port.list_experiments()
            conditions = self.port.list_conditions()
        except Exception as exc:
            return self._publish(error=f"{type(exc).__name__}: {exc}")

        selected_experiment_id = self._snapshot.selected_experiment_id
        if selected_experiment_id not in {row.experiment_id for row in experiments}:
            selected_experiment_id = experiments[0].experiment_id if experiments else None
        selected_condition_id = self._snapshot.selected_condition_id
        if selected_condition_id not in {row.condition_id for row in conditions}:
            selected_condition_id = conditions[0].condition_id if conditions else None

        runs: tuple[ExperimentRunRow, ...] = ()
        if selected_experiment_id:
            try:
                runs = self.port.list_experiment_runs(selected_experiment_id)
            except Exception as exc:
                return self._publish(
                    experiments=experiments,
                    conditions=conditions,
                    selected_experiment_id=selected_experiment_id,
                    selected_condition_id=selected_condition_id,
                    runs=(),
                    error=f"{type(exc).__name__}: {exc}",
                )

        linked = {condition.condition_id: 0 for condition in conditions}
        for run in runs:
            linked[run.condition_id] = linked.get(run.condition_id, 0) + 1
        conditions = tuple(
            replace(row, linked_run_count=linked.get(row.condition_id, 0))
            for row in conditions
        )
        counts = {row.experiment_id: 0 for row in experiments}
        if selected_experiment_id:
            counts[selected_experiment_id] = len(runs)
        experiments = tuple(
            replace(row, run_count=counts.get(row.experiment_id, row.run_count))
            for row in experiments
        )
        return self._publish(
            experiments=experiments,
            conditions=conditions,
            selected_experiment_id=selected_experiment_id,
            selected_condition_id=selected_condition_id,
            runs=runs,
            error=None,
        )

    def set_filters(self, *, query: str | None = None, status: str | None = None) -> ExperimentCatalogSnapshot:
        changes = {}
        if query is not None:
            changes["query"] = str(query)
        if status is not None:
            changes["status_filter"] = str(status)
        return self._publish(**changes)

    def select_experiment(self, experiment_id: str) -> ExperimentCatalogSnapshot:
        experiment_id = str(experiment_id).strip()
        if experiment_id not in {row.experiment_id for row in self._snapshot.experiments}:
            raise ValueError(f"unknown experiment_id: {experiment_id}")
        runs = self.port.list_experiment_runs(experiment_id)
        linked = {condition.condition_id: 0 for condition in self._snapshot.conditions}
        for run in runs:
            linked[run.condition_id] = linked.get(run.condition_id, 0) + 1
        conditions = tuple(
            replace(row, linked_run_count=linked.get(row.condition_id, 0))
            for row in self._snapshot.conditions
        )
        experiments = tuple(
            replace(row, run_count=(len(runs) if row.experiment_id == experiment_id else row.run_count))
            for row in self._snapshot.experiments
        )
        selected_condition_id = self._snapshot.selected_condition_id
        linked_ids = {run.condition_id for run in runs}
        if linked_ids:
            preferred = next((row.condition_id for row in conditions if row.condition_id in linked_ids), None)
            if preferred:
                selected_condition_id = preferred
        return self._publish(
            experiments=experiments,
            conditions=conditions,
            selected_experiment_id=experiment_id,
            selected_condition_id=selected_condition_id,
            runs=runs,
            error=None,
        )

    def select_condition(self, condition_id: str) -> ExperimentCatalogSnapshot:
        condition_id = str(condition_id).strip()
        if condition_id not in {row.condition_id for row in self._snapshot.conditions}:
            raise ValueError(f"unknown condition_id: {condition_id}")
        return self._publish(selected_condition_id=condition_id)

    def next_replicate_index(self, *, rule_id: int, role: str) -> int:
        experiment_id = self._snapshot.selected_experiment_id
        condition_id = self._snapshot.selected_condition_id
        if not experiment_id or not condition_id:
            raise ValueError("select experiment and condition first")
        used = {
            int(row.replicate_index)
            for row in self._snapshot.runs
            if row.condition_id == condition_id
            and row.rule_id == int(rule_id)
            and row.role == str(role)
        }
        candidate = 0
        while candidate in used:
            candidate += 1
        return candidate


__all__ = ["ExperimentCatalogController", "ExperimentCatalogPort"]
