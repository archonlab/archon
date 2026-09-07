"""Stable Mutation Analyzer schemas and metric catalogues."""
from __future__ import annotations

import re

SCHEMA = "archon_mutation_analysis_v1"

REPORT_SCHEMA = "archon_mutation_report_v1"

PER_MUTATION_ANALYSIS_VERSION = 1

CONTROL_RESOLUTION_FILENAME = "required_control_resolution.json"

RULE_RE = re.compile(r"rule_(\d{1,6})_", re.I)

NUMERIC_METRICS = [
    "objects",
    "largest",
    "total_living_mass",
    "mean_object_size",
    "ecosystem_health",
    "fragmentation_index",
    "stability_index",
    "active_families",
    "deepest_generation",
    "oldest_lineage_age",
    "demo_survival_ratio",
    "evo_stress",
    "evo_adapt",
    "evo_pressure",
    "evo_recovery",
    "evo_extinction_risk",
    "civ_score",
    "civ_peak_score",
    "knowledge_score",
    "knowledge_peak_score",
    "knowledge_transfer",
    "knowledge_loss",
    "feedback_score",
    "feedback_peak_score",
    "feedback_self_direction",
    "feedback_environment_impact",
    "emergence_score",
    "emergence_peak_score",
    "emergence_complexity_index",
    "emergence_stability_signal",
    "validation_quality",
    "validation_repeatability",
    "validation_false_positive_risk",
    "validation_noise_sensitivity",
    "morphology_compactness",
    "morphology_aspect",
    "morphology_edge_complexity",
    "morphology_bbox_fill",
    "morphology_symmetry",
    "morphology_branching",
    "morphology_filament_score",
    "morphology_lattice_score",
    "morphology_change_rate",
    "morphology_peak_complexity",
    "bbox_width",
    "bbox_height",
    "defect_cells",
    "changed",
    "health",
    "cx",
    "cy",
    "step_drift",
    "total_drift",
    "identity_persistence",
    "information_survival",
    "post_collapse_structure",
    "expansion_front_speed",
]

CATEGORICAL_METRICS = [
    "alive",
    "growth_phase",
    "ecosystem_phase",
    "story_era",
    "evo_phase",
    "civ_stage",
    "knowledge_dominant_axis",
    "feedback_regime",
    "emergence_confidence",
    "validation_grade",
    "validation_warning",
    "morphology_class",
]

