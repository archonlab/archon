"""OL2-QUEUE2 queue-view lifecycle on top of frozen QUEUE1 dispatch semantics."""
from __future__ import annotations

from Analyzer_next.execution.observer.shell2.queue1.controller import ObserverQueueController
from Analyzer_next.execution.observer.shell2.queue1.model import QueueItemStatus, QueueSnapshot


class ObserverQueue2Controller(ObserverQueueController):
    """Add view cleanup without deleting terminal history or changing dispatch."""

    def clear_completed(self) -> QueueSnapshot:
        """Remove only successful COMPLETED rows from launcher-owned Queue state."""
        with self._lock:
            items = tuple(
                item
                for item in self._snapshot.items
                if item.status is not QueueItemStatus.COMPLETED
            )
            if len(items) == len(self._snapshot.items):
                return self._snapshot
            return self._publish(items=items)

    def remove_terminal(self, queue_id: str) -> QueueSnapshot:
        with self._lock:
            item = self._find(queue_id)
            if not item.status.terminal:
                raise RuntimeError("only terminal queue rows can be removed from the active view")
            if item.status is QueueItemStatus.RECOVERY_REQUIRED and not any(
                row.retry_of == queue_id for row in self._snapshot.items
            ):
                raise RuntimeError(
                    "unresolved RECOVERY_REQUIRED row cannot be removed; retry it by clone first"
                )
            items = tuple(row for row in self._snapshot.items if row.queue_id != queue_id)
            return self._publish(
                items=items,
                blocked_queue_id=(
                    None if self._snapshot.blocked_queue_id == queue_id
                    else self._snapshot.blocked_queue_id
                ),
                last_error=(
                    None if self._snapshot.blocked_queue_id == queue_id
                    else self._snapshot.last_error
                ),
            )

    def clear_queue_view(self) -> QueueSnapshot:
        """Cancel WAITING, remove terminal rows, preserve an active RUNNING row.

        QUEUE1 already writes terminal history before this cleanup.  This method
        only changes the launcher-owned active queue snapshot.
        """
        with self._lock:
            for item in tuple(self._snapshot.items):
                if item.status is QueueItemStatus.WAITING:
                    updated = self._replace_item(
                        item.queue_id,
                        status=QueueItemStatus.CANCELLED,
                        error="queue cleared before dispatch",
                    )
                    self._record_terminal(updated)
            retried_sources = {
                row.retry_of for row in self._snapshot.items if row.retry_of
            }
            kept = tuple(
                item
                for item in self._snapshot.items
                if (
                    not item.status.terminal
                    or (
                        item.status is QueueItemStatus.RECOVERY_REQUIRED
                        and item.queue_id not in retried_sources
                    )
                )
            )
            return self._publish(
                items=kept,
                blocked_queue_id=None,
                last_error=None,
            )


__all__ = ["ObserverQueue2Controller"]
