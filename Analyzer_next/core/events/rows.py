"""Normalize event telemetry rows without filesystem ownership."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from Analyzer_next.core.events.constants import NUMERIC_COLUMNS
from Analyzer_next.core.events.numeric import clamp01, safe_float, safe_int


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
    match = re.search(
        r"(?:^|[_/\-])rule[_\-]?(\d{1,6})(?:[_/\-]|$)",
        text,
        flags=re.I,
    )
    if match:
        return f"{int(match.group(1)):05d}"
    matches = re.findall(r"(\d{3,6})", path.stem)
    if matches:
        return f"{int(matches[0]):05d}"
    return path.stem


def local_mci(row: dict[str, Any]) -> float:
    edge = safe_float(row.get("_morphology_edge_complexity"), 0.0)
    branching = safe_float(row.get("_morphology_branching"), 0.0)
    change = safe_float(row.get("_morphology_change_rate"), 0.0)
    filament = safe_float(row.get("_morphology_filament_score"), 0.0)
    lattice = safe_float(row.get("_morphology_lattice_score"), 0.0)
    symmetry = safe_float(row.get("_morphology_symmetry"), 0.0)
    aspect = safe_float(row.get("_morphology_aspect"), 1.0)
    edge_n = min(1.0, edge / 40.0)
    branching_n = min(1.0, branching / 2.0)
    change_n = min(1.0, change / 2.0)
    form_n = max(filament, lattice)
    aspect_n = min(1.0, abs(aspect - 1.0) / 5.0)
    return clamp01(
        0.30 * edge_n
        + 0.24 * branching_n
        + 0.16 * change_n
        + 0.14 * form_n
        + 0.10 * symmetry
        + 0.06 * aspect_n
    )


def normalize_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        row = dict(raw)
        row["_tick"] = safe_int(row.get("tick"), 0)
        row["_class"] = clean_class(row.get("morphology_class"))
        for column in NUMERIC_COLUMNS:
            if column in row:
                row[f"_{column}"] = safe_float(row.get(column), 0.0)
        row["_mci"] = local_mci(row)
        rows.append(row)
    rows.sort(key=lambda item: item.get("_tick", 0))
    return rows

