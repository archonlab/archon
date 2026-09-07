"""Canonical runtime projection for Observer morphology diagnostics.

The morphology detector already computes these fields.  This module keeps the
live ``Observer.current`` snapshot and its UI consumers from silently dropping
part of that result and substituting display defaults.
"""

from __future__ import annotations

from typing import Any, Mapping


MORPHOLOGY_RUNTIME_DEFAULTS: dict[str, Any] = {
    "morphology_compactness": 0.0,
    "morphology_aspect": 0.0,
    "morphology_edge_complexity": 0.0,
    "morphology_bbox_fill": 0.0,
    "morphology_symmetry": 0.0,
    "morphology_branching": 0.0,
    "morphology_filament_score": 0.0,
    "morphology_lattice_score": 0.0,
    "morphology_score": 0.0,
    "morphology_change_rate": 0.0,
    "morphology_stability_ticks": 0,
    "morphology_longest_stable_ticks": 0,
    "morphology_peak_complexity": 0.0,
    "morphology_score_peak": 0.0,
    "morphology_transition_count": 0,
    "morphology_major_transition_count": 0,
    "morphology_class": "none",
    "morphology_dominant_class": "none",
    "morphology_last_event": "",
    "morphology_line": "MORPH none",
}


def build_morphology_runtime_snapshot(
    morphology: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete detector-to-runtime morphology projection.

    A missing detector field is an integration error, not a scientific zero,
    so populated projections intentionally use direct indexing.
    """

    if morphology is None:
        return dict(MORPHOLOGY_RUNTIME_DEFAULTS)
    return {key: morphology[key] for key in MORPHOLOGY_RUNTIME_DEFAULTS}
