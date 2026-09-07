#!/usr/bin/env python3
"""Confidence aggregation for Project ARCHON Observer evidence.

This module evaluates confidence without deciding what a hypothesis means.
It is deliberately domain-neutral: no life thresholds, no emergence verdicts,
and no hard-coded preferences for morphology, memory, repair, or reproduction.

The engine separates three layers:

1. Observation confidence
   Confidence already attached to direct sensor measurements.

2. Evidence confidence
   Aggregated from the observations referenced by one neutral Evidence object.

3. Hypothesis confidence
   Aggregated from HypothesisAssessment objects while preventing correlated
   evidence in the same EvidenceGroup from being counted as independent proof.

All formulas are configurable and return diagnostics so every result can be
traced back to its inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import prod
from typing import Any, Iterable, Mapping, Sequence

try:
    from .evidence_models import (
        Evidence,
        EvidenceGroup,
        EvidenceModelError,
        EvidenceQuality,
        EvidenceRelation,
        HypothesisAssessment,
        Observation,
        Provenance,
    )
except ImportError:  # Direct execution from the Observer directory.
    from evidence_models import (
        Evidence,
        EvidenceGroup,
        EvidenceModelError,
        EvidenceQuality,
        EvidenceRelation,
        HypothesisAssessment,
        Observation,
        Provenance,
    )


OBSERVER_CONFIDENCE_ENGINE_VERSION = "1.0.0"


class ConfidenceEngineError(ValueError):
    """Raised when confidence cannot be calculated safely."""


@dataclass(frozen=True, slots=True)
class ConfidenceConfig:
    """Configuration for domain-neutral confidence aggregation.

    ``quality_multipliers`` modify confidence according to declared data
    quality.  ``group_cap`` limits the total contribution of correlated
    assessments sharing one independence group.

    ``contradiction_penalty`` controls how strongly contradictory evidence
    reduces hypothesis confidence relative to supporting evidence.
    """

    quality_multipliers: Mapping[EvidenceQuality, float] = field(
        default_factory=lambda: {
            EvidenceQuality.UNKNOWN: 0.80,
            EvidenceQuality.VERY_LOW: 0.35,
            EvidenceQuality.LOW: 0.55,
            EvidenceQuality.MEDIUM: 0.75,
            EvidenceQuality.HIGH: 0.90,
            EvidenceQuality.VERY_HIGH: 1.00,
        }
    )
    evidence_method: str = "weighted_geometric"
    group_method: str = "noisy_or"
    hypothesis_method: str = "support_minus_contradiction"
    group_cap: float = 0.95
    contradiction_penalty: float = 1.0
    neutral_weight: float = 0.0
    minimum_effective_confidence: float = 0.0

    def __post_init__(self) -> None:
        allowed_evidence = {"weighted_mean", "weighted_geometric", "minimum"}
        allowed_group = {"maximum", "mean", "noisy_or"}
        allowed_hypothesis = {"support_minus_contradiction"}

        if self.evidence_method not in allowed_evidence:
            raise ConfidenceEngineError(
                f"Unsupported evidence_method {self.evidence_method!r}; "
                f"allowed: {sorted(allowed_evidence)}"
            )
        if self.group_method not in allowed_group:
            raise ConfidenceEngineError(
                f"Unsupported group_method {self.group_method!r}; "
                f"allowed: {sorted(allowed_group)}"
            )
        if self.hypothesis_method not in allowed_hypothesis:
            raise ConfidenceEngineError(
                f"Unsupported hypothesis_method {self.hypothesis_method!r}; "
                f"allowed: {sorted(allowed_hypothesis)}"
            )

        for name, value in (
            ("group_cap", self.group_cap),
            ("contradiction_penalty", self.contradiction_penalty),
            ("neutral_weight", self.neutral_weight),
            ("minimum_effective_confidence", self.minimum_effective_confidence),
        ):
            _require_unit_interval(value, name)

        normalized: dict[EvidenceQuality, float] = {}
        for quality in EvidenceQuality:
            raw = self.quality_multipliers.get(quality)
            if raw is None:
                raise ConfidenceEngineError(
                    f"quality_multipliers is missing {quality.value!r}"
                )
            normalized[quality] = _require_unit_interval(
                raw, f"quality_multipliers[{quality.value}]"
            )
        object.__setattr__(self, "quality_multipliers", normalized)


@dataclass(frozen=True, slots=True)
class ConfidenceContribution:
    """One traceable contribution to an aggregate confidence result."""

    source_id: str
    raw_confidence: float
    quality_multiplier: float
    weight: float
    effective_confidence: float
    relation: EvidenceRelation | None = None
    group_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    """Aggregate confidence plus a transparent calculation trace."""

    confidence: float
    method: str
    contributions: tuple[ConfidenceContribution, ...]
    support: float = 0.0
    contradiction: float = 0.0
    neutral: float = 0.0
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


def _require_unit_interval(value: float, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfidenceEngineError(f"{name} must be a number in [0, 1]") from exc
    if not 0.0 <= numeric <= 1.0:
        raise ConfidenceEngineError(f"{name} must be in [0, 1], got {numeric!r}")
    return numeric


def _weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    total_weight = sum(weights)
    if total_weight <= 0.0:
        return 0.0
    return sum(value * weight for value, weight in zip(values, weights)) / total_weight


def _weighted_geometric(values: Sequence[float], weights: Sequence[float]) -> float:
    """Weighted geometric mean that remains defined for zero confidence."""

    total_weight = sum(weights)
    if total_weight <= 0.0:
        return 0.0
    if any(value <= 0.0 and weight > 0.0 for value, weight in zip(values, weights)):
        return 0.0
    return prod(
        value ** (weight / total_weight)
        for value, weight in zip(values, weights)
        if weight > 0.0
    )


def _noisy_or(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return 1.0 - prod(1.0 - _require_unit_interval(value, "noisy_or value") for value in values)


class ConfidenceEngine:
    """Configurable confidence calculator with independence-group handling."""

    def __init__(self, config: ConfidenceConfig | None = None) -> None:
        self.config = config or ConfidenceConfig()

    def observation_effective_confidence(
        self,
        observation: Observation,
    ) -> ConfidenceContribution:
        """Apply the declared quality multiplier to one observation."""

        if not isinstance(observation, Observation):
            raise ConfidenceEngineError("observation must be an Observation")

        quality_multiplier = self.config.quality_multipliers[observation.quality]
        effective = max(
            self.config.minimum_effective_confidence,
            observation.confidence * quality_multiplier,
        )
        effective = min(1.0, effective)

        return ConfidenceContribution(
            source_id=observation.observation_id,
            raw_confidence=observation.confidence,
            quality_multiplier=quality_multiplier,
            weight=1.0,
            effective_confidence=effective,
        )

    def evidence_confidence(
        self,
        evidence: Evidence,
        observations: Mapping[str, Observation] | Iterable[Observation],
    ) -> ConfidenceResult:
        """Recalculate confidence for one Evidence object from its observations.

        The Evidence object's own confidence is not silently overwritten.  The
        returned result can be compared with it, logged, or used to create a
        revised Evidence object in a later integration step.
        """

        if not isinstance(evidence, Evidence):
            raise ConfidenceEngineError("evidence must be Evidence")

        observation_map = _index_observations(observations)
        missing = [
            observation_id
            for observation_id in evidence.observation_ids
            if observation_id not in observation_map
        ]
        if missing:
            raise ConfidenceEngineError(
                "Evidence references missing observations: " + ", ".join(missing)
            )

        contributions = tuple(
            self.observation_effective_confidence(observation_map[item_id])
            for item_id in evidence.observation_ids
        )
        values = [item.effective_confidence for item in contributions]
        weights = [item.weight for item in contributions]

        if self.config.evidence_method == "weighted_mean":
            aggregate = _weighted_mean(values, weights)
        elif self.config.evidence_method == "weighted_geometric":
            aggregate = _weighted_geometric(values, weights)
        else:
            aggregate = min(values) if values else 0.0

        evidence_quality_multiplier = self.config.quality_multipliers[evidence.quality]
        aggregate *= evidence_quality_multiplier
        aggregate = _require_unit_interval(aggregate, "evidence confidence")

        return ConfidenceResult(
            confidence=aggregate,
            method=self.config.evidence_method,
            contributions=contributions,
            diagnostics={
                "declared_evidence_confidence": evidence.confidence,
                "evidence_quality": evidence.quality.value,
                "evidence_quality_multiplier": evidence_quality_multiplier,
                "observation_count": len(contributions),
            },
        )

    def hypothesis_confidence(
        self,
        assessments: Sequence[HypothesisAssessment],
        evidence: Mapping[str, Evidence] | Iterable[Evidence],
        groups: Mapping[str, EvidenceGroup] | Iterable[EvidenceGroup] = (),
    ) -> ConfidenceResult:
        """Aggregate hypothesis assessments without double-counting groups."""

        evidence_map = _index_evidence(evidence)
        group_map = _index_groups(groups)

        contributions: list[ConfidenceContribution] = []
        grouped: dict[str, list[ConfidenceContribution]] = {}

        for assessment in assessments:
            if not isinstance(assessment, HypothesisAssessment):
                raise ConfidenceEngineError(
                    "assessments must contain HypothesisAssessment objects"
                )
            item = evidence_map.get(assessment.evidence_id)
            if item is None:
                raise ConfidenceEngineError(
                    f"Assessment references missing evidence: {assessment.evidence_id}"
                )
            if assessment.group_id is not None and assessment.group_id not in group_map:
                raise ConfidenceEngineError(
                    f"Assessment references missing group: {assessment.group_id}"
                )
            if (
                assessment.group_id is not None
                and assessment.evidence_id not in group_map[assessment.group_id].evidence_ids
            ):
                raise ConfidenceEngineError(
                    f"Evidence {assessment.evidence_id} is not a member of "
                    f"group {assessment.group_id}"
                )

            quality_multiplier = self.config.quality_multipliers[item.quality]
            effective = (
                assessment.weight
                * assessment.confidence
                * item.confidence
                * quality_multiplier
            )
            effective = _require_unit_interval(effective, "assessment contribution")

            contribution = ConfidenceContribution(
                source_id=assessment.evidence_id,
                raw_confidence=assessment.confidence,
                quality_multiplier=quality_multiplier,
                weight=assessment.weight,
                effective_confidence=effective,
                relation=assessment.relation,
                group_id=assessment.group_id,
            )
            contributions.append(contribution)
            key = assessment.group_id or f"independent:{assessment.assessment_id}"
            grouped.setdefault(key, []).append(contribution)

        group_scores = {
            key: self._aggregate_group(items)
            for key, items in grouped.items()
        }

        support_scores: list[float] = []
        contradiction_scores: list[float] = []
        neutral_scores: list[float] = []

        for key, items in grouped.items():
            score = group_scores[key]
            relations = {item.relation for item in items}
            if len(relations) > 1:
                # Mixed relations inside one dependence group are not collapsed
                # into a false consensus. Split them by relation.
                for relation in EvidenceRelation:
                    subset = [item for item in items if item.relation is relation]
                    if not subset:
                        continue
                    subset_score = self._aggregate_group(subset)
                    self._append_relation_score(
                        relation,
                        subset_score,
                        support_scores,
                        contradiction_scores,
                        neutral_scores,
                    )
            else:
                relation = next(iter(relations), EvidenceRelation.NEUTRAL)
                self._append_relation_score(
                    relation,
                    score,
                    support_scores,
                    contradiction_scores,
                    neutral_scores,
                )

        support = _noisy_or(support_scores)
        contradiction = _noisy_or(contradiction_scores)
        neutral = _noisy_or(neutral_scores)

        if self.config.hypothesis_method == "support_minus_contradiction":
            confidence = support * (1.0 - contradiction * self.config.contradiction_penalty)
            confidence += neutral * self.config.neutral_weight * (1.0 - confidence)
        else:  # Guarded by config validation.
            raise ConfidenceEngineError(
                f"Unsupported hypothesis method: {self.config.hypothesis_method}"
            )

        confidence = max(0.0, min(1.0, confidence))
        return ConfidenceResult(
            confidence=confidence,
            method=self.config.hypothesis_method,
            contributions=tuple(contributions),
            support=support,
            contradiction=contradiction,
            neutral=neutral,
            diagnostics={
                "assessment_count": len(assessments),
                "independence_unit_count": len(grouped),
                "group_scores": group_scores,
                "group_method": self.config.group_method,
                "group_cap": self.config.group_cap,
                "contradiction_penalty": self.config.contradiction_penalty,
            },
        )

    def build_assessment(
        self,
        *,
        evidence: Evidence,
        relation: EvidenceRelation,
        weight: float,
        confidence: float,
        rationale: str,
        group: EvidenceGroup | None = None,
        module_name: str = "observer_confidence_engine",
        algorithm: str = "explicit_hypothesis_assessment",
        algorithm_version: str = OBSERVER_CONFIDENCE_ENGINE_VERSION,
        metadata: Mapping[str, Any] | None = None,
    ) -> HypothesisAssessment:
        """Create a validated assessment while preserving provenance.

        Relation and weight remain explicit inputs.  The confidence engine does
        not infer whether evidence supports or contradicts a hypothesis.
        """

        if not isinstance(evidence, Evidence):
            raise ConfidenceEngineError("evidence must be Evidence")
        if group is not None:
            if not isinstance(group, EvidenceGroup):
                raise ConfidenceEngineError("group must be EvidenceGroup or None")
            if evidence.evidence_id not in group.evidence_ids:
                raise ConfidenceEngineError(
                    f"Evidence {evidence.evidence_id} is not in group {group.group_id}"
                )

        provenance = Provenance(
            module=module_name,
            algorithm=algorithm,
            version=algorithm_version,
            source_ids=(evidence.evidence_id,),
            metadata=metadata or {},
        )
        try:
            return HypothesisAssessment(
                evidence_id=evidence.evidence_id,
                relation=relation,
                weight=weight,
                confidence=confidence,
                rationale=rationale,
                group_id=group.group_id if group is not None else None,
                provenance=provenance,
            )
        except EvidenceModelError as exc:
            raise ConfidenceEngineError(
                f"Could not build HypothesisAssessment: {exc}"
            ) from exc

    def _aggregate_group(
        self,
        contributions: Sequence[ConfidenceContribution],
    ) -> float:
        values = [item.effective_confidence for item in contributions]
        if not values:
            return 0.0
        if self.config.group_method == "maximum":
            result = max(values)
        elif self.config.group_method == "mean":
            result = sum(values) / len(values)
        else:
            result = _noisy_or(values)
        return min(self.config.group_cap, result)

    @staticmethod
    def _append_relation_score(
        relation: EvidenceRelation,
        score: float,
        support_scores: list[float],
        contradiction_scores: list[float],
        neutral_scores: list[float],
    ) -> None:
        if relation is EvidenceRelation.SUPPORTS:
            support_scores.append(score)
        elif relation is EvidenceRelation.CONTRADICTS:
            contradiction_scores.append(score)
        else:
            neutral_scores.append(score)


def _index_observations(
    items: Mapping[str, Observation] | Iterable[Observation],
) -> dict[str, Observation]:
    if isinstance(items, Mapping):
        result = dict(items)
    else:
        result = {item.observation_id: item for item in items}
    if not all(isinstance(item, Observation) for item in result.values()):
        raise ConfidenceEngineError("observations must contain Observation objects")
    return result


def _index_evidence(
    items: Mapping[str, Evidence] | Iterable[Evidence],
) -> dict[str, Evidence]:
    if isinstance(items, Mapping):
        result = dict(items)
    else:
        result = {item.evidence_id: item for item in items}
    if not all(isinstance(item, Evidence) for item in result.values()):
        raise ConfidenceEngineError("evidence must contain Evidence objects")
    return result


def _index_groups(
    items: Mapping[str, EvidenceGroup] | Iterable[EvidenceGroup],
) -> dict[str, EvidenceGroup]:
    if isinstance(items, Mapping):
        result = dict(items)
    else:
        result = {item.group_id: item for item in items}
    if not all(isinstance(item, EvidenceGroup) for item in result.values()):
        raise ConfidenceEngineError("groups must contain EvidenceGroup objects")
    return result


__all__ = [
    "OBSERVER_CONFIDENCE_ENGINE_VERSION",
    "ConfidenceEngineError",
    "ConfidenceConfig",
    "ConfidenceContribution",
    "ConfidenceResult",
    "ConfidenceEngine",
]
