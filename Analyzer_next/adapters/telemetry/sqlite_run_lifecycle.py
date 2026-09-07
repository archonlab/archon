"""SQLite implementation of the storage-independent run lifecycle port."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Callable

from Analyzer_next.core.telemetry.run_lifecycle import (
    RunFinalization,
    RunRegistration,
    TelemetryRunLifecycleError,
)


Clock = Callable[[], str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteRunLifecycleRepository:
    """Persist lifecycle changes without owning commit or rollback."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._connection = connection
        self._clock = clock

    def register_run(self, registration: RunRegistration) -> None:
        run_id = str(registration.run_id).strip()
        if not run_id:
            raise TelemetryRunLifecycleError("run_id must not be empty")

        now = self._clock()
        metadata_json = json.dumps(
            dict(registration.metadata or {}),
            ensure_ascii=False,
            sort_keys=True,
        )

        try:
            self._connection.execute(
                """
                INSERT INTO runs (
                    run_id,
                    rule_id,
                    world_id,
                    observer_version,
                    started_at_utc,
                    status,
                    source_path,
                    metadata_json,
                    created_at_utc,
                    updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    registration.rule_id,
                    registration.world_id,
                    registration.observer_version,
                    registration.started_at_utc or now,
                    registration.status,
                    registration.source_path,
                    metadata_json,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise TelemetryRunLifecycleError(
                f"Could not register run {run_id!r}: {exc}"
            ) from exc

    def finalize_run(self, finalization: RunFinalization) -> None:
        self._connection.row_factory = sqlite3.Row
        row = self._connection.execute(
            "SELECT metadata_json FROM runs WHERE run_id = ?",
            (finalization.run_id,),
        ).fetchone()
        if row is None:
            raise TelemetryRunLifecycleError(
                f"Unknown run_id: {finalization.run_id!r}"
            )

        metadata = json.loads(row["metadata_json"])
        metadata.update(dict(finalization.metadata_update or {}))

        counts = {
            "samples": self._count("samples", finalization.run_id),
            "events": self._count("events", finalization.run_id),
            "chronicle": self._count("chronicle", finalization.run_id),
            "pressure": self._count("pressure", finalization.run_id),
        }

        cursor = self._connection.execute(
            """
            UPDATE runs
            SET
                finished_at_utc = ?,
                status = ?,
                final_tick = ?,
                samples_count = ?,
                events_count = ?,
                chronicle_count = ?,
                pressure_count = ?,
                metadata_json = ?,
                updated_at_utc = ?
            WHERE run_id = ?
            """,
            (
                finalization.finished_at_utc or self._clock(),
                finalization.status,
                finalization.final_tick,
                counts["samples"],
                counts["events"],
                counts["chronicle"],
                counts["pressure"],
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                self._clock(),
                finalization.run_id,
            ),
        )

        if cursor.rowcount != 1:
            raise TelemetryRunLifecycleError(
                f"Could not finalize run {finalization.run_id!r}"
            )

    def _count(self, table: str, run_id: str) -> int:
        return int(self._connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0])


__all__ = ["SQLiteRunLifecycleRepository", "utc_now"]
