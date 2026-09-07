#!/usr/bin/env python3
"""Evidence timeline construction for Project ARCHON Observer.

This module reconstructs how evidence, hypotheses, unknowns, and conflicts
change across checkpoints of one Observer run.

A timeline is built from ordered EvidenceReport snapshots.  It records events
such as:

- observation appeared;
- evidence appeared;
- evidence confidence increased or decreased;
- hypothesis confidence changed;
- hypothesis status changed;
- a new leading hypothesis emerged;
- an unknown question opened, became partial, or was resolved;
- an evidence conflict appeared or was resolved.

The module does not reinterpret evidence or rerun scientific engines.  It only
compares already validated reports and emits an immutable historical record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

try:
    from .evidence_models import (
        ConflictStatus,
        Evidence,
        EvidenceConflict,
        EvidenceReport,
        Hypothesis,
        Observation,
        UnknownQuestion,
        UnknownStatus,
    )
except ImportError:  # Direct execution from the Observer directory.
    from evidence_models import (
        ConflictStatus,
        Evidence,
        EvidenceConflict,
        EvidenceReport,
        Hypothesis,
        Observation,
        UnknownQuestion,
        UnknownStatus,
    )


OBSERVER_EVIDENCE_TIMELINE_VERSION = "1.0.0"


class EvidenceTimelineError(ValueError):
    """Raised when timeline checkpoints or event construction are invalid."""


class TimelineEventType(str, Enum):
    """Stable event vocabulary for Evidence Framework history."""

    OBSERVATION_APPEARED = "observation_appeared"
    EVIDENCE_APPEARED = "evidence_appeared"
    EVIDENCE_CONFIDENCE_INCREASED = "evidence_confidence_increased"
    EVIDENCE_CONFIDENCE_DECREASED = "evidence_confidence_decreased"
    HYPOTHESIS_APPEARED = "hypothesis_appeared"
    HYPOTHESIS_CONFIDENCE_INCREASED = "hypothesis_confidence_increased"
    HYPOTHESIS_CONFIDENCE_DECREASED = "hypothesis_confidence_decreased"
    HYPOTHESIS_STATUS_CHANGED = "hypothesis_status_changed"
    LEADING_HYPOTHESIS_CHANGED = "leading_hypothesis_changed"
    UNKNOWN_OPENED = "unknown_opened"
    UNKNOWN_STATUS_CHANGED = "unknown_status_changed"
    UNKNOWN_RESOLVED = "unknown_resolved"
    CONFLICT_APPEARED = "conflict_appeared"
    CONFLICT_STATUS_CHANGED = "conflict_status_changed"
    CONFLICT_RESOLVED = "conflict_resolved"


@dataclass(frozen=True, slots=True)
class TimelineCheckpoint:
    """One validated EvidenceReport observed at a specific tick."""

    tick: int
    report: EvidenceReport
    label: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        tick = int(self.tick)
        if tick < 0:
            raise EvidenceTimelineError("checkpoint tick must be >= 0")
        if not isinstance(self.report, EvidenceReport):
            raise EvidenceTimelineError(
                "checkpoint report must be an EvidenceReport"
            )
        object.__setattr__(self, "tick", tick)
        object.__setattr__(self, "label", str(self.label).strip())
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    """One traceable change between EvidenceReport checkpoints."""

    tick: int
    event_type: TimelineEventType
    title: str
    description: str
    entity_id: str
    entity_type: str
    previous_value: Any = None
    current_value: Any = None
    confidence_delta: float | None = None
    source_report_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(
        default_factory=lambda: f"EVT-{uuid4().hex}"
    )

    def __post_init__(self) -> None:
        tick = int(self.tick)
        if tick < 0:
            raise EvidenceTimelineError("event tick must be >= 0")
        if not isinstance(self.event_type, TimelineEventType):
            try:
                object.__setattr__(
                    self,
                    "event_type",
                    TimelineEventType(str(self.event_type)),
                )
            except ValueError as exc:
                raise EvidenceTimelineError(
                    f"Invalid event type: {self.event_type!r}"
                ) from exc

        for name in ("title", "entity_id", "entity_type", "event_id"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise EvidenceTimelineError(f"{name} must not be empty")
            object.__setattr__(self, name, value)

        object.__setattr__(
            self,
            "description",
            str(self.description).strip(),
        )
        object.__setattr__(
            self,
            "source_report_id",
            (
                str(self.source_report_id).strip()
                if self.source_report_id is not None
                else None
            ),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

        if self.confidence_delta is not None:
            object.__setattr__(
                self,
                "confidence_delta",
                float(self.confidence_delta),
            )


@dataclass(frozen=True, slots=True)
class EvidenceTimeline:
    """Complete history for one world and run."""

    world_id: str
    run_id: str
    events: tuple[TimelineEvent, ...]
    checkpoint_ticks: tuple[int, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timeline_id: str = field(
        default_factory=lambda: f"TML-{uuid4().hex}"
    )
    schema: str = "archon.evidence_timeline"
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        world_id = str(self.world_id).strip()
        run_id = str(self.run_id).strip()
        timeline_id = str(self.timeline_id).strip()

        if not world_id:
            raise EvidenceTimelineError("world_id must not be empty")
        if not run_id:
            raise EvidenceTimelineError("run_id must not be empty")
        if not timeline_id:
            raise EvidenceTimelineError("timeline_id must not be empty")

        events = tuple(self.events)
        if not all(isinstance(item, TimelineEvent) for item in events):
            raise EvidenceTimelineError(
                "events must contain TimelineEvent objects"
            )

        checkpoint_ticks = tuple(int(item) for item in self.checkpoint_ticks)
        if any(item < 0 for item in checkpoint_ticks):
            raise EvidenceTimelineError(
                "checkpoint_ticks must contain non-negative values"
            )
        if tuple(sorted(checkpoint_ticks)) != checkpoint_ticks:
            raise EvidenceTimelineError(
                "checkpoint_ticks must be sorted"
            )

        object.__setattr__(self, "world_id", world_id)
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "timeline_id", timeline_id)
        object.__setattr__(
            self,
            "events",
            tuple(sorted(events, key=lambda item: (item.tick, item.event_id))),
        )
        object.__setattr__(self, "checkpoint_ticks", checkpoint_ticks)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "timeline_id": self.timeline_id,
            "world_id": self.world_id,
            "run_id": self.run_id,
            "checkpoint_ticks": list(self.checkpoint_ticks),
            "metadata": _jsonable(self.metadata),
            "events": [
                {
                    "event_id": item.event_id,
                    "tick": item.tick,
                    "event_type": item.event_type.value,
                    "title": item.title,
                    "description": item.description,
                    "entity_id": item.entity_id,
                    "entity_type": item.entity_type,
                    "previous_value": _jsonable(item.previous_value),
                    "current_value": _jsonable(item.current_value),
                    "confidence_delta": item.confidence_delta,
                    "source_report_id": item.source_report_id,
                    "metadata": _jsonable(item.metadata),
                }
                for item in self.events
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class EvidenceTimelineConfig:
    """Thresholds controlling which changes become timeline events."""

    evidence_confidence_delta: float = 0.05
    hypothesis_confidence_delta: float = 0.05
    emit_initial_snapshot_events: bool = True
    emit_observation_events: bool = True
    emit_evidence_events: bool = True
    emit_hypothesis_events: bool = True
    emit_unknown_events: bool = True
    emit_conflict_events: bool = True

    def __post_init__(self) -> None:
        for name in (
            "evidence_confidence_delta",
            "hypothesis_confidence_delta",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise EvidenceTimelineError(
                    f"{name} must be in [0, 1]"
                )
            object.__setattr__(self, name, value)


class EvidenceTimelineBuilder:
    """Build an EvidenceTimeline from ordered report checkpoints."""

    def __init__(
        self,
        config: EvidenceTimelineConfig | None = None,
    ) -> None:
        self.config = config or EvidenceTimelineConfig()

    def build(
        self,
        checkpoints: Sequence[TimelineCheckpoint],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> EvidenceTimeline:
        checkpoints = tuple(checkpoints)
        if not checkpoints:
            raise EvidenceTimelineError(
                "At least one TimelineCheckpoint is required"
            )
        if not all(
            isinstance(item, TimelineCheckpoint)
            for item in checkpoints
        ):
            raise EvidenceTimelineError(
                "checkpoints must contain TimelineCheckpoint objects"
            )

        checkpoints = tuple(
            sorted(checkpoints, key=lambda item: item.tick)
        )
        self._validate_checkpoint_identity(checkpoints)

        events: list[TimelineEvent] = []

        if self.config.emit_initial_snapshot_events:
            events.extend(
                self._initial_events(checkpoints[0])
            )

        for previous, current in zip(
            checkpoints,
            checkpoints[1:],
        ):
            events.extend(
                self._compare_reports(previous, current)
            )

        first_report = checkpoints[0].report
        final_report = checkpoints[-1].report

        timeline_metadata = dict(metadata or {})
        timeline_metadata.update(
            {
                "timeline_builder_version": (
                    OBSERVER_EVIDENCE_TIMELINE_VERSION
                ),
                "checkpoint_count": len(checkpoints),
                "event_count": len(events),
                "first_report_id": first_report.report_id,
                "final_report_id": final_report.report_id,
                "first_tick": checkpoints[0].tick,
                "last_tick": checkpoints[-1].tick,
            }
        )

        return EvidenceTimeline(
            world_id=first_report.world_id,
            run_id=first_report.run_id,
            events=tuple(events),
            checkpoint_ticks=tuple(
                item.tick for item in checkpoints
            ),
            metadata=timeline_metadata,
        )

    def _initial_events(
        self,
        checkpoint: TimelineCheckpoint,
    ) -> list[TimelineEvent]:
        report = checkpoint.report
        events: list[TimelineEvent] = []

        if self.config.emit_observation_events:
            for item in report.observations:
                events.append(
                    self._observation_appeared(
                        checkpoint.tick,
                        item,
                        report.report_id,
                    )
                )

        if self.config.emit_evidence_events:
            for item in report.evidence:
                events.append(
                    self._evidence_appeared(
                        checkpoint.tick,
                        item,
                        report.report_id,
                    )
                )

        if self.config.emit_hypothesis_events:
            for item in report.hypotheses:
                events.append(
                    self._hypothesis_appeared(
                        checkpoint.tick,
                        item,
                        report.report_id,
                    )
                )
            if report.leading_hypothesis_id is not None:
                events.append(
                    TimelineEvent(
                        tick=checkpoint.tick,
                        event_type=(
                            TimelineEventType.LEADING_HYPOTHESIS_CHANGED
                        ),
                        title="Leading hypothesis established",
                        description=(
                            "The first checkpoint identifies a leading "
                            "hypothesis."
                        ),
                        entity_id=report.leading_hypothesis_id,
                        entity_type="hypothesis",
                        previous_value=None,
                        current_value=report.leading_hypothesis_id,
                        source_report_id=report.report_id,
                    )
                )

        if self.config.emit_unknown_events:
            for item in report.unknowns:
                events.append(
                    self._unknown_opened(
                        checkpoint.tick,
                        item,
                        report.report_id,
                    )
                )

        if self.config.emit_conflict_events:
            for item in report.conflicts:
                events.append(
                    self._conflict_appeared(
                        checkpoint.tick,
                        item,
                        report.report_id,
                    )
                )

        return events

    def _compare_reports(
        self,
        previous: TimelineCheckpoint,
        current: TimelineCheckpoint,
    ) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        old = previous.report
        new = current.report

        if self.config.emit_observation_events:
            old_items = {
                item.observation_id: item
                for item in old.observations
            }
            for item in new.observations:
                if item.observation_id not in old_items:
                    events.append(
                        self._observation_appeared(
                            current.tick,
                            item,
                            new.report_id,
                        )
                    )

        if self.config.emit_evidence_events:
            events.extend(
                self._compare_evidence(
                    current.tick,
                    old.evidence,
                    new.evidence,
                    new.report_id,
                )
            )

        if self.config.emit_hypothesis_events:
            events.extend(
                self._compare_hypotheses(
                    current.tick,
                    old.hypotheses,
                    new.hypotheses,
                    new.report_id,
                )
            )
            if (
                old.leading_hypothesis_id
                != new.leading_hypothesis_id
            ):
                events.append(
                    TimelineEvent(
                        tick=current.tick,
                        event_type=(
                            TimelineEventType.LEADING_HYPOTHESIS_CHANGED
                        ),
                        title="Leading hypothesis changed",
                        description=(
                            "The hypothesis leading the current evidence "
                            "competition changed."
                        ),
                        entity_id=(
                            new.leading_hypothesis_id
                            or old.leading_hypothesis_id
                            or "none"
                        ),
                        entity_type="hypothesis",
                        previous_value=old.leading_hypothesis_id,
                        current_value=new.leading_hypothesis_id,
                        source_report_id=new.report_id,
                    )
                )

        if self.config.emit_unknown_events:
            events.extend(
                self._compare_unknowns(
                    current.tick,
                    old.unknowns,
                    new.unknowns,
                    new.report_id,
                )
            )

        if self.config.emit_conflict_events:
            events.extend(
                self._compare_conflicts(
                    current.tick,
                    old.conflicts,
                    new.conflicts,
                    new.report_id,
                )
            )

        return events

    def _compare_evidence(
        self,
        tick: int,
        previous: Iterable[Evidence],
        current: Iterable[Evidence],
        report_id: str,
    ) -> list[TimelineEvent]:
        old_map = {
            item.evidence_id: item
            for item in previous
        }
        events: list[TimelineEvent] = []

        for item in current:
            old = old_map.get(item.evidence_id)
            if old is None:
                events.append(
                    self._evidence_appeared(
                        tick,
                        item,
                        report_id,
                    )
                )
                continue

            delta = item.confidence - old.confidence
            if (
                abs(delta)
                < self.config.evidence_confidence_delta
            ):
                continue

            event_type = (
                TimelineEventType.EVIDENCE_CONFIDENCE_INCREASED
                if delta > 0
                else TimelineEventType.EVIDENCE_CONFIDENCE_DECREASED
            )
            events.append(
                TimelineEvent(
                    tick=tick,
                    event_type=event_type,
                    title=f"Evidence confidence changed: {item.title}",
                    description=(
                        "Confidence assigned to an existing evidence item "
                        "changed between checkpoints."
                    ),
                    entity_id=item.evidence_id,
                    entity_type="evidence",
                    previous_value=old.confidence,
                    current_value=item.confidence,
                    confidence_delta=delta,
                    source_report_id=report_id,
                    metadata={
                        "category": item.category.value,
                        "quality": item.quality.value,
                    },
                )
            )

        return events

    def _compare_hypotheses(
        self,
        tick: int,
        previous: Iterable[Hypothesis],
        current: Iterable[Hypothesis],
        report_id: str,
    ) -> list[TimelineEvent]:
        old_map = {
            item.hypothesis_type.value: item
            for item in previous
        }
        events: list[TimelineEvent] = []

        for item in current:
            key = item.hypothesis_type.value
            old = old_map.get(key)

            if old is None:
                events.append(
                    self._hypothesis_appeared(
                        tick,
                        item,
                        report_id,
                    )
                )
                continue

            delta = item.confidence - old.confidence
            if (
                abs(delta)
                >= self.config.hypothesis_confidence_delta
            ):
                event_type = (
                    TimelineEventType.HYPOTHESIS_CONFIDENCE_INCREASED
                    if delta > 0
                    else TimelineEventType.HYPOTHESIS_CONFIDENCE_DECREASED
                )
                events.append(
                    TimelineEvent(
                        tick=tick,
                        event_type=event_type,
                        title=(
                            f"Hypothesis confidence changed: "
                            f"{item.title}"
                        ),
                        description=(
                            "The evaluated confidence of a competing "
                            "hypothesis changed."
                        ),
                        entity_id=item.hypothesis_id,
                        entity_type="hypothesis",
                        previous_value=old.confidence,
                        current_value=item.confidence,
                        confidence_delta=delta,
                        source_report_id=report_id,
                        metadata={
                            "hypothesis_type": key,
                        },
                    )
                )

            if old.status is not item.status:
                events.append(
                    TimelineEvent(
                        tick=tick,
                        event_type=(
                            TimelineEventType.HYPOTHESIS_STATUS_CHANGED
                        ),
                        title=(
                            f"Hypothesis status changed: "
                            f"{item.title}"
                        ),
                        description=(
                            "The assessment state of a competing hypothesis "
                            "changed."
                        ),
                        entity_id=item.hypothesis_id,
                        entity_type="hypothesis",
                        previous_value=old.status.value,
                        current_value=item.status.value,
                        source_report_id=report_id,
                        metadata={
                            "hypothesis_type": key,
                        },
                    )
                )

        return events

    def _compare_unknowns(
        self,
        tick: int,
        previous: Iterable[UnknownQuestion],
        current: Iterable[UnknownQuestion],
        report_id: str,
    ) -> list[TimelineEvent]:
        old_map = {
            item.question_id: item
            for item in previous
        }
        events: list[TimelineEvent] = []

        for item in current:
            old = old_map.get(item.question_id)
            if old is None:
                events.append(
                    self._unknown_opened(
                        tick,
                        item,
                        report_id,
                    )
                )
                continue

            if old.status is item.status:
                continue

            event_type = (
                TimelineEventType.UNKNOWN_RESOLVED
                if item.status is UnknownStatus.RESOLVED
                else TimelineEventType.UNKNOWN_STATUS_CHANGED
            )
            events.append(
                TimelineEvent(
                    tick=tick,
                    event_type=event_type,
                    title=f"Unknown status changed: {item.title}",
                    description=(
                        "The lifecycle state of an explicit scientific "
                        "unknown changed."
                    ),
                    entity_id=item.question_id,
                    entity_type="unknown_question",
                    previous_value=old.status.value,
                    current_value=item.status.value,
                    source_report_id=report_id,
                    metadata={
                        "category": item.category.value,
                        "priority": item.priority,
                        "resolution_evidence_ids": (
                            item.resolution_evidence_ids
                        ),
                    },
                )
            )

        return events

    def _compare_conflicts(
        self,
        tick: int,
        previous: Iterable[EvidenceConflict],
        current: Iterable[EvidenceConflict],
        report_id: str,
    ) -> list[TimelineEvent]:
        old_map = {
            item.conflict_id: item
            for item in previous
        }
        events: list[TimelineEvent] = []

        for item in current:
            old = old_map.get(item.conflict_id)
            if old is None:
                events.append(
                    self._conflict_appeared(
                        tick,
                        item,
                        report_id,
                    )
                )
                continue

            if old.status is item.status:
                continue

            event_type = (
                TimelineEventType.CONFLICT_RESOLVED
                if item.status is ConflictStatus.RESOLVED
                else TimelineEventType.CONFLICT_STATUS_CHANGED
            )
            events.append(
                TimelineEvent(
                    tick=tick,
                    event_type=event_type,
                    title=f"Conflict status changed: {item.title}",
                    description=(
                        "The lifecycle state of an evidence conflict "
                        "changed."
                    ),
                    entity_id=item.conflict_id,
                    entity_type="evidence_conflict",
                    previous_value=old.status.value,
                    current_value=item.status.value,
                    source_report_id=report_id,
                    metadata={
                        "severity": item.severity,
                        "evidence_ids": item.evidence_ids,
                        "resolution_note": item.resolution_note,
                    },
                )
            )

        return events

    @staticmethod
    def _observation_appeared(
        tick: int,
        item: Observation,
        report_id: str,
    ) -> TimelineEvent:
        return TimelineEvent(
            tick=tick,
            event_type=TimelineEventType.OBSERVATION_APPEARED,
            title=f"Observation appeared: {item.name}",
            description=item.description,
            entity_id=item.observation_id,
            entity_type="observation",
            current_value=item.value,
            source_report_id=report_id,
            metadata={
                "sensor": item.sensor.value,
                "category": item.category.value,
                "confidence": item.confidence,
                "quality": item.quality.value,
                "object_id": item.object_id,
            },
        )

    @staticmethod
    def _evidence_appeared(
        tick: int,
        item: Evidence,
        report_id: str,
    ) -> TimelineEvent:
        return TimelineEvent(
            tick=tick,
            event_type=TimelineEventType.EVIDENCE_APPEARED,
            title=f"Evidence appeared: {item.title}",
            description=item.description,
            entity_id=item.evidence_id,
            entity_type="evidence",
            current_value=item.confidence,
            source_report_id=report_id,
            metadata={
                "category": item.category.value,
                "quality": item.quality.value,
                "observation_ids": item.observation_ids,
                "tags": item.tags,
            },
        )

    @staticmethod
    def _hypothesis_appeared(
        tick: int,
        item: Hypothesis,
        report_id: str,
    ) -> TimelineEvent:
        return TimelineEvent(
            tick=tick,
            event_type=TimelineEventType.HYPOTHESIS_APPEARED,
            title=f"Hypothesis appeared: {item.title}",
            description=item.description,
            entity_id=item.hypothesis_id,
            entity_type="hypothesis",
            current_value=item.confidence,
            source_report_id=report_id,
            metadata={
                "hypothesis_type": item.hypothesis_type.value,
                "status": item.status.value,
                "assessment_count": len(item.assessments),
            },
        )

    @staticmethod
    def _unknown_opened(
        tick: int,
        item: UnknownQuestion,
        report_id: str,
    ) -> TimelineEvent:
        return TimelineEvent(
            tick=tick,
            event_type=TimelineEventType.UNKNOWN_OPENED,
            title=f"Unknown recorded: {item.title}",
            description=item.description,
            entity_id=item.question_id,
            entity_type="unknown_question",
            current_value=item.status.value,
            source_report_id=report_id,
            metadata={
                "category": item.category.value,
                "priority": item.priority,
                "required_observation_names": (
                    item.required_observation_names
                ),
            },
        )

    @staticmethod
    def _conflict_appeared(
        tick: int,
        item: EvidenceConflict,
        report_id: str,
    ) -> TimelineEvent:
        return TimelineEvent(
            tick=tick,
            event_type=TimelineEventType.CONFLICT_APPEARED,
            title=f"Conflict appeared: {item.title}",
            description=item.description,
            entity_id=item.conflict_id,
            entity_type="evidence_conflict",
            current_value=item.status.value,
            source_report_id=report_id,
            metadata={
                "severity": item.severity,
                "evidence_ids": item.evidence_ids,
            },
        )

    @staticmethod
    def _validate_checkpoint_identity(
        checkpoints: Sequence[TimelineCheckpoint],
    ) -> None:
        world_ids = {
            item.report.world_id
            for item in checkpoints
        }
        run_ids = {
            item.report.run_id
            for item in checkpoints
        }
        ticks = [
            item.tick
            for item in checkpoints
        ]

        if len(world_ids) != 1:
            raise EvidenceTimelineError(
                "All checkpoints must belong to one world_id"
            )
        if len(run_ids) != 1:
            raise EvidenceTimelineError(
                "All checkpoints must belong to one run_id"
            )
        if len(set(ticks)) != len(ticks):
            raise EvidenceTimelineError(
                "Checkpoint ticks must be unique"
            )


def build_evidence_timeline(
    checkpoints: Sequence[TimelineCheckpoint],
    *,
    config: EvidenceTimelineConfig | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> EvidenceTimeline:
    """Convenience wrapper for EvidenceTimelineBuilder."""

    return EvidenceTimelineBuilder(config).build(
        checkpoints,
        metadata=metadata,
    )


def checkpoint_from_report(
    report: EvidenceReport,
    *,
    tick: int | None = None,
    label: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> TimelineCheckpoint:
    """Create a checkpoint using an explicit or report-derived tick.

    When ``tick`` is omitted, the maximum observation tick in the report is
    used.  Reports without observations require an explicit tick.
    """

    if not isinstance(report, EvidenceReport):
        raise EvidenceTimelineError(
            "report must be an EvidenceReport"
        )

    if tick is None:
        if not report.observations:
            raise EvidenceTimelineError(
                "tick is required when report has no observations"
            )
        tick = max(item.tick for item in report.observations)

    return TimelineCheckpoint(
        tick=tick,
        report=report,
        label=label,
        metadata=metadata or {},
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(
        value,
        (str, int, float, bool),
    ):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            _jsonable(item)
            for item in value
        ]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    return str(value)


__all__ = [
    "OBSERVER_EVIDENCE_TIMELINE_VERSION",
    "EvidenceTimelineError",
    "TimelineEventType",
    "TimelineCheckpoint",
    "TimelineEvent",
    "EvidenceTimeline",
    "EvidenceTimelineConfig",
    "EvidenceTimelineBuilder",
    "build_evidence_timeline",
    "checkpoint_from_report",
]
