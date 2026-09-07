#!/usr/bin/env python3
"""Native facade and CLI contract for CSV↔SQLite storage parity."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from Analyzer_next.application.telemetry.storage_parity import (
    StorageParityCommand,
    run_storage_parity,
)
from Analyzer_next.core.telemetry.storage_parity import (
    ChannelParity,
    FieldMismatch,
    StorageParityError,
    StorageParityReport,
)

from .parity_csv_source import StreamingParityCsvSource
from .sqlite_parity_source import SQLiteParitySourceFactory


def validate_storage_parity(
    *,
    database_path: str | Path,
    run_id: str,
    samples_csv: str | Path | None = None,
    events_csv: str | Path | None = None,
    chronicle_csv: str | Path | None = None,
    pressure_csv: str | Path | None = None,
    float_tolerance: float = 1e-9,
    max_mismatches_per_channel: int = 100,
) -> StorageParityReport:
    return run_storage_parity(
        StorageParityCommand(
            database_path=str(database_path),
            run_id=run_id,
            channel_paths={
                "sample": samples_csv,
                "event": events_csv,
                "chronicle": chronicle_csv,
                "pressure": pressure_csv,
            },
            float_tolerance=float_tolerance,
            max_mismatches_per_channel=max_mismatches_per_channel,
        ),
        csv_source=StreamingParityCsvSource(),
        sqlite_factory=SQLiteParitySourceFactory(),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare ARCHON Telemetry CSV files with one SQLite run."
        )
    )
    parser.add_argument("database")
    parser.add_argument("run_id")
    parser.add_argument("--samples-csv")
    parser.add_argument("--events-csv")
    parser.add_argument("--chronicle-csv")
    parser.add_argument("--pressure-csv")
    parser.add_argument(
        "--float-tolerance",
        type=float,
        default=1e-9,
    )
    parser.add_argument(
        "--max-mismatches",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--json-output",
        help="Optional path for the parity report JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_storage_parity(
        database_path=args.database,
        run_id=args.run_id,
        samples_csv=args.samples_csv,
        events_csv=args.events_csv,
        chronicle_csv=args.chronicle_csv,
        pressure_csv=args.pressure_csv,
        float_tolerance=args.float_tolerance,
        max_mismatches_per_channel=args.max_mismatches,
    )
    for item in report.channels:
        state = "PASS" if item.passed else "FAIL"
        print(
            f"{state:4} {item.channel:10} "
            f"csv={item.csv_count} sqlite={item.sqlite_count} "
            f"ticks={'ok' if item.tick_match else 'mismatch'} "
            f"fields={len(item.field_mismatches)} "
            f"promoted={len(item.promoted_column_mismatches)}"
        )
    if report.run_counter_mismatches:
        print("Run counters mismatch:", dict(report.run_counter_mismatches))
    print("RESULT:", "PASS" if report.passed else "FAIL")
    if args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.to_json() + "\n", encoding="utf-8")
    return 0 if report.passed else 1


__all__ = [
    "StorageParityError",
    "FieldMismatch",
    "ChannelParity",
    "StorageParityReport",
    "validate_storage_parity",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
