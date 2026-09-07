#!/usr/bin/env python3
"""Unknown-question detection for Project ARCHON Observer.

This module identifies explicit gaps in the current evidence package.

It does not infer life, emergence, or mechanism.  It answers narrower
questions:

- Which scientific categories are still unobserved?
- Which expected observations are missing?
- Which hypothesis definitions remain under-supported?
- Which unknowns have been partially or fully resolved by later evidence?

The output is a set of immutable ``UnknownQuestion`` objects that can be stored
in EvidenceReport and later consumed by Research Director or Experiment
Planner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

try:
    from .evidence_models import (
        Evidence,
        EvidenceCategory,
        EvidenceModelError,
        Hypothesis,
        HypothesisStatus,
        Observation,
        UnknownQuestion,
        UnknownStatus,
    )
    from .observer_hypothesis_engine import (
        HypothesisDefinition,
        HypothesisEvaluation,
    )
except ImportError:  # Direct execution from the Observer directory.
    from evidence_models import (
        Evidence,
        EvidenceCategory,
        EvidenceModelError,
        Hypothesis,
        HypothesisStatus,
        Observation,
        UnknownQuestion,
        UnknownStatus,
    )
    from observer_hypothesis_engine import (
        HypothesisDefinition,
        HypothesisEvaluation,
    )


OBSERVER_UNKNOWNS_VERSION = "1.0.0"


class UnknownEngineError(ValueError):
    """Raised when unknown-question generation is invalid."""


@dataclass(frozen=True, slots=True)
class UnknownCriterion:
    """Declarative condition that creates one scientific unknown.

    ``required_observation_names`` and ``required_evidence_tags`` use all-of
    semantics.  A criterion becomes unresolved when one or more required items
    are absent.

    ``minimum_evidence_count`` may be used for broad domains where named
    observations are not yet standardized.
    """

    category: EvidenceCategory
    title: str
    description: str
    priority: float
    required_observation_names: tuple[str, ...] = ()
    required_evidence_tags: tuple[str, ...] = ()
    minimum_evidence_count: int = 0
    criterion_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.category, EvidenceCategory):
            try:
                object.__setattr__(
                    self,
                    "category",
                    EvidenceCategory(str(self.category)),
                )
            except ValueError as exc:
                raise UnknownEngineError(
                    f"Invalid category: {self.category!r}"
                ) from exc

        title = str(self.title).strip()
        description = str(self.description).strip()
        if not title:
            raise UnknownEngineError("title must not be empty")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "priority", _probability(self.priority, "priority"))

        observation_names = tuple(
            str(item).strip()
            for item in self.required_observation_names
            if str(item).strip()
        )
        evidence_tags = tuple(
            str(item).strip().lower()
            for item in self.required_evidence_tags
            if str(item).strip()
        )
        object.__setattr__(
            self,
            "required_observation_names",
            observation_names,
        )
        object.__setattr__(
            self,
            "required_evidence_tags",
            evidence_tags,
        )

        count = int(self.minimum_evidence_count)
        if count < 0:
            raise UnknownEngineError("minimum_evidence_count must be >= 0")
        object.__setattr__(self, "minimum_evidence_count", count)

        if not observation_names and not evidence_tags and count <= 0:
            raise UnknownEngineError(
                "UnknownCriterion must define at least one requirement"
            )

        if self.criterion_id:
            object.__setattr__(
                self,
                "criterion_id",
                str(self.criterion_id).strip(),
            )


@dataclass(frozen=True, slots=True)
class UnknownDetection:
    """One generated question plus transparent gap diagnostics."""

    question: UnknownQuestion
    criterion_id: str
    missing_observation_names: tuple[str, ...] = ()
    missing_evidence_tags: tuple[str, ...] = ()
    evidence_count: int = 0
    required_evidence_count: int = 0
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UnknownResolution:
    """Updated lifecycle state for a previously recorded unknown."""

    question: UnknownQuestion
    matched_evidence_ids: tuple[str, ...]
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


def _probability(value: float, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise UnknownEngineError(f"{name} must be in [0, 1]") from exc
    if not 0.0 <= numeric <= 1.0:
        raise UnknownEngineError(f"{name} must be in [0, 1], got {numeric!r}")
    return numeric


class UnknownEngine:
    """Detect and update explicit scientific unknowns."""

    def detect(
        self,
        criteria: Sequence[UnknownCriterion],
        observations: Iterable[Observation],
        evidence: Iterable[Evidence],
    ) -> tuple[UnknownDetection, ...]:
        """Generate questions for criteria not fully satisfied."""

        criteria = tuple(criteria)
        observations = tuple(observations)
        evidence = tuple(evidence)

        if not all(isinstance(item, UnknownCriterion) for item in criteria):
            raise UnknownEngineError(
                "criteria must contain UnknownCriterion objects"
            )
        if not all(isinstance(item, Observation) for item in observations):
            raise UnknownEngineError(
                "observations must contain Observation objects"
            )
        if not all(isinstance(item, Evidence) for item in evidence):
            raise UnknownEngineError(
                "evidence must contain Evidence objects"
            )

        observation_names_by_category: dict[EvidenceCategory, set[str]] = {}
        for item in observations:
            observation_names_by_category.setdefault(
                item.category,
                set(),
            ).add(item.name)

        evidence_by_category: dict[EvidenceCategory, list[Evidence]] = {}
        tags_by_category: dict[EvidenceCategory, set[str]] = {}
        for item in evidence:
            evidence_by_category.setdefault(item.category, []).append(item)
            tags_by_category.setdefault(item.category, set()).update(
                str(tag).lower() for tag in item.tags
            )

        detections: list[UnknownDetection] = []
        for index, criterion in enumerate(criteria):
            observed_names = observation_names_by_category.get(
                criterion.category,
                set(),
            )
            available_tags = tags_by_category.get(
                criterion.category,
                set(),
            )
            category_evidence = evidence_by_category.get(
                criterion.category,
                [],
            )

            missing_observations = tuple(
                name
                for name in criterion.required_observation_names
                if name not in observed_names
            )
            missing_tags = tuple(
                tag
                for tag in criterion.required_evidence_tags
                if tag not in available_tags
            )
            count_gap = max(
                0,
                criterion.minimum_evidence_count - len(category_evidence),
            )

            if not missing_observations and not missing_tags and count_gap == 0:
                continue

            completeness = self._completeness(
                criterion,
                missing_observations,
                missing_tags,
                len(category_evidence),
            )
            status = (
                UnknownStatus.OPEN
                if completeness <= 0.0
                else UnknownStatus.PARTIAL
            )

            criterion_id = (
                criterion.criterion_id
                or f"{criterion.category.value}:criterion:{index + 1}"
            )
            description = self._build_description(
                criterion,
                missing_observations,
                missing_tags,
                count_gap,
            )

            try:
                question = UnknownQuestion(
                    category=criterion.category,
                    title=criterion.title,
                    description=description,
                    priority=criterion.priority,
                    required_observation_names=missing_observations,
                    status=status,
                    resolution_evidence_ids=(),
                )
            except EvidenceModelError as exc:
                raise UnknownEngineError(
                    f"Could not build UnknownQuestion: {exc}"
                ) from exc

            detections.append(
                UnknownDetection(
                    question=question,
                    criterion_id=criterion_id,
                    missing_observation_names=missing_observations,
                    missing_evidence_tags=missing_tags,
                    evidence_count=len(category_evidence),
                    required_evidence_count=criterion.minimum_evidence_count,
                    diagnostics={
                        "completeness": completeness,
                        "count_gap": count_gap,
                        "available_observation_names": tuple(sorted(observed_names)),
                        "available_evidence_tags": tuple(sorted(available_tags)),
                    },
                )
            )

        return tuple(detections)

    def detect_from_hypothesis_evaluations(
        self,
        definitions: Sequence[HypothesisDefinition],
        evaluations: Sequence[HypothesisEvaluation],
    ) -> tuple[UnknownQuestion, ...]:
        """Create unknowns for missing hypothesis evidence categories."""

        definition_by_type = {
            item.hypothesis_type: item
            for item in definitions
        }
        questions: list[UnknownQuestion] = []

        for evaluation in evaluations:
            hypothesis = evaluation.hypothesis
            definition = definition_by_type.get(hypothesis.hypothesis_type)
            if definition is None:
                continue

            for category in evaluation.missing_required_categories:
                priority = self._hypothesis_gap_priority(
                    hypothesis,
                    category,
                )
                try:
                    questions.append(
                        UnknownQuestion(
                            category=category,
                            title=(
                                f"Missing {category.value} evidence for "
                                f"{hypothesis.title}"
                            ),
                            description=(
                                f"The hypothesis '{hypothesis.title}' cannot be "
                                f"assessed fully because evidence category "
                                f"'{category.value}' is absent."
                            ),
                            priority=priority,
                            required_observation_names=(),
                            status=UnknownStatus.OPEN,
                            resolution_evidence_ids=(),
                        )
                    )
                except EvidenceModelError as exc:
                    raise UnknownEngineError(
                        f"Could not build hypothesis-gap unknown: {exc}"
                    ) from exc

        return self.deduplicate(questions)

    def update_status(
        self,
        question: UnknownQuestion,
        observations: Iterable[Observation],
        evidence: Iterable[Evidence],
    ) -> UnknownResolution:
        """Update one existing unknown using later observations and evidence.

        Resolution is conservative:
        - RESOLVED when all named observations exist in the same category;
        - PARTIAL when some named observations exist or category evidence exists;
        - OPEN otherwise.
        """

        if not isinstance(question, UnknownQuestion):
            raise UnknownEngineError(
                "question must be an UnknownQuestion"
            )

        observations = tuple(observations)
        evidence = tuple(evidence)

        relevant_observations = tuple(
            item
            for item in observations
            if item.category is question.category
        )
        relevant_evidence = tuple(
            item
            for item in evidence
            if item.category is question.category
        )

        available_names = {item.name for item in relevant_observations}
        required_names = set(question.required_observation_names)
        matched_names = required_names.intersection(available_names)

        if required_names and matched_names == required_names:
            status = UnknownStatus.RESOLVED
        elif matched_names or relevant_evidence:
            status = UnknownStatus.PARTIAL
        else:
            status = UnknownStatus.OPEN

        resolution_ids = (
            tuple(item.evidence_id for item in relevant_evidence)
            if status is UnknownStatus.RESOLVED
            else ()
        )

        if status is UnknownStatus.RESOLVED and not resolution_ids:
            # The model contract requires at least one resolving Evidence ID.
            status = UnknownStatus.PARTIAL

        try:
            updated = UnknownQuestion(
                category=question.category,
                title=question.title,
                description=question.description,
                priority=question.priority,
                required_observation_names=tuple(
                    name
                    for name in question.required_observation_names
                    if name not in available_names
                ),
                status=status,
                resolution_evidence_ids=resolution_ids,
                question_id=question.question_id,
            )
        except EvidenceModelError as exc:
            raise UnknownEngineError(
                f"Could not update UnknownQuestion: {exc}"
            ) from exc

        return UnknownResolution(
            question=updated,
            matched_evidence_ids=tuple(
                item.evidence_id for item in relevant_evidence
            ),
            diagnostics={
                "available_observation_names": tuple(sorted(available_names)),
                "matched_required_names": tuple(sorted(matched_names)),
                "relevant_evidence_count": len(relevant_evidence),
            },
        )

    @staticmethod
    def deduplicate(
        questions: Iterable[UnknownQuestion],
    ) -> tuple[UnknownQuestion, ...]:
        """Deduplicate semantically equivalent unknowns.

        Questions are considered equivalent when category, normalized title,
        and required observation names match.  The highest-priority instance
        is retained.
        """

        selected: dict[
            tuple[EvidenceCategory, str, tuple[str, ...]],
            UnknownQuestion,
        ] = {}

        for item in questions:
            if not isinstance(item, UnknownQuestion):
                raise UnknownEngineError(
                    "questions must contain UnknownQuestion objects"
                )
            key = (
                item.category,
                item.title.strip().lower(),
                tuple(sorted(item.required_observation_names)),
            )
            current = selected.get(key)
            if current is None or item.priority > current.priority:
                selected[key] = item

        return tuple(
            sorted(
                selected.values(),
                key=lambda item: (-item.priority, item.category.value, item.title),
            )
        )

    @staticmethod
    def _completeness(
        criterion: UnknownCriterion,
        missing_observations: Sequence[str],
        missing_tags: Sequence[str],
        evidence_count: int,
    ) -> float:
        total_requirements = (
            len(criterion.required_observation_names)
            + len(criterion.required_evidence_tags)
            + (1 if criterion.minimum_evidence_count > 0 else 0)
        )
        if total_requirements == 0:
            return 1.0

        satisfied = (
            len(criterion.required_observation_names) - len(missing_observations)
            + len(criterion.required_evidence_tags) - len(missing_tags)
        )
        if criterion.minimum_evidence_count > 0:
            satisfied += int(
                evidence_count >= criterion.minimum_evidence_count
            )

        return max(0.0, min(1.0, satisfied / total_requirements))

    @staticmethod
    def _build_description(
        criterion: UnknownCriterion,
        missing_observations: Sequence[str],
        missing_tags: Sequence[str],
        count_gap: int,
    ) -> str:
        parts = [criterion.description] if criterion.description else []

        if missing_observations:
            parts.append(
                "Missing observations: "
                + ", ".join(missing_observations)
                + "."
            )
        if missing_tags:
            parts.append(
                "Missing evidence tags: "
                + ", ".join(missing_tags)
                + "."
            )
        if count_gap:
            parts.append(
                f"Need {count_gap} additional evidence item(s) in "
                f"category '{criterion.category.value}'."
            )

        return " ".join(parts).strip()

    @staticmethod
    def _hypothesis_gap_priority(
        hypothesis: Hypothesis,
        category: EvidenceCategory,
    ) -> float:
        base = 0.55

        if hypothesis.status is HypothesisStatus.INSUFFICIENT_EVIDENCE:
            base += 0.20
        elif hypothesis.status is HypothesisStatus.PLAUSIBLE:
            base += 0.15
        elif hypothesis.status is HypothesisStatus.LEADING:
            base += 0.10

        if category in {
            EvidenceCategory.MEMORY,
            EvidenceCategory.ADAPTATION,
            EvidenceCategory.REPRODUCTION,
            EvidenceCategory.REPAIR,
        }:
            base += 0.05

        return min(1.0, base)


def canonical_unknown_criteria() -> tuple[UnknownCriterion, ...]:
    """Return starter unknown criteria for the first Evidence Framework phase.

    These criteria are intentionally conservative.  They identify missing
    observational domains without declaring that any one domain is sufficient
    for life or emergence.
    """

    return (
        UnknownCriterion(
            category=EvidenceCategory.IDENTITY,
            title="Identity continuity is untested",
            description=(
                "The current evidence package does not yet establish whether "
                "an organization preserves identity through time."
            ),
            priority=0.85,
            required_observation_names=("identity_persistence",),
            minimum_evidence_count=1,
            criterion_id="identity_continuity",
        ),
        UnknownCriterion(
            category=EvidenceCategory.REPAIR,
            title="Repair capacity is unknown",
            description=(
                "No adequate observation yet establishes whether damage is "
                "followed by organized restoration."
            ),
            priority=0.80,
            required_evidence_tags=("active_repair",),
            minimum_evidence_count=1,
            criterion_id="repair_capacity",
        ),
        UnknownCriterion(
            category=EvidenceCategory.MEMORY,
            title="Memory persistence is unknown",
            description=(
                "The evidence package does not yet establish whether prior "
                "states influence later behavior."
            ),
            priority=0.90,
            required_evidence_tags=("functional_memory",),
            minimum_evidence_count=1,
            criterion_id="memory_persistence",
        ),
        UnknownCriterion(
            category=EvidenceCategory.ADAPTATION,
            title="Adaptive response is unknown",
            description=(
                "No adequate evidence yet establishes context-sensitive "
                "organizational change."
            ),
            priority=0.90,
            required_evidence_tags=("context_sensitive",),
            minimum_evidence_count=1,
            criterion_id="adaptive_response",
        ),
        UnknownCriterion(
            category=EvidenceCategory.REPRODUCTION,
            title="Reproduction is untested",
            description=(
                "The current run has not yet established whether organized "
                "descendants are produced."
            ),
            priority=0.65,
            required_evidence_tags=("reproduction",),
            minimum_evidence_count=1,
            criterion_id="reproduction",
        ),
        UnknownCriterion(
            category=EvidenceCategory.RESOURCE_USAGE,
            title="Resource economy is unknown",
            description=(
                "The evidence package does not yet describe acquisition, "
                "transport, consumption, or recycling of resources."
            ),
            priority=0.70,
            minimum_evidence_count=1,
            criterion_id="resource_economy",
        ),
        UnknownCriterion(
            category=EvidenceCategory.COMMUNICATION,
            title="Communication is unknown",
            description=(
                "The current run has not established information transfer "
                "between distinct organized entities."
            ),
            priority=0.55,
            minimum_evidence_count=1,
            criterion_id="communication",
        ),
    )


__all__ = [
    "OBSERVER_UNKNOWNS_VERSION",
    "UnknownEngineError",
    "UnknownCriterion",
    "UnknownDetection",
    "UnknownResolution",
    "UnknownEngine",
    "canonical_unknown_criteria",
]
