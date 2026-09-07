"""Native read adapter for raw rows used by storage parity validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from Analyzer_next.core.telemetry.storage_parity import (
    ParitySqliteRow,
    StorageParityError,
)

from .connection import connect_database
from .schema import resolve_channel


class SQLiteParitySource:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        self._connection = connect_database(database_path, read_only=True)
        self._closed = False

    @property
    def database_path(self) -> str:
        return self._database_path

    def get_run(self, run_id: str) -> Mapping[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise StorageParityError(
                f"run_id not found in SQLite: {run_id!r}"
            )
        return dict(row)

    def iter_channel(
        self,
        run_id: str,
        channel: str,
    ) -> Iterator[ParitySqliteRow]:
        table, id_column = resolve_channel(channel)
        cursor = self._connection.execute(
            f"""
            SELECT *
            FROM {table}
            WHERE run_id = ?
            ORDER BY tick, {id_column}
            """,
            (run_id,),
        )

        def rows() -> Iterator[ParitySqliteRow]:
            for row in cursor:
                try:
                    payload = json.loads(row["payload_json"])
                except json.JSONDecodeError as exc:
                    raise StorageParityError(
                        f"Invalid payload_json in {table}: {exc}"
                    ) from exc
                yield ParitySqliteRow(columns=dict(row), payload=payload)

        return rows()

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True


class SQLiteParitySourceFactory:
    @staticmethod
    def resolve_path(value: str) -> str:
        return str(Path(value).expanduser().resolve())

    @staticmethod
    def open(database_path: str) -> SQLiteParitySource:
        if not Path(database_path).exists():
            raise StorageParityError(
                f"SQLite database does not exist: {database_path}"
            )
        return SQLiteParitySource(database_path)


__all__ = ["SQLiteParitySource", "SQLiteParitySourceFactory"]
