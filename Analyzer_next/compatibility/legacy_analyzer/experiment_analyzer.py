#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARCHON Experiment Analyzer v1.3 — Stage 1C Claim Builder.

Reads experimental provenance from Telemetry SQLite and normalized Observer
profiles from observer_profiles_v31.json. It compares baseline and treatment
arms without changing legacy rule-level Analyzer behaviour.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent

NUMERIC_METRICS: tuple[str, ...] = (
    "life_score",
    "life_confidence",
    "longest_age",
    "peak_objects",
    "peak_largest",
    "final_mass",
    "stability_index",
    "family_count",
    "deepest_generation",
    "oldest_lineage_age",
    "demo_survival_ratio",
    "evo_stress",
    "evo_adapt",
    "evo_pressure",
    "evo_risk",
    "civilization_score",
    "knowledge_score",
    "feedback_score",
    "emergence_score",
    "emergence_stability",
    "validation_quality",
    "validation_repeatability",
    "validation_noise_sensitivity",
    "layer_stack_score",
)

CATEGORICAL_METRICS: tuple[str, ...] = (
    "life_state",
    "structural_state",
    "ecology_state",
    "analyzer_category",
    "scientific_confidence",
    "emergence_confidence",
    "validation_grade",
)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def mean_or_none(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def sample_sd_or_none(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def summarize_numeric(values: Iterable[Any]) -> dict[str, Any]:
    clean = [x for value in values if (x := safe_float(value)) is not None]
    return {
        "n": len(clean),
        "mean": mean_or_none(clean),
        "median": median_or_none(clean),
        "sd": sample_sd_or_none(clean),
        "min": min(clean) if clean else None,
        "max": max(clean) if clean else None,
    }


def pooled_standardized_difference(
    baseline: list[float],
    treatment: list[float],
) -> float | None:
    """Hedges-like standardized difference, conservative for tiny samples."""
    if not baseline or not treatment:
        return None
    mean_delta = statistics.fmean(treatment) - statistics.fmean(baseline)
    if len(baseline) < 2 or len(treatment) < 2:
        return None
    var_b = statistics.variance(baseline)
    var_t = statistics.variance(treatment)
    denom_df = len(baseline) + len(treatment) - 2
    if denom_df <= 0:
        return None
    pooled_var = (
        (len(baseline) - 1) * var_b
        + (len(treatment) - 1) * var_t
    ) / denom_df
    if pooled_var <= 0:
        return 0.0 if mean_delta == 0 else None
    d = mean_delta / math.sqrt(pooled_var)
    correction = 1.0 - 3.0 / max(1.0, 4.0 * denom_df - 1.0)
    return d * correction


def categorical_counts(values: Iterable[Any]) -> dict[str, int]:
    counter = Counter(
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    )
    return dict(sorted(counter.items()))


def normalize_rule_id(value: Any) -> str | None:
    """Return a canonical five-digit rule id without accepting arbitrary text."""
    if value is None:
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return f"{number:05d}" if number >= 0 else None


def load_profile_index(
    profiles_path: Path,
) -> dict[str, dict[str, tuple[dict[str, Any], str]]]:
    """Build explicit profile indexes and preserve the match method."""
    payload = read_json(profiles_path, {})
    records = payload.get("profile_records", []) if isinstance(payload, dict) else []
    indexes: dict[str, dict[str, tuple[dict[str, Any], str]]] = {
        "observer_state_run_id": {},
        "experiment_id_legacy": {},
    }
    for record in records:
        if not isinstance(record, dict):
            continue
        run_id = record.get("observer_state_run_id")
        if run_id:
            indexes["observer_state_run_id"][str(run_id)] = (
                record,
                "observer_state_run_id",
            )
        legacy_id = record.get("experiment_id")
        if legacy_id:
            indexes["experiment_id_legacy"][str(legacy_id)] = (
                record,
                "experiment_id_legacy",
            )
    return indexes


def match_profile(
    run_id: Any,
    profile_index: dict[str, dict[str, tuple[dict[str, Any], str]]],
) -> tuple[dict[str, Any] | None, str]:
    key = str(run_id)
    direct = profile_index["observer_state_run_id"].get(key)
    if direct is not None:
        return direct
    legacy = profile_index["experiment_id_legacy"].get(key)
    if legacy is not None:
        return legacy
    return None, "unmatched"


def connect_ro(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{database.resolve()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    return connection


def load_experiment_rows(
    connection: sqlite3.Connection,
    experiment_id: str | None,
) -> list[dict[str, Any]]:
    where = ""
    params: tuple[Any, ...] = ()
    if experiment_id:
        where = "WHERE er.experiment_id = ?"
        params = (experiment_id,)

    rows = connection.execute(
        f"""
        SELECT
            er.experiment_run_id,
            er.experiment_id,
            e.title AS experiment_title,
            e.research_question,
            e.status AS experiment_status,
            e.metadata_json AS experiment_metadata_json,
            er.run_id,
            er.rule_id,
            er.role,
            er.replicate_index,
            er.condition_id,
            c.name AS condition_name,
            c.field_width,
            c.field_height,
            c.topology,
            c.boundary_mode,
            c.initial_state_mode,
            r.status AS run_status,
            r.final_tick,
            r.started_at_utc,
            r.finished_at_utc,
            r.metadata_json AS run_metadata_json
        FROM experiment_runs er
        JOIN experiments e
            ON e.experiment_id = er.experiment_id
        JOIN experimental_conditions c
            ON c.condition_id = er.condition_id
        JOIN runs r
            ON r.run_id = er.run_id
        {where}
        ORDER BY er.experiment_id, er.created_at_utc, er.replicate_index
        """,
        params,
    ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        try:
            run_metadata = json.loads(item.pop("run_metadata_json") or "{}")
        except Exception:
            run_metadata = {}
        try:
            experiment_metadata = json.loads(
                item.pop("experiment_metadata_json") or "{}"
            )
        except Exception:
            experiment_metadata = {}
        context = run_metadata.get("experimental_context")
        item["metadata"] = run_metadata
        item["experiment_metadata"] = (
            experiment_metadata if isinstance(experiment_metadata, dict) else {}
        )
        item["experimental_context"] = context if isinstance(context, dict) else {}
        item["experiment_seed"] = item["experimental_context"].get(
            "experiment_seed"
        )
        result.append(item)
    return result


def arm_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["condition_id"]), str(row["role"])


def confidence_rank(value: str) -> int:
    return {
        "NONE": 0,
        "LOW": 1,
        "PRELIMINARY": 1,
        "MEDIUM": 2,
        "HIGH": 3,
    }.get(str(value).upper(), 0)


def outcome_confidence(
    design_confidence: str,
    *,
    baseline_n: int,
    treatment_n: int,
    complete: bool = True,
) -> str:
    """Conservative confidence for one descriptive experiment outcome."""
    rank = confidence_rank(design_confidence)
    if not complete or baseline_n < 1 or treatment_n < 1:
        return "NONE"
    if treatment_n < 3:
        rank = min(rank, 1)
    elif baseline_n < 2:
        rank = min(rank, 2)
    return {0: "NONE", 1: "LOW", 2: "MEDIUM", 3: "HIGH"}.get(rank, "NONE")


def dominant_category(counts: dict[str, int]) -> tuple[str | None, int, int]:
    total = sum(int(value) for value in counts.values())
    if not counts or total <= 0:
        return None, 0, total
    category, count = max(
        counts.items(),
        key=lambda item: (int(item[1]), str(item[0])),
    )
    return str(category), int(count), total


def coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    if abs(mean) < 1e-12:
        return None
    return abs(statistics.stdev(values) / mean)


def classify_numeric_direction(
    baseline_mean: float | None,
    treatment_mean: float | None,
) -> tuple[str, float | None]:
    if baseline_mean is None or treatment_mean is None:
        return "unavailable", None
    delta = treatment_mean - baseline_mean
    scale = max(abs(baseline_mean), abs(treatment_mean), 1e-9)
    relative = delta / scale
    if abs(relative) < 0.05:
        return "approximately_stable", relative
    return ("increased" if delta > 0 else "decreased"), relative


def classify_variability(cv: float | None) -> str:
    if cv is None:
        return "unavailable"
    if cv < 0.10:
        return "low"
    if cv < 0.25:
        return "moderate"
    if cv < 0.50:
        return "high"
    return "very_high"


def build_comparison_outcomes(
    *,
    experiment_id: str,
    comparison_index: int,
    comparison: dict[str, Any],
    design_confidence: str,
    comparable_horizon: bool,
    all_completed: bool,
) -> list[dict[str, Any]]:
    """Translate one arm comparison into descriptive, non-causal outcomes."""
    outcomes: list[dict[str, Any]] = []
    prefix = f"OUT-{experiment_id}-{comparison_index:02d}"

    for metric_index, metric in enumerate(CATEGORICAL_METRICS, 1):
        item = comparison["categorical_comparison"].get(metric, {})
        baseline = dict(item.get("baseline") or {})
        treatment = dict(item.get("treatment") or {})
        baseline_category, baseline_count, baseline_total = dominant_category(baseline)
        treatment_category, treatment_count, treatment_total = dominant_category(treatment)
        preserved_count = (
            int(treatment.get(baseline_category, 0))
            if baseline_category is not None
            else 0
        )
        preservation_ratio = (
            preserved_count / treatment_total if treatment_total else None
        )

        if baseline_category is None or treatment_total == 0:
            status = "unavailable"
        elif preservation_ratio == 1.0:
            status = "preserved"
        elif preservation_ratio and preservation_ratio > 0.0:
            status = "mixed"
        else:
            status = "transitioned"

        outcomes.append({
            "outcome_id": f"{prefix}-CAT-{metric_index:02d}",
            "experiment_id": experiment_id,
            "comparison_index": comparison_index,
            "baseline_arm": comparison["baseline_arm"],
            "treatment_arm": comparison["treatment_arm"],
            "outcome_type": "categorical_state",
            "metric": metric,
            "status": status,
            "baseline_dominant": baseline_category,
            "baseline_dominant_count": baseline_count,
            "baseline_n": baseline_total,
            "treatment_dominant": treatment_category,
            "treatment_dominant_count": treatment_count,
            "treatment_n": treatment_total,
            "preserved_count": preserved_count,
            "preservation_ratio": preservation_ratio,
            "baseline_distribution": baseline,
            "treatment_distribution": treatment,
            "confidence": outcome_confidence(
                design_confidence,
                baseline_n=baseline_total,
                treatment_n=treatment_total,
                complete=all_completed and comparable_horizon,
            ),
            "interpretation_policy": "descriptive_categorical_v1",
        })

    for metric_index, metric in enumerate(NUMERIC_METRICS, 1):
        result = comparison["numeric_differences"].get(metric, {})
        baseline_mean = safe_float(result.get("baseline_mean"))
        treatment_mean = safe_float(result.get("treatment_mean"))
        direction, relative_difference = classify_numeric_direction(
            baseline_mean,
            treatment_mean,
        )
        treatment_values = []
        for raw_value in result.get("treatment_values", []):
            clean_value = safe_float(raw_value)
            if clean_value is not None:
                treatment_values.append(clean_value)
        cv = coefficient_of_variation(treatment_values)
        baseline_n = int(result.get("baseline_n") or 0)
        treatment_n = int(result.get("treatment_n") or 0)
        limitations: list[str] = []
        if baseline_n < 2:
            limitations.append("baseline_variance_unavailable")
        if treatment_n < 2:
            limitations.append("treatment_variance_unavailable")
        if result.get("standardized_difference") is None:
            limitations.append("standardized_effect_unavailable")

        outcomes.append({
            "outcome_id": f"{prefix}-NUM-{metric_index:02d}",
            "experiment_id": experiment_id,
            "comparison_index": comparison_index,
            "baseline_arm": comparison["baseline_arm"],
            "treatment_arm": comparison["treatment_arm"],
            "outcome_type": "numeric_change",
            "metric": metric,
            "status": direction,
            "baseline_mean": baseline_mean,
            "treatment_mean": treatment_mean,
            "absolute_difference": result.get("absolute_difference"),
            "relative_difference": relative_difference,
            "standardized_difference": result.get("standardized_difference"),
            "baseline_n": baseline_n,
            "treatment_n": treatment_n,
            "treatment_cv": cv,
            "variability": classify_variability(cv),
            "confidence": outcome_confidence(
                design_confidence,
                baseline_n=baseline_n,
                treatment_n=treatment_n,
                complete=all_completed and comparable_horizon,
            ),
            "limitations": sorted(set(limitations)),
            "interpretation_policy": "descriptive_numeric_v1",
        })

    return outcomes


CONFIDENCE_RANK = {
    "NONE": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "VERY_HIGH": 4,
}

QUALITATIVE_CORE_METRICS: tuple[str, ...] = (
    "analyzer_category",
    "scientific_confidence",
    "emergence_confidence",
    "validation_grade",
    "life_state",
    "ecology_state",
)

QUANTITATIVE_SENSITIVITY_METRICS: tuple[str, ...] = (
    "peak_objects",
    "peak_largest",
    "final_mass",
    "stability_index",
    "family_count",
    "deepest_generation",
)


def weakest_confidence(values: Iterable[str], default: str = "NONE") -> str:
    clean = [
        str(value).upper()
        for value in values
        if str(value).upper() in CONFIDENCE_RANK
    ]
    if not clean:
        return default
    return min(clean, key=lambda value: CONFIDENCE_RANK[value])


def make_claim_id(experiment_id: str, index: int) -> str:
    return f"ECL-{experiment_id}-{index:03d}"


def build_experiment_claims(
    *,
    experiment_id: str,
    rule_ids: list[str],
    outcomes: list[dict[str, Any]],
    design_confidence: str,
    common_horizon: int | None,
    experiment_limitations: list[str],
    arms: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build scoped, descriptive claims from formal outcomes only.

    Stage 1C deliberately avoids causal language, principle promotion, and
    direct reads from raw profile metrics. Every claim must be traceable to
    one or more Stage 1B outcome ids.
    """
    claims: list[dict[str, Any]] = []
    by_metric = {item.get("metric"): item for item in outcomes}
    scope_rule_text = (
        f"Rule {rule_ids[0]}" if len(rule_ids) == 1
        else f"Rules {', '.join(rule_ids)}" if rule_ids
        else "The tested rule set"
    )

    geometries = []
    initial_states = []
    for arm in arms.values():
        geometry = dict(arm.get("geometry") or {})
        if geometry and geometry not in geometries:
            geometries.append(geometry)
        mode = geometry.get("initial_state_mode")
        if mode and mode not in initial_states:
            initial_states.append(mode)

    base_scope = {
        "rule_ids": list(rule_ids),
        "horizon": common_horizon,
        "geometries": geometries,
        "initial_state_modes": initial_states,
    }

    core = [
        by_metric[metric]
        for metric in QUALITATIVE_CORE_METRICS
        if metric in by_metric
        and by_metric[metric].get("outcome_type") == "categorical_state"
        and by_metric[metric].get("status") != "unavailable"
    ]
    preserved = [item for item in core if item.get("status") == "preserved"]
    changed = [item for item in core if item.get("status") in {"mixed", "transitioned"}]
    if core:
        if preserved and not changed:
            claim_status = "supported"
            statement = (
                f"{scope_rule_text} preserved all measured core qualitative "
                f"states across the tested experimental arms"
            )
        elif preserved and changed:
            claim_status = "mixed"
            statement = (
                f"{scope_rule_text} preserved some core qualitative states "
                f"while others changed across the tested experimental arms"
            )
        else:
            claim_status = "not_supported"
            statement = (
                f"{scope_rule_text} did not preserve the measured core "
                f"qualitative states across the tested experimental arms"
            )
        if common_horizon is not None:
            statement += f" through tick {common_horizon}."
        else:
            statement += "."
        qualitative_limitations = list(experiment_limitations)
        missing_core = sorted(set(QUALITATIVE_CORE_METRICS) - {str(item['metric']) for item in core})
        if missing_core:
            qualitative_limitations.append("core_qualitative_metrics_incomplete")
        claims.append({
            "claim_id": make_claim_id(experiment_id, len(claims) + 1),
            "experiment_id": experiment_id,
            "claim_type": "qualitative_state_preservation",
            "statement": statement,
            "status": claim_status,
            "confidence": weakest_confidence(
                [design_confidence, *[str(item.get("confidence", "NONE")) for item in core]],
                default="NONE",
            ),
            "scope": dict(base_scope),
            "supported_by_outcome_ids": [str(item["outcome_id"]) for item in core],
            "supporting_metrics": [str(item["metric"]) for item in preserved],
            "contradicting_metrics": [str(item["metric"]) for item in changed],
            "limitations": sorted(set(qualitative_limitations)),
            "interpretation_policy": "scoped_descriptive_claim_v1",
            "automatic_promotion": False,
            "causal_interpretation": False,
        })

    age_outcome = by_metric.get("longest_age")
    if (
        age_outcome
        and age_outcome.get("outcome_type") == "numeric_change"
        and age_outcome.get("status") != "unavailable"
        and common_horizon is not None
    ):
        preserved_horizon = age_outcome.get("status") == "approximately_stable"
        claims.append({
            "claim_id": make_claim_id(experiment_id, len(claims) + 1),
            "experiment_id": experiment_id,
            "claim_type": "observed_horizon_preservation",
            "statement": (
                f"{scope_rule_text} {'reached the same observed horizon in the tested arms' if preserved_horizon else 'showed a changed observed lifetime across the tested arms'} "
                f"at tick {common_horizon}."
            ),
            "status": "supported" if preserved_horizon else "not_supported",
            "confidence": weakest_confidence([
                design_confidence,
                str(age_outcome.get("confidence", "NONE")),
            ]),
            "scope": dict(base_scope),
            "supported_by_outcome_ids": [str(age_outcome["outcome_id"])],
            "supporting_metrics": ["longest_age"] if preserved_horizon else [],
            "contradicting_metrics": [] if preserved_horizon else ["longest_age"],
            "limitations": sorted(set(experiment_limitations)),
            "interpretation_policy": "scoped_descriptive_claim_v1",
            "automatic_promotion": False,
            "causal_interpretation": False,
        })

    sensitivity = []
    stable_numeric = []
    for metric in QUANTITATIVE_SENSITIVITY_METRICS:
        item = by_metric.get(metric)
        if not item or item.get("outcome_type") != "numeric_change":
            continue
        if item.get("status") in {"increased", "decreased"}:
            sensitivity.append(item)
        elif (
            item.get("status") == "approximately_stable"
            and item.get("variability") in {"high", "very_high"}
        ):
            sensitivity.append(item)
        elif item.get("status") == "approximately_stable":
            stable_numeric.append(item)

    if sensitivity or stable_numeric:
        if sensitivity:
            status = "supported"
            sensitive_names = ", ".join(str(item["metric"]) for item in sensitivity)
            statement = (
                f"{scope_rule_text} showed quantitative sensitivity across the "
                f"tested arms in: {sensitive_names}."
            )
            evidence_items = sensitivity
        else:
            status = "not_supported"
            statement = (
                f"{scope_rule_text} showed no clear quantitative sensitivity in "
                f"the monitored morphology and lineage metrics across the tested arms."
            )
            evidence_items = stable_numeric
        claim_limitations = list(experiment_limitations)
        claim_limitations.extend(
            limitation
            for item in evidence_items
            for limitation in item.get("limitations", [])
        )
        claims.append({
            "claim_id": make_claim_id(experiment_id, len(claims) + 1),
            "experiment_id": experiment_id,
            "claim_type": "quantitative_sensitivity",
            "statement": statement,
            "status": status,
            "confidence": weakest_confidence(
                [design_confidence, *[str(item.get("confidence", "NONE")) for item in evidence_items]],
                default="NONE",
            ),
            "scope": dict(base_scope),
            "supported_by_outcome_ids": [str(item["outcome_id"]) for item in evidence_items],
            "supporting_metrics": [str(item["metric"]) for item in sensitivity],
            "contradicting_metrics": [],
            "limitations": sorted(set(claim_limitations)),
            "interpretation_policy": "scoped_descriptive_claim_v1",
            "automatic_promotion": False,
            "causal_interpretation": False,
        })

    return claims


def analyze_experiment(
    experiment_id: str,
    rows: list[dict[str, Any]],
    profile_index: dict[str, dict[str, tuple[dict[str, Any], str]]],
) -> dict[str, Any]:
    arms: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    unmatched: list[str] = []
    profile_match_methods: dict[str, str] = {}

    for row in rows:
        profile, match_method = match_profile(row["run_id"], profile_index)
        enriched = dict(row)
        enriched["profile"] = profile
        enriched["profile_match_method"] = match_method
        profile_match_methods[str(row["run_id"])] = match_method
        if profile is None:
            unmatched.append(str(row["run_id"]))
        arms[arm_key(row)].append(enriched)

    baseline_keys = [
        key for key in arms
        if key[1] == "baseline"
    ]
    treatment_keys = [
        key for key in arms
        if key[1] == "treatment"
    ]

    all_ticks = [
        int(row["final_tick"])
        for row in rows
        if row["final_tick"] is not None
    ]
    all_statuses = [str(row["run_status"]) for row in rows]
    comparable_horizon = bool(all_ticks) and len(set(all_ticks)) == 1
    all_completed = bool(rows) and all(
        status == "completed" for status in all_statuses
    )

    arm_payloads: dict[str, Any] = {}
    for key, records in sorted(arms.items()):
        condition_id, role = key
        profiles = [
            record["profile"]
            for record in records
            if isinstance(record.get("profile"), dict)
        ]
        numeric = {
            metric: summarize_numeric(
                profile.get(metric) for profile in profiles
            )
            for metric in NUMERIC_METRICS
        }
        categorical = {
            metric: categorical_counts(
                profile.get(metric) for profile in profiles
            )
            for metric in CATEGORICAL_METRICS
        }
        seeds = [
            record.get("experiment_seed")
            for record in records
            if record.get("experiment_seed") is not None
        ]
        arm_payloads[f"{condition_id}:{role}"] = {
            "condition_id": condition_id,
            "condition_name": records[0]["condition_name"],
            "role": role,
            "geometry": {
                "field_width": records[0]["field_width"],
                "field_height": records[0]["field_height"],
                "topology": records[0]["topology"],
                "boundary_mode": records[0]["boundary_mode"],
                "initial_state_mode": records[0]["initial_state_mode"],
            },
            "run_count": len(records),
            "profile_count": len(profiles),
            "completed_count": sum(
                record["run_status"] == "completed"
                for record in records
            ),
            "final_ticks": sorted({
                record["final_tick"]
                for record in records
                if record["final_tick"] is not None
            }),
            "replicate_indices": [
                int(record["replicate_index"])
                for record in records
            ],
            "seeds": seeds,
            "unique_seed_count": len(set(seeds)),
            "numeric_metrics": numeric,
            "categorical_metrics": categorical,
            "runs": [
                {
                    "run_id": record["run_id"],
                    "replicate_index": record["replicate_index"],
                    "status": record["run_status"],
                    "final_tick": record["final_tick"],
                    "experiment_seed": record.get("experiment_seed"),
                    "profile_found": record["profile"] is not None,
                    "profile_match_method": record["profile_match_method"],
                }
                for record in records
            ],
        }

    comparisons: list[dict[str, Any]] = []
    if len(baseline_keys) == 1:
        baseline_records = arms[baseline_keys[0]]
        baseline_profiles = [
            record["profile"]
            for record in baseline_records
            if isinstance(record.get("profile"), dict)
        ]
        baseline_name = f"{baseline_keys[0][0]}:{baseline_keys[0][1]}"

        for treatment_key in treatment_keys:
            treatment_records = arms[treatment_key]
            treatment_profiles = [
                record["profile"]
                for record in treatment_records
                if isinstance(record.get("profile"), dict)
            ]
            numeric_differences: dict[str, Any] = {}
            for metric in NUMERIC_METRICS:
                baseline_values = [
                    value for profile in baseline_profiles
                    if (value := safe_float(profile.get(metric))) is not None
                ]
                treatment_values = [
                    value for profile in treatment_profiles
                    if (value := safe_float(profile.get(metric))) is not None
                ]
                baseline_mean = mean_or_none(baseline_values)
                treatment_mean = mean_or_none(treatment_values)
                numeric_differences[metric] = {
                    "baseline_mean": baseline_mean,
                    "treatment_mean": treatment_mean,
                    "absolute_difference": (
                        treatment_mean - baseline_mean
                        if baseline_mean is not None
                        and treatment_mean is not None
                        else None
                    ),
                    "standardized_difference": (
                        pooled_standardized_difference(
                            baseline_values,
                            treatment_values,
                        )
                    ),
                    "baseline_n": len(baseline_values),
                    "treatment_n": len(treatment_values),
                    "baseline_values": baseline_values,
                    "treatment_values": treatment_values,
                }

            comparisons.append({
                "baseline_arm": baseline_name,
                "treatment_arm": (
                    f"{treatment_key[0]}:{treatment_key[1]}"
                ),
                "numeric_differences": numeric_differences,
                "categorical_comparison": {
                    metric: {
                        "baseline": categorical_counts(
                            profile.get(metric)
                            for profile in baseline_profiles
                        ),
                        "treatment": categorical_counts(
                            profile.get(metric)
                            for profile in treatment_profiles
                        ),
                    }
                    for metric in CATEGORICAL_METRICS
                },
            })

    treatment_replicates = sum(len(arms[key]) for key in treatment_keys)
    if not rows:
        confidence = "NONE"
    elif not all_completed or not comparable_horizon or unmatched:
        confidence = "LOW"
    elif treatment_replicates >= 20 and len(baseline_keys) == 1:
        confidence = "HIGH"
    elif treatment_replicates >= 5 and len(baseline_keys) == 1:
        confidence = "MEDIUM"
    else:
        confidence = "PRELIMINARY"

    warnings: list[str] = []
    limitations: list[str] = []
    if len(baseline_keys) != 1:
        warnings.append(
            "exactly_one_baseline_arm_required_for_direct_comparison"
        )
    if not comparable_horizon:
        warnings.append("unequal_or_missing_final_tick")
    if not all_completed:
        warnings.append("non_completed_runs_present")
    if unmatched:
        warnings.append("profile_records_missing_for_some_runs")
    if treatment_replicates < 5:
        warnings.append("small_treatment_sample")

    legacy_matches = sorted(
        run_id for run_id, method in profile_match_methods.items()
        if method == "experiment_id_legacy"
    )
    if legacy_matches:
        warnings.append("legacy_profile_match_used")
        limitations.append("legacy_profile_identity_fallback")

    rule_ids = sorted({
        normalized
        for row in rows
        if (normalized := normalize_rule_id(row.get("rule_id"))) is not None
    })
    single_rule_design = len(rule_ids) == 1
    if not single_rule_design:
        limitations.append(
            "multi_rule_design" if rule_ids else "rule_identity_missing"
        )

    baseline_run_count = sum(len(arms[key]) for key in baseline_keys)
    if baseline_run_count == 1:
        limitations.extend([
            "single_baseline_observation",
            "baseline_variance_unavailable",
            "standardized_effect_unavailable",
        ])
    elif baseline_run_count == 0:
        limitations.append("baseline_observation_missing")

    if comparable_horizon and len(set(all_ticks)) == 1:
        common_horizon = all_ticks[0]
        if common_horizon < 10_000:
            limitations.append("short_horizon")
    else:
        common_horizon = None

    if single_rule_design:
        limitations.append("single_rule_scope")

    experiment_metadata = rows[0].get("experiment_metadata", {}) if rows else {}
    experiment_type = (
        experiment_metadata.get("experiment_type")
        or experiment_metadata.get("type")
    )
    if not experiment_type:
        limitations.append("experiment_type_not_declared")

    outcomes: list[dict[str, Any]] = []
    for comparison_index, comparison in enumerate(comparisons, 1):
        outcomes.extend(build_comparison_outcomes(
            experiment_id=experiment_id,
            comparison_index=comparison_index,
            comparison=comparison,
            design_confidence=confidence,
            comparable_horizon=comparable_horizon,
            all_completed=all_completed,
        ))
    claims = build_experiment_claims(
        experiment_id=experiment_id,
        rule_ids=rule_ids,
        outcomes=outcomes,
        design_confidence=confidence,
        common_horizon=common_horizon,
        experiment_limitations=sorted(set(limitations)),
        arms=arm_payloads,
    )
    claim_summary = {
        "total": len(claims),
        "supported": sum(item["status"] == "supported" for item in claims),
        "mixed": sum(item["status"] == "mixed" for item in claims),
        "not_supported": sum(
            item["status"] == "not_supported" for item in claims
        ),
        "by_type": dict(Counter(item["claim_type"] for item in claims)),
    }

    outcome_summary = {
        "total": len(outcomes),
        "categorical": sum(
            item["outcome_type"] == "categorical_state"
            for item in outcomes
        ),
        "numeric": sum(
            item["outcome_type"] == "numeric_change"
            for item in outcomes
        ),
        "preserved_categorical": sum(
            item["outcome_type"] == "categorical_state"
            and item["status"] == "preserved"
            for item in outcomes
        ),
        "mixed_categorical": sum(
            item["outcome_type"] == "categorical_state"
            and item["status"] == "mixed"
            for item in outcomes
        ),
        "transitioned_categorical": sum(
            item["outcome_type"] == "categorical_state"
            and item["status"] == "transitioned"
            for item in outcomes
        ),
        "numeric_increased": sum(
            item["outcome_type"] == "numeric_change"
            and item["status"] == "increased"
            for item in outcomes
        ),
        "numeric_decreased": sum(
            item["outcome_type"] == "numeric_change"
            and item["status"] == "decreased"
            for item in outcomes
        ),
        "numeric_approximately_stable": sum(
            item["outcome_type"] == "numeric_change"
            and item["status"] == "approximately_stable"
            for item in outcomes
        ),
    }

    return {
        "experiment_id": experiment_id,
        "title": rows[0]["experiment_title"] if rows else None,
        "research_question": rows[0]["research_question"] if rows else None,
        "experiment_status": rows[0]["experiment_status"] if rows else None,
        "experiment_metadata": experiment_metadata,
        "experiment_type": experiment_type,
        "rule_ids": rule_ids,
        "single_rule_design": single_rule_design,
        "common_horizon": common_horizon,
        "run_ids": [str(row["run_id"]) for row in rows],
        "condition_ids": sorted({str(row["condition_id"]) for row in rows}),
        "run_count": len(rows),
        "arm_count": len(arms),
        "baseline_arm_count": len(baseline_keys),
        "treatment_arm_count": len(treatment_keys),
        "all_completed": all_completed,
        "comparable_horizon": comparable_horizon,
        "observed_horizons": sorted(set(all_ticks)),
        "unmatched_profile_run_ids": unmatched,
        "legacy_profile_match_run_ids": legacy_matches,
        "profile_match_methods": profile_match_methods,
        "design_confidence": confidence,
        "analysis_confidence": confidence,
        "limitations": sorted(set(limitations)),
        "warnings": warnings,
        "outcome_summary": outcome_summary,
        "outcomes": outcomes,
        "claim_summary": claim_summary,
        "claims": claims,
        "arms": arm_payloads,
        "comparisons": comparisons,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# ARCHON Experiment Analysis v1",
        "",
        "Controlled comparison of experimental arms using SQLite provenance "
        "and Observer Profile v31 records.",
        "",
    ]

    for experiment in payload["experiments"]:
        lines.extend([
            f"## {experiment['experiment_id']}: "
            f"{experiment.get('title') or 'Untitled experiment'}",
            "",
            f"- Runs: **{experiment['run_count']}**",
            f"- Arms: **{experiment['arm_count']}**",
            f"- Design confidence: **{experiment['design_confidence']}**",
            f"- Rules: {experiment['rule_ids'] or '-'}",
            f"- Single-rule design: **{experiment['single_rule_design']}**",
            f"- Experiment type: {experiment.get('experiment_type') or 'not declared'}",
            f"- Comparable horizon: **{experiment['comparable_horizon']}**",
            f"- Horizons: {experiment['observed_horizons']}",
            f"- Profile matching: {experiment['profile_match_methods']}",
            f"- Limitations: {', '.join(experiment['limitations']) if experiment['limitations'] else 'none'}",
            f"- Warnings: {', '.join(experiment['warnings']) if experiment['warnings'] else 'none'}",
            "",
            "### Arms",
            "",
            "| Arm | Runs | Profiles | Completed | Initial state | Seeds |",
            "| --- | ---: | ---: | ---: | --- | --- |",
        ])

        for arm_name, arm in experiment["arms"].items():
            seeds = ", ".join(str(x) for x in arm["seeds"]) or "-"
            lines.append(
                f"| {arm_name} | {arm['run_count']} | "
                f"{arm['profile_count']} | {arm['completed_count']} | "
                f"{arm['geometry']['initial_state_mode']} | {seeds} |"
            )

        lines.extend([
            "",
            "### Formal Outcomes",
            "",
            f"- Total outcomes: **{experiment['outcome_summary']['total']}**",
            f"- Preserved categorical states: **{experiment['outcome_summary']['preserved_categorical']}**",
            f"- Mixed categorical states: **{experiment['outcome_summary']['mixed_categorical']}**",
            f"- Transitioned categorical states: **{experiment['outcome_summary']['transitioned_categorical']}**",
            "",
            "| Type | Metric | Status | Confidence | Detail |",
            "| --- | --- | --- | --- | --- |",
        ])
        for outcome in experiment["outcomes"]:
            if outcome["outcome_type"] == "categorical_state":
                detail = (
                    f"{outcome.get('preserved_count', 0)}/"
                    f"{outcome.get('treatment_n', 0)} preserved"
                )
            else:
                relative = outcome.get("relative_difference")
                detail = (
                    f"relative={relative:.3f}; variability={outcome.get('variability')}"
                    if isinstance(relative, (int, float))
                    else f"variability={outcome.get('variability')}"
                )
            lines.append(
                f"| {outcome['outcome_type']} | {outcome['metric']} | "
                f"{outcome['status']} | {outcome['confidence']} | {detail} |"
            )

        lines.extend([
            "",
            "### Scoped Experiment Claims",
            "",
            f"- Total claims: **{experiment['claim_summary']['total']}**",
            f"- Supported: **{experiment['claim_summary']['supported']}**",
            f"- Mixed: **{experiment['claim_summary']['mixed']}**",
            f"- Not supported: **{experiment['claim_summary']['not_supported']}**",
            "",
        ])
        for claim in experiment["claims"]:
            lines.extend([
                f"#### {claim['claim_id']}: {claim['claim_type']}",
                "",
                claim["statement"],
                "",
                f"- Status: **{claim['status']}**",
                f"- Confidence: **{claim['confidence']}**",
                f"- Outcomes: {', '.join(claim['supported_by_outcome_ids'])}",
                f"- Limitations: {', '.join(claim['limitations']) if claim['limitations'] else 'none'}",
                f"- Automatic promotion: **{claim['automatic_promotion']}**",
                "",
            ])

        for comparison in experiment["comparisons"]:
            lines.extend([
                "",
                f"### Comparison: {comparison['baseline_arm']} → "
                f"{comparison['treatment_arm']}",
                "",
                "| Metric | Baseline mean | Treatment mean | Δ | Std. difference |",
                "| --- | ---: | ---: | ---: | ---: |",
            ])
            for metric, result in comparison["numeric_differences"].items():
                def fmt(value: Any) -> str:
                    return "-" if value is None else f"{float(value):.6g}"
                lines.append(
                    f"| {metric} | {fmt(result['baseline_mean'])} | "
                    f"{fmt(result['treatment_mean'])} | "
                    f"{fmt(result['absolute_difference'])} | "
                    f"{fmt(result['standardized_difference'])} |"
                )
        lines.append("")

    return "\n".join(lines)



def build_experiment_knowledge_payload(analysis_payload: dict[str, Any]) -> dict[str, Any]:
    """Build the stable Stage 1D knowledge contract from analyzed experiments."""
    experiments_registry: dict[str, dict[str, Any]] = {}
    outcomes_registry: dict[str, dict[str, Any]] = {}
    claims_registry: dict[str, dict[str, Any]] = {}
    relations = {
        "experiment_outcomes": [],
        "experiment_claims": [],
        "claim_outcomes": [],
        "claim_rules": [],
    }

    for experiment in analysis_payload.get("experiments", []):
        experiment_id = str(experiment["experiment_id"])
        outcome_ids = [str(item["outcome_id"]) for item in experiment.get("outcomes", [])]
        claim_ids = [str(item["claim_id"]) for item in experiment.get("claims", [])]
        experiments_registry[experiment_id] = {
            "experiment_id": experiment_id,
            "title": experiment.get("title"),
            "research_question": experiment.get("research_question"),
            "experiment_status": experiment.get("experiment_status"),
            "experiment_type": experiment.get("experiment_type"),
            "experiment_metadata": experiment.get("experiment_metadata", {}),
            "rule_ids": experiment.get("rule_ids", []),
            "single_rule_design": experiment.get("single_rule_design", False),
            "design_confidence": experiment.get("design_confidence", "NONE"),
            "common_horizon": experiment.get("common_horizon"),
            "run_ids": experiment.get("run_ids", []),
            "condition_ids": experiment.get("condition_ids", []),
            "limitations": experiment.get("limitations", []),
            "warnings": experiment.get("warnings", []),
            "outcome_ids": outcome_ids,
            "claim_ids": claim_ids,
        }
        for outcome in experiment.get("outcomes", []):
            outcome_id = str(outcome["outcome_id"])
            stored = dict(outcome)
            stored["experiment_id"] = experiment_id
            outcomes_registry[outcome_id] = stored
            relations["experiment_outcomes"].append({
                "experiment_id": experiment_id,
                "outcome_id": outcome_id,
            })
        for claim in experiment.get("claims", []):
            claim_id = str(claim["claim_id"])
            stored = dict(claim)
            stored["kind"] = "experiment_claim"
            claims_registry[claim_id] = stored
            relations["experiment_claims"].append({
                "experiment_id": experiment_id,
                "claim_id": claim_id,
            })
            for outcome_id in claim.get("supported_by_outcome_ids", []):
                relations["claim_outcomes"].append({
                    "claim_id": claim_id,
                    "outcome_id": str(outcome_id),
                })
            for rule_id in claim.get("scope", {}).get("rule_ids", []):
                relations["claim_rules"].append({
                    "claim_id": claim_id,
                    "rule_id": str(rule_id),
                })

    return {
        "schema": "archon_experiment_knowledge_v1",
        "source_analysis_schema": analysis_payload.get("schema"),
        "telemetry_database": analysis_payload.get("telemetry_database"),
        "profiles_source": analysis_payload.get("profiles_source"),
        "summary": {
            "experiments": len(experiments_registry),
            "outcomes": len(outcomes_registry),
            "claims": len(claims_registry),
            "supported_claims": sum(
                item.get("status") == "supported"
                for item in claims_registry.values()
            ),
            "mixed_claims": sum(
                item.get("status") == "mixed"
                for item in claims_registry.values()
            ),
            "not_supported_claims": sum(
                item.get("status") == "not_supported"
                for item in claims_registry.values()
            ),
        },
        "experiments": experiments_registry,
        "outcomes": outcomes_registry,
        "claims": claims_registry,
        "relations": relations,
        "policy": {
            "automatic_promotion": False,
            "causal_interpretation": False,
            "consumer_contract": "knowledge_consumers_must_not_read_raw_analysis",
        },
    }


def audit_experiment_knowledge(payload: dict[str, Any]) -> dict[str, Any]:
    experiments = payload.get("experiments", {})
    outcomes = payload.get("outcomes", {})
    claims = payload.get("claims", {})
    issues: list[dict[str, Any]] = []

    def issue(code: str, **context: Any) -> None:
        issues.append({"code": code, **context})

    for outcome_id, outcome in outcomes.items():
        experiment_id = str(outcome.get("experiment_id", ""))
        if experiment_id not in experiments:
            issue("outcome_unknown_experiment", outcome_id=outcome_id, experiment_id=experiment_id)

    for claim_id, claim in claims.items():
        experiment_id = str(claim.get("experiment_id", ""))
        if experiment_id not in experiments:
            issue("claim_unknown_experiment", claim_id=claim_id, experiment_id=experiment_id)
        outcome_ids = [str(x) for x in claim.get("supported_by_outcome_ids", [])]
        if not outcome_ids:
            issue("claim_without_provenance", claim_id=claim_id)
        for outcome_id in outcome_ids:
            if outcome_id not in outcomes:
                issue("claim_unknown_outcome", claim_id=claim_id, outcome_id=outcome_id)
            elif str(outcomes[outcome_id].get("experiment_id")) != experiment_id:
                issue("cross_experiment_outcome_reference", claim_id=claim_id, outcome_id=outcome_id)
        if claim.get("automatic_promotion") is not False:
            issue("automatic_promotion_not_disabled", claim_id=claim_id)
        if claim.get("causal_interpretation") is not False:
            issue("causal_interpretation_not_disabled", claim_id=claim_id)
        rule_ids = claim.get("scope", {}).get("rule_ids", [])
        if any(normalize_rule_id(rule_id) != str(rule_id) for rule_id in rule_ids):
            issue("noncanonical_rule_id", claim_id=claim_id, rule_ids=rule_ids)
        if len(rule_ids) <= 1 and claim.get("claim_type") not in {
            "qualitative_state_preservation",
            "observed_horizon_preservation",
            "quantitative_sensitivity",
        }:
            issue("possible_overgeneralized_single_rule_claim", claim_id=claim_id)

    relation_seen: set[tuple[str, str, str]] = set()
    for relation_type, items in payload.get("relations", {}).items():
        for item in items:
            marker = (relation_type, json.dumps(item, sort_keys=True), "")
            if marker in relation_seen:
                issue("duplicate_relation", relation_type=relation_type, relation=item)
            relation_seen.add(marker)

    return {
        "schema": "archon_experiment_knowledge_integrity_v1",
        "ok": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "counts": {
            "experiments": len(experiments),
            "outcomes": len(outcomes),
            "claims": len(claims),
            "relations": sum(len(v) for v in payload.get("relations", {}).values()),
        },
    }


def render_knowledge_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# ARCHON Experiment Knowledge v1",
        "",
        "Machine-readable experiment outcomes and scoped claims.",
        "",
        f"- Experiments: **{payload['summary']['experiments']}**",
        f"- Outcomes: **{payload['summary']['outcomes']}**",
        f"- Claims: **{payload['summary']['claims']}**",
        "",
    ]
    for experiment_id, experiment in payload.get("experiments", {}).items():
        lines.extend([
            f"## {experiment_id}: {experiment.get('title') or 'Untitled experiment'}",
            "",
            f"- Rules: {experiment.get('rule_ids') or '-'}",
            f"- Design confidence: **{experiment.get('design_confidence', 'NONE')}**",
            f"- Horizon: {experiment.get('common_horizon')}",
            f"- Limitations: {', '.join(experiment.get('limitations', [])) or 'none'}",
            "",
            "### Claims",
            "",
        ])
        for claim_id in experiment.get("claim_ids", []):
            claim = payload["claims"][claim_id]
            lines.extend([
                f"#### {claim_id}: {claim.get('claim_type')}",
                "",
                str(claim.get("statement", "")),
                "",
                f"- Status: **{claim.get('status')}**",
                f"- Confidence: **{claim.get('confidence')}**",
                f"- Outcomes: {', '.join(claim.get('supported_by_outcome_ids', []))}",
                f"- Automatic promotion: **{claim.get('automatic_promotion')}**",
                "",
            ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_folder")
    parser.add_argument("--telemetry-db", required=True)
    parser.add_argument("--profiles")
    parser.add_argument("--experiment-id", action="append")
    parser.add_argument("--out-dir")
    args = parser.parse_args(argv)

    results = Path(args.results_folder).expanduser().resolve()
    database = Path(args.telemetry_db).expanduser().resolve()
    profiles_path = (
        Path(args.profiles).expanduser().resolve()
        if args.profiles
        else results / "observer_profiles_v31.json"
    )
    out_dir = (
        Path(args.out_dir).expanduser().resolve()
        if args.out_dir
        else PROJECT_ROOT / "Results" / "Analysis" / "Experiments"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    profile_index = load_profile_index(profiles_path)
    connection = connect_ro(database)
    try:
        rows = load_experiment_rows(connection, None)
    finally:
        connection.close()

    wanted = set(args.experiment_id or [])
    if wanted:
        rows = [
            row for row in rows
            if row["experiment_id"] in wanted
        ]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["experiment_id"])].append(row)

    experiments = [
        analyze_experiment(experiment_id, experiment_rows, profile_index)
        for experiment_id, experiment_rows in sorted(grouped.items())
    ]

    payload = {
        "schema": "archon_experiment_analysis_v1_4",
        "telemetry_database": str(database),
        "profiles_source": str(profiles_path),
        "experiment_count": len(experiments),
        "experiments": experiments,
    }

    knowledge_payload = build_experiment_knowledge_payload(payload)
    integrity_payload = audit_experiment_knowledge(knowledge_payload)

    json_out = out_dir / "experiment_analysis.json"
    md_out = out_dir / "experiment_analysis.md"
    knowledge_json_out = out_dir / "experiment_knowledge.json"
    knowledge_md_out = out_dir / "experiment_knowledge.md"
    integrity_out = out_dir / "experiment_knowledge_integrity.json"

    json_out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_out.write_text(render_markdown(payload), encoding="utf-8")
    knowledge_json_out.write_text(
        json.dumps(knowledge_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    knowledge_md_out.write_text(
        render_knowledge_markdown(knowledge_payload),
        encoding="utf-8",
    )
    integrity_out.write_text(
        json.dumps(integrity_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("ARCHON Experiment Analyzer v1.4 — Stage 1D")
    print("=" * 72)
    print(f"Experiments: {len(experiments)}")
    print(f"JSON: {json_out}")
    print(f"Markdown: {md_out}")
    print(f"Knowledge JSON: {knowledge_json_out}")
    print(f"Knowledge Markdown: {knowledge_md_out}")
    print(f"Knowledge Integrity: {integrity_out}")
    print(
        f"Knowledge integrity: {'PASS' if integrity_payload['ok'] else 'FAIL'} "
        f"issues={integrity_payload['issue_count']}"
    )
    for experiment in experiments:
        print(
            f"{experiment['experiment_id']}: "
            f"runs={experiment['run_count']} "
            f"arms={experiment['arm_count']} "
            f"design_confidence={experiment['design_confidence']} "
            f"outcomes={experiment['outcome_summary']['total']} "
            f"claims={experiment['claim_summary']['total']} "
            f"warnings={len(experiment['warnings'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
