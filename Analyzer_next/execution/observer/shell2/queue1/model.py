"""Immutable queue contracts for OL2-QUEUE1."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from Analyzer_next.execution.observer.shell2.config1.model import PreparedConfiguration


class QueueItemStatus(str, Enum):
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"

    @property
    def terminal(self) -> bool:
        return self in {
            QueueItemStatus.COMPLETED,
            QueueItemStatus.FAILED,
            QueueItemStatus.CANCELLED,
            QueueItemStatus.RECOVERY_REQUIRED,
        }


class QueuePhase(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    BLOCKED = "BLOCKED"
    FINISHED = "FINISHED"


@dataclass(frozen=True, slots=True)
class QueueItem:
    queue_id: str
    prepared: PreparedConfiguration
    status: QueueItemStatus = QueueItemStatus.WAITING
    retry_of: str | None = None
    execution_id: str | None = None
    process_identity: str | None = None
    telemetry_run_id: str | None = None
    exit_code: int | None = None
    error: str | None = None

    @property
    def rule_id(self) -> int:
        return self.prepared.run_spec.rule_id

    @property
    def mode(self) -> str:
        return self.prepared.run_spec.mode


def retry_leaf_items(items: Iterable[QueueItem]) -> tuple[QueueItem, ...]:
    """Return effective Queue rows after retry-lineage supersession.

    Retry sources remain in durable Queue/history for provenance, but a child
    clone is the effective execution row for terminal lifecycle and scientific
    refresh decisions.  Chained retries naturally resolve to the latest leaf.
    """
    rows = tuple(items)
    superseded = {
        str(getattr(item, "retry_of", None))
        for item in rows
        if str(getattr(item, "retry_of", None) or "").strip()
    }
    return tuple(item for item in rows if item.queue_id not in superseded)


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    items: tuple[QueueItem, ...] = ()
    active_queue_id: str | None = None
    dispatching: bool = False
    stop_requested: bool = False
    blocked_queue_id: str | None = None
    last_error: str | None = None
    sequence: int = 0
    revision: int = 0

    @property
    def waiting_count(self) -> int:
        return sum(item.status is QueueItemStatus.WAITING for item in self.items)

    @property
    def running_count(self) -> int:
        return sum(item.status is QueueItemStatus.RUNNING for item in self.items)

    @property
    def completed_count(self) -> int:
        return sum(item.status is QueueItemStatus.COMPLETED for item in self.items)

    @property
    def failed_count(self) -> int:
        return sum(item.status is QueueItemStatus.FAILED for item in self.items)

    @property
    def cancelled_count(self) -> int:
        return sum(item.status is QueueItemStatus.CANCELLED for item in self.items)

    @property
    def recovery_count(self) -> int:
        return sum(item.status is QueueItemStatus.RECOVERY_REQUIRED for item in self.items)

    @property
    def terminal_count(self) -> int:
        return sum(item.status.terminal for item in self.items)

    @property
    def phase(self) -> QueuePhase:
        if self.blocked_queue_id is not None:
            return QueuePhase.BLOCKED
        if self.stop_requested and self.active_queue_id is not None:
            return QueuePhase.STOPPING
        if self.dispatching or self.active_queue_id is not None:
            return QueuePhase.RUNNING
        if self.waiting_count:
            return QueuePhase.READY
        if not self.items:
            return QueuePhase.IDLE
        return QueuePhase.FINISHED


__all__ = ["QueueItem", "QueueItemStatus", "QueuePhase", "QueueSnapshot", "retry_leaf_items"]
