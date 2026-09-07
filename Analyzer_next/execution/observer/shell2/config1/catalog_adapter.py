"""Read-only adapter from the native Atlas catalog to CONFIG1 world records."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from Analyzer_next.execution.observer.catalog import find_rule_file, load_rules, read_json

from .model import WorldIntegrity, WorldRecord


RuleLoader = Callable[[], list[dict[str, Any]]]
RuleResolver = Callable[[int], Path | None]
JsonReader = Callable[[Path, Any], Any]


class NativeWorldCatalog:
    """Resolve Atlas rows and fail closed when canonical rule identity is absent."""

    def __init__(
        self,
        *,
        loader: RuleLoader = load_rules,
        resolver: RuleResolver = find_rule_file,
        reader: JsonReader = read_json,
    ) -> None:
        self._loader = loader
        self._resolver = resolver
        self._reader = reader

    def load_worlds(self) -> tuple[WorldRecord, ...]:
        by_id: dict[int, WorldRecord] = {}
        for row in self._loader():
            try:
                rule_id = int(row["rule_id"])
            except (KeyError, TypeError, ValueError):
                continue
            source = self._resolve_source(rule_id, row)
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
            parents = row.get("parents")
            genome_hash = row.get("genome_hash")
            if not genome_hash and source is not None:
                name = source.parent.name
                genome_hash = name.rsplit("_", 1)[-1] if "_" in name else None
            by_id[rule_id] = WorldRecord(
                rule_id=rule_id,
                world_class=str(row.get("class") or "Unclassified"),
                score=float(score) if score is not None else None,
                genome_hash=str(genome_hash) if genome_hash else None,
                observed=bool(row.get("observed")),
                mutation_runs=max(0, int(row.get("mutation_runs") or 0)),
                last_run=str(row.get("last_run") or "-"),
                source_path=str(source) if source is not None else None,
                integrity=integrity,
            )
        return tuple(by_id[key] for key in sorted(by_id))

    def _resolve_source(self, rule_id: int, row: dict[str, Any]) -> Path | None:
        source = self._resolver(rule_id)
        if source is not None:
            return Path(source)
        folder = row.get("folder")
        if folder:
            candidate = Path(str(folder)) / "rule.json"
            if candidate.is_file():
                return candidate
        return None
