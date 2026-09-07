"""Validated persistent cache for the OL2 world catalog."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Protocol

from Analyzer_next.execution.observer.shell2.config1.model import WorldIntegrity, WorldRecord


CACHE_SCHEMA = "archon.ol2.world-catalog-cache.v3"


class WorldCatalogPort(Protocol):
    def load_worlds(self) -> tuple[WorldRecord, ...]: ...


@dataclass(frozen=True, slots=True)
class CatalogCacheStatus:
    hit: bool
    reason: str
    world_count: int
    elapsed_seconds: float
    cache_path: str


class ValidatedWorldCatalogCache:
    """Serve immutable WorldRecords from cache only while source probes match.

    Validation deliberately uses bounded directory scans and cached source-file
    stat checks.  It never recursively walks Atlas or observation_logs on a
    warm start.
    """

    def __init__(
        self,
        backend: WorldCatalogPort,
        *,
        project_root: Path,
        world_atlas_dir: Path,
        observation_logs_dir: Path,
        mutation_root: Path,
        cache_path: Path,
    ) -> None:
        self.backend = backend
        self.project_root = Path(project_root).expanduser().resolve()
        self.world_atlas_dir = Path(world_atlas_dir).expanduser().resolve()
        self.observation_logs_dir = Path(observation_logs_dir).expanduser().resolve()
        self.mutation_root = Path(mutation_root).expanduser().resolve()
        self.cache_path = Path(cache_path).expanduser().resolve()
        self._status = CatalogCacheStatus(False, "not-loaded", 0, 0.0, str(self.cache_path))

    @property
    def status(self) -> CatalogCacheStatus:
        return self._status

    def load_worlds(self) -> tuple[WorldRecord, ...]:
        started = time.perf_counter()
        payload, reason = self._read_valid_cache()
        if payload is not None:
            try:
                worlds = self._decode_worlds(payload.get("worlds"))
            except (TypeError, ValueError, KeyError):
                payload = None
                reason = "cache-worlds-invalid"
            else:
                self._status = CatalogCacheStatus(
                    True,
                    "cache-hit",
                    len(worlds),
                    time.perf_counter() - started,
                    str(self.cache_path),
                )
                return worlds
        return self._rebuild(started=started, reason=reason)

    def refresh_worlds(self) -> tuple[WorldRecord, ...]:
        return self._rebuild(started=time.perf_counter(), reason="explicit-refresh")

    def invalidate(self) -> None:
        try:
            self.cache_path.unlink()
        except FileNotFoundError:
            pass

    def _rebuild(self, *, started: float, reason: str) -> tuple[WorldRecord, ...]:
        worlds = tuple(self.backend.load_worlds())
        write_reason = reason
        try:
            self._write_cache(worlds)
        except OSError as exc:
            write_reason = f"{reason};cache-write-failed:{type(exc).__name__}"
        self._status = CatalogCacheStatus(
            False,
            write_reason,
            len(worlds),
            time.perf_counter() - started,
            str(self.cache_path),
        )
        return worlds

    def _read_valid_cache(self) -> tuple[dict[str, Any] | None, str]:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None, "cache-missing"
        except (OSError, json.JSONDecodeError):
            return None, "cache-unreadable"
        if not isinstance(payload, dict) or payload.get("schema") != CACHE_SCHEMA:
            return None, "cache-schema-mismatch"
        if payload.get("project_root") != str(self.project_root):
            return None, "project-root-changed"
        expected = payload.get("source_signature")
        if not isinstance(expected, dict):
            return None, "cache-signature-missing"
        current = self._source_signature()
        if expected != current:
            return None, "source-signature-changed"
        source_files = payload.get("source_files")
        if not isinstance(source_files, dict) or not self._source_files_match(source_files):
            return None, "source-file-changed"
        return payload, "cache-hit"

    def _write_cache(self, worlds: tuple[WorldRecord, ...]) -> None:
        payload = {
            "schema": CACHE_SCHEMA,
            "project_root": str(self.project_root),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_signature": self._source_signature(),
            "source_files": self._source_file_signature(worlds),
            "worlds": [self._encode_world(world) for world in worlds],
        }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.cache_path.with_name(self.cache_path.name + f".tmp-{os.getpid()}")
        temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.replace(temp, self.cache_path)

    @staticmethod
    def _fingerprint(path: Path) -> dict[str, int | bool]:
        try:
            stat = path.stat()
        except OSError:
            return {"exists": False, "mtime_ns": 0, "size": 0}
        return {"exists": True, "mtime_ns": int(stat.st_mtime_ns), "size": int(stat.st_size)}

    @staticmethod
    def _immediate_directories(path: Path) -> list[dict[str, int | str]]:
        rows: list[dict[str, int | str]] = []
        try:
            with os.scandir(path) as iterator:
                for entry in iterator:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    rows.append({"name": entry.name, "mtime_ns": int(stat.st_mtime_ns)})
        except OSError:
            return []
        rows.sort(key=lambda row: str(row["name"]))
        return rows

    @staticmethod
    def _observation_file_summary(path: Path) -> dict[str, int]:
        """Bounded signature for flat legacy/campaign observation evidence."""
        count = 0
        max_mtime_ns = 0
        total_size = 0
        try:
            with os.scandir(path) as iterator:
                for entry in iterator:
                    if not entry.name.startswith("rule_") or not entry.name.endswith(
                        ("_samples.csv", "_passport.json")
                    ):
                        continue
                    try:
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    count += 1
                    max_mtime_ns = max(max_mtime_ns, int(stat.st_mtime_ns))
                    total_size += int(stat.st_size)
        except OSError:
            pass
        return {
            "count": count,
            "max_mtime_ns": max_mtime_ns,
            "total_size": total_size,
        }


    @staticmethod
    def _mutation_tree_signature(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            with os.scandir(path) as rules:
                for rule in rules:
                    try:
                        if not rule.is_dir(follow_symlinks=False):
                            continue
                        rule_stat = rule.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    children: list[dict[str, int | str]] = []
                    try:
                        with os.scandir(rule.path) as mutations:
                            for mutation in mutations:
                                try:
                                    if not mutation.is_dir(follow_symlinks=False) or not mutation.name.startswith("MUT-"):
                                        continue
                                    stat = mutation.stat(follow_symlinks=False)
                                except OSError:
                                    continue
                                children.append({"name": mutation.name, "mtime_ns": int(stat.st_mtime_ns)})
                    except OSError:
                        pass
                    children.sort(key=lambda row: str(row["name"]))
                    rows.append({
                        "name": rule.name,
                        "mtime_ns": int(rule_stat.st_mtime_ns),
                        "mutations": children,
                    })
        except OSError:
            return []
        rows.sort(key=lambda row: str(row["name"]))
        return rows

    def _source_signature(self) -> dict[str, Any]:
        telemetry = self.observation_logs_dir / "telemetry.sqlite"
        return {
            "atlas_index": self._fingerprint(self.world_atlas_dir / "atlas_index.json"),
            "atlas_root": self._fingerprint(self.world_atlas_dir),
            "atlas_classes": self._immediate_directories(self.world_atlas_dir),
            "observation_root": self._fingerprint(self.observation_logs_dir),
            "observation_runs": self._immediate_directories(self.observation_logs_dir),
            "observation_files": self._observation_file_summary(self.observation_logs_dir),
            "telemetry": self._fingerprint(telemetry),
            "telemetry_wal": self._fingerprint(telemetry.with_name(telemetry.name + "-wal")),
            "mutation_root": self._fingerprint(self.mutation_root),
            "mutation_tree": self._mutation_tree_signature(self.mutation_root),
        }

    def _source_file_signature(self, worlds: tuple[WorldRecord, ...]) -> dict[str, dict[str, int | bool]]:
        result: dict[str, dict[str, int | bool]] = {}
        for world in worlds:
            if world.source_path:
                path = Path(world.source_path).expanduser().resolve()
                result[str(path)] = self._fingerprint(path)
        return dict(sorted(result.items()))

    def _source_files_match(self, expected: dict[str, Any]) -> bool:
        for raw_path, fingerprint in expected.items():
            if not isinstance(raw_path, str) or not isinstance(fingerprint, dict):
                return False
            if self._fingerprint(Path(raw_path)) != fingerprint:
                return False
        return True

    @staticmethod
    def _encode_world(world: WorldRecord) -> dict[str, Any]:
        return {
            "rule_id": world.rule_id,
            "world_class": world.world_class,
            "score": world.score,
            "genome_hash": world.genome_hash,
            "observed": world.observed,
            "mutation_runs": world.mutation_runs,
            "last_run": world.last_run,
            "source_path": world.source_path,
            "integrity": world.integrity.value,
        }

    @staticmethod
    def _decode_worlds(rows: Any) -> tuple[WorldRecord, ...]:
        if not isinstance(rows, list):
            raise TypeError("world cache rows must be a list")
        worlds: list[WorldRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("world cache row must be an object")
            worlds.append(
                WorldRecord(
                    rule_id=int(row["rule_id"]),
                    world_class=str(row.get("world_class") or "Unclassified"),
                    score=(float(row["score"]) if row.get("score") is not None else None),
                    genome_hash=(str(row["genome_hash"]) if row.get("genome_hash") else None),
                    observed=bool(row.get("observed")),
                    mutation_runs=int(row.get("mutation_runs") or 0),
                    last_run=str(row.get("last_run") or "-"),
                    source_path=(str(row["source_path"]) if row.get("source_path") else None),
                    integrity=WorldIntegrity(str(row["integrity"])),
                )
            )
        worlds.sort(key=lambda world: world.rule_id)
        return tuple(worlds)


__all__ = ["CACHE_SCHEMA", "CatalogCacheStatus", "ValidatedWorldCatalogCache"]
