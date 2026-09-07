"""Required canonical-control construction and normalization."""
from __future__ import annotations

import statistics
from typing import Any

from .utils import safe_float, safe_int

def infer_sample_interval(rows: list[dict[str, str]]) -> int | None:
    ticks = [
        tick for row in rows
        if (tick := safe_int(row.get("tick"))) is not None
    ]
    if len(ticks) < 2:
        return None
    diffs = [
        b - a for a, b in zip(ticks, ticks[1:])
        if b > a
    ]
    return int(statistics.median(diffs)) if diffs else None


def build_required_control(
    manifest: dict[str, Any],
    original_rule: dict[str, Any],
    baseline_rows: list[dict[str, str]],
    mutant_rows: list[dict[str, str]],
    parent_rule_id: str,
    baseline_match: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Produce a machine-readable control request when a usable canonical
    baseline is missing or too weak for a controlled comparison.
    """
    match_type = baseline_match.get("match_type")
    coverage = safe_float(baseline_match.get("coverage_ratio")) or 0.0
    baseline_interval = infer_sample_interval(baseline_rows)
    sample_interval = infer_sample_interval(mutant_rows)
    sample_interval_matches = (
        baseline_interval is not None
        and sample_interval is not None
        and baseline_interval == sample_interval
    )

    needs_control = (
        match_type == "missing"
        or coverage < 1.0
        or baseline_match.get("same_seed") is not True
        or not sample_interval_matches
    )
    if not needs_control:
        return None

    final_tick_value = (
        safe_int(mutant_rows[-1].get("tick"))
        if mutant_rows else None
    )
    if match_type == "missing":
        reason = "canonical_baseline_missing"
    elif baseline_match.get("same_seed") is not True:
        reason = "baseline_seed_mismatch"
    elif coverage < 1.0:
        reason = "baseline_horizon_incomplete"
    else:
        reason = "baseline_sample_interval_mismatch"

    return {
        "schema": "archon_required_control_v1",
        "status": "required",
        "reason": reason,
        "job_type": "observer_control",
        "experiment_role": "canonical_control",
        "canonical_rule_id": parent_rule_id,
        "canonical_rule_seed": original_rule.get("seed"),
        "target_ticks": final_tick_value,
        "sample_interval": sample_interval,
        "current_baseline_sample_interval": baseline_interval,
        "observer_version": manifest.get("observer_version")
            or manifest.get("version"),
        "required_conditions": {
            "use_canonical_original": True,
            "mutation_enabled": False,
            "same_rule_seed": True,
            "same_initial_state": True,
            "same_observer_configuration": True,
            "same_tick_horizon": True,
            "same_sample_interval": True,
        },
        "source_mutation_id": manifest.get("mutation_id"),
        "source_mutation_mode": manifest.get("mutation_mode"),
        "source_mutation_parameter": manifest.get("mutation_parameter"),
        "source_mutation_seed": manifest.get("mutation_seed"),
        "current_baseline_match": match_type,
        "current_coverage_ratio": round(coverage, 4),
        "priority": "HIGH",
        "blocking": [
            "causal_effect_interpretation",
            "institutional_evidence_ingestion",
            "director_level_conclusion",
        ],
    }


def render_control_markdown(control: dict[str, Any]) -> str:
    lines = [
        "# ARCHON Required Control",
        "",
        f"Canonical rule: **{control.get('canonical_rule_id')}**",
        f"Source mutation: **{control.get('source_mutation_id')}**",
        f"Reason: **{control.get('reason')}**",
        f"Priority: **{control.get('priority')}**",
        "",
        "## Required run",
        "",
        f"- Rule: **{control.get('canonical_rule_id')}**",
        f"- Seed: **{control.get('canonical_rule_seed')}**",
        f"- Target ticks: **{control.get('target_ticks')}**",
        f"- Sample interval: **{control.get('sample_interval')}**",
        f"- Observer version: **{control.get('observer_version')}**",
        "- Mutation enabled: **False**",
        "",
        "## Scientific requirement",
        "",
        "The clean canonical rule must be observed under the same conditions "
        "as the mutation before causal interpretation is allowed.",
        "",
    ]
    return "\n".join(lines)


def normalize_required_control_reason(
    control: dict[str, Any],
) -> dict[str, Any]:
    """Migrate the former catch-all reason without recomputing old reports."""

    normalized = dict(control)
    if normalized.get("reason") != "canonical_baseline_not_exact":
        return normalized
    coverage = safe_float(normalized.get("current_coverage_ratio")) or 0.0
    normalized["reason"] = (
        "baseline_horizon_incomplete"
        if coverage < 1.0
        else "baseline_sample_interval_mismatch"
    )
    return normalized

