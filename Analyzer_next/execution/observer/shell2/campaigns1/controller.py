"""Toolkit/storage-independent OL2-CAMPAIGNS1 batch composer."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Iterable, Protocol

from Analyzer_next.execution.observer.shell2.config1.model import (
    ConfigurationDraft,
    ConfigurationReview,
    ProvenanceKind,
    WorldRecord,
)

from .model import CampaignDraft, CampaignPlan, CampaignPlanRow, CampaignSnapshot, CampaignStage


class CampaignReviewPort(Protocol):
    def review(self, draft: ConfigurationDraft) -> ConfigurationReview: ...


class CampaignController:
    """Compose canonical queue rows without owning persistence or dispatch."""

    def __init__(self, review_port: CampaignReviewPort, *, worlds: Iterable[WorldRecord]) -> None:
        self.review_port = review_port
        ordered = tuple(sorted(tuple(worlds), key=lambda item: item.rule_id))
        if len({world.rule_id for world in ordered}) != len(ordered):
            raise ValueError("duplicate campaign world rule_id")
        self._snapshot = CampaignSnapshot(worlds=ordered)

    @property
    def snapshot(self) -> CampaignSnapshot:
        return self._snapshot

    def _publish(self, **changes) -> CampaignSnapshot:
        self._snapshot = replace(
            self._snapshot,
            **changes,
            revision=self._snapshot.revision + 1,
        )
        return self._snapshot

    def set_query(self, query: str) -> CampaignSnapshot:
        return self._publish(query=str(query))

    def set_scope(self, rule_ids: Iterable[int]) -> CampaignSnapshot:
        requested = tuple(sorted({int(value) for value in rule_ids}))
        by_id = {world.rule_id: world for world in self._snapshot.worlds}
        missing = [rule_id for rule_id in requested if rule_id not in by_id]
        if missing:
            raise ValueError(f"campaign source is not in canonical catalog: {missing[0]}")
        unverified = [by_id[rule_id].display_id for rule_id in requested if not by_id[rule_id].source_verified]
        if unverified:
            raise ValueError(f"campaign source identity is not verified: {unverified[0]}")
        draft = self._snapshot.draft.with_updates(selected_rule_ids=requested)
        return self._publish(draft=draft, plan=None)

    def select_visible(self) -> CampaignSnapshot:
        current = set(self._snapshot.draft.selected_rule_ids)
        current.update(world.rule_id for world in self._snapshot.visible_worlds if world.source_verified)
        return self.set_scope(current)

    def select_not_observed_visible(self) -> CampaignSnapshot:
        """Replace visible selection with verified Worlds not marked observed.

        Hidden selections are preserved, matching the Campaigns tree's existing
        filtered multi-selection contract.  Observation meaning remains owned by
        the canonical WorldRecord supplied by CATALOG1.
        """
        visible = self._snapshot.visible_worlds
        current = set(self._snapshot.draft.selected_rule_ids)
        current.difference_update(world.rule_id for world in visible)
        current.update(
            world.rule_id
            for world in visible
            if world.source_verified and not world.observed
        )
        return self.set_scope(current)

    def clear_scope(self) -> CampaignSnapshot:
        return self.set_scope(())

    def update_draft(self, **changes) -> CampaignSnapshot:
        draft = self._snapshot.draft.with_updates(**changes)
        if draft.max_ticks < 1:
            raise ValueError("campaign horizon must be positive")
        if draft.sample_every < 1:
            raise ValueError("campaign sample cadence must be positive")
        if draft.pressure_every < 1:
            raise ValueError("campaign pressure cadence must be positive")
        if draft.repetitions < 1 or draft.repetitions > 50:
            raise ValueError("campaign repetitions must be between 1 and 50")
        if draft.seed_start is not None and draft.seed_start < 0:
            raise ValueError("campaign seed start cannot be negative")
        return self._publish(draft=draft, plan=None)

    def set_stage(self, stage: CampaignStage | str) -> CampaignSnapshot:
        return self._publish(stage=CampaignStage(stage))

    def prepare(self) -> CampaignSnapshot:
        draft = self._snapshot.draft
        if not draft.selected_rule_ids:
            raise ValueError("select at least one canonical world for the campaign")
        worlds = {world.rule_id: world for world in self._snapshot.worlds}
        rows: list[CampaignPlanRow] = []
        ordinal = 0
        for rule_id in draft.selected_rule_ids:
            world = worlds[rule_id]
            if not world.source_verified:
                raise ValueError(f"campaign source identity is not verified: {world.display_id}")
            for repetition in range(1, draft.repetitions + 1):
                ordinal += 1
                seed = None if draft.seed_start is None else draft.seed_start + ordinal - 1
                config = ConfigurationDraft(
                    world=world,
                    provenance=ProvenanceKind.CANONICAL_QUEUE,
                    max_ticks=draft.max_ticks,
                    sample_every=draft.sample_every,
                    pressure_every=draft.pressure_every,
                    seed=seed,
                )
                review = self.review_port.review(config)
                if not review.valid or review.prepared is None:
                    detail = "; ".join(issue.message for issue in review.issues) or "unknown CONFIG1 validation failure"
                    raise ValueError(f"Rule {world.display_id} campaign row rejected: {detail}")
                rows.append(
                    CampaignPlanRow(
                        ordinal=ordinal,
                        rule_id=world.rule_id,
                        repetition=repetition,
                        seed=seed,
                        prepared=review.prepared,
                    )
                )
        payload = [
            {
                "ordinal": row.ordinal,
                "rule_id": row.rule_id,
                "repetition": row.repetition,
                "seed": row.seed,
                "review_hash": row.prepared.review_hash,
                "run_spec_hash": row.prepared.run_spec.content_hash,
            }
            for row in rows
        ]
        plan_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        plan = CampaignPlan(rows=tuple(rows), plan_hash=plan_hash)
        return self._publish(plan=plan, stage=CampaignStage.QUEUE)


__all__ = ["CampaignController", "CampaignReviewPort"]
