"""Native SQLite sink for the CSV import application service."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from Analyzer_next.core.telemetry.csv_import import CSVImportError

from .connection import connect_database
from .sqlite_writer import SQLiteWriter, SQLiteWriterConfig


class NativeSqliteImportSink:
    def __init__(self, writer: SQLiteWriter) -> None:
        self.writer = writer
        self._methods = {
            "sample": writer.write_sample,
            "event": writer.write_event,
            "chronicle": writer.write_chronicle,
            "pressure": writer.write_pressure,
        }

    def write(self, channel: str, row: Mapping[str, Any]) -> bool:
        return bool(self._methods[channel](**dict(row)))

    def finalize(
        self,
        *,
        status: str,
        final_tick: int | None,
        metadata_update: Mapping[str, Any],
    ) -> None:
        self.writer.finalize(
            status=status,
            final_tick=final_tick,
            metadata_update=metadata_update,
        )

    def abort(self) -> None:
        try:
            self.writer._connection.rollback()
        finally:
            self.writer._connection.close()
            self.writer._closed = True

    def close(self) -> None:
        self.writer._connection.close()
        self.writer._closed = True


class NativeSqliteImportSinkFactory:
    def prepare_existing_run(
        self,
        *,
        database_path: str,
        run_id: str,
        policy: str,
    ) -> None:
        path = Path(database_path)
        if not path.exists():
            if policy == "append":
                raise CSVImportError(
                    f"Cannot append because database does not exist: {path}"
                )
            return

        connection = connect_database(path)
        try:
            row = connection.execute(
                "SELECT run_id FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                if policy == "append":
                    raise CSVImportError(
                        f"Cannot append because run_id does not exist: {run_id}"
                    )
                return
            if policy == "error":
                raise CSVImportError(
                    f"run_id already exists in SQLite: {run_id}"
                )
            if policy == "replace":
                connection.execute(
                    "DELETE FROM runs WHERE run_id = ?",
                    (run_id,),
                )
                connection.commit()
        finally:
            connection.close()

    def open_sink(self, **options: Any) -> NativeSqliteImportSink:
        existing_run_policy = str(options.pop("existing_run_policy"))
        duplicate_policy = str(options.pop("duplicate_policy"))
        batch_size = int(options.pop("batch_size"))
        writer = SQLiteWriter(
            **options,
            config=SQLiteWriterConfig(
                batch_size=batch_size,
                duplicate_sample_policy=duplicate_policy,
                duplicate_pressure_policy=duplicate_policy,
                auto_register_run=(existing_run_policy != "append"),
                finalize_on_close=False,
            ),
        )
        if existing_run_policy == "append":
            row = writer._connection.execute(
                "SELECT run_id FROM runs WHERE run_id = ?",
                (writer.run_id,),
            ).fetchone()
            if row is None:
                raise CSVImportError(
                    f"Append target run_id does not exist: {writer.run_id}"
                )
        return NativeSqliteImportSink(writer)

    def remove_run_quietly(
        self,
        *,
        database_path: str,
        run_id: str,
    ) -> None:
        try:
            connection = connect_database(database_path)
            try:
                connection.execute(
                    "DELETE FROM runs WHERE run_id = ?",
                    (run_id,),
                )
                connection.commit()
            finally:
                connection.close()
        except Exception:
            pass


__all__ = ["NativeSqliteImportSink", "NativeSqliteImportSinkFactory"]
