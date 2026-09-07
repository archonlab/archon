"""Stable macro-event vocabulary for Morphological Event Fusion v1.0."""
from __future__ import annotations

from typing import Any


FUSION_TYPES: dict[str, dict[str, Any]] = {
    "COLLAPSE_EVENT": {
        "events": {
            "MASS_COLLAPSE", "OBJECT_DIEBACK", "COMPLEXITY_DROP",
            "STABILITY_LOSS", "RISK_SPIKE", "SYMMETRY_BREAK",
            "FILAMENT_FADE", "LATTICE_FADE",
        },
        "family": "collapse",
    },
    "STRUCTURAL_EXPANSION_EVENT": {
        "events": {
            "MASS_EXPLOSION", "OBJECT_BURST", "COMPLEXITY_SURGE",
            "BRANCHING_BURST", "EDGE_COMPLEXITY_BURST",
            "FILAMENT_EMERGENCE", "LATTICE_EMERGENCE",
        },
        "family": "growth",
    },
    "REORGANIZATION_EVENT": {
        "events": {
            "REORGANIZATION", "MORPHOLOGY_CLASS_SHIFT",
            "OSCILLATION_START", "OSCILLATION_END",
            "PRESSURE_SPIKE",
        },
        "family": "reorganization",
    },
    "DORMANCY_TRANSITION": {
        "events": {
            "DORMANCY_START", "OSCILLATION_END", "COMPLEXITY_DROP",
            "STABILITY_GAIN", "PRESSURE_SPIKE",
        },
        "family": "dormancy",
    },
    "REVIVAL_EVENT": {
        "events": {
            "REVIVAL", "DORMANCY_END", "MASS_EXPLOSION", "OBJECT_BURST",
            "COMPLEXITY_SURGE", "STABILITY_GAIN", "SYMMETRY_RECOVERY",
        },
        "family": "recovery",
    },
    "ORDERING_EVENT": {
        "events": {
            "LATTICE_EMERGENCE", "SYMMETRY_RECOVERY", "STABILITY_GAIN",
            "COMPLEXITY_SURGE",
        },
        "family": "ordering",
    },
    "FRAGMENTATION_EVENT": {
        "events": {
            "SYMMETRY_BREAK", "FILAMENT_FADE", "LATTICE_FADE",
            "OBJECT_DIEBACK", "COMPLEXITY_DROP",
        },
        "family": "fragmentation",
    },
}


EVENT_TO_FUSION: dict[str, list[str]] = {}
for fusion_type, specification in FUSION_TYPES.items():
    for event_type in specification["events"]:
        EVENT_TO_FUSION.setdefault(event_type, []).append(fusion_type)

