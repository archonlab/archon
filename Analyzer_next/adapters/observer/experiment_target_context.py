"""Read-only canonical target context lookup for registered experiments."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3


@dataclass(frozen=True, slots=True)
class ExperimentTargetContext:
    experiment_id: str
    condition_id: str | None
    rule_ids: tuple[int, ...]
    plan_id: str | None = None


class ExperimentTargetContextError(RuntimeError):
    pass


class ExperimentTargetContextReader:
    def __init__(self, database_path: str | Path, target_registry_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.target_registry_path = Path(target_registry_path).expanduser().resolve()

    def _metadata(self, experiment_id: str) -> dict:
        if not self.database_path.is_file():
            raise ExperimentTargetContextError(f"telemetry database missing: {self.database_path}")
        uri = f"file:{self.database_path.as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute(
                "SELECT metadata_json FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
        finally:
            con.close()
        if row is None:
            raise ExperimentTargetContextError(f"experiment is not registered: {experiment_id}")
        try:
            value = json.loads(row["metadata_json"] or "{}")
        except (TypeError, ValueError) as exc:
            raise ExperimentTargetContextError(f"invalid experiment metadata_json for {experiment_id}: {exc}") from exc
        return value if isinstance(value, dict) else {}

    def _registry_identity(self, experiment_id: str) -> tuple[str | None, tuple[int, ...], str | None]:
        if not self.target_registry_path.is_file():
            return None, (), None
        try:
            payload = json.loads(self.target_registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ExperimentTargetContextError(f"cannot read target resolution registry: {exc}") from exc
        rows = payload.get("resolutions", []) if isinstance(payload, dict) else []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            identities = row.get("identities")
            if not isinstance(identities, dict) or str(identities.get("experiment_id") or "") != experiment_id:
                continue
            condition_id = str(identities.get("condition_id") or "").strip() or None
            raw_rules = identities.get("rule_ids")
            if not isinstance(raw_rules, list):
                single = identities.get("rule_id")
                raw_rules = [] if single is None else [single]
            rules = tuple(sorted({int(value) for value in raw_rules if str(value).strip()}))
            return condition_id, rules, (str(row.get("plan_id") or "").strip() or None)
        return None, (), None

    def resolve(self, experiment_id: str) -> ExperimentTargetContext:
        experiment_id = str(experiment_id).strip()
        if not experiment_id:
            raise ExperimentTargetContextError("experiment_id is required")
        metadata = self._metadata(experiment_id)
        raw_metadata_rules = metadata.get("rule_ids")
        if not isinstance(raw_metadata_rules, list):
            raw_metadata_rules = []
        metadata_rules = tuple(sorted({int(value) for value in raw_metadata_rules if str(value).strip()}))
        condition_id, registry_rules, plan_id = self._registry_identity(experiment_id)
        if metadata_rules and registry_rules and metadata_rules != registry_rules:
            raise ExperimentTargetContextError(
                f"target identity mismatch for {experiment_id}: SQLite={metadata_rules} registry={registry_rules}"
            )
        rules = registry_rules or metadata_rules
        if not rules:
            raise ExperimentTargetContextError(f"no canonical rule target recorded for {experiment_id}")
        return ExperimentTargetContext(
            experiment_id=experiment_id,
            condition_id=condition_id,
            rule_ids=rules,
            plan_id=plan_id or (str(metadata.get("source_plan_id") or "").strip() or None),
        )


__all__ = ["ExperimentTargetContext", "ExperimentTargetContextError", "ExperimentTargetContextReader"]
