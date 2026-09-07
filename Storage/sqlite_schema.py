#!/usr/bin/env python3
"""SQLite schema management for Project ARCHON Telemetry.

The schema stores multiple Observer runs in one database while preserving every
telemetry payload exactly as JSON.

Tables
------
schema_migrations
    Applied schema versions.

runs
    One row per Observer run.

samples
events
chronicle
pressure
    Channel records keyed by run_id and tick. Frequently queried fields are
    promoted to columns; the full original payload remains in payload_json.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


SQLITE_SCHEMA_VERSION = 4
SQLITE_SCHEMA_NAME = "archon.telemetry.sqlite"


class SQLiteSchemaError(RuntimeError):
    """Raised when the telemetry database schema is invalid."""


@dataclass(frozen=True, slots=True)
class SchemaInfo:
    schema_name: str
    expected_version: int
    applied_version: int
    database_path: str | None
    journal_mode: str
    foreign_keys: bool
    tables: tuple[str, ...]


MIGRATION_001 = r"""
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL,
    checksum TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    rule_id INTEGER,
    world_id TEXT,
    observer_version TEXT,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    final_tick INTEGER,
    samples_count INTEGER NOT NULL DEFAULT 0,
    events_count INTEGER NOT NULL DEFAULT 0,
    chronicle_count INTEGER NOT NULL DEFAULT 0,
    pressure_count INTEGER NOT NULL DEFAULT 0,
    source_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    CHECK (status IN ('running', 'completed', 'stopped', 'failed', 'imported')),
    CHECK (final_tick IS NULL OR final_tick >= 0),
    CHECK (samples_count >= 0),
    CHECK (events_count >= 0),
    CHECK (chronicle_count >= 0),
    CHECK (pressure_count >= 0),
    CHECK (json_valid(metadata_json))
);

CREATE INDEX IF NOT EXISTS idx_runs_rule_id
    ON runs(rule_id);

CREATE INDEX IF NOT EXISTS idx_runs_status
    ON runs(status);

CREATE INDEX IF NOT EXISTS idx_runs_started_at
    ON runs(started_at_utc);

CREATE TABLE IF NOT EXISTS samples (
    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    alive INTEGER,
    objects INTEGER,
    largest INTEGER,
    total_living_mass INTEGER,
    ecosystem_health REAL,
    stability_index REAL,
    ecosystem_phase TEXT,
    morphology_class TEXT,
    emergence_score REAL,
    validation_quality REAL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    CHECK (tick >= 0),
    CHECK (alive IS NULL OR alive IN (0, 1)),
    CHECK (json_valid(payload_json)),
    UNIQUE (run_id, tick)
);

CREATE INDEX IF NOT EXISTS idx_samples_run_tick
    ON samples(run_id, tick);

CREATE INDEX IF NOT EXISTS idx_samples_phase
    ON samples(run_id, ecosystem_phase, tick);

CREATE INDEX IF NOT EXISTS idx_samples_morphology
    ON samples(run_id, morphology_class, tick);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    CHECK (tick >= 0),
    CHECK (json_valid(payload_json))
);

CREATE INDEX IF NOT EXISTS idx_events_run_tick
    ON events(run_id, tick);

CREATE INDEX IF NOT EXISTS idx_events_type
    ON events(run_id, event_type, tick);

CREATE TABLE IF NOT EXISTS chronicle (
    chronicle_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    severity TEXT,
    event TEXT,
    family TEXT,
    colony TEXT,
    phase TEXT,
    pressure REAL,
    risk REAL,
    cause TEXT,
    details TEXT,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    CHECK (tick >= 0),
    CHECK (json_valid(payload_json))
);

CREATE INDEX IF NOT EXISTS idx_chronicle_run_tick
    ON chronicle(run_id, tick);

CREATE INDEX IF NOT EXISTS idx_chronicle_severity
    ON chronicle(run_id, severity, tick);

CREATE INDEX IF NOT EXISTS idx_chronicle_event
    ON chronicle(run_id, event, tick);

CREATE TABLE IF NOT EXISTS pressure (
    pressure_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    phase TEXT,
    stress REAL,
    adapt REAL,
    pressure REAL,
    recovery REAL,
    risk REAL,
    cause TEXT,
    ecosystem_phase TEXT,
    objects INTEGER,
    mass INTEGER,
    largest INTEGER,
    families INTEGER,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    CHECK (tick >= 0),
    CHECK (json_valid(payload_json)),
    UNIQUE (run_id, tick)
);

CREATE INDEX IF NOT EXISTS idx_pressure_run_tick
    ON pressure(run_id, tick);

CREATE INDEX IF NOT EXISTS idx_pressure_phase
    ON pressure(run_id, phase, tick);

CREATE INDEX IF NOT EXISTS idx_pressure_cause
    ON pressure(run_id, cause, tick);

CREATE VIEW IF NOT EXISTS run_channel_counts AS
SELECT
    r.run_id,
    r.rule_id,
    r.status,
    r.final_tick,
    (SELECT COUNT(*) FROM samples s WHERE s.run_id = r.run_id) AS samples_actual,
    (SELECT COUNT(*) FROM events e WHERE e.run_id = r.run_id) AS events_actual,
    (SELECT COUNT(*) FROM chronicle c WHERE c.run_id = r.run_id) AS chronicle_actual,
    (SELECT COUNT(*) FROM pressure p WHERE p.run_id = r.run_id) AS pressure_actual,
    r.samples_count,
    r.events_count,
    r.chronicle_count,
    r.pressure_count
FROM runs r;
"""


MIGRATION_002 = r"""
CREATE INDEX IF NOT EXISTS idx_samples_life_state
    ON samples(run_id, life_state, tick);

CREATE INDEX IF NOT EXISTS idx_samples_structural_state
    ON samples(run_id, structural_state, tick);
"""


MIGRATION_003 = r"""
CREATE TABLE IF NOT EXISTS experimental_conditions (
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
            'saved_state',
            'deterministic_regenerated'
        )
    ),
    CHECK (schema_version >= 1),
    CHECK (json_valid(parameters_json))
);

CREATE INDEX IF NOT EXISTS idx_conditions_geometry
    ON experimental_conditions(
        field_width,
        field_height,
        topology,
        boundary_mode
    );

CREATE INDEX IF NOT EXISTS idx_conditions_name
    ON experimental_conditions(name);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    research_question TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    CHECK (length(trim(experiment_id)) > 0),
    CHECK (length(trim(title)) > 0),
    CHECK (
        status IN (
            'planned',
            'running',
            'completed',
            'stopped',
            'failed',
            'archived'
        )
    ),
    CHECK (json_valid(metadata_json))
);

CREATE INDEX IF NOT EXISTS idx_experiments_status
    ON experiments(status);

CREATE INDEX IF NOT EXISTS idx_experiments_created_at
    ON experiments(created_at_utc);

CREATE TABLE IF NOT EXISTS experiment_runs (
    experiment_run_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE,
    condition_id TEXT NOT NULL,
    rule_id INTEGER,
    role TEXT NOT NULL,
    replicate_index INTEGER NOT NULL DEFAULT 0,
    treatment_arm TEXT NOT NULL DEFAULT '',
    parent_run_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (experiment_id)
        REFERENCES experiments(experiment_id)
        ON DELETE CASCADE,
    FOREIGN KEY (run_id)
        REFERENCES runs(run_id)
        ON DELETE CASCADE,
    FOREIGN KEY (condition_id)
        REFERENCES experimental_conditions(condition_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (parent_run_id)
        REFERENCES runs(run_id)
        ON DELETE SET NULL,
    CHECK (length(trim(experiment_run_id)) > 0),
    CHECK (
        role IN (
            'baseline',
            'treatment',
            'control',
            'calibration'
        )
    ),
    CHECK (replicate_index >= 0),
    CHECK (json_valid(metadata_json)),
    UNIQUE (
        experiment_id,
        condition_id,
        rule_id,
        role,
        replicate_index,
        treatment_arm
    )
);

CREATE INDEX IF NOT EXISTS idx_experiment_runs_experiment
    ON experiment_runs(experiment_id, role, replicate_index);

CREATE INDEX IF NOT EXISTS idx_experiment_runs_condition
    ON experiment_runs(condition_id);

CREATE INDEX IF NOT EXISTS idx_experiment_runs_rule
    ON experiment_runs(rule_id);

CREATE VIEW IF NOT EXISTS experiment_run_overview AS
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


# Migration 4 rebuilds only the tiny experimental_conditions table.
# It is applied by _apply_migration_004() because SQLite cannot alter an
# existing CHECK constraint in place.
MIGRATION_004 = r"""
-- Applied programmatically by _apply_migration_004().
"""


_OBSERVER_STATE_SAMPLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("life_state", "TEXT"),
    ("life_score", "REAL"),
    ("life_confidence", "REAL"),
    ("structural_state", "TEXT"),
)


def _ensure_observer_state_sample_columns(
    connection: sqlite3.Connection,
) -> None:
    """Add Stage 1C sample columns only when they are actually absent.

    Some ARCHON databases already contain these columns while their
    ``schema_migrations`` table still reports version 1, for example after a
    partially applied migration or an older development build. SQLite's plain
    ``ALTER TABLE ... ADD COLUMN`` is not idempotent, so replaying migration 2
    would otherwise fail with ``duplicate column name``.
    """
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


MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (1, "initial_telemetry_schema", MIGRATION_001),
    (2, "observer_state_telemetry_contract", MIGRATION_002),
    (3, "experimental_conditions_storage_v1", MIGRATION_003),
    (4, "initial_state_random_seed_v1", MIGRATION_004),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_database(
    database: str | Path,
    *,
    timeout: float = 30.0,
    read_only: bool = False,
) -> sqlite3.Connection:
    path = Path(database).expanduser().resolve()
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)

    if read_only:
        connection = sqlite3.connect(
            f"file:{path}?mode=ro",
            uri=True,
            timeout=timeout,
        )
    else:
        connection = sqlite3.connect(path, timeout=timeout)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    if not read_only:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA busy_timeout = 30000")

    return connection



def _apply_migration_004(
    connection: sqlite3.Connection,
    *,
    name: str,
    sql: str,
) -> None:
    """Expand initial_state_mode CHECK without touching telemetry channels.

    SQLite cannot alter a CHECK constraint in place, so only the small
    experimental_conditions table is rebuilt. Large samples/events/chronicle/
    pressure tables are never copied.
    """
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("PRAGMA legacy_alter_table = ON")

    try:
        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            "DROP VIEW IF EXISTS experiment_run_overview"
        )
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
                4,
                name,
                utc_now(),
                _migration_checksum(sql),
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA legacy_alter_table = OFF")
        connection.execute("PRAGMA foreign_keys = ON")

    violations = list(connection.execute("PRAGMA foreign_key_check"))
    if violations:
        raise SQLiteSchemaError(
            "Migration 4 produced foreign-key violations: "
            f"{violations[:5]}"
        )

def initialize_database(
    database: str | Path | sqlite3.Connection,
) -> SchemaInfo:
    owns_connection = not isinstance(database, sqlite3.Connection)
    connection = connect_database(database) if owns_connection else database

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

        applied = {
            int(row["version"])
            for row in connection.execute(
                "SELECT version FROM schema_migrations"
            )
        }

        for version, name, sql in MIGRATIONS:
            if version in applied:
                continue

            if version == 4:
                _apply_migration_004(
                    connection,
                    name=name,
                    sql=sql,
                )
                applied.add(version)
                continue

            try:
                connection.execute("BEGIN IMMEDIATE")
                if version == 2:
                    _ensure_observer_state_sample_columns(connection)
                connection.executescript(sql)
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
                        version,
                        name,
                        utc_now(),
                        _migration_checksum(sql),
                    ),
                )
                connection.commit()
                applied.add(version)
            except Exception:
                connection.rollback()
                raise

        validate_schema(connection)
        return inspect_schema(connection)
    except Exception as exc:
        if isinstance(exc, SQLiteSchemaError):
            raise
        raise SQLiteSchemaError(
            f"Could not initialize telemetry database: {exc}"
        ) from exc
    finally:
        if owns_connection:
            connection.close()


def validate_schema(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row

    required_tables = {
        "schema_migrations",
        "runs",
        "samples",
        "events",
        "chronicle",
        "pressure",
        "experimental_conditions",
        "experiments",
        "experiment_runs",
    }
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    missing = required_tables - tables
    if missing:
        raise SQLiteSchemaError(
            f"Missing required tables: {sorted(missing)}"
        )

    version = current_schema_version(connection)
    if version != SQLITE_SCHEMA_VERSION:
        raise SQLiteSchemaError(
            f"Schema version {version} does not match expected "
            f"{SQLITE_SCHEMA_VERSION}"
        )

    try:
        valid = connection.execute(
            "SELECT json_valid(?) AS valid",
            ('{"ok": true}',),
        ).fetchone()["valid"]
    except sqlite3.DatabaseError as exc:
        raise SQLiteSchemaError(
            "SQLite JSON functions are unavailable"
        ) from exc

    if valid != 1:
        raise SQLiteSchemaError(
            "SQLite JSON validation is not working"
        )

    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise SQLiteSchemaError(
            "SQLite foreign_keys must be enabled"
        )


def inspect_schema(connection: sqlite3.Connection) -> SchemaInfo:
    connection.row_factory = sqlite3.Row
    tables = tuple(
        sorted(
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            )
        )
    )

    database_path = None
    for row in connection.execute("PRAGMA database_list"):
        if row["name"] == "main":
            database_path = row["file"] or None
            break

    return SchemaInfo(
        schema_name=SQLITE_SCHEMA_NAME,
        expected_version=SQLITE_SCHEMA_VERSION,
        applied_version=current_schema_version(connection),
        database_path=database_path,
        journal_mode=str(
            connection.execute("PRAGMA journal_mode").fetchone()[0]
        ),
        foreign_keys=bool(
            connection.execute("PRAGMA foreign_keys").fetchone()[0]
        ),
        tables=tables,
    )


def current_schema_version(
    connection: sqlite3.Connection,
) -> int:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) AS version "
        "FROM schema_migrations"
    ).fetchone()
    return int(row["version"])


def register_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    rule_id: int | None = None,
    world_id: str | None = None,
    observer_version: str | None = None,
    started_at_utc: str | None = None,
    status: str = "running",
    source_path: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    run_id = str(run_id).strip()
    if not run_id:
        raise SQLiteSchemaError("run_id must not be empty")

    now = utc_now()
    metadata_json = json.dumps(
        dict(metadata or {}),
        ensure_ascii=False,
        sort_keys=True,
    )

    try:
        connection.execute(
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
                rule_id,
                world_id,
                observer_version,
                started_at_utc or now,
                status,
                source_path,
                metadata_json,
                now,
                now,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise SQLiteSchemaError(
            f"Could not register run {run_id!r}: {exc}"
        ) from exc


def finalize_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    status: str,
    final_tick: int | None,
    finished_at_utc: str | None = None,
    metadata_update: Mapping[str, Any] | None = None,
) -> None:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT metadata_json FROM runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise SQLiteSchemaError(
            f"Unknown run_id: {run_id!r}"
        )

    metadata = json.loads(row["metadata_json"])
    metadata.update(dict(metadata_update or {}))

    counts = {
        "samples": connection.execute(
            "SELECT COUNT(*) FROM samples WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0],
        "events": connection.execute(
            "SELECT COUNT(*) FROM events WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0],
        "chronicle": connection.execute(
            "SELECT COUNT(*) FROM chronicle WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0],
        "pressure": connection.execute(
            "SELECT COUNT(*) FROM pressure WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0],
    }

    cursor = connection.execute(
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
            finished_at_utc or utc_now(),
            status,
            final_tick,
            counts["samples"],
            counts["events"],
            counts["chronicle"],
            counts["pressure"],
            json.dumps(
                metadata,
                ensure_ascii=False,
                sort_keys=True,
            ),
            utc_now(),
            run_id,
        ),
    )

    if cursor.rowcount != 1:
        raise SQLiteSchemaError(
            f"Could not finalize run {run_id!r}"
        )


def _migration_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


__all__ = [
    "SQLITE_SCHEMA_VERSION",
    "SQLITE_SCHEMA_NAME",
    "SQLiteSchemaError",
    "SchemaInfo",
    "MIGRATIONS",
    "connect_database",
    "initialize_database",
    "validate_schema",
    "inspect_schema",
    "current_schema_version",
    "register_run",
    "finalize_run",
    "utc_now",
]
