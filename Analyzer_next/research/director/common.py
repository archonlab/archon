"""Pure JSON, numeric, hashing, and time helpers."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

def clamp(x: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        if x is None:
            return lo
        v = float(x)
        if math.isnan(v):
            return lo
        return max(lo, min(hi, v))
    except Exception:
        return lo

def safe_num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v):
            return default
        return v
    except Exception:
        return default

def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def read_text(path: Path, default: str = "") -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return default

def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def first_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}

def iter_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, list):
        for x in value:
            if isinstance(x, dict):
                yield x
    elif isinstance(value, dict):
        # Common possible containers.
        for key in ("records", "profiles", "principles", "items", "claims", "entries"):
            if isinstance(value.get(key), list):
                for x in value[key]:
                    if isinstance(x, dict):
                        yield x
                return
        # If it is a dict of dicts, emit values with id carried over.
        for k, x in value.items():
            if isinstance(x, dict):
                y = dict(x)
                y.setdefault("id", k)
                yield y

def count_unique_rules(records: Iterable[Dict[str, Any]]) -> int:
    rules = set()
    for r in records:
        rule = r.get("rule") or r.get("rule_id") or r.get("id") or r.get("name")
        if rule is not None:
            rules.add(str(rule))
    return len(rules)

def canonical_json_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 hash for JSON-compatible data."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def atomic_write_json(path: Path, payload: Any) -> None:
    """Atomically write JSON using fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
