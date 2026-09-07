"""Canonical ecology-level vocabulary for Project ARCHON."""

from __future__ import annotations

from enum import Enum


class EcologyState(str, Enum):
    """World ecology phase, distinct from life and structural state."""

    UNKNOWN = "unknown"
    ABSENT = "absent"
    SEED = "seed"
    WARMUP = "warmup"
    EXPANSION = "expansion"
    FRAGMENTATION = "fragmentation"
    MERGING = "merging"
    STABLE = "stable"
    REORGANIZING = "reorganizing"
    CRISIS = "crisis"
    RECOVERY = "recovery"
    COLLAPSED = "collapsed"


class PopulationState(str, Enum):
    UNKNOWN = "unknown"
    ABSENT = "absent"
    EMERGING = "emerging"
    GROWING = "growing"
    STABLE = "stable"
    DECLINING = "declining"
    BOTTLENECK = "bottleneck"
    RECOVERING = "recovering"
    EXTINCT = "extinct"
