"""Storage-independent contracts for importing legacy Telemetry CSV rows."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Iterable, Iterator, Mapping, Protocol


CHANNELS = ("sample", "event", "chronicle", "pressure")


class CSVImportError(RuntimeError):
    """Raised when legacy CSV data cannot be imported safely."""


@dataclass(frozen=True, slots=True)
class ChannelImportResult:
    channel: str
    path: str | None
    rows_read: int
    rows_written: int
    rows_skipped: int
    first_tick: int | None
    last_tick: int | None


@dataclass(frozen=True, slots=True)
class CSVImportReport:
    database_path: str
    run_id: str
    rule_id: int | None
    final_tick: int | None
    channels: tuple[ChannelImportResult, ...]
    total_rows_read: int
    total_rows_written: int
    total_rows_skipped: int
    status: str
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": self.database_path,
            "run_id": self.run_id,
            "rule_id": self.rule_id,
            "final_tick": self.final_tick,
            "channels": [asdict(item) for item in self.channels],
            "total_rows_read": self.total_rows_read,
            "total_rows_written": self.total_rows_written,
            "total_rows_skipped": self.total_rows_skipped,
            "status": self.status,
            "dry_run": self.dry_run,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )


class CsvImportValidator(Protocol):
    def normalize(
        self,
        channel: str,
        row: Mapping[str, Any],
        *,
        row_index: int,
    ) -> dict[str, Any]: ...


class CsvImportSource(Protocol):
    def resolve_path(self, value: str | None) -> str | None: ...

    def require_files(self, paths: Iterable[str]) -> None: ...

    def infer_run_identity(self, paths: Iterable[str]) -> dict[str, Any]: ...

    def scan(
        self,
        path: str,
        channel: str,
    ) -> tuple[int, int | None, int | None]: ...

    def iter_rows(
        self,
        path: str,
        channel: str,
    ) -> Iterator[dict[str, Any]]: ...


class SqliteImportSink(Protocol):
    def write(self, channel: str, row: Mapping[str, Any]) -> bool: ...

    def finalize(
        self,
        *,
        status: str,
        final_tick: int | None,
        metadata_update: Mapping[str, Any],
    ) -> None: ...

    def abort(self) -> None: ...

    def close(self) -> None: ...


class SqliteImportSinkFactory(Protocol):
    def prepare_existing_run(
        self,
        *,
        database_path: str,
        run_id: str,
        policy: str,
    ) -> None: ...

    def open_sink(self, **options: Any) -> SqliteImportSink: ...

    def remove_run_quietly(
        self,
        *,
        database_path: str,
        run_id: str,
    ) -> None: ...


class ImportAuditHook(Protocol):
    def completed(self, report: CSVImportReport) -> None: ...


class NullImportAuditHook:
    """Explicit DL7 boundary: storage-parity audit remains a later slice."""

    def completed(self, report: CSVImportReport) -> None:
        del report


__all__ = [
    "CHANNELS",
    "CSVImportError",
    "CSVImportReport",
    "ChannelImportResult",
    "CsvImportSource",
    "CsvImportValidator",
    "ImportAuditHook",
    "NullImportAuditHook",
    "SqliteImportSink",
    "SqliteImportSinkFactory",
]
