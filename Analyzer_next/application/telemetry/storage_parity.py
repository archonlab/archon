"""Storage-independent CSV↔SQLite parity orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import zip_longest
from typing import Any

from Analyzer_next.core.telemetry.storage_parity import (
    CHANNELS,
    CHANNEL_COUNT_COLUMNS,
    PROMOTED_COLUMNS,
    UNIQUE_TICK_CHANNELS,
    ChannelParity,
    FieldMismatch,
    ParityCsvSource,
    ParitySqliteRow,
    ParitySqliteSource,
    ParitySqliteSourceFactory,
    StorageParityError,
    StorageParityReport,
    int_or_none,
    normalize_csv_value,
    normalize_promoted_value,
    normalize_value,
    track_duplicate,
    values_equal,
)


@dataclass(frozen=True, slots=True)
class StorageParityCommand:
    database_path: str
    run_id: str
    channel_paths: dict[str, str | None]
    float_tolerance: float = 1e-9
    max_mismatches_per_channel: int = 100


def run_storage_parity(
    command: StorageParityCommand,
    *,
    csv_source: ParityCsvSource,
    sqlite_factory: ParitySqliteSourceFactory,
) -> StorageParityReport:
    if command.float_tolerance < 0:
        raise StorageParityError("float_tolerance must be >= 0")
    if command.max_mismatches_per_channel < 1:
        raise StorageParityError(
            "max_mismatches_per_channel must be >= 1"
        )

    database_path = sqlite_factory.resolve_path(command.database_path)
    sqlite_source = sqlite_factory.open(database_path)
    csv_paths = {
        channel: csv_source.resolve_path(command.channel_paths.get(channel))
        for channel in CHANNELS
    }
    try:
        run = sqlite_source.get_run(command.run_id)
        channels = tuple(
            _validate_channel(
                sqlite_source=sqlite_source,
                csv_source=csv_source,
                run_id=command.run_id,
                channel=channel,
                csv_path=csv_paths[channel],
                float_tolerance=command.float_tolerance,
                max_mismatches=command.max_mismatches_per_channel,
            )
            for channel in CHANNELS
        )

        counter_mismatches = {}
        for item in channels:
            stored = int(run[CHANNEL_COUNT_COLUMNS[item.channel]])
            actual = int(item.sqlite_count)
            if stored != actual:
                counter_mismatches[item.channel] = (stored, actual)

        passed = all(item.passed for item in channels) and not counter_mismatches
        return StorageParityReport(
            run_id=command.run_id,
            database_path=database_path,
            channels=channels,
            run_counter_mismatches=counter_mismatches,
            passed=passed,
            summary={
                "checked_channels": len(channels),
                "passed_channels": sum(1 for item in channels if item.passed),
                "total_csv_rows": sum(item.csv_count for item in channels),
                "total_sqlite_rows": sum(item.sqlite_count for item in channels),
                "total_field_mismatches": sum(
                    len(item.field_mismatches) for item in channels
                ),
                "total_promoted_column_mismatches": sum(
                    len(item.promoted_column_mismatches) for item in channels
                ),
            },
        )
    finally:
        sqlite_source.close()


def _validate_channel(
    *,
    sqlite_source: ParitySqliteSource,
    csv_source: ParityCsvSource,
    run_id: str,
    channel: str,
    csv_path: str | None,
    float_tolerance: float,
    max_mismatches: int,
) -> ChannelParity:
    sqlite_rows = sqlite_source.iter_channel(run_id, channel)
    if csv_path is not None and not csv_source.exists(csv_path):
        raise StorageParityError(f"CSV file does not exist: {csv_path}")

    csv_count = 0
    sqlite_count = 0
    tick_match = True
    csv_seen: set[int] = set()
    sqlite_seen: set[int] = set()
    csv_duplicates: set[int] = set()
    sqlite_duplicates: set[int] = set()
    field_mismatches: list[FieldMismatch] = []
    promoted_mismatches: list[FieldMismatch] = []
    missing = object()
    csv_rows = iter(()) if csv_path is None else csv_source.iter_rows(csv_path)

    for index, (csv_row, sqlite_item) in enumerate(
        zip_longest(csv_rows, sqlite_rows, fillvalue=missing)
    ):
        if csv_row is not missing:
            csv_count += 1
            csv_tick = int_or_none(csv_row.get("tick"))
            track_duplicate(csv_tick, csv_seen, csv_duplicates)
        else:
            csv_tick = None

        if sqlite_item is not missing:
            sqlite_count += 1
            assert isinstance(sqlite_item, ParitySqliteRow)
            sqlite_row = sqlite_item.columns
            payload = sqlite_item.payload
            sqlite_tick = int_or_none(payload.get("tick"))
            track_duplicate(sqlite_tick, sqlite_seen, sqlite_duplicates)
        else:
            sqlite_row = None
            payload = None
            sqlite_tick = None

        if (
            csv_row is missing
            or sqlite_item is missing
            or csv_tick != sqlite_tick
        ):
            tick_match = False
        if csv_row is missing or sqlite_item is missing:
            continue

        tick = sqlite_tick
        all_fields = sorted(set(csv_row) | set(payload))
        if len(field_mismatches) < max_mismatches:
            for field_name in all_fields:
                csv_value = normalize_csv_value(csv_row.get(field_name))
                sqlite_value = normalize_value(payload.get(field_name))
                if not values_equal(
                    csv_value,
                    sqlite_value,
                    tolerance=float_tolerance,
                ):
                    field_mismatches.append(FieldMismatch(
                        channel=channel,
                        row_index=index,
                        tick=tick,
                        field=field_name,
                        csv_value=csv_value,
                        sqlite_value=sqlite_value,
                    ))
                    if len(field_mismatches) >= max_mismatches:
                        break

        if len(promoted_mismatches) < max_mismatches:
            for column in PROMOTED_COLUMNS[channel]:
                if channel == "event" and column == "event_type":
                    payload_value = normalize_value(
                        payload.get("type", payload.get("event_type"))
                    )
                else:
                    payload_value = normalize_value(payload.get(column))
                column_value = normalize_value(sqlite_row[column])
                payload_value = normalize_promoted_value(
                    channel=channel,
                    field_name=column,
                    value=payload_value,
                )
                column_value = normalize_promoted_value(
                    channel=channel,
                    field_name=column,
                    value=column_value,
                )
                if channel == "sample" and column == "alive":
                    if payload_value is not None:
                        payload_value = bool(payload_value)
                    if column_value is not None:
                        column_value = bool(column_value)
                if not values_equal(
                    payload_value,
                    column_value,
                    tolerance=float_tolerance,
                ):
                    promoted_mismatches.append(FieldMismatch(
                        channel=channel,
                        row_index=index,
                        tick=tick,
                        field=column,
                        csv_value=payload_value,
                        sqlite_value=column_value,
                    ))
                    if len(promoted_mismatches) >= max_mismatches:
                        break

    count_match = csv_count == sqlite_count
    duplicate_ticks_csv = tuple(sorted(csv_duplicates))
    duplicate_ticks_sqlite = tuple(sorted(sqlite_duplicates))
    uniqueness_ok = True
    if channel in UNIQUE_TICK_CHANNELS:
        uniqueness_ok = not duplicate_ticks_csv and not duplicate_ticks_sqlite
    passed = (
        count_match
        and tick_match
        and uniqueness_ok
        and not field_mismatches
        and not promoted_mismatches
    )
    return ChannelParity(
        channel=channel,
        csv_path=csv_path,
        csv_count=csv_count,
        sqlite_count=sqlite_count,
        count_match=count_match,
        tick_match=tick_match,
        duplicate_ticks_csv=duplicate_ticks_csv,
        duplicate_ticks_sqlite=duplicate_ticks_sqlite,
        field_mismatches=tuple(field_mismatches),
        promoted_column_mismatches=tuple(promoted_mismatches),
        passed=passed,
    )


__all__ = ["StorageParityCommand", "run_storage_parity"]
