"""Streaming raw-CSV source for storage parity validation."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterator, Mapping


class StreamingParityCsvSource:
    @staticmethod
    def resolve_path(value: str | None) -> str | None:
        if value is None:
            return None
        return str(Path(value).expanduser().resolve())

    @staticmethod
    def exists(path: str) -> bool:
        return Path(path).exists()

    @staticmethod
    def iter_rows(path: str) -> Iterator[Mapping[str, Any]]:
        with Path(path).open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            yield from csv.DictReader(handle)


__all__ = ["StreamingParityCsvSource"]
