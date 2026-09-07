"""Ports used by the OL2-QUEUE1 application service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from Analyzer_next.execution.observer.shell2.config1.model import PreparedConfiguration

from .model import QueueItem, QueueSnapshot


@dataclass(frozen=True, slots=True)
class QueueAuthorizationDecision:
    authorized: bool
    code: str
    reason: str


class QueueAuthorizationPort(Protocol):
    def authorize(self, prepared: PreparedConfiguration) -> QueueAuthorizationDecision: ...


class QueueRepository(Protocol):
    def load(self) -> QueueSnapshot | None: ...
    def save(self, snapshot: QueueSnapshot) -> None: ...
    def record_terminal(self, item: QueueItem) -> None: ...


class FailClosedQueueAuthorization:
    """Allow explicit manual modes; reject unbound/unknown authorization modes.

    CONFIG1 currently has no experiment authorization receipt port. QUEUE1 must
    therefore refuse experimental dispatch rather than infer authorization from
    a valid command preview. Future production-campaign modes are also rejected
    by default because they are not in the manual allow-list.
    """

    _MANUAL_MODES = frozenset({"canonical", "canonical_queue", "required_control"})

    def authorize(self, prepared: PreparedConfiguration) -> QueueAuthorizationDecision:
        mode = prepared.run_spec.mode.strip()
        if mode in self._MANUAL_MODES:
            return QueueAuthorizationDecision(
                authorized=True,
                code="MANUAL_EXPLICIT_QUEUE",
                reason="Mode is covered by explicit user queue action.",
            )
        if mode == "experimental":
            return QueueAuthorizationDecision(
                authorized=False,
                code="EXPERIMENT_AUTHORIZATION_UNBOUND",
                reason=(
                    "Experimental queue dispatch requires a verified authorization "
                    "receipt port; CONFIG1 validation alone is not authorization."
                ),
            )
        return QueueAuthorizationDecision(
            authorized=False,
            code="UNKNOWN_PRODUCTION_AUTHORIZATION",
            reason=f"No fail-closed queue authorization policy exists for mode {mode!r}.",
        )


class MemoryQueueRepository:
    """Deterministic test repository; stores no files and rewrites no evidence."""

    def __init__(self, initial: QueueSnapshot | None = None) -> None:
        self.current = initial
        self.saves: list[QueueSnapshot] = []
        self.terminal_records: dict[str, QueueItem] = {}

    def load(self) -> QueueSnapshot | None:
        return self.current

    def save(self, snapshot: QueueSnapshot) -> None:
        self.current = snapshot
        self.saves.append(snapshot)

    def record_terminal(self, item: QueueItem) -> None:
        self.terminal_records.setdefault(item.queue_id, item)


__all__ = [
    "FailClosedQueueAuthorization",
    "MemoryQueueRepository",
    "QueueAuthorizationDecision",
    "QueueAuthorizationPort",
    "QueueRepository",
]
