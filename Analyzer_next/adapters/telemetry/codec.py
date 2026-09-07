"""SQLite row decoding for the Telemetry read adapter."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from Analyzer_next.core.telemetry.contracts import (
    RunSummary,
    TelemetryQueryError,
)


def decode_payload(
    value: str | None,
    *,
    table: str,
    row_id: Any,
) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise TelemetryQueryError(
            f"Invalid JSON in {table} row {row_id}: {exc}"
        ) from exc
    if not isinstance(decoded, dict):
        raise TelemetryQueryError(
            f"Expected JSON object in {table} row {row_id}"
        )
    return decoded


def run_from_row(row: sqlite3.Row) -> RunSummary:
    metadata = decode_payload(
        row["metadata_json"],
        table="runs",
        row_id=row["run_id"],
    )
    return RunSummary(
        run_id=row["run_id"],
        rule_id=row["rule_id"],
        world_id=row["world_id"],
        observer_version=row["observer_version"],
        status=row["status"],
        started_at_utc=row["started_at_utc"],
        finished_at_utc=row["finished_at_utc"],
        final_tick=row["final_tick"],
        samples_count=int(row["samples_count"]),
        events_count=int(row["events_count"]),
        chronicle_count=int(row["chronicle_count"]),
        pressure_count=int(row["pressure_count"]),
        source_path=row["source_path"],
        metadata=metadata,
    )
