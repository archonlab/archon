"""Feature drift, oscillation, and morphology behaviour labels."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.morphology.numeric import (
    mean,
    oscillation_score,
    safe_float,
    slope,
    sparkline,
    stdev,
)
from Analyzer_next.core.morphology.rows import series
from Analyzer_next.core.morphology.segmentation import local_mci


def behaviour_signature(rows: list[dict[str, Any]], entropy: float) -> dict[str, Any]:
    if not rows:
        return {
            "label": "NO_DATA",
            "scores": {},
            "feature_slopes": {},
            "sparklines": {},
            "description": "No morphology samples available.",
        }

    mci = [local_mci(row, entropy) for row in rows]
    branching = series("_morphology_branching", rows)
    edge = series("_morphology_edge_complexity", rows)
    filament = series("_morphology_filament_score", rows)
    lattice = series("_morphology_lattice_score", rows)
    change = series("_morphology_change_rate", rows)
    compactness = series("_morphology_compactness", rows)
    symmetry = series("_morphology_symmetry", rows)

    slopes = {
        "mci": slope(mci),
        "branching": slope(branching),
        "edge": slope(edge) / 40.0,
        "filament": slope(filament),
        "lattice": slope(lattice),
        "change_rate": slope(change),
        "compactness": slope(compactness),
        "symmetry": slope(symmetry),
    }

    volatility = min(1.0, (stdev(mci) + stdev(change) + 0.5 * stdev(branching)) / 1.2)
    drift_strength = min(1.0, (
        abs(slopes["mci"]) +
        abs(slopes["branching"]) * 0.35 +
        abs(slopes["edge"]) +
        abs(slopes["filament"]) +
        abs(slopes["lattice"]) +
        abs(slopes["change_rate"]) * 0.5
    ) / 2.2)

    oscillation = min(1.0, (
        oscillation_score(mci) * 0.35 +
        oscillation_score(branching) * 0.20 +
        oscillation_score(edge) * 0.20 +
        oscillation_score(change) * 0.25
    ))

    mci_slope = slopes["mci"]
    branching_slope = slopes["branching"]
    edge_slope = slopes["edge"]
    filament_slope = slopes["filament"]
    lattice_slope = slopes["lattice"]
    change_slope = slopes["change_rate"]

    maturation = max(0.0, min(1.0,
        0.45 * max(0.0, mci_slope) +
        0.20 * max(0.0, branching_slope) +
        0.20 * max(0.0, edge_slope) +
        0.15 * max(0.0, mean(mci))
    ))
    instability = max(0.0, min(1.0,
        0.45 * volatility +
        0.30 * oscillation +
        0.25 * max(0.0, change_slope)
    ))
    pulse = max(0.0, min(1.0,
        0.55 * oscillation +
        0.25 * volatility +
        0.20 * max(0.0, mean(change))
    ))

    if instability >= 0.40 and pulse >= 0.35:
        label = "VOLATILE_RECONFIGURATION"
    elif pulse >= 0.35:
        label = "OSCILLATING_FORM"
    elif filament_slope > 0.10 and mean(filament[-max(1, len(filament)//3):]) > mean(filament[:max(1, len(filament)//3)]):
        label = "FILAMENT_PULSE"
    elif lattice_slope > 0.10:
        label = "LATTICE_SHIFT"
    elif branching_slope > 0.25:
        label = "BRANCHING_SURGE"
    elif mci_slope > 0.08:
        label = "GROWING_COMPLEXITY"
    elif mci_slope < -0.08:
        label = "SIMPLIFYING_FORM"
    elif maturation >= 0.18:
        label = "QUIET_MATURATION"
    else:
        label = "STABLE_FORM"

    descriptions = {
        "VOLATILE_RECONFIGURATION": "Shape features fluctuate strongly while the world keeps reorganizing.",
        "OSCILLATING_FORM": "Shape repeatedly swings between nearby morphology states.",
        "FILAMENT_PULSE": "Filament-like structure becomes more visible over time.",
        "LATTICE_SHIFT": "Lattice-like ordering increases through the observation.",
        "BRANCHING_SURGE": "Branching grows noticeably during the run.",
        "GROWING_COMPLEXITY": "Overall morphology becomes more complex over time.",
        "SIMPLIFYING_FORM": "Overall morphology becomes simpler over time.",
        "QUIET_MATURATION": "The form matures without large class-level transitions.",
        "STABLE_FORM": "The morphology stays comparatively stable.",
    }

    return {
        "label": label,
        "description": descriptions.get(label, ""),
        "scores": {
            "behaviour_volatility": volatility,
            "behaviour_drift_strength": drift_strength,
            "behaviour_oscillation": oscillation,
            "behaviour_maturation_score": maturation,
            "behaviour_instability_score": instability,
            "behaviour_pulse_score": pulse,
        },
        "feature_slopes": {
            "behaviour_complexity_slope": mci_slope,
            "behaviour_branching_slope": branching_slope,
            "behaviour_edge_slope": edge_slope,
            "behaviour_filament_slope": filament_slope,
            "behaviour_lattice_slope": lattice_slope,
            "behaviour_change_slope": change_slope,
            "compactness_slope": slopes["compactness"],
            "symmetry_slope": slopes["symmetry"],
        },
        "feature_means": {
            "mci": mean(mci),
            "branching": mean(branching),
            "edge": mean(edge),
            "filament": mean(filament),
            "lattice": mean(lattice),
            "change_rate": mean(change),
            "compactness": mean(compactness),
            "symmetry": mean(symmetry),
        },
        "sparklines": {
            "mci": sparkline(mci),
            "branching": sparkline(branching),
            "edge": sparkline(edge),
            "filament": sparkline(filament),
            "lattice": sparkline(lattice),
            "change_rate": sparkline(change),
        }
    }


def behaviour_feature_vector(signature: dict[str, Any]) -> dict[str, float]:
    scores = signature.get("scores", {})
    slopes = signature.get("feature_slopes", {})
    return {
        "behaviour_volatility": safe_float(scores.get("behaviour_volatility")),
        "behaviour_drift_strength": safe_float(scores.get("behaviour_drift_strength")),
        "behaviour_oscillation": safe_float(scores.get("behaviour_oscillation")),
        "behaviour_complexity_slope": safe_float(slopes.get("behaviour_complexity_slope")),
        "behaviour_branching_slope": safe_float(slopes.get("behaviour_branching_slope")),
        "behaviour_edge_slope": safe_float(slopes.get("behaviour_edge_slope")),
        "behaviour_filament_slope": safe_float(slopes.get("behaviour_filament_slope")),
        "behaviour_lattice_slope": safe_float(slopes.get("behaviour_lattice_slope")),
        "behaviour_change_slope": safe_float(slopes.get("behaviour_change_slope")),
        "behaviour_maturation_score": safe_float(scores.get("behaviour_maturation_score")),
        "behaviour_instability_score": safe_float(scores.get("behaviour_instability_score")),
        "behaviour_pulse_score": safe_float(scores.get("behaviour_pulse_score")),
    }
