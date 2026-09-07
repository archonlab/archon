# -*- coding: utf-8 -*-
"""
Project ARCHON Scientific Claims Registry v1.1

Single source of truth for principle-level scientific claims.

Defines for each claim:
- identity and wording;
- support / counterexample / neutral classification;
- near-counterexample scoring;
- explicit counterexample search targets;
- claim family and interpretation notes.

Compatibility exports:
- CLAIMS
- POTENTIAL
- TARGETS

These allow Evidence Engine and Counterexample Engine to migrate without
changing their internal loops immediately.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable


ClaimTest = Callable[[dict[str, Any]], tuple[str, float, str]]
PotentialTest = Callable[[dict[str, Any]], tuple[float, str]]


CONF_RANK = {
    "NONE": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "VERY_HIGH": 4,
}


def sf(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def si(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def ss(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def conf(value: Any) -> str:
    normalized = ss(value, "NONE").strip().upper().replace(" ", "_")
    return normalized if normalized in CONF_RANK else "NONE"


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class ClaimSpec:
    id: str
    title: str
    description: str
    family: str
    test: ClaimTest
    potential: PotentialTest
    search_targets: tuple[dict[str, Any], ...]
    interpretation: str
    required_fields: tuple[str, ...] = ()
    allow_none_fields: tuple[str, ...] = ()
    version: str = "1.1"


def _is_present(profile: dict[str, Any], field: str, *, allow_none: bool = False) -> bool:
    if field not in profile:
        return False
    value = profile.get(field)
    if value is None:
        return allow_none
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return False
    return True


def missing_required_fields(spec: ClaimSpec, profile: dict[str, Any]) -> tuple[str, ...]:
    allow_none = set(spec.allow_none_fields)
    return tuple(
        field
        for field in spec.required_fields
        if not _is_present(profile, field, allow_none=field in allow_none)
    )


def _unavailable_result(spec: ClaimSpec, profile: dict[str, Any]) -> tuple[str, float, str] | None:
    missing = missing_required_fields(spec, profile)
    if not missing:
        return None
    return (
        "unavailable",
        0.0,
        "missing required measurements: " + ", ".join(missing),
    )


def _guarded_test(spec: ClaimSpec, profile: dict[str, Any]) -> tuple[str, float, str]:
    unavailable = _unavailable_result(spec, profile)
    return unavailable if unavailable is not None else spec.test(profile)


def _guarded_potential(spec: ClaimSpec, profile: dict[str, Any]) -> tuple[float, str]:
    missing = missing_required_fields(spec, profile)
    if missing:
        return 0.0, "unavailable: missing required measurements: " + ", ".join(missing)
    return spec.potential(profile)


# ---------------------------------------------------------------------------
# GP-101: Validated emergence
# ---------------------------------------------------------------------------

def claim_validated_emergence(
    p: dict[str, Any],
) -> tuple[str, float, str]:
    emg = sf(p.get("emergence_score"))
    val = sf(p.get("validation_quality"))
    emg_c = conf(p.get("emergence_confidence"))
    val_c = conf(p.get("validation_grade"))
    fp = sf(p.get("validation_false_positive_risk"))
    fn = sf(p.get("validation_false_negative_risk"))

    if (
        emg >= 0.65
        and val >= 0.70
        and CONF_RANK[emg_c] >= 3
        and CONF_RANK[val_c] >= 3
        and fp <= 0.25
    ):
        strength = (emg + val + (1.0 - fp)) / 3.0
        return (
            "support",
            clamp01(strength),
            "high EMG + high VAL with low false-positive risk",
        )

    if emg >= 0.65 and (val < 0.35 or fp > 0.45):
        strength = emg * (1.0 - val + fp) / 2.0
        return (
            "counterexample",
            clamp01(strength),
            "high EMG but weak validation or high false-positive risk",
        )

    if val >= 0.75 and emg < 0.20 and fn > 0.35:
        return (
            "counterexample",
            clamp01(val * fn),
            "validation hints possible false negative while EMG is low",
        )

    return (
        "neutral",
        clamp01(max(emg, val) * 0.25),
        "insufficient emergence-validation signal",
    )


def potential_gp101(p: dict[str, Any]) -> tuple[float, str]:
    emg = sf(p.get("emergence_score"))
    val = sf(p.get("validation_quality"))
    fp = sf(p.get("validation_false_positive_risk"))
    fn = sf(p.get("validation_false_negative_risk"))

    high_emg_weak_val = (
        max(0.0, emg - 0.45)
        * max(0.0, 0.60 - val + fp)
    )
    low_emg_false_negative = (
        max(0.0, val - 0.65)
        * max(0.0, 0.35 - emg)
        * max(fn, 0.15)
    )

    if high_emg_weak_val >= low_emg_false_negative:
        return (
            clamp01(high_emg_weak_val * 2.5),
            "near high-EMG / weak-validation contradiction",
        )

    return (
        clamp01(low_emg_false_negative * 2.5),
        "near low-EMG / possible-false-negative contradiction",
    )


# ---------------------------------------------------------------------------
# GP-102: Knowledge-feedback coupling
# ---------------------------------------------------------------------------

def claim_knowledge_feedback_coupling(
    p: dict[str, Any],
) -> tuple[str, float, str]:
    independence = ss(
        p.get("feedback_metric_independence_status")
    ).upper()
    if independence != "STRUCTURALLY_INDEPENDENT_V2":
        return (
            "unavailable",
            0.0,
            "feedback metric is structurally coupled to knowledge axes",
        )
    know = sf(p.get("knowledge_score"))
    fb = sf(p.get("feedback_score"))
    transfer = sf(p.get("knowledge_transfer"))
    knowledge_impact = sf(p.get("feedback_knowledge_impact"))
    regime = ss(p.get("feedback_regime"), "NONE").upper()

    if (
        know >= 0.50
        and fb >= 0.50
        and (
            transfer >= 0.35
            or knowledge_impact >= 0.35
            or regime not in {"NONE", "WEAK", "WEAK_LOOP"}
        )
    ):
        strength = (know + fb + max(transfer, knowledge_impact)) / 3.0
        return (
            "support",
            clamp01(strength),
            "knowledge accumulation coincides with measurable feedback coupling",
        )

    if know >= 0.65 and fb < 0.20:
        return (
            "counterexample",
            clamp01(know * (1.0 - fb)),
            "knowledge accumulates without feedback response",
        )

    if fb >= 0.65 and know < 0.20:
        return (
            "counterexample",
            clamp01(fb * (1.0 - know)),
            "feedback appears without knowledge scaffold",
        )

    return (
        "neutral",
        clamp01(max(know, fb) * 0.25),
        "weak or partial knowledge-feedback signal",
    )


def potential_gp102(p: dict[str, Any]) -> tuple[float, str]:
    if ss(
        p.get("feedback_metric_independence_status")
    ).upper() != "STRUCTURALLY_INDEPENDENT_V2":
        return 0.0, "unavailable: feedback metric is coupled to KNOW"
    know = sf(p.get("knowledge_score"))
    fb = sf(p.get("feedback_score"))

    knowledge_without_feedback = (
        max(0.0, know - 0.40)
        * max(0.0, 0.40 - fb)
    )
    feedback_without_knowledge = (
        max(0.0, fb - 0.40)
        * max(0.0, 0.40 - know)
    )

    if knowledge_without_feedback >= feedback_without_knowledge:
        return (
            clamp01(knowledge_without_feedback * 4.0),
            "near high-KNOW / low-FB decoupling",
        )

    return (
        clamp01(feedback_without_knowledge * 4.0),
        "near high-FB / low-KNOW decoupling",
    )


# ---------------------------------------------------------------------------
# GP-103: Self-regulation marker
# ---------------------------------------------------------------------------

def claim_self_regulation_marker(
    p: dict[str, Any],
) -> tuple[str, float, str]:
    if ss(
        p.get("feedback_metric_independence_status")
    ).upper() != "STRUCTURALLY_INDEPENDENT_V2":
        return (
            "unavailable",
            0.0,
            "self-regulation requires the independent feedback metric v2",
        )
    fb = sf(p.get("feedback_score"))
    self_direction = sf(p.get("feedback_self_direction"))
    pressure = sf(p.get("feedback_effective_pressure"))
    effective_risk = sf(p.get("feedback_effective_risk"))
    regime = ss(p.get("feedback_regime"), "NONE").upper()
    survival_bonus = sf(p.get("feedback_survival_bonus"))

    if (
        fb >= 0.55
        and self_direction >= 0.45
        and (
            "SELF" in regime
            or "ADAPT" in regime
            or survival_bonus >= 0.65
        )
        and effective_risk <= 0.35
    ):
        strength = (
            fb
            + self_direction
            + (1.0 - effective_risk)
        ) / 3.0
        return (
            "support",
            clamp01(strength),
            "feedback shows self-direction with reduced effective risk",
        )

    if fb >= 0.60 and effective_risk > 0.60:
        return (
            "counterexample",
            clamp01(fb * effective_risk),
            "strong feedback score but effective risk remains high",
        )

    if self_direction >= 0.60 and fb < 0.25:
        return (
            "counterexample",
            clamp01(self_direction * (1.0 - fb)),
            "self-direction marker without feedback score",
        )

    return (
        "neutral",
        clamp01(max(fb, self_direction, 1.0 - pressure) * 0.20),
        "self-regulation signal incomplete",
    )


def potential_gp103(p: dict[str, Any]) -> tuple[float, str]:
    if ss(
        p.get("feedback_metric_independence_status")
    ).upper() != "STRUCTURALLY_INDEPENDENT_V2":
        return 0.0, "unavailable: feedback metric is coupled to KNOW"
    fb = sf(p.get("feedback_score"))
    self_direction = sf(p.get("feedback_self_direction"))
    risk = sf(p.get("feedback_effective_risk"))

    feedback_high_risk = (
        max(0.0, fb - 0.40)
        * max(0.0, risk - 0.40)
    )
    direction_weak_feedback = (
        max(0.0, self_direction - 0.45)
        * max(0.0, 0.40 - fb)
    )

    if feedback_high_risk >= direction_weak_feedback:
        return (
            clamp01(feedback_high_risk * 3.0),
            "near strong-feedback / high-risk contradiction",
        )

    return (
        clamp01(direction_weak_feedback * 3.0),
        "near self-direction / weak-feedback contradiction",
    )


# ---------------------------------------------------------------------------
# GP-104: Pattern-life separation
# This is a validation/calibration claim, not a general law of life.
# ---------------------------------------------------------------------------

def claim_pattern_life_separation(
    p: dict[str, Any],
) -> tuple[str, float, str]:
    peak = si(p.get("peak_objects"))
    mass = si(p.get("final_mass"))
    longest = si(p.get("longest_age"))
    emg = sf(p.get("emergence_score"))
    know = sf(p.get("knowledge_score"))
    fb = sf(p.get("feedback_score"))
    category = ss(p.get("analyzer_category"), "").lower()

    if (
        (peak <= 1 or mass <= 0)
        and emg < 0.15
        and know < 0.15
        and fb < 0.15
    ):
        return (
            "support",
            clamp01(0.75 + (0.15 - emg)),
            "low-life/static pattern kept separate from emergence",
        )

    if (peak <= 1 or mass <= 0) and emg >= 0.45:
        return (
            "counterexample",
            clamp01(emg),
            "high emergence assigned to almost lifeless pattern",
        )

    if "beautiful_dead" in category and emg < 0.20:
        return (
            "support",
            0.70,
            "beautiful/dead category correctly remains low emergence",
        )

    if longest > 100 and peak >= 3 and emg < 0.10:
        return (
            "counterexample",
            clamp01(longest / 1000.0),
            "nontrivial persistence may be under-scored",
        )

    return (
        "neutral",
        0.15,
        "not a clear pattern-life boundary case",
    )


def potential_gp104(p: dict[str, Any]) -> tuple[float, str]:
    peak = si(p.get("peak_objects"))
    mass = si(p.get("final_mass"))
    longest = si(p.get("longest_age"))
    emg = sf(p.get("emergence_score"))

    lifeless = (
        1.0
        if peak <= 1 or mass <= 0
        else max(0.0, 1.0 - peak / 5.0)
    )
    lifeless_high_emg = lifeless * max(0.0, emg - 0.20)
    persistence_under_scored = (
        min(1.0, longest / 10000.0)
        * max(0.0, 0.25 - emg)
    )

    if lifeless_high_emg >= persistence_under_scored:
        return (
            clamp01(lifeless_high_emg * 2.5),
            "near lifeless-pattern / elevated-EMG contradiction",
        )

    return (
        clamp01(persistence_under_scored * 2.5),
        "near persistent-life / under-scored-EMG contradiction",
    )


# ---------------------------------------------------------------------------
# GP-105: Civilization requires knowledge scaffold
# ---------------------------------------------------------------------------

def claim_civilization_requires_knowledge(
    p: dict[str, Any],
) -> tuple[str, float, str]:
    civ = sf(p.get("civilization_score"))
    know = sf(p.get("knowledge_score"))
    cities = si(p.get("civilization_cities"))
    tech = sf(p.get("civilization_tech"))
    culture = sf(p.get("civilization_culture"))

    if (
        civ >= 0.45
        and know >= 0.40
        and (cities >= 1 or tech >= 0.35 or culture >= 0.35)
    ):
        strength = (civ + know + max(tech, culture)) / 3.0
        return (
            "support",
            clamp01(strength),
            "civilization-like signal is accompanied by knowledge scaffold",
        )

    if civ >= 0.55 and know < 0.20:
        return (
            "counterexample",
            clamp01(civ * (1.0 - know)),
            "civilization-like signal without knowledge scaffold",
        )

    if know >= 0.55 and civ < 0.15:
        return (
            "neutral",
            clamp01(know * 0.20),
            "knowledge without civilization is allowed by the claim",
        )

    return (
        "neutral",
        clamp01(max(civ, know) * 0.20),
        "civilization-knowledge signal weak or incomplete",
    )


def potential_gp105(p: dict[str, Any]) -> tuple[float, str]:
    civ = sf(p.get("civilization_score"))
    know = sf(p.get("knowledge_score"))
    score = (
        max(0.0, civ - 0.35)
        * max(0.0, 0.40 - know)
        * 4.0
    )
    return (
        clamp01(score),
        "near high-CIV / low-KNOW contradiction",
    )


# ---------------------------------------------------------------------------
# GP-201: Memory-stability signature
# ---------------------------------------------------------------------------

def claim_memory_stability(
    p: dict[str, Any],
) -> tuple[str, float, str]:
    memory = sf(p.get("knowledge_memory"))
    memory_peak = sf(p.get("knowledge_memory_peak"), memory)
    stability = sf(p.get("stability_index"))
    repeatability = sf(p.get("validation_repeatability"))
    noise = sf(p.get("validation_noise_sensitivity"))
    collapsed = si(p.get("collapse_tick"), -1) >= 0

    if (
        memory >= 0.50
        and (stability >= 0.45 or repeatability >= 0.55)
        and noise <= 0.35
        and not collapsed
    ):
        strength = (
            memory
            + max(stability, repeatability)
            + (1.0 - noise)
        ) / 3.0
        return (
            "support",
            clamp01(strength),
            "memory is paired with stability/repeatability and low noise sensitivity",
        )

    if memory_peak >= 0.65 and collapsed:
        return (
            "counterexample",
            clamp01(memory_peak * (1.0 - 0.25 * stability)),
            "strong pre-collapse memory marker does not prevent collapse",
        )

    return (
        "neutral",
        clamp01(max(memory, stability, repeatability) * 0.20),
        "memory-stability relation unclear",
    )


def potential_gp201(p: dict[str, Any]) -> tuple[float, str]:
    memory = sf(p.get("knowledge_memory"))
    memory_peak = sf(p.get("knowledge_memory_peak"), memory)
    stability = sf(p.get("stability_index"))
    repeatability = sf(p.get("validation_repeatability"))
    collapsed = si(p.get("collapse_tick"), -1) >= 0

    instability = 1.0 - max(stability, repeatability)
    collapse_bonus = 0.25 if collapsed else 0.0
    score = (
        max(0.0, memory_peak - 0.40)
        * max(0.0, instability + collapse_bonus)
        * 2.0
    )
    return (
        clamp01(score),
        "near high-memory / low-stability contradiction",
    )


CLAIM_SPECS: dict[str, ClaimSpec] = {
    "GP-101": ClaimSpec(
        id="GP-101",
        title="Validated emergence criterion",
        description=(
            "High emergence should become credible only when validation "
            "quality is also high and false-positive risk is low."
        ),
        family="emergence_validation",
        test=claim_validated_emergence,
        potential=potential_gp101,
        search_targets=(
            {
                "name": "high_emg_low_validation",
                "constraints": {
                    "EMG": ">=0.65",
                    "VAL": "<0.35 or FP>0.45",
                },
            },
            {
                "name": "low_emg_false_negative",
                "constraints": {
                    "VAL": ">=0.75",
                    "EMG": "<0.20",
                    "FN": ">0.35",
                },
            },
        ),
        required_fields=(
            "emergence_score",
            "validation_quality",
            "validation_false_positive_risk",
            "validation_false_negative_risk",
        ),
        interpretation=(
            "Scientific credibility requires emergence and validation "
            "together; visual complexity alone is insufficient."
        ),
    ),
    "GP-102": ClaimSpec(
        id="GP-102",
        title="Knowledge-feedback coupling",
        description=(
            "Accumulated knowledge should often coincide with measurable "
            "feedback loops or knowledge impact."
        ),
        family="knowledge_feedback",
        test=claim_knowledge_feedback_coupling,
        potential=potential_gp102,
        search_targets=(
            {
                "name": "knowledge_without_feedback",
                "constraints": {
                    "KNOW": ">=0.65",
                    "FB": "<0.20",
                },
            },
            {
                "name": "feedback_without_knowledge",
                "constraints": {
                    "FB": ">=0.65",
                    "KNOW": "<0.20",
                },
            },
        ),
        required_fields=(
            "knowledge_score",
            "feedback_score",
            "feedback_metric_independence_status",
        ),
        interpretation=(
            "This is a coupling claim, not a claim that knowledge and "
            "feedback must always appear together."
        ),
    ),
    "GP-103": ClaimSpec(
        id="GP-103",
        title="Self-regulation marker",
        description=(
            "Self-regulating worlds should show feedback, self-direction, "
            "and reduced effective risk."
        ),
        family="feedback_regulation",
        test=claim_self_regulation_marker,
        potential=potential_gp103,
        search_targets=(
            {
                "name": "feedback_without_risk_reduction",
                "constraints": {
                    "FB": ">=0.60",
                    "effective_risk": ">0.60",
                },
            },
            {
                "name": "self_direction_without_feedback",
                "constraints": {
                    "self_direction": ">=0.60",
                    "FB": "<0.25",
                },
            },
        ),
        required_fields=(
            "feedback_score",
            "feedback_self_direction",
            "feedback_effective_risk",
            "feedback_metric_independence_status",
        ),
        interpretation=(
            "A high feedback score is insufficient unless feedback is "
            "directional and associated with lower effective risk."
        ),
    ),
    "GP-104": ClaimSpec(
        id="GP-104",
        title="Pattern-life separation",
        description=(
            "A visually rich but lifeless/static pattern should not be "
            "promoted to high emergence."
        ),
        family="validation_calibration",
        test=claim_pattern_life_separation,
        potential=potential_gp104,
        search_targets=(
            {
                "name": "lifeless_high_emergence",
                "constraints": {
                    "peak_objects": "<=1 or final_mass<=0",
                    "EMG": ">=0.45",
                },
            },
            {
                "name": "persistent_under_scored",
                "constraints": {
                    "longest_age": ">100",
                    "peak_objects": ">=3",
                    "EMG": "<0.10",
                },
            },
        ),
        required_fields=(
            "peak_objects",
            "final_mass",
            "longest_age",
            "emergence_score",
            "knowledge_score",
            "feedback_score",
        ),
        interpretation=(
            "This is an Observer calibration claim. Supporting cases are "
            "reference controls, not independent evidence for a universal "
            "law of life."
        ),
    ),
    "GP-105": ClaimSpec(
        id="GP-105",
        title="Civilization requires knowledge scaffold",
        description=(
            "Civilization-like organization should be accompanied by "
            "knowledge, tech, culture, or cities."
        ),
        family="civilization_knowledge",
        test=claim_civilization_requires_knowledge,
        potential=potential_gp105,
        search_targets=(
            {
                "name": "civilization_without_knowledge",
                "constraints": {
                    "CIV": ">=0.55",
                    "KNOW": "<0.20",
                },
            },
        ),
        required_fields=(
            "civilization_score",
            "knowledge_score",
        ),
        interpretation=(
            "Civilization-like structure without a knowledge scaffold should "
            "be treated as a weaker or conflicting interpretation."
        ),
    ),
    "GP-201": ClaimSpec(
        id="GP-201",
        title="Memory-stability genome signature",
        description=(
            "Knowledge memory should be associated with stability, "
            "repeatability, and low noise sensitivity."
        ),
        family="memory_stability",
        test=claim_memory_stability,
        potential=potential_gp201,
        search_targets=(
            {
                "name": "memory_with_collapse",
                "constraints": {
                    "memory": ">=0.65",
                    "collapsed": True,
                },
            },
            {
                "name": "memory_without_stability",
                "constraints": {
                    "memory": ">=0.65",
                    "collapsed": False,
                    "stability": "<0.25",
                },
            },
        ),
        required_fields=(
            "knowledge_memory",
            "knowledge_memory_peak",
            "stability_index",
            "validation_repeatability",
            "validation_noise_sensitivity",
            "collapse_tick",
        ),
        allow_none_fields=("collapse_tick",),
        interpretation=(
            "Observer repeatability is not equivalent to independent "
            "multi-seed replication."
        ),
    ),
}


CLAIM_ORDER: tuple[str, ...] = tuple(CLAIM_SPECS)


def iter_claim_specs() -> tuple[ClaimSpec, ...]:
    return tuple(CLAIM_SPECS[claim_id] for claim_id in CLAIM_ORDER)


def get_claim_spec(claim_id: str) -> ClaimSpec:
    try:
        return CLAIM_SPECS[claim_id]
    except KeyError as exc:
        raise KeyError(f"Unknown scientific claim: {claim_id}") from exc


def evaluate_claim(
    claim_id: str,
    profile: dict[str, Any],
) -> tuple[str, float, str]:
    spec = get_claim_spec(claim_id)
    return _guarded_test(spec, profile)


def evaluate_near_counterexample(
    claim_id: str,
    profile: dict[str, Any],
) -> tuple[float, str]:
    spec = get_claim_spec(claim_id)
    return _guarded_potential(spec, profile)


# ---------------------------------------------------------------------------
# Compatibility exports for gradual engine migration.
# ---------------------------------------------------------------------------

CLAIMS: list[
    tuple[
        str,
        str,
        str,
        ClaimTest,
    ]
] = [
    (
        spec.id,
        spec.title,
        spec.description,
        (lambda profile, _spec=spec: _guarded_test(_spec, profile)),
    )
    for spec in iter_claim_specs()
]

POTENTIAL: dict[str, PotentialTest] = {
    spec.id: (lambda profile, _spec=spec: _guarded_potential(_spec, profile))
    for spec in iter_claim_specs()
}

TARGETS: dict[str, list[dict[str, Any]]] = {
    spec.id: [
        {
            "name": target["name"],
            "constraints": dict(target["constraints"]),
        }
        for target in spec.search_targets
    ]
    for spec in iter_claim_specs()
}
