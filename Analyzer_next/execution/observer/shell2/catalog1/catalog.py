"""Cold-path world catalog for OL2-CATALOG1.

The legacy CONFIG1 catalog performs per-rule recursive resolution and per-rule
observation/mutation globbing.  This adapter preserves the resulting
WorldRecord semantics while indexing each filesystem area once.
"""
from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable

from Analyzer_next.execution.observer.shell2.config1.model import WorldIntegrity, WorldRecord


_RULE_DIR = re.compile(r"^rule_(\d{5})_")
_OBSERVATION_ARTIFACT = re.compile(
    r"^rule_(\d{5})_.+_(samples\.csv|passport\.json)$"
)
_MUTATION_RULE_DIR = re.compile(r"^rule_(\d{5})$")


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


class Catalog1WorldCatalog:
    """Resolve canonical worlds with bounded, single-pass directory scans."""

    def __init__(
        self,
        *,
        world_atlas_dir: Path,
        observation_logs_dir: Path,
        mutation_root: Path,
        reader: Callable[[Path, Any], Any] = _read_json,
    ) -> None:
        self.world_atlas_dir = Path(world_atlas_dir).expanduser().resolve()
        self.observation_logs_dir = Path(observation_logs_dir).expanduser().resolve()
        self.mutation_root = Path(mutation_root).expanduser().resolve()
        self._reader = reader

    def load_worlds(self) -> tuple[WorldRecord, ...]:
        rows = self._atlas_rows()
        sources = self._source_index()
        observations = self._observation_index()
        telemetry_observations = self._telemetry_observation_index()
        mutations = self._mutation_index()

        if not rows:
            rows = self._rows_from_sources(sources)

        by_id: dict[int, WorldRecord] = {}
        for row in rows:
            try:
                rule_id = int(row["rule_id"])
            except (KeyError, TypeError, ValueError):
                continue

            source = sources.get(rule_id)
            if source is None:
                folder = row.get("folder")
                if folder:
                    candidate = Path(str(folder)).expanduser()
                    if candidate.name != "rule.json":
                        candidate = candidate / "rule.json"
                    try:
                        candidate = candidate.resolve()
                    except OSError:
                        pass
                    if candidate.is_file():
                        source = candidate

            integrity = WorldIntegrity.SOURCE_MISSING
            if source is not None and source.is_file():
                payload = self._reader(source, None)
                if not isinstance(payload, dict):
                    integrity = WorldIntegrity.PAYLOAD_INVALID
                else:
                    try:
                        payload_rule_id = int(payload.get("rule_id"))
                    except (TypeError, ValueError):
                        integrity = WorldIntegrity.PAYLOAD_INVALID
                    else:
                        integrity = (
                            WorldIntegrity.VERIFIED
                            if payload_rule_id == rule_id
                            else WorldIntegrity.IDENTITY_MISMATCH
                        )

            score = row.get("score")
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                score = None
            genome_hash = row.get("genome_hash")
            if not genome_hash and source is not None:
                name = source.parent.name
                genome_hash = name.rsplit("_", 1)[-1] if "_" in name else None

            observation_dirs = observations.get(rule_id, ())
            mutation_dirs = mutations.get(rule_id, ())
            persisted_run = telemetry_observations.get(rule_id)
            latest_directory = max(
                (_mtime(path) for path in observation_dirs),
                default=0.0,
            )
            directory_time = (
                datetime.fromtimestamp(latest_directory).strftime("%Y-%m-%d %H:%M")
                if latest_directory else None
            )
            # The canonical run ledger is authoritative when available.  The
            # directory timestamp is compatibility-only for pre-SQLite runs.
            last_run = persisted_run[0] if persisted_run else (directory_time or "-")

            by_id[rule_id] = WorldRecord(
                rule_id=rule_id,
                world_class=str(row.get("class") or "Unclassified"),
                score=float(score) if score is not None else None,
                genome_hash=str(genome_hash) if genome_hash else None,
                observed=bool(observation_dirs or persisted_run),
                mutation_runs=len(mutation_dirs),
                last_run=last_run,
                source_path=str(source) if source is not None else None,
                integrity=integrity,
            )
        return tuple(by_id[key] for key in sorted(by_id))

    def _telemetry_observation_index(self) -> dict[int, tuple[str, str]]:
        """Index valid per-rule Observer evidence from the canonical run ledger.

        A run counts only after durable execution evidence exists: at least one
        sample or a positive final tick.  Failed registrations and zero-work
        queue members therefore remain unobserved.  Campaigns need no special
        UI bookkeeping because their physical member runs are expanded by the
        telemetry writer into one row per canonical rule identity.
        """
        database = self.observation_logs_dir / "telemetry.sqlite"
        if not database.is_file():
            return {}
        try:
            connection = sqlite3.connect(
                f"file:{database}?mode=ro", uri=True, timeout=0.2
            )
            connection.row_factory = sqlite3.Row
        except sqlite3.Error:
            return {}
        try:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "runs" not in tables:
                return {}
            run_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(runs)")
            }
            if not {"run_id", "rule_id", "status"}.issubset(run_columns):
                return {}
            sample_capable = "samples" in tables and {
                "run_id", "tick"
            }.issubset({
                str(row[1])
                for row in connection.execute("PRAGMA table_info(samples)")
            })
            time_columns = [
                name
                for name in (
                    "finished_at_utc", "started_at_utc", "updated_at_utc", "created_at_utc"
                )
                if name in run_columns
            ]
            time_sql = (
                "COALESCE(" + ", ".join(f"r.{name}" for name in time_columns) + ", '')"
                if time_columns else "''"
            )
            final_tick_sql = "COALESCE(r.final_tick, 0)" if "final_tick" in run_columns else "0"
            evidence_sql = (
                f"(EXISTS (SELECT 1 FROM samples s WHERE s.run_id = r.run_id) OR {final_tick_sql} > 0)"
                if sample_capable else f"({final_tick_sql} > 0)"
            )
            rows = connection.execute(
                f"""
                SELECT r.run_id, r.rule_id, {time_sql} AS run_time
                FROM runs r
                WHERE lower(trim(r.status)) IN ('running', 'completed', 'stopped', 'imported')
                  AND r.rule_id IS NOT NULL
                  AND {evidence_sql}
                """
            )
            result: dict[int, tuple[str, str]] = {}
            for row in rows:
                try:
                    rule_id = int(row["rule_id"])
                except (TypeError, ValueError):
                    continue
                raw_time = str(row["run_time"] or "").strip()
                display_time = raw_time.replace("T", " ")[:16] if raw_time else "-"
                candidate = (display_time, str(row["run_id"] or ""))
                if rule_id not in result or candidate[0] > result[rule_id][0]:
                    result[rule_id] = candidate
            return result
        except sqlite3.Error:
            # Catalog loading stays fail-closed and read-only on partial/locked
            # or historical schemas; directory evidence remains available.
            return {}
        finally:
            connection.close()

    def _atlas_rows(self) -> list[dict[str, Any]]:
        index = self._reader(self.world_atlas_dir / "atlas_index.json", [])
        if not isinstance(index, list):
            return []
        rows: list[dict[str, Any]] = []
        for entry in index:
            if not isinstance(entry, dict):
                continue
            try:
                rule_id = int(entry.get("rule_id"))
            except (TypeError, ValueError):
                continue
            metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
            rows.append(
                {
                    "rule_id": rule_id,
                    "score": entry.get("score", metrics.get("score")),
                    "class": entry.get("class", metrics.get("class", metrics.get("world_class", ""))),
                    "folder": entry.get("folder"),
                    "genome_hash": entry.get("key") or entry.get("genome_hash"),
                }
            )
        # Match the legacy catalog's last-row-wins behavior for duplicate IDs.
        deduped: dict[int, dict[str, Any]] = {}
        for row in rows:
            deduped[int(row["rule_id"])] = row
        return [deduped[key] for key in sorted(deduped)]

    def _source_index(self) -> dict[int, Path]:
        result: dict[int, Path] = {}
        if not self.world_atlas_dir.exists():
            return result
        try:
            paths = sorted(self.world_atlas_dir.rglob("rule.json"))
        except OSError:
            return result
        for path in paths:
            match = _RULE_DIR.match(path.parent.name)
            rule_id: int | None = int(match.group(1)) if match else None
            if rule_id is None:
                payload = self._reader(path, {})
                if isinstance(payload, dict):
                    try:
                        rule_id = int(payload.get("rule_id"))
                    except (TypeError, ValueError):
                        rule_id = None
            if rule_id is not None:
                result.setdefault(rule_id, path.resolve())
        return result

    def _rows_from_sources(self, sources: dict[int, Path]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for rule_id, path in sorted(sources.items()):
            payload = self._reader(path, {})
            rows.append(
                {
                    "rule_id": rule_id,
                    "score": None,
                    "class": path.parent.parent.name,
                    "folder": str(path.parent),
                    "genome_hash": path.parent.name.rsplit("_", 1)[-1] if "_" in path.parent.name else None,
                    "parent_a": payload.get("parent_a") if isinstance(payload, dict) else None,
                    "parent_b": payload.get("parent_b") if isinstance(payload, dict) else None,
                }
            )
        return rows

    def _observation_index(self) -> dict[int, tuple[Path, ...]]:
        grouped: dict[int, list[Path]] = {}
        try:
            children = tuple(self.observation_logs_dir.iterdir())
        except OSError:
            return {}
        for path in children:
            match = _RULE_DIR.match(path.name)
            if path.is_dir():
                if match:
                    grouped.setdefault(int(match.group(1)), []).append(path)
                continue
            artifact = _OBSERVATION_ARTIFACT.match(path.name)
            if artifact and self._has_flat_observation_evidence(
                path,
                artifact.group(2),
                int(artifact.group(1)),
            ):
                grouped.setdefault(int(artifact.group(1)), []).append(path)
        return {
            key: tuple(sorted(values, key=_mtime, reverse=True))
            for key, values in grouped.items()
        }

    def _has_flat_observation_evidence(
        self,
        path: Path,
        artifact_kind: str,
        filename_rule_id: int,
    ) -> bool:
        """Accept durable legacy/campaign files without counting empty starts."""
        if artifact_kind == "samples.csv":
            try:
                with path.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames or "tick" not in reader.fieldnames:
                        return False
                    for row_index, row in enumerate(reader):
                        if row_index >= 32:
                            break
                        try:
                            if int(row.get("tick", "")) >= 0:
                                return True
                        except (TypeError, ValueError):
                            continue
            except (OSError, csv.Error, UnicodeError):
                return False
            return False

        payload = self._reader(path, None)
        if not isinstance(payload, dict):
            return False
        try:
            payload_rule_id = int(payload.get("rule_id", filename_rule_id))
        except (TypeError, ValueError):
            return False
        if payload_rule_id != filename_rule_id:
            return False
        for key in ("final_tick_observed", "final_tick", "last_tick", "tick"):
            try:
                if int(payload.get(key, 0)) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _mutation_index(self) -> dict[int, tuple[Path, ...]]:
        grouped: dict[int, tuple[Path, ...]] = {}
        try:
            rule_dirs = tuple(self.mutation_root.iterdir())
        except OSError:
            return grouped
        for rule_dir in rule_dirs:
            if not rule_dir.is_dir():
                continue
            match = _MUTATION_RULE_DIR.match(rule_dir.name)
            if not match:
                continue
            try:
                mutation_dirs = tuple(
                    child
                    for child in rule_dir.iterdir()
                    if child.is_dir() and child.name.startswith("MUT-")
                )
            except OSError:
                mutation_dirs = ()
            grouped[int(match.group(1))] = tuple(sorted(mutation_dirs, key=_mtime, reverse=True))
        return grouped


__all__ = ["Catalog1WorldCatalog"]
