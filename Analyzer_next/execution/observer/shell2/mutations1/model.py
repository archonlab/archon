"""Immutable models for OL2-MUTATIONS1."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from Analyzer_next.execution.observer.shell2.config1.model import WorldRecord


class MutationStage(str, Enum):
    SOURCE = "source"
    MUTATION = "mutation"
    EXECUTION = "execution"


class MutationStrategy(str, Enum):
    SINGLE_PARAMETER = "single_parameter"
    PRESET = "preset"
    LOCAL_RANDOM = "local_random"


@dataclass(frozen=True, slots=True)
class MutationDraft:
    source_rule_id: int | None = None
    strategy: MutationStrategy = MutationStrategy.SINGLE_PARAMETER
    parameter: str | None = None
    preset: str = "balanced"
    intensity: float = 0.70
    count: int = 1
    seed: int = 0

    def with_updates(self, **changes: Any) -> "MutationDraft":
        if "strategy" in changes:
            changes["strategy"] = MutationStrategy(changes["strategy"])
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class MutationPreview:
    source_rule_id: int
    strategy: str
    seed: int
    mutated_hash: str
    change_count: int
    changes: tuple[dict[str, Any], ...]
    baseline_status: str
    baseline_detail: str


@dataclass(frozen=True, slots=True)
class MutationRecord:
    mutation_id: str
    parent_rule_id: int
    mode: str
    parameter: str | None
    preset: str | None
    intensity: float
    seed: int
    change_count: int
    created_at: str
    status: str
    run_dir: Path
    rule_file: Path
    manifest_file: Path
    analysis_report: Path | None = None


@dataclass(frozen=True, slots=True)
class MutationSnapshot:
    worlds: tuple[WorldRecord, ...] = ()
    query: str = ""
    selected_source_id: int | None = None
    draft: MutationDraft = MutationDraft()
    preview: MutationPreview | None = None
    records: tuple[MutationRecord, ...] = ()
    selected_mutation_id: str | None = None
    stage: MutationStage = MutationStage.SOURCE
    revision: int = 0

    @property
    def selected_source(self) -> WorldRecord | None:
        return next((w for w in self.worlds if w.rule_id == self.selected_source_id), None)

    @property
    def selected_record(self) -> MutationRecord | None:
        return next((r for r in self.records if r.mutation_id == self.selected_mutation_id), None)

    @property
    def visible_worlds(self) -> tuple[WorldRecord, ...]:
        query = self.query.strip().lower()
        if not query:
            return self.worlds
        digits = "".join(ch for ch in query if ch.isdigit())
        numeric = str(int(digits)) if digits else ""
        rows: list[WorldRecord] = []
        for world in self.worlds:
            rid = world.display_id
            rid_numeric = str(world.rule_id)
            if (
                query in rid.lower()
                or (numeric and numeric == rid_numeric)
                or query in world.world_class.lower()
                or query in str(world.genome_hash or "").lower()
            ):
                rows.append(world)
        if numeric:
            rows.sort(key=lambda w: (0 if str(w.rule_id) == numeric else 1, w.rule_id))
        return tuple(rows)


__all__ = [
    "MutationDraft",
    "MutationPreview",
    "MutationRecord",
    "MutationSnapshot",
    "MutationStage",
    "MutationStrategy",
]
