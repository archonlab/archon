"""Filesystem CSV discovery and preflight for the Stage 2M audit."""
from __future__ import annotations

import csv
from pathlib import Path
import re

from Analyzer_next.core.telemetry.migration_audit import (
    CHANNEL_SUFFIXES,
    UNIQUE_TICK_CHANNELS,
    ChannelInventory,
    MigrationAuditError,
    RunInventory,
)


class StreamingMigrationCsvSource:
    def resolve_path(self, value: str) -> str:
        return str(Path(value).expanduser().resolve())

    def discover_runs(self, source_root: str) -> tuple[RunInventory, ...]:
        root = Path(source_root)
        if not root.exists():
            raise MigrationAuditError(
                f"CSV source root does not exist: {root}"
            )

        grouped: dict[str, dict[str, Path]] = {}
        collisions: dict[str, list[str]] = {}
        for path in sorted(root.rglob("*.csv")):
            channel, run_id = _channel_and_run_id(path.name)
            if channel is None or run_id is None:
                continue
            bucket = grouped.setdefault(run_id, {})
            previous = bucket.get(channel)
            if previous is not None and previous != path:
                collisions.setdefault(run_id, []).append(
                    f"multiple {channel} files: {previous} | {path}"
                )
                continue
            bucket[channel] = path.resolve()

        inventories: list[RunInventory] = []
        for run_id in sorted(grouped):
            channels = grouped[run_id]
            errors = list(collisions.get(run_id, ()))
            warnings: list[str] = []
            channel_inventory: list[ChannelInventory] = []

            if "sample" not in channels:
                errors.append("missing required samples channel")
            for optional in ("event", "chronicle", "pressure"):
                if optional not in channels:
                    warnings.append(f"channel absent in legacy run: {optional}")

            for channel in ("sample", "event", "chronicle", "pressure"):
                path = channels.get(channel)
                if path is None:
                    continue
                item = _scan_channel(path, channel)
                channel_inventory.append(item)
                errors.extend(f"{channel}: {message}" for message in item.errors)

            rule_match = re.search(r"rule[_-]?(\d+)", run_id, re.I)
            rule_id = int(rule_match.group(1)) if rule_match else None
            if rule_id is None:
                warnings.append("rule_id could not be inferred from filename")

            inventories.append(RunInventory(
                run_id=run_id,
                rule_id=rule_id,
                channels={
                    channel: str(path) for channel, path in channels.items()
                },
                channel_inventory=tuple(channel_inventory),
                valid=not errors,
                incomplete=("sample" not in channels),
                errors=tuple(errors),
                warnings=tuple(warnings),
            ))
        return tuple(inventories)


def _channel_and_run_id(filename: str) -> tuple[str | None, str | None]:
    lowered = filename.lower()
    for suffix, channel in CHANNEL_SUFFIXES.items():
        if lowered.endswith(suffix):
            run_id = filename[: -len(suffix)].strip()
            return channel, run_id or None
    return None, None


def _scan_channel(path: Path, channel: str) -> ChannelInventory:
    errors: list[str] = []
    rows = 0
    first_tick: int | None = None
    last_tick: int | None = None
    previous_tick: int | None = None
    monotonic = True
    seen: set[int] = set()
    duplicates: set[int] = set()

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                errors.append("CSV has no header")
            elif "tick" not in reader.fieldnames:
                errors.append("CSV has no tick column")
            else:
                for row_index, row in enumerate(reader):
                    raw_tick = row.get("tick")
                    try:
                        tick = int(str(raw_tick).strip())
                    except (TypeError, ValueError):
                        errors.append(
                            f"row {row_index} has invalid tick {raw_tick!r}"
                        )
                        if len(errors) >= 20:
                            break
                        continue
                    if tick < 0:
                        errors.append(f"row {row_index} has negative tick")
                        if len(errors) >= 20:
                            break
                        continue

                    if channel == "event":
                        event_type = row.get("type", row.get("event_type"))
                        if event_type is None or not str(event_type).strip():
                            errors.append(f"row {row_index} has no event type")
                            if len(errors) >= 20:
                                break

                    rows += 1
                    first_tick = tick if first_tick is None else min(first_tick, tick)
                    last_tick = tick if last_tick is None else max(last_tick, tick)
                    if previous_tick is not None and tick < previous_tick:
                        monotonic = False
                    previous_tick = tick

                    if channel in UNIQUE_TICK_CHANNELS:
                        if tick in seen:
                            duplicates.add(tick)
                        else:
                            seen.add(tick)
    except (OSError, csv.Error) as exc:
        errors.append(str(exc))

    if rows == 0 and not errors:
        errors.append("CSV channel is empty")
    if duplicates:
        preview = ", ".join(str(item) for item in sorted(duplicates)[:20])
        errors.append(f"duplicate ticks: {preview}")
    if not monotonic:
        errors.append("tick order is not monotonic")

    return ChannelInventory(
        channel=channel,
        path=str(path),
        rows=rows,
        first_tick=first_tick,
        last_tick=last_tick,
        duplicate_ticks=tuple(sorted(duplicates)[:100]),
        valid=not errors,
        errors=tuple(errors),
    )


__all__ = ["StreamingMigrationCsvSource"]
