"""Stable scientific contracts for morphological epoch detection."""

NUMERIC_COLUMNS = [
    "objects",
    "largest",
    "total_living_mass",
    "stability_index",
    "evo_stress",
    "evo_adapt",
    "evo_pressure",
    "evo_extinction_risk",
    "knowledge_score",
    "feedback_score",
    "emergence_score",
    "validation_quality",
    "morphology_compactness",
    "morphology_aspect",
    "morphology_edge_complexity",
    "morphology_bbox_fill",
    "morphology_symmetry",
    "morphology_branching",
    "morphology_filament_score",
    "morphology_lattice_score",
    "morphology_change_rate",
    "morphology_stability_ticks",
]

EPOCH_TYPES = [
    "FORMATION",
    "RAPID_EXPANSION",
    "STRUCTURAL_ORGANIZATION",
    "STABLE_OSCILLATION",
    "QUIET_PLATEAU",
    "RECONFIGURATION_EPOCH",
    "DECAY_EPOCH",
    "COLLAPSE_EPOCH",
    "RECOVERY_EPOCH",
    "TRANSITION_EPOCH",
]

ARTIFACT_NAMES = (
    "morphological_epoch_report.json",
    "morphological_epoch_report.md",
    "morphological_epochs.json",
    "morphological_epochs.md",
)

