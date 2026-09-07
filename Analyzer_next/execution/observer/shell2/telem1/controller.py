"""Toolkit-independent freshness and identity controller for OL2 live telemetry."""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from Analyzer_next.core.telemetry.contracts import TelemetryQueryError
from Analyzer_next.core.telemetry.live import LiveTelemetryFrame, LiveTelemetryPort
from Analyzer_next.execution.observer.state import TelemetryState


Clock = Callable[[], float]
TERMINAL_RUN_STATUSES = frozenset({"completed", "stopped", "failed", "imported"})


@dataclass(frozen=True, slots=True)
class LiveTelemetryPoll:
    run_id: str
    state: TelemetryState
    frame: LiveTelemetryFrame | None
    age_seconds: float | None
    error: str | None = None


class LiveTelemetryController:
    """Poll one run identity and derive LIVE/STALE/ERROR without changing run state."""

    def __init__(
        self,
        port: LiveTelemetryPort,
        *,
        stale_after_seconds: float = 3.0,
        clock: Clock = time.monotonic,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be > 0")
        self.port = port
        self.stale_after_seconds = float(stale_after_seconds)
        self.clock = clock
        self._run_id: str | None = None
        self._last_tick: int | None = None
        self._last_sample_identity: tuple[object, ...] | None = None
        self._last_change_at: float | None = None
        self._last_frame: LiveTelemetryFrame | None = None
        self._read_interrupted = False

    def poll(self, run_id: str) -> LiveTelemetryPoll:
        normalized = str(run_id).strip()
        if not normalized:
            return LiveTelemetryPoll(
                run_id="",
                state=TelemetryState.ERROR,
                frame=None,
                age_seconds=None,
                error="run_id is required",
            )
        if normalized != self._run_id:
            self._reset_identity(normalized)

        now = self.clock()
        try:
            frame = self.port.read_frame(normalized, history_limit=8)
        except TelemetryQueryError as exc:
            self._read_interrupted = True
            return LiveTelemetryPoll(
                run_id=normalized,
                state=TelemetryState.ERROR,
                frame=self._last_frame,
                age_seconds=self._age(now),
                error=str(exc),
            )

        if frame is None or frame.latest is None:
            return LiveTelemetryPoll(
                run_id=normalized,
                state=TelemetryState.CONNECTING,
                frame=self._last_frame,
                age_seconds=self._age(now),
            )
        if frame.run_id != normalized or frame.latest.run_id != normalized:
            return LiveTelemetryPoll(
                run_id=normalized,
                state=TelemetryState.ERROR,
                frame=self._last_frame,
                age_seconds=self._age(now),
                error="telemetry run identity mismatch",
            )

        latest_tick = frame.latest.tick
        sample_identity = (
            latest_tick,
            frame.latest.fields.get("sample_id"),
            frame.latest.created_at_utc,
        )
        if self._read_interrupted or self._last_sample_identity != sample_identity:
            self._last_tick = latest_tick
            self._last_sample_identity = sample_identity
            self._last_change_at = now
        self._read_interrupted = False
        self._last_frame = frame
        age = self._age(now) or 0.0

        if frame.run_status.lower() in TERMINAL_RUN_STATUSES:
            state = TelemetryState.CLOSED
        elif age >= self.stale_after_seconds:
            state = TelemetryState.STALE
        else:
            state = TelemetryState.LIVE
        return LiveTelemetryPoll(
            run_id=normalized,
            state=state,
            frame=frame,
            age_seconds=age,
        )

    def _reset_identity(self, run_id: str) -> None:
        self._run_id = run_id
        self._last_tick = None
        self._last_sample_identity = None
        self._last_change_at = None
        self._last_frame = None
        self._read_interrupted = False

    def _age(self, now: float) -> float | None:
        if self._last_change_at is None:
            return None
        return max(0.0, now - self._last_change_at)

    def close(self) -> None:
        self.port.close()


__all__ = ["LiveTelemetryController", "LiveTelemetryPoll"]
