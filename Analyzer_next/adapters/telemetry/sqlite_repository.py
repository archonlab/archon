"""Read-only SQLite implementation of the Telemetry repository port."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Iterator

from Analyzer_next.core.telemetry.contracts import (
    ChannelSummary,
    RunSummary,
    ScientificRunContext,
    TelemetryQueryError,
)

from .codec import decode_payload, run_from_row
from .connection import connect_database
from .schema import canonical_channel, resolve_channel, validate_read_schema


class SQLiteTelemetryRepository:
    """Read-only query facade over one ARCHON Telemetry database."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        validate: bool = True,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        if not self.database_path.exists():
            raise TelemetryQueryError(
                f"Telemetry database does not exist: {self.database_path}"
            )

        try:
            self._connection = connect_database(
                self.database_path,
                read_only=True,
            )
        except sqlite3.Error as exc:
            raise TelemetryQueryError(
                f"Could not open Telemetry database: {exc}"
            ) from exc
        self._closed = False

        if validate:
            try:
                validate_read_schema(self._connection)
            except Exception as exc:
                self._connection.close()
                self._closed = True
                if isinstance(exc, TelemetryQueryError):
                    detail = str(exc)
                else:
                    detail = str(exc)
                raise TelemetryQueryError(
                    f"Invalid Telemetry schema: {detail}"
                ) from exc

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def __enter__(self) -> "SQLiteTelemetryRepository":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def list_runs(
        self,
        *,
        rule_id: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> list[RunSummary]:
        self._ensure_open()
        where = []
        values: list[Any] = []
        if rule_id is not None:
            where.append("rule_id = ?")
            values.append(int(rule_id))
        if status is not None:
            where.append("status = ?")
            values.append(str(status))

        sql = "SELECT * FROM runs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += (
            " ORDER BY started_at_utc DESC, run_id DESC"
            if newest_first
            else " ORDER BY started_at_utc ASC, run_id ASC"
        )
        if limit is not None:
            if int(limit) < 1:
                raise TelemetryQueryError("limit must be >= 1")
            sql += " LIMIT ?"
            values.append(int(limit))
        rows = self._connection.execute(sql, values).fetchall()
        return [run_from_row(row) for row in rows]

    def get_run(self, run_id: str) -> RunSummary:
        self._ensure_open()
        row = self._connection.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()
        if row is None:
            raise TelemetryQueryError(f"run_id not found: {run_id!r}")
        return run_from_row(row)

    def get_scientific_run_context(
        self,
        run_id: str,
    ) -> ScientificRunContext:
        self._ensure_open()
        row = self._connection.execute(
            """
            SELECT
                r.run_id,
                r.status,
                r.source_path,
                r.metadata_json,
                er.experiment_id,
                er.condition_id,
                er.role
            FROM runs r
            LEFT JOIN experiment_runs er
                ON er.run_id = r.run_id
            WHERE r.run_id = ?
            """,
            (str(run_id),),
        ).fetchone()
        if row is None:
            raise TelemetryQueryError(f"run_id not found: {run_id!r}")

        metadata = decode_payload(
            row["metadata_json"],
            table="runs",
            row_id=row["run_id"],
        )
        experimental_context = metadata.get("experimental_context")
        is_experimental = (
            row["experiment_id"] is not None
            or isinstance(experimental_context, dict)
        )
        source_path = str(row["source_path"] or "").replace("\\", "/")
        mutation_markers = (
            metadata.get("mutation_id"),
            metadata.get("mutation_manifest"),
            metadata.get("parent_mutation_id"),
        )
        run_kind = str(
            metadata.get("run_kind") or metadata.get("role") or ""
        ).strip().lower()
        is_mutation = (
            "/mutation_runs/" in source_path
            or any(value not in (None, "") for value in mutation_markers)
            or run_kind in {"mutation", "mutated", "perturbation"}
        )

        exclusion_reason = None
        if str(row["status"]) not in {"completed", "imported"}:
            exclusion_reason = "RUN_NOT_COMPLETED"
        elif is_mutation:
            exclusion_reason = "MUTATION_RUN"
        elif is_experimental:
            exclusion_reason = "EXPERIMENTAL_RUN"

        return ScientificRunContext(
            run_id=str(row["run_id"]),
            status=str(row["status"]),
            experiment_id=(
                str(row["experiment_id"])
                if row["experiment_id"] is not None
                else None
            ),
            condition_id=(
                str(row["condition_id"])
                if row["condition_id"] is not None
                else None
            ),
            role=(
                str(row["role"])
                if row["role"] is not None
                else None
            ),
            is_experimental=is_experimental,
            is_mutation=is_mutation,
            observational_eligible=exclusion_reason is None,
            exclusion_reason=exclusion_reason,
        )

    def latest_run(
        self,
        *,
        rule_id: int | None = None,
        status: str | None = None,
    ) -> RunSummary | None:
        runs = self.list_runs(
            rule_id=rule_id,
            status=status,
            limit=1,
            newest_first=True,
        )
        return runs[0] if runs else None

    def channel_summary(
        self,
        run_id: str,
        channel: str,
    ) -> ChannelSummary:
        table, _ = resolve_channel(channel)
        row = self._connection.execute(
            f"""
            SELECT
                COUNT(*) AS row_count,
                MIN(tick) AS first_tick,
                MAX(tick) AS last_tick
            FROM {table}
            WHERE run_id = ?
            """,
            (str(run_id),),
        ).fetchone()
        return ChannelSummary(
            run_id=str(run_id),
            channel=canonical_channel(channel),
            row_count=int(row["row_count"]),
            first_tick=row["first_tick"],
            last_tick=row["last_tick"],
        )

    def all_channel_summaries(
        self,
        run_id: str,
    ) -> dict[str, ChannelSummary]:
        self.get_run(run_id)
        return {
            channel: self.channel_summary(run_id, channel)
            for channel in ("sample", "event", "chronicle", "pressure")
        }

    def read_channel(
        self,
        run_id: str,
        channel: str,
        *,
        tick_from: int | None = None,
        tick_to: int | None = None,
        limit: int | None = None,
        newest_first: bool = False,
        payload_only: bool = True,
    ) -> list[dict[str, Any]]:
        return list(
            self.iter_channel(
                run_id,
                channel,
                tick_from=tick_from,
                tick_to=tick_to,
                limit=limit,
                newest_first=newest_first,
                payload_only=payload_only,
            )
        )

    def iter_channel(
        self,
        run_id: str,
        channel: str,
        *,
        tick_from: int | None = None,
        tick_to: int | None = None,
        limit: int | None = None,
        newest_first: bool = False,
        payload_only: bool = True,
        fetch_size: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        self._ensure_open()
        table, id_column = resolve_channel(channel)
        if fetch_size < 1:
            raise TelemetryQueryError("fetch_size must be >= 1")

        where = ["run_id = ?"]
        values: list[Any] = [str(run_id)]
        if tick_from is not None:
            where.append("tick >= ?")
            values.append(int(tick_from))
        if tick_to is not None:
            where.append("tick <= ?")
            values.append(int(tick_to))
        if (
            tick_from is not None
            and tick_to is not None
            and int(tick_from) > int(tick_to)
        ):
            raise TelemetryQueryError("tick_from must be <= tick_to")

        direction = "DESC" if newest_first else "ASC"
        sql = (
            f"SELECT * FROM {table} "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY tick {direction}, {id_column} {direction}"
        )
        if limit is not None:
            if int(limit) < 1:
                raise TelemetryQueryError("limit must be >= 1")
            sql += " LIMIT ?"
            values.append(int(limit))

        cursor = self._connection.execute(sql, values)
        while True:
            rows = cursor.fetchmany(fetch_size)
            if not rows:
                break
            for row in rows:
                payload = decode_payload(
                    row["payload_json"],
                    table=table,
                    row_id=row[id_column],
                )
                if payload_only:
                    yield payload
                else:
                    result = dict(row)
                    result["payload"] = payload
                    result.pop("payload_json", None)
                    yield result

    def samples(self, run_id: str, **kwargs) -> list[dict[str, Any]]:
        return self.read_channel(run_id, "sample", **kwargs)

    def events(self, run_id: str, **kwargs) -> list[dict[str, Any]]:
        return self.read_channel(run_id, "event", **kwargs)

    def chronicle(self, run_id: str, **kwargs) -> list[dict[str, Any]]:
        return self.read_channel(run_id, "chronicle", **kwargs)

    def pressure(self, run_id: str, **kwargs) -> list[dict[str, Any]]:
        return self.read_channel(run_id, "pressure", **kwargs)

    def nearest_sample(
        self,
        run_id: str,
        tick: int,
    ) -> dict[str, Any] | None:
        self._ensure_open()
        row = self._connection.execute(
            """
            SELECT *, ABS(tick - ?) AS tick_distance
            FROM samples
            WHERE run_id = ?
            ORDER BY tick_distance ASC, tick ASC
            LIMIT 1
            """,
            (int(tick), str(run_id)),
        ).fetchone()
        if row is None:
            return None
        return decode_payload(
            row["payload_json"],
            table="samples",
            row_id=row["sample_id"],
        )

    def ticks(
        self,
        run_id: str,
        channel: str = "sample",
    ) -> list[int]:
        table, id_column = resolve_channel(channel)
        rows = self._connection.execute(
            f"""
            SELECT tick
            FROM {table}
            WHERE run_id = ?
            ORDER BY tick ASC, {id_column} ASC
            """,
            (str(run_id),),
        ).fetchall()
        return [int(row["tick"]) for row in rows]

    def count(
        self,
        run_id: str,
        channel: str,
        *,
        tick_from: int | None = None,
        tick_to: int | None = None,
    ) -> int:
        table, _ = resolve_channel(channel)
        where = ["run_id = ?"]
        values: list[Any] = [str(run_id)]
        if tick_from is not None:
            where.append("tick >= ?")
            values.append(int(tick_from))
        if tick_to is not None:
            where.append("tick <= ?")
            values.append(int(tick_to))
        row = self._connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE {' AND '.join(where)}
            """,
            values,
        ).fetchone()
        return int(row["count"])

    def _ensure_open(self) -> None:
        if self._closed:
            raise TelemetryQueryError(
                "TelemetryQueryAPI is already closed"
            )
