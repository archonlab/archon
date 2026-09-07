"""Storage-independent live Telemetry read contract for Observer Launcher 2."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class LiveTelemetrySample:
    """One canonical sample row plus its decoded payload."""

    run_id: str
    tick: int
    fields: Mapping[str, Any]
    payload: Mapping[str, Any]
    created_at_utc: str | None = None

    def value(self, key: str) -> Any:
        if key in self.fields and self.fields[key] is not None:
            return self.fields[key]
        return self.payload.get(key)


@dataclass(frozen=True, slots=True)
class LiveTelemetryFrame:
    """Small chronological window used to project cards and state safely."""

    run_id: str
    run_status: str
    final_tick: int | None
    samples: tuple[LiveTelemetrySample, ...]

    @property
    def latest(self) -> LiveTelemetrySample | None:
        return self.samples[-1] if self.samples else None


class LiveTelemetryPort(Protocol):
    """Read-only capability consumed by the OL2 presentation/application layer."""

    def read_frame(
        self,
        run_id: str,
        *,
        history_limit: int = 8,
    ) -> LiveTelemetryFrame | None: ...

    def close(self) -> None: ...


__all__ = [
    "LiveTelemetryFrame",
    "LiveTelemetryPort",
    "LiveTelemetrySample",
]
