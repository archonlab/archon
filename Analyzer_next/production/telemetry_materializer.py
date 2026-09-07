"""Materialize canonical Telemetry SQLite runs for the Analyzer DAG.

The production Analyzer still consumes deterministic CSV files under
``observation_logs``. This module owns that compatibility projection while the
read model is supplied through a storage-independent Telemetry repository port.
The default adapter reads canonical SQLite without importing legacy Storage.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from Analyzer_next.adapters.telemetry.sqlite_repository import (
    SQLiteTelemetryRepository,
)
from Analyzer_next.core.telemetry.contracts import (
    RunSummary,
    TelemetryReadRepository,
)


class TelemetryMaterializationError(RuntimeError):
    """Raised when no eligible Telemetry run can be materialized."""


@dataclass(frozen=True, slots=True)
class MaterializedChannel:
    channel: str
    path: str
    rows: int
    columns: int
    first_tick: int | None
    last_tick: int | None


@dataclass(frozen=True, slots=True)
class MaterializedRun:
    run_id: str
    rule_id: int | None
    status: str
    output_dir: str
    channels: tuple[MaterializedChannel, ...]


@dataclass(frozen=True, slots=True)
class MaterializationReport:
    database_path: str
    output_dir: str
    runs: tuple[MaterializedRun, ...]
    total_runs: int
    total_rows: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": self.database_path,
            "output_dir": self.output_dir,
            "runs": [
                {
                    **asdict(run),
                    "channels": [
                        asdict(channel)
                        for channel in run.channels
                    ],
                }
                for run in self.runs
            ],
            "total_runs": self.total_runs,
            "total_rows": self.total_rows,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )


CHANNEL_FILE_SUFFIX = {
    "sample": "samples.csv",
    "event": "events.csv",
    "chronicle": "chronicle.csv",
    "pressure": "pressure_timeline.csv",
}

PREFERRED_COLUMNS = {
    "sample": (
        "tick",
        "alive",
        "objects",
        "largest",
        "total_living_mass",
        "top10_mass",
        "mean_object_size",
        "ecosystem_health",
        "stability_index",
        "ecosystem_phase",
        "morphology_class",
        "emergence_score",
        "validation_quality",
    ),
    "event": ("tick", "type", "detail"),
    "chronicle": (
        "tick",
        "severity",
        "event",
        "family",
        "colony",
        "phase",
        "pressure",
        "risk",
        "cause",
        "details",
    ),
    "pressure": (
        "tick",
        "phase",
        "stress",
        "adapt",
        "pressure",
        "recovery",
        "risk",
        "cause",
        "ecosystem_phase",
        "objects",
        "mass",
        "largest",
        "families",
    ),
}


def materialize_telemetry(
    *,
    database_path: str | Path,
    results_dir: str | Path,
    run_ids: Sequence[str] | None = None,
    rule_id: int | None = None,
    latest_only: bool = False,
    statuses: Sequence[str] | None = None,
    overwrite: bool = True,
    include_empty_channels: bool = False,
    repository: TelemetryReadRepository | None = None,
) -> MaterializationReport:
    """Export selected Telemetry runs into Analyzer-compatible CSV files."""
    database_path = Path(database_path).expanduser().resolve()
    results_dir = Path(results_dir).expanduser().resolve()
    output_dir = results_dir / "observation_logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    allowed_statuses = set(statuses or ())

    if repository is None:
        with SQLiteTelemetryRepository(database_path) as sqlite_repository:
            materialized_runs, total_rows = _materialize_runs(
                sqlite_repository,
                output_dir=output_dir,
                run_ids=run_ids,
                rule_id=rule_id,
                latest_only=latest_only,
                allowed_statuses=allowed_statuses,
                overwrite=overwrite,
                include_empty_channels=include_empty_channels,
            )
    else:
        materialized_runs, total_rows = _materialize_runs(
            repository,
            output_dir=output_dir,
            run_ids=run_ids,
            rule_id=rule_id,
            latest_only=latest_only,
            allowed_statuses=allowed_statuses,
            overwrite=overwrite,
            include_empty_channels=include_empty_channels,
        )

    report = MaterializationReport(
        database_path=str(database_path),
        output_dir=str(output_dir),
        runs=tuple(materialized_runs),
        total_runs=len(materialized_runs),
        total_rows=total_rows,
    )
    (output_dir / "telemetry_bridge_manifest.json").write_text(
        report.to_json() + "\n",
        encoding="utf-8",
    )
    return report


def _materialize_runs(
    repository: TelemetryReadRepository,
    *,
    output_dir: Path,
    run_ids: Sequence[str] | None,
    rule_id: int | None,
    latest_only: bool,
    allowed_statuses: set[str],
    overwrite: bool,
    include_empty_channels: bool,
) -> tuple[list[MaterializedRun], int]:
    runs = _select_runs(
        repository,
        run_ids=run_ids,
        rule_id=rule_id,
        latest_only=latest_only,
    )
    if allowed_statuses:
        runs = [run for run in runs if run.status in allowed_statuses]
    if not runs:
        raise TelemetryMaterializationError(
            "No matching Telemetry runs were found"
        )

    materialized_runs: list[MaterializedRun] = []
    total_rows = 0
    for run in runs:
        channels: list[MaterializedChannel] = []
        for channel in ("sample", "event", "chronicle", "pressure"):
            rows = repository.read_channel(
                run.run_id,
                channel,
                payload_only=True,
            )
            if not rows and not include_empty_channels:
                continue

            path = output_dir / (
                f"{run.run_id}_{CHANNEL_FILE_SUFFIX[channel]}"
            )
            if path.exists() and not overwrite:
                summary = repository.channel_summary(run.run_id, channel)
                channels.append(MaterializedChannel(
                    channel=channel,
                    path=str(path),
                    rows=summary.row_count,
                    columns=_count_csv_columns(path),
                    first_tick=summary.first_tick,
                    last_tick=summary.last_tick,
                ))
                total_rows += summary.row_count
                continue

            fieldnames = _fieldnames_for_rows(channel, rows)
            _write_csv(path, rows, fieldnames)
            valid_ticks = [
                tick
                for tick in (_tick_or_none(row.get("tick")) for row in rows)
                if tick is not None
            ]
            channels.append(MaterializedChannel(
                channel=channel,
                path=str(path),
                rows=len(rows),
                columns=len(fieldnames),
                first_tick=min(valid_ticks) if valid_ticks else None,
                last_tick=max(valid_ticks) if valid_ticks else None,
            ))
            total_rows += len(rows)

        materialized_runs.append(MaterializedRun(
            run_id=run.run_id,
            rule_id=run.rule_id,
            status=run.status,
            output_dir=str(output_dir),
            channels=tuple(channels),
        ))
    return materialized_runs, total_rows


def _select_runs(
    api: TelemetryReadRepository,
    *,
    run_ids: Sequence[str] | None,
    rule_id: int | None,
    latest_only: bool,
) -> list[RunSummary]:
    if run_ids:
        return [api.get_run(run_id) for run_id in run_ids]
    if latest_only:
        latest = api.latest_run(rule_id=rule_id)
        return [latest] if latest is not None else []
    return api.list_runs(rule_id=rule_id, newest_first=False)


def _fieldnames_for_rows(
    channel: str,
    rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in PREFERRED_COLUMNS[channel]:
        if any(name in row for row in rows):
            ordered.append(name)
            seen.add(name)
    for row in rows:
        for raw_key in row:
            key = str(raw_key)
            if key not in seen:
                ordered.append(key)
                seen.add(key)
    if not ordered:
        ordered = list(PREFERRED_COLUMNS[channel])
    if "tick" in ordered:
        ordered.remove("tick")
        ordered.insert(0, "tick")
    return ordered


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str],
) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: _csv_value(row.get(key))
                for key in fieldnames
            })
    temporary.replace(path)


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return value


def _tick_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _count_csv_columns(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return len(next(csv.reader(handle), []))


__all__ = [
    "MaterializationReport",
    "MaterializedChannel",
    "MaterializedRun",
    "TelemetryMaterializationError",
    "materialize_telemetry",
]
