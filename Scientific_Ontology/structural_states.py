"""Canonical structural-state vocabulary for Project ARCHON."""

from __future__ import annotations

from enum import Enum


class StructuralState(str, Enum):
    """Physical state of structures, independent of claims about life."""

    UNKNOWN = "unknown"
    EMPTY = "empty"
    PRESENT = "present"
    FRAGMENTED = "fragmented"
    COALESCING = "coalescing"
    GROWING = "growing"
    STABLE = "stable"
    OSCILLATING = "oscillating"
    DECLINING = "declining"
    STRUCTURALLY_EXTINCT = "structurally_extinct"


class TrackState(str, Enum):
    """State of one tracked colony or object, never of the whole world."""

    UNKNOWN = "unknown"
    ACTIVE = "active"
    MISSING = "missing"
    EXTINCT = "extinct"


def parse_structural_state(value: object) -> StructuralState:
    if isinstance(value, StructuralState):
        return value
    if value is None:
        return StructuralState.UNKNOWN
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return StructuralState(normalized)
    except ValueError as exc:
        raise ValueError(f"Unknown StructuralState value: {value!r}") from exc
