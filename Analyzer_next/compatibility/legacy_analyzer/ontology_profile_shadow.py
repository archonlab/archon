#!/usr/bin/env python3
"""Stage 1F ontology-based Profile classification in shadow mode.

The classifier translates already-produced ontology states into a compact
Analyzer-facing summary. It does not infer life from telemetry and never
replaces the legacy ``analyzer_category``.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "ontology_profile_shadow/1.0"

STRUCTURE_PRESENT = {
    "present",
    "fragmented",
    "coalescing",
    "growing",
    "stable",
    "oscillating",
    "declining",
}
STRUCTURE_EXTINCT = {"empty", "structurally_extinct"}
POSITIVE_LIFE = {
    "active_structure",
    "adaptive_organization",
    "life_candidate",
}
NON_LIFE_DYNAMICS = {
    "passive_oscillation",
    "stable_attractor",
    "crystal_dynamics",
}


def _state(value: Any) -> str:
    return str(value or "unknown").strip().lower().replace("-", "_").replace(" ", "_")


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _legacy_relation(legacy_category: str, shadow_category: str) -> str:
    """Describe broad semantic compatibility without equating vocabularies."""

    legacy = _state(legacy_category)
    positive = shadow_category in POSITIVE_LIFE
    non_life = shadow_category in (
        NON_LIFE_DYNAMICS
        | {
            "structure_without_life_evidence",
            "no_life_evidence",
            "structurally_extinct",
        }
    )

    if legacy == "collapsed_world":
        if shadow_category == "structurally_extinct":
            return "compatible"
        if positive or shadow_category in {"unresolved_structure", "structure_without_life_evidence"}:
            return "potential_conflict"
        return "indeterminate"
    if legacy == "beautiful_dead_or_static_world":
        if non_life:
            return "compatible"
        if positive:
            return "potential_conflict"
        return "indeterminate"
    if legacy in {"credible_emergent_organization", "adaptive_feedback_candidate"}:
        if positive:
            return "compatible"
        if non_life:
            return "potential_conflict"
        return "indeterminate"
    if legacy in {"knowledge_accumulation_candidate", "civilization_like_candidate"}:
        return "different_scope"
    return "indeterminate"


def classify_ontology_shadow(profile: dict[str, Any]) -> dict[str, Any]:
    """Build an additive, read-only shadow classification for one profile."""

    life_state = _state(profile.get("life_state"))
    life_status = _state(profile.get("life_status"))
    structural_state = _state(profile.get("structural_state"))
    ecology_state = _state(profile.get("ecology_state"))

    life_confidence = _confidence(profile.get("life_confidence"))
    structural_confidence = _confidence(profile.get("structural_confidence"))
    ecology_confidence = _confidence(profile.get("ecology_confidence"))

    reasons: list[str] = []
    warnings: list[str] = []

    if life_state in POSITIVE_LIFE | NON_LIFE_DYNAMICS:
        category = life_state
        confidence = life_confidence
        reasons.append(f"life_state={life_state}")
    elif life_state == "no_life_evidence":
        if structural_state in STRUCTURE_EXTINCT:
            category = "structurally_extinct"
            confidence = min(life_confidence, structural_confidence)
            reasons.extend([
                "life_state=no_life_evidence",
                f"structural_state={structural_state}",
            ])
        elif structural_state in STRUCTURE_PRESENT:
            category = "structure_without_life_evidence"
            confidence = min(life_confidence, structural_confidence)
            reasons.extend([
                "life_state=no_life_evidence",
                f"structural_state={structural_state}",
            ])
        else:
            category = "no_life_evidence"
            confidence = life_confidence
            reasons.append("life_state=no_life_evidence")
            warnings.append("structural_state_not_evaluated")
    elif structural_state in STRUCTURE_EXTINCT:
        category = "structurally_extinct"
        confidence = structural_confidence
        reasons.append(f"structural_state={structural_state}")
        warnings.append("life_state_not_evaluated")
    elif structural_state in STRUCTURE_PRESENT:
        category = "unresolved_structure"
        confidence = structural_confidence
        reasons.append(f"structural_state={structural_state}")
        warnings.append("life_state_not_evaluated")
    else:
        category = "insufficient_ontology_data"
        confidence = 0.0
        warnings.extend(["life_state_not_evaluated", "structural_state_not_evaluated"])

    if ecology_state == "collapsed":
        reasons.append("ecology_state=collapsed")
    elif ecology_state == "unknown":
        warnings.append("ecology_state_not_evaluated")

    if life_status in {"not_evaluated", "insufficient_evidence"}:
        warnings.append(f"life_status={life_status}")
    elif life_status == "contested":
        warnings.append("life_status=contested")
    if confidence < 0.5:
        warnings.append("low_shadow_confidence")

    # Ecology is contextual rather than a gate for the life classification.
    # Record its confidence only when ecology contributes an explicit claim.
    if ecology_state == "collapsed":
        confidence = min(confidence, ecology_confidence)

    status = (
        "not_evaluated"
        if category == "insufficient_ontology_data"
        else "insufficient_evidence"
        if life_status in {"not_evaluated", "insufficient_evidence"} or confidence < 0.5
        else "contested"
        if life_status == "contested"
        else "supported"
        if life_status == "supported"
        else "provisional"
    )

    # Preserve order while removing duplicate warnings.
    warnings = list(dict.fromkeys(warnings))
    legacy_category = str(profile.get("analyzer_category") or "unknown")
    return {
        "ontology_shadow_schema_version": SCHEMA_VERSION,
        "ontology_shadow_category": category,
        "ontology_shadow_status": status,
        "ontology_shadow_confidence": round(confidence, 6),
        "ontology_shadow_reasons": reasons,
        "ontology_shadow_warnings": warnings,
        "ontology_shadow_legacy_relation": _legacy_relation(legacy_category, category),
    }

