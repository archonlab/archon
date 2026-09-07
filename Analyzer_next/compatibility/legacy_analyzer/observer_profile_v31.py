#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
observer_profile_v31.py

Analyzer v30 Step 2: Observer Profile v31 Parser.

Reads modern Observer passport JSON files from a shared results workspace and
builds one normalized profile per rule. This is the bridge between the new
Observer layers and the older Analyzer engines.

Expected input:
    universe_search_v23_results/
        observation_logs/
            rule_00252_YYYYMMDD_HHMMSS_passport.json
            rule_00252_YYYYMMDD_HHMMSS_passport.md

Outputs, written into the results folder:
    observer_profiles_v31.json
    observer_profiles_v31.md

Usage:
    python observer_profile_v31.py ../universe_search_v23_results
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.compatibility.legacy_analyzer.ontology_profile_shadow import (
    classify_ontology_shadow,
)
from Scientific_Ontology.lifecycle_reconciliation import reconcile_lifecycle_contract


CONF_RANK = {
    "NONE": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "VERY_HIGH": 4,
}


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def norm_conf(value: Any) -> str:
    s = str(value or "NONE").strip().upper().replace(" ", "_")
    return s if s in CONF_RANK else "NONE"


def split_csv_words(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "-"}:
        return []
    return [p.strip() for p in re.split(r"[,;|]+", text) if p.strip()]


def get_life(data: dict[str, Any]) -> dict[str, Any]:
    life = data.get("life")
    return life if isinstance(life, dict) else {}


def get_metrics(data: dict[str, Any]) -> dict[str, Any]:
    metrics = data.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def get_observer_state(data: dict[str, Any]) -> dict[str, Any]:
    state = data.get("observer_state")
    return state if isinstance(state, dict) else {}


def get_nested(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    return value if isinstance(value, dict) else {}


def safe_mapping(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, item in value.items():
        try:
            result[str(key)] = float(item)
        except (TypeError, ValueError):
            continue
    return result


def safe_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


@dataclass
class ObserverProfile:
    source_file: str
    rule: str
    created: Optional[str]
    score: float
    source: Optional[str]
    generation: int
    seed: Optional[int]
    experiment_id: str

    # Stage 1D ontology contract. These fields are additive and do not yet
    # replace legacy Analyzer classifications.
    ontology_version: str
    observer_state_schema_version: str
    observer_state_tick: int
    observer_state_world_id: str
    observer_state_run_id: str
    observer_state_observer_version: str

    life_state: str
    life_status: str
    life_score: float
    life_confidence: float
    life_uncertainty: float
    life_winner: str
    life_runner_up: str
    life_margin: float
    life_gate_passed: Optional[bool]
    life_axes: dict[str, float]
    life_hypotheses: dict[str, float]
    life_warnings: list[str]

    structural_state: str
    structural_confidence: float
    structure_birth_tick: Optional[int]
    structural_extinction_tick: Optional[int]
    ecology_state: str
    ecology_population_state: str
    ecology_confidence: float
    identity_state: str
    identity_confidence: float
    knowledge_state: str
    knowledge_confidence: float

    # Stage 2C typed lifecycle summary. Descriptive shadow data only.
    lifecycle_summary_schema_version: str
    lifecycle_history_status: str
    lifecycle_history_complete: bool
    lifecycle_observed_through_tick: Optional[int]
    lifecycle_phase: str
    lifecycle_event_count: int
    lifecycle_event_types: list[str]
    lifecycle_first_ticks: dict[str, int]
    lifecycle_latest_event_type: Optional[str]
    lifecycle_latest_event_tick: Optional[int]
    lifecycle_canonical_source: str
    lifecycle_verification_status: str
    lifecycle_mismatch_fields: list[str]
    lifecycle_temporal_integrity_status: str
    lifecycle_temporal_issue_codes: list[str]
    lifecycle_temporal_issues: list[dict[str, Any]]
    lifecycle_events: list[dict[str, Any]]

    # Stage 1F shadow classification. This is deliberately separate from
    # analyzer_category and is not consumed by legacy Analyzer modules.
    ontology_shadow_schema_version: str
    ontology_shadow_category: str
    ontology_shadow_status: str
    ontology_shadow_confidence: float
    ontology_shadow_reasons: list[str]
    ontology_shadow_warnings: list[str]
    ontology_shadow_legacy_relation: str

    # Life / family base
    final_tick: int
    birth_tick: Optional[int]
    collapse_tick: Optional[int]
    longest_age: int
    peak_objects: int
    peak_largest: int
    final_mass: int
    stability_index: float
    family_count: int
    deepest_generation: int
    oldest_lineage_age: int
    dynasty_mass: int
    demo_survival_ratio: float

    # Evolution pressure
    evo_phase: str
    evo_stress: float
    evo_adapt: float
    evo_pressure: float
    evo_risk: float
    evo_cause: str

    # Civilization layer
    civilization_stage: str
    civilization_score: float
    civilization_peak: float
    civilization_age: int
    civilization_cities: int
    civilization_urbanization: float
    civilization_trade: float
    civilization_conflict: float
    civilization_cohesion: float
    civilization_specialization: float
    civilization_tech: float
    civilization_culture: float
    civilization_collapse_risk: float

    # Knowledge layer
    knowledge_score: float
    knowledge_peak: float
    knowledge_age: int
    knowledge_families: int
    knowledge_axis: str
    knowledge_exploration: float
    knowledge_cooperation: float
    knowledge_aggression: float
    knowledge_efficiency: float
    knowledge_adaptation: float
    knowledge_memory: float
    knowledge_memory_peak: float
    knowledge_memory_peak_tick: int | None
    knowledge_transfer: float
    knowledge_loss: float
    knowledge_discoveries: list[str]

    # Feedback layer
    feedback_regime: str
    feedback_score: float
    feedback_peak: float
    feedback_survival_bonus: float
    feedback_pressure_buffer: float
    feedback_effective_pressure: float
    feedback_effective_risk: float
    feedback_self_direction: float
    feedback_environment_impact: float
    feedback_knowledge_impact: float
    feedback_response_capacity: float
    feedback_response_opportunity: float
    feedback_observed_response: float
    feedback_legacy_score: float
    feedback_metric_version: str
    feedback_metric_independence_status: str

    # Emergence evidence
    emergence_confidence: str
    emergence_score: float
    emergence_peak: float
    emergence_evidence_count: int
    emergence_positive: list[str]
    emergence_negative: list[str]
    emergence_complexity: float
    emergence_stability: float

    # Validation / calibration
    validation_grade: str
    validation_quality: float
    validation_peak: float
    validation_repeatability: float
    validation_stability_confidence: float
    validation_false_positive_risk: float
    validation_false_negative_risk: float
    validation_noise_sensitivity: float
    validation_warning: str
    validation_explain: list[str]

    # Derived v30 summary
    layer_stack_score: float
    scientific_confidence: str
    analyzer_category: str
    key_reasons: list[str]
    warnings: list[str]

    # Evidence routing is additive. Legacy consumers can ignore these fields.
    telemetry_run_status: str = "unverified"
    evidence_channel: str = "legacy_unverified_observational"
    observational_eligible: bool = True
    evidence_exclusion_reason: Optional[str] = None
    telemetry_experiment_id: Optional[str] = None
    telemetry_condition_id: Optional[str] = None
    telemetry_experiment_role: Optional[str] = None


def derive_summary(p: dict[str, Any]) -> tuple[float, str, str, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []

    life = min(1.0, safe_float(p.get("longest_age")) / 500.0) if safe_float(p.get("longest_age")) else 0.0
    families = min(1.0, safe_float(p.get("family_count")) / 5.0)
    dyn = min(1.0, safe_float(p.get("deepest_generation")) / 5.0)
    civ = safe_float(p.get("civilization_score"))
    know = safe_float(p.get("knowledge_score"))
    fb = safe_float(p.get("feedback_score"))
    emg = safe_float(p.get("emergence_score"))
    val = safe_float(p.get("validation_quality"))
    stability = safe_float(p.get("stability_index"))

    score = (
        0.10 * life
        + 0.10 * families
        + 0.08 * dyn
        + 0.12 * civ
        + 0.15 * know
        + 0.15 * fb
        + 0.18 * emg
        + 0.08 * val
        + 0.04 * stability
    )
    score = max(0.0, min(1.0, score))

    emg_conf = norm_conf(p.get("emergence_confidence"))
    val_grade = norm_conf(p.get("validation_grade"))

    if safe_int(p.get("collapse_tick"), -1) >= 0:
        warnings.append("collapsed")
    if safe_float(p.get("validation_false_positive_risk")) >= 0.35:
        warnings.append("possible_false_positive")
    if safe_float(p.get("validation_false_negative_risk")) >= 0.35:
        warnings.append("possible_false_negative")
    if safe_float(p.get("validation_noise_sensitivity")) >= 0.45:
        warnings.append("noise_sensitive")
    if str(p.get("validation_warning") or "").lower() not in {"", "ok", "none"}:
        warnings.append(str(p.get("validation_warning")))

    if safe_float(p.get("knowledge_score")) >= 0.5:
        reasons.append("knowledge")
    if safe_float(p.get("feedback_score")) >= 0.5:
        reasons.append("feedback")
    if CONF_RANK[emg_conf] >= CONF_RANK["HIGH"]:
        reasons.append("emergence")
    if CONF_RANK[val_grade] >= CONF_RANK["HIGH"]:
        reasons.append("validation")
    if safe_int(p.get("family_count")) >= 4:
        reasons.append("families")
    if safe_int(p.get("deepest_generation")) >= 3:
        reasons.append("generations")
    if safe_float(p.get("civilization_score")) >= 0.45:
        reasons.append("civilization")

    if score >= 0.75 and CONF_RANK[val_grade] >= 3:
        sci = "VERY_HIGH"
    elif score >= 0.60 and CONF_RANK[val_grade] >= 2:
        sci = "HIGH"
    elif score >= 0.40:
        sci = "MEDIUM"
    elif score >= 0.18:
        sci = "LOW"
    else:
        sci = "NONE"

    if safe_float(p.get("emergence_score")) >= 0.60 and safe_float(p.get("validation_quality")) >= 0.60:
        category = "credible_emergent_organization"
    elif safe_float(p.get("feedback_score")) >= 0.55:
        category = "adaptive_feedback_candidate"
    elif safe_float(p.get("knowledge_score")) >= 0.50:
        category = "knowledge_accumulation_candidate"
    elif safe_float(p.get("civilization_score")) >= 0.45:
        category = "civilization_like_candidate"
    elif safe_int(p.get("peak_objects")) <= 1 and safe_float(p.get("emergence_score")) < 0.1:
        category = "beautiful_dead_or_static_world"
    elif safe_int(p.get("collapse_tick"), -1) >= 0:
        category = "collapsed_world"
    else:
        category = "weak_or_unclear_signal"

    return round(score, 6), sci, category, reasons, warnings



def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def build_experiment_id(
    *,
    path: Path,
    rule: str,
    seed: Optional[int],
    created: Optional[str],
    source: Optional[str],
) -> str:
    """
    Build a stable identifier for one passport-producing run.

    Prefer an explicit identifier from the passport when available. Otherwise
    hash stable passport identity fields. This identifies a record/run, not an
    independently replicated scientific result.
    """
    identity = "|".join(
        [
            rule,
            str(seed) if seed is not None else "",
            str(created or ""),
            str(source or ""),
            path.name,
        ]
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    return f"EXP-{rule}-{digest}"

def profile_from_passport(path: Path) -> ObserverProfile:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    life = get_life(data)
    observer_state = get_observer_state(data)
    state_life = get_nested(observer_state, "life")
    state_structure = get_nested(observer_state, "structure")
    state_ecology = get_nested(observer_state, "ecology")
    state_identity = get_nested(observer_state, "identity")
    state_knowledge = get_nested(observer_state, "knowledge")
    lifecycle_contract = reconcile_lifecycle_contract(
        data.get("lifecycle_summary")
        if isinstance(data.get("lifecycle_summary"), dict)
        else None,
        observer_state or None,
    )
    lifecycle = lifecycle_contract["summary"]

    rule = str(
        data.get("rule_id")
        if data.get("rule_id") is not None
        else "unknown"
    ).zfill(5)
    seed = _optional_int(
        data.get("seed")
        if data.get("seed") is not None
        else life.get("seed")
    )
    created = data.get("created")
    source = data.get("source")
    explicit_experiment_id = (
        data.get("experiment_id")
        or data.get("run_id")
        or data.get("observation_id")
    )
    experiment_id = str(explicit_experiment_id or build_experiment_id(
        path=path,
        rule=rule,
        seed=seed,
        created=created,
        source=source,
    ))

    base: dict[str, Any] = {
        "source_file": str(path),
        "rule": rule,
        "created": created,
        "score": safe_float(data.get("score")),
        "source": source,
        "generation": safe_int(data.get("generation")),
        "seed": seed,
        "experiment_id": experiment_id,
        "ontology_version": str(
            observer_state.get("metadata", {}).get("ontology_version", "1.0.0")
            if isinstance(observer_state.get("metadata"), dict)
            else "1.0.0"
        ),
        "observer_state_schema_version": str(observer_state.get("schema_version") or "legacy-unavailable"),
        "observer_state_tick": safe_int(observer_state.get("tick"), safe_int(life.get("final_tick_observed"))),
        "observer_state_world_id": str(observer_state.get("world_id") or rule),
        "observer_state_run_id": str(observer_state.get("run_id") or experiment_id),
        "observer_state_observer_version": str(observer_state.get("observer_version") or "unknown"),
        "life_state": str(
            state_life.get("state")
            or life.get("life_evidence_verdict_final")
            or "unknown"
        ).strip().lower(),
        "life_status": str(state_life.get("status") or ("provisional" if life.get("life_evidence_verdict_final") is not None else "not_evaluated")),
        "life_score": safe_float(state_life.get("score"), safe_float(life.get("life_evidence_score_final"))),
        "life_confidence": safe_float(state_life.get("confidence"), safe_float(life.get("life_evidence_confidence_final"))),
        "life_uncertainty": safe_float(state_life.get("uncertainty"), safe_float(life.get("life_evidence_uncertainty_final"), 1.0)),
        "life_winner": str(state_life.get("winner") or life.get("life_evidence_winner_final") or ""),
        "life_runner_up": str(state_life.get("runner_up") or life.get("life_evidence_runner_up_final") or ""),
        "life_margin": safe_float(state_life.get("margin"), safe_float(life.get("life_evidence_margin_final"))),
        "life_gate_passed": safe_bool(state_life.get("gate_passed") if "gate_passed" in state_life else life.get("life_evidence_gate_passed_final")),
        "life_axes": safe_mapping(state_life.get("axes") or life.get("life_evidence_axes_final")),
        "life_hypotheses": safe_mapping(state_life.get("hypotheses") or life.get("life_evidence_hypotheses_final")),
        "life_warnings": split_csv_words(state_life.get("warnings") or life.get("life_evidence_warnings_final")),
        "structural_state": str(state_structure.get("state") or "unknown"),
        "structural_confidence": safe_float(state_structure.get("confidence")),
        "structure_birth_tick": _optional_int(state_structure.get("structure_birth_tick")),
        "structural_extinction_tick": _optional_int(state_structure.get("structural_extinction_tick")),
        "ecology_state": str(state_ecology.get("state") or "unknown"),
        "ecology_population_state": str(state_ecology.get("population_state") or "unknown"),
        "ecology_confidence": safe_float(state_ecology.get("confidence")),
        "identity_state": str(state_identity.get("state") or "unknown"),
        "identity_confidence": safe_float(state_identity.get("confidence")),
        "knowledge_state": str(state_knowledge.get("state") or "unknown"),
        "knowledge_confidence": safe_float(state_knowledge.get("confidence")),
        "lifecycle_summary_schema_version": str(lifecycle.get("schema_version") or "1.0.0"),
        "lifecycle_history_status": str(lifecycle.get("history_status") or "unavailable"),
        "lifecycle_history_complete": bool(lifecycle.get("history_complete_for_supported_types")),
        "lifecycle_observed_through_tick": _optional_int(lifecycle.get("observed_through_tick")),
        "lifecycle_phase": str(lifecycle.get("phase") or "unavailable"),
        "lifecycle_event_count": safe_int(lifecycle.get("event_count")),
        "lifecycle_event_types": split_csv_words(lifecycle.get("event_types")),
        "lifecycle_first_ticks": {
            str(key): safe_int(value)
            for key, value in (lifecycle.get("first_ticks") or {}).items()
        },
        "lifecycle_latest_event_type": (
            str(lifecycle.get("latest_event_type"))
            if lifecycle.get("latest_event_type") is not None
            else None
        ),
        "lifecycle_latest_event_tick": _optional_int(lifecycle.get("latest_event_tick")),
        "lifecycle_canonical_source": str(lifecycle_contract["canonical_source"]),
        "lifecycle_verification_status": str(lifecycle_contract["verification_status"]),
        "lifecycle_mismatch_fields": [
            str(field) for field in lifecycle_contract["mismatch_fields"]
        ],
        "lifecycle_temporal_integrity_status": str(
            lifecycle_contract.get("temporal_integrity", {}).get(
                "status", "unavailable"
            )
        ),
        "lifecycle_temporal_issue_codes": [
            str(code)
            for code in lifecycle_contract.get(
                "temporal_integrity", {}
            ).get("issue_codes", [])
        ],
        "lifecycle_temporal_issues": list(
            lifecycle_contract.get("temporal_integrity", {}).get(
                "issues", []
            )
        ),
        "lifecycle_events": list(lifecycle_contract["events"]),
        "final_tick": safe_int(life.get("final_tick_observed")),
        "birth_tick": life.get("birth_tick"),
        "collapse_tick": life.get("collapse_tick"),
        "longest_age": safe_int(life.get("longest_observed_age")),
        "peak_objects": safe_int(life.get("peak_objects")),
        "peak_largest": safe_int(life.get("peak_largest_object_cells")),
        "final_mass": safe_int(life.get("final_total_living_mass")),
        "stability_index": safe_float(life.get("stability_index_final")),
        "family_count": safe_int(life.get("active_families_final")),
        "deepest_generation": safe_int(life.get("deepest_generation_final")),
        "oldest_lineage_age": safe_int(life.get("oldest_lineage_age_final")),
        "dynasty_mass": safe_int(life.get("dynasty_mass_final")),
        "demo_survival_ratio": safe_float(life.get("demo_survival_ratio_final")),
        "evo_phase": str(life.get("evo_phase_final") or ""),
        "evo_stress": safe_float(life.get("evo_stress_final")),
        "evo_adapt": safe_float(life.get("evo_adapt_final")),
        "evo_pressure": safe_float(life.get("evo_pressure_final")),
        "evo_risk": safe_float(life.get("evo_extinction_risk_final")),
        "evo_cause": str(life.get("evo_cause_final") or ""),
        "civilization_stage": str(life.get("civilization_stage_final") or "NONE"),
        "civilization_score": safe_float(life.get("civilization_score_final")),
        "civilization_peak": safe_float(life.get("civilization_peak_score")),
        "civilization_age": safe_int(life.get("civilization_age_final")),
        "civilization_cities": safe_int(life.get("civilization_cities_final")),
        "civilization_urbanization": safe_float(life.get("civilization_urbanization_final")),
        "civilization_trade": safe_float(life.get("civilization_trade_index_final")),
        "civilization_conflict": safe_float(life.get("civilization_conflict_index_final")),
        "civilization_cohesion": safe_float(life.get("civilization_cohesion_final")),
        "civilization_specialization": safe_float(life.get("civilization_specialization_final")),
        "civilization_tech": safe_float(life.get("civilization_tech_index_final")),
        "civilization_culture": safe_float(life.get("civilization_culture_index_final")),
        "civilization_collapse_risk": safe_float(life.get("civilization_collapse_risk_final")),
        "knowledge_score": safe_float(life.get("knowledge_score_final")),
        "knowledge_peak": safe_float(life.get("knowledge_peak_score")),
        "knowledge_age": safe_int(life.get("knowledge_age_final")),
        "knowledge_families": safe_int(life.get("knowledge_families_final")),
        "knowledge_axis": str(life.get("knowledge_dominant_axis_final") or "none"),
        "knowledge_exploration": safe_float(life.get("knowledge_exploration_final")),
        "knowledge_cooperation": safe_float(life.get("knowledge_cooperation_final")),
        "knowledge_aggression": safe_float(life.get("knowledge_aggression_final")),
        "knowledge_efficiency": safe_float(life.get("knowledge_efficiency_final")),
        "knowledge_adaptation": safe_float(life.get("knowledge_adaptation_final")),
        "knowledge_memory": safe_float(life.get("knowledge_memory_final")),
        "knowledge_memory_peak": safe_float(
            life.get(
                "knowledge_memory_peak",
                max(
                    (
                        safe_float(item.get("knowledge_memory"))
                        for item in life.get("knowledge_recent_history", [])
                        if isinstance(item, dict)
                    ),
                    default=safe_float(life.get("knowledge_memory_final")),
                ),
            )
        ),
        "knowledge_memory_peak_tick": (
            safe_int(life.get("knowledge_memory_peak_tick"))
            if life.get("knowledge_memory_peak_tick") is not None
            else None
        ),
        "knowledge_transfer": safe_float(life.get("knowledge_transfer_final")),
        "knowledge_loss": safe_float(life.get("knowledge_loss_final")),
        "knowledge_discoveries": split_csv_words(life.get("knowledge_discoveries")),
        "feedback_regime": str(life.get("feedback_regime_final") or "NONE"),
        "feedback_score": safe_float(life.get("feedback_score_final")),
        "feedback_peak": safe_float(life.get("feedback_peak_score")),
        "feedback_survival_bonus": safe_float(life.get("feedback_survival_bonus_final")),
        "feedback_pressure_buffer": safe_float(life.get("feedback_pressure_buffer_final")),
        "feedback_effective_pressure": safe_float(life.get("feedback_effective_pressure_final")),
        "feedback_effective_risk": safe_float(life.get("feedback_effective_risk_final")),
        "feedback_self_direction": safe_float(life.get("feedback_self_direction_final")),
        "feedback_environment_impact": safe_float(life.get("feedback_environment_impact_final")),
        "feedback_knowledge_impact": safe_float(life.get("feedback_knowledge_impact_final")),
        "feedback_response_capacity": safe_float(
            life.get("feedback_response_capacity_final")
        ),
        "feedback_response_opportunity": safe_float(
            life.get("feedback_response_opportunity_final")
        ),
        "feedback_observed_response": safe_float(
            life.get("feedback_observed_response_final")
        ),
        "feedback_legacy_score": safe_float(
            life.get("feedback_legacy_score_final")
        ),
        "feedback_metric_version": str(
            life.get("feedback_metric_version") or "1.0"
        ),
        "feedback_metric_independence_status": str(
            life.get("feedback_metric_independence_status")
            or "LEGACY_COUPLED_V1"
        ),
        "emergence_confidence": norm_conf(life.get("emergence_confidence_final")),
        "emergence_score": safe_float(life.get("emergence_score_final")),
        "emergence_peak": safe_float(life.get("emergence_peak_score")),
        "emergence_evidence_count": safe_int(life.get("emergence_evidence_count_final")),
        "emergence_positive": split_csv_words(life.get("emergence_positive_evidence_final")),
        "emergence_negative": split_csv_words(life.get("emergence_negative_evidence_final")),
        "emergence_complexity": safe_float(life.get("emergence_complexity_index_final")),
        "emergence_stability": safe_float(life.get("emergence_stability_signal_final")),
        "validation_grade": norm_conf(life.get("validation_grade_final")),
        "validation_quality": safe_float(life.get("validation_quality_final")),
        "validation_peak": safe_float(life.get("validation_quality_peak")),
        "validation_repeatability": safe_float(life.get("validation_repeatability_final")),
        "validation_stability_confidence": safe_float(life.get("validation_stability_confidence_final")),
        "validation_false_positive_risk": safe_float(life.get("validation_false_positive_risk_final")),
        "validation_false_negative_risk": safe_float(life.get("validation_false_negative_risk_final")),
        "validation_noise_sensitivity": safe_float(life.get("validation_noise_sensitivity_final")),
        "validation_warning": str(life.get("validation_warning_final") or ""),
        "validation_explain": split_csv_words(life.get("validation_explain_final")),
    }

    layer_score, sci_conf, category, reasons, warnings = derive_summary(base)
    base.update(
        layer_stack_score=layer_score,
        scientific_confidence=sci_conf,
        analyzer_category=category,
        key_reasons=reasons,
        warnings=warnings,
    )
    base.update(classify_ontology_shadow(base))
    return ObserverProfile(**base)


def collect_passport_json(results_folder: Path) -> list[Path]:
    logs = results_folder / "observation_logs"
    roots = [logs] if logs.exists() else [results_folder]
    files: list[Path] = []
    for root in roots:
        files.extend(sorted(root.rglob("*passport.json")))
    return files


def profile_rank(profile: ObserverProfile) -> tuple[int, int, float]:
    """
    Rank a representative profile for backward-compatible consumers.

    The complete history is preserved separately. This ranking only chooses
    the legacy `profiles` view.
    """
    try:
        stamp = Path(profile.source_file).stat().st_mtime
    except OSError:
        stamp = 0.0

    return (
        max(profile.longest_age, profile.final_tick),
        profile.final_tick,
        stamp,
    )


def group_profiles_by_rule(
    profiles: list[ObserverProfile],
) -> dict[str, list[ObserverProfile]]:
    grouped: dict[str, list[ObserverProfile]] = {}
    for profile in profiles:
        grouped.setdefault(profile.rule, []).append(profile)

    for records in grouped.values():
        records.sort(key=profile_rank, reverse=True)

    return grouped


def select_representative_profiles(
    profiles_by_rule: dict[str, list[ObserverProfile]],
) -> list[ObserverProfile]:
    representatives: list[ObserverProfile] = []
    for _, records in sorted(profiles_by_rule.items()):
        eligible = [
            profile
            for profile in records
            if profile.observational_eligible
        ]
        if eligible:
            representatives.append(eligible[0])
    return representatives


def build_profile_records(
    files: list[Path],
) -> tuple[list[ObserverProfile], list[str]]:
    records: list[ObserverProfile] = []
    failures: list[str] = []

    for path in files:
        try:
            records.append(profile_from_passport(path))
        except Exception as exc:
            failures.append(f"{path}: {exc}")
            print(f"[WARN] Failed to profile {path}: {exc}")

    return records, failures


def _profile_run_id(profile: ObserverProfile) -> str:
    run_id = str(profile.observer_state_run_id or "").strip()
    if run_id and not run_id.startswith("EXP-"):
        return run_id

    name = Path(profile.source_file).name
    suffix = "_passport.json"
    if name.endswith(suffix):
        return name[:-len(suffix)]
    return run_id


def annotate_scientific_provenance(
    profiles: list[ObserverProfile],
    telemetry_database: Path | None,
) -> tuple[list[ObserverProfile], dict[str, int]]:
    """Route completed canonical runs into observational evidence.

    If a Telemetry database exists, provenance is fail-closed: unresolved,
    incomplete, experimental, and mutation runs remain in ``profile_records``
    but cannot become the representative observational profile for a rule.
    """
    summary = {
        "canonical_completed": 0,
        "canonical_live_completed": 0,
        "canonical_imported": 0,
        "experimental_excluded": 0,
        "mutation_excluded": 0,
        "incomplete_excluded": 0,
        "unresolved_excluded": 0,
        "legacy_unverified": 0,
    }
    if telemetry_database is None or not telemetry_database.is_file():
        summary["legacy_unverified"] = len(profiles)
        return profiles, summary

    try:
        from Storage.query_api import (
            TelemetryQueryAPI,
            TelemetryQueryError,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Telemetry SQLite exists but Storage.query_api is unavailable"
        ) from exc

    annotated: list[ObserverProfile] = []
    with TelemetryQueryAPI(telemetry_database) as api:
        for profile in profiles:
            try:
                context = api.get_scientific_run_context(
                    _profile_run_id(profile)
                )
            except TelemetryQueryError:
                annotated.append(replace(
                    profile,
                    telemetry_run_status="unresolved",
                    evidence_channel="excluded",
                    observational_eligible=False,
                    evidence_exclusion_reason="RUN_NOT_FOUND_IN_TELEMETRY",
                ))
                summary["unresolved_excluded"] += 1
                continue

            if context.observational_eligible:
                channel = "canonical_observational"
                summary["canonical_completed"] += 1
                if context.status == "imported":
                    summary["canonical_imported"] += 1
                else:
                    summary["canonical_live_completed"] += 1
            elif context.is_mutation:
                channel = "perturbation"
                summary["mutation_excluded"] += 1
            elif context.is_experimental:
                channel = "experimental"
                summary["experimental_excluded"] += 1
            else:
                channel = "excluded"
                summary["incomplete_excluded"] += 1

            annotated.append(replace(
                profile,
                telemetry_run_status=context.status,
                evidence_channel=channel,
                observational_eligible=context.observational_eligible,
                evidence_exclusion_reason=context.exclusion_reason,
                telemetry_experiment_id=context.experiment_id,
                telemetry_condition_id=context.condition_id,
                telemetry_experiment_role=context.role,
            ))

    return annotated, summary


def select_latest_by_rule(files: list[Path]) -> tuple[list[Path], int]:
    """
    Legacy compatibility helper.

    New code should use build_profile_records(), group_profiles_by_rule(), and
    select_representative_profiles().
    """
    records, _ = build_profile_records(files)
    grouped = group_profiles_by_rule(records)
    representatives = select_representative_profiles(grouped)
    paths = [Path(profile.source_file) for profile in representatives]
    return paths, max(0, len(files) - len(paths))

def render_markdown(profiles: list[ObserverProfile], all_count: int, skipped: int) -> str:
    rows = sorted(profiles, key=lambda p: p.layer_stack_score, reverse=True)
    lines = [
        "# Observer Profiles v31",
        "",
        "Normalized profile layer for modern Universe Search Observer passports.",
        "",
        "## Summary",
        "",
        f"- Passport JSON files scanned: **{all_count}**",
        f"- Unique rules profiled: **{len(rows)}**",
        f"- Additional passport records retained in JSON history: **{skipped}**",
        "",
        "| Rule | Life state | Life conf | Structure | Legacy category | Ontology shadow | Relation | Sci conf | Layer score | EMG | VAL | KNOW | FB | CIV | Reasons | Warnings |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for p in rows:
        reasons = ", ".join(p.key_reasons) if p.key_reasons else "-"
        warnings = ", ".join(p.warnings) if p.warnings else "-"
        lines.append(
            f"| {p.rule} | {p.life_state} | {p.life_confidence:.3f} | {p.structural_state} | "
            f"{p.analyzer_category} | {p.ontology_shadow_category} "
            f"({p.ontology_shadow_confidence:.3f}) | {p.ontology_shadow_legacy_relation} | "
            f"{p.scientific_confidence} | "
            f"{p.layer_stack_score:.3f} | {p.emergence_score:.3f} {p.emergence_confidence} | "
            f"{p.validation_quality:.3f} {p.validation_grade} | {p.knowledge_score:.3f} | "
            f"{p.feedback_score:.3f} | {p.civilization_score:.3f} | {reasons} | {warnings} |"
        )

    lines.extend(["", "## Rule Details", ""])
    for p in rows:
        lines.extend([
            f"### Rule {p.rule}",
            "",
            f"- Category: **{p.analyzer_category}**",
            f"- Ontology shadow category: **{p.ontology_shadow_category}** ({p.ontology_shadow_status}, confidence={p.ontology_shadow_confidence:.3f})",
            f"- Shadow/legacy relation: **{p.ontology_shadow_legacy_relation}**",
            f"- Shadow reasons: {', '.join(p.ontology_shadow_reasons) if p.ontology_shadow_reasons else '-'}",
            f"- Shadow warnings: {', '.join(p.ontology_shadow_warnings) if p.ontology_shadow_warnings else '-'}",
            f"- Scientific confidence: **{p.scientific_confidence}**",
            f"- Layer stack score: **{p.layer_stack_score:.3f}**",
            f"- Ontology state: life={p.life_state}, score={p.life_score:.3f}, confidence={p.life_confidence:.3f}, uncertainty={p.life_uncertainty:.3f}",
            f"- Structural/ecology state: structure={p.structural_state}, ecology={p.ecology_state}, identity={p.identity_state}, knowledge={p.knowledge_state}",
            f"- Typed lifecycle (shadow): phase={p.lifecycle_phase}, events={p.lifecycle_event_count}, first_ticks={p.lifecycle_first_ticks}, history={p.lifecycle_history_status}",
            f"- Lifecycle contract: source={p.lifecycle_canonical_source}, verification={p.lifecycle_verification_status}, mismatches={', '.join(p.lifecycle_mismatch_fields) if p.lifecycle_mismatch_fields else '-'}",
            f"- Lifecycle temporal integrity: status={p.lifecycle_temporal_integrity_status}, issues={', '.join(p.lifecycle_temporal_issue_codes) if p.lifecycle_temporal_issue_codes else '-'}",
            f"- Life evidence: winner={p.life_winner or '-'}, runner_up={p.life_runner_up or '-'}, margin={p.life_margin:.3f}, warnings={', '.join(p.life_warnings) if p.life_warnings else '-'}",
            f"- Legacy life metrics: longest_age={p.longest_age}, peak_objects={p.peak_objects}, families={p.family_count}, generations={p.deepest_generation}",
            f"- Civilization: stage={p.civilization_stage}, score={p.civilization_score:.3f}, cities={p.civilization_cities}, tech={p.civilization_tech:.3f}, culture={p.civilization_culture:.3f}",
            f"- Knowledge: score={p.knowledge_score:.3f}, axis={p.knowledge_axis}, discoveries={', '.join(p.knowledge_discoveries) if p.knowledge_discoveries else '-'}",
            f"- Feedback: regime={p.feedback_regime}, score={p.feedback_score:.3f}, self_direction={p.feedback_self_direction:.3f}",
            f"- Emergence: {p.emergence_confidence}, score={p.emergence_score:.3f}, evidence={p.emergence_evidence_count}, positive={', '.join(p.emergence_positive) if p.emergence_positive else '-'}",
            f"- Validation: {p.validation_grade}, quality={p.validation_quality:.3f}, repeatability={p.validation_repeatability:.3f}, warning={p.validation_warning or 'ok'}",
            f"- Source: `{Path(p.source_file).name}`",
            "",
        ])
    return "\n".join(lines)


def build_profiles(results_folder: Path) -> list[ObserverProfile]:
    """Return the backward-compatible representative profile per rule."""
    all_files = collect_passport_json(results_folder)
    records, _ = build_profile_records(all_files)
    records, _ = annotate_scientific_provenance(
        records,
        results_folder / "observation_logs" / "telemetry.sqlite",
    )
    grouped = group_profiles_by_rule(records)
    return select_representative_profiles(grouped)

def main() -> int:
    parser = argparse.ArgumentParser(description="Build normalized Observer v31 profiles from passport JSON files.")
    parser.add_argument("results_folder", help="Shared Universe Search results folder")
    parser.add_argument("--json-out", default=None, help="Output JSON path; default: RESULTS/observer_profiles_v31.json")
    parser.add_argument("--compat-json-out", default=None, help="Compatibility JSON path; default: RESULTS/observer_profiles_v30.json")
    parser.add_argument("--md-out", default=None, help="Output Markdown path; default: RESULTS/observer_profiles_v31.md")
    parser.add_argument("--compat-md-out", default=None, help="Compatibility Markdown path; default: RESULTS/observer_profiles_v30.md")
    parser.add_argument(
        "--telemetry-db",
        default=None,
        help=(
            "Telemetry SQLite used for scientific provenance. "
            "Default: RESULTS/observation_logs/telemetry.sqlite"
        ),
    )
    args = parser.parse_args()

    results_folder = Path(args.results_folder).resolve()
    if not results_folder.exists():
        raise SystemExit(f"Results folder does not exist: {results_folder}")

    all_files = collect_passport_json(results_folder)
    if not all_files:
        raise SystemExit(f"No *passport.json files found under: {results_folder}")

    profile_records, failures = build_profile_records(all_files)
    telemetry_database = (
        Path(args.telemetry_db).expanduser().resolve()
        if args.telemetry_db
        else results_folder / "observation_logs" / "telemetry.sqlite"
    )
    profile_records, provenance_summary = annotate_scientific_provenance(
        profile_records,
        telemetry_database,
    )
    profiles_by_rule = group_profiles_by_rule(profile_records)
    profiles = select_representative_profiles(profiles_by_rule)
    additional_records = max(0, len(profile_records) - len(profiles))

    json_out = Path(args.json_out) if args.json_out else results_folder / "observer_profiles_v31.json"
    md_out = Path(args.md_out) if args.md_out else results_folder / "observer_profiles_v31.md"
    compat_json_out = Path(args.compat_json_out) if args.compat_json_out else results_folder / "observer_profiles_v30.json"
    compat_md_out = Path(args.compat_md_out) if args.compat_md_out else results_folder / "observer_profiles_v30.md"

    payload = {
        "schema": "observer_profiles_v31_1",
        "compatibility_schema": "observer_profiles_v30",
        "ontology_contract": "ObserverState/1.0.0",
        "shadow_classification_contract": "ontology_profile_shadow/1.0",
        "lifecycle_reconciliation_contract": "lifecycle_reconciliation/1.1.0",
        "results_folder": str(results_folder),
        "passport_files_scanned": len(all_files),
        "profile_records_count": len(profile_records),
        "unique_rules": len(profiles),
        "additional_records_retained": additional_records,
        "parse_failures": failures,
        "scientific_provenance": {
            "telemetry_database": (
                str(telemetry_database)
                if telemetry_database.is_file()
                else None
            ),
            "strict_routing_active": telemetry_database.is_file(),
            **provenance_summary,
        },
        "lifecycle_reconciliation": {
            "verified": sum(
                profile.lifecycle_verification_status == "verified"
                for profile in profile_records
            ),
            "mismatch": sum(
                profile.lifecycle_verification_status == "mismatch"
                for profile in profile_records
            ),
            "temporal_invalid": sum(
                profile.lifecycle_verification_status == "temporal_invalid"
                for profile in profile_records
            ),
            "passport_summary_unavailable": sum(
                profile.lifecycle_verification_status
                == "passport_summary_unavailable"
                for profile in profile_records
            ),
            "observer_state_unavailable": sum(
                profile.lifecycle_verification_status
                == "observer_state_unavailable"
                for profile in profile_records
            ),
            "unavailable": sum(
                profile.lifecycle_verification_status == "unavailable"
                for profile in profile_records
            ),
        },
        # Backward-compatible one-profile-per-rule view.
        "profiles": [
            asdict(p)
            for p in sorted(profiles, key=lambda x: x.rule)
        ],
        # Complete record/run history.
        "profile_records": [
            asdict(p)
            for p in sorted(
                profile_records,
                key=lambda x: (x.rule, x.created or "", x.source_file),
            )
        ],
        # Convenient grouped history for rule-level consumers.
        "profiles_by_rule": {
            rule: [asdict(p) for p in records]
            for rule, records in sorted(profiles_by_rule.items())
        },
    }
    rendered_json = json.dumps(payload, indent=2, ensure_ascii=False)
    rendered_md = render_markdown(profiles, len(all_files), additional_records)
    json_out.write_text(rendered_json, encoding="utf-8")
    md_out.write_text(rendered_md, encoding="utf-8")
    # Stage 1D keeps the v30 filenames alive so existing Analyzer consumers
    # receive the additive v31 fields without a flag day migration.
    compat_json_out.write_text(rendered_json, encoding="utf-8")
    compat_md_out.write_text(rendered_md, encoding="utf-8")

    print("")
    print("=" * 64)
    print("Observer Profile v31")
    print("=" * 64)
    print(f"Results folder:          {results_folder}")
    print(f"Passport JSON scanned:   {len(all_files)}")
    print(f"Unique rules profiled:   {len(profiles)}")
    print(f"Profile records built:   {len(profile_records)}")
    print(f"Additional retained:     {additional_records}")
    print(f"Parse failures:          {len(failures)}")
    print(
        "Canonical completed:     "
        f"{provenance_summary['canonical_completed']}"
    )
    print(
        "Non-observational excl.: "
        f"{sum(provenance_summary[key] for key in (
            'experimental_excluded',
            'mutation_excluded',
            'incomplete_excluded',
            'unresolved_excluded',
        ))}"
    )
    print(f"JSON written:            {json_out}")
    print(f"Markdown written:        {md_out}")
    print(f"Compatibility JSON:      {compat_json_out}")
    print(f"Compatibility Markdown:  {compat_md_out}")
    print("-" * 64)
    for p in sorted(profiles, key=lambda x: x.layer_stack_score, reverse=True)[:10]:
        print(
            f"Rule {p.rule}: {p.analyzer_category} | "
            f"score={p.layer_stack_score:.3f} EMG={p.emergence_score:.3f}/{p.emergence_confidence} "
            f"VAL={p.validation_quality:.3f}/{p.validation_grade}"
        )
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
