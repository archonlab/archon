"""Storage-independent contracts for the Stage 2M migration audit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


STAGE = "2M"
REPORT_SCHEMA = "archon.sqlite_migration_integrity_report.v1"
CHANNEL_SUFFIXES = {
    "_samples.csv": "sample",
    "_events.csv": "event",
    "_chronicle.csv": "chronicle",
    "_pressure_timeline.csv": "pressure",
    "_pressure.csv": "pressure",
}
CHANNEL_ARGUMENTS = {
    "sample": "samples_csv",
    "event": "events_csv",
    "chronicle": "chronicle_csv",
    "pressure": "pressure_csv",
}
UNIQUE_TICK_CHANNELS = frozenset({"sample", "pressure"})


class MigrationAuditError(RuntimeError):
    """Raised when Stage 2M cannot continue safely."""


class MigrationAuditDependencyError(RuntimeError):
    """Expected importer, parity, or SQLite failure for one run."""


@dataclass(frozen=True, slots=True)
class ChannelInventory:
    channel: str
    path: str
    rows: int
    first_tick: int | None
    last_tick: int | None
    duplicate_ticks: tuple[int, ...]
    valid: bool
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunInventory:
    run_id: str
    rule_id: int | None
    channels: Mapping[str, str]
    channel_inventory: tuple[ChannelInventory, ...]
    valid: bool
    incomplete: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def import_arguments(self) -> dict[str, str]:
        return {
            CHANNEL_ARGUMENTS[channel]: path
            for channel, path in self.channels.items()
        }


@dataclass(frozen=True, slots=True)
class ParityAuditResult:
    passed: bool
    report: Mapping[str, Any]


class MigrationAuditSource(Protocol):
    def resolve_path(self, value: str) -> str: ...

    def discover_runs(self, source_root: str) -> tuple[RunInventory, ...]: ...


class MigrationAuditDatabase(Protocol):
    def resolve_path(self, value: str) -> str: ...

    def exists(self, database_path: str) -> bool: ...

    def initialize(self, database_path: str) -> None: ...

    def inspect(self, database_path: str) -> Mapping[str, Any]: ...


class MigrationAuditImporter(Protocol):
    def import_run(
        self,
        *,
        database_path: str,
        inventory: RunInventory,
        source_root: str,
        batch_size: int,
    ) -> Mapping[str, Any]: ...


class MigrationAuditParityValidator(Protocol):
    def validate_run(
        self,
        *,
        database_path: str,
        inventory: RunInventory,
        max_mismatches: int,
    ) -> ParityAuditResult: ...


__all__ = [
    "CHANNEL_ARGUMENTS",
    "CHANNEL_SUFFIXES",
    "REPORT_SCHEMA",
    "STAGE",
    "UNIQUE_TICK_CHANNELS",
    "ChannelInventory",
    "MigrationAuditDatabase",
    "MigrationAuditDependencyError",
    "MigrationAuditError",
    "MigrationAuditImporter",
    "MigrationAuditParityValidator",
    "MigrationAuditSource",
    "ParityAuditResult",
    "RunInventory",
]
