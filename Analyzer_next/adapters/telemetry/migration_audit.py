#!/usr/bin/env python3
"""Native Stage 2M facade and CLI contract."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from Analyzer_next.application.telemetry.migration_audit import (
    MigrationAuditCommand,
    run_migration_audit,
)
from Analyzer_next.core.telemetry.csv_import import CSVImportError
from Analyzer_next.core.telemetry.migration_audit import (
    ChannelInventory,
    MigrationAuditDependencyError,
    MigrationAuditError,
    ParityAuditResult,
    RunInventory,
)
from Analyzer_next.core.telemetry.storage_parity import StorageParityError

from .csv_import import import_csv_to_sqlite
from .migration_csv_source import StreamingMigrationCsvSource
from .sqlite_migration_audit import (
    NativeMigrationAuditDatabase,
    inspect_database as _inspect_database,
)
from .sqlite_writer import SQLiteWriterError
from .storage_parity import validate_storage_parity


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NativeMigrationAuditImporter:
    def import_run(
        self,
        *,
        database_path: str,
        inventory: RunInventory,
        source_root: str,
        batch_size: int,
    ) -> Mapping[str, Any]:
        try:
            report = import_csv_to_sqlite(
                database_path=database_path,
                run_id=inventory.run_id,
                rule_id=inventory.rule_id,
                batch_size=batch_size,
                duplicate_policy="error",
                existing_run_policy="error",
                metadata={
                    "stage": "2M",
                    "migration_source_root": source_root,
                },
                **inventory.import_arguments(),
            )
        except (CSVImportError, SQLiteWriterError, sqlite3.Error) as exc:
            raise MigrationAuditDependencyError(str(exc)) from exc
        return report.to_dict()


class NativeMigrationAuditParityValidator:
    def validate_run(
        self,
        *,
        database_path: str,
        inventory: RunInventory,
        max_mismatches: int,
    ) -> ParityAuditResult:
        try:
            report = validate_storage_parity(
                database_path=database_path,
                run_id=inventory.run_id,
                max_mismatches_per_channel=max_mismatches,
                **inventory.import_arguments(),
            )
        except (StorageParityError, sqlite3.Error) as exc:
            raise MigrationAuditDependencyError(str(exc)) from exc
        return ParityAuditResult(passed=report.passed, report=report.to_dict())


def discover_csv_runs(source_root: str | Path) -> tuple[RunInventory, ...]:
    source = StreamingMigrationCsvSource()
    return source.discover_runs(source.resolve_path(str(source_root)))


def inspect_database(database_path: str | Path) -> dict[str, Any]:
    return _inspect_database(str(database_path))


def run_stage2m(
    *,
    command: str,
    source_root: str | Path,
    database_path: str | Path,
    rebuild_output: str | Path | None = None,
    batch_size: int = 1000,
    max_mismatches: int = 100,
    allowed_invalid_csv: int = 0,
) -> dict[str, Any]:
    source = StreamingMigrationCsvSource()
    database = NativeMigrationAuditDatabase(clock=utc_now)
    return run_migration_audit(
        MigrationAuditCommand(
            command=command,
            source_root=str(source_root),
            database_path=str(database_path),
            rebuild_output=(
                None if rebuild_output is None else str(rebuild_output)
            ),
            batch_size=batch_size,
            max_mismatches=max_mismatches,
            allowed_invalid_csv=allowed_invalid_csv,
        ),
        source=source,
        database=database,
        importer=NativeMigrationAuditImporter(),
        parity=NativeMigrationAuditParityValidator(),
        now=utc_now,
    )


def _default_paths() -> tuple[Path, Path, Path]:
    project_root = Path(__file__).resolve().parents[4]
    source = project_root / "Results" / "Universe_Search" / "observation_logs"
    database = source / "telemetry.sqlite"
    report = (
        project_root
        / "Results"
        / "Analysis"
        / "sqlite_migration_integrity_report.json"
    )
    return source, database, report


def _build_parser() -> argparse.ArgumentParser:
    source, database, report = _default_paths()
    parser = argparse.ArgumentParser(
        description=(
            "Stage 2M: audit, migrate, or safely rebuild ARCHON telemetry."
        )
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("audit", "migrate", "rebuild"),
        default="audit",
    )
    parser.add_argument("--source-root", default=str(source))
    parser.add_argument("--database", default=str(database))
    parser.add_argument("--rebuild-output")
    parser.add_argument("--report", default=str(report))
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--max-mismatches", type=int, default=100)
    parser.add_argument(
        "--allowed-invalid-csv",
        type=int,
        default=0,
        help=(
            "Number of known legacy-invalid CSV runs that may be tolerated "
            "without failing the overall Stage 2M result."
        ),
    )
    return parser


def _write_report(path: str | Path, report: Mapping[str, Any]) -> None:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            dict(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = run_stage2m(
            command=args.command,
            source_root=args.source_root,
            database_path=args.database,
            rebuild_output=args.rebuild_output,
            batch_size=args.batch_size,
            max_mismatches=args.max_mismatches,
            allowed_invalid_csv=args.allowed_invalid_csv,
        )
        _write_report(args.report, report)
    except MigrationAuditError as exc:
        print(f"[Stage 2M] REFUSED: {exc}")
        return 2

    summary = report["summary"]
    print(
        "[Stage 2M] "
        f"CSV runs={summary['csv_runs_discovered']} "
        f"valid={summary['csv_runs_valid']} "
        f"invalid={summary['csv_runs_invalid']}"
    )
    print(
        "[Stage 2M] "
        f"imported={summary['runs_imported']} "
        f"verified={summary['runs_verified_existing']} "
        f"missing={summary['runs_missing_from_sqlite']} "
        f"conflicts={summary['run_conflicts']} "
        f"sqlite_only={summary['sqlite_only_runs']}"
    )
    print(
        "[Stage 2M] RESULT:",
        "PASS" if summary["passed"] else "ATTENTION_REQUIRED",
    )
    print(f"[Stage 2M] report: {Path(args.report).resolve()}")
    return 0 if summary["passed"] else 1


__all__ = [
    "MigrationAuditError",
    "ChannelInventory",
    "RunInventory",
    "discover_csv_runs",
    "inspect_database",
    "run_stage2m",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
