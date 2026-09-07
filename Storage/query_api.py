#!/usr/bin/env python3
"""Stable read API for ARCHON Telemetry SQLite storage.

Analyzer modules should use this interface instead of embedding raw SQL.

Supported operations:
- list and inspect runs;
- read samples, events, chronicle, and pressure;
- query tick ranges and limits;
- retrieve original payload_json dictionaries;
- get channel counts and tick bounds;
- stream large result sets without loading everything into memory.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterator, Mapping, Sequence

# Support direct execution from the canonical project-root Storage package.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from Storage.sqlite_schema import connect_database, validate_schema


class TelemetryQueryError(RuntimeError):
    """Raised when a Telemetry query cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: str
    rule_id: int | None
    world_id: str | None
    observer_version: str | None
    status: str
    started_at_utc: str | None
    finished_at_utc: str | None
    final_tick: int | None
    samples_count: int
    events_count: int
    chronicle_count: int
    pressure_count: int
    source_path: str | None
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ChannelSummary:
    run_id: str
    channel: str
    row_count: int
    first_tick: int | None
    last_tick: int | None


@dataclass(frozen=True, slots=True)
class ScientificRunContext:
    """Scientific provenance used to route one run into an evidence channel."""

    run_id: str
    status: str
    experiment_id: str | None
    condition_id: str | None
    role: str | None
    is_experimental: bool
    is_mutation: bool
    observational_eligible: bool
    exclusion_reason: str | None


CHANNEL_TABLES = {
    "sample": ("samples", "sample_id"),
    "samples": ("samples", "sample_id"),
    "event": ("events", "event_id"),
    "events": ("events", "event_id"),
    "chronicle": ("chronicle", "chronicle_id"),
    "pressure": ("pressure", "pressure_id"),
}


class TelemetryQueryAPI:
    """Read-only query facade over one ARCHON Telemetry database."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        validate: bool = True,
    ) -> None:
        self.database_path = Path(
            database_path
        ).expanduser().resolve()

        if not self.database_path.exists():
            raise TelemetryQueryError(
                f"Telemetry database does not exist: {self.database_path}"
            )

        uri = f"file:{self.database_path}?mode=ro"
        try:
            self._connection = sqlite3.connect(
                uri,
                uri=True,
                timeout=30.0,
            )
        except sqlite3.Error as exc:
            raise TelemetryQueryError(
                f"Could not open Telemetry database: {exc}"
            ) from exc

        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        self._closed = False

        if validate:
            try:
                validate_schema(self._connection)
            except Exception as exc:
                self._connection.close()
                self._closed = True
                raise TelemetryQueryError(
                    f"Invalid Telemetry schema: {exc}"
                ) from exc

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def __enter__(self) -> "TelemetryQueryAPI":
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
        return [self._run_from_row(row) for row in rows]

    def get_run(self, run_id: str) -> RunSummary:
        self._ensure_open()
        row = self._connection.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()
        if row is None:
            raise TelemetryQueryError(
                f"run_id not found: {run_id!r}"
            )
        return self._run_from_row(row)

    def get_scientific_run_context(
        self,
        run_id: str,
    ) -> ScientificRunContext:
        """Classify a run without treating experiments as observations.

        A canonical observational run must have a terminal successful status
        (``completed`` or the historical-migration status ``imported``), must
        not be linked to ``experiment_runs``, and must not carry experimental
        or mutation provenance in the run metadata.
        """
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
            raise TelemetryQueryError(
                f"run_id not found: {run_id!r}"
            )

        metadata = self._decode_payload(
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
            metadata.get("run_kind")
            or metadata.get("role")
            or ""
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
        table, _ = self._resolve_channel(channel)
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
            channel=self._canonical_channel(channel),
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
            for channel in (
                "sample",
                "event",
                "chronicle",
                "pressure",
            )
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
        table, id_column = self._resolve_channel(channel)

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
            raise TelemetryQueryError(
                "tick_from must be <= tick_to"
            )

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
                payload = self._decode_payload(
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
            SELECT *,
                   ABS(tick - ?) AS tick_distance
            FROM samples
            WHERE run_id = ?
            ORDER BY tick_distance ASC, tick ASC
            LIMIT 1
            """,
            (int(tick), str(run_id)),
        ).fetchone()
        if row is None:
            return None
        return self._decode_payload(
            row["payload_json"],
            table="samples",
            row_id=row["sample_id"],
        )

    def ticks(
        self,
        run_id: str,
        channel: str = "sample",
    ) -> list[int]:
        table, id_column = self._resolve_channel(channel)
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
        table, _ = self._resolve_channel(channel)
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

    def _run_from_row(self, row: sqlite3.Row) -> RunSummary:
        metadata = self._decode_payload(
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

    @staticmethod
    def _decode_payload(
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

    @staticmethod
    def _canonical_channel(channel: str) -> str:
        normalized = str(channel).strip().lower()
        aliases = {
            "samples": "sample",
            "events": "event",
        }
        return aliases.get(normalized, normalized)

    def _resolve_channel(
        self,
        channel: str,
    ) -> tuple[str, str]:
        normalized = str(channel).strip().lower()
        if normalized not in CHANNEL_TABLES:
            raise TelemetryQueryError(
                f"Unknown channel: {channel!r}"
            )
        return CHANNEL_TABLES[normalized]

    def _ensure_open(self) -> None:
        if self._closed:
            raise TelemetryQueryError(
                "TelemetryQueryAPI is already closed"
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect ARCHON Telemetry SQLite storage."
    )
    parser.add_argument("database")
    sub = parser.add_subparsers(dest="command", required=True)

    runs = sub.add_parser("runs")
    runs.add_argument("--rule-id", type=int)
    runs.add_argument("--status")
    runs.add_argument("--limit", type=int)

    show = sub.add_parser("show-run")
    show.add_argument("run_id")

    channel = sub.add_parser("channel")
    channel.add_argument("run_id")
    channel.add_argument(
        "channel",
        choices=("sample", "event", "chronicle", "pressure"),
    )
    channel.add_argument("--tick-from", type=int)
    channel.add_argument("--tick-to", type=int)
    channel.add_argument("--limit", type=int)
    channel.add_argument("--newest-first", action="store_true")
    channel.add_argument("--with-columns", action="store_true")

    summary = sub.add_parser("summary")
    summary.add_argument("run_id")

    nearest = sub.add_parser("nearest-sample")
    nearest.add_argument("run_id")
    nearest.add_argument("tick", type=int)

    parser.add_argument("--json-output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    with TelemetryQueryAPI(args.database) as api:
        if args.command == "runs":
            result = [
                asdict(item)
                for item in api.list_runs(
                    rule_id=args.rule_id,
                    status=args.status,
                    limit=args.limit,
                )
            ]
        elif args.command == "show-run":
            result = asdict(api.get_run(args.run_id))
        elif args.command == "channel":
            result = api.read_channel(
                args.run_id,
                args.channel,
                tick_from=args.tick_from,
                tick_to=args.tick_to,
                limit=args.limit,
                newest_first=args.newest_first,
                payload_only=not args.with_columns,
            )
        elif args.command == "summary":
            result = {
                key: asdict(value)
                for key, value in api.all_channel_summaries(
                    args.run_id
                ).items()
            }
        elif args.command == "nearest-sample":
            result = api.nearest_sample(
                args.run_id,
                args.tick,
            )
        else:
            raise TelemetryQueryError(
                f"Unsupported command: {args.command}"
            )

    output = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    print(output)

    if args.json_output:
        path = Path(args.json_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "TelemetryQueryError",
    "RunSummary",
    "ChannelSummary",
    "ScientificRunContext",
    "TelemetryQueryAPI",
    "main",
]
