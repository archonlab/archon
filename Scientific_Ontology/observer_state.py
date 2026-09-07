"""Versioned scientific state contract shared by ARCHON modules.

Stage 1A introduces this contract without replacing legacy Observer fields.
Adapters may populate it alongside existing outputs.  No classifier logic or
thresholds belong in this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from .ecological_states import EcologyState, PopulationState
from .event_types import (
    BirthType,
    CollapseType,
    EventScope,
    ExtinctionType,
    OntologyEvent,
)
from .life_states import LifeEvidenceStatus, LifeState, parse_life_state
from .structural_states import StructuralState, parse_structural_state

SCHEMA_VERSION = "1.0.0"


def _bounded(value: float | None, name: str) -> None:
    if value is not None and not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {f.name: _jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return value


@dataclass(frozen=True, slots=True)
class LifeAssessment:
    state: LifeState = LifeState.UNKNOWN
    status: LifeEvidenceStatus = LifeEvidenceStatus.NOT_EVALUATED
    score: float | None = None
    confidence: float | None = None
    uncertainty: float | None = None
    winner: str | None = None
    runner_up: str | None = None
    margin: float | None = None
    gate_passed: bool | None = None
    axes: Mapping[str, float] = field(default_factory=dict)
    hypotheses: Mapping[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _bounded(self.score, "life.score")
        _bounded(self.confidence, "life.confidence")
        _bounded(self.uncertainty, "life.uncertainty")
        _bounded(self.margin, "life.margin")
        for name, value in self.axes.items():
            _bounded(float(value), f"life.axes[{name!r}]")
        for name, value in self.hypotheses.items():
            _bounded(float(value), f"life.hypotheses[{name!r}]")


@dataclass(frozen=True, slots=True)
class StructuralAssessment:
    state: StructuralState = StructuralState.UNKNOWN
    confidence: float | None = None
    objects: int | None = None
    total_living_mass: int | None = None
    largest_object: int | None = None
    structure_birth_tick: int | None = None
    structural_extinction_tick: int | None = None

    def __post_init__(self) -> None:
        _bounded(self.confidence, "structure.confidence")
        for name in ("objects", "total_living_mass", "largest_object"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"structure.{name} must be non-negative")
        for name in ("structure_birth_tick", "structural_extinction_tick"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"structure.{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class EcologyAssessment:
    state: EcologyState = EcologyState.UNKNOWN
    population_state: PopulationState = PopulationState.UNKNOWN
    confidence: float | None = None
    ecosystem_health: float | None = None
    extinction_risk: float | None = None

    def __post_init__(self) -> None:
        _bounded(self.confidence, "ecology.confidence")
        _bounded(self.ecosystem_health, "ecology.ecosystem_health")
        _bounded(self.extinction_risk, "ecology.extinction_risk")


@dataclass(frozen=True, slots=True)
class LayerAssessment:
    """Generic assessment for identity, civilization, knowledge, and similar layers."""

    state: str = "unknown"
    score: float | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _bounded(self.score, "layer.score")
        _bounded(self.confidence, "layer.confidence")


@dataclass(frozen=True, slots=True)
class LegacyCompatibility:
    """Uninterpreted legacy fields kept during migration.

    `alive` is intentionally not treated as a canonical life verdict.
    `birth_tick` and `collapse_tick` retain their historical meanings until
    dedicated adapters replace them.
    """

    alive: bool | None = None
    birth_tick: int | None = None
    collapse_tick: int | None = None
    source_version: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObserverState:
    """Canonical snapshot exchanged between Observer, storage, and Analyzer."""

    tick: int
    world_id: str
    run_id: str
    observer_version: str
    life: LifeAssessment = field(default_factory=LifeAssessment)
    structure: StructuralAssessment = field(default_factory=StructuralAssessment)
    ecology: EcologyAssessment = field(default_factory=EcologyAssessment)
    identity: LayerAssessment = field(default_factory=LayerAssessment)
    civilization: LayerAssessment = field(default_factory=LayerAssessment)
    knowledge: LayerAssessment = field(default_factory=LayerAssessment)
    emergence: LayerAssessment = field(default_factory=LayerAssessment)
    validation: LayerAssessment = field(default_factory=LayerAssessment)
    events: tuple[OntologyEvent, ...] = ()
    legacy: LegacyCompatibility = field(default_factory=LegacyCompatibility)
    schema_version: str = SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.tick < 0:
            raise ValueError("tick must be non-negative")
        if not self.world_id.strip():
            raise ValueError("world_id must be non-empty")
        if not self.run_id.strip():
            raise ValueError("run_id must be non-empty")
        if not self.observer_version.strip():
            raise ValueError("observer_version must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary with stable enum values."""

        return _jsonable(self)

    def to_telemetry_dict(self) -> dict[str, Any]:
        """Return the compact, flat Stage 1C telemetry contract.

        This projection deliberately contains only stable scalar values. Rich
        axes, hypotheses, warnings, events, and metadata remain available in
        :meth:`to_dict` and passport outputs.
        """

        return {
            "life_state": self.life.state.value,
            "life_score": self.life.score,
            "life_confidence": self.life.confidence,
            "life_uncertainty": self.life.uncertainty,
            "structural_state": self.structure.state.value,
            "ecology_state": self.ecology.state.value,
            "identity_state": self.identity.state,
            "knowledge_state": self.knowledge.state,
        }

    @classmethod
    def from_legacy_snapshot(
        cls,
        snapshot: Mapping[str, Any],
        *,
        world_id: str,
        run_id: str,
        observer_version: str,
    ) -> "ObserverState":
        """Create a non-invasive state wrapper around current Observer output.

        This adapter copies existing Life Evidence fields when present.  It
        does *not* derive canonical life or structural verdicts from legacy
        `alive`, `birth_tick`, or `collapse_tick`.

        Stage 2A also promotes *explicitly named* lifecycle fields to typed
        ontology events. Ambiguous legacy ticks remain compatibility data and
        are exposed only as semantic candidates, never as canonical events.
        """

        verdict = snapshot.get("life_evidence_verdict")
        normalized_verdict = (
            str(verdict).strip().lower().replace("-", "_").replace(" ", "_")
            if verdict is not None
            else None
        )
        # Legacy Life Evidence uses INSUFFICIENT_EVIDENCE as a verdict, while
        # the canonical ontology deliberately models it as assessment status,
        # not as a LifeState.  Preserve that distinction instead of passing
        # the status label to parse_life_state(), which correctly rejects it.
        if normalized_verdict == LifeEvidenceStatus.INSUFFICIENT_EVIDENCE.value:
            life_state = LifeState.UNKNOWN
            status = LifeEvidenceStatus.INSUFFICIENT_EVIDENCE
        elif verdict is not None:
            life_state = parse_life_state(verdict)
            status = LifeEvidenceStatus.PROVISIONAL
        else:
            life_state = LifeState.UNKNOWN
            status = LifeEvidenceStatus.NOT_EVALUATED
        hypotheses = _numeric_mapping(snapshot.get("life_evidence_hypotheses"))
        axes = _numeric_mapping(snapshot.get("life_evidence_axes"))
        warnings = _string_tuple(snapshot.get("life_evidence_warnings"))

        objects = _optional_int(snapshot.get("objects"))
        mass = _optional_int(snapshot.get("total_living_mass"))
        largest = _optional_int(snapshot.get("largest"))

        structural_state = StructuralState.UNKNOWN
        # Empty is an observation, not an inference about life.
        if objects == 0 and mass == 0 and (largest in (None, 0)):
            structural_state = StructuralState.EMPTY
        elif any(value is not None and value > 0 for value in (objects, mass, largest)):
            structural_state = StructuralState.PRESENT

        lifecycle_events = _canonical_lifecycle_events(snapshot)
        legacy_birth_tick = _optional_int(snapshot.get("birth_tick"))
        legacy_collapse_tick = _optional_int(snapshot.get("collapse_tick"))
        legacy_semantic_candidates: dict[str, list[str]] = {}
        if legacy_birth_tick is not None:
            legacy_semantic_candidates["birth_tick"] = [
                BirthType.STRUCTURE_APPEARANCE.value,
                BirthType.ORGANIZATION_ONSET.value,
                BirthType.LIFE_EVIDENCE_ONSET.value,
            ]
        if legacy_collapse_tick is not None:
            legacy_semantic_candidates["collapse_tick"] = [
                ExtinctionType.STRUCTURAL_EXTINCTION.value,
                CollapseType.POPULATION_COLLAPSE.value,
                CollapseType.ECOLOGICAL_COLLAPSE.value,
            ]

        return cls(
            tick=int(snapshot.get("tick", 0)),
            world_id=world_id,
            run_id=run_id,
            observer_version=observer_version,
            life=LifeAssessment(
                state=life_state,
                status=status,
                score=_optional_float(snapshot.get("life_evidence_score")),
                confidence=_optional_float(snapshot.get("life_evidence_confidence")),
                uncertainty=_optional_float(snapshot.get("life_evidence_uncertainty")),
                winner=_optional_str(snapshot.get("life_evidence_winner")),
                runner_up=_optional_str(snapshot.get("life_evidence_runner_up")),
                margin=_optional_float(snapshot.get("life_evidence_margin")),
                gate_passed=_optional_bool(snapshot.get("life_evidence_gate_passed")),
                axes=axes,
                hypotheses=hypotheses,
                warnings=warnings,
            ),
            structure=StructuralAssessment(
                state=structural_state,
                objects=objects,
                total_living_mass=mass,
                largest_object=largest,
                structure_birth_tick=_optional_int(
                    snapshot.get("structure_birth_tick")
                ),
                structural_extinction_tick=_optional_int(
                    snapshot.get("structural_extinction_tick")
                ),
            ),
            ecology=EcologyAssessment(
                state=_parse_ecology_state(snapshot.get("ecosystem_phase")),
                ecosystem_health=_optional_float(snapshot.get("ecosystem_health")),
                extinction_risk=_optional_float(snapshot.get("evo_extinction_risk")),
            ),
            identity=LayerAssessment(
                state="observed" if snapshot.get("identity_persistence") is not None else "unknown",
                score=_optional_float(snapshot.get("identity_persistence")),
            ),
            civilization=LayerAssessment(
                state=str(
                    snapshot.get("civilization_stage")
                    or snapshot.get("civ_stage")
                    or "unknown"
                ),
                score=_optional_probability(
                    snapshot.get("civilization_score", snapshot.get("civ_score"))
                ),
            ),
            knowledge=LayerAssessment(
                state=str(snapshot.get("knowledge_stage") or "observed"),
                score=_optional_probability(
                    snapshot.get("knowledge_score", snapshot.get("knowledge_memory"))
                ),
            ),
            emergence=LayerAssessment(
                state="observed" if snapshot.get("emergence_score") is not None else "unknown",
                score=_optional_probability(snapshot.get("emergence_score")),
                confidence=_optional_probability(snapshot.get("emergence_confidence")),
            ),
            validation=LayerAssessment(
                state="observed" if snapshot.get("validation_quality") is not None else "unknown",
                score=_optional_probability(snapshot.get("validation_quality")),
            ),
            events=lifecycle_events,
            legacy=LegacyCompatibility(
                alive=_optional_bool(snapshot.get("alive")),
                birth_tick=legacy_birth_tick,
                collapse_tick=legacy_collapse_tick,
                source_version=observer_version,
                extra={
                    "semantic_candidates": legacy_semantic_candidates,
                    "promoted_to_canonical_events": False,
                },
            ),
            metadata={
                "ontology_version": SCHEMA_VERSION,
                "lifecycle_contract": "stage2a-shadow",
            },
        )


def _canonical_lifecycle_events(
    snapshot: Mapping[str, Any],
) -> tuple[OntologyEvent, ...]:
    """Promote only unambiguous lifecycle fields to typed events.

    Legacy ``birth_tick`` and ``collapse_tick`` are intentionally absent from
    this mapping because their historical meanings overlap several canonical
    event types.
    """

    field_contract = (
        ("structure_birth_tick", BirthType.STRUCTURE_APPEARANCE, EventScope.STRUCTURE),
        ("organization_onset_tick", BirthType.ORGANIZATION_ONSET, EventScope.WORLD),
        ("life_evidence_onset_tick", BirthType.LIFE_EVIDENCE_ONSET, EventScope.WORLD),
        ("life_emergence_tick", BirthType.LIFE_EVIDENCE_ONSET, EventScope.WORLD),
        ("population_emergence_tick", BirthType.POPULATION_EMERGENCE, EventScope.POPULATION),
        ("ecosystem_emergence_tick", BirthType.ECOSYSTEM_EMERGENCE, EventScope.ECOSYSTEM),
        ("population_collapse_tick", CollapseType.POPULATION_COLLAPSE, EventScope.POPULATION),
        ("ecological_collapse_tick", CollapseType.ECOLOGICAL_COLLAPSE, EventScope.ECOSYSTEM),
        ("ecosystem_collapse_tick", CollapseType.ECOLOGICAL_COLLAPSE, EventScope.ECOSYSTEM),
        ("structural_extinction_tick", ExtinctionType.STRUCTURAL_EXTINCTION, EventScope.STRUCTURE),
    )
    events: list[OntologyEvent] = []
    seen: set[tuple[int, str, str]] = set()
    for field_name, event_type, scope in field_contract:
        tick = _optional_int(snapshot.get(field_name))
        if tick is None:
            continue
        key = (tick, event_type.value, scope.value)
        if key in seen:
            continue
        seen.add(key)
        confidence = _optional_probability(
            snapshot.get(f"{field_name}_confidence")
        )
        events.append(
            OntologyEvent(
                tick=tick,
                event_type=event_type,
                scope=scope,
                confidence=confidence,
                details={
                    "source_field": field_name,
                    "provenance": "explicit_snapshot_field",
                },
            )
        )
    return tuple(sorted(events, key=lambda event: (event.tick, event.event_type.value)))


def _numeric_mapping(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, item in value.items():
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if 0.0 <= number <= 1.0:
            result[str(key)] = number
    return result


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        # Current Observer sometimes publishes a comma-separated display line.
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(item) for item in value)
    return (str(value),)


def _optional_probability(value: Any) -> float | None:
    try:
        number = _optional_float(value)
    except (TypeError, ValueError):
        return None
    if number is None or not 0.0 <= number <= 1.0:
        return None
    return number


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Cannot parse boolean value: {value!r}")


def _parse_ecology_state(value: Any) -> EcologyState:
    if value is None or value == "":
        return EcologyState.UNKNOWN
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "collapsed": EcologyState.COLLAPSED,
        "seed": EcologyState.SEED,
        "warmup": EcologyState.WARMUP,
        "expansion": EcologyState.EXPANSION,
        "fragmentation": EcologyState.FRAGMENTATION,
        "merging": EcologyState.MERGING,
        "stable": EcologyState.STABLE,
        "reorganizing": EcologyState.REORGANIZING,
        "reorganisation": EcologyState.REORGANIZING,
        "reorganization": EcologyState.REORGANIZING,
    }
    return aliases.get(normalized, EcologyState.UNKNOWN)
