#!/usr/bin/env python3
"""
ARCHON Scientific State v1.0

Canonical, serializable scientific state for one Universe Search generation.

The state is deliberately descriptive rather than prescriptive. It records:
- search outcomes for the current generation
- deltas against the previous generation
- scientific-stack totals
- stagnation and progress signals
- the policy that produced the generation

EvolutionPolicy and ResearchCycle may read this object, but they remain responsible
for deciding what to do with it.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

SCIENTIFIC_STATE_VERSION = "v1.0 Scientific State"


@dataclass
class ScientificState:
    version: str = SCIENTIFIC_STATE_VERSION
    generation: int = 0
    score_mode: str = "unknown"
    search_run_id: str = "unknown"
    written_at: str = ""

    population_evaluated: int = 0
    valid_worlds: int = 0

    best_rule_id: Optional[int] = None
    best_score: float = 0.0
    mean_score: float = 0.0
    median_score: float = 0.0
    score_gain: float = 0.0
    best_ever_score: float = 0.0
    best_ever_improved: bool = False

    mean_novelty: float = 0.0
    mean_diversity: float = 0.0
    novelty_gain: float = 0.0
    diversity_gain: float = 0.0

    discoveries: int = 0
    new_discoveries: int = 0
    supported_discoveries: int = 0
    foundational_discoveries: int = 0

    experiments: int = 0
    new_trials: int = 0
    positive_trials: int = 0
    successful_experiments: int = 0
    repeatable_experiments: int = 0

    theories: int = 0
    active_theories: int = 0
    paradigms: int = 0
    active_paradigms: int = 0

    reference_controls_available: int = 0
    reference_controls_used: int = 0
    reference_control_fallback_used: int = 0

    family_count: int = 0
    family_distribution: Dict[str, int] = field(default_factory=dict)

    stagnation_generations: int = 0
    adaptive_trend: str = "UNKNOWN"
    progress_score: float = 0.0
    adaptive_risk: float = 0.0
    adaptive_maturity: float = 0.0

    policy_ratios: Dict[str, float] = field(default_factory=dict)
    policy_reasons: List[str] = field(default_factory=list)
    cycle_phase: str = "unknown"
    cycle_directives: List[str] = field(default_factory=list)

    signals: List[str] = field(default_factory=list)
    source_files: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScientificState":
        if not isinstance(data, dict):
            return cls()
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: data[k] for k in allowed if k in data})
