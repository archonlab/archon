"""Storage-independent contract for read-only telemetry run inspection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class TelemetryRunInspection:
    tables: tuple[str, ...]
    counts: Mapping[str, int]
    run_row: Mapping[str, Any] | None
    run_id_found: bool


class TelemetryRunInspectionPort(Protocol):
    def inspect_run(self, run_id: str) -> TelemetryRunInspection: ...


__all__ = [
    "TelemetryRunInspection",
    "TelemetryRunInspectionPort",
]
