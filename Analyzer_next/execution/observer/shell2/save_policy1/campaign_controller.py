"""SAVE-POLICY1 campaign controller with explicit pre-review autosave cadence."""
from __future__ import annotations

import hashlib
import json

from Analyzer_next.execution.observer.shell2.campaigns1.controller import CampaignController
from Analyzer_next.execution.observer.shell2.campaigns1.model import CampaignPlan, CampaignPlanRow, CampaignStage
from Analyzer_next.execution.observer.shell2.config1.model import ConfigurationDraft, ProvenanceKind


class SavePolicyCampaignController(CampaignController):
    def __init__(self, *args, autosave_every: int = 5_000, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._autosave_every = 0
        self.set_autosave_every(autosave_every, invalidate=False)

    @property
    def autosave_every(self) -> int:
        return self._autosave_every

    def set_autosave_every(self, value: int, *, invalidate: bool = True):
        ticks = int(value)
        if ticks < 0:
            raise ValueError("campaign autosave ticks cannot be negative")
        changed = ticks != self._autosave_every
        self._autosave_every = ticks
        if changed and invalidate:
            return self._publish(plan=None)
        return self.snapshot

    def prepare(self):
        draft = self.snapshot.draft
        if not draft.selected_rule_ids:
            raise ValueError("select at least one canonical world for the campaign")
        worlds = {world.rule_id: world for world in self.snapshot.worlds}
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
                    autosave_every=self._autosave_every,
                    sample_every=draft.sample_every,
                    pressure_every=draft.pressure_every,
                    seed=seed,
                )
                review = self.review_port.review(config)
                if not review.valid or review.prepared is None:
                    detail = "; ".join(issue.message for issue in review.issues) or "unknown CONFIG1 validation failure"
                    raise ValueError(f"Rule {world.display_id} campaign row rejected: {detail}")
                rows.append(CampaignPlanRow(
                    ordinal=ordinal,
                    rule_id=world.rule_id,
                    repetition=repetition,
                    seed=seed,
                    prepared=review.prepared,
                ))
        payload = [{
            "ordinal": row.ordinal,
            "rule_id": row.rule_id,
            "repetition": row.repetition,
            "seed": row.seed,
            "review_hash": row.prepared.review_hash,
            "run_spec_hash": row.prepared.run_spec.content_hash,
            "autosave_every": row.prepared.effective_draft.autosave_every,
        } for row in rows]
        plan_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        plan = CampaignPlan(rows=tuple(rows), plan_hash=plan_hash)
        return self._publish(plan=plan, stage=CampaignStage.QUEUE)


__all__ = ["SavePolicyCampaignController"]
