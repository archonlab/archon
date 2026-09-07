"""Toolkit/process/storage-independent controller for OL2-FUNCTIONS1G/BRIDGE4."""
from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .model import (
    ExperimentRuntimeRow,
    RuntimeAuthorizationResult,
    RuntimeHandoffSnapshot,
    RuntimeQueuePreparation,
    SearchDispatchResult,
    SearchLauncherOpenResult,
)


class ExperimentRuntimeHandoffPort(Protocol):
    def list_runtimes(self, experiment_id: str | None = None) -> tuple[ExperimentRuntimeRow, ...]: ...
    def authorize_runtime(self, runtime_id: str, *, requested_by: str) -> RuntimeAuthorizationResult: ...
    def prepare_authorized_runtime(
        self,
        runtime_id: str,
        *,
        execution_horizon: int | None = None,
        autosave_every: int | None = None,
    ) -> RuntimeQueuePreparation: ...
    def start_authorized_search(self, runtime_id: str, *, requested_by: str) -> SearchDispatchResult: ...
    def open_authorized_search_launcher(self, runtime_id: str, *, requested_by: str) -> SearchLauncherOpenResult: ...


class ExperimentRuntimeHandoffController:
    def __init__(self, port: ExperimentRuntimeHandoffPort) -> None:
        self.port = port
        self._snapshot = RuntimeHandoffSnapshot()

    @property
    def snapshot(self) -> RuntimeHandoffSnapshot:
        return self._snapshot

    def _publish(self, **changes) -> RuntimeHandoffSnapshot:
        self._snapshot = replace(
            self._snapshot,
            **changes,
            revision=self._snapshot.revision + 1,
        )
        return self._snapshot

    def refresh(self, experiment_id: str | None = None) -> RuntimeHandoffSnapshot:
        try:
            rows = self.port.list_runtimes(experiment_id)
        except Exception as exc:
            return self._publish(
                runtimes=(),
                selected_runtime_id=None,
                experiment_id=experiment_id,
                error=f"{type(exc).__name__}: {exc}",
                message=f"Runtime inventory unavailable: {exc}",
            )
        selected = self._snapshot.selected_runtime_id
        ids = {row.runtime_id for row in rows}
        if selected not in ids:
            selected = rows[0].runtime_id if rows else None
        return self._publish(
            runtimes=rows,
            selected_runtime_id=selected,
            experiment_id=experiment_id,
            error=None,
            message=(
                f"{len(rows)} materialized runtime(s)"
                if rows
                else "No materialized runtime is registered for this experiment."
            ),
        )

    def select(self, runtime_id: str) -> RuntimeHandoffSnapshot:
        runtime_id = str(runtime_id).strip()
        if runtime_id not in {row.runtime_id for row in self._snapshot.runtimes}:
            raise ValueError(f"unknown runtime_id: {runtime_id}")
        return self._publish(selected_runtime_id=runtime_id, error=None)

    def begin(self, stage: str, message: str) -> RuntimeHandoffSnapshot:
        if self._snapshot.busy:
            raise RuntimeError("runtime handoff is already busy")
        if self._snapshot.selected is None:
            raise RuntimeError("select a runtime first")
        return self._publish(busy=True, stage=str(stage), message=str(message), error=None)

    def complete_authorization(self, result: RuntimeAuthorizationResult) -> RuntimeHandoffSnapshot:
        if self._snapshot.selected_runtime_id and result.runtime_id != self._snapshot.selected_runtime_id:
            raise ValueError("authorization result runtime identity mismatch")
        return self._publish(
            busy=False,
            stage="authorized" if result.authorized else "authorization-refused",
            message=result.message or result.status,
            error=None if result.authorized else (result.message or result.status),
        )

    def complete_queue(self, preparation: RuntimeQueuePreparation) -> RuntimeHandoffSnapshot:
        if self._snapshot.selected_runtime_id and preparation.runtime_id != self._snapshot.selected_runtime_id:
            raise ValueError("queue preparation runtime identity mismatch")
        return self._publish(
            busy=False,
            stage="queued",
            message=preparation.message or f"Prepared {len(preparation.prepared)} queue row(s)",
            error=None,
        )

    def complete_search(self, result: SearchDispatchResult) -> RuntimeHandoffSnapshot:
        if self._snapshot.selected_runtime_id and result.runtime_id != self._snapshot.selected_runtime_id:
            raise ValueError("search dispatch result runtime identity mismatch")
        return self._publish(
            busy=False,
            stage="search-started" if result.started else "search-start-refused",
            message=result.message or ("Search started" if result.started else "Search start refused"),
            error=None if result.started else (result.message or "Search start refused"),
        )


    def complete_search_launcher(self, result: SearchLauncherOpenResult) -> RuntimeHandoffSnapshot:
        if self._snapshot.selected_runtime_id and result.runtime_id != self._snapshot.selected_runtime_id:
            raise ValueError("search launcher result runtime identity mismatch")
        return self._publish(
            busy=False,
            stage="search-launcher-opened" if result.opened else "search-launcher-refused",
            message=result.message or ("Search Launcher opened" if result.opened else "Search Launcher open refused"),
            error=None if result.opened else (result.message or "Search Launcher open refused"),
        )

    def fail(self, error: BaseException | str) -> RuntimeHandoffSnapshot:
        text = str(error)
        return self._publish(busy=False, stage="failed", message=text, error=text)


__all__ = ["ExperimentRuntimeHandoffController", "ExperimentRuntimeHandoffPort"]
