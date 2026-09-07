"""Immutable models for OL2-CAMPAIGNS1."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from Analyzer_next.execution.observer.shell2.config1.model import PreparedConfiguration, WorldRecord


class CampaignStage(str, Enum):
    SCOPE = "scope"
    CAMPAIGN = "campaign"
    QUEUE = "queue"


@dataclass(frozen=True, slots=True)
class CampaignDraft:
    selected_rule_ids: tuple[int, ...] = ()
    max_ticks: int = 20_000
    sample_every: int = 10
    pressure_every: int = 100
    repetitions: int = 1
    seed_start: int | None = None

    def with_updates(self, **changes: Any) -> "CampaignDraft":
        if "selected_rule_ids" in changes:
            changes["selected_rule_ids"] = tuple(sorted({int(v) for v in changes["selected_rule_ids"]}))
        if "seed_start" in changes and changes["seed_start"] is not None:
            changes["seed_start"] = int(changes["seed_start"])
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class CampaignPlanRow:
    ordinal: int
    rule_id: int
    repetition: int
    seed: int | None
    prepared: PreparedConfiguration


@dataclass(frozen=True, slots=True)
class CampaignPlan:
    rows: tuple[CampaignPlanRow, ...]
    plan_hash: str

    @property
    def run_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True, slots=True)
class CampaignSnapshot:
    worlds: tuple[WorldRecord, ...] = ()
    query: str = ""
    draft: CampaignDraft = CampaignDraft()
    plan: CampaignPlan | None = None
    stage: CampaignStage = CampaignStage.SCOPE
    revision: int = 0

    @property
    def selected_worlds(self) -> tuple[WorldRecord, ...]:
        selected = set(self.draft.selected_rule_ids)
        return tuple(world for world in self.worlds if world.rule_id in selected)

    @property
    def visible_worlds(self) -> tuple[WorldRecord, ...]:
        query = self.query.strip().lower()
        if not query:
            return self.worlds
        digits = "".join(ch for ch in query if ch.isdigit())
        numeric = str(int(digits)) if digits else ""
        rows: list[WorldRecord] = []
        for world in self.worlds:
            if (
                query in world.display_id.lower()
                or (numeric and numeric == str(world.rule_id))
                or query in world.world_class.lower()
                or query in str(world.genome_hash or "").lower()
            ):
                rows.append(world)
        if numeric:
            rows.sort(key=lambda item: (0 if str(item.rule_id) == numeric else 1, item.rule_id))
        return tuple(rows)


__all__ = [
    "CampaignDraft",
    "CampaignPlan",
    "CampaignPlanRow",
    "CampaignSnapshot",
    "CampaignStage",
]
