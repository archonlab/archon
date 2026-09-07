#!/usr/bin/env python3
"""Competing-hypothesis evaluation for Project ARCHON Observer.

This module turns neutral Evidence objects into explicit, traceable
HypothesisAssessment objects and then delegates numerical aggregation to
``observer_confidence_engine.py``.

Design boundary
---------------
The engine does not inspect raw cellular-automaton state and does not invent
scientific meaning from metric names.  Scientific interpretation is supplied
through declarative HypothesisDefinition and EvidenceRule objects.

A rule states:

    evidence matching these explicit conditions
    -> supports / contradicts / remains neutral toward this hypothesis

The resulting Hypothesis keeps every assessment and rationale, so a verdict
can always be traced back to Evidence and ultimately to Observation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

try:
    from .evidence_models import (
        Evidence,
        EvidenceCategory,
        EvidenceGroup,
        EvidenceModelError,
        EvidenceRelation,
        Hypothesis,
        HypothesisStatus,
        HypothesisType,
        UnknownQuestion,
    )
    from .observer_confidence_engine import (
        ConfidenceEngine,
        ConfidenceEngineError,
        ConfidenceResult,
    )
except ImportError:  # Direct execution from the Observer directory.
    from evidence_models import (
        Evidence,
        EvidenceCategory,
        EvidenceGroup,
        EvidenceModelError,
        EvidenceRelation,
        Hypothesis,
        HypothesisStatus,
        HypothesisType,
        UnknownQuestion,
    )
    from observer_confidence_engine import (
        ConfidenceEngine,
        ConfidenceEngineError,
        ConfidenceResult,
    )


OBSERVER_HYPOTHESIS_ENGINE_VERSION = "1.0.0"


class HypothesisEngineError(ValueError):
    """Raised when a hypothesis definition or evaluation is invalid."""


@dataclass(frozen=True, slots=True)
class EvidenceRule:
    """Declarative rule mapping neutral evidence to one hypothesis relation.

    Matching is explicit and conservative.  A rule may constrain category,
    evidence IDs, required tags, and title fragments.  At least one constraint
    must be present.

    ``required_tags`` uses all-of semantics.
    ``title_contains`` is case-insensitive.
    """

    relation: EvidenceRelation
    weight: float
    rationale: str
    category: EvidenceCategory | None = None
    evidence_ids: tuple[str, ...] = ()
    required_tags: tuple[str, ...] = ()
    title_contains: tuple[str, ...] = ()
    group_independence_key: str | None = None
    minimum_evidence_confidence: float = 0.0
    rule_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.relation, EvidenceRelation):
            try:
                object.__setattr__(self, "relation", EvidenceRelation(str(self.relation)))
            except ValueError as exc:
                raise HypothesisEngineError(
                    f"Invalid evidence relation: {self.relation!r}"
                ) from exc

        if self.category is not None and not isinstance(self.category, EvidenceCategory):
            try:
                object.__setattr__(
                    self, "category", EvidenceCategory(str(self.category))
                )
            except ValueError as exc:
                raise HypothesisEngineError(
                    f"Invalid evidence category: {self.category!r}"
                ) from exc

        object.__setattr__(self, "weight", _probability(self.weight, "weight"))
        object.__setattr__(
            self,
            "minimum_evidence_confidence",
            _probability(
                self.minimum_evidence_confidence,
                "minimum_evidence_confidence",
            ),
        )
        rationale = str(self.rationale).strip()
        if not rationale:
            raise HypothesisEngineError("rationale must not be empty")
        object.__setattr__(self, "rationale", rationale)

        evidence_ids = tuple(str(item).strip() for item in self.evidence_ids if str(item).strip())
        required_tags = tuple(str(item).strip().lower() for item in self.required_tags if str(item).strip())
        title_contains = tuple(str(item).strip().lower() for item in self.title_contains if str(item).strip())
        object.__setattr__(self, "evidence_ids", evidence_ids)
        object.__setattr__(self, "required_tags", required_tags)
        object.__setattr__(self, "title_contains", title_contains)

        if self.group_independence_key is not None:
            key = str(self.group_independence_key).strip()
            object.__setattr__(self, "group_independence_key", key or None)

        if not (
            self.category is not None
            or evidence_ids
            or required_tags
            or title_contains
        ):
            raise HypothesisEngineError(
                "EvidenceRule must contain at least one matching constraint"
            )

        if self.rule_id:
            object.__setattr__(self, "rule_id", str(self.rule_id).strip())


@dataclass(frozen=True, slots=True)
class HypothesisDefinition:
    """Declarative scientific profile for one competing hypothesis."""

    hypothesis_type: HypothesisType
    title: str
    description: str
    rules: tuple[EvidenceRule, ...]
    required_categories: tuple[EvidenceCategory, ...] = ()
    minimum_assessments: int = 1
    plausible_threshold: float = 0.35
    leading_threshold: float = 0.60
    rejected_threshold: float = 0.10
    definition_version: str = "1.0.0"
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.hypothesis_type, HypothesisType):
            try:
                object.__setattr__(
                    self,
                    "hypothesis_type",
                    HypothesisType(str(self.hypothesis_type)),
                )
            except ValueError as exc:
                raise HypothesisEngineError(
                    f"Invalid hypothesis type: {self.hypothesis_type!r}"
                ) from exc

        title = str(self.title).strip()
        if not title:
            raise HypothesisEngineError("title must not be empty")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", str(self.description).strip())

        rules = tuple(self.rules)
        if not rules or not all(isinstance(item, EvidenceRule) for item in rules):
            raise HypothesisEngineError(
                "rules must contain at least one EvidenceRule"
            )
        object.__setattr__(self, "rules", rules)

        categories: list[EvidenceCategory] = []
        for item in self.required_categories:
            if isinstance(item, EvidenceCategory):
                categories.append(item)
            else:
                try:
                    categories.append(EvidenceCategory(str(item)))
                except ValueError as exc:
                    raise HypothesisEngineError(
                        f"Invalid required category: {item!r}"
                    ) from exc
        object.__setattr__(self, "required_categories", tuple(categories))

        minimum = int(self.minimum_assessments)
        if minimum < 0:
            raise HypothesisEngineError("minimum_assessments must be >= 0")
        object.__setattr__(self, "minimum_assessments", minimum)

        for name in (
            "plausible_threshold",
            "leading_threshold",
            "rejected_threshold",
        ):
            object.__setattr__(
                self, name, _probability(getattr(self, name), name)
            )

        if self.rejected_threshold > self.plausible_threshold:
            raise HypothesisEngineError(
                "rejected_threshold must not exceed plausible_threshold"
            )
        if self.plausible_threshold > self.leading_threshold:
            raise HypothesisEngineError(
                "plausible_threshold must not exceed leading_threshold"
            )

        version = str(self.definition_version).strip()
        if not version:
            raise HypothesisEngineError("definition_version must not be empty")
        object.__setattr__(self, "definition_version", version)
        object.__setattr__(
            self,
            "notes",
            tuple(str(item).strip() for item in self.notes if str(item).strip()),
        )


@dataclass(frozen=True, slots=True)
class HypothesisEvaluation:
    """Hypothesis plus transparent confidence diagnostics."""

    hypothesis: Hypothesis
    confidence_result: ConfidenceResult
    matched_rule_ids: tuple[str, ...]
    unmatched_evidence_ids: tuple[str, ...]
    missing_required_categories: tuple[EvidenceCategory, ...]


@dataclass(frozen=True, slots=True)
class HypothesisCompetition:
    """Result of evaluating multiple definitions against one evidence set."""

    evaluations: tuple[HypothesisEvaluation, ...]
    leading_hypothesis_id: str | None
    margin: float
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


def _probability(value: float, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise HypothesisEngineError(f"{name} must be in [0, 1]") from exc
    if not 0.0 <= numeric <= 1.0:
        raise HypothesisEngineError(f"{name} must be in [0, 1], got {numeric!r}")
    return numeric


class HypothesisEngine:
    """Evaluate declarative competing hypotheses against neutral evidence."""

    def __init__(self, confidence_engine: ConfidenceEngine | None = None) -> None:
        self.confidence_engine = confidence_engine or ConfidenceEngine()

    def evaluate(
        self,
        definition: HypothesisDefinition,
        evidence: Iterable[Evidence],
        groups: Iterable[EvidenceGroup] = (),
        unknowns: Iterable[UnknownQuestion] = (),
    ) -> HypothesisEvaluation:
        """Evaluate one hypothesis definition."""

        evidence_items = tuple(evidence)
        group_items = tuple(groups)
        unknown_items = tuple(unknowns)

        if not all(isinstance(item, Evidence) for item in evidence_items):
            raise HypothesisEngineError("evidence must contain Evidence objects")
        if not all(isinstance(item, EvidenceGroup) for item in group_items):
            raise HypothesisEngineError("groups must contain EvidenceGroup objects")
        if not all(isinstance(item, UnknownQuestion) for item in unknown_items):
            raise HypothesisEngineError(
                "unknowns must contain UnknownQuestion objects"
            )

        group_by_key = {
            item.independence_key: item
            for item in group_items
        }

        assessments = []
        matched_rule_ids: list[str] = []
        matched_evidence_ids: set[str] = set()

        for rule_index, rule in enumerate(definition.rules):
            rule_id = rule.rule_id or f"{definition.hypothesis_type.value}:rule:{rule_index + 1}"
            matched_any = False

            for item in evidence_items:
                if not self._matches(rule, item):
                    continue

                group = None
                if rule.group_independence_key is not None:
                    group = group_by_key.get(rule.group_independence_key)
                    if group is None:
                        raise HypothesisEngineError(
                            f"Rule {rule_id!r} references missing independence key "
                            f"{rule.group_independence_key!r}"
                        )
                    if item.evidence_id not in group.evidence_ids:
                        continue

                assessment_confidence = min(
                    item.confidence,
                    max(
                        rule.minimum_evidence_confidence,
                        item.confidence,
                    ),
                )

                try:
                    assessment = self.confidence_engine.build_assessment(
                        evidence=item,
                        relation=rule.relation,
                        weight=rule.weight,
                        confidence=assessment_confidence,
                        rationale=rule.rationale,
                        group=group,
                        algorithm="declarative_evidence_rule",
                        algorithm_version=definition.definition_version,
                        metadata={
                            "hypothesis_type": definition.hypothesis_type.value,
                            "rule_id": rule_id,
                        },
                    )
                except ConfidenceEngineError as exc:
                    raise HypothesisEngineError(
                        f"Could not build assessment for rule {rule_id}: {exc}"
                    ) from exc

                assessments.append(assessment)
                matched_evidence_ids.add(item.evidence_id)
                matched_any = True

            if matched_any:
                matched_rule_ids.append(rule_id)

        available_categories = {item.category for item in evidence_items}
        missing_required = tuple(
            category
            for category in definition.required_categories
            if category not in available_categories
        )

        try:
            confidence_result = self.confidence_engine.hypothesis_confidence(
                assessments,
                evidence_items,
                group_items,
            )
        except ConfidenceEngineError as exc:
            raise HypothesisEngineError(
                f"Could not calculate hypothesis confidence: {exc}"
            ) from exc

        status = self._status(
            definition=definition,
            confidence=confidence_result.confidence,
            assessment_count=len(assessments),
            missing_required_categories=missing_required,
        )

        relevant_unknown_ids = tuple(
            item.question_id
            for item in unknown_items
            if (
                not definition.required_categories
                or item.category in definition.required_categories
            )
        )

        notes = list(definition.notes)
        if missing_required:
            notes.append(
                "Missing required evidence categories: "
                + ", ".join(item.value for item in missing_required)
            )

        try:
            hypothesis = Hypothesis(
                hypothesis_type=definition.hypothesis_type,
                title=definition.title,
                description=definition.description,
                assessments=tuple(assessments),
                confidence=confidence_result.confidence,
                status=status,
                unknown_question_ids=relevant_unknown_ids,
                notes=tuple(notes),
            )
        except EvidenceModelError as exc:
            raise HypothesisEngineError(
                f"Could not build Hypothesis: {exc}"
            ) from exc

        return HypothesisEvaluation(
            hypothesis=hypothesis,
            confidence_result=confidence_result,
            matched_rule_ids=tuple(matched_rule_ids),
            unmatched_evidence_ids=tuple(
                item.evidence_id
                for item in evidence_items
                if item.evidence_id not in matched_evidence_ids
            ),
            missing_required_categories=missing_required,
        )

    def compete(
        self,
        definitions: Sequence[HypothesisDefinition],
        evidence: Iterable[Evidence],
        groups: Iterable[EvidenceGroup] = (),
        unknowns: Iterable[UnknownQuestion] = (),
        *,
        minimum_leading_margin: float = 0.05,
    ) -> HypothesisCompetition:
        """Evaluate competing definitions and identify a cautious leader."""

        margin_required = _probability(
            minimum_leading_margin, "minimum_leading_margin"
        )
        definitions = tuple(definitions)
        if not definitions:
            raise HypothesisEngineError(
                "At least one HypothesisDefinition is required"
            )

        evidence_items = tuple(evidence)
        group_items = tuple(groups)
        unknown_items = tuple(unknowns)

        evaluations = tuple(
            self.evaluate(
                definition,
                evidence_items,
                group_items,
                unknown_items,
            )
            for definition in definitions
        )
        ranked = sorted(
            evaluations,
            key=lambda item: item.hypothesis.confidence,
            reverse=True,
        )

        leader = ranked[0]
        runner_up_confidence = (
            ranked[1].hypothesis.confidence if len(ranked) > 1 else 0.0
        )
        margin = leader.hypothesis.confidence - runner_up_confidence

        leading_id = None
        if (
            leader.hypothesis.status
            in {HypothesisStatus.LEADING, HypothesisStatus.PLAUSIBLE}
            and margin >= margin_required
        ):
            leading_id = leader.hypothesis.hypothesis_id

        return HypothesisCompetition(
            evaluations=evaluations,
            leading_hypothesis_id=leading_id,
            margin=margin,
            diagnostics={
                "definition_count": len(definitions),
                "evidence_count": len(evidence_items),
                "minimum_leading_margin": margin_required,
                "ranked_hypothesis_ids": tuple(
                    item.hypothesis.hypothesis_id for item in ranked
                ),
            },
        )

    @staticmethod
    def _matches(rule: EvidenceRule, evidence: Evidence) -> bool:
        if (
            rule.category is not None
            and evidence.category is not rule.category
        ):
            return False
        if rule.evidence_ids and evidence.evidence_id not in rule.evidence_ids:
            return False
        evidence_tags = {str(item).lower() for item in evidence.tags}
        if rule.required_tags and not set(rule.required_tags).issubset(evidence_tags):
            return False
        title = evidence.title.lower()
        if rule.title_contains and not all(
            fragment in title for fragment in rule.title_contains
        ):
            return False
        if evidence.confidence < rule.minimum_evidence_confidence:
            return False
        return True

    @staticmethod
    def _status(
        *,
        definition: HypothesisDefinition,
        confidence: float,
        assessment_count: int,
        missing_required_categories: Sequence[EvidenceCategory],
    ) -> HypothesisStatus:
        if (
            assessment_count < definition.minimum_assessments
            or missing_required_categories
        ):
            return HypothesisStatus.INSUFFICIENT_EVIDENCE
        if confidence <= definition.rejected_threshold:
            return HypothesisStatus.REJECTED
        if confidence >= definition.leading_threshold:
            return HypothesisStatus.LEADING
        if confidence >= definition.plausible_threshold:
            return HypothesisStatus.PLAUSIBLE
        return HypothesisStatus.DISFAVORED


def canonical_hypothesis_definitions() -> tuple[HypothesisDefinition, ...]:
    """Return conservative starter definitions for the six canonical models.

    These are intentionally broad scaffolds, not final scientific truth.
    They rely on explicit Evidence tags that future sensor adapters must emit.
    Thresholds and weights should be calibrated against known reference worlds.
    """

    return (
        HypothesisDefinition(
            hypothesis_type=HypothesisType.PASSIVE_OSCILLATION,
            title="Passive oscillation",
            description="Persistent activity explained by repetition without autonomous organization.",
            required_categories=(EvidenceCategory.DYNAMICS,),
            rules=(
                EvidenceRule(
                    category=EvidenceCategory.DYNAMICS,
                    required_tags=("periodic",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.85,
                    rationale="Strong periodicity supports passive oscillation.",
                ),
                EvidenceRule(
                    category=EvidenceCategory.REPAIR,
                    required_tags=("active_repair",),
                    relation=EvidenceRelation.CONTRADICTS,
                    weight=0.75,
                    rationale="Active repair is not expected from passive oscillation.",
                ),
            ),
        ),
        HypothesisDefinition(
            hypothesis_type=HypothesisType.STABLE_ATTRACTOR,
            title="Stable attractor",
            description="The world converges toward a stable or repeating dynamical basin.",
            required_categories=(EvidenceCategory.STABILITY,),
            rules=(
                EvidenceRule(
                    category=EvidenceCategory.STABILITY,
                    required_tags=("persistent",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.85,
                    rationale="Persistent stability supports an attractor explanation.",
                ),
                EvidenceRule(
                    category=EvidenceCategory.ADAPTATION,
                    required_tags=("context_sensitive",),
                    relation=EvidenceRelation.CONTRADICTS,
                    weight=0.60,
                    rationale="Context-sensitive adaptation weakens a simple attractor explanation.",
                ),
            ),
        ),
        HypothesisDefinition(
            hypothesis_type=HypothesisType.CRYSTAL_DYNAMICS,
            title="Crystal dynamics",
            description="Ordered growth and persistence are explained by repetitive crystalline organization.",
            required_categories=(EvidenceCategory.MORPHOLOGY,),
            rules=(
                EvidenceRule(
                    category=EvidenceCategory.MORPHOLOGY,
                    required_tags=("crystalline",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.90,
                    rationale="Crystalline morphology supports crystal dynamics.",
                ),
                EvidenceRule(
                    category=EvidenceCategory.MEMORY,
                    required_tags=("functional_memory",),
                    relation=EvidenceRelation.CONTRADICTS,
                    weight=0.55,
                    rationale="Functional memory weakens a purely crystalline explanation.",
                ),
            ),
        ),
        HypothesisDefinition(
            hypothesis_type=HypothesisType.ACTIVE_STRUCTURE,
            title="Active structure",
            description="A persistent organized structure maintains activity without demonstrated adaptation.",
            required_categories=(EvidenceCategory.IDENTITY, EvidenceCategory.DYNAMICS),
            rules=(
                EvidenceRule(
                    category=EvidenceCategory.IDENTITY,
                    required_tags=("persistent",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.75,
                    rationale="Persistent identity supports an active structure.",
                ),
                EvidenceRule(
                    category=EvidenceCategory.DYNAMICS,
                    required_tags=("active",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.70,
                    rationale="Sustained activity supports an active structure.",
                ),
            ),
        ),
        HypothesisDefinition(
            hypothesis_type=HypothesisType.ADAPTIVE_ORGANIZATION,
            title="Adaptive organization",
            description="Organization persists through context-sensitive regulation, recovery, or change.",
            required_categories=(EvidenceCategory.IDENTITY, EvidenceCategory.ADAPTATION),
            rules=(
                EvidenceRule(
                    category=EvidenceCategory.ADAPTATION,
                    required_tags=("context_sensitive",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.90,
                    rationale="Context-sensitive change supports adaptive organization.",
                ),
                EvidenceRule(
                    category=EvidenceCategory.REPAIR,
                    required_tags=("active_repair",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.80,
                    rationale="Active repair supports adaptive organization.",
                ),
                EvidenceRule(
                    category=EvidenceCategory.IDENTITY,
                    required_tags=("persistent",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.70,
                    rationale="Persistent identity supports organized continuity.",
                ),
            ),
        ),
        HypothesisDefinition(
            hypothesis_type=HypothesisType.LIFE_CANDIDATE,
            title="Life candidate",
            description="Multiple independent life-like capacities are jointly supported.",
            required_categories=(
                EvidenceCategory.IDENTITY,
                EvidenceCategory.MEMORY,
                EvidenceCategory.ADAPTATION,
            ),
            minimum_assessments=3,
            plausible_threshold=0.45,
            leading_threshold=0.70,
            rules=(
                EvidenceRule(
                    category=EvidenceCategory.IDENTITY,
                    required_tags=("persistent",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.65,
                    rationale="Persistent identity is one component of life-like organization.",
                ),
                EvidenceRule(
                    category=EvidenceCategory.MEMORY,
                    required_tags=("functional_memory",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.80,
                    rationale="Functional memory supports a life-candidate explanation.",
                ),
                EvidenceRule(
                    category=EvidenceCategory.ADAPTATION,
                    required_tags=("context_sensitive",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.85,
                    rationale="Context-sensitive adaptation supports a life candidate.",
                ),
                EvidenceRule(
                    category=EvidenceCategory.REPRODUCTION,
                    required_tags=("reproduction",),
                    relation=EvidenceRelation.SUPPORTS,
                    weight=0.75,
                    rationale="Reproduction provides additional independent life-like support.",
                ),
            ),
        ),
    )


__all__ = [
    "OBSERVER_HYPOTHESIS_ENGINE_VERSION",
    "HypothesisEngineError",
    "EvidenceRule",
    "HypothesisDefinition",
    "HypothesisEvaluation",
    "HypothesisCompetition",
    "HypothesisEngine",
    "canonical_hypothesis_definitions",
]
