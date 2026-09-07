"""Storage-independent port for the Experimental Conditions aggregate.

The port deliberately models the complete repository boundary. A runtime
profile must select one implementation for conditions, experiments, plans,
and run links together; mixing implementations would break enum and identity
semantics across the aggregate.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExperimentalConditionsRepositoryPort(Protocol):
    """Complete persistence/orchestration boundary used by ARCHON runtimes."""

    database_path: Any

    def create_or_get_condition(self, **options: Any) -> Any: ...

    def get_condition(self, condition_id: str, **options: Any) -> Any: ...

    def list_conditions(self) -> tuple[Any, ...]: ...

    def create_experiment(self, **options: Any) -> Any: ...

    def get_experiment(self, experiment_id: str) -> Any: ...

    def list_experiments(self) -> tuple[Any, ...]: ...

    def update_experiment_status(self, experiment_id: str, status: Any) -> Any: ...

    def link_run(self, **options: Any) -> Any: ...

    def get_run_link(self, run_id: str) -> Any: ...

    def list_experiment_runs(self, experiment_id: str) -> tuple[Any, ...]: ...

    def validate_plan(self, plan: Any) -> Any: ...

    def next_replicate_index(self, **options: Any) -> int: ...

    def expand_plan(self, plan: Any) -> tuple[Any, ...]: ...

    def build_run_request(self, **options: Any) -> Any: ...


__all__ = ["ExperimentalConditionsRepositoryPort"]
