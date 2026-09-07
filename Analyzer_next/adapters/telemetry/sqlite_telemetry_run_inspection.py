"""Read-only SQLite implementation of Stage 7.5 run inspection."""
from __future__ import annotations

import sqlite3

from Analyzer_next.core.telemetry.telemetry_run_inspection import (
    TelemetryRunInspection,
)

from .connection import connect_database


class SQLiteTelemetryRunInspectionRepository:
    def __init__(self, database_path) -> None:
        self.database_path = database_path

    def inspect_run(self, run_id: str) -> TelemetryRunInspection:
        counts: dict[str, int] = {}
        run_row = None
        run_id_found = False
        connection = connect_database(
            self.database_path,
            read_only=True,
        )
        try:
            tables = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                )
            )
            for table in tables:
                safe = table.replace('"', '""')
                try:
                    count = connection.execute(
                        f'SELECT COUNT(*) FROM "{safe}"'
                    ).fetchone()[0]
                except sqlite3.Error:
                    continue
                counts[table] = int(count)

            if "runs" in tables:
                columns = tuple(
                    str(row[1])
                    for row in connection.execute(
                        'PRAGMA table_info("runs")'
                    )
                )
                if "run_id" in columns:
                    row = connection.execute(
                        'SELECT * FROM "runs" '
                        "WHERE run_id = ? LIMIT 1",
                        (run_id,),
                    ).fetchone()
                    if row is not None:
                        run_row = dict(row)
                        run_id_found = True
        finally:
            connection.close()
        return TelemetryRunInspection(
            tables=tables,
            counts=counts,
            run_row=run_row,
            run_id_found=run_id_found,
        )


__all__ = ["SQLiteTelemetryRunInspectionRepository"]
