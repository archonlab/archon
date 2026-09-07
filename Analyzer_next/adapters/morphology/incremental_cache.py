#!/usr/bin/env python3
"""Shared incremental CSV cache for ARCHON morphology analyzers.

The first morphology stage parses each source CSV and stores its raw rows in a
pickle cache. Later stages reuse those rows instead of reopening and reparsing
all CSV files. Cache entries are invalidated by file size, nanosecond mtime,
resolved path, and cache schema version.
"""
from __future__ import annotations

import csv
import hashlib
import inspect
import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any, Iterable

CACHE_SCHEMA = 3
CACHE_DIR_NAME = ".morphology_cache"
MANIFEST_NAME = "manifest.json"
DEFAULT_MAX_ROWS = 15000

def _max_rows() -> int:
    """Maximum cached rows per CSV. 0 disables downsampling."""
    raw = os.environ.get("ARCHON_MORPH_MAX_ROWS", str(DEFAULT_MAX_ROWS))
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MAX_ROWS

def _even_downsample(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    """Preserve first/last rows and long-range structure with even sampling."""
    if limit <= 0 or len(rows) <= limit:
        return rows
    if limit == 1:
        return [rows[-1]]
    last = len(rows) - 1
    indices = [round(i * last / (limit - 1)) for i in range(limit)]
    return [rows[i] for i in indices]



def _results_root(path: Path) -> Path:
    path = path.resolve()
    start = path if path.is_dir() else path.parent
    for candidate in (start, *start.parents):
        if (candidate / "observation_logs").exists() or (candidate / "observer_profiles_v30.json").exists():
            return candidate
        if candidate.name == "Universe_Search" and candidate.parent.name == "Results":
            return candidate
    return start


def _cache_dir(path: Path) -> Path:
    root = _results_root(path)
    out = root / CACHE_DIR_NAME
    out.mkdir(parents=True, exist_ok=True)
    return out


def _fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "schema": CACHE_SCHEMA,
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _key(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_bytes(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def read_header(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            return [str(x).strip() for x in next(csv.reader(handle), [])]
    except (OSError, StopIteration, csv.Error):
        return []


def find_cached_csvs(
    results_dir: Path,
    *,
    required: Iterable[str] = ("tick",),
    required_any: Iterable[str] = ("morphology_class", "morphology_change_rate"),
    name_tokens: Iterable[str] = ("sample", "observer", "morph"),
) -> list[Path]:
    """Discover morphology CSVs with an incremental header manifest."""
    results_dir = results_dir.resolve()
    cache_dir = _cache_dir(results_dir)
    manifest_path = cache_dir / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = {"schema": CACHE_SCHEMA, "files": {}}
    if manifest.get("schema") != CACHE_SCHEMA or not isinstance(manifest.get("files"), dict):
        manifest = {"schema": CACHE_SCHEMA, "files": {}}

    required_set = set(required)
    required_any_set = set(required_any)
    tokens = tuple(x.lower() for x in name_tokens)
    found: list[Path] = []
    live: set[str] = set()
    changed = False

    for path in results_dir.rglob("*.csv"):
        low = path.name.lower()
        if tokens and not any(token in low for token in tokens):
            continue
        resolved = str(path.resolve())
        live.add(resolved)
        try:
            fp = _fingerprint(path)
        except OSError:
            continue
        old = manifest["files"].get(resolved, {})
        if any(old.get(k) != fp[k] for k in ("schema", "size", "mtime_ns")):
            header = read_header(path)
            manifest["files"][resolved] = {**fp, "header": header}
            changed = True
        else:
            header = old.get("header", [])
        fields = set(header)
        if required_set.issubset(fields) and (not required_any_set or bool(fields & required_any_set)):
            found.append(path.resolve())

    stale = [key for key in manifest["files"] if key not in live]
    for key in stale:
        manifest["files"].pop(key, None)
        changed = True

    if changed or not manifest_path.exists():
        _atomic_write_json(manifest_path, manifest)
    return sorted(set(found))


def load_cached_rows(path: Path) -> list[dict[str, str]]:
    """Return cached DictReader rows without duplicating the cache in memory.

    Cache files contain a bounded, evenly sampled representation. This keeps
    long observations useful while preventing a single accidental ultra-dense
    CSV from freezing the desktop.
    """
    path = path.resolve()
    cache_dir = _cache_dir(path)
    cache_path = cache_dir / f"{_key(path)}.pickle"
    fingerprint = _fingerprint(path)
    limit = _max_rows()

    if cache_path.exists():
        try:
            with cache_path.open("rb") as handle:
                payload = pickle.load(handle)
            if (
                payload.get("fingerprint") == fingerprint
                and payload.get("max_rows") == limit
                and isinstance(payload.get("rows"), list)
            ):
                return payload["rows"]
        except Exception:
            pass

    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        for row in csv.DictReader(handle):
            if row and "tick" in row:
                rows.append(dict(row))

    original_rows = len(rows)
    rows = _even_downsample(rows, limit)
    payload = {
        "fingerprint": fingerprint,
        "max_rows": limit,
        "original_rows": original_rows,
        "cached_rows": len(rows),
        "rows": rows,
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=cache_path.name + ".", dir=cache_path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, cache_path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
    return rows


def _producer_fingerprint(producer: Any) -> dict[str, Any]:
    """Fingerprint the analysis callable, not unrelated code in its module."""
    module = inspect.getmodule(producer)
    module_file = getattr(module, "__file__", None)
    try:
        source = inspect.getsource(producer).encode("utf-8")
        callable_sha256 = hashlib.sha256(source).hexdigest()
    except (OSError, TypeError):
        callable_sha256 = None
    return {
        "module": getattr(module, "__name__", ""),
        "file": str(Path(module_file).resolve()) if module_file else None,
        "callable": getattr(producer, "__qualname__", getattr(producer, "__name__", "")),
        "callable_sha256": callable_sha256,
    }


def _stage2f_compatible_identity(
    cached: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    """Allow a one-time import from Stage 2F's module-mtime identity."""
    old_producer = cached.get("producer")
    new_producer = current.get("producer")
    if not isinstance(old_producer, dict) or not isinstance(new_producer, dict):
        return False
    if "callable_sha256" in old_producer:
        return False
    if old_producer.get("file") != new_producer.get("file"):
        return False
    stable_keys = (
        "schema",
        "source",
        "namespace",
        "analysis_version",
        "max_rows",
    )
    return all(cached.get(key) == current.get(key) for key in stable_keys)


def load_cached_analysis(
    path: Path,
    *,
    namespace: str,
    producer: Any,
    analysis_version: int = 1,
) -> tuple[Any, bool]:
    """Load one derived per-CSV result or compute and cache it.

    The entry is valid only while the source CSV, cache schema, analysis
    version, and owning analyzer module are unchanged.  The bool return value
    is True for a cache hit and False for a fresh computation.
    """
    path = path.resolve()
    safe_namespace = "".join(
        ch if ch.isalnum() or ch in "._-" else "_"
        for ch in str(namespace)
    ).strip("._") or "analysis"
    cache_dir = _cache_dir(path)
    cache_path = cache_dir / (
        f"analysis.{safe_namespace}.{_key(path)}.pickle"
    )
    identity = {
        "schema": CACHE_SCHEMA,
        "source": _fingerprint(path),
        "namespace": safe_namespace,
        "analysis_version": int(analysis_version),
        "producer": _producer_fingerprint(producer),
        "max_rows": _max_rows(),
    }

    if cache_path.exists():
        try:
            with cache_path.open("rb") as handle:
                payload = pickle.load(handle)
            if (
                isinstance(payload, dict)
                and (
                    payload.get("identity") == identity
                    or _stage2f_compatible_identity(payload.get("identity", {}), identity)
                )
                and "value" in payload
            ):
                if payload.get("identity") != identity:
                    payload["identity"] = identity
                    _atomic_write_bytes(
                        cache_path,
                        pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL),
                    )
                return payload["value"], True
        except Exception:
            pass

    value = producer(path)
    payload = {"identity": identity, "value": value}
    fd, tmp_name = tempfile.mkstemp(
        prefix=cache_path.name + ".",
        dir=cache_path.parent,
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, cache_path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
    return value, False


def _analysis_identity(
    path: Path,
    *,
    namespace: str,
    producer: Any,
    analysis_version: int,
) -> dict[str, Any]:
    return {
        "schema": CACHE_SCHEMA,
        "source": _fingerprint(path.resolve()),
        "namespace": namespace,
        "analysis_version": int(analysis_version),
        "producer": _producer_fingerprint(producer),
        "max_rows": _max_rows(),
    }


def load_incremental_collection(
    paths: Iterable[Path],
    *,
    namespace: str,
    producer: Any,
    analysis_version: int = 1,
) -> tuple[list[Any], dict[str, int]]:
    """Update and return a complete per-CSV analysis collection.

    Unlike opening one cache pickle for every historical run on every Analyzer
    invocation, this keeps a single stage collection.  Only new or changed
    sources call ``producer``.  On the first Stage 2G run, existing Stage 2F
    per-file cache entries are imported without recomputation.
    """
    resolved = sorted({Path(path).resolve() for path in paths}, key=str)
    safe_namespace = "".join(
        ch if ch.isalnum() or ch in "._-" else "_"
        for ch in str(namespace)
    ).strip("._") or "analysis"
    root = resolved[0] if resolved else Path.cwd()
    cache_dir = _cache_dir(root)
    collection_path = cache_dir / f"collection.{safe_namespace}.pickle"

    try:
        with collection_path.open("rb") as handle:
            payload = pickle.load(handle)
        if payload.get("schema") != CACHE_SCHEMA or not isinstance(payload.get("entries"), dict):
            raise ValueError("stale collection")
        entries = payload["entries"]
    except Exception:
        entries = {}

    live = {str(path) for path in resolved}
    stats = {"new": 0, "changed": 0, "removed": 0, "reused": 0}
    updated: dict[str, dict[str, Any]] = {}

    for path in resolved:
        key = str(path)
        identity = _analysis_identity(
            path,
            namespace=safe_namespace,
            producer=producer,
            analysis_version=analysis_version,
        )
        previous = entries.get(key)
        if isinstance(previous, dict) and previous.get("identity") == identity and "value" in previous:
            value = previous["value"]
            stats["reused"] += 1
        else:
            value, imported = load_cached_analysis(
                path,
                namespace=safe_namespace,
                producer=producer,
                analysis_version=analysis_version,
            )
            if previous is None:
                stats["new"] += 1
            else:
                stats["changed"] += 1
            # ``imported`` means Stage 2F had already computed the value.
            if imported:
                stats["reused"] += 1
                if previous is None:
                    stats["new"] -= 1
        updated[key] = {"identity": identity, "value": value}

    stats["removed"] = len(set(entries) - live)
    payload = {
        "schema": CACHE_SCHEMA,
        "namespace": safe_namespace,
        "entries": updated,
    }
    _atomic_write_bytes(
        collection_path,
        pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL),
    )
    return [updated[str(path)]["value"] for path in resolved], stats


def cache_stats(results_dir: Path) -> dict[str, int]:
    cache_dir = _cache_dir(results_dir)
    entries = list(cache_dir.glob("*.pickle"))
    analysis_entries = list(cache_dir.glob("analysis.*.pickle"))
    return {
        "entries": len(entries),
        "analysis_entries": len(analysis_entries),
        "bytes": sum(p.stat().st_size for p in entries if p.is_file()),
    }
