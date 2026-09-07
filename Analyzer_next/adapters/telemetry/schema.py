"""Read-side SQLite schema validation and channel metadata."""
from __future__ import annotations

import sqlite3

from Analyzer_next.core.telemetry.contracts import TelemetryQueryError
from Analyzer_next.core.telemetry.schema_contracts import (
    TelemetrySchemaContractError,
)
from Analyzer_next.core.telemetry.schema_validation import (
    require_compatible_schema,
)

from .schema_catalog import TELEMETRY_SCHEMA_CONTRACT
from .schema_inspector import inspect_schema


SQLITE_SCHEMA_VERSION = TELEMETRY_SCHEMA_CONTRACT.expected_version
REQUIRED_TABLES = TELEMETRY_SCHEMA_CONTRACT.required_tables

CHANNEL_TABLES = {
    "sample": ("samples", "sample_id"),
    "samples": ("samples", "sample_id"),
    "event": ("events", "event_id"),
    "events": ("events", "event_id"),
    "chronicle": ("chronicle", "chronicle_id"),
    "pressure": ("pressure", "pressure_id"),
}


def validate_read_schema(connection: sqlite3.Connection) -> None:
    """Validate structural and migration-history assumptions used by queries."""
    snapshot = inspect_schema(connection, TELEMETRY_SCHEMA_CONTRACT)
    try:
        require_compatible_schema(
            TELEMETRY_SCHEMA_CONTRACT,
            snapshot,
            require_current=True,
            verify_history=True,
        )
    except TelemetrySchemaContractError as exc:
        raise TelemetryQueryError(str(exc)) from exc


def canonical_channel(channel: str) -> str:
    normalized = str(channel).strip().lower()
    return {"samples": "sample", "events": "event"}.get(
        normalized,
        normalized,
    )


def resolve_channel(channel: str) -> tuple[str, str]:
    normalized = str(channel).strip().lower()
    if normalized not in CHANNEL_TABLES:
        raise TelemetryQueryError(f"Unknown channel: {channel!r}")
    return CHANNEL_TABLES[normalized]
