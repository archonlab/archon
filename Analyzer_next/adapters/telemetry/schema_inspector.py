"""Read-only SQLite inspection for Telemetry schema contracts."""
from __future__ import annotations

import sqlite3

from Analyzer_next.core.telemetry.schema_contracts import (
    AppliedMigration,
    TelemetrySchemaContract,
    TelemetrySchemaSnapshot,
)


def inspect_schema(
    connection: sqlite3.Connection,
    contract: TelemetrySchemaContract,
) -> TelemetrySchemaSnapshot:
    """Observe schema metadata without applying migrations or mutating data."""
    connection.row_factory = sqlite3.Row
    tables = tuple(sorted(
        str(row["name"])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            """
        )
    ))

    applied: tuple[AppliedMigration, ...] = ()
    if "schema_migrations" in tables:
        applied = tuple(
            AppliedMigration(
                version=int(row["version"]),
                name=str(row["name"]),
                applied_at_utc=str(row["applied_at_utc"]),
                checksum=str(row["checksum"]),
            )
            for row in connection.execute(
                """
                SELECT version, name, applied_at_utc, checksum
                FROM schema_migrations
                ORDER BY version
                """
            )
        )

    database_path = None
    for row in connection.execute("PRAGMA database_list"):
        if row["name"] == "main":
            database_path = row["file"] or None
            break

    json_functions = False
    try:
        row = connection.execute(
            "SELECT json_valid(?) AS valid",
            ('{"ok": true}',),
        ).fetchone()
        json_functions = bool(row["valid"] == 1)
    except sqlite3.DatabaseError:
        json_functions = False

    return TelemetrySchemaSnapshot(
        schema_name=contract.schema_name,
        applied_version=max((item.version for item in applied), default=0),
        database_path=database_path,
        journal_mode=str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
        foreign_keys=bool(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
        json_functions=json_functions,
        tables=tables,
        applied_migrations=applied,
    )
