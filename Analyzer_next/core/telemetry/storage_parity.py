"""Storage-independent CSV↔SQLite parity models, ports, and normalization."""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
import json
import math
from typing import Any, Iterator, Mapping, Protocol


CHANNELS = ("sample", "event", "chronicle", "pressure")

CHANNEL_COUNT_COLUMNS = {
    "sample": "samples_count",
    "event": "events_count",
    "chronicle": "chronicle_count",
    "pressure": "pressure_count",
}

UNIQUE_TICK_CHANNELS = {"sample", "pressure"}

PROMOTED_COLUMNS = {
    "sample": (
        "alive", "life_state", "life_score", "life_confidence",
        "structural_state", "objects", "largest", "total_living_mass",
        "ecosystem_health", "stability_index", "ecosystem_phase",
        "morphology_class", "emergence_score", "validation_quality",
    ),
    "event": ("event_type", "detail"),
    "chronicle": (
        "severity", "event", "family", "colony", "phase", "pressure",
        "risk", "cause", "details",
    ),
    "pressure": (
        "phase", "stress", "adapt", "pressure", "recovery", "risk",
        "cause", "ecosystem_phase", "objects", "mass", "largest",
        "families",
    ),
}


class StorageParityError(RuntimeError):
    """Raised when parity validation cannot be performed."""


@dataclass(frozen=True, slots=True)
class FieldMismatch:
    channel: str
    row_index: int
    tick: int | None
    field: str
    csv_value: Any
    sqlite_value: Any


@dataclass(frozen=True, slots=True)
class ChannelParity:
    channel: str
    csv_path: str | None
    csv_count: int
    sqlite_count: int
    count_match: bool
    tick_match: bool
    duplicate_ticks_csv: tuple[int, ...]
    duplicate_ticks_sqlite: tuple[int, ...]
    field_mismatches: tuple[FieldMismatch, ...]
    promoted_column_mismatches: tuple[FieldMismatch, ...]
    passed: bool


@dataclass(frozen=True, slots=True)
class StorageParityReport:
    run_id: str
    database_path: str
    channels: tuple[ChannelParity, ...]
    run_counter_mismatches: Mapping[str, tuple[int, int]]
    passed: bool
    summary: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "database_path": self.database_path,
            "passed": self.passed,
            "run_counter_mismatches": {
                key: [value[0], value[1]]
                for key, value in self.run_counter_mismatches.items()
            },
            "summary": dict(self.summary),
            "channels": [
                {
                    "channel": item.channel,
                    "csv_path": item.csv_path,
                    "csv_count": item.csv_count,
                    "sqlite_count": item.sqlite_count,
                    "count_match": item.count_match,
                    "tick_match": item.tick_match,
                    "duplicate_ticks_csv": list(item.duplicate_ticks_csv),
                    "duplicate_ticks_sqlite": list(item.duplicate_ticks_sqlite),
                    "field_mismatches": [
                        asdict(mismatch) for mismatch in item.field_mismatches
                    ],
                    "promoted_column_mismatches": [
                        asdict(mismatch)
                        for mismatch in item.promoted_column_mismatches
                    ],
                    "passed": item.passed,
                }
                for item in self.channels
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class ParitySqliteRow:
    columns: Mapping[str, Any]
    payload: Mapping[str, Any]


class ParityCsvSource(Protocol):
    def resolve_path(self, value: str | None) -> str | None: ...

    def exists(self, path: str) -> bool: ...

    def iter_rows(self, path: str) -> Iterator[Mapping[str, Any]]: ...


class ParitySqliteSource(Protocol):
    @property
    def database_path(self) -> str: ...

    def get_run(self, run_id: str) -> Mapping[str, Any]: ...

    def iter_channel(
        self,
        run_id: str,
        channel: str,
    ) -> Iterator[ParitySqliteRow]: ...

    def close(self) -> None: ...


class ParitySqliteSourceFactory(Protocol):
    def resolve_path(self, value: str) -> str: ...

    def open(self, database_path: str) -> ParitySqliteSource: ...


def normalize_promoted_value(
    *,
    channel: str,
    field_name: str,
    value: Any,
) -> Any:
    if value is None:
        return None
    if channel == "chronicle" and field_name in {"family", "colony"}:
        return str(value)
    if channel == "event" and field_name == "detail":
        if isinstance(value, Mapping):
            return normalize_value(value)
        if isinstance(value, (list, tuple)):
            return normalize_value(value)
        if isinstance(value, str):
            text = value.strip()
            if text == "":
                return None
            try:
                return normalize_value(json.loads(text))
            except json.JSONDecodeError:
                pass
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return text
            if isinstance(parsed, (Mapping, list, tuple)):
                return normalize_value(parsed)
    return value


def normalize_csv_value(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return normalize_value(value)
    text = value.strip()
    if text == "":
        return None
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered == "null":
        return None
    if (
        (text.startswith("{") and text.endswith("}"))
        or (text.startswith("[") and text.endswith("]"))
    ):
        try:
            return normalize_value(json.loads(text))
        except json.JSONDecodeError:
            pass
    try:
        if any(character in text for character in ".eE"):
            return float(text)
        return int(text)
    except ValueError:
        return text


def normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, Mapping):
        return {
            str(key): normalize_value(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [normalize_value(item) for item in value]
    return str(value)


def values_equal(left: Any, right: Any, *, tolerance: float) -> bool:
    if left is None and right is None:
        return True
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(
            float(left),
            float(right),
            rel_tol=tolerance,
            abs_tol=tolerance,
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            values_equal(a, b, tolerance=tolerance)
            for a, b in zip(left, right)
        )
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(
            values_equal(left[key], right[key], tolerance=tolerance)
            for key in left
        )
    return left == right


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def track_duplicate(
    tick: int | None,
    seen: set[int],
    duplicates: set[int],
) -> None:
    if tick is None:
        return
    if tick in seen:
        duplicates.add(tick)
    else:
        seen.add(tick)


__all__ = [
    "CHANNELS",
    "CHANNEL_COUNT_COLUMNS",
    "PROMOTED_COLUMNS",
    "UNIQUE_TICK_CHANNELS",
    "ChannelParity",
    "FieldMismatch",
    "ParityCsvSource",
    "ParitySqliteRow",
    "ParitySqliteSource",
    "ParitySqliteSourceFactory",
    "StorageParityError",
    "StorageParityReport",
    "int_or_none",
    "normalize_csv_value",
    "normalize_promoted_value",
    "normalize_value",
    "track_duplicate",
    "values_equal",
]
