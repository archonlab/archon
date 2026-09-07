"""Toolkit/storage-independent campaign dispatcher for OL2-QUEUE1."""
from __future__ import annotations

from dataclasses import replace
import threading

from Analyzer_next.execution.observer.shell2.config1.model import PreparedConfiguration
from Analyzer_next.execution.observer.shell2.control1.controller import ObserverControlController
from Analyzer_next.execution.observer.state import RunState

from .contracts import (
    FailClosedQueueAuthorization,
    MemoryQueueRepository,
    QueueAuthorizationPort,
    QueueRepository,
)
from .model import QueueItem, QueueItemStatus, QueueSnapshot


_TERMINAL_RUNS = {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}


class ObserverQueueController:
    """Own ordering/recovery while CONTROL1 remains the sole process owner."""

    def __init__(
        self,
        control: ObserverControlController,
        *,
        repository: QueueRepository | None = None,
        authorization: QueueAuthorizationPort | None = None,
        lifecycle=None,
    ) -> None:
        self.control = control
        self.repository = repository or MemoryQueueRepository()
        self.authorization = authorization or FailClosedQueueAuthorization()
        self.lifecycle = lifecycle
        self._lock = threading.RLock()
        loaded = self.repository.load()
        self._snapshot = loaded or QueueSnapshot()
        self._reconcile_startup_locked()

    @property
    def snapshot(self) -> QueueSnapshot:
        with self._lock:
            return self._snapshot

    def _publish(self, **changes) -> QueueSnapshot:
        self._snapshot = replace(
            self._snapshot,
            **changes,
            revision=self._snapshot.revision + 1,
        )
        self.repository.save(self._snapshot)
        return self._snapshot

    def _replace_item(self, queue_id: str, **changes) -> QueueItem:
        items = list(self._snapshot.items)
        for index, item in enumerate(items):
            if item.queue_id == queue_id:
                updated = replace(item, **changes)
                items[index] = updated
                self._publish(items=tuple(items))
                return updated
        raise RuntimeError(f"queue item disappeared: {queue_id}")

    def _record_terminal(self, item: QueueItem) -> None:
        if item.status.terminal:
            self.repository.record_terminal(item)

    def _lifecycle_queued(self, items) -> None:
        if self.lifecycle is None:
            return
        try:
            self.lifecycle.mark_queued(items)
        except Exception as exc:
            raise RuntimeError(f"authoritative cycle queue transition refused: {exc}") from exc

    def _lifecycle_running(self, item: QueueItem) -> None:
        if self.lifecycle is None:
            return
        try:
            self.lifecycle.mark_running(item)
        except Exception as exc:
            raise RuntimeError(f"authoritative cycle running transition refused: {exc}") from exc

    def _lifecycle_launch_failure(self, item: QueueItem, reason: str) -> None:
        if self.lifecycle is None:
            return
        try:
            self.lifecycle.mark_launch_failure(item, reason)
        except Exception as exc:
            raise RuntimeError(f"authoritative cycle launch-failure transition refused: {exc}") from exc

    def _lifecycle_reconcile_terminal(self, *, runtime_item: QueueItem | None = None) -> None:
        if self.lifecycle is None:
            return
        runtime_id = None
        if runtime_item is not None:
            try:
                context = runtime_item.prepared.run_spec.experimental_context
                execution = context.get("execution_attempt", {}) if isinstance(context, dict) else {}
                if isinstance(execution, dict):
                    runtime_id = execution.get("source_runtime_id")
                if not runtime_id and isinstance(context, dict):
                    runtime_id = context.get("runtime_id")
            except (AttributeError, TypeError, ValueError):
                runtime_id = None
        try:
            self.lifecycle.reconcile_terminal(self._snapshot.items, runtime_id=runtime_id)
        except Exception as exc:
            raise RuntimeError(f"authoritative cycle terminal reconciliation refused: {exc}") from exc

    def _reconcile_startup_locked(self) -> None:
        """Fail closed after launcher restart without touching Observer/evidence.

        A persisted RUNNING row cannot safely reacquire OS process ownership.
        Preserve its identities and evidence pointers, mark it recovery-required,
        keep waiting rows waiting, and never auto-dispatch on startup.
        """
        recovered: list[QueueItem] = []
        changed = bool(
            self._snapshot.dispatching
            or self._snapshot.active_queue_id
            or self._snapshot.stop_requested
            or self._snapshot.blocked_queue_id
        )
        for item in self._snapshot.items:
            if item.status is QueueItemStatus.RUNNING:
                changed = True
                item = replace(
                    item,
                    status=QueueItemStatus.RECOVERY_REQUIRED,
                    error=(
                        "startup reconciliation: prior process ownership is not "
                        "reacquired; inspect evidence and retry by clone if needed"
                    ),
                )
                self._record_terminal(item)
            recovered.append(item)
        if changed:
            self._snapshot = replace(
                self._snapshot,
                items=tuple(recovered),
                active_queue_id=None,
                dispatching=False,
                stop_requested=False,
                blocked_queue_id=None,
                last_error=None,
                revision=self._snapshot.revision + 1,
            )
            self.repository.save(self._snapshot)
            self._lifecycle_reconcile_terminal()

    def enqueue(self, prepared: PreparedConfiguration, *, retry_of: str | None = None) -> QueueSnapshot:
        if not prepared.command:
            raise ValueError("prepared command is empty")
        with self._lock:
            sequence = self._snapshot.sequence + 1
            queue_id = f"OL2-Q-{sequence:04d}"
            item = QueueItem(queue_id=queue_id, prepared=prepared, retry_of=retry_of)
            return self._publish(
                items=self._snapshot.items + (item,),
                sequence=sequence,
                blocked_queue_id=None,
                last_error=None,
            )

    def retry_by_clone(self, queue_id: str) -> QueueSnapshot:
        with self._lock:
            source = self._find(queue_id)
            if not source.status.terminal:
                raise RuntimeError("only terminal queue rows can be retried by clone")
            if source.status is QueueItemStatus.COMPLETED:
                raise RuntimeError(
                    "COMPLETED queue rows cannot be retried; create an explicit new reviewed replication instead"
                )
            can_retry = getattr(self.lifecycle, "can_retry", None)
            if callable(can_retry) and not can_retry(source):
                raise RuntimeError(
                    "authoritative ResearchCycle is already terminal; retry requires a new reviewed cycle"
                )
            return self.enqueue(source.prepared, retry_of=source.queue_id)

    def cancel_waiting(self, queue_id: str) -> QueueSnapshot:
        with self._lock:
            item = self._find(queue_id)
            if item.status is not QueueItemStatus.WAITING:
                raise RuntimeError("only WAITING queue rows can be cancelled")
            updated = self._replace_item(
                queue_id,
                status=QueueItemStatus.CANCELLED,
                error="cancelled before dispatch",
            )
            self._record_terminal(updated)
            self._lifecycle_reconcile_terminal(runtime_item=updated)
            if self._snapshot.blocked_queue_id == queue_id:
                self._publish(blocked_queue_id=None, last_error=None)
            return self._snapshot

    def cancel_all_waiting(self) -> QueueSnapshot:
        with self._lock:
            waiting = [item.queue_id for item in self._snapshot.items if item.status is QueueItemStatus.WAITING]
            for queue_id in waiting:
                updated = self._replace_item(
                    queue_id,
                    status=QueueItemStatus.CANCELLED,
                    error="queue cleared before dispatch",
                )
                self._record_terminal(updated)
                self._lifecycle_reconcile_terminal(runtime_item=updated)
            self._publish(blocked_queue_id=None, last_error=None)
            return self._snapshot

    def move_waiting(self, queue_id: str, direction: int) -> QueueSnapshot:
        if direction not in {-1, 1}:
            raise ValueError("direction must be -1 or 1")
        with self._lock:
            items = list(self._snapshot.items)
            index = next((i for i, item in enumerate(items) if item.queue_id == queue_id), None)
            if index is None:
                raise KeyError(queue_id)
            if items[index].status is not QueueItemStatus.WAITING:
                raise RuntimeError("only WAITING queue rows can be reordered")
            candidates = range(index - 1, -1, -1) if direction < 0 else range(index + 1, len(items))
            other = next((i for i in candidates if items[i].status is QueueItemStatus.WAITING), None)
            if other is None:
                return self._snapshot
            items[index], items[other] = items[other], items[index]
            return self._publish(items=tuple(items), blocked_queue_id=None, last_error=None)

    def start(self) -> QueueSnapshot:
        with self._lock:
            if self._snapshot.dispatching:
                raise RuntimeError("queue is already dispatching")
            if self.control.process_active:
                raise RuntimeError("CONTROL1 already owns an active Observer process")
            waiting_items = tuple(
                item for item in self._snapshot.items
                if item.status is QueueItemStatus.WAITING
            )
            if not waiting_items:
                raise RuntimeError("queue has no waiting runs")
            self._lifecycle_queued(waiting_items)
            self._publish(
                dispatching=True,
                stop_requested=False,
                blocked_queue_id=None,
                last_error=None,
            )
            self._launch_next_locked()
            return self._snapshot

    def _launch_next_locked(self) -> None:
        """Launch the FIFO head and consume fail-closed start failures safely."""
        while self._snapshot.dispatching and self._snapshot.active_queue_id is None:
            next_item = next(
                (item for item in self._snapshot.items if item.status is QueueItemStatus.WAITING),
                None,
            )
            if next_item is None:
                self._publish(dispatching=False, stop_requested=False)
                return

            decision = self.authorization.authorize(next_item.prepared)
            if not decision.authorized:
                message = f"{decision.code}: {decision.reason}"
                self._publish(
                    dispatching=False,
                    blocked_queue_id=next_item.queue_id,
                    last_error=message,
                )
                return

            try:
                self._lifecycle_running(next_item)
                if next_item.retry_of is None:
                    control_snapshot = self.control.start(next_item.prepared)
                else:
                    control_snapshot = self.control.start(
                        next_item.prepared,
                        retry_of=next_item.retry_of,
                    )
            except (RuntimeError, ValueError) as exc:
                message = f"CONTROL1 refused queue head: {type(exc).__name__}: {exc}"
                try:
                    self._lifecycle_launch_failure(next_item, message)
                except RuntimeError as lifecycle_exc:
                    message += f"; {lifecycle_exc}"
                self._publish(dispatching=False, last_error=message)
                return

            run = control_snapshot.run
            if run is None:
                updated = self._replace_item(
                    next_item.queue_id,
                    status=QueueItemStatus.FAILED,
                    error="CONTROL1 returned no RunRecord",
                )
                self._record_terminal(updated)
                continue

            if run.state in _TERMINAL_RUNS:
                updated = self._replace_item(
                    next_item.queue_id,
                    status=self._status_for_run_state(run.state),
                    execution_id=run.run_id,
                    process_identity=run.process_identity,
                    telemetry_run_id=control_snapshot.telemetry_run_id,
                    exit_code=run.exit_code,
                    error=run.error,
                )
                self._record_terminal(updated)
                self._lifecycle_reconcile_terminal(runtime_item=updated)
                continue

            self._replace_item(
                next_item.queue_id,
                status=QueueItemStatus.RUNNING,
                execution_id=run.run_id,
                process_identity=run.process_identity,
                telemetry_run_id=control_snapshot.telemetry_run_id,
                exit_code=run.exit_code,
                error=run.error,
            )
            self._publish(active_queue_id=next_item.queue_id)
            return

    @staticmethod
    def _status_for_run_state(state: RunState) -> QueueItemStatus:
        if state is RunState.COMPLETED:
            return QueueItemStatus.COMPLETED
        if state is RunState.CANCELLED:
            return QueueItemStatus.CANCELLED
        return QueueItemStatus.FAILED

    def poll(self) -> QueueSnapshot:
        """Synchronize the active row with CONTROL1 and advance on terminal state."""
        with self._lock:
            queue_id = self._snapshot.active_queue_id
            if queue_id is None:
                if self._snapshot.dispatching:
                    self._launch_next_locked()
                return self._snapshot

            control_snapshot = self.control.snapshot
            run = control_snapshot.run
            if run is None:
                return self._snapshot
            item = self._find(queue_id)
            if item.execution_id is not None and run.run_id != item.execution_id:
                # Never steal a later/manual CONTROL1 identity after a restart or
                # external action. Queue remains fail-closed until reconciled.
                self._publish(
                    dispatching=False,
                    blocked_queue_id=queue_id,
                    last_error=(
                        f"CONTROL1 execution identity mismatch: expected {item.execution_id}, "
                        f"got {run.run_id}"
                    ),
                )
                return self._snapshot

            self._replace_item(
                queue_id,
                process_identity=run.process_identity,
                telemetry_run_id=control_snapshot.telemetry_run_id,
                exit_code=run.exit_code,
                error=run.error,
            )
            if run.state not in _TERMINAL_RUNS:
                return self._snapshot

            updated = self._replace_item(
                queue_id,
                status=self._status_for_run_state(run.state),
                process_identity=run.process_identity,
                telemetry_run_id=control_snapshot.telemetry_run_id,
                exit_code=run.exit_code,
                error=run.error,
            )
            self._record_terminal(updated)
            self._lifecycle_reconcile_terminal(runtime_item=updated)
            self._publish(active_queue_id=None)
            if self._snapshot.dispatching and not self._snapshot.stop_requested:
                self._launch_next_locked()
            else:
                self._publish(dispatching=False, stop_requested=False)
            return self._snapshot

    def stop(self) -> QueueSnapshot:
        """Cancel waiting rows and stop the active run through CONTROL1 only."""
        with self._lock:
            for item in tuple(self._snapshot.items):
                if item.status is QueueItemStatus.WAITING:
                    updated = self._replace_item(
                        item.queue_id,
                        status=QueueItemStatus.CANCELLED,
                        error="queue stopped before dispatch",
                    )
                    self._record_terminal(updated)
                    self._lifecycle_reconcile_terminal(runtime_item=updated)
            active = self._snapshot.active_queue_id
            self._publish(
                dispatching=False,
                stop_requested=active is not None,
                blocked_queue_id=None,
                last_error=None,
            )
            if active is not None and self.control.process_active:
                self.control.stop()
            elif active is None:
                self._publish(stop_requested=False)
            return self._snapshot


    def close(
        self,
        *,
        grace_seconds: float = 2.0,
        kill_seconds: float = 1.0,
    ) -> bool:
        """Stop dispatch and reconcile the owned execution before GUI exit.

        Waiting rows remain durable and WAITING for a later explicit Queue start.
        An active CONTROL1 process is stopped through its existing owner and the
        resulting terminal state is persisted before the launcher is destroyed.
        If process release cannot be confirmed, keep the active row unresolved so
        startup recovery can fail closed instead of fabricating completion.
        """
        with self._lock:
            active = self._snapshot.active_queue_id
            if self._snapshot.dispatching or active is not None:
                self._publish(
                    dispatching=False,
                    stop_requested=active is not None,
                    blocked_queue_id=None,
                    last_error=None,
                )

        closer = getattr(self.control, "close", None)
        if callable(closer):
            try:
                clean = bool(
                    closer(
                        grace_seconds=grace_seconds,
                        kill_seconds=kill_seconds,
                    )
                )
            except TypeError:
                # Deterministic compatibility adapters may expose the legacy
                # no-argument close() signature.
                result = closer()
                clean = True if result is None else bool(result)
        else:
            clean = not bool(getattr(self.control, "process_active", False))

        with self._lock:
            if active is not None:
                # CONTROL1 finalization owns RunState. Queue only projects that
                # already-terminal identity into durable queue state.
                try:
                    self.poll()
                except RuntimeError as exc:
                    self._publish(last_error=f"launcher close reconciliation refused: {exc}")
                    clean = False
            if self._snapshot.active_queue_id is not None:
                self._publish(
                    dispatching=False,
                    stop_requested=False,
                    last_error=(
                        self._snapshot.last_error
                        or "launcher close could not confirm terminal Observer ownership release"
                    ),
                )
                return False
            if self._snapshot.stop_requested:
                self._publish(stop_requested=False)
            return clean and not bool(getattr(self.control, "process_active", False))

    def _find(self, queue_id: str) -> QueueItem:
        for item in self._snapshot.items:
            if item.queue_id == queue_id:
                return item
        raise KeyError(queue_id)


__all__ = ["ObserverQueueController"]
