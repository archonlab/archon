"""Pure validation and planning for Telemetry schema contracts."""
from __future__ import annotations

import re

from .schema_contracts import (
    MigrationDescriptor,
    SchemaValidationReport,
    SchemaViolation,
    TelemetrySchemaContract,
    TelemetrySchemaContractError,
    TelemetrySchemaSnapshot,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_contract(contract: TelemetrySchemaContract) -> None:
    """Reject malformed migration catalogs before any database is inspected."""
    if not contract.schema_name.strip():
        raise TelemetrySchemaContractError("schema_name must not be empty")
    if contract.expected_version < 1:
        raise TelemetrySchemaContractError("expected_version must be >= 1")
    if not contract.required_tables:
        raise TelemetrySchemaContractError("required_tables must not be empty")

    versions = tuple(item.version for item in contract.migrations)
    expected_versions = tuple(range(1, contract.expected_version + 1))
    if versions != expected_versions:
        raise TelemetrySchemaContractError(
            "Migration versions must be contiguous and ordered: "
            f"expected {expected_versions}, got {versions}"
        )

    names = [item.name for item in contract.migrations]
    if any(not name.strip() for name in names):
        raise TelemetrySchemaContractError(
            "Migration names must not be empty"
        )
    if len(set(names)) != len(names):
        raise TelemetrySchemaContractError(
            "Migration names must be unique"
        )

    for item in contract.migrations:
        for checksum in item.accepted_checksums:
            if not _SHA256_RE.fullmatch(checksum):
                raise TelemetrySchemaContractError(
                    f"Migration {item.version} has an invalid SHA-256 checksum"
                )
        if len(item.accepted_checksums) != 1 + len(item.compatible_checksums):
            raise TelemetrySchemaContractError(
                f"Migration {item.version} repeats a compatible checksum"
            )
        if item.execution_mode not in {"sql", "programmatic"}:
            raise TelemetrySchemaContractError(
                f"Migration {item.version} has an invalid execution mode"
            )


def migration_by_version(
    contract: TelemetrySchemaContract,
) -> dict[int, MigrationDescriptor]:
    validate_contract(contract)
    return {item.version: item for item in contract.migrations}


def pending_migrations(
    contract: TelemetrySchemaContract,
    snapshot: TelemetrySchemaSnapshot,
) -> tuple[MigrationDescriptor, ...]:
    """Return the ordered suffix not yet recorded by the database."""
    catalog = migration_by_version(contract)
    applied_versions = {item.version for item in snapshot.applied_migrations}
    return tuple(
        catalog[version]
        for version in range(1, contract.expected_version + 1)
        if version not in applied_versions
    )


def validate_snapshot(
    contract: TelemetrySchemaContract,
    snapshot: TelemetrySchemaSnapshot,
    *,
    require_current: bool = True,
    verify_history: bool = True,
) -> SchemaValidationReport:
    """Validate a read-only snapshot without importing or executing SQLite."""
    catalog = migration_by_version(contract)
    violations: list[SchemaViolation] = []

    missing = sorted(contract.required_tables - set(snapshot.tables))
    if missing:
        violations.append(
            SchemaViolation(
                "MISSING_REQUIRED_TABLES",
                f"Missing required tables: {missing}",
            )
        )

    if require_current and snapshot.applied_version != contract.expected_version:
        violations.append(
            SchemaViolation(
                "SCHEMA_VERSION_MISMATCH",
                f"Schema version {snapshot.applied_version} does not match "
                f"expected {contract.expected_version}",
            )
        )
    elif snapshot.applied_version > contract.expected_version:
        violations.append(
            SchemaViolation(
                "SCHEMA_VERSION_AHEAD",
                f"Schema version {snapshot.applied_version} is newer than "
                f"supported {contract.expected_version}",
            )
        )

    if not snapshot.json_functions:
        violations.append(
            SchemaViolation(
                "SQLITE_JSON_UNAVAILABLE",
                "SQLite JSON functions are unavailable",
            )
        )
    if not snapshot.foreign_keys:
        violations.append(
            SchemaViolation(
                "FOREIGN_KEYS_DISABLED",
                "SQLite foreign_keys must be enabled",
            )
        )

    if verify_history:
        seen_versions: set[int] = set()
        for applied in snapshot.applied_migrations:
            if applied.version in seen_versions:
                violations.append(
                    SchemaViolation(
                        "DUPLICATE_MIGRATION_VERSION",
                        f"Migration version {applied.version} is recorded more than once",
                    )
                )
                continue
            seen_versions.add(applied.version)
            expected = catalog.get(applied.version)
            if expected is None:
                violations.append(
                    SchemaViolation(
                        "UNKNOWN_MIGRATION_VERSION",
                        f"Unknown migration version {applied.version}",
                    )
                )
                continue
            if applied.name != expected.name:
                violations.append(
                    SchemaViolation(
                        "MIGRATION_NAME_MISMATCH",
                        f"Migration {applied.version} name {applied.name!r} does not "
                        f"match expected {expected.name!r}",
                    )
                )
            if applied.checksum not in expected.accepted_checksums:
                violations.append(
                    SchemaViolation(
                        "MIGRATION_CHECKSUM_MISMATCH",
                        f"Migration {applied.version} checksum does not match contract",
                    )
                )

        required_history = set(range(1, snapshot.applied_version + 1))
        missing_history = sorted(required_history - seen_versions)
        if missing_history:
            violations.append(
                SchemaViolation(
                    "MIGRATION_HISTORY_GAP",
                    f"Migration history is missing versions: {missing_history}",
                )
            )

    pending = tuple(item.version for item in pending_migrations(contract, snapshot))
    return SchemaValidationReport(
        schema_name=contract.schema_name,
        expected_version=contract.expected_version,
        applied_version=snapshot.applied_version,
        valid=not violations,
        pending_versions=pending,
        violations=tuple(violations),
    )


def require_compatible_schema(
    contract: TelemetrySchemaContract,
    snapshot: TelemetrySchemaSnapshot,
    *,
    require_current: bool = True,
    verify_history: bool = True,
) -> SchemaValidationReport:
    report = validate_snapshot(
        contract,
        snapshot,
        require_current=require_current,
        verify_history=verify_history,
    )
    if report.violations:
        raise TelemetrySchemaContractError(report.violations[0].message)
    return report
