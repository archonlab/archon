"""Canonical event and transition vocabulary for Project ARCHON."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class BirthType(str, Enum):
    STRUCTURE_APPEARANCE = "structure_appearance"
    ORGANIZATION_ONSET = "organization_onset"
    LIFE_EVIDENCE_ONSET = "life_evidence_onset"
    POPULATION_EMERGENCE = "population_emergence"
    ECOSYSTEM_EMERGENCE = "ecosystem_emergence"
    FAMILY_ORIGIN = "family_origin"
    COLONY_ORIGIN = "colony_origin"


class CollapseType(str, Enum):
    POPULATION_COLLAPSE = "population_collapse"
    ECOLOGICAL_COLLAPSE = "ecological_collapse"
    ORGANIZATIONAL_COLLAPSE = "organizational_collapse"
    KNOWLEDGE_LOSS = "knowledge_loss"
    CIVILIZATION_COLLAPSE = "civilization_collapse"


class ExtinctionType(str, Enum):
    STRUCTURAL_EXTINCTION = "structural_extinction"
    POPULATION_EXTINCTION = "population_extinction"
    COLONY_EXTINCTION = "colony_extinction"
    FAMILY_EXTINCTION = "family_extinction"
    SPECIES_EXTINCTION = "species_extinction"
    MASS_EXTINCTION = "mass_extinction"


class EventScope(str, Enum):
    WORLD = "world"
    ECOSYSTEM = "ecosystem"
    POPULATION = "population"
    FAMILY = "family"
    COLONY = "colony"
    SPECIES = "species"
    STRUCTURE = "structure"


@dataclass(frozen=True, slots=True)
class OntologyEvent:
    """Typed event reference usable by Observer, telemetry, and Analyzer."""

    tick: int
    event_type: BirthType | CollapseType | ExtinctionType
    scope: EventScope
    confidence: float | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.tick < 0:
            raise ValueError("tick must be non-negative")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
