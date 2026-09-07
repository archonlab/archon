"""Storage/toolkit-independent coordinator for OL2-MUTATIONS1."""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Protocol

from Analyzer_next.execution.observer.shell2.config1.model import PreparedConfiguration, WorldRecord

from .model import (
    MutationDraft,
    MutationPreview,
    MutationRecord,
    MutationSnapshot,
    MutationStage,
)


class MutationWorkspacePort(Protocol):
    def load_worlds(self) -> tuple[WorldRecord, ...]: ...
    def parameter_choices(self, rule_id: int) -> tuple[str, ...]: ...
    def preview(self, draft: MutationDraft) -> MutationPreview: ...
    def materialize(self, draft: MutationDraft) -> tuple[MutationRecord, ...]: ...
    def load_records(self) -> tuple[MutationRecord, ...]: ...
    def prepare_launch(self, mutation_id: str) -> PreparedConfiguration: ...


class MutationWorkspaceController:
    def __init__(
        self,
        port: MutationWorkspacePort,
        *,
        initial_worlds: Iterable[WorldRecord] | None = None,
    ) -> None:
        self.port = port
        worlds = tuple(sorted(tuple(initial_worlds or ()), key=lambda item: item.rule_id))
        self._snapshot = MutationSnapshot(worlds=worlds)

    @property
    def snapshot(self) -> MutationSnapshot:
        return self._snapshot

    def _publish(self, **changes) -> MutationSnapshot:
        self._snapshot = replace(
            self._snapshot,
            **changes,
            revision=self._snapshot.revision + 1,
        )
        return self._snapshot

    def refresh_sources(self) -> MutationSnapshot:
        worlds = tuple(sorted(self.port.load_worlds(), key=lambda item: item.rule_id))
        selected = self._snapshot.selected_source_id
        if selected not in {w.rule_id for w in worlds}:
            selected = None
        draft = self._snapshot.draft.with_updates(source_rule_id=selected)
        return self._publish(worlds=worlds, selected_source_id=selected, draft=draft, preview=None)

    def set_query(self, query: str) -> MutationSnapshot:
        return self._publish(query=str(query))

    def select_source(self, rule_id: int) -> MutationSnapshot:
        world = next((w for w in self._snapshot.worlds if w.rule_id == int(rule_id)), None)
        if world is None:
            raise ValueError(f"mutation source is not in canonical catalog: {rule_id}")
        if not world.source_verified:
            raise ValueError(f"mutation source identity is not verified: {world.display_id}")
        draft = self._snapshot.draft.with_updates(source_rule_id=world.rule_id)
        choices = self.port.parameter_choices(world.rule_id)
        if draft.parameter not in choices:
            draft = draft.with_updates(parameter=(choices[0] if choices else None))
        return self._publish(
            selected_source_id=world.rule_id,
            draft=draft,
            preview=None,
            stage=MutationStage.MUTATION,
        )

    def parameter_choices(self) -> tuple[str, ...]:
        if self._snapshot.selected_source_id is None:
            return ()
        return self.port.parameter_choices(self._snapshot.selected_source_id)

    def update_draft(self, **changes) -> MutationSnapshot:
        draft = self._snapshot.draft.with_updates(**changes)
        if draft.count < 1 or draft.count > 20:
            raise ValueError("mutation batch size must be between 1 and 20")
        if not (0.05 <= float(draft.intensity) <= 3.0):
            raise ValueError("mutation intensity must be between 0.05 and 3.0")
        if draft.seed < 0:
            raise ValueError("mutation seed cannot be negative")
        return self._publish(draft=draft, preview=None)

    def set_stage(self, stage: MutationStage | str) -> MutationSnapshot:
        stage = MutationStage(stage)
        if stage is MutationStage.MUTATION and self._snapshot.selected_source_id is None:
            raise ValueError("select a source rule first")
        if stage is MutationStage.EXECUTION:
            self.refresh_records()
        return self._publish(stage=stage)

    def preview(self) -> MutationSnapshot:
        if self._snapshot.selected_source_id is None:
            raise ValueError("select a source rule first")
        preview = self.port.preview(self._snapshot.draft)
        return self._publish(preview=preview)

    def create_batch(self) -> MutationSnapshot:
        if self._snapshot.selected_source_id is None:
            raise ValueError("select a source rule first")
        records = self.port.materialize(self._snapshot.draft)
        all_records = self.port.load_records()
        selected = records[0].mutation_id if records else None
        return self._publish(
            records=all_records,
            selected_mutation_id=selected,
            stage=MutationStage.EXECUTION,
            preview=None,
        )

    def refresh_records(self) -> MutationSnapshot:
        records = self.port.load_records()
        selected = self._snapshot.selected_mutation_id
        if selected not in {r.mutation_id for r in records}:
            selected = records[0].mutation_id if records else None
        return self._publish(records=records, selected_mutation_id=selected)

    def select_record(self, mutation_id: str) -> MutationSnapshot:
        if mutation_id not in {r.mutation_id for r in self._snapshot.records}:
            raise ValueError(f"unknown mutation: {mutation_id}")
        return self._publish(selected_mutation_id=mutation_id)

    def prepare_selected_launch(self) -> PreparedConfiguration:
        selected = self._snapshot.selected_record
        if selected is None:
            raise ValueError("select a prepared mutation first")
        return self.port.prepare_launch(selected.mutation_id)


__all__ = ["MutationWorkspaceController", "MutationWorkspacePort"]
