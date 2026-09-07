"""SQL payloads for the versioned ARCHON Telemetry schema.

The migration identities live in ``schema_catalog``.  Keeping executable SQL
in the SQLite adapter prevents the storage-independent core from depending on
SQLite while preserving the canonical schema byte-for-byte at the DDL level.
"""
from __future__ import annotations


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


MIGRATION_004 = r"""
-- Applied programmatically by _apply_migration_004().
"""


MIGRATION_SQL = {
    1: MIGRATION_001,
    2: MIGRATION_002,
    3: MIGRATION_003,
    4: MIGRATION_004,
}


__all__ = ["MIGRATION_001", "MIGRATION_002", "MIGRATION_003", "MIGRATION_004", "MIGRATION_SQL"]
