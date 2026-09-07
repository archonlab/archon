#!/usr/bin/env python3
"""Telemetry router for Project ARCHON.

Observer produces channel payloads. Telemetry fans each payload out to every
configured writer. Writers own persistence details such as CSV or SQLite.

Supported channels:
- sample
- event
- chronicle
- pressure

The router does not transform scientific values. It coordinates writer
lifecycle, error handling, and lightweight delivery statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any, Iterable, Mapping


class TelemetryError(RuntimeError):
    """Base error for Telemetry routing and lifecycle failures."""


class TelemetryClosedError(TelemetryError):
    """Raised when data is sent after Telemetry.close()."""


class TelemetryWriterError(TelemetryError):
    """Raised when one or more writers fail."""

    def __init__(
        self,
        message: str,
        *,
        failures: tuple["WriterFailure", ...] = (),
    ) -> None:
        super().__init__(message)
        self.failures = failures


class ErrorPolicy(str, Enum):
    """How Telemetry handles writer failures."""

    RAISE = "raise"
    CONTINUE = "continue"


@dataclass(frozen=True, slots=True)
class WriterFailure:
    """One failed writer operation."""

    writer_name: str
    operation: str
    channel: str | None
    error_type: str
    error_message: str


@dataclass(slots=True)
class _WriterState:
    writer: Any
    name: str
    enabled: bool = True
    writes_attempted: int = 0
    writes_succeeded: int = 0
    writes_skipped: int = 0
    errors: int = 0
    flushes: int = 0
    closes: int = 0
    last_error: WriterFailure | None = None
    channel_successes: dict[str, int] = field(
        default_factory=lambda: {
            "sample": 0,
            "event": 0,
            "chronicle": 0,
            "pressure": 0,
        }
    )


class Telemetry:
    """Route Observer telemetry to one or more persistence writers.

    Writers may implement any subset of:

    - write_sample(**payload)
    - write_event(**payload)
    - write_chronicle(**payload)
    - write_pressure(**payload)
    - flush()
    - close()
    - stats()

    A missing channel method is an intentional skip. A channel method returning
    ``False`` is also counted as skipped, which supports disabled writer
    channels.
    """

    CHANNEL_METHODS = {
        "sample": "write_sample",
        "event": "write_event",
        "chronicle": "write_chronicle",
        "pressure": "write_pressure",
    }

    def __init__(
        self,
        writers: Iterable[Any] | None = None,
        *,
        error_policy: ErrorPolicy | str = ErrorPolicy.RAISE,
        disable_writer_after_error: bool = False,
    ) -> None:
        try:
            self.error_policy = ErrorPolicy(error_policy)
        except ValueError as exc:
            raise TelemetryError(
                f"Unknown error_policy: {error_policy!r}"
            ) from exc

        self.disable_writer_after_error = bool(
            disable_writer_after_error
        )
        self._closed = False
        self._lock = RLock()
        self._writers: list[_WriterState] = []
        self._channel_attempts = {
            channel: 0 for channel in self.CHANNEL_METHODS
        }
        self._channel_deliveries = {
            channel: 0 for channel in self.CHANNEL_METHODS
        }
        self._channel_skips = {
            channel: 0 for channel in self.CHANNEL_METHODS
        }
        self._failures: list[WriterFailure] = []

        for writer in writers or ():
            self.add_writer(writer)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def writers(self) -> tuple[Any, ...]:
        return tuple(state.writer for state in self._writers)

    @property
    def failures(self) -> tuple[WriterFailure, ...]:
        return tuple(self._failures)

    def add_writer(
        self,
        writer: Any,
        *,
        name: str | None = None,
        enabled: bool = True,
    ) -> None:
        if writer is None:
            raise TelemetryError("writer must not be None")

        with self._lock:
            self._ensure_open()
            if any(state.writer is writer for state in self._writers):
                raise TelemetryError(
                    "The same writer object is already attached"
                )

            writer_name = (
                str(name).strip()
                if name is not None
                else type(writer).__name__
            )
            if not writer_name:
                raise TelemetryError("writer name must not be empty")

            self._writers.append(
                _WriterState(
                    writer=writer,
                    name=writer_name,
                    enabled=bool(enabled),
                )
            )

    def remove_writer(
        self,
        writer: Any,
        *,
        close: bool = False,
    ) -> bool:
        with self._lock:
            self._ensure_open()
            for index, state in enumerate(self._writers):
                if state.writer is not writer:
                    continue

                if close:
                    self._call_lifecycle(
                        state,
                        operation="close",
                        channel=None,
                    )
                self._writers.pop(index)
                return True
        return False

    def enable_writer(
        self,
        writer: Any,
        enabled: bool = True,
    ) -> bool:
        with self._lock:
            self._ensure_open()
            for state in self._writers:
                if state.writer is writer:
                    state.enabled = bool(enabled)
                    return True
        return False

    def sample(self, **kwargs: Any) -> int:
        return self._dispatch("sample", kwargs)

    def event(self, **kwargs: Any) -> int:
        return self._dispatch("event", kwargs)

    def chronicle(self, **kwargs: Any) -> int:
        return self._dispatch("chronicle", kwargs)

    def pressure(self, **kwargs: Any) -> int:
        return self._dispatch("pressure", kwargs)

    def emit(
        self,
        channel: str,
        payload: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> int:
        if channel not in self.CHANNEL_METHODS:
            raise TelemetryError(
                f"Unknown telemetry channel: {channel!r}"
            )

        row = dict(payload or {})
        row.update(kwargs)
        return self._dispatch(channel, row)

    def flush(self) -> None:
        """Flush every enabled writer that implements ``flush``."""

        with self._lock:
            self._ensure_open()
            failures = []
            for state in self._writers:
                if not state.enabled:
                    continue
                failure = self._call_lifecycle(
                    state,
                    operation="flush",
                    channel=None,
                )
                if failure is not None:
                    failures.append(failure)

            self._raise_if_required(
                "Telemetry flush failed",
                failures,
            )

    def close(self) -> None:
        """Flush and close all writers. Safe to call repeatedly."""

        with self._lock:
            if self._closed:
                return

            failures: list[WriterFailure] = []

            for state in self._writers:
                if not state.enabled:
                    continue
                failure = self._call_lifecycle(
                    state,
                    operation="flush",
                    channel=None,
                )
                if failure is not None:
                    failures.append(failure)

            for state in reversed(self._writers):
                failure = self._call_lifecycle(
                    state,
                    operation="close",
                    channel=None,
                )
                if failure is not None:
                    failures.append(failure)

            self._closed = True
            self._raise_if_required(
                "Telemetry close failed",
                failures,
            )

    def stats(self) -> dict[str, Any]:
        """Return routing and nested writer diagnostics."""

        with self._lock:
            writer_stats = []

            for state in self._writers:
                nested = None
                method = getattr(state.writer, "stats", None)
                if callable(method):
                    try:
                        nested = method()
                    except Exception as exc:
                        nested = {
                            "stats_error": (
                                f"{type(exc).__name__}: {exc}"
                            )
                        }

                writer_stats.append(
                    {
                        "name": state.name,
                        "type": type(state.writer).__name__,
                        "enabled": state.enabled,
                        "writes_attempted": state.writes_attempted,
                        "writes_succeeded": state.writes_succeeded,
                        "writes_skipped": state.writes_skipped,
                        "errors": state.errors,
                        "flushes": state.flushes,
                        "closes": state.closes,
                        "channel_successes": dict(
                            state.channel_successes
                        ),
                        "last_error": (
                            {
                                "operation": state.last_error.operation,
                                "channel": state.last_error.channel,
                                "error_type": state.last_error.error_type,
                                "error_message": (
                                    state.last_error.error_message
                                ),
                            }
                            if state.last_error is not None
                            else None
                        ),
                        "writer_stats": nested,
                    }
                )

            return {
                "closed": self._closed,
                "error_policy": self.error_policy.value,
                "disable_writer_after_error": (
                    self.disable_writer_after_error
                ),
                "writer_count": len(self._writers),
                "channel_attempts": dict(
                    self._channel_attempts
                ),
                "channel_deliveries": dict(
                    self._channel_deliveries
                ),
                "channel_skips": dict(
                    self._channel_skips
                ),
                "failure_count": len(self._failures),
                "writers": writer_stats,
            }

    def __enter__(self) -> "Telemetry":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _dispatch(
        self,
        channel: str,
        payload: Mapping[str, Any],
    ) -> int:
        method_name = self.CHANNEL_METHODS[channel]

        with self._lock:
            self._ensure_open()
            self._channel_attempts[channel] += 1

            deliveries = 0
            failures: list[WriterFailure] = []

            for state in self._writers:
                if not state.enabled:
                    state.writes_skipped += 1
                    self._channel_skips[channel] += 1
                    continue

                method = getattr(
                    state.writer,
                    method_name,
                    None,
                )
                if not callable(method):
                    state.writes_skipped += 1
                    self._channel_skips[channel] += 1
                    continue

                state.writes_attempted += 1
                try:
                    accepted = method(**dict(payload))
                except Exception as exc:
                    failures.append(
                        self._record_failure(
                            state,
                            operation=method_name,
                            channel=channel,
                            exc=exc,
                        )
                    )
                    continue

                if accepted is False:
                    state.writes_skipped += 1
                    self._channel_skips[channel] += 1
                    continue

                state.writes_succeeded += 1
                state.channel_successes[channel] += 1
                self._channel_deliveries[channel] += 1
                deliveries += 1

            self._raise_if_required(
                f"Telemetry {channel} delivery failed",
                failures,
            )
            return deliveries

    def _call_lifecycle(
        self,
        state: _WriterState,
        *,
        operation: str,
        channel: str | None,
    ) -> WriterFailure | None:
        method = getattr(state.writer, operation, None)
        if not callable(method):
            return None

        try:
            method()
        except Exception as exc:
            return self._record_failure(
                state,
                operation=operation,
                channel=channel,
                exc=exc,
            )

        if operation == "flush":
            state.flushes += 1
        elif operation == "close":
            state.closes += 1
        return None

    def _record_failure(
        self,
        state: _WriterState,
        *,
        operation: str,
        channel: str | None,
        exc: Exception,
    ) -> WriterFailure:
        failure = WriterFailure(
            writer_name=state.name,
            operation=operation,
            channel=channel,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        state.errors += 1
        state.last_error = failure
        self._failures.append(failure)

        if self.disable_writer_after_error:
            state.enabled = False

        return failure

    def _raise_if_required(
        self,
        message: str,
        failures: list[WriterFailure],
    ) -> None:
        if (
            failures
            and self.error_policy is ErrorPolicy.RAISE
        ):
            details = "; ".join(
                f"{item.writer_name}.{item.operation}: "
                f"{item.error_type}: {item.error_message}"
                for item in failures
            )
            raise TelemetryWriterError(
                f"{message}: {details}",
                failures=tuple(failures),
            )

    def _ensure_open(self) -> None:
        if self._closed:
            raise TelemetryClosedError(
                "Telemetry is already closed"
            )


__all__ = [
    "TelemetryError",
    "TelemetryClosedError",
    "TelemetryWriterError",
    "ErrorPolicy",
    "WriterFailure",
    "Telemetry",
]
