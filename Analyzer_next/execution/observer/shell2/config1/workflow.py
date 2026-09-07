"""Pure CONFIG1 selection, editing, and review workflow."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from .model import (
    ConfigStep,
    ConfigurationDraft,
    ConfigurationReview,
    ProvenanceKind,
    WorldRecord,
)
from .selection import filter_worlds


class ReviewService(Protocol):
    def review(self, draft: ConfigurationDraft) -> ConfigurationReview: ...


@dataclass(frozen=True, slots=True)
class WorldFilter:
    query: str = ""
    world_class: str = "All"
    status: str = "All"
    sort: str = "Rule ID"


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    worlds: tuple[WorldRecord, ...]
    filters: WorldFilter
    selected_world_id: int | None
    draft: ConfigurationDraft
    review: ConfigurationReview | None
    step: ConfigStep
    revision: int = 0

    @property
    def visible_worlds(self) -> tuple[WorldRecord, ...]:
        return filter_worlds(
            self.worlds,
            query=self.filters.query,
            world_class=self.filters.world_class,
            status=self.filters.status,
            sort=self.filters.sort,
        )

    @property
    def world_classes(self) -> tuple[str, ...]:
        return tuple(sorted({world.world_class for world in self.worlds}))


class ConfigurationWorkflow:
    """Mutable coordinator whose every published value is immutable."""

    def __init__(
        self,
        command_service: ReviewService,
        *,
        default_output_dir: Path | str,
    ) -> None:
        self._command_service = command_service
        self._snapshot = ConfigSnapshot(
            worlds=(),
            filters=WorldFilter(),
            selected_world_id=None,
            draft=ConfigurationDraft(
                world=None,
                output_dir=str(default_output_dir),
            ),
            review=None,
            step=ConfigStep.SELECT_WORLD,
        )

    @property
    def snapshot(self) -> ConfigSnapshot:
        return self._snapshot

    def _publish(self, snapshot: ConfigSnapshot) -> ConfigSnapshot:
        self._snapshot = replace(snapshot, revision=self._snapshot.revision + 1)
        return self._snapshot

    def load_worlds(self, worlds: tuple[WorldRecord, ...]) -> ConfigSnapshot:
        ordered = tuple(sorted(worlds, key=lambda item: item.rule_id))
        if len({world.rule_id for world in ordered}) != len(ordered):
            raise ValueError("duplicate world rule_id")
        selected = self._snapshot.selected_world_id
        if selected is not None and selected not in {world.rule_id for world in ordered}:
            selected = None
        draft = self._snapshot.draft
        if selected is None:
            draft = draft.with_updates(world=None)
        return self._publish(
            replace(
                self._snapshot,
                worlds=ordered,
                selected_world_id=selected,
                draft=draft,
                review=None,
                step=(
                    self._snapshot.step
                    if selected is not None
                    else ConfigStep.SELECT_WORLD
                ),
            )
        )

    def set_filters(self, **changes: str) -> ConfigSnapshot:
        filters = replace(self._snapshot.filters, **changes)
        return self._publish(replace(self._snapshot, filters=filters))

    def select_world(self, rule_id: int) -> ConfigSnapshot:
        world = next(
            (item for item in self._snapshot.worlds if item.rule_id == int(rule_id)),
            None,
        )
        if world is None:
            raise ValueError(f"world is not in catalog: {rule_id}")
        return self._publish(
            replace(
                self._snapshot,
                selected_world_id=world.rule_id,
                draft=self._snapshot.draft.with_updates(world=world),
                review=None,
                step=ConfigStep.CONFIGURE,
            )
        )

    def update_draft(self, **changes: Any) -> ConfigSnapshot:
        if self._snapshot.draft.world is None:
            raise ValueError("select a world before configuration")
        draft = self._snapshot.draft.with_updates(**changes)
        return self._publish(
            replace(
                self._snapshot,
                draft=draft,
                review=None,
                step=ConfigStep.CONFIGURE,
            )
        )

    def set_provenance(self, provenance: ProvenanceKind | str) -> ConfigSnapshot:
        return self.update_draft(provenance=ProvenanceKind(provenance))

    def review(self) -> ConfigSnapshot:
        review = self._command_service.review(self._snapshot.draft)
        return self._publish(
            replace(
                self._snapshot,
                review=review,
                step=ConfigStep.REVIEW if review.valid else ConfigStep.CONFIGURE,
            )
        )

    def back_to_worlds(self) -> ConfigSnapshot:
        return self._publish(
            replace(self._snapshot, step=ConfigStep.SELECT_WORLD, review=None)
        )
