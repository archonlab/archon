"""Storage-independent contracts for ARCHON's scientific file Data Layer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .ids import normalize_rule_id


@dataclass(frozen=True)
class ScientificDataPaths:
    results_root: Path
    analysis_root: Path
    knowledge_root: Path
    atlas_path: Path

    @classmethod
    def create(
        cls,
        *,
        results_root: Path,
        analysis_root: Path,
        knowledge_root: Path,
        atlas_path: Path | None = None,
    ) -> "ScientificDataPaths":
        results_root = results_root.resolve()
        analysis_root = analysis_root.resolve()
        knowledge_root = knowledge_root.resolve()
        return cls(
            results_root=results_root,
            analysis_root=analysis_root,
            knowledge_root=knowledge_root,
            atlas_path=(
                atlas_path or knowledge_root / "research_atlas.json"
            ).resolve(),
        )


@dataclass(frozen=True)
class ScientificDataSnapshot:
    passport_records: list[dict[str, Any]]
    passports_by_rule: dict[str, list[dict[str, Any]]]
    passports: dict[str, dict[str, Any]]
    atlas_experiments: list[dict[str, Any]]
    atlas_by_rule: dict[str, list[dict[str, Any]]]
    atlas: dict[str, dict[str, Any]]
    mechanisms_by_rule: dict[str, dict[str, Any]]
    notebooks_by_rule: dict[str, dict[str, Any]]
    discoveries: dict[str, list[dict[str, Any]]]
    principles: dict[str, dict[str, Any]]
    predictions: dict[str, dict[str, Any]]
    validations: dict[str, dict[str, Any]]

    @property
    def rule_ids(self) -> tuple[str, ...]:
        discovery_rules = {
            rule_id
            for rule_id, discoveries in self.discoveries.items()
            if discoveries
        }
        ids = (
            set(self.passports_by_rule)
            | set(self.atlas_by_rule)
            | set(self.mechanisms_by_rule)
            | set(self.notebooks_by_rule)
            | discovery_rules
        )
        return tuple(sorted(ids))

    def experiments_for_rule(self, rule_id: str) -> list[dict[str, Any]]:
        normalized = normalize_rule_id(rule_id)
        return list(self.atlas_by_rule.get(normalized, [])) if normalized else []

    def passports_for_rule(self, rule_id: str) -> list[dict[str, Any]]:
        normalized = normalize_rule_id(rule_id)
        return list(self.passports_by_rule.get(normalized, [])) if normalized else []

    def current_atlas_record(self, rule_id: str) -> dict[str, Any] | None:
        normalized = normalize_rule_id(rule_id)
        return self.atlas.get(normalized) if normalized else None

    def best_passport(self, rule_id: str) -> dict[str, Any] | None:
        normalized = normalize_rule_id(rule_id)
        return self.passports.get(normalized) if normalized else None

    def mechanism(self, rule_id: str) -> dict[str, Any]:
        normalized = normalize_rule_id(rule_id)
        if not normalized:
            return {"scores": {}, "mechanisms": []}
        return self.mechanisms_by_rule.get(
            normalized,
            {"scores": {}, "mechanisms": []},
        )

    def notebook(self, rule_id: str) -> dict[str, Any]:
        normalized = normalize_rule_id(rule_id)
        return self.notebooks_by_rule.get(normalized, {}) if normalized else {}

    def principle_ids_for_rule(self, rule_id: str) -> list[str]:
        normalized = normalize_rule_id(rule_id)
        if not normalized:
            return []
        matches: list[str] = []
        for principle_id, principle in self.principles.items():
            principle_rules = {
                candidate
                for raw_rule in principle.get("rules", [])
                if (candidate := normalize_rule_id(raw_rule))
            }
            if normalized in principle_rules:
                matches.append(principle_id)
        return sorted(matches)

    def summary(self) -> dict[str, int]:
        return {
            "rules": len(self.rule_ids),
            "passport_records": len(self.passport_records),
            "passports": len(self.passports),
            "atlas_records": len(self.atlas_experiments),
            "atlas_rules": len(self.atlas_by_rule),
            "mechanism_reports": len(self.mechanisms_by_rule),
            "notebooks": len(self.notebooks_by_rule),
            "rules_with_discoveries": sum(
                1 for discoveries in self.discoveries.values() if discoveries
            ),
            "principles": len(self.principles),
            "predictions": len(self.predictions),
            "validations": len(self.validations),
        }


class ScientificDataRepository(Protocol):
    def load(self, paths: ScientificDataPaths) -> ScientificDataSnapshot:
        ...
