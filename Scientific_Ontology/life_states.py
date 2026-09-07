"""Canonical world-level life-state vocabulary for Project ARCHON.

This module defines labels only.  It deliberately contains no thresholds and
must not be used to infer a state directly from telemetry.  Classification
belongs to Observer evidence models.
"""

from __future__ import annotations

from enum import Enum


class LifeState(str, Enum):
    """Canonical interpretation of organization at the world level."""

    UNKNOWN = "unknown"
    NO_LIFE_EVIDENCE = "no_life_evidence"
    PASSIVE_OSCILLATION = "passive_oscillation"
    STABLE_ATTRACTOR = "stable_attractor"
    CRYSTAL_DYNAMICS = "crystal_dynamics"
    ACTIVE_STRUCTURE = "active_structure"
    ADAPTIVE_ORGANIZATION = "adaptive_organization"
    LIFE_CANDIDATE = "life_candidate"


class LifeEvidenceStatus(str, Enum):
    """Status of a life assessment, separate from its verdict."""

    NOT_EVALUATED = "not_evaluated"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PROVISIONAL = "provisional"
    SUPPORTED = "supported"
    CONTESTED = "contested"


LIFE_STATE_ORDER: tuple[LifeState, ...] = (
    LifeState.NO_LIFE_EVIDENCE,
    LifeState.PASSIVE_OSCILLATION,
    LifeState.STABLE_ATTRACTOR,
    LifeState.CRYSTAL_DYNAMICS,
    LifeState.ACTIVE_STRUCTURE,
    LifeState.ADAPTIVE_ORGANIZATION,
    LifeState.LIFE_CANDIDATE,
)


def parse_life_state(value: object) -> LifeState:
    """Parse a serialized value without silently inventing a classification."""

    if isinstance(value, LifeState):
        return value
    if value is None:
        return LifeState.UNKNOWN
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "none": LifeState.UNKNOWN,
        "unknown": LifeState.UNKNOWN,
        "passive": LifeState.PASSIVE_OSCILLATION,
        "stable": LifeState.STABLE_ATTRACTOR,
        "crystal": LifeState.CRYSTAL_DYNAMICS,
        "active": LifeState.ACTIVE_STRUCTURE,
        "adaptive": LifeState.ADAPTIVE_ORGANIZATION,
        "life": LifeState.LIFE_CANDIDATE,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return LifeState(normalized)
    except ValueError as exc:
        raise ValueError(f"Unknown LifeState value: {value!r}") from exc
