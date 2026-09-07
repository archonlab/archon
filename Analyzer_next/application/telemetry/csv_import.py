"""Storage-independent orchestration of one CSV-to-SQLite import."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Callable, Mapping

from Analyzer_next.core.telemetry.csv_import import (
    CHANNELS,
    CSVImportError,
    CSVImportReport,
    ChannelImportResult,
    CsvImportSource,
    ImportAuditHook,
    SqliteImportSinkFactory,
)


@dataclass(frozen=True, slots=True)
class CSVImportCommand:
    database_path: str
    channel_paths: Mapping[str, str | None]
    run_id: str | None = None
    rule_id: int | None = None
    world_id: str | None = None
    observer_version: str = "legacy-csv-import"
    source_path: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    batch_size: int = 500
    duplicate_policy: str = "replace"
    existing_run_policy: str = "error"
    dry_run: bool = False


def run_csv_import(
    command: CSVImportCommand,
    *,
    source: CsvImportSource,
    sink_factory: SqliteImportSinkFactory,
    audit_hook: ImportAuditHook,
    now: Callable[[], str],
    fallback_run_id: Callable[[int | None], str],
) -> CSVImportReport:
    paths = {
        channel: source.resolve_path(command.channel_paths.get(channel))
        for channel in CHANNELS
    }
    provided = [path for path in paths.values() if path is not None]
    if not provided:
        raise CSVImportError("At least one CSV path must be provided")
    source.require_files(provided)

    if command.duplicate_policy not in {"replace", "ignore", "error"}:
        raise CSVImportError(
            "duplicate_policy must be replace, ignore, or error"
        )
    if command.existing_run_policy not in {"error", "append", "replace"}:
        raise CSVImportError(
            "existing_run_policy must be error, append, or replace"
        )
    if command.batch_size < 1:
        raise CSVImportError("batch_size must be >= 1")

    inferred = source.infer_run_identity(provided)
    resolved_rule_id = (
        int(command.rule_id)
        if command.rule_id is not None
        else inferred["rule_id"]
    )
    resolved_run_id = (
        str(command.run_id).strip()
        if command.run_id is not None
        else inferred["run_id"]
    )
    if not resolved_run_id:
        resolved_run_id = fallback_run_id(resolved_rule_id)
    resolved_world_id = (
        str(command.world_id)
        if command.world_id is not None
        else (
            f"rule_{resolved_rule_id:05d}"
            if resolved_rule_id is not None
            else None
        )
    )

    scans: list[ChannelImportResult] = []
    final_tick: int | None = None
    for channel in CHANNELS:
        path = paths[channel]
        if path is None:
            scans.append(ChannelImportResult(
                channel, None, 0, 0, 0, None, None
            ))
            continue
        row_count, first, last = source.scan(path, channel)
        if last is not None:
            final_tick = last if final_tick is None else max(final_tick, last)
        scans.append(ChannelImportResult(
            channel, path, row_count, 0, 0, first, last
        ))

    database_path = command.database_path
    if command.dry_run:
        report = CSVImportReport(
            database_path,
            resolved_run_id,
            resolved_rule_id,
            final_tick,
            tuple(scans),
            sum(item.rows_read for item in scans),
            0,
            0,
            "dry-run",
            True,
        )
        audit_hook.completed(report)
        return report

    sink_factory.prepare_existing_run(
        database_path=database_path,
        run_id=resolved_run_id,
        policy=command.existing_run_policy,
    )
    import_metadata = {
        "imported_from_csv": True,
        "imported_at_utc": now(),
        "source_files": {
            channel: path for channel, path in paths.items()
        },
        "duplicate_policy": command.duplicate_policy,
        "existing_run_policy": command.existing_run_policy,
    }
    import_metadata.update(dict(command.metadata))

    sink = sink_factory.open_sink(
        database_path=database_path,
        run_id=resolved_run_id,
        rule_id=resolved_rule_id,
        world_id=resolved_world_id,
        observer_version=command.observer_version,
        started_at_utc=None,
        source_path=command.source_path or os.path.dirname(provided[0]),
        metadata=import_metadata,
        batch_size=command.batch_size,
        duplicate_policy=command.duplicate_policy,
        existing_run_policy=command.existing_run_policy,
    )

    results: list[ChannelImportResult] = []
    total_written = 0
    total_skipped = 0
    try:
        for scan in scans:
            written = 0
            skipped = 0
            path = paths[scan.channel]
            if path is None:
                results.append(scan)
                continue
            for row in source.iter_rows(path, scan.channel):
                if sink.write(scan.channel, row):
                    written += 1
                else:
                    skipped += 1
            results.append(ChannelImportResult(
                scan.channel,
                scan.path,
                scan.rows_read,
                written,
                skipped,
                scan.first_tick,
                scan.last_tick,
            ))
            total_written += written
            total_skipped += skipped

        sink.finalize(
            status="imported",
            final_tick=final_tick,
            metadata_update={
                "import_summary": {
                    "rows_read": sum(item.rows_read for item in results),
                    "rows_written": total_written,
                    "rows_skipped": total_skipped,
                    "final_tick": final_tick,
                }
            },
        )
    except Exception:
        sink.abort()
        if command.existing_run_policy != "append":
            sink_factory.remove_run_quietly(
                database_path=database_path,
                run_id=resolved_run_id,
            )
        raise
    else:
        sink.close()

    report = CSVImportReport(
        database_path,
        resolved_run_id,
        resolved_rule_id,
        final_tick,
        tuple(results),
        sum(item.rows_read for item in results),
        total_written,
        total_skipped,
        "imported",
        False,
    )
    audit_hook.completed(report)
    return report


__all__ = ["CSVImportCommand", "run_csv_import"]
