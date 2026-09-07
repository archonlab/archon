"""Small deterministic helpers shared by the mutation pipeline."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import RULE_RE

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_rule_id(value: Any) -> str | None:
    try:
        return f"{int(str(value)):05d}"
    except Exception:
        return None


def read_json(path: Path, default: Any = None) -> Any:
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def safe_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    number = safe_float(value)
    return int(number) if number is not None else None


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def rule_id_from_filename(path: Path) -> str | None:
    match = RULE_RE.search(path.name)
    return normalize_rule_id(match.group(1)) if match else None

