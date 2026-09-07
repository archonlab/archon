#!/usr/bin/env python3
"""Canonical evidence data models for Project ARCHON Observer.

This module defines the shared language used by the Observer evidence pipeline:

    sensor output -> Observation -> Evidence -> HypothesisAssessment
    -> Hypothesis -> EvidenceReport

The models are intentionally domain-neutral and contain no scoring formulas,
thresholds, life-detection logic, or imports from other ARCHON modules.  Their
job is to preserve traceability, immutability, serialization, and structural
integrity between Observer components.

Design rules
------------
1. Observations record measurements; they do not declare conclusions.
2. Evidence groups observations into a scientifically meaningful claim.
3. Evidence remains neutral until assessed against a hypothesis.
4. HypothesisAssessment stores support or contradiction for one hypothesis.
5. Every derived object refers back to source IDs, preserving provenance.
6. EvidenceReport validates references but does not decide which hypothesis
   should win.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar, Iterable, Mapping, TypeVar
from uuid import uuid4


EVIDENCE_MODELS_VERSION = "1.0.0"
EVIDENCE_REPORT_SCHEMA = "archon.observer.evidence-report"
EVIDENCE_REPORT_SCHEMA_VERSION = "1.0.0"


class EvidenceModelError(ValueError):
    """Raised when an evidence model violates its structural contract."""


class _StringEnum(str, Enum):
    """Enum whose members serialize naturally as stable lowercase strings."""

    def __str__(self) -> str:
        return self.value


class SensorType(_StringEnum):
    """Observer subsystem that produced an observation."""

    IDENTITY = "identity"
    MORPHOLOGY = "morphology"
    GEOMETRY = "geometry"
    ECOLOGY = "ecology"
    ECOSYSTEM = "ecosystem"
    MEMORY = "memory"
    NETWORK = "network"
    DYNAMICS = "dynamics"
    LINEAGE = "lineage"
    EVOLUTION = "evolution"
    CHRONICLE = "chronicle"
    CIVILIZATION = "civilization"
    INSTITUTIONS = "institutions"
    EMERGENCE = "emergence"
    VALIDATION = "validation"
    LIFE_EVIDENCE = "life_evidence"
    SCIENTIFIC = "scientific"
    OTHER = "other"


class EvidenceCategory(_StringEnum):
    """Scientific domain described by an observation or evidence item."""

    BOUNDED_ORGANIZATION = "bounded_organization"
    IDENTITY = "identity"
    STABILITY = "stability"
    REPAIR = "repair"
    MEMORY = "memory"
    REPRODUCTION = "reproduction"
    ADAPTATION = "adaptation"
    COMMUNICATION = "communication"
    RESOURCE_USAGE = "resource_usage"
    INFORMATION = "information"
    MORPHOLOGY = "morphology"
    ECOLOGY = "ecology"
    NETWORK = "network"
    DYNAMICS = "dynamics"
    EVOLUTION = "evolution"
    VALIDATION = "validation"
    OTHER = "other"


class EvidenceQuality(_StringEnum):
    """Qualitative data-quality label independent of hypothesis support."""

    UNKNOWN = "unknown"
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class HypothesisType(_StringEnum):
    """Canonical competing explanations used by Observer life evidence."""

    PASSIVE_OSCILLATION = "passive_oscillation"
    STABLE_ATTRACTOR = "stable_attractor"
    CRYSTAL_DYNAMICS = "crystal_dynamics"
    ACTIVE_STRUCTURE = "active_structure"
    ADAPTIVE_ORGANIZATION = "adaptive_organization"
    LIFE_CANDIDATE = "life_candidate"
    CUSTOM = "custom"


class HypothesisStatus(_StringEnum):
    """Assessment state assigned by a hypothesis engine."""

    UNASSESSED = "unassessed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PLAUSIBLE = "plausible"
    LEADING = "leading"
    DISFAVORED = "disfavored"
    REJECTED = "rejected"


class EvidenceRelation(_StringEnum):
    """How one evidence item relates to one hypothesis."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class UnknownStatus(_StringEnum):
    """Lifecycle state of an explicitly recorded unknown question."""

    OPEN = "open"
    PARTIAL = "partial"
    RESOLVED = "resolved"
    NOT_TESTABLE = "not_testable"


class ConflictStatus(_StringEnum):
    """Lifecycle state of a conflict between evidence items."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


EnumT = TypeVar("EnumT", bound=Enum)


def _new_id(prefix: str) -> str:
    """Return a collision-resistant, readable identifier."""

    return f"{prefix}-{uuid4().hex}"


def _utc_now_iso() -> str:
    """Return an RFC 3339 UTC timestamp with second precision."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_non_empty(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise EvidenceModelError(f"{field_name} must be a non-empty string")
    return normalized


def _require_probability(value: float, field_name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceModelError(f"{field_name} must be a number in [0, 1]") from exc
    if not 0.0 <= numeric <= 1.0:
        raise EvidenceModelError(f"{field_name} must be in [0, 1], got {numeric!r}")
    return numeric


def _require_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool):
        raise EvidenceModelError(f"{field_name} must be a non-negative integer")
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceModelError(f"{field_name} must be a non-negative integer") from exc
    if numeric < 0 or numeric != value:
        raise EvidenceModelError(f"{field_name} must be a non-negative integer")
    return numeric


def _enum_from_value(enum_type: type[EnumT], value: EnumT | str) -> EnumT:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value))
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise EvidenceModelError(
            f"invalid {enum_type.__name__} value {value!r}; allowed: {allowed}"
        ) from exc


def _as_tuple(values: Iterable[Any] | None) -> tuple[Any, ...]:
    if values is None:
        return ()
    if isinstance(values, tuple):
        return values
    if isinstance(values, (str, bytes)):
        raise EvidenceModelError("expected an iterable of values, not a string")
    return tuple(values)


def _freeze(value: Any) -> Any:
    """Recursively freeze JSON-like containers used inside frozen models."""

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(_freeze(item) for item in sorted(value, key=repr))
    return value


def _to_primitive(value: Any) -> Any:
    """Convert models, enums, and frozen containers to JSON-compatible data."""

    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: _to_primitive(getattr(value, item.name))
            for item in fields(value)
            if not item.name.startswith("_")
        }
    if isinstance(value, Mapping):
        return {str(key): _to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_to_primitive(item) for item in value]
    return value


def _ensure_unique_ids(items: Iterable[Any], attribute: str, label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        identifier = str(getattr(item, attribute))
        if identifier in seen:
            duplicates.add(identifier)
        seen.add(identifier)
    if duplicates:
        joined = ", ".join(sorted(duplicates))
        raise EvidenceModelError(f"duplicate {label} IDs: {joined}")


class JsonModel:
    """Small serialization mixin shared by all evidence models."""

    def to_dict(self) -> dict[str, Any]:
        return _to_primitive(self)

    def to_json(self, *, indent: int | None = 2, sort_keys: bool = True) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=sort_keys,
        )


@dataclass(frozen=True, slots=True)
class Provenance(JsonModel):
    """Origin of a measurement or derived evidence item.

    ``source_ids`` links this object to upstream observations, evidence,
    snapshots, files, or events. ``metadata`` may contain additional
    JSON-compatible reproducibility information such as parameters or hashes.
    """

    module: str
    algorithm: str
    version: str
    source_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "module", _require_non_empty(self.module, "module"))
        object.__setattr__(self, "algorithm", _require_non_empty(self.algorithm, "algorithm"))
        object.__setattr__(self, "version", _require_non_empty(self.version, "version"))
        object.__setattr__(
            self,
            "source_ids",
            tuple(_require_non_empty(item, "source_id") for item in _as_tuple(self.source_ids)),
        )
        object.__setattr__(self, "metadata", _freeze(self.metadata))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Provenance":
        return cls(
            module=data["module"],
            algorithm=data["algorithm"],
            version=data["version"],
            source_ids=tuple(data.get("source_ids") or ()),
            metadata=data.get("metadata") or {},
        )


@dataclass(frozen=True, slots=True)
class Observation(JsonModel):
    """One direct Observer measurement without a high-level conclusion."""

    sensor: SensorType
    category: EvidenceCategory
    name: str
    value: Any
    confidence: float
    tick: int
    quality: EvidenceQuality = EvidenceQuality.UNKNOWN
    description: str = ""
    units: str | None = None
    world_id: str | None = None
    run_id: str | None = None
    object_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    provenance: Provenance | None = None
    observation_id: str = field(default_factory=lambda: _new_id("OBS"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "sensor", _enum_from_value(SensorType, self.sensor))
        object.__setattr__(self, "category", _enum_from_value(EvidenceCategory, self.category))
        object.__setattr__(self, "quality", _enum_from_value(EvidenceQuality, self.quality))
        object.__setattr__(self, "name", _require_non_empty(self.name, "name"))
        object.__setattr__(self, "confidence", _require_probability(self.confidence, "confidence"))
        object.__setattr__(self, "tick", _require_non_negative_int(self.tick, "tick"))
        object.__setattr__(self, "observation_id", _require_non_empty(self.observation_id, "observation_id"))
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(self, "units", str(self.units).strip() if self.units is not None else None)
        object.__setattr__(self, "world_id", str(self.world_id).strip() if self.world_id is not None else None)
        object.__setattr__(self, "run_id", str(self.run_id).strip() if self.run_id is not None else None)
        object.__setattr__(self, "object_id", str(self.object_id).strip() if self.object_id is not None else None)
        object.__setattr__(self, "value", _freeze(self.value))
        object.__setattr__(self, "details", _freeze(self.details))
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise EvidenceModelError("provenance must be Provenance or None")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Observation":
        provenance_data = data.get("provenance")
        return cls(
            sensor=_enum_from_value(SensorType, data["sensor"]),
            category=_enum_from_value(EvidenceCategory, data["category"]),
            name=data["name"],
            value=data.get("value"),
            confidence=data["confidence"],
            tick=data["tick"],
            quality=_enum_from_value(EvidenceQuality, data.get("quality", "unknown")),
            description=data.get("description", ""),
            units=data.get("units"),
            world_id=data.get("world_id"),
            run_id=data.get("run_id"),
            object_id=data.get("object_id"),
            details=data.get("details") or {},
            provenance=Provenance.from_dict(provenance_data) if provenance_data else None,
            observation_id=data.get("observation_id") or _new_id("OBS"),
        )


@dataclass(frozen=True, slots=True)
class Evidence(JsonModel):
    """Neutral interpretation derived from one or more observations.

    Evidence deliberately contains no hypothesis-specific support score.  The
    same evidence can support one hypothesis, contradict another, and remain
    neutral toward a third.  Those relations belong in HypothesisAssessment.
    """

    category: EvidenceCategory
    title: str
    description: str
    observation_ids: tuple[str, ...]
    confidence: float
    quality: EvidenceQuality = EvidenceQuality.UNKNOWN
    limitations: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    provenance: Provenance | None = None
    evidence_id: str = field(default_factory=lambda: _new_id("EVD"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", _enum_from_value(EvidenceCategory, self.category))
        object.__setattr__(self, "quality", _enum_from_value(EvidenceQuality, self.quality))
        object.__setattr__(self, "title", _require_non_empty(self.title, "title"))
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(self, "confidence", _require_probability(self.confidence, "confidence"))
        object.__setattr__(self, "evidence_id", _require_non_empty(self.evidence_id, "evidence_id"))
        observation_ids = tuple(
            _require_non_empty(item, "observation_id")
            for item in _as_tuple(self.observation_ids)
        )
        if not observation_ids:
            raise EvidenceModelError("Evidence must reference at least one observation")
        if len(set(observation_ids)) != len(observation_ids):
            raise EvidenceModelError("Evidence observation_ids must be unique")
        object.__setattr__(self, "observation_ids", observation_ids)
        object.__setattr__(
            self,
            "limitations",
            tuple(str(item).strip() for item in _as_tuple(self.limitations) if str(item).strip()),
        )
        object.__setattr__(
            self,
            "tags",
            tuple(str(item).strip() for item in _as_tuple(self.tags) if str(item).strip()),
        )
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise EvidenceModelError("provenance must be Provenance or None")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Evidence":
        provenance_data = data.get("provenance")
        return cls(
            category=_enum_from_value(EvidenceCategory, data["category"]),
            title=data["title"],
            description=data.get("description", ""),
            observation_ids=tuple(data.get("observation_ids") or ()),
            confidence=data["confidence"],
            quality=_enum_from_value(EvidenceQuality, data.get("quality", "unknown")),
            limitations=tuple(data.get("limitations") or ()),
            tags=tuple(data.get("tags") or ()),
            provenance=Provenance.from_dict(provenance_data) if provenance_data else None,
            evidence_id=data.get("evidence_id") or _new_id("EVD"),
        )


@dataclass(frozen=True, slots=True)
class EvidenceGroup(JsonModel):
    """Dependence group used to avoid double-counting correlated evidence."""

    name: str
    description: str
    evidence_ids: tuple[str, ...]
    independence_key: str
    category: EvidenceCategory | None = None
    group_id: str = field(default_factory=lambda: _new_id("GRP"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_non_empty(self.name, "name"))
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(
            self,
            "independence_key",
            _require_non_empty(self.independence_key, "independence_key"),
        )
        object.__setattr__(self, "group_id", _require_non_empty(self.group_id, "group_id"))
        if self.category is not None:
            object.__setattr__(self, "category", _enum_from_value(EvidenceCategory, self.category))
        evidence_ids = tuple(
            _require_non_empty(item, "evidence_id") for item in _as_tuple(self.evidence_ids)
        )
        if not evidence_ids:
            raise EvidenceModelError("EvidenceGroup must reference at least one evidence item")
        if len(set(evidence_ids)) != len(evidence_ids):
            raise EvidenceModelError("EvidenceGroup evidence_ids must be unique")
        object.__setattr__(self, "evidence_ids", evidence_ids)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceGroup":
        category = data.get("category")
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            evidence_ids=tuple(data.get("evidence_ids") or ()),
            independence_key=data["independence_key"],
            category=_enum_from_value(EvidenceCategory, category) if category else None,
            group_id=data.get("group_id") or _new_id("GRP"),
        )


@dataclass(frozen=True, slots=True)
class HypothesisAssessment(JsonModel):
    """Hypothesis-specific interpretation of one neutral evidence item."""

    evidence_id: str
    relation: EvidenceRelation
    weight: float
    confidence: float
    rationale: str
    group_id: str | None = None
    provenance: Provenance | None = None
    assessment_id: str = field(default_factory=lambda: _new_id("ASM"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _require_non_empty(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "relation", _enum_from_value(EvidenceRelation, self.relation))
        object.__setattr__(self, "weight", _require_probability(self.weight, "weight"))
        object.__setattr__(self, "confidence", _require_probability(self.confidence, "confidence"))
        object.__setattr__(self, "rationale", _require_non_empty(self.rationale, "rationale"))
        object.__setattr__(self, "assessment_id", _require_non_empty(self.assessment_id, "assessment_id"))
        object.__setattr__(self, "group_id", str(self.group_id).strip() if self.group_id is not None else None)
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise EvidenceModelError("provenance must be Provenance or None")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisAssessment":
        provenance_data = data.get("provenance")
        return cls(
            evidence_id=data["evidence_id"],
            relation=_enum_from_value(EvidenceRelation, data["relation"]),
            weight=data["weight"],
            confidence=data["confidence"],
            rationale=data["rationale"],
            group_id=data.get("group_id"),
            provenance=Provenance.from_dict(provenance_data) if provenance_data else None,
            assessment_id=data.get("assessment_id") or _new_id("ASM"),
        )


@dataclass(frozen=True, slots=True)
class UnknownQuestion(JsonModel):
    """An explicit gap in current evidence that may motivate an experiment."""

    category: EvidenceCategory
    title: str
    description: str
    priority: float
    required_observation_names: tuple[str, ...] = ()
    status: UnknownStatus = UnknownStatus.OPEN
    resolution_evidence_ids: tuple[str, ...] = ()
    question_id: str = field(default_factory=lambda: _new_id("UNK"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", _enum_from_value(EvidenceCategory, self.category))
        object.__setattr__(self, "title", _require_non_empty(self.title, "title"))
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(self, "priority", _require_probability(self.priority, "priority"))
        object.__setattr__(self, "status", _enum_from_value(UnknownStatus, self.status))
        object.__setattr__(self, "question_id", _require_non_empty(self.question_id, "question_id"))
        object.__setattr__(
            self,
            "required_observation_names",
            tuple(
                _require_non_empty(item, "required_observation_name")
                for item in _as_tuple(self.required_observation_names)
            ),
        )
        object.__setattr__(
            self,
            "resolution_evidence_ids",
            tuple(
                _require_non_empty(item, "resolution_evidence_id")
                for item in _as_tuple(self.resolution_evidence_ids)
            ),
        )
        if self.status is UnknownStatus.RESOLVED and not self.resolution_evidence_ids:
            raise EvidenceModelError(
                "resolved UnknownQuestion must reference resolution_evidence_ids"
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UnknownQuestion":
        return cls(
            category=_enum_from_value(EvidenceCategory, data["category"]),
            title=data["title"],
            description=data.get("description", ""),
            priority=data["priority"],
            required_observation_names=tuple(data.get("required_observation_names") or ()),
            status=_enum_from_value(UnknownStatus, data.get("status", "open")),
            resolution_evidence_ids=tuple(data.get("resolution_evidence_ids") or ()),
            question_id=data.get("question_id") or _new_id("UNK"),
        )


@dataclass(frozen=True, slots=True)
class EvidenceConflict(JsonModel):
    """Recorded incompatibility between two or more evidence items."""

    title: str
    description: str
    evidence_ids: tuple[str, ...]
    severity: float
    status: ConflictStatus = ConflictStatus.OPEN
    resolution_note: str = ""
    conflict_id: str = field(default_factory=lambda: _new_id("CNF"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _require_non_empty(self.title, "title"))
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(self, "severity", _require_probability(self.severity, "severity"))
        object.__setattr__(self, "status", _enum_from_value(ConflictStatus, self.status))
        object.__setattr__(self, "resolution_note", str(self.resolution_note).strip())
        object.__setattr__(self, "conflict_id", _require_non_empty(self.conflict_id, "conflict_id"))
        evidence_ids = tuple(
            _require_non_empty(item, "evidence_id") for item in _as_tuple(self.evidence_ids)
        )
        if len(evidence_ids) < 2:
            raise EvidenceModelError("EvidenceConflict must reference at least two evidence items")
        if len(set(evidence_ids)) != len(evidence_ids):
            raise EvidenceModelError("EvidenceConflict evidence_ids must be unique")
        object.__setattr__(self, "evidence_ids", evidence_ids)
        if self.status is ConflictStatus.RESOLVED and not self.resolution_note:
            raise EvidenceModelError("resolved EvidenceConflict requires resolution_note")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceConflict":
        return cls(
            title=data["title"],
            description=data.get("description", ""),
            evidence_ids=tuple(data.get("evidence_ids") or ()),
            severity=data["severity"],
            status=_enum_from_value(ConflictStatus, data.get("status", "open")),
            resolution_note=data.get("resolution_note", ""),
            conflict_id=data.get("conflict_id") or _new_id("CNF"),
        )


@dataclass(frozen=True, slots=True)
class Hypothesis(JsonModel):
    """One competing explanatory model and its traceable assessments."""

    hypothesis_type: HypothesisType
    title: str
    description: str
    assessments: tuple[HypothesisAssessment, ...]
    confidence: float
    status: HypothesisStatus = HypothesisStatus.UNASSESSED
    unknown_question_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    hypothesis_id: str = field(default_factory=lambda: _new_id("HYP"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypothesis_type", _enum_from_value(HypothesisType, self.hypothesis_type))
        object.__setattr__(self, "status", _enum_from_value(HypothesisStatus, self.status))
        object.__setattr__(self, "title", _require_non_empty(self.title, "title"))
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(self, "confidence", _require_probability(self.confidence, "confidence"))
        object.__setattr__(self, "hypothesis_id", _require_non_empty(self.hypothesis_id, "hypothesis_id"))
        assessments = _as_tuple(self.assessments)
        if not all(isinstance(item, HypothesisAssessment) for item in assessments):
            raise EvidenceModelError("assessments must contain HypothesisAssessment objects")
        _ensure_unique_ids(assessments, "assessment_id", "assessment")
        object.__setattr__(self, "assessments", assessments)
        object.__setattr__(
            self,
            "unknown_question_ids",
            tuple(
                _require_non_empty(item, "unknown_question_id")
                for item in _as_tuple(self.unknown_question_ids)
            ),
        )
        object.__setattr__(
            self,
            "notes",
            tuple(str(item).strip() for item in _as_tuple(self.notes) if str(item).strip()),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Hypothesis":
        return cls(
            hypothesis_type=_enum_from_value(HypothesisType, data["hypothesis_type"]),
            title=data["title"],
            description=data.get("description", ""),
            assessments=tuple(
                HypothesisAssessment.from_dict(item)
                for item in data.get("assessments") or ()
            ),
            confidence=data["confidence"],
            status=_enum_from_value(HypothesisStatus, data.get("status", "unassessed")),
            unknown_question_ids=tuple(data.get("unknown_question_ids") or ()),
            notes=tuple(data.get("notes") or ()),
            hypothesis_id=data.get("hypothesis_id") or _new_id("HYP"),
        )


@dataclass(frozen=True, slots=True)
class EvidenceReport(JsonModel):
    """Complete, self-validating evidence package for one Observer run."""

    world_id: str
    run_id: str
    observer_version: str
    observations: tuple[Observation, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    groups: tuple[EvidenceGroup, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    conflicts: tuple[EvidenceConflict, ...] = ()
    unknowns: tuple[UnknownQuestion, ...] = ()
    leading_hypothesis_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    report_id: str = field(default_factory=lambda: _new_id("RPT"))
    generated_at: str = field(default_factory=_utc_now_iso)
    schema: str = EVIDENCE_REPORT_SCHEMA
    schema_version: str = EVIDENCE_REPORT_SCHEMA_VERSION

    MODEL_VERSION: ClassVar[str] = EVIDENCE_MODELS_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_id", _require_non_empty(self.world_id, "world_id"))
        object.__setattr__(self, "run_id", _require_non_empty(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "observer_version",
            _require_non_empty(self.observer_version, "observer_version"),
        )
        object.__setattr__(self, "report_id", _require_non_empty(self.report_id, "report_id"))
        object.__setattr__(self, "generated_at", _require_non_empty(self.generated_at, "generated_at"))
        object.__setattr__(self, "schema", _require_non_empty(self.schema, "schema"))
        object.__setattr__(self, "schema_version", _require_non_empty(self.schema_version, "schema_version"))
        object.__setattr__(self, "metadata", _freeze(self.metadata))

        observations = _as_tuple(self.observations)
        evidence = _as_tuple(self.evidence)
        groups = _as_tuple(self.groups)
        hypotheses = _as_tuple(self.hypotheses)
        conflicts = _as_tuple(self.conflicts)
        unknowns = _as_tuple(self.unknowns)

        expected_types = (
            (observations, Observation, "observations"),
            (evidence, Evidence, "evidence"),
            (groups, EvidenceGroup, "groups"),
            (hypotheses, Hypothesis, "hypotheses"),
            (conflicts, EvidenceConflict, "conflicts"),
            (unknowns, UnknownQuestion, "unknowns"),
        )
        for collection, expected_type, field_name in expected_types:
            if not all(isinstance(item, expected_type) for item in collection):
                raise EvidenceModelError(
                    f"{field_name} must contain only {expected_type.__name__} objects"
                )

        _ensure_unique_ids(observations, "observation_id", "observation")
        _ensure_unique_ids(evidence, "evidence_id", "evidence")
        _ensure_unique_ids(groups, "group_id", "group")
        _ensure_unique_ids(hypotheses, "hypothesis_id", "hypothesis")
        _ensure_unique_ids(conflicts, "conflict_id", "conflict")
        _ensure_unique_ids(unknowns, "question_id", "unknown-question")

        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "groups", groups)
        object.__setattr__(self, "hypotheses", hypotheses)
        object.__setattr__(self, "conflicts", conflicts)
        object.__setattr__(self, "unknowns", unknowns)

        self._validate_references()

    def _validate_references(self) -> None:
        observation_ids = {item.observation_id for item in self.observations}
        evidence_ids = {item.evidence_id for item in self.evidence}
        group_ids = {item.group_id for item in self.groups}
        hypothesis_ids = {item.hypothesis_id for item in self.hypotheses}
        unknown_ids = {item.question_id for item in self.unknowns}

        for item in self.evidence:
            missing = set(item.observation_ids) - observation_ids
            if missing:
                raise EvidenceModelError(
                    f"Evidence {item.evidence_id} references missing observations: "
                    + ", ".join(sorted(missing))
                )

        for group in self.groups:
            missing = set(group.evidence_ids) - evidence_ids
            if missing:
                raise EvidenceModelError(
                    f"EvidenceGroup {group.group_id} references missing evidence: "
                    + ", ".join(sorted(missing))
                )

        for hypothesis in self.hypotheses:
            for assessment in hypothesis.assessments:
                if assessment.evidence_id not in evidence_ids:
                    raise EvidenceModelError(
                        f"Hypothesis {hypothesis.hypothesis_id} assessment references "
                        f"missing evidence {assessment.evidence_id}"
                    )
                if assessment.group_id is not None and assessment.group_id not in group_ids:
                    raise EvidenceModelError(
                        f"Hypothesis {hypothesis.hypothesis_id} assessment references "
                        f"missing group {assessment.group_id}"
                    )
            missing_unknowns = set(hypothesis.unknown_question_ids) - unknown_ids
            if missing_unknowns:
                raise EvidenceModelError(
                    f"Hypothesis {hypothesis.hypothesis_id} references missing unknowns: "
                    + ", ".join(sorted(missing_unknowns))
                )

        for conflict in self.conflicts:
            missing = set(conflict.evidence_ids) - evidence_ids
            if missing:
                raise EvidenceModelError(
                    f"EvidenceConflict {conflict.conflict_id} references missing evidence: "
                    + ", ".join(sorted(missing))
                )

        for question in self.unknowns:
            missing = set(question.resolution_evidence_ids) - evidence_ids
            if missing:
                raise EvidenceModelError(
                    f"UnknownQuestion {question.question_id} references missing resolution evidence: "
                    + ", ".join(sorted(missing))
                )

        if self.leading_hypothesis_id is not None:
            leading_id = _require_non_empty(
                self.leading_hypothesis_id,
                "leading_hypothesis_id",
            )
            if leading_id not in hypothesis_ids:
                raise EvidenceModelError(
                    f"leading_hypothesis_id references missing hypothesis {leading_id}"
                )
            object.__setattr__(self, "leading_hypothesis_id", leading_id)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceReport":
        return cls(
            world_id=data["world_id"],
            run_id=data["run_id"],
            observer_version=data["observer_version"],
            observations=tuple(
                Observation.from_dict(item) for item in data.get("observations") or ()
            ),
            evidence=tuple(
                Evidence.from_dict(item) for item in data.get("evidence") or ()
            ),
            groups=tuple(
                EvidenceGroup.from_dict(item) for item in data.get("groups") or ()
            ),
            hypotheses=tuple(
                Hypothesis.from_dict(item) for item in data.get("hypotheses") or ()
            ),
            conflicts=tuple(
                EvidenceConflict.from_dict(item) for item in data.get("conflicts") or ()
            ),
            unknowns=tuple(
                UnknownQuestion.from_dict(item) for item in data.get("unknowns") or ()
            ),
            leading_hypothesis_id=data.get("leading_hypothesis_id"),
            metadata=data.get("metadata") or {},
            report_id=data.get("report_id") or _new_id("RPT"),
            generated_at=data.get("generated_at") or _utc_now_iso(),
            schema=data.get("schema") or EVIDENCE_REPORT_SCHEMA,
            schema_version=data.get("schema_version") or EVIDENCE_REPORT_SCHEMA_VERSION,
        )

    @classmethod
    def from_json(cls, payload: str | bytes | bytearray) -> "EvidenceReport":
        data = json.loads(payload)
        if not isinstance(data, Mapping):
            raise EvidenceModelError("EvidenceReport JSON root must be an object")
        return cls.from_dict(data)


__all__ = [
    "EVIDENCE_MODELS_VERSION",
    "EVIDENCE_REPORT_SCHEMA",
    "EVIDENCE_REPORT_SCHEMA_VERSION",
    "EvidenceModelError",
    "SensorType",
    "EvidenceCategory",
    "EvidenceQuality",
    "HypothesisType",
    "HypothesisStatus",
    "EvidenceRelation",
    "UnknownStatus",
    "ConflictStatus",
    "Provenance",
    "Observation",
    "Evidence",
    "EvidenceGroup",
    "HypothesisAssessment",
    "UnknownQuestion",
    "EvidenceConflict",
    "Hypothesis",
    "EvidenceReport",
]
