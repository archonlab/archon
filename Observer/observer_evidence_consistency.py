#!/usr/bin/env python3
"""Evidence consistency checking for Project ARCHON Observer.

This module detects explicit conflicts between neutral Evidence objects before
those conflicts are hidden inside a single hypothesis score.

It operates through declarative ConflictRule objects.  A rule defines two
evidence patterns that should not coexist without review.  The checker then
creates immutable EvidenceConflict records with transparent diagnostics.

Design boundary
---------------
This module does not decide which evidence is correct.  It only records that
two or more claims are difficult to reconcile under a declared rule.
Resolution belongs to later validation, repeated experiments, or Analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

try:
    from .evidence_models import (
        ConflictStatus,
        Evidence,
        EvidenceCategory,
        EvidenceConflict,
        EvidenceModelError,
        EvidenceQuality,
    )
except ImportError:  # Direct execution from the Observer directory.
    from evidence_models import (
        ConflictStatus,
        Evidence,
        EvidenceCategory,
        EvidenceConflict,
        EvidenceModelError,
        EvidenceQuality,
    )


OBSERVER_EVIDENCE_CONSISTENCY_VERSION = "1.0.0"


class ConsistencyCheckerError(ValueError):
    """Raised when conflict rules or evidence inputs are invalid."""


@dataclass(frozen=True, slots=True)
class EvidencePattern:
    """Explicit matcher for one side of a conflict rule."""

    category: EvidenceCategory | None = None
    required_tags: tuple[str, ...] = ()
    title_contains: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    minimum_confidence: float = 0.0
    minimum_quality: EvidenceQuality = EvidenceQuality.UNKNOWN

    def __post_init__(self) -> None:
        if self.category is not None and not isinstance(
            self.category, EvidenceCategory
        ):
            try:
                object.__setattr__(
                    self,
                    "category",
                    EvidenceCategory(str(self.category)),
                )
            except ValueError as exc:
                raise ConsistencyCheckerError(
                    f"Invalid category: {self.category!r}"
                ) from exc

        if not isinstance(self.minimum_quality, EvidenceQuality):
            try:
                object.__setattr__(
                    self,
                    "minimum_quality",
                    EvidenceQuality(str(self.minimum_quality)),
                )
            except ValueError as exc:
                raise ConsistencyCheckerError(
                    f"Invalid minimum_quality: {self.minimum_quality!r}"
                ) from exc

        object.__setattr__(
            self,
            "minimum_confidence",
            _probability(self.minimum_confidence, "minimum_confidence"),
        )
        object.__setattr__(
            self,
            "required_tags",
            tuple(
                str(item).strip().lower()
                for item in self.required_tags
                if str(item).strip()
            ),
        )
        object.__setattr__(
            self,
            "title_contains",
            tuple(
                str(item).strip().lower()
                for item in self.title_contains
                if str(item).strip()
            ),
        )
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(
                str(item).strip()
                for item in self.evidence_ids
                if str(item).strip()
            ),
        )

        if not (
            self.category is not None
            or self.required_tags
            or self.title_contains
            or self.evidence_ids
        ):
            raise ConsistencyCheckerError(
                "EvidencePattern requires at least one matching constraint"
            )


@dataclass(frozen=True, slots=True)
class ConflictRule:
    """Declarative incompatibility between two evidence patterns."""

    title: str
    description: str
    left: EvidencePattern
    right: EvidencePattern
    base_severity: float
    rule_id: str = ""
    symmetric: bool = True
    require_distinct_evidence: bool = True

    def __post_init__(self) -> None:
        title = str(self.title).strip()
        description = str(self.description).strip()
        if not title:
            raise ConsistencyCheckerError("title must not be empty")
        if not isinstance(self.left, EvidencePattern):
            raise ConsistencyCheckerError("left must be EvidencePattern")
        if not isinstance(self.right, EvidencePattern):
            raise ConsistencyCheckerError("right must be EvidencePattern")

        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", description)
        object.__setattr__(
            self,
            "base_severity",
            _probability(self.base_severity, "base_severity"),
        )
        if self.rule_id:
            object.__setattr__(
                self,
                "rule_id",
                str(self.rule_id).strip(),
            )


@dataclass(frozen=True, slots=True)
class ConflictDetection:
    """One detected conflict plus calculation diagnostics."""

    conflict: EvidenceConflict
    rule_id: str
    left_evidence_id: str
    right_evidence_id: str
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConsistencyReport:
    """Complete output of one consistency pass."""

    conflicts: tuple[EvidenceConflict, ...]
    detections: tuple[ConflictDetection, ...]
    checked_rule_count: int
    checked_evidence_count: int
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


def _probability(value: float, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ConsistencyCheckerError(f"{name} must be in [0, 1]") from exc
    if not 0.0 <= numeric <= 1.0:
        raise ConsistencyCheckerError(
            f"{name} must be in [0, 1], got {numeric!r}"
        )
    return numeric


_QUALITY_RANK = {
    EvidenceQuality.UNKNOWN: 0,
    EvidenceQuality.VERY_LOW: 1,
    EvidenceQuality.LOW: 2,
    EvidenceQuality.MEDIUM: 3,
    EvidenceQuality.HIGH: 4,
    EvidenceQuality.VERY_HIGH: 5,
}


class EvidenceConsistencyChecker:
    """Apply declarative conflict rules to a neutral evidence collection."""

    def check(
        self,
        evidence: Iterable[Evidence],
        rules: Sequence[ConflictRule],
    ) -> ConsistencyReport:
        evidence = tuple(evidence)
        rules = tuple(rules)

        if not all(isinstance(item, Evidence) for item in evidence):
            raise ConsistencyCheckerError(
                "evidence must contain Evidence objects"
            )
        if not all(isinstance(item, ConflictRule) for item in rules):
            raise ConsistencyCheckerError(
                "rules must contain ConflictRule objects"
            )

        detections: list[ConflictDetection] = []
        seen_pairs: set[tuple[str, str, str]] = set()

        for rule_index, rule in enumerate(rules):
            rule_id = rule.rule_id or f"conflict_rule:{rule_index + 1}"
            left_matches = tuple(
                item for item in evidence if self._matches(rule.left, item)
            )
            right_matches = tuple(
                item for item in evidence if self._matches(rule.right, item)
            )

            for left_item in left_matches:
                for right_item in right_matches:
                    if (
                        rule.require_distinct_evidence
                        and left_item.evidence_id == right_item.evidence_id
                    ):
                        continue

                    pair = (
                        min(left_item.evidence_id, right_item.evidence_id)
                        if rule.symmetric
                        else left_item.evidence_id,
                        max(left_item.evidence_id, right_item.evidence_id)
                        if rule.symmetric
                        else right_item.evidence_id,
                        rule_id,
                    )
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    severity = self._severity(
                        rule,
                        left_item,
                        right_item,
                    )
                    description = self._description(
                        rule,
                        left_item,
                        right_item,
                    )

                    try:
                        conflict = EvidenceConflict(
                            title=rule.title,
                            description=description,
                            evidence_ids=(
                                left_item.evidence_id,
                                right_item.evidence_id,
                            ),
                            severity=severity,
                            status=ConflictStatus.OPEN,
                            resolution_note="",
                        )
                    except EvidenceModelError as exc:
                        raise ConsistencyCheckerError(
                            f"Could not build EvidenceConflict: {exc}"
                        ) from exc

                    detections.append(
                        ConflictDetection(
                            conflict=conflict,
                            rule_id=rule_id,
                            left_evidence_id=left_item.evidence_id,
                            right_evidence_id=right_item.evidence_id,
                            diagnostics={
                                "left_confidence": left_item.confidence,
                                "right_confidence": right_item.confidence,
                                "left_quality": left_item.quality.value,
                                "right_quality": right_item.quality.value,
                                "base_severity": rule.base_severity,
                            },
                        )
                    )

        conflicts = self.deduplicate(
            item.conflict for item in detections
        )
        return ConsistencyReport(
            conflicts=conflicts,
            detections=tuple(detections),
            checked_rule_count=len(rules),
            checked_evidence_count=len(evidence),
            diagnostics={
                "raw_detection_count": len(detections),
                "deduplicated_conflict_count": len(conflicts),
            },
        )

    def update_resolution(
        self,
        conflict: EvidenceConflict,
        *,
        status: ConflictStatus,
        resolution_note: str = "",
    ) -> EvidenceConflict:
        """Return a new conflict object with updated lifecycle state."""

        if not isinstance(conflict, EvidenceConflict):
            raise ConsistencyCheckerError(
                "conflict must be EvidenceConflict"
            )
        if not isinstance(status, ConflictStatus):
            try:
                status = ConflictStatus(str(status))
            except ValueError as exc:
                raise ConsistencyCheckerError(
                    f"Invalid conflict status: {status!r}"
                ) from exc

        note = str(resolution_note).strip()
        try:
            return EvidenceConflict(
                title=conflict.title,
                description=conflict.description,
                evidence_ids=conflict.evidence_ids,
                severity=conflict.severity,
                status=status,
                resolution_note=note,
                conflict_id=conflict.conflict_id,
            )
        except EvidenceModelError as exc:
            raise ConsistencyCheckerError(
                f"Could not update conflict: {exc}"
            ) from exc

    @staticmethod
    def deduplicate(
        conflicts: Iterable[EvidenceConflict],
    ) -> tuple[EvidenceConflict, ...]:
        """Merge duplicate conflicts over the same evidence set and title."""

        selected: dict[
            tuple[str, tuple[str, ...]],
            EvidenceConflict,
        ] = {}

        for item in conflicts:
            if not isinstance(item, EvidenceConflict):
                raise ConsistencyCheckerError(
                    "conflicts must contain EvidenceConflict objects"
                )
            key = (
                item.title.strip().lower(),
                tuple(sorted(item.evidence_ids)),
            )
            current = selected.get(key)
            if current is None or item.severity > current.severity:
                selected[key] = item

        return tuple(
            sorted(
                selected.values(),
                key=lambda item: (-item.severity, item.title),
            )
        )

    @staticmethod
    def _matches(
        pattern: EvidencePattern,
        evidence: Evidence,
    ) -> bool:
        if (
            pattern.category is not None
            and evidence.category is not pattern.category
        ):
            return False
        if (
            pattern.evidence_ids
            and evidence.evidence_id not in pattern.evidence_ids
        ):
            return False
        tags = {str(item).lower() for item in evidence.tags}
        if (
            pattern.required_tags
            and not set(pattern.required_tags).issubset(tags)
        ):
            return False
        title = evidence.title.lower()
        if pattern.title_contains and not all(
            fragment in title
            for fragment in pattern.title_contains
        ):
            return False
        if evidence.confidence < pattern.minimum_confidence:
            return False
        if (
            _QUALITY_RANK[evidence.quality]
            < _QUALITY_RANK[pattern.minimum_quality]
        ):
            return False
        return True

    @staticmethod
    def _severity(
        rule: ConflictRule,
        left: Evidence,
        right: Evidence,
    ) -> float:
        confidence_factor = (left.confidence + right.confidence) / 2.0
        quality_factor = (
            _QUALITY_RANK[left.quality]
            + _QUALITY_RANK[right.quality]
        ) / (2.0 * max(_QUALITY_RANK.values()))
        quality_factor = max(0.20, quality_factor)

        severity = (
            rule.base_severity
            * confidence_factor
            * quality_factor
        )
        return max(0.0, min(1.0, severity))

    @staticmethod
    def _description(
        rule: ConflictRule,
        left: Evidence,
        right: Evidence,
    ) -> str:
        base = rule.description.strip()
        details = (
            f"Conflicting evidence: '{left.title}' "
            f"({left.evidence_id}) and '{right.title}' "
            f"({right.evidence_id})."
        )
        return f"{base} {details}".strip()


def canonical_conflict_rules() -> tuple[ConflictRule, ...]:
    """Return conservative starter conflict rules.

    These rules only fire when sensor adapters emit explicit semantic tags.
    They are scaffolding for calibration against known worlds, not immutable
    scientific doctrine.
    """

    return (
        ConflictRule(
            rule_id="stable_vs_unstable_identity",
            title="Stable and unstable identity coexist",
            description=(
                "The same evidence package contains strong claims of both "
                "persistent and unstable identity."
            ),
            left=EvidencePattern(
                category=EvidenceCategory.IDENTITY,
                required_tags=("persistent",),
                minimum_confidence=0.60,
            ),
            right=EvidencePattern(
                category=EvidenceCategory.IDENTITY,
                required_tags=("unstable",),
                minimum_confidence=0.60,
            ),
            base_severity=0.85,
        ),
        ConflictRule(
            rule_id="active_repair_vs_no_recovery",
            title="Repair evidence conflicts with failed recovery",
            description=(
                "Active restoration and persistent failure to recover are "
                "simultaneously reported."
            ),
            left=EvidencePattern(
                category=EvidenceCategory.REPAIR,
                required_tags=("active_repair",),
                minimum_confidence=0.60,
            ),
            right=EvidencePattern(
                category=EvidenceCategory.REPAIR,
                required_tags=("no_recovery",),
                minimum_confidence=0.60,
            ),
            base_severity=0.90,
        ),
        ConflictRule(
            rule_id="functional_memory_vs_memory_absent",
            title="Memory evidence is internally inconsistent",
            description=(
                "Functional memory and absence of memory are both strongly "
                "supported in the same run."
            ),
            left=EvidencePattern(
                category=EvidenceCategory.MEMORY,
                required_tags=("functional_memory",),
                minimum_confidence=0.60,
            ),
            right=EvidencePattern(
                category=EvidenceCategory.MEMORY,
                required_tags=("memory_absent",),
                minimum_confidence=0.60,
            ),
            base_severity=0.90,
        ),
        ConflictRule(
            rule_id="adaptive_vs_context_insensitive",
            title="Adaptive interpretation conflicts with context insensitivity",
            description=(
                "Context-sensitive adaptation and context-insensitive behavior "
                "are both reported."
            ),
            left=EvidencePattern(
                category=EvidenceCategory.ADAPTATION,
                required_tags=("context_sensitive",),
                minimum_confidence=0.60,
            ),
            right=EvidencePattern(
                category=EvidenceCategory.ADAPTATION,
                required_tags=("context_insensitive",),
                minimum_confidence=0.60,
            ),
            base_severity=0.85,
        ),
        ConflictRule(
            rule_id="reproduction_vs_no_descendants",
            title="Reproduction evidence conflicts with absent descendants",
            description=(
                "Organized reproduction and absence of viable descendants are "
                "both asserted."
            ),
            left=EvidencePattern(
                category=EvidenceCategory.REPRODUCTION,
                required_tags=("reproduction",),
                minimum_confidence=0.60,
            ),
            right=EvidencePattern(
                category=EvidenceCategory.REPRODUCTION,
                required_tags=("no_viable_descendants",),
                minimum_confidence=0.60,
            ),
            base_severity=0.80,
        ),
        ConflictRule(
            rule_id="crystalline_vs_morphologically_plastic",
            title="Crystalline and plastic morphology coexist",
            description=(
                "Strong crystalline order and strong context-sensitive "
                "morphological plasticity are reported together."
            ),
            left=EvidencePattern(
                category=EvidenceCategory.MORPHOLOGY,
                required_tags=("crystalline",),
                minimum_confidence=0.65,
            ),
            right=EvidencePattern(
                category=EvidenceCategory.MORPHOLOGY,
                required_tags=("plastic",),
                minimum_confidence=0.65,
            ),
            base_severity=0.65,
        ),
    )


__all__ = [
    "OBSERVER_EVIDENCE_CONSISTENCY_VERSION",
    "ConsistencyCheckerError",
    "EvidencePattern",
    "ConflictRule",
    "ConflictDetection",
    "ConsistencyReport",
    "EvidenceConsistencyChecker",
    "canonical_conflict_rules",
]
