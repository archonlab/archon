"""PERF1 asynchronous live Telemetry controller.

All SQLite reads live on one worker thread.  Tk only submits the desired run id
and consumes the latest immutable poll snapshot, so SQLite busy periods cannot
stall rendering or input handling.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import queue
import sqlite3
import threading
import time
from typing import Any, Callable

from Analyzer_next.adapters.telemetry.codec import decode_payload
from Analyzer_next.adapters.telemetry.connection import SQLiteConnectionPolicy, connect_database
from Analyzer_next.adapters.telemetry.routed_live import RoutedLiveTelemetryAdapter
from Analyzer_next.core.telemetry.contracts import TelemetryQueryError
from Analyzer_next.core.telemetry.live import LiveTelemetryFrame, LiveTelemetryPort, LiveTelemetrySample
from Analyzer_next.execution.observer.shell2.telem1.controller import LiveTelemetryController, LiveTelemetryPoll
from Analyzer_next.execution.observer.state import TelemetryState


_READ_POLICY = SQLiteConnectionPolicy(
    timeout_seconds=0.20,
    busy_timeout_ms=200,
)


class ResponsiveSQLiteLiveTelemetryAdapter:
    """Bounded read-only live adapter with a short busy timeout.

    It is intentionally local to PERF1.  Canonical Storage connection policy and
    write-side semantics are untouched.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        if not self.database_path.exists():
            raise TelemetryQueryError(f"Telemetry database does not exist: {self.database_path}")
        try:
            self._connection = connect_database(
                self.database_path,
                read_only=True,
                policy=_READ_POLICY,
            )
        except sqlite3.Error as exc:
            raise TelemetryQueryError(f"Could not open Telemetry database: {exc}") from exc
        self._closed = False

    def read_frame(self, run_id: str, *, history_limit: int = 8) -> LiveTelemetryFrame | None:
        if int(history_limit) < 2:
            raise TelemetryQueryError("history_limit must be >= 2")
        expected = str(run_id).strip()
        if not expected:
            raise TelemetryQueryError("run_id is required")
        try:
            run = self._connection.execute(
                "SELECT run_id, status, final_tick FROM runs WHERE run_id = ?",
                (expected,),
            ).fetchone()
            if run is None:
                raise TelemetryQueryError(f"run_id not found: {expected!r}")
            rows = self._connection.execute(
                "SELECT * FROM samples WHERE run_id = ? ORDER BY tick DESC, sample_id DESC LIMIT ?",
                (expected, int(history_limit)),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            detail = str(exc)
            if "no such table" in detail.lower():
                raise TelemetryQueryError(f"Invalid Telemetry schema: {detail}") from exc
            raise TelemetryQueryError(f"Telemetry read busy: {detail}") from exc
        except sqlite3.Error as exc:
            raise TelemetryQueryError(f"Telemetry read failed: {exc}") from exc
        if not rows:
            return None
        samples: list[LiveTelemetrySample] = []
        for row in reversed(rows):
            row_id = str(row["run_id"] or "")
            if row_id != expected:
                raise TelemetryQueryError("Telemetry row identity mismatch")
            payload = decode_payload(row["payload_json"], table="samples", row_id=row["sample_id"])
            fields = dict(row)
            fields.pop("payload_json", None)
            samples.append(
                LiveTelemetrySample(
                    run_id=row_id,
                    tick=int(row["tick"]),
                    fields=fields,
                    payload=payload,
                    created_at_utc=(str(row["created_at_utc"]) if row["created_at_utc"] is not None else None),
                )
            )
        return LiveTelemetryFrame(
            run_id=expected,
            run_status=str(run["status"]),
            final_tick=(int(run["final_tick"]) if run["final_tick"] is not None else None),
            samples=tuple(samples),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._connection.close()


class _UnavailableTelemetryPort:
    def __init__(self, error: str) -> None:
        self.error = str(error)
    def read_frame(self, run_id: str, *, history_limit: int = 8) -> LiveTelemetryFrame | None:
        raise TelemetryQueryError(self.error)
    def close(self) -> None:
        return None


PortFactory = Callable[[Path], LiveTelemetryPort]


class RecoveringTelemetryPort:
    """Worker-owned lazy reader; never creates a DB or changes writer state.

    Initialization waits are bounded per identity. Errors remain retryable but
    visible after the grace period. All reads and closes stay on the worker.
    """

    def __init__(self, path, factory, *, clock=time.monotonic, grace_seconds=30.0):
        self.database_path = Path(path)
        self.factory = factory
        self.clock = clock
        self.grace_seconds = grace_seconds
        self.reader = None
        self.reader_file_identity = None
        self.identity = None
        self.started = 0.0
        self.next_attempt = 0.0
        self.error = None
        self.pending = False
        self.closed = False

    def read_frame(self, run_id, *, history_limit=8):
        if self.closed:
            raise TelemetryQueryError("live telemetry reader is closed")
        now = self.clock()
        if self.identity != run_id:
            self.identity, self.started = run_id, now
            self.next_attempt = 0.0
        current_file_identity = self._file_identity()
        if self.reader is not None and current_file_identity != self.reader_file_identity:
            self._close_reader()
        if now >= self.next_attempt:
            try:
                if self.reader is None:
                    if not self.database_path.exists():
                        raise TelemetryQueryError("Telemetry database does not exist: " + str(self.database_path))
                    self.reader = self.factory(self.database_path)
                    self.reader_file_identity = self._file_identity()
                frame = self.reader.read_frame(run_id, history_limit=history_limit)
                self.error = None
                self.pending = False
                return frame
            except TelemetryQueryError as exc:
                self.error = exc
                detail = str(exc)
                self.pending = (
                    not self.database_path.exists()
                    or detail == f"run_id not found: {run_id!r}"
                    or (isinstance(exc.__cause__, sqlite3.OperationalError)
                        and str(exc.__cause__) in {"no such table: runs", "no such table: samples"})
                )
                self.next_attempt = now + 0.5
        if self.error is not None:
            if self.pending and now - self.started < self.grace_seconds:
                return None
            if self.pending:
                raise TelemetryQueryError("Telemetry initialization timed out: waiting for database, schema or run registration") from self.error
            raise self.error
        return None

    def _file_identity(self):
        try:
            stat = self.database_path.stat()
        except OSError:
            return None
        return (int(stat.st_dev), int(stat.st_ino))

    def _close_reader(self):
        if self.reader is not None:
            try:
                self.reader.close()
            finally:
                self.reader = None
                self.reader_file_identity = None

    def close(self):
        self.closed = True
        self._close_reader()


class AsyncLiveTelemetryController:
    """Non-blocking facade with the TELEM1 controller + mutation-router APIs."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        stale_after_seconds: float = 3.0,
        poll_interval_seconds: float = 0.35,
        port_factory: PortFactory | None = None,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.stale_after_seconds = float(stale_after_seconds)
        self.poll_interval_seconds = max(0.05, float(poll_interval_seconds))
        self._port_factory = port_factory or (lambda path: ResponsiveSQLiteLiveTelemetryAdapter(path))
        self._lock = threading.RLock()
        self._commands: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._requested_run_id = ""
        self._latest: LiveTelemetryPoll | None = None
        self._armed_database: Path | None = None
        self._thread = threading.Thread(target=self._worker, name="ol2-perf1-telemetry", daemon=True)
        self._thread.start()

    @property
    def port(self) -> "AsyncLiveTelemetryController":
        # SETTINGS only needs database_path from telemetry_controller.port.
        return self

    @property
    def armed_database(self) -> Path | None:
        with self._lock:
            return self._armed_database

    def poll(self, run_id: str) -> LiveTelemetryPoll:
        normalized = str(run_id).strip()
        if not normalized:
            return LiveTelemetryPoll("", TelemetryState.ERROR, None, None, "run_id is required")
        with self._lock:
            changed = normalized != self._requested_run_id
            self._requested_run_id = normalized
            latest = self._latest
        if changed:
            self._wake.set()
        if latest is not None and latest.run_id == normalized:
            return latest
        self._wake.set()
        return LiveTelemetryPoll(normalized, TelemetryState.CONNECTING, None, None)

    def arm_database(self, database_path: str | Path) -> None:
        path = Path(database_path).expanduser().resolve()
        with self._lock:
            self._armed_database = path
            self._latest = None
        self._commands.put(("arm", path))
        self._wake.set()

    def clear_armed_database(self) -> None:
        with self._lock:
            self._armed_database = None
        self._commands.put(("clear", None))
        self._wake.set()

    def finalize_armed_database(self, run_id: str | None, *, history_limit: int = 8) -> None:
        self._commands.put(("finalize", (str(run_id or ""), int(history_limit))))
        self._wake.set()
        return None

    def _worker(self) -> None:
        try:
            factory = lambda path: RecoveringTelemetryPort(path, self._port_factory)
            default = factory(self.database_path)
            router = RoutedLiveTelemetryAdapter(default, port_factory=factory)
            controller = LiveTelemetryController(
                router,
                stale_after_seconds=self.stale_after_seconds,
            )
            while not self._stop.is_set():
                self._drain_commands(router)
                with self._lock:
                    run_id = self._requested_run_id
                if run_id:
                    poll = controller.poll(run_id)
                    with self._lock:
                        self._latest = poll
                        if poll.frame is not None and self._armed_database is not None:
                            # The router bound the armed DB to this identity.
                            self._armed_database = None
                self._wake.wait(self.poll_interval_seconds)
                self._wake.clear()
        finally:
            try:
                controller.close()  # type: ignore[possibly-undefined]
            except Exception:
                pass

    def _drain_commands(self, router: RoutedLiveTelemetryAdapter) -> None:
        while True:
            try:
                command, payload = self._commands.get_nowait()
            except queue.Empty:
                return
            if command == "arm":
                router.arm_database(payload)
            elif command == "clear":
                router.clear_armed_database()
            elif command == "finalize":
                run_id, history_limit = payload
                try:
                    router.finalize_armed_database(run_id, history_limit=history_limit)
                except TelemetryQueryError:
                    pass
                with self._lock:
                    self._armed_database = None

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=1.0)


__all__ = [
    "AsyncLiveTelemetryController",
    "ResponsiveSQLiteLiveTelemetryAdapter",
]
