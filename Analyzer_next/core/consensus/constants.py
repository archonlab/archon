"""Schemas, registry keys, and scientific calibration constants."""
from __future__ import annotations

from typing import Any

DB_SCHEMA = "consensus_database_v32"

REPORT_SCHEMA = "consensus_report_v33_1_stage3_3_1"

RULE_REFERENCE_KEYS = {
    "rule", "rule_id", "rule_ids", "rules",
    "target_rule", "target_rules",
    "seed_rule", "seed_rules",
    "parent_a", "parent_b",
    "canonical_rule_id",
}

RULE_KEYED_MAPS = {
    "observations",
    "rules_by_id",
    "profiles_by_rule",
}

METRIC_INDEPENDENCE_CALIBRATION: dict[str, dict[str, Any]] = {
    "GP-101": {
        "score": 0.58,
        "channels": [
            "emergence",
            "observer_validation",
            "false_positive_risk",
            "false_negative_risk",
        ],
        "shared_upstream_penalty": 0.20,
        "formula_overlap_penalty": 0.17,
        "same_pipeline_penalty": 0.05,
        "rationale": (
            "EMG and validation risks are separate outputs, but all are "
            "produced by the same Observer validation pipeline and may share "
            "upstream morphology and dynamics features."
        ),
    },
    "GP-102": {
        "score": 0.52,
        "channels": ["knowledge", "feedback"],
        "shared_upstream_penalty": 0.25,
        "formula_overlap_penalty": 0.18,
        "same_pipeline_penalty": 0.05,
        "rationale": (
            "Knowledge and feedback are conceptually distinct, but the current "
            "scores share organization, persistence, and adaptive-history "
            "signals, so their apparent coupling is partly architecturally "
            "expected."
        ),
    },
    "GP-103": {
        "score": 0.61,
        "channels": [
            "feedback",
            "feedback_self_direction",
            "feedback_effective_risk",
        ],
        "shared_upstream_penalty": 0.20,
        "formula_overlap_penalty": 0.14,
        "same_pipeline_penalty": 0.05,
        "rationale": (
            "The three measures represent different aspects of regulation, "
            "but self-direction and effective risk are subchannels of the same "
            "feedback layer rather than fully independent instruments."
        ),
    },
    "GP-104": {
        "score": 0.72,
        "channels": [
            "object_population",
            "mass",
            "object_age",
            "emergence",
            "knowledge",
            "feedback",
        ],
        "shared_upstream_penalty": 0.13,
        "formula_overlap_penalty": 0.10,
        "same_pipeline_penalty": 0.05,
        "rationale": (
            "Object counts, mass, and age provide relatively direct controls "
            "against composite EMG/KNOW/FB scores, although all still originate "
            "from the same Observer run and emergence may include persistence "
            "or morphology-derived information."
        ),
    },
    "GP-105": {
        "score": 0.46,
        "channels": ["civilization", "knowledge"],
        "shared_upstream_penalty": 0.28,
        "formula_overlap_penalty": 0.21,
        "same_pipeline_penalty": 0.05,
        "rationale": (
            "Civilization and knowledge are not currently orthogonal enough: "
            "knowledge, technology, culture, and city-like organization are "
            "part of the conceptual scaffold used to interpret civilization."
        ),
    },
    "GP-201": {
        "score": 0.66,
        "channels": [
            "knowledge_memory",
            "stability",
            "observer_repeatability",
            "noise_sensitivity",
            "collapse",
        ],
        "shared_upstream_penalty": 0.17,
        "formula_overlap_penalty": 0.12,
        "same_pipeline_penalty": 0.05,
        "rationale": (
            "Memory and stability are distinct channels, but repeatability, "
            "noise sensitivity, and collapse behavior partially overlap with "
            "the stability construct and are measured in the same pipeline."
        ),
    },
}

ACTION_SIGNAL_PRIORITY = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "NONE": 0,
}

SIGNAL_BASE_SCORE = {
    "needs_scope_test": 90,
    "needs_perturbation_resolution": 86,
    "needs_counterexample_search": 82,
    "needs_controlled_experiment": 76,
    "needs_replication": 70,
    "needs_perturbation_evidence": 58,
    "ready_for_broader_validation": 35,
}

