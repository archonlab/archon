"""Canonical read-side identity of the ARCHON Telemetry SQLite schema.

The SQL executors remain in :mod:`Storage.sqlite_schema` during DL3.  This
module contains only immutable names, versions and checksums so Analyzer_next
can validate databases without importing the legacy writer implementation.
"""
from __future__ import annotations

from Analyzer_next.core.telemetry.schema_contracts import (
    MigrationDescriptor,
    TelemetrySchemaContract,
)


TELEMETRY_SCHEMA_CONTRACT = TelemetrySchemaContract(
    schema_name="archon.telemetry.sqlite",
    expected_version=4,
    required_tables=frozenset({
        "schema_migrations",
        "runs",
        "samples",
        "events",
        "chronicle",
        "pressure",
        "experimental_conditions",
        "experiments",
        "experiment_runs",
    }),
    migrations=(
        MigrationDescriptor(
            1,
            "initial_telemetry_schema",
            "c71e473d72f61f03d65a30626a0f346a25c73d223b74f5123aadc8a7455d7f1d",
        ),
        MigrationDescriptor(
            2,
            "observer_state_telemetry_contract",
            "8de1dee1464eeb37984f114d1d6b94aca44b81488c263912a845cdb02044768d",
        ),
        MigrationDescriptor(
            3,
            "experimental_conditions_storage_v1",
            "01a7632a383be6f86094d426d6e2df2907448e4ddf5727099e026544c72d22b0",
            compatible_checksums=(
                "a15ef44740067feecf3f885ce3ca1b0816a97c02813a4e98d674d3878c8cd273",
            ),
        ),
        MigrationDescriptor(
            4,
            "initial_state_random_seed_v1",
            "bf7952315055df9f5947feb61dc7a8b9509a67fc0852eec9a07f1e09bb45d19f",
            execution_mode="programmatic",
        ),
    ),
)
