#!/usr/bin/env python3
"""Integrated Evidence Framework pipeline for Project ARCHON Observer.

The pipeline assembles the first Evidence Framework phase into one reproducible
run:

    collected observations and neutral evidence
        -> evidence-confidence diagnostics
        -> baseline unknown detection
        -> competing-hypothesis evaluation
        -> hypothesis-specific unknown detection
        -> evidence consistency checking
        -> validated EvidenceReport

The pipeline does not inspect a cellular-automaton field directly. Existing
Observer sensors remain responsible for producing explicit Observation and
Evidence objects through ``EvidenceCollector``.

Design goals
------------
1. One public entry point for a complete evidence pass.
2. No hidden semantic inference from metric names.
3. Every intermediate result remains available for debugging and calibration.
4. A final EvidenceReport is structurally validated by evidence_models.py.
5. Conservative failure: invalid references stop the pipeline rather than
   producing a persuasive but broken report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

try:
    from .evidence_models import (
        Evidence,
        EvidenceGroup,
        EvidenceModelError,
        EvidenceReport,
        Hypothesis,
        Observation,
        UnknownQuestion,
    )
    from .observer_confidence_engine import (
        ConfidenceEngine,
        ConfidenceEngineError,
        ConfidenceResult,
    )
    from .observer_evidence import EvidenceCollector
    from .observer_evidence_consistency import (
        ConflictRule,
        ConsistencyReport,
        EvidenceConsistencyChecker,
        canonical_conflict_rules,
    )
    from .observer_hypothesis_engine import (
        HypothesisCompetition,
        HypothesisDefinition,
        HypothesisEngine,
        HypothesisEngineError,
        canonical_hypothesis_definitions,
    )
    from .observer_unknowns import (
        UnknownCriterion,
        UnknownDetection,
        UnknownEngine,
        UnknownEngineError,
        canonical_unknown_criteria,
    )
except ImportError:  # Direct execution from the Observer directory.
    from evidence_models import (
        Evidence,
        EvidenceGroup,
        EvidenceModelError,
        EvidenceReport,
        Hypothesis,
        Observation,
        UnknownQuestion,
    )
    from observer_confidence_engine import (
        ConfidenceEngine,
        ConfidenceEngineError,
        ConfidenceResult,
    )
    from observer_evidence import EvidenceCollector
    from observer_evidence_consistency import (
        ConflictRule,
        ConsistencyReport,
        EvidenceConsistencyChecker,
        canonical_conflict_rules,
    )
    from observer_hypothesis_engine import (
        HypothesisCompetition,
        HypothesisDefinition,
        HypothesisEngine,
        HypothesisEngineError,
        canonical_hypothesis_definitions,
    )
    from observer_unknowns import (
        UnknownCriterion,
        UnknownDetection,
        UnknownEngine,
        UnknownEngineError,
        canonical_unknown_criteria,
    )


OBSERVER_EVIDENCE_PIPELINE_VERSION = "1.0.0"


class EvidencePipelineError(RuntimeError):
    """Raised when an integrated evidence pass cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class EvidencePipelineConfig:
    """Configuration for one integrated evidence pass."""

    hypothesis_definitions: tuple[HypothesisDefinition, ...] = field(
        default_factory=canonical_hypothesis_definitions
    )
    unknown_criteria: tuple[UnknownCriterion, ...] = field(
        default_factory=canonical_unknown_criteria
    )
    conflict_rules: tuple[ConflictRule, ...] = field(
        default_factory=canonical_conflict_rules
    )
    minimum_leading_margin: float = 0.05
    recalculate_evidence_confidence: bool = True
    run_unknown_detection: bool = True
    run_consistency_check: bool = True
    second_hypothesis_pass: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hypothesis_definitions",
            tuple(self.hypothesis_definitions),
        )
        object.__setattr__(
            self,
            "unknown_criteria",
            tuple(self.unknown_criteria),
        )
        object.__setattr__(
            self,
            "conflict_rules",
            tuple(self.conflict_rules),
        )

        if not self.hypothesis_definitions:
            raise EvidencePipelineError(
                "At least one hypothesis definition is required"
            )
        if not all(
            isinstance(item, HypothesisDefinition)
            for item in self.hypothesis_definitions
        ):
            raise EvidencePipelineError(
                "hypothesis_definitions must contain HypothesisDefinition objects"
            )
        if not all(
            isinstance(item, UnknownCriterion)
            for item in self.unknown_criteria
        ):
            raise EvidencePipelineError(
                "unknown_criteria must contain UnknownCriterion objects"
            )
        if not all(
            isinstance(item, ConflictRule)
            for item in self.conflict_rules
        ):
            raise EvidencePipelineError(
                "conflict_rules must contain ConflictRule objects"
            )

        margin = _probability(
            self.minimum_leading_margin,
            "minimum_leading_margin",
        )
        object.__setattr__(self, "minimum_leading_margin", margin)


@dataclass(frozen=True, slots=True)
class EvidenceConfidenceAudit:
    """Declared and recalculated confidence for one Evidence object."""

    evidence_id: str
    declared_confidence: float
    recalculated: ConfidenceResult
    absolute_delta: float


@dataclass(frozen=True, slots=True)
class EvidencePipelineResult:
    """Final report together with every important intermediate product."""

    report: EvidenceReport
    evidence_confidence_audits: tuple[EvidenceConfidenceAudit, ...]
    baseline_unknown_detections: tuple[UnknownDetection, ...]
    hypothesis_competition: HypothesisCompetition
    consistency_report: ConsistencyReport
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


def _probability(value: float, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidencePipelineError(f"{name} must be in [0, 1]") from exc
    if not 0.0 <= numeric <= 1.0:
        raise EvidencePipelineError(
            f"{name} must be in [0, 1], got {numeric!r}"
        )
    return numeric


class EvidencePipeline:
    """Coordinate the complete Observer Evidence Framework pass."""

    def __init__(
        self,
        *,
        config: EvidencePipelineConfig | None = None,
        confidence_engine: ConfidenceEngine | None = None,
        hypothesis_engine: HypothesisEngine | None = None,
        unknown_engine: UnknownEngine | None = None,
        consistency_checker: EvidenceConsistencyChecker | None = None,
    ) -> None:
        self.config = config or EvidencePipelineConfig()
        self.confidence_engine = confidence_engine or ConfidenceEngine()
        self.hypothesis_engine = hypothesis_engine or HypothesisEngine(
            self.confidence_engine
        )
        self.unknown_engine = unknown_engine or UnknownEngine()
        self.consistency_checker = (
            consistency_checker or EvidenceConsistencyChecker()
        )

    def run(
        self,
        collector: EvidenceCollector,
        *,
        metadata: Mapping[str, Any] | None = None,
        existing_unknowns: Iterable[UnknownQuestion] = (),
    ) -> EvidencePipelineResult:
        """Run the complete evidence pipeline for one collector.

        The collector identity supplies world_id, run_id, and observer_version.
        Existing unknowns may be carried forward from an earlier checkpoint.
        """

        if not isinstance(collector, EvidenceCollector):
            raise EvidencePipelineError(
                "collector must be an EvidenceCollector"
            )

        observations = collector.observations
        evidence = collector.evidence
        groups = collector.groups

        return self.run_components(
            world_id=collector.world_id,
            run_id=collector.run_id,
            observer_version=collector.observer_version,
            observations=observations,
            evidence=evidence,
            groups=groups,
            metadata={
                **collector.metadata,
                **dict(metadata or {}),
            },
            existing_unknowns=existing_unknowns,
        )

    def run_components(
        self,
        *,
        world_id: str,
        run_id: str,
        observer_version: str,
        observations: Iterable[Observation],
        evidence: Iterable[Evidence],
        groups: Iterable[EvidenceGroup] = (),
        metadata: Mapping[str, Any] | None = None,
        existing_unknowns: Iterable[UnknownQuestion] = (),
    ) -> EvidencePipelineResult:
        """Run from explicit immutable model collections."""

        observations = tuple(observations)
        evidence = tuple(evidence)
        groups = tuple(groups)
        existing_unknowns = tuple(existing_unknowns)

        self._validate_input_types(
            observations,
            evidence,
            groups,
            existing_unknowns,
        )

        confidence_audits = self._audit_evidence_confidence(
            evidence,
            observations,
        )

        baseline_detections: tuple[UnknownDetection, ...] = ()
        baseline_unknowns: tuple[UnknownQuestion, ...] = ()
        if self.config.run_unknown_detection:
            try:
                baseline_detections = self.unknown_engine.detect(
                    self.config.unknown_criteria,
                    observations,
                    evidence,
                )
            except UnknownEngineError as exc:
                raise EvidencePipelineError(
                    f"Unknown detection failed: {exc}"
                ) from exc
            baseline_unknowns = tuple(
                item.question for item in baseline_detections
            )

        initial_unknowns = self.unknown_engine.deduplicate(
            (*existing_unknowns, *baseline_unknowns)
        )

        first_competition = self._compete(
            evidence=evidence,
            groups=groups,
            unknowns=initial_unknowns,
        )

        hypothesis_gap_unknowns: tuple[UnknownQuestion, ...] = ()
        if self.config.run_unknown_detection:
            try:
                hypothesis_gap_unknowns = (
                    self.unknown_engine.detect_from_hypothesis_evaluations(
                        self.config.hypothesis_definitions,
                        first_competition.evaluations,
                    )
                )
            except UnknownEngineError as exc:
                raise EvidencePipelineError(
                    f"Hypothesis-gap unknown detection failed: {exc}"
                ) from exc

        final_unknowns = self.unknown_engine.deduplicate(
            (
                *existing_unknowns,
                *baseline_unknowns,
                *hypothesis_gap_unknowns,
            )
        )

        if self.config.second_hypothesis_pass:
            competition = self._compete(
                evidence=evidence,
                groups=groups,
                unknowns=final_unknowns,
            )
        else:
            competition = first_competition

        if self.config.run_consistency_check:
            try:
                consistency = self.consistency_checker.check(
                    evidence,
                    self.config.conflict_rules,
                )
            except Exception as exc:
                raise EvidencePipelineError(
                    f"Evidence consistency check failed: {exc}"
                ) from exc
        else:
            consistency = ConsistencyReport(
                conflicts=(),
                detections=(),
                checked_rule_count=0,
                checked_evidence_count=len(evidence),
                diagnostics={"disabled": True},
            )

        hypotheses = tuple(
            item.hypothesis for item in competition.evaluations
        )

        report_metadata = self._build_metadata(
            metadata=metadata,
            observations=observations,
            evidence=evidence,
            groups=groups,
            hypotheses=hypotheses,
            unknowns=final_unknowns,
            confidence_audits=confidence_audits,
            consistency=consistency,
            competition=competition,
        )

        try:
            report = EvidenceReport(
                world_id=str(world_id),
                run_id=str(run_id),
                observer_version=str(observer_version),
                observations=observations,
                evidence=evidence,
                groups=groups,
                hypotheses=hypotheses,
                conflicts=consistency.conflicts,
                unknowns=final_unknowns,
                leading_hypothesis_id=competition.leading_hypothesis_id,
                metadata=report_metadata,
            )
        except EvidenceModelError as exc:
            raise EvidencePipelineError(
                f"Final EvidenceReport validation failed: {exc}"
            ) from exc

        return EvidencePipelineResult(
            report=report,
            evidence_confidence_audits=confidence_audits,
            baseline_unknown_detections=baseline_detections,
            hypothesis_competition=competition,
            consistency_report=consistency,
            diagnostics={
                "first_pass_leader": first_competition.leading_hypothesis_id,
                "final_leader": competition.leading_hypothesis_id,
                "hypothesis_gap_unknown_count": len(
                    hypothesis_gap_unknowns
                ),
                "final_unknown_count": len(final_unknowns),
                "conflict_count": len(consistency.conflicts),
            },
        )

    def _audit_evidence_confidence(
        self,
        evidence: tuple[Evidence, ...],
        observations: tuple[Observation, ...],
    ) -> tuple[EvidenceConfidenceAudit, ...]:
        if not self.config.recalculate_evidence_confidence:
            return ()

        audits: list[EvidenceConfidenceAudit] = []
        for item in evidence:
            try:
                result = self.confidence_engine.evidence_confidence(
                    item,
                    observations,
                )
            except ConfidenceEngineError as exc:
                raise EvidencePipelineError(
                    f"Evidence confidence audit failed for "
                    f"{item.evidence_id}: {exc}"
                ) from exc

            audits.append(
                EvidenceConfidenceAudit(
                    evidence_id=item.evidence_id,
                    declared_confidence=item.confidence,
                    recalculated=result,
                    absolute_delta=abs(
                        item.confidence - result.confidence
                    ),
                )
            )

        return tuple(audits)

    def _compete(
        self,
        *,
        evidence: tuple[Evidence, ...],
        groups: tuple[EvidenceGroup, ...],
        unknowns: tuple[UnknownQuestion, ...],
    ) -> HypothesisCompetition:
        try:
            return self.hypothesis_engine.compete(
                self.config.hypothesis_definitions,
                evidence,
                groups,
                unknowns,
                minimum_leading_margin=(
                    self.config.minimum_leading_margin
                ),
            )
        except HypothesisEngineError as exc:
            raise EvidencePipelineError(
                f"Hypothesis competition failed: {exc}"
            ) from exc

    @staticmethod
    def _validate_input_types(
        observations: tuple[Observation, ...],
        evidence: tuple[Evidence, ...],
        groups: tuple[EvidenceGroup, ...],
        unknowns: tuple[UnknownQuestion, ...],
    ) -> None:
        checks = (
            (observations, Observation, "observations"),
            (evidence, Evidence, "evidence"),
            (groups, EvidenceGroup, "groups"),
            (unknowns, UnknownQuestion, "existing_unknowns"),
        )
        for collection, expected, name in checks:
            if not all(
                isinstance(item, expected) for item in collection
            ):
                raise EvidencePipelineError(
                    f"{name} must contain only {expected.__name__} objects"
                )

    @staticmethod
    def _build_metadata(
        *,
        metadata: Mapping[str, Any] | None,
        observations: tuple[Observation, ...],
        evidence: tuple[Evidence, ...],
        groups: tuple[EvidenceGroup, ...],
        hypotheses: tuple[Hypothesis, ...],
        unknowns: tuple[UnknownQuestion, ...],
        confidence_audits: tuple[EvidenceConfidenceAudit, ...],
        consistency: ConsistencyReport,
        competition: HypothesisCompetition,
    ) -> dict[str, Any]:
        result = dict(metadata or {})
        result.update(
            {
                "evidence_pipeline_version": (
                    OBSERVER_EVIDENCE_PIPELINE_VERSION
                ),
                "pipeline_stage": "complete_evidence_framework_v1",
                "observation_count": len(observations),
                "evidence_count": len(evidence),
                "evidence_group_count": len(groups),
                "hypothesis_count": len(hypotheses),
                "unknown_count": len(unknowns),
                "conflict_count": len(consistency.conflicts),
                "confidence_audit_count": len(confidence_audits),
                "leading_hypothesis_id": (
                    competition.leading_hypothesis_id
                ),
                "leading_margin": competition.margin,
            }
        )

        if confidence_audits:
            result["mean_evidence_confidence_delta"] = (
                sum(item.absolute_delta for item in confidence_audits)
                / len(confidence_audits)
            )
            result["maximum_evidence_confidence_delta"] = max(
                item.absolute_delta for item in confidence_audits
            )

        return result


def run_evidence_pipeline(
    collector: EvidenceCollector,
    *,
    config: EvidencePipelineConfig | None = None,
    metadata: Mapping[str, Any] | None = None,
    existing_unknowns: Iterable[UnknownQuestion] = (),
) -> EvidencePipelineResult:
    """Convenience function for the standard one-shot pipeline."""

    return EvidencePipeline(config=config).run(
        collector,
        metadata=metadata,
        existing_unknowns=existing_unknowns,
    )


__all__ = [
    "OBSERVER_EVIDENCE_PIPELINE_VERSION",
    "EvidencePipelineError",
    "EvidencePipelineConfig",
    "EvidenceConfidenceAudit",
    "EvidencePipelineResult",
    "EvidencePipeline",
    "run_evidence_pipeline",
]
