#!/usr/bin/env python3
"""Native facade and CLI contract for legacy CSV-to-SQLite import."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from Analyzer_next.application.telemetry.csv_import import (
    CSVImportCommand,
    run_csv_import,
)
from Analyzer_next.core.telemetry.csv_import import (
    CSVImportError,
    CSVImportReport,
    ChannelImportResult,
    NullImportAuditHook,
)

from .csv_source import StreamingCsvImportSource
from .sqlite_import_sink import NativeSqliteImportSinkFactory
from .sqlite_writer import SQLiteWriter, SQLiteWriterConfig, SQLiteWriterError


def import_csv_to_sqlite(
    *,
    database_path: str | Path,
    samples_csv: str | Path | None = None,
    events_csv: str | Path | None = None,
    chronicle_csv: str | Path | None = None,
    pressure_csv: str | Path | None = None,
    run_id: str | None = None,
    rule_id: int | None = None,
    world_id: str | None = None,
    observer_version: str = "legacy-csv-import",
    source_path: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    batch_size: int = 500,
    duplicate_policy: str = "replace",
    existing_run_policy: str = "error",
    dry_run: bool = False,
) -> CSVImportReport:
    source = StreamingCsvImportSource()
    return run_csv_import(
        CSVImportCommand(
            database_path=str(Path(database_path).expanduser().resolve()),
            channel_paths={
                "sample": samples_csv,
                "event": events_csv,
                "chronicle": chronicle_csv,
                "pressure": pressure_csv,
            },
            run_id=run_id,
            rule_id=rule_id,
            world_id=world_id,
            observer_version=observer_version,
            source_path=source_path,
            metadata=dict(metadata or {}),
            batch_size=batch_size,
            duplicate_policy=duplicate_policy,
            existing_run_policy=existing_run_policy,
            dry_run=dry_run,
        ),
        source=source,
        sink_factory=NativeSqliteImportSinkFactory(),
        audit_hook=NullImportAuditHook(),
        now=_utc_now,
        fallback_run_id=_fallback_run_id,
    )


def infer_run_identity(paths: Iterable[str | Path]) -> dict[str, Any]:
    return StreamingCsvImportSource.infer_run_identity(
        str(Path(path)) for path in paths
    )


def _fallback_run_id(rule_id: int | None) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if rule_id is None:
        return f"legacy_import_{stamp}"
    return f"rule_{rule_id:05d}_{stamp}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import legacy ARCHON Observer CSV files into Telemetry SQLite."
        )
    )
    parser.add_argument("database")
    parser.add_argument("--samples-csv")
    parser.add_argument("--events-csv")
    parser.add_argument("--chronicle-csv")
    parser.add_argument("--pressure-csv")
    parser.add_argument("--run-id")
    parser.add_argument("--rule-id", type=int)
    parser.add_argument("--world-id")
    parser.add_argument(
        "--observer-version",
        default="legacy-csv-import",
    )
    parser.add_argument("--source-path")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--duplicate-policy",
        choices=("replace", "ignore", "error"),
        default="replace",
    )
    parser.add_argument(
        "--existing-run-policy",
        choices=("error", "append", "replace"),
        default="error",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = import_csv_to_sqlite(
            database_path=args.database,
            samples_csv=args.samples_csv,
            events_csv=args.events_csv,
            chronicle_csv=args.chronicle_csv,
            pressure_csv=args.pressure_csv,
            run_id=args.run_id,
            rule_id=args.rule_id,
            world_id=args.world_id,
            observer_version=args.observer_version,
            source_path=args.source_path,
            batch_size=args.batch_size,
            duplicate_policy=args.duplicate_policy,
            existing_run_policy=args.existing_run_policy,
            dry_run=args.dry_run,
        )
    except (CSVImportError, SQLiteWriterError) as exc:
        print(f"IMPORT FAILED: {exc}")
        return 1

    for item in report.channels:
        if item.path is None:
            continue
        print(
            f"{item.channel:10} "
            f"read={item.rows_read} "
            f"written={item.rows_written} "
            f"skipped={item.rows_skipped} "
            f"ticks={item.first_tick}..{item.last_tick}"
        )
    print(
        f"RESULT: {report.status.upper()} "
        f"run_id={report.run_id} "
        f"rows={report.total_rows_written}/{report.total_rows_read}"
    )
    if args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.to_json() + "\n", encoding="utf-8")
    return 0


__all__ = [
    "CSVImportError",
    "CSVImportReport",
    "ChannelImportResult",
    "SQLiteWriter",
    "SQLiteWriterConfig",
    "SQLiteWriterError",
    "import_csv_to_sqlite",
    "infer_run_identity",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
