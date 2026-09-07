"""Native SQLite writer for Project ARCHON Telemetry.

The public contract mirrors the canonical legacy writer while composing the
DL4 connection/schema adapters and the DL5 run-lifecycle adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from threading import RLock
from typing import Any, Mapping

from Analyzer_next.core.telemetry.run_lifecycle import (
    RunFinalization,
    RunRegistration,
)

from .connection import connect_database
from .schema_manager import initialize_database
from .sqlite_run_lifecycle import SQLiteRunLifecycleRepository


class SQLiteWriterError(RuntimeError):
    """Raised when telemetry cannot be written safely."""


@dataclass(frozen=True, slots=True)
class SQLiteWriterConfig:
    batch_size: int = 250
    duplicate_sample_policy: str = "replace"
    duplicate_pressure_policy: str = "replace"
    auto_register_run: bool = True
    finalize_on_close: bool = True
    close_status: str = "completed"
    busy_retries: int = 12
    busy_retry_seconds: float = 0.025

    def __post_init__(self) -> None:
        if int(self.batch_size) < 1:
            raise SQLiteWriterError("batch_size must be >= 1")
        if int(self.busy_retries) < 0:
            raise SQLiteWriterError("busy_retries must be >= 0")
        if float(self.busy_retry_seconds) < 0:
            raise SQLiteWriterError("busy_retry_seconds must be >= 0")
        valid = {"replace", "ignore", "error"}
        if self.duplicate_sample_policy not in valid:
            raise SQLiteWriterError(
                "duplicate_sample_policy must be replace, ignore, or error"
            )
        if self.duplicate_pressure_policy not in valid:
            raise SQLiteWriterError(
                "duplicate_pressure_policy must be replace, ignore, or error"
            )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteWriter:
    """Persist one Observer run into an ARCHON Telemetry SQLite database."""

    def __init__(
        self,
        *,
        database_path: str | Path,
        run_id: str,
        rule_id: int | None = None,
        world_id: str | None = None,
        observer_version: str | None = None,
        started_at_utc: str | None = None,
        source_path: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        config: SQLiteWriterConfig | None = None,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.run_id = str(run_id).strip()
        if not self.run_id:
            raise SQLiteWriterError("run_id must not be empty")

        self.rule_id = rule_id
        self.world_id = world_id
        self.observer_version = observer_version
        self.started_at_utc = started_at_utc
        self.source_path = source_path
        self.metadata = dict(metadata or {})
        self.config = config or SQLiteWriterConfig()

        self._lock = RLock()
        self._closed = False
        self._pending = 0
        self._buffer: list[
            tuple[str, str, tuple[Any, ...], str | None]
        ] = []
        self._max_tick: int | None = None
        self._writes = {
            "sample": 0,
            "event": 0,
            "chronicle": 0,
            "pressure": 0,
        }
        self._ignored = {"sample": 0, "pressure": 0}
        self._flushes = 0
        self._commits = 0
        self._rollbacks = 0
        self._errors = 0

        self._connection = connect_database(self.database_path)
        initialize_database(self._connection, clock=utc_now)
        self._lifecycle = SQLiteRunLifecycleRepository(
            self._connection,
            clock=utc_now,
        )

        if self.config.auto_register_run:
            self._ensure_run_registered()

    @property
    def closed(self) -> bool:
        return self._closed

    def write_sample(self, **row: Any) -> bool:
        tick = self._require_tick(row)
        columns = (
            "run_id", "tick", "alive", "life_state", "life_score",
            "life_confidence", "structural_state", "objects", "largest",
            "total_living_mass", "ecosystem_health", "stability_index",
            "ecosystem_phase", "morphology_class", "emergence_score",
            "validation_quality", "payload_json", "created_at_utc",
        )
        sql = self._upsert_sql(
            table="samples",
            unique_columns=("run_id", "tick"),
            policy=self.config.duplicate_sample_policy,
            columns=columns,
        )
        values = (
            self.run_id,
            tick,
            _bool_int(row.get("alive")),
            _text_or_none(row.get("life_state")),
            _float_or_none(row.get("life_score")),
            _float_or_none(row.get("life_confidence")),
            _text_or_none(row.get("structural_state")),
            _int_or_none(row.get("objects")),
            _int_or_none(row.get("largest")),
            _int_or_none(row.get("total_living_mass")),
            _float_or_none(row.get("ecosystem_health")),
            _float_or_none(row.get("stability_index")),
            _text_or_none(row.get("ecosystem_phase")),
            _text_or_none(row.get("morphology_class")),
            _float_or_none(row.get("emergence_score")),
            _float_or_none(row.get("validation_quality")),
            _payload_json(row),
            utc_now(),
        )
        return self._execute_channel(
            "sample",
            sql,
            values,
            duplicate_policy=self.config.duplicate_sample_policy,
        )

    def write_event(self, **row: Any) -> bool:
        tick = self._require_tick(row)
        event_type = row.get("type", row.get("event_type"))
        if event_type is None or not str(event_type).strip():
            raise SQLiteWriterError(
                "event row requires non-empty 'type' or 'event_type'"
            )
        sql = """
        INSERT INTO events (
            run_id, tick, event_type, detail, payload_json, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?)
        """
        return self._execute_channel(
            "event",
            sql,
            (
                self.run_id,
                tick,
                str(event_type),
                _text_or_none(row.get("detail")),
                _payload_json(row),
                utc_now(),
            ),
        )

    def write_chronicle(self, **row: Any) -> bool:
        tick = self._require_tick(row)
        sql = """
        INSERT INTO chronicle (
            run_id, tick, severity, event, family, colony, phase,
            pressure, risk, cause, details, payload_json, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return self._execute_channel(
            "chronicle",
            sql,
            (
                self.run_id,
                tick,
                _text_or_none(row.get("severity")),
                _text_or_none(row.get("event")),
                _text_or_none(row.get("family")),
                _text_or_none(row.get("colony")),
                _text_or_none(row.get("phase")),
                _float_or_none(row.get("pressure")),
                _float_or_none(row.get("risk")),
                _text_or_none(row.get("cause")),
                _text_or_none(row.get("details")),
                _payload_json(row),
                utc_now(),
            ),
        )

    def write_pressure(self, **row: Any) -> bool:
        tick = self._require_tick(row)
        columns = (
            "run_id", "tick", "phase", "stress", "adapt", "pressure",
            "recovery", "risk", "cause", "ecosystem_phase", "objects",
            "mass", "largest", "families", "payload_json", "created_at_utc",
        )
        sql = self._upsert_sql(
            table="pressure",
            unique_columns=("run_id", "tick"),
            policy=self.config.duplicate_pressure_policy,
            columns=columns,
        )
        values = (
            self.run_id,
            tick,
            _text_or_none(row.get("phase")),
            _float_or_none(row.get("stress")),
            _float_or_none(row.get("adapt")),
            _float_or_none(row.get("pressure")),
            _float_or_none(row.get("recovery")),
            _float_or_none(row.get("risk")),
            _text_or_none(row.get("cause")),
            _text_or_none(row.get("ecosystem_phase")),
            _int_or_none(row.get("objects")),
            _int_or_none(row.get("mass")),
            _int_or_none(row.get("largest")),
            _int_or_none(row.get("families")),
            _payload_json(row),
            utc_now(),
        )
        return self._execute_channel(
            "pressure",
            sql,
            values,
            duplicate_policy=self.config.duplicate_pressure_policy,
        )

    def flush(self) -> None:
        """Persist the current FIFO buffer in one short transaction."""
        with self._lock:
            self._ensure_open()
            if not self._buffer:
                return

            batch = list(self._buffer)
            last_error: Exception | None = None

            for attempt in range(self.config.busy_retries + 1):
                try:
                    self._connection.execute("BEGIN IMMEDIATE")
                    ignored_by_channel = {"sample": 0, "pressure": 0}

                    for channel, sql, values, duplicate_policy in batch:
                        before = self._connection.total_changes
                        self._connection.execute(sql, values)
                        changed = self._connection.total_changes > before
                        if (
                            not changed
                            and duplicate_policy == "ignore"
                            and channel in ignored_by_channel
                        ):
                            ignored_by_channel[channel] += 1

                    self._connection.commit()
                    for channel, count in ignored_by_channel.items():
                        self._ignored[channel] += count

                    del self._buffer[:len(batch)]
                    self._pending = len(self._buffer)
                    self._flushes += 1
                    self._commits += 1
                    return

                except sqlite3.OperationalError as exc:
                    try:
                        self._connection.rollback()
                    except Exception:
                        pass
                    last_error = exc
                    locked = (
                        "locked" in str(exc).lower()
                        or "busy" in str(exc).lower()
                    )
                    if not locked or attempt >= self.config.busy_retries:
                        break
                    delay = self.config.busy_retry_seconds * (attempt + 1)
                    if delay > 0:
                        time.sleep(delay)

                except Exception as exc:
                    try:
                        self._connection.rollback()
                    except Exception:
                        pass
                    last_error = exc
                    break

            self._errors += 1
            self._rollbacks += 1
            raise SQLiteWriterError(
                f"SQLite flush failed after "
                f"{self.config.busy_retries + 1} attempt(s): {last_error}"
            ) from last_error

    def finalize(
        self,
        *,
        status: str = "completed",
        final_tick: int | None = None,
        metadata_update: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._ensure_open()
            self.flush()
            try:
                self._lifecycle.finalize_run(RunFinalization(
                    run_id=self.run_id,
                    status=status,
                    final_tick=(
                        self._max_tick if final_tick is None else int(final_tick)
                    ),
                    metadata_update=dict(metadata_update or {}),
                ))
                self._connection.commit()
                self._commits += 1
            except Exception as exc:
                self._errors += 1
                self._rollbacks += 1
                self._connection.rollback()
                raise SQLiteWriterError(
                    f"Could not finalize run {self.run_id!r}: {exc}"
                ) from exc

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return

            failure: Exception | None = None
            try:
                self.flush()
                if self.config.finalize_on_close:
                    self._lifecycle.finalize_run(RunFinalization(
                        run_id=self.run_id,
                        status=self.config.close_status,
                        final_tick=self._max_tick,
                    ))
                    self._connection.commit()
                    self._commits += 1
            except Exception as exc:
                failure = exc
                self._errors += 1
                self._rollbacks += 1
                try:
                    self._connection.rollback()
                except Exception:
                    pass
            finally:
                self._connection.close()
                self._closed = True

            if failure is not None:
                raise SQLiteWriterError(
                    f"SQLite close failed: {failure}"
                ) from failure

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "database_path": str(self.database_path),
                "run_id": self.run_id,
                "closed": self._closed,
                "pending_rows": self._pending,
                "max_tick": self._max_tick,
                "writes": dict(self._writes),
                "ignored_duplicates": dict(self._ignored),
                "flushes": self._flushes,
                "commits": self._commits,
                "rollbacks": self._rollbacks,
                "errors": self._errors,
                "batch_size": self.config.batch_size,
                "buffered_rows": len(self._buffer),
                "busy_retries": self.config.busy_retries,
                "busy_retry_seconds": self.config.busy_retry_seconds,
            }

    def __enter__(self) -> "SQLiteWriter":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is not None:
            try:
                self._connection.rollback()
                self._rollbacks += 1
            finally:
                self._connection.close()
                self._closed = True
            return
        self.close()

    def _ensure_run_registered(self) -> None:
        row = self._connection.execute(
            "SELECT run_id FROM runs WHERE run_id = ?",
            (self.run_id,),
        ).fetchone()
        if row is not None:
            return

        try:
            self._lifecycle.register_run(RunRegistration(
                run_id=self.run_id,
                rule_id=self.rule_id,
                world_id=self.world_id,
                observer_version=self.observer_version,
                started_at_utc=self.started_at_utc,
                source_path=self.source_path,
                metadata=self.metadata,
            ))
            self._connection.commit()
            self._commits += 1
        except Exception as exc:
            self._connection.rollback()
            self._rollbacks += 1
            raise SQLiteWriterError(
                f"Could not register run {self.run_id!r}: {exc}"
            ) from exc

    def _execute_channel(
        self,
        channel: str,
        sql: str,
        values: tuple[Any, ...],
        *,
        duplicate_policy: str | None = None,
    ) -> bool:
        """Queue one row without opening a SQLite write transaction."""
        with self._lock:
            self._ensure_open()
            tick = int(values[1])
            self._max_tick = tick if self._max_tick is None else max(
                self._max_tick, tick
            )
            self._writes[channel] += 1
            self._buffer.append((channel, sql, values, duplicate_policy))
            self._pending = len(self._buffer)
            if self._pending >= self.config.batch_size:
                self.flush()
            return True

    @staticmethod
    def _upsert_sql(
        *,
        table: str,
        unique_columns: tuple[str, ...],
        policy: str,
        columns: tuple[str, ...],
    ) -> str:
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(columns)
        if policy == "error":
            return f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})"
        if policy == "ignore":
            return (
                f"INSERT OR IGNORE INTO {table} ({column_sql}) "
                f"VALUES ({placeholders})"
            )

        update_columns = [
            column for column in columns
            if column not in unique_columns and column != "created_at_utc"
        ]
        update_sql = ", ".join(
            f"{column}=excluded.{column}" for column in update_columns
        )
        conflict_sql = ", ".join(unique_columns)
        return (
            f"INSERT INTO {table} ({column_sql}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}"
        )

    @staticmethod
    def _require_tick(row: Mapping[str, Any]) -> int:
        if "tick" not in row:
            raise SQLiteWriterError("telemetry row requires 'tick'")
        try:
            tick = int(row["tick"])
        except (TypeError, ValueError) as exc:
            raise SQLiteWriterError(
                f"tick must be an integer, got {row['tick']!r}"
            ) from exc
        if tick < 0:
            raise SQLiteWriterError("tick must be >= 0")
        return tick

    def _ensure_open(self) -> None:
        if self._closed:
            raise SQLiteWriterError("SQLiteWriter is already closed")


def _payload_json(row: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            dict(row),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
    except Exception as exc:
        raise SQLiteWriterError(
            f"Telemetry payload is not JSON serializable: {exc}"
        ) from exc


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item") and callable(value.item):
        return value.item()
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return str(value)


def _bool_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return 1
        if normalized in {"false", "no", "0"}:
            return 0
    return 1 if bool(value) else 0


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


__all__ = ["SQLiteWriterError", "SQLiteWriterConfig", "SQLiteWriter"]
