"""Streaming legacy-CSV source and exact row-normalization adapter."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import Any, Iterable, Iterator, Mapping

from Analyzer_next.core.telemetry.csv_import import CSVImportError


class LegacyCsvImportValidator:
    """Preserve the canonical legacy CSV value and row semantics."""

    def normalize(
        self,
        channel: str,
        row: Mapping[str, Any],
        *,
        row_index: int,
    ) -> dict[str, Any]:
        normalized = {
            str(key): self.parse_value(value)
            for key, value in row.items()
            if key is not None
        }
        if "tick" not in normalized:
            raise CSVImportError(
                f"{channel} row {row_index} has no tick column"
            )
        try:
            tick = int(normalized["tick"])
        except (TypeError, ValueError) as exc:
            raise CSVImportError(
                f"{channel} row {row_index} has invalid tick: "
                f"{normalized['tick']!r}"
            ) from exc
        if tick < 0:
            raise CSVImportError(
                f"{channel} row {row_index} has negative tick"
            )
        normalized["tick"] = tick

        if channel == "event":
            event_type = normalized.get(
                "type",
                normalized.get("event_type"),
            )
            if event_type in (None, ""):
                raise CSVImportError(
                    f"event row {row_index} has no event type"
                )
        return normalized

    @staticmethod
    def parse_value(value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text == "":
            return None
        lowered = text.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered == "null":
            return None
        if (
            (text.startswith("{") and text.endswith("}"))
            or (text.startswith("[") and text.endswith("]"))
        ):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        try:
            if any(char in text for char in ".eE"):
                return float(text)
            return int(text)
        except ValueError:
            return text


class StreamingCsvImportSource:
    """Read each channel twice without retaining channel rows in memory."""

    def __init__(self, validator: LegacyCsvImportValidator | None = None) -> None:
        self.validator = validator or LegacyCsvImportValidator()

    @staticmethod
    def resolve_path(value: str | None) -> str | None:
        if value is None:
            return None
        return str(Path(value).expanduser().resolve())

    @staticmethod
    def require_files(paths: Iterable[str]) -> None:
        for value in paths:
            path = Path(value)
            if not path.exists() or not path.is_file():
                raise CSVImportError(f"CSV file does not exist: {path}")

    @staticmethod
    def infer_run_identity(paths: Iterable[str]) -> dict[str, Any]:
        names = [Path(path).name for path in paths]
        rule_ids = []
        timestamps = []
        for name in names:
            match = re.search(r"rule[_-]?(\d+)", name, re.I)
            if match:
                rule_ids.append(int(match.group(1)))
            match = re.search(r"(20\d{6}[_-]\d{6})", name)
            if match:
                timestamps.append(match.group(1).replace("-", "_"))

        rule_id = None
        if rule_ids:
            unique = sorted(set(rule_ids))
            if len(unique) > 1:
                raise CSVImportError(
                    f"CSV filenames refer to multiple rule IDs: {unique}"
                )
            rule_id = unique[0]

        timestamp = None
        if timestamps:
            unique = sorted(set(timestamps))
            if len(unique) > 1:
                raise CSVImportError(
                    f"CSV filenames refer to multiple runs: {unique}"
                )
            timestamp = unique[0]

        run_id = None
        if rule_id is not None and timestamp is not None:
            run_id = f"rule_{rule_id:05d}_{timestamp}"
        elif rule_id is not None:
            run_id = f"rule_{rule_id:05d}_legacy_import"
        return {"rule_id": rule_id, "timestamp": timestamp, "run_id": run_id}

    def iter_rows(self, path: str, channel: str) -> Iterator[dict[str, Any]]:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise CSVImportError(f"CSV has no header: {path}")
            for row_index, row in enumerate(reader):
                yield self.validator.normalize(
                    channel,
                    dict(row),
                    row_index=row_index,
                )

    def scan(
        self,
        path: str,
        channel: str,
    ) -> tuple[int, int | None, int | None]:
        count = 0
        first_tick: int | None = None
        last_tick: int | None = None
        for row in self.iter_rows(path, channel):
            tick = int(row["tick"])
            count += 1
            first_tick = tick if first_tick is None else min(first_tick, tick)
            last_tick = tick if last_tick is None else max(last_tick, tick)
        return count, first_tick, last_tick


__all__ = ["LegacyCsvImportValidator", "StreamingCsvImportSource"]
