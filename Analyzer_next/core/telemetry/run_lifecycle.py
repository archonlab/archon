"""Storage-independent write contract for one Telemetry run lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


class TelemetryRunLifecycleError(RuntimeError):
    """Raised when a run cannot be registered or finalized safely."""


@dataclass(frozen=True, slots=True)
class RunRegistration:
    """Values persisted when a Telemetry run is first registered."""

    run_id: str
    rule_id: int | None = None
    world_id: str | None = None
    observer_version: str | None = None
    started_at_utc: str | None = None
    status: str = "running"
    source_path: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunFinalization:
    """Values applied when a Telemetry run reaches a terminal state."""

    run_id: str
    status: str
    final_tick: int | None
    finished_at_utc: str | None = None
    metadata_update: Mapping[str, Any] = field(default_factory=dict)


class TelemetryRunLifecycleRepository(Protocol):
    """Write port whose transaction boundary belongs to the caller."""

    def register_run(self, registration: RunRegistration) -> None: ...

    def finalize_run(self, finalization: RunFinalization) -> None: ...


__all__ = [
    "RunFinalization",
    "RunRegistration",
    "TelemetryRunLifecycleError",
    "TelemetryRunLifecycleRepository",
]
