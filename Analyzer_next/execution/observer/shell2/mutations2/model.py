"""Immutable UI projection contracts for OL2-MUTATIONS2."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MutationMetricDelta:
    metric: str
    baseline: float | int | None
    mutant: float | int | None
    absolute_delta: float | int | None
    relative_delta: float | None


@dataclass(frozen=True, slots=True)
class MutationAnalysisView:
    mutation_id: str
    parent_rule_id: int
    generated: str
    effect_primary: str
    effect_labels: tuple[str, ...]
    evidence: tuple[str, ...]
    confidence_grade: str
    confidence_score: float
    confidence_reasons: tuple[str, ...]
    baseline_match_type: str
    baseline_same_seed: bool | None
    baseline_coverage: float
    comparison_end_tick: int | None
    lifecycle_status: str
    required_control: bool
    required_control_reason: str | None
    required_control_target_ticks: int | None
    required_control_sample_interval: int | None
    warnings: tuple[str, ...]
    metric_deltas: tuple[MutationMetricDelta, ...]
    report_json: Path
    report_markdown: Path | None

    @property
    def control_label(self) -> str:
        return "REQUIRED" if self.required_control else "not needed"

    @property
    def confidence_label(self) -> str:
        score = f"{self.confidence_score:.2f}" if self.confidence_score >= 0 else "n/a"
        return f"{self.confidence_grade} ({score})"


@dataclass(frozen=True, slots=True)
class MutationAnalysisRunOutcome:
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True, slots=True)
class MutationAnalysisSnapshot:
    selected_mutation_id: str | None = None
    analysis: MutationAnalysisView | None = None
    busy: bool = False
    status: str = "Select an observed mutation to inspect scientific effect."
    revision: int = 0


__all__ = [
    "MutationAnalysisRunOutcome",
    "MutationAnalysisSnapshot",
    "MutationAnalysisView",
    "MutationMetricDelta",
]
