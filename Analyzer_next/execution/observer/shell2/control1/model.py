"""Immutable OL2-CONTROL1 execution projection."""
from __future__ import annotations

from dataclasses import dataclass

from Analyzer_next.execution.observer.state import RunRecord, RunState


@dataclass(frozen=True, slots=True)
class ControlSnapshot:
    """One Observer process attempt plus discovered canonical telemetry identity."""

    run: RunRecord | None = None
    review_hash: str | None = None
    command: tuple[str, ...] = ()
    telemetry_run_id: str | None = None
    attempt: int = 0
    started_monotonic: float | None = None
    finished_monotonic: float | None = None
    revision: int = 0

    @property
    def active(self) -> bool:
        return bool(
            self.run is not None
            and self.run.state
            in {
                RunState.STARTING,
                RunState.RUNNING,
                RunState.PAUSING,
                RunState.PAUSED,
                RunState.RESUMING,
                RunState.STOPPING,
            }
        )


__all__ = ["ControlSnapshot"]
