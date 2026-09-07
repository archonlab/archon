"""Storage-independent Stage 2M migration and integrity orchestration."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from Analyzer_next.core.telemetry.migration_audit import (
    REPORT_SCHEMA,
    STAGE,
    MigrationAuditDatabase,
    MigrationAuditDependencyError,
    MigrationAuditError,
    MigrationAuditImporter,
    MigrationAuditParityValidator,
    MigrationAuditSource,
)


@dataclass(frozen=True, slots=True)
class MigrationAuditCommand:
    command: str
    source_root: str
    database_path: str
    rebuild_output: str | None = None
    batch_size: int = 1000
    max_mismatches: int = 100
    allowed_invalid_csv: int = 0


def run_migration_audit(
    command: MigrationAuditCommand,
    *,
    source: MigrationAuditSource,
    database: MigrationAuditDatabase,
    importer: MigrationAuditImporter,
    parity: MigrationAuditParityValidator,
    now: Callable[[], str],
) -> dict[str, Any]:
    if command.command not in {"audit", "migrate", "rebuild"}:
        raise MigrationAuditError(f"Unsupported command: {command.command}")
    if command.batch_size < 1:
        raise MigrationAuditError("batch_size must be >= 1")
    if command.allowed_invalid_csv < 0:
        raise MigrationAuditError("allowed_invalid_csv must be >= 0")

    source_root = source.resolve_path(command.source_root)
    active_database = database.resolve_path(command.database_path)
    target_database = active_database
    if command.command == "rebuild":
        if command.rebuild_output is None:
            raise MigrationAuditError(
                "rebuild requires a separate --rebuild-output path"
            )
        target_database = database.resolve_path(command.rebuild_output)
        if target_database == active_database:
            raise MigrationAuditError(
                "rebuild output must differ from the active database"
            )
        if database.exists(target_database):
            raise MigrationAuditError(
                f"rebuild output already exists: {target_database}"
            )

    inventories = source.discover_runs(source_root)
    before = dict(database.inspect(target_database))

    if command.command in {"migrate", "rebuild"}:
        database.initialize(target_database)

    existing_ids = set(before.get("run_ids", ()))
    run_results: list[dict[str, Any]] = []
    imported = 0
    verified = 0
    conflicts = 0
    invalid = 0
    missing = 0

    for inventory in inventories:
        result: dict[str, Any] = {
            "run_id": inventory.run_id,
            "rule_id": inventory.rule_id,
            "valid": inventory.valid,
            "incomplete": inventory.incomplete,
            "errors": list(inventory.errors),
            "warnings": list(inventory.warnings),
            "channels": [asdict(item) for item in inventory.channel_inventory],
        }
        if not inventory.valid:
            result["status"] = "invalid_csv"
            invalid += 1
            run_results.append(result)
            continue

        if inventory.run_id in existing_ids:
            try:
                parity_result = parity.validate_run(
                    database_path=target_database,
                    inventory=inventory,
                    max_mismatches=command.max_mismatches,
                )
                result["parity"] = dict(parity_result.report)
                if parity_result.passed:
                    result["status"] = "verified_existing"
                    verified += 1
                else:
                    result["status"] = "existing_conflict"
                    conflicts += 1
            except MigrationAuditDependencyError as exc:
                result["status"] = "existing_conflict"
                result["errors"].append(str(exc))
                conflicts += 1
            run_results.append(result)
            continue

        if command.command == "audit":
            result["status"] = "missing_from_sqlite"
            missing += 1
            run_results.append(result)
            continue

        try:
            import_report = importer.import_run(
                database_path=target_database,
                inventory=inventory,
                source_root=source_root,
                batch_size=command.batch_size,
            )
            parity_result = parity.validate_run(
                database_path=target_database,
                inventory=inventory,
                max_mismatches=command.max_mismatches,
            )
            result["import"] = dict(import_report)
            result["parity"] = dict(parity_result.report)
            if not parity_result.passed:
                result["status"] = "imported_parity_failed"
                conflicts += 1
            else:
                result["status"] = "imported_verified"
                imported += 1
                existing_ids.add(inventory.run_id)
        except MigrationAuditDependencyError as exc:
            result["status"] = "import_failed"
            result["errors"].append(str(exc))
            conflicts += 1
        run_results.append(result)

    after = dict(database.inspect(target_database))
    csv_ids = {item.run_id for item in inventories}
    sqlite_ids = set(after.get("run_ids", ()))
    sqlite_only = sorted(sqlite_ids - csv_ids)

    passed = (
        invalid <= command.allowed_invalid_csv
        and conflicts == 0
        and (missing == 0 or command.command == "audit")
        and (
            not after.get("exists")
            if command.command == "audit" and not database.exists(active_database)
            else bool(after.get("passed"))
        )
    )
    if command.command == "audit" and missing:
        passed = False

    return {
        "report_schema": REPORT_SCHEMA,
        "stage": STAGE,
        "generated_at_utc": now(),
        "command": command.command,
        "source_root": source_root,
        "active_database": active_database,
        "audited_database": target_database,
        "summary": {
            "csv_runs_discovered": len(inventories),
            "csv_runs_valid": sum(1 for item in inventories if item.valid),
            "csv_runs_invalid": invalid,
            "allowed_invalid_csv": command.allowed_invalid_csv,
            "runs_imported": imported,
            "runs_verified_existing": verified,
            "runs_missing_from_sqlite": missing,
            "run_conflicts": conflicts,
            "sqlite_only_runs": len(sqlite_only),
            "passed": passed,
        },
        "sqlite_only_run_ids": sqlite_only,
        "database_before": before,
        "database_after": after,
        "runs": run_results,
    }


__all__ = ["MigrationAuditCommand", "run_migration_audit"]
