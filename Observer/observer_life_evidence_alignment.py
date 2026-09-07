#!/usr/bin/env python3
"""Shadow alignment between Life Evidence and Evidence Framework hypotheses.

The legacy-compatible Life Evidence model and the domain-neutral Evidence
Framework both evaluate the same six competing explanations.  This module
compares their outputs without feeding either conclusion back into the other
system.  Keeping the comparison observational avoids circular evidence and
preserves both pipelines as independently calibratable instruments.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

try:
    from .evidence_models import EvidenceReport, HypothesisType
except ImportError:
    from evidence_models import EvidenceReport, HypothesisType


LIFE_EVIDENCE_ALIGNMENT_VERSION = "1.0.0"
LIFE_EVIDENCE_ALIGNMENT_SCHEMA = "archon.observer.life-evidence-alignment"

_CANONICAL_TYPES = tuple(
    item for item in HypothesisType if item is not HypothesisType.CUSTOM
)
_TYPE_BY_NORMALIZED_NAME = {
    item.value: item for item in _CANONICAL_TYPES
}


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _canonical_type(value: Any) -> HypothesisType | None:
    normalized = str(value or "").strip().lower()
    return _TYPE_BY_NORMALIZED_NAME.get(normalized)


def _ranked(scores: Mapping[str, float]) -> tuple[str, ...]:
    return tuple(
        key for key, _ in sorted(
            scores.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )


def _rank_overlap(
    left: tuple[str, ...],
    right: tuple[str, ...],
    *,
    depth: int = 3,
) -> float:
    """Return order-aware overlap for the first ``depth`` ranked hypotheses."""

    if not left or not right:
        return 0.0
    limit = min(depth, len(left), len(right))
    if limit <= 0:
        return 0.0
    weights = tuple(range(limit, 0, -1))
    denominator = float(sum(weights))
    score = 0.0
    for index in range(limit):
        if left[index] == right[index]:
            score += weights[index]
        elif left[index] in right[:limit]:
            score += weights[index] * 0.35
    return round(score / denominator, 6)


@dataclass(frozen=True, slots=True)
class LifeEvidenceAlignment:
    """Serializable Stage 1G shadow comparison."""

    tick: int
    status: str
    severity: str
    comparable: bool
    life_verdict: str | None
    life_winner: str | None
    life_confidence: float
    framework_leader: str | None
    framework_top: str | None
    framework_top_confidence: float
    top_match: bool | None
    rank_overlap_top3: float
    life_scores: Mapping[str, float]
    framework_scores: Mapping[str, float]
    framework_statuses: Mapping[str, str]
    score_deltas: Mapping[str, float]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    life_evidence_version: str | None
    evidence_report_id: str
    schema: str = LIFE_EVIDENCE_ALIGNMENT_SCHEMA
    schema_version: str = LIFE_EVIDENCE_ALIGNMENT_VERSION
    mode: str = "shadow"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "mode": self.mode,
            "tick": self.tick,
            "status": self.status,
            "severity": self.severity,
            "comparable": self.comparable,
            "life_evidence": {
                "version": self.life_evidence_version,
                "verdict": self.life_verdict,
                "winner": self.life_winner,
                "confidence": self.life_confidence,
                "hypothesis_scores": dict(self.life_scores),
            },
            "evidence_framework": {
                "report_id": self.evidence_report_id,
                "leader": self.framework_leader,
                "top_ranked": self.framework_top,
                "top_confidence": self.framework_top_confidence,
                "hypothesis_scores": dict(self.framework_scores),
                "hypothesis_statuses": dict(self.framework_statuses),
            },
            "comparison": {
                "top_match": self.top_match,
                "rank_overlap_top3": self.rank_overlap_top3,
                "score_deltas": dict(self.score_deltas),
                "reasons": list(self.reasons),
                "warnings": list(self.warnings),
            },
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )


def build_life_evidence_alignment(
    *,
    current: Mapping[str, Any],
    report: EvidenceReport,
    tick: int,
) -> LifeEvidenceAlignment:
    """Compare one Life Evidence snapshot with one EvidenceReport."""

    if not isinstance(report, EvidenceReport):
        raise TypeError("report must be an EvidenceReport")

    raw_life_scores = current.get("life_evidence_hypotheses")
    raw_life_scores = (
        raw_life_scores if isinstance(raw_life_scores, Mapping) else {}
    )
    life_scores: dict[str, float] = {}
    warnings: list[str] = []
    for raw_name, raw_score in raw_life_scores.items():
        hypothesis_type = _canonical_type(raw_name)
        if hypothesis_type is None:
            warnings.append(f"unmapped Life Evidence hypothesis: {raw_name}")
            continue
        life_scores[hypothesis_type.value] = _clamp(raw_score)

    framework_scores = {
        item.hypothesis_type.value: _clamp(item.confidence)
        for item in report.hypotheses
        if item.hypothesis_type in _CANONICAL_TYPES
    }
    framework_statuses = {
        item.hypothesis_type.value: item.status.value
        for item in report.hypotheses
        if item.hypothesis_type in _CANONICAL_TYPES
    }
    framework_by_id = {
        item.hypothesis_id: item for item in report.hypotheses
    }
    framework_leader_type = None
    if report.leading_hypothesis_id:
        leader = framework_by_id.get(report.leading_hypothesis_id)
        if leader is not None and leader.hypothesis_type in _CANONICAL_TYPES:
            framework_leader_type = leader.hypothesis_type

    life_verdict_type = _canonical_type(
        current.get("life_evidence_verdict")
    )
    life_winner_type = _canonical_type(
        current.get("life_evidence_winner")
    )
    life_rank = _ranked(life_scores)
    framework_rank = _ranked(framework_scores)
    framework_top = framework_rank[0] if framework_rank else None
    primary_life_type = life_verdict_type or life_winner_type

    missing_life = sorted(
        item.value for item in _CANONICAL_TYPES
        if item.value not in life_scores
    )
    missing_framework = sorted(
        item.value for item in _CANONICAL_TYPES
        if item.value not in framework_scores
    )
    reasons: list[str] = []
    if missing_life:
        reasons.append(
            "Life Evidence lacks canonical hypotheses: "
            + ", ".join(missing_life)
        )
    if missing_framework:
        reasons.append(
            "Evidence Framework lacks canonical hypotheses: "
            + ", ".join(missing_framework)
        )
    if primary_life_type is None:
        reasons.append("Life Evidence has no canonical verdict or winner")
    if framework_leader_type is None:
        reasons.append("Evidence Framework has no explicit leading hypothesis")

    comparable = not (
        missing_life
        or missing_framework
        or primary_life_type is None
        or framework_leader_type is None
    )
    top_match: bool | None = None
    if primary_life_type is not None and framework_top is not None:
        top_match = primary_life_type.value == framework_top

    life_confidence = _clamp(current.get("life_evidence_confidence"))
    framework_top_confidence = (
        framework_scores.get(framework_top, 0.0)
        if framework_top is not None else 0.0
    )

    if not comparable:
        status = "insufficient_data"
        severity = "none"
    elif primary_life_type is framework_leader_type:
        status = "agreement"
        severity = "none"
        reasons.append("Both systems select the same canonical hypothesis")
    else:
        status = "shadow_disagreement"
        joint_confidence = min(
            life_confidence,
            framework_scores.get(framework_leader_type.value, 0.0),
        )
        if joint_confidence >= 0.70:
            severity = "high"
        elif joint_confidence >= 0.45:
            severity = "medium"
        else:
            severity = "low"
        reasons.append(
            "Life Evidence and Evidence Framework select different hypotheses"
        )

    score_deltas = {
        item.value: round(
            life_scores[item.value] - framework_scores[item.value],
            6,
        )
        for item in _CANONICAL_TYPES
        if item.value in life_scores and item.value in framework_scores
    }

    return LifeEvidenceAlignment(
        tick=max(0, int(tick)),
        status=status,
        severity=severity,
        comparable=comparable,
        life_verdict=(
            life_verdict_type.value if life_verdict_type is not None else None
        ),
        life_winner=(
            life_winner_type.value if life_winner_type is not None else None
        ),
        life_confidence=life_confidence,
        framework_leader=(
            framework_leader_type.value
            if framework_leader_type is not None else None
        ),
        framework_top=framework_top,
        framework_top_confidence=framework_top_confidence,
        top_match=top_match,
        rank_overlap_top3=_rank_overlap(life_rank, framework_rank),
        life_scores=life_scores,
        framework_scores=framework_scores,
        framework_statuses=framework_statuses,
        score_deltas=score_deltas,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        life_evidence_version=(
            str(current.get("life_evidence_version"))
            if current.get("life_evidence_version")
            else None
        ),
        evidence_report_id=report.report_id,
    )


__all__ = [
    "LIFE_EVIDENCE_ALIGNMENT_VERSION",
    "LIFE_EVIDENCE_ALIGNMENT_SCHEMA",
    "LifeEvidenceAlignment",
    "build_life_evidence_alignment",
]
