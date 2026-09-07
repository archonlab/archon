"""Storage-independent contracts for the ARCHON Telemetry SQLite schema."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


class TelemetrySchemaContractError(RuntimeError):
    """Raised when schema metadata violates the declared contract."""


MigrationExecutionMode = Literal["sql", "programmatic"]


@dataclass(frozen=True, slots=True)
class MigrationDescriptor:
    """Immutable identity of one ordered schema migration."""

    version: int
    name: str
    checksum: str
    execution_mode: MigrationExecutionMode = "sql"
    compatible_checksums: tuple[str, ...] = ()

    @property
    def accepted_checksums(self) -> frozenset[str]:
        return frozenset((self.checksum, *self.compatible_checksums))


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """One migration record observed in ``schema_migrations``."""

    version: int
    name: str
    applied_at_utc: str
    checksum: str


@dataclass(frozen=True, slots=True)
class TelemetrySchemaContract:
    """Expected identity and structural requirements of one schema line."""

    schema_name: str
    expected_version: int
    required_tables: frozenset[str]
    migrations: tuple[MigrationDescriptor, ...]


@dataclass(frozen=True, slots=True)
class TelemetrySchemaSnapshot:
    """Read-only observation of one SQLite database connection."""

    schema_name: str
    applied_version: int
    database_path: str | None
    journal_mode: str
    foreign_keys: bool
    json_functions: bool
    tables: tuple[str, ...]
    applied_migrations: tuple[AppliedMigration, ...]


@dataclass(frozen=True, slots=True)
class SchemaViolation:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SchemaValidationReport:
    schema_name: str
    expected_version: int
    applied_version: int
    valid: bool
    pending_versions: tuple[int, ...]
    violations: tuple[SchemaViolation, ...]
