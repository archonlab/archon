"""Native facade matching the protected Stage 7.5 inspection API."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from Analyzer_next.application.telemetry.telemetry_run_inspection import (
    inspect_telemetry_run,
)

from .sqlite_telemetry_run_inspection import (
    SQLiteTelemetryRunInspectionRepository,
)


def inspect_sqlite(path: Path, run_id: str) -> Dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "tables": [],
            "counts": {},
            "run_row": None,
            "run_id_found": False,
        }
    return inspect_telemetry_run(
        repository=SQLiteTelemetryRunInspectionRepository(path),
        run_id=run_id,
    )


__all__ = ["inspect_sqlite"]
