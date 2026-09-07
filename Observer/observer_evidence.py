#!/usr/bin/env python3
"""Evidence collection and construction layer for Project ARCHON Observer.

This module is the first integration layer above ``evidence_models.py``. It
turns explicit sensor outputs into immutable Observation and Evidence objects,
keeps their provenance intact, and assembles a structurally valid draft
EvidenceReport.

It deliberately does NOT:
- classify life or emergence;
- rank competing hypotheses;
- calculate hypothesis confidence;
- invent thresholds for existing Observer sensors;
- inspect or import concrete Observer mixins.

Existing sensors may integrate gradually by calling ``EvidenceCollector``.
This keeps the current Observer operational while the evidence pipeline is
introduced one sensor at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

try:
    from .evidence_models import (
        Evidence,
        EvidenceCategory,
        EvidenceGroup,
        EvidenceModelError,
        EvidenceQuality,
        EvidenceReport,
        Observation,
        Provenance,
        SensorType,
    )
except ImportError:  # Direct execution from the Observer directory.
    from evidence_models import (
        Evidence,
        EvidenceCategory,
        EvidenceGroup,
        EvidenceModelError,
        EvidenceQuality,
        EvidenceReport,
        Observation,
        Provenance,
        SensorType,
    )


OBSERVER_EVIDENCE_VERSION = "1.0.0"


class EvidenceCollectionError(ValueError):
    """Raised when raw sensor output cannot be converted safely."""


@dataclass(frozen=True, slots=True)
class ObservationInput:
    """Typed input contract used by sensors before creating an Observation."""

    sensor: SensorType
    category: EvidenceCategory
    name: str
    value: Any
    confidence: float
    tick: int
    quality: EvidenceQuality = EvidenceQuality.UNKNOWN
    description: str = ""
    units: str | None = None
    object_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    algorithm: str = "direct_sensor_output"
    algorithm_version: str = "1.0.0"
    source_ids: tuple[str, ...] = ()
    provenance_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    """Typed input contract for a neutral interpretation of observations."""

    category: EvidenceCategory
    title: str
    description: str
    observation_ids: tuple[str, ...]
    confidence: float
    quality: EvidenceQuality = EvidenceQuality.UNKNOWN
    limitations: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    algorithm: str = "evidence_assembly"
    algorithm_version: str = "1.0.0"
    source_ids: tuple[str, ...] = ()
    provenance_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceGroupInput:
    """Typed input contract for a dependence or independence group."""

    name: str
    description: str
    evidence_ids: tuple[str, ...]
    independence_key: str
    category: EvidenceCategory | None = None


def _as_sensor(value: SensorType | str) -> SensorType:
    try:
        return value if isinstance(value, SensorType) else SensorType(str(value))
    except ValueError as exc:
        raise EvidenceCollectionError(f"Unknown sensor type: {value!r}") from exc


def _as_category(value: EvidenceCategory | str) -> EvidenceCategory:
    try:
        return value if isinstance(value, EvidenceCategory) else EvidenceCategory(str(value))
    except ValueError as exc:
        raise EvidenceCollectionError(f"Unknown evidence category: {value!r}") from exc


def _as_quality(value: EvidenceQuality | str | None) -> EvidenceQuality:
    if value is None:
        return EvidenceQuality.UNKNOWN
    try:
        return value if isinstance(value, EvidenceQuality) else EvidenceQuality(str(value))
    except ValueError as exc:
        raise EvidenceCollectionError(f"Unknown evidence quality: {value!r}") from exc


def observation_input_from_mapping(
    raw: Mapping[str, Any],
    *,
    default_sensor: SensorType | str | None = None,
    default_category: EvidenceCategory | str | None = None,
    default_tick: int | None = None,
    default_confidence: float = 1.0,
    default_quality: EvidenceQuality | str = EvidenceQuality.UNKNOWN,
) -> ObservationInput:
    """Convert one explicit sensor-output mapping into ObservationInput.

    Required values are ``name`` and ``value``. ``sensor``, ``category``, and
    ``tick`` may be supplied in the mapping or through defaults.

    This function intentionally performs no semantic inference. It will not
    guess that a field named ``symmetry`` belongs to morphology, nor assign
    confidence based on the value.
    """

    if not isinstance(raw, Mapping):
        raise EvidenceCollectionError("raw sensor output must be a mapping")

    sensor_value = raw.get("sensor", default_sensor)
    category_value = raw.get("category", default_category)
    tick_value = raw.get("tick", default_tick)

    if sensor_value is None:
        raise EvidenceCollectionError("sensor is required")
    if category_value is None:
        raise EvidenceCollectionError("category is required")
    if tick_value is None:
        raise EvidenceCollectionError("tick is required")
    if "name" not in raw:
        raise EvidenceCollectionError("name is required")
    if "value" not in raw:
        raise EvidenceCollectionError("value is required")

    details = raw.get("details") or {}
    provenance_metadata = raw.get("provenance_metadata") or {}
    if not isinstance(details, Mapping):
        raise EvidenceCollectionError("details must be a mapping")
    if not isinstance(provenance_metadata, Mapping):
        raise EvidenceCollectionError("provenance_metadata must be a mapping")

    return ObservationInput(
        sensor=_as_sensor(sensor_value),
        category=_as_category(category_value),
        name=str(raw["name"]),
        value=raw["value"],
        confidence=float(raw.get("confidence", default_confidence)),
        tick=int(tick_value),
        quality=_as_quality(raw.get("quality", default_quality)),
        description=str(raw.get("description", "")),
        units=str(raw["units"]) if raw.get("units") is not None else None,
        object_id=str(raw["object_id"]) if raw.get("object_id") is not None else None,
        details=dict(details),
        algorithm=str(raw.get("algorithm", "direct_sensor_output")),
        algorithm_version=str(raw.get("algorithm_version", "1.0.0")),
        source_ids=tuple(str(item) for item in (raw.get("source_ids") or ())),
        provenance_metadata=dict(provenance_metadata),
    )


class EvidenceCollector:
    """Mutable run-local builder for immutable evidence models.

    A collector belongs to exactly one world/run pair. Sensors add
    observations; evidence builders then reference those observations by ID.
    The collector rejects missing references and duplicate IDs before a report
    reaches disk.
    """

    def __init__(
        self,
        *,
        world_id: str,
        run_id: str,
        observer_version: str,
        module_name: str = "observer_evidence",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.world_id = str(world_id).strip()
        self.run_id = str(run_id).strip()
        self.observer_version = str(observer_version).strip()
        self.module_name = str(module_name).strip()
        self.metadata = dict(metadata or {})

        if not self.world_id:
            raise EvidenceCollectionError("world_id must not be empty")
        if not self.run_id:
            raise EvidenceCollectionError("run_id must not be empty")
        if not self.observer_version:
            raise EvidenceCollectionError("observer_version must not be empty")
        if not self.module_name:
            raise EvidenceCollectionError("module_name must not be empty")

        self._observations: dict[str, Observation] = {}
        self._evidence: dict[str, Evidence] = {}
        self._groups: dict[str, EvidenceGroup] = {}

    @property
    def observations(self) -> tuple[Observation, ...]:
        return tuple(self._observations.values())

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        return tuple(self._evidence.values())

    @property
    def groups(self) -> tuple[EvidenceGroup, ...]:
        return tuple(self._groups.values())

    def add_observation(self, item: ObservationInput) -> Observation:
        """Create, validate, and register one Observation."""

        provenance = Provenance(
            module=self.module_name,
            algorithm=item.algorithm,
            version=item.algorithm_version,
            source_ids=item.source_ids,
            metadata=item.provenance_metadata,
        )
        observation = Observation(
            sensor=item.sensor,
            category=item.category,
            name=item.name,
            value=item.value,
            confidence=item.confidence,
            tick=item.tick,
            quality=item.quality,
            description=item.description,
            units=item.units,
            world_id=self.world_id,
            run_id=self.run_id,
            object_id=item.object_id,
            details=item.details,
            provenance=provenance,
        )
        self._register_unique(
            self._observations,
            observation.observation_id,
            observation,
            "observation",
        )
        return observation

    def add_observation_mapping(
        self,
        raw: Mapping[str, Any],
        **defaults: Any,
    ) -> Observation:
        """Convert a mapping through the explicit adapter and register it."""

        return self.add_observation(observation_input_from_mapping(raw, **defaults))

    def add_observations(
        self,
        items: Iterable[ObservationInput],
    ) -> tuple[Observation, ...]:
        return tuple(self.add_observation(item) for item in items)

    def add_evidence(self, item: EvidenceInput) -> Evidence:
        """Create neutral Evidence referencing registered observations."""

        missing = [
            observation_id
            for observation_id in item.observation_ids
            if observation_id not in self._observations
        ]
        if missing:
            raise EvidenceCollectionError(
                "Evidence references unknown observation IDs: " + ", ".join(missing)
            )

        source_ids = item.source_ids or item.observation_ids
        provenance = Provenance(
            module=self.module_name,
            algorithm=item.algorithm,
            version=item.algorithm_version,
            source_ids=source_ids,
            metadata=item.provenance_metadata,
        )
        evidence = Evidence(
            category=item.category,
            title=item.title,
            description=item.description,
            observation_ids=item.observation_ids,
            confidence=item.confidence,
            quality=item.quality,
            limitations=item.limitations,
            tags=item.tags,
            provenance=provenance,
        )
        self._register_unique(
            self._evidence,
            evidence.evidence_id,
            evidence,
            "evidence",
        )
        return evidence

    def add_group(self, item: EvidenceGroupInput) -> EvidenceGroup:
        """Create a group used later to control correlated evidence."""

        missing = [
            evidence_id
            for evidence_id in item.evidence_ids
            if evidence_id not in self._evidence
        ]
        if missing:
            raise EvidenceCollectionError(
                "EvidenceGroup references unknown evidence IDs: " + ", ".join(missing)
            )

        group = EvidenceGroup(
            name=item.name,
            description=item.description,
            evidence_ids=item.evidence_ids,
            independence_key=item.independence_key,
            category=item.category,
        )
        self._register_unique(self._groups, group.group_id, group, "group")
        return group

    def build_report(
        self,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> EvidenceReport:
        """Build a valid pre-hypothesis EvidenceReport.

        Hypotheses, conflicts, and unknown questions are intentionally empty.
        Their engines will enrich this report in later stages.
        """

        merged_metadata = dict(self.metadata)
        merged_metadata.update(metadata or {})
        merged_metadata.setdefault(
            "evidence_collector_version",
            OBSERVER_EVIDENCE_VERSION,
        )
        merged_metadata.setdefault("pipeline_stage", "evidence_collection")

        try:
            return EvidenceReport(
                world_id=self.world_id,
                run_id=self.run_id,
                observer_version=self.observer_version,
                observations=self.observations,
                evidence=self.evidence,
                groups=self.groups,
                hypotheses=(),
                conflicts=(),
                unknowns=(),
                leading_hypothesis_id=None,
                metadata=merged_metadata,
            )
        except EvidenceModelError as exc:
            raise EvidenceCollectionError(
                f"Could not build EvidenceReport: {exc}"
            ) from exc

    def clear(self) -> None:
        """Clear run-local content while preserving collector identity."""

        self._observations.clear()
        self._evidence.clear()
        self._groups.clear()

    @staticmethod
    def _register_unique(
        registry: dict[str, Any],
        item_id: str,
        item: Any,
        kind: str,
    ) -> None:
        if item_id in registry:
            raise EvidenceCollectionError(f"Duplicate {kind} ID: {item_id}")
        registry[item_id] = item


def collect_explicit_sensor_outputs(
    raw_items: Sequence[Mapping[str, Any]],
    *,
    world_id: str,
    run_id: str,
    observer_version: str,
    default_sensor: SensorType | str | None = None,
    default_category: EvidenceCategory | str | None = None,
    default_tick: int | None = None,
    module_name: str = "observer_evidence",
    metadata: Mapping[str, Any] | None = None,
) -> tuple[EvidenceCollector, tuple[Observation, ...]]:
    """Convenience adapter for a batch of already-labelled sensor outputs.

    This is intended for incremental migration of existing Observer modules.
    Each mapping must still state its scientific meaning explicitly. The
    adapter does not infer categories or create Evidence automatically.
    """

    collector = EvidenceCollector(
        world_id=world_id,
        run_id=run_id,
        observer_version=observer_version,
        module_name=module_name,
        metadata=metadata,
    )
    observations = tuple(
        collector.add_observation_mapping(
            raw,
            default_sensor=default_sensor,
            default_category=default_category,
            default_tick=default_tick,
        )
        for raw in raw_items
    )
    return collector, observations


__all__ = [
    "OBSERVER_EVIDENCE_VERSION",
    "EvidenceCollectionError",
    "ObservationInput",
    "EvidenceInput",
    "EvidenceGroupInput",
    "EvidenceCollector",
    "observation_input_from_mapping",
    "collect_explicit_sensor_outputs",
]
