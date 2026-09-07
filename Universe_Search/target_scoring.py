#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project ARCHON constraint-aware target scoring v1.1.

This module converts Analyzer search-job constraints into a bounded Search
bonus and an auditable target-distance report.

Supported examples:
- EMG >= 0.65
- VAL < 0.35 or FP > 0.45
- collapsed = false
- final_tick >= 50000

Safety rule:
Missing metrics never count as a match. They reduce coverage and therefore
reduce the target bonus instead of silently inventing evidence.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from typing import Any

VERSION = "Project ARCHON Target Scoring v1.1"

ALIASES = {
    "EMG": "emergence_score",
    "VAL": "validation_quality",
    "FP": "validation_false_positive_risk",
    "FN": "validation_false_negative_risk",
    "KNOW": "knowledge_score",
    "FB": "feedback_score",
    "CIV": "civilization_score",
    "memory": "knowledge_memory",
    "stability": "stability_index",
    "effective_risk": "feedback_effective_risk",
    "self_direction": "feedback_self_direction",
    "collapsed": "collapsed",
    "final_tick": "final_tick",
}

# Conservative fallbacks for Search-time metrics that predate Analyzer names.
# Exact Analyzer fields always win when present.
FALLBACK_METRICS = {
    "emergence_score": (
        "emergence_score",
        "observer_score",
        "information_survival",
        "best_entity_quality",
        "best_region_score",
    ),
    "validation_quality": (
        "validation_quality",
        "post_test_truth",
        "information_temporal_stability",
        "stability_index",
    ),
    "validation_false_positive_risk": (
        "validation_false_positive_risk",
        "false_positive_risk",
        "defect_density",
    ),
    "validation_false_negative_risk": (
        "validation_false_negative_risk",
        "false_negative_risk",
    ),
    "knowledge_score": (
        "knowledge_score",
        "knowledge_memory",
        "collective_memory_score",
    ),
    "feedback_score": (
        "feedback_score",
        "feedback_self_direction",
    ),
    "civilization_score": (
        "civilization_score",
        "institution_score",
    ),
    "knowledge_memory": (
        "knowledge_memory",
        "memory_trace_score",
        "collective_memory_score",
    ),
    "stability_index": (
        "stability_index",
        "information_temporal_stability",
        "post_test_truth",
    ),
    "feedback_effective_risk": (
        "feedback_effective_risk",
        "effective_risk",
    ),
    "feedback_self_direction": (
        "feedback_self_direction",
        "self_direction",
    ),
    "collapsed": (
        "collapsed",
        "collapse_tick",
        # Search-time candidate proxy.  This is explicitly reported through
        # source_metric so downstream consumers can require Observer
        # validation before treating a Search hit as canonical cohort evidence.
        "organism_collapse_tick",
    ),
    "final_tick": (
        "final_tick",
        "ticks",
        "tick",
    ),
}

_COMPARISON_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)?\s*"
    r"(>=|<=|==|=|>|<)\s*"
    r"(true|false|-?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


@dataclass
class ClauseResult:
    alias: str
    metric: str
    operator: str
    threshold: Any
    value: Any
    source_metric: str | None
    available: bool
    passed: bool
    normalized_deficit: float
    expression: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TargetScoreResult:
    active: bool
    exact_match: bool
    coverage: float
    target_distance: float
    target_bonus: float
    passed_constraints: int
    total_constraints: int
    missing_metrics: list[str]
    clauses: list[ClauseResult]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["clauses"] = [x.to_dict() for x in self.clauses]
        return payload


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _normalize_metric_value(metric: str, value: Any) -> Any:
    if metric == "collapsed":
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        # collapse_tick present means collapsed.
        if isinstance(value, (int, float)):
            return bool(value >= 0)
        text = str(value).strip().lower()
        if text in {"true", "yes", "1", "collapsed"}:
            return True
        if text in {"false", "no", "0", "alive", "persistent"}:
            return False
        return None

    number = _to_number(value)
    if number is None:
        return None

    # Known legacy scores are not always normalized to [0, 1].
    if metric == "emergence_score" and number > 1.0:
        number = number / 100.0
    if metric == "knowledge_memory" and number > 1.0:
        number = number / 120.0
    if metric in {
        "validation_quality",
        "validation_false_positive_risk",
        "validation_false_negative_risk",
        "knowledge_score",
        "feedback_score",
        "civilization_score",
        "stability_index",
        "feedback_effective_risk",
        "feedback_self_direction",
        "emergence_score",
    }:
        number = max(0.0, min(1.0, number))
    return number


def resolve_value(metrics: dict[str, Any], alias: str) -> tuple[Any, str | None, str]:
    metric = ALIASES.get(alias, alias)
    candidates = FALLBACK_METRICS.get(metric, (metric,))
    for key in candidates:
        if key not in metrics:
            continue
        raw = metrics.get(key)
        if metric == "collapsed" and key in {"collapse_tick", "organism_collapse_tick"}:
            # Presence of a collapse-tick field is itself evidence.  ``None``
            # means the probe completed without collapse, not that the metric
            # is missing.  A failed organism probe remains unavailable.
            if key == "organism_collapse_tick" and metrics.get("organism_analysis_error") not in {None, ""}:
                continue
            if raw is None:
                return False, key, metric
            number = _to_number(raw)
            if number is not None:
                return bool(number >= 0), key, metric
            value = _normalize_metric_value(metric, raw)
            if value is not None:
                return value, key, metric
            continue
        value = _normalize_metric_value(metric, raw)
        if value is not None:
            return value, key, metric
    return None, None, metric


def _parse_threshold(token: str) -> Any:
    lowered = token.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return float(lowered)


def _compare(value: Any, operator: str, threshold: Any) -> tuple[bool, float]:
    if isinstance(threshold, bool):
        passed = bool(value) == threshold
        return passed, 0.0 if passed else 1.0

    numeric = _to_number(value)
    target = _to_number(threshold)
    if numeric is None or target is None:
        return False, 1.0

    if operator in {"=", "=="}:
        deficit = abs(numeric - target)
        return deficit <= 1e-12, min(1.0, deficit / max(abs(target), 1.0))
    if operator == ">=":
        deficit = max(0.0, target - numeric)
    elif operator == ">":
        deficit = max(0.0, target - numeric + 1e-12)
    elif operator == "<=":
        deficit = max(0.0, numeric - target)
    elif operator == "<":
        deficit = max(0.0, numeric - target + 1e-12)
    else:
        return False, 1.0

    return deficit <= 1e-12, min(1.0, deficit / max(abs(target), 1.0))


def _parse_clause(default_alias: str, text: str) -> tuple[str, str, Any] | None:
    match = _COMPARISON_RE.match(text)
    if not match:
        return None
    alias, operator, threshold = match.groups()
    return alias or default_alias, operator, _parse_threshold(threshold)


def evaluate_constraints(
    metrics: dict[str, Any],
    constraints: dict[str, Any],
    *,
    max_bonus: float = 60.0,
    exact_bonus: float = 20.0,
) -> TargetScoreResult:
    """Evaluate Analyzer constraints using AND across dict entries.

    Within one expression, `or` selects the nearest passing branch.
    `and` is also supported for explicit compound expressions.
    """
    if not constraints:
        return TargetScoreResult(
            active=False,
            exact_match=False,
            coverage=0.0,
            target_distance=1.0,
            target_bonus=0.0,
            passed_constraints=0,
            total_constraints=0,
            missing_metrics=[],
            clauses=[],
        )

    entry_distances: list[float] = []
    entry_passed: list[bool] = []
    entry_available: list[bool] = []
    clause_results: list[ClauseResult] = []
    missing: set[str] = set()

    for default_alias, raw_expression in constraints.items():
        # Planner constraints may be native JSON booleans/numbers rather than
        # textual comparison expressions.  Treat them as equality constraints
        # instead of misclassifying them as an unavailable metric.
        if isinstance(raw_expression, bool):
            expression = "= true" if raw_expression else "= false"
        elif isinstance(raw_expression, (int, float)) and not isinstance(raw_expression, bool):
            expression = f"= {raw_expression}"
        else:
            expression = str(raw_expression).strip()
        # OR groups, each of which can contain AND clauses.
        or_groups = re.split(r"\s+or\s+", expression, flags=re.IGNORECASE)
        group_results: list[tuple[bool, bool, float, list[ClauseResult]]] = []

        for group in or_groups:
            and_clauses = re.split(r"\s+and\s+", group, flags=re.IGNORECASE)
            local_results: list[ClauseResult] = []

            for clause_text in and_clauses:
                parsed = _parse_clause(str(default_alias), clause_text)
                if parsed is None:
                    alias = str(default_alias)
                    metric = ALIASES.get(alias, alias)
                    result = ClauseResult(
                        alias=alias,
                        metric=metric,
                        operator="?",
                        threshold=clause_text.strip(),
                        value=None,
                        source_metric=None,
                        available=False,
                        passed=False,
                        normalized_deficit=1.0,
                        expression=clause_text.strip(),
                    )
                    missing.add(metric)
                    local_results.append(result)
                    continue

                alias, operator, threshold = parsed
                value, source_metric, metric = resolve_value(metrics, alias)
                available = value is not None
                if not available:
                    passed, deficit = False, 1.0
                    missing.add(metric)
                else:
                    passed, deficit = _compare(value, operator, threshold)

                local_results.append(ClauseResult(
                    alias=alias,
                    metric=metric,
                    operator=operator,
                    threshold=threshold,
                    value=value,
                    source_metric=source_metric,
                    available=available,
                    passed=passed,
                    normalized_deficit=round(float(deficit), 6),
                    expression=clause_text.strip(),
                ))

            group_available = bool(local_results) and all(x.available for x in local_results)
            group_passed = group_available and all(x.passed for x in local_results)
            group_distance = (
                sum(x.normalized_deficit for x in local_results)
                / max(1, len(local_results))
            )
            group_results.append(
                (group_passed, group_available, group_distance, local_results)
            )

        # For OR, choose a passing branch first, otherwise the nearest branch.
        chosen = min(
            group_results,
            key=lambda x: (
                0 if x[0] else 1,
                0 if x[1] else 1,
                x[2],
            ),
        )
        passed, available, distance, chosen_clauses = chosen
        clause_results.extend(chosen_clauses)
        entry_passed.append(passed)
        entry_available.append(available)
        entry_distances.append(distance)

    total = len(entry_passed)
    available_count = sum(1 for x in entry_available if x)
    passed_count = sum(1 for x in entry_passed if x)
    coverage = available_count / max(1, total)
    distance = sum(entry_distances) / max(1, total)
    exact = total > 0 and coverage == 1.0 and passed_count == total

    # Scientific fail-closed rule: partial metric coverage must never steer
    # evolution as though the target were measured.  A candidate receives no
    # target reward until every required constraint is observable.
    proximity = max(0.0, 1.0 - distance)
    bonus = 0.0 if coverage < 1.0 else max_bonus * proximity
    if exact:
        bonus += exact_bonus

    return TargetScoreResult(
        active=True,
        exact_match=exact,
        coverage=round(coverage, 6),
        target_distance=round(distance, 6),
        target_bonus=round(bonus, 6),
        passed_constraints=passed_count,
        total_constraints=total,
        missing_metrics=sorted(missing),
        clauses=clause_results,
    )


def apply_target_score(
    score: float,
    metrics: dict[str, Any],
    constraints: dict[str, Any],
    *,
    max_bonus: float = 60.0,
    exact_bonus: float = 20.0,
) -> tuple[float, TargetScoreResult]:
    result = evaluate_constraints(
        metrics,
        constraints,
        max_bonus=max_bonus,
        exact_bonus=exact_bonus,
    )
    metrics["target_scoring_version"] = VERSION
    metrics["target_match"] = result.exact_match
    metrics["target_coverage"] = result.coverage
    metrics["target_distance"] = result.target_distance
    metrics["target_bonus"] = result.target_bonus
    metrics["target_passed_constraints"] = result.passed_constraints
    metrics["target_total_constraints"] = result.total_constraints
    metrics["target_missing_metrics"] = list(result.missing_metrics)
    metrics["target_constraint_details"] = [
        x.to_dict() for x in result.clauses
    ]
    return score + result.target_bonus, result


def _fallback_sources(details: list[dict[str, Any]]) -> list[str]:
    sources: set[str] = set()
    for detail in details:
        if not isinstance(detail, dict):
            continue
        source = detail.get("source_metric")
        metric = detail.get("metric")
        if source and metric and source != metric:
            sources.add(str(source))
    return sorted(sources)


def summarize_generation(results: list[tuple[float, Any, dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    missing_metric_counts: dict[str, int] = {}
    fallback_metric_counts: dict[str, int] = {}
    full_coverage_count = 0
    for score, rule, metrics in results:
        missing_metrics = [str(x) for x in metrics.get("target_missing_metrics", [])]
        details = [
            dict(x) for x in metrics.get("target_constraint_details", [])
            if isinstance(x, dict)
        ]
        fallback_sources = _fallback_sources(details)
        coverage = metrics.get("target_coverage")
        if coverage == 1.0:
            full_coverage_count += 1
        for name in missing_metrics:
            missing_metric_counts[name] = missing_metric_counts.get(name, 0) + 1
        for name in fallback_sources:
            fallback_metric_counts[name] = fallback_metric_counts.get(name, 0) + 1
        rows.append({
            "rule_id": getattr(rule, "rule_id", None),
            "score": round(float(score), 6),
            "target_match": bool(metrics.get("target_match", False)),
            "target_distance": metrics.get("target_distance"),
            "target_coverage": coverage,
            "target_bonus": metrics.get("target_bonus"),
            "missing_metrics": missing_metrics,
            "fallback_metrics": fallback_sources,
        })
    rows.sort(key=lambda x: (
        0 if x["target_match"] else 1,
        x["target_distance"] if x["target_distance"] is not None else 999.0,
        0 if x["target_coverage"] == 1.0 else 1,
        -x["score"],
    ))
    evaluated = len(rows)
    exact_matches = sum(1 for x in rows if x["target_match"])
    return {
        "version": VERSION,
        "evaluated": evaluated,
        "exact_matches": exact_matches,
        "full_coverage_count": full_coverage_count,
        "partial_coverage_count": evaluated - full_coverage_count,
        "missing_metric_counts": dict(sorted(missing_metric_counts.items())),
        "fallback_metric_counts": dict(sorted(fallback_metric_counts.items())),
        "all_candidates_fully_measured": evaluated > 0 and full_coverage_count == evaluated,
        "best_target_candidates": rows[:10],
    }


def finalize_search_outcome(
    generation_summaries: list[dict[str, Any]],
    *,
    constraints: dict[str, Any],
    search_mode: str | None = None,
    search_job_id: str | None = None,
    target_regime: str | None = None,
    runtime_id: str | None = None,
    dispatch_id: str | None = None,
    search_run_id: str | None = None,
    expected_generations: int | None = None,
) -> dict[str, Any]:
    """Build a conservative machine-readable Search target outcome.

    ``TARGET_NOT_FOUND`` is only legal when every evaluated candidate had
    complete target-metric coverage.  Any partial coverage makes the outcome
    inconclusive because a hidden target match cannot be ruled out.
    """
    summaries = [dict(x) for x in generation_summaries if isinstance(x, dict)]
    evaluated = sum(int(x.get("evaluated") or 0) for x in summaries)
    exact_matches = sum(int(x.get("exact_matches") or 0) for x in summaries)
    full_coverage = sum(int(x.get("full_coverage_count") or 0) for x in summaries)
    missing_counts: dict[str, int] = {}
    fallback_counts: dict[str, int] = {}
    candidates: list[dict[str, Any]] = []
    for summary in summaries:
        for name, count in (summary.get("missing_metric_counts") or {}).items():
            missing_counts[str(name)] = missing_counts.get(str(name), 0) + int(count or 0)
        for name, count in (summary.get("fallback_metric_counts") or {}).items():
            fallback_counts[str(name)] = fallback_counts.get(str(name), 0) + int(count or 0)
        candidates.extend(
            dict(row) for row in summary.get("best_target_candidates", [])
            if isinstance(row, dict)
        )
    candidates.sort(key=lambda x: (
        0 if x.get("target_match") else 1,
        x.get("target_distance") if x.get("target_distance") is not None else 999.0,
        0 if x.get("target_coverage") == 1.0 else 1,
        -float(x.get("score") or 0.0),
    ))
    best = candidates[0] if candidates else None

    if exact_matches > 0:
        scientific_status = "TARGET_FOUND"
        reason = "ONE_OR_MORE_EXACT_SEARCH_TARGET_MATCHES"
    elif evaluated <= 0:
        scientific_status = "TARGET_INCONCLUSIVE"
        reason = "NO_VALID_CANDIDATES_EVALUATED"
    elif expected_generations is not None and len(summaries) != int(expected_generations):
        scientific_status = "TARGET_INCONCLUSIVE"
        reason = "INCOMPLETE_GENERATION_COVERAGE_FOR_FINAL_OUTCOME"
    elif full_coverage != evaluated:
        scientific_status = "TARGET_INCONCLUSIVE"
        reason = "PARTIAL_TARGET_METRIC_COVERAGE"
    else:
        scientific_status = "TARGET_NOT_FOUND"
        reason = "FULLY_MEASURED_BUDGET_EXHAUSTED_WITHOUT_EXACT_MATCH"

    return {
        "schema": "archon_search_target_outcome_v1",
        "target_scoring_version": VERSION,
        "scientific_status": scientific_status,
        "reason": reason,
        "search_mode": search_mode,
        "search_job_id": search_job_id,
        "target_regime": target_regime,
        "runtime_id": runtime_id,
        "dispatch_id": dispatch_id,
        "search_run_id": search_run_id,
        "constraints": dict(constraints or {}),
        "generations_completed": len(summaries),
        "expected_generations": expected_generations,
        "evaluated_candidate_slots": evaluated,
        "exact_matches": exact_matches,
        "full_coverage_candidate_slots": full_coverage,
        "partial_coverage_candidate_slots": max(0, evaluated - full_coverage),
        "missing_metric_counts": dict(sorted(missing_counts.items())),
        "fallback_metric_counts": dict(sorted(fallback_counts.items())),
        "best_target_candidate": best,
        "requires_observer_validation": bool(exact_matches > 0 and fallback_counts),
        "scientific_policy": {
            "missing_metrics_never_count_as_failure": True,
            "target_not_found_requires_full_metric_coverage": True,
            "fallback_metric_hits_require_observer_validation": True,
        },
    }
