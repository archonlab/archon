"""Application service for the Stage 7.5 telemetry inspection contract."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.telemetry.telemetry_run_inspection import (
    TelemetryRunInspectionPort,
)


def inspect_telemetry_run(
    *,
    repository: TelemetryRunInspectionPort,
    run_id: str,
) -> dict[str, Any]:
    snapshot = repository.inspect_run(run_id)
    return {
        "exists": True,
        "tables": list(snapshot.tables),
        "counts": dict(snapshot.counts),
        "run_row": (
            dict(snapshot.run_row)
            if snapshot.run_row is not None
            else None
        ),
        "run_id_found": snapshot.run_id_found,
    }


__all__ = ["inspect_telemetry_run"]
