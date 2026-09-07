"""SQLite adapters for the storage-independent Telemetry ports."""

from .csv_import import (
    CSVImportError,
    CSVImportReport,
    ChannelImportResult,
    import_csv_to_sqlite,
    infer_run_identity,
)
from .connection import SQLiteConnectionPolicy, connect_database
from .migration_audit import (
    ChannelInventory,
    MigrationAuditError,
    RunInventory,
    discover_csv_runs,
    run_stage2m,
)
from .schema_catalog import TELEMETRY_SCHEMA_CONTRACT
from .schema_inspector import inspect_schema
from .schema_manager import (
    TelemetrySchemaMigrationError,
    initialize_database,
)
from .storage_parity import (
    ChannelParity,
    FieldMismatch,
    StorageParityError,
    StorageParityReport,
    validate_storage_parity,
)
from .sqlite_repository import SQLiteTelemetryRepository
from .sqlite_run_lifecycle import SQLiteRunLifecycleRepository
from .sqlite_writer import SQLiteWriter, SQLiteWriterConfig, SQLiteWriterError

__all__ = [
    "CSVImportError",
    "CSVImportReport",
    "ChannelImportResult",
    "ChannelParity",
    "ChannelInventory",
    "FieldMismatch",
    "MigrationAuditError",
    "SQLiteTelemetryRepository",
    "SQLiteRunLifecycleRepository",
    "SQLiteWriter",
    "SQLiteWriterConfig",
    "SQLiteWriterError",
    "RunInventory",
    "StorageParityError",
    "StorageParityReport",
    "SQLiteConnectionPolicy",
    "TELEMETRY_SCHEMA_CONTRACT",
    "TelemetrySchemaMigrationError",
    "connect_database",
    "discover_csv_runs",
    "import_csv_to_sqlite",
    "infer_run_identity",
    "initialize_database",
    "inspect_schema",
    "run_stage2m",
    "validate_storage_parity",
]
