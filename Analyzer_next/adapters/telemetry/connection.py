"""SQLite connection policy for ARCHON Telemetry storage.

This adapter owns connection creation and PRAGMA configuration only.  Schema
planning remains in :mod:`Analyzer_next.core.telemetry`; migration execution is
assembled by the outer schema manager.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3


@dataclass(frozen=True, slots=True)
class SQLiteConnectionPolicy:
    """Write-side settings preserved from the canonical Storage layer."""

    timeout_seconds: float = 30.0
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    temp_store: str = "MEMORY"
    busy_timeout_ms: int = 30_000

    def __post_init__(self) -> None:
        if self.timeout_seconds < 0:
            raise ValueError("timeout_seconds must be >= 0")
        if self.busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be >= 0")


DEFAULT_CONNECTION_POLICY = SQLiteConnectionPolicy()


def connect_database(
    database: str | Path,
    *,
    timeout: float | None = None,
    read_only: bool = False,
    policy: SQLiteConnectionPolicy = DEFAULT_CONNECTION_POLICY,
) -> sqlite3.Connection:
    """Open one canonical SQLite database with legacy-compatible settings."""
    path = Path(database).expanduser().resolve()
    effective_timeout = (
        policy.timeout_seconds if timeout is None else float(timeout)
    )
    if effective_timeout < 0:
        raise ValueError("timeout must be >= 0")
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)

    if read_only:
        connection = sqlite3.connect(
            f"file:{path}?mode=ro",
            uri=True,
            timeout=effective_timeout,
        )
    else:
        connection = sqlite3.connect(path, timeout=effective_timeout)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        f"PRAGMA busy_timeout = {int(policy.busy_timeout_ms)}"
    )

    if not read_only:
        connection.execute(f"PRAGMA journal_mode = {policy.journal_mode}")
        connection.execute(f"PRAGMA synchronous = {policy.synchronous}")
        connection.execute(f"PRAGMA temp_store = {policy.temp_store}")

    return connection


__all__ = [
    "DEFAULT_CONNECTION_POLICY",
    "SQLiteConnectionPolicy",
    "connect_database",
]
