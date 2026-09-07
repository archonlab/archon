"""Normalize raw telemetry rows without owning filesystem access."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from Analyzer_next.core.morphology.constants import NUMERIC_COLUMNS
from Analyzer_next.core.morphology.numeric import safe_float, safe_int


def clean_class(value: Any) -> str:
    text = str(value or "none").strip()
    return text.upper() if text else "NONE"


def infer_rule_id(path: Path, rows: list[dict[str, Any]]) -> str:
    for key in ("rule", "rule_id", "rule_number"):
        for row in rows[:20]:
            value = row.get(key)
            if value not in (None, ""):
                match = re.search(r"(\d+)", str(value))
                if match:
                    return f"{int(match.group(1)):05d}"

    text = "_".join(path.parts)
    match = re.search(r"(?:^|[_/\-])rule[_\-]?(\d{1,6})(?:[_/\-]|$)", text, flags=re.I)
    if match:
        return f"{int(match.group(1)):05d}"

    matches = re.findall(r"(\d{3,6})", path.stem)
    if matches:
        return f"{int(matches[0]):05d}"
    return path.stem


def normalize_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        row: dict[str, Any] = dict(raw)
        row["_tick"] = safe_int(row.get("tick"), 0)
        row["_class"] = clean_class(row.get("morphology_class"))
        for column in NUMERIC_COLUMNS:
            if column in row:
                row[f"_{column}"] = safe_float(row.get(column), 0.0)
        rows.append(row)
    rows.sort(key=lambda item: item.get("_tick", 0))
    return rows


def series(row_key: str, rows: list[dict[str, Any]]) -> list[float]:
    return [safe_float(row.get(row_key), 0.0) for row in rows]
