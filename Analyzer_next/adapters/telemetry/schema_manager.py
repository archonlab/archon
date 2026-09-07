"""Write-side migration execution for the canonical Telemetry database."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from typing import Callable

from Analyzer_next.core.telemetry.schema_contracts import (
    MigrationDescriptor,
    TelemetrySchemaSnapshot,
)
from Analyzer_next.core.telemetry.schema_validation import (
    require_compatible_schema,
    validate_contract,
)

from .connection import (
    DEFAULT_CONNECTION_POLICY,
    SQLiteConnectionPolicy,
    connect_database,
)
from .migration_sql import MIGRATION_SQL
from .schema_catalog import TELEMETRY_SCHEMA_CONTRACT
from .schema_inspector import inspect_schema


class TelemetrySchemaMigrationError(RuntimeError):
    """Raised when schema initialization cannot complete atomically."""


Clock = Callable[[], str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_database(
    database: str | Path | sqlite3.Connection,
    *,
    policy: SQLiteConnectionPolicy = DEFAULT_CONNECTION_POLICY,
    clock: Clock = utc_now,
) -> TelemetrySchemaSnapshot:
    """Apply the declared migration suffix to the one Telemetry database."""
    contract = TELEMETRY_SCHEMA_CONTRACT
    validate_contract(contract)
    _validate_executable_catalog()
    owns_connection = not isinstance(database, sqlite3.Connection)
    connection = (
        connect_database(database, policy=policy)
        if owns_connection
        else database
    )

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at_utc TEXT NOT NULL,
                checksum TEXT NOT NULL
            )
            """
        )
        applied = _load_applied_history(connection)

        for descriptor in contract.migrations:
            if descriptor.version in applied:
                continue
            _apply_migration(connection, descriptor, clock=clock)
            applied.add(descriptor.version)

        snapshot = inspect_schema(connection, contract)
        require_compatible_schema(contract, snapshot)
        return snapshot
    except Exception as exc:
        if isinstance(exc, TelemetrySchemaMigrationError):
            raise
        raise TelemetrySchemaMigrationError(
            f"Could not initialize telemetry database: {exc}"
        ) from exc
    finally:
        if owns_connection:
            connection.close()


def _validate_executable_catalog() -> None:
    descriptors = TELEMETRY_SCHEMA_CONTRACT.migrations
    if set(MIGRATION_SQL) != {item.version for item in descriptors}:
        raise TelemetrySchemaMigrationError(
            "Executable migration catalog does not match schema contract"
        )
    for descriptor in descriptors:
        checksum = hashlib.sha256(
            MIGRATION_SQL[descriptor.version].encode("utf-8")
        ).hexdigest()
        if checksum != descriptor.checksum:
            raise TelemetrySchemaMigrationError(
                f"Migration {descriptor.version} SQL checksum does not match contract"
            )


def _load_applied_history(connection: sqlite3.Connection) -> set[int]:
    """Validate the recorded prefix before any pending migration is applied."""
    descriptors = {
        item.version: item
        for item in TELEMETRY_SCHEMA_CONTRACT.migrations
    }
    rows = list(connection.execute(
        """
        SELECT version, name, checksum
        FROM schema_migrations
        ORDER BY version
        """
    ))
    versions = tuple(int(row["version"]) for row in rows)
    expected_prefix = tuple(range(1, len(versions) + 1))
    if versions != expected_prefix:
        raise TelemetrySchemaMigrationError(
            "Applied migration history must be a contiguous prefix: "
            f"expected {expected_prefix}, got {versions}"
        )
    for row in rows:
        version = int(row["version"])
        descriptor = descriptors.get(version)
        if descriptor is None:
            raise TelemetrySchemaMigrationError(
                f"Unknown applied migration version {version}"
            )
        if str(row["name"]) != descriptor.name:
            raise TelemetrySchemaMigrationError(
                f"Migration {version} name does not match contract"
            )
        if str(row["checksum"]) not in descriptor.accepted_checksums:
            raise TelemetrySchemaMigrationError(
                f"Migration {version} checksum does not match contract"
            )
    return set(versions)


def _apply_migration(
    connection: sqlite3.Connection,
    descriptor: MigrationDescriptor,
    *,
    clock: Clock,
) -> None:
    sql = MIGRATION_SQL[descriptor.version]
    if descriptor.execution_mode == "programmatic":
        if descriptor.version != 4:
            raise TelemetrySchemaMigrationError(
                f"No programmatic executor for migration {descriptor.version}"
            )
        _apply_migration_004(connection, descriptor, clock=clock)
        return

    try:
        connection.execute("BEGIN IMMEDIATE")
        if descriptor.version == 2:
            _ensure_observer_state_sample_columns(connection)
        connection.executescript(sql)
        _record_migration(connection, descriptor, clock=clock)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _record_migration(
    connection: sqlite3.Connection,
    descriptor: MigrationDescriptor,
    *,
    clock: Clock,
) -> None:
    connection.execute(
        """
        INSERT INTO schema_migrations (
            version,
            name,
            applied_at_utc,
            checksum
        ) VALUES (?, ?, ?, ?)
        """,
        (
            descriptor.version,
            descriptor.name,
            clock(),
            descriptor.checksum,
        ),
    )


_OBSERVER_STATE_SAMPLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("life_state", "TEXT"),
    ("life_score", "REAL"),
    ("life_confidence", "REAL"),
    ("structural_state", "TEXT"),
)


def _ensure_observer_state_sample_columns(
    connection: sqlite3.Connection,
) -> None:
    existing = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(samples)")
    }
    for column_name, column_type in _OBSERVER_STATE_SAMPLE_COLUMNS:
        if column_name in existing:
            continue
        connection.execute(
            f'ALTER TABLE samples ADD COLUMN "{column_name}" {column_type}'
        )
        existing.add(column_name)


def _apply_migration_004(
    connection: sqlite3.Connection,
    descriptor: MigrationDescriptor,
    *,
    clock: Clock,
) -> None:
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("PRAGMA legacy_alter_table = ON")

    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP VIEW IF EXISTS experiment_run_overview")
        connection.execute(
            """
            ALTER TABLE experimental_conditions
            RENAME TO experimental_conditions_v3
            """
        )
        connection.executescript(
            """
            CREATE TABLE experimental_conditions (
                condition_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                field_width INTEGER NOT NULL,
                field_height INTEGER NOT NULL,
                topology TEXT NOT NULL,
                boundary_mode TEXT NOT NULL,
                initial_state_mode TEXT NOT NULL,
                condition_hash TEXT NOT NULL UNIQUE,
                parameters_json TEXT NOT NULL DEFAULT '{}',
                schema_version INTEGER NOT NULL DEFAULT 1,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                CHECK (length(trim(condition_id)) > 0),
                CHECK (length(trim(name)) > 0),
                CHECK (field_width > 0),
                CHECK (field_height > 0),
                CHECK (topology IN ('torus', 'bounded')),
                CHECK (
                    boundary_mode IN (
                        'wrap',
                        'fixed_dead',
                        'fixed_alive',
                        'reflective'
                    )
                ),
                CHECK (
                    initial_state_mode IN (
                        'canonical_seed',
                        'random_seed',
                        'saved_state',
                        'deterministic_regenerated'
                    )
                ),
                CHECK (schema_version >= 1),
                CHECK (json_valid(parameters_json))
            );

            INSERT INTO experimental_conditions (
                condition_id,
                name,
                field_width,
                field_height,
                topology,
                boundary_mode,
                initial_state_mode,
                condition_hash,
                parameters_json,
                schema_version,
                created_at_utc,
                updated_at_utc
            )
            SELECT
                condition_id,
                name,
                field_width,
                field_height,
                topology,
                boundary_mode,
                initial_state_mode,
                condition_hash,
                parameters_json,
                schema_version,
                created_at_utc,
                updated_at_utc
            FROM experimental_conditions_v3;

            DROP TABLE experimental_conditions_v3;

            CREATE INDEX idx_conditions_geometry
                ON experimental_conditions(
                    field_width,
                    field_height,
                    topology,
                    boundary_mode
                );

            CREATE INDEX idx_conditions_name
                ON experimental_conditions(name);

            CREATE VIEW experiment_run_overview AS
            SELECT
                er.experiment_run_id,
                er.experiment_id,
                e.title AS experiment_title,
                e.status AS experiment_status,
                er.run_id,
                er.rule_id,
                er.role,
                er.replicate_index,
                er.parent_run_id,
                er.condition_id,
                c.name AS condition_name,
                c.field_width,
                c.field_height,
                c.topology,
                c.boundary_mode,
                c.initial_state_mode,
                r.status AS run_status,
                r.final_tick,
                r.started_at_utc,
                r.finished_at_utc
            FROM experiment_runs er
            JOIN experiments e
                ON e.experiment_id = er.experiment_id
            JOIN experimental_conditions c
                ON c.condition_id = er.condition_id
            JOIN runs r
                ON r.run_id = er.run_id;
            """
        )
        _record_migration(connection, descriptor, clock=clock)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA legacy_alter_table = OFF")
        connection.execute("PRAGMA foreign_keys = ON")

    violations = list(connection.execute("PRAGMA foreign_key_check"))
    if violations:
        raise TelemetrySchemaMigrationError(
            "Migration 4 produced foreign-key violations: "
            f"{violations[:5]}"
        )


__all__ = [
    "TelemetrySchemaMigrationError",
    "initialize_database",
    "utc_now",
]
