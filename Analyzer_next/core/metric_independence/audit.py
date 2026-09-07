"""Pure calculations for ARCHON KNOW/FB metric independence.

BRIDGE5.3.3 keeps the protected observational audit semantics unchanged while
making the controlled metric-baseline lane count *physical experiment runs*,
not every retained passport/profile snapshot.

Observer Profile v31 intentionally routes baseline/control records through the
``experimental`` evidence channel and treatment records through the
``perturbation`` channel. Both are members of the same controlled experiment.
Metric-readiness validation therefore selects experiment-linked baseline and
treatment rows from either channel, then deduplicates retained snapshots to one
canonical final record per physical run. Standalone perturbation records without
an experiment identity/role are excluded. Conflicting duplicate identities are
excluded fail-closed and reported explicitly.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

VERSION = "1.1-BRIDGE5.3.3"
INDEPENDENT = "STRUCTURALLY_INDEPENDENT_V2"
MINIMUM_BASELINE_PROFILES = 10
MINIMUM_PARENT_RULES = 2


def number(value: Any):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def correlation(rows, left, right):
    pairs = [
        (x, y)
        for row in rows
        if (x := number(row.get(left))) is not None
        and (y := number(row.get(right))) is not None
    ]
    if len(pairs) < 3:
        return None
    mx = sum(x for x, _ in pairs) / len(pairs)
    my = sum(y for _, y in pairs) / len(pairs)
    n = sum((x - mx) * (y - my) for x, y in pairs)
    d = math.sqrt(
        sum((x - mx) ** 2 for x, _ in pairs)
        * sum((y - my) ** 2 for _, y in pairs)
    )
    return None if d == 0 else n / d


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rule_id(row: dict[str, Any]) -> str | None:
    value = _text(row.get("rule")) or _text(row.get("rule_id"))
    if not value:
        return None
    try:
        return f"{int(value):05d}"
    except (TypeError, ValueError):
        return value


def _role(row: dict[str, Any]) -> str:
    value = _text(row.get("telemetry_experiment_role")).lower()
    if value in {"baseline_control", "control", "baseline"}:
        return "baseline"
    if value in {"treatment", "treated"}:
        return "treatment"
    return value or "unknown"


def _physical_run_id(row: dict[str, Any]) -> str:
    """Mirror Observer v31 provenance identity without importing legacy code.

    A real Observer state run id is authoritative. Legacy/synthetic profile
    records may expose an ``EXP-*`` placeholder instead; Observer v31 resolves
    those via the passport filename, so the audit uses the same fallback.
    """
    run_id = _text(row.get("observer_state_run_id"))
    if run_id and not run_id.startswith("EXP-"):
        return run_id

    source = _text(row.get("source_file"))
    if source:
        name = Path(source).name
        suffix = "_passport.json"
        if name.endswith(suffix):
            resolved = name[:-len(suffix)]
            if resolved:
                return resolved
        if name:
            return name
    return run_id


def _run_group_key(row: dict[str, Any]) -> str:
    run_id = _physical_run_id(row)
    experiment_id = _text(row.get("telemetry_experiment_id"))
    # Prefix the legacy fallback with experiment identity to avoid accidental
    # collisions between historical runtime packages with reused filenames.
    if run_id:
        return f"{experiment_id}|{run_id}" if experiment_id else run_id
    return ""


def _identity_conflicts(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    fields = {
        "telemetry_experiment_id": lambda row: _text(row.get("telemetry_experiment_id")),
        "telemetry_condition_id": lambda row: _text(row.get("telemetry_condition_id")),
        "telemetry_experiment_role": _role,
        "rule": lambda row: _rule_id(row) or "",
    }
    conflicts: dict[str, list[str]] = {}
    for field, getter in fields.items():
        values = sorted({value for row in rows if (value := getter(row))})
        if len(values) > 1:
            conflicts[field] = values
    return conflicts


def _record_rank(row: dict[str, Any]) -> tuple[int, str, str]:
    value = row.get("observer_state_tick")
    try:
        tick = -1 if value in (None, "") else int(value)
    except (TypeError, ValueError):
        tick = -1
    return (
        tick,
        _text(row.get("created")),
        _text(row.get("source_file")),
    )


def _canonical_experimental_runs(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return one final profile per physical run plus integrity conflicts."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unresolved = 0
    for row in records:
        key = _run_group_key(row)
        if not key:
            unresolved += 1
            continue
        grouped[key].append(row)

    canonical: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for key, rows in sorted(grouped.items()):
        identity_conflicts = _identity_conflicts(rows)
        if identity_conflicts:
            conflicts.append({
                "run_key": key,
                "record_count": len(rows),
                "conflicts": identity_conflicts,
            })
            continue
        canonical.append(max(rows, key=_record_rank))
    return canonical, conflicts, unresolved


def _experimental_validation(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build a non-observational feedback-v2 baseline validation summary.

    The field is omitted entirely for legacy payloads that do not expose
    ``profile_records``. This preserves exact characterization parity for old
    Observer profile fixtures.
    """
    records = payload.get("profile_records")
    if not isinstance(records, list):
        return None

    # Observer Profile v31 deliberately gives treatment observations the
    # ``perturbation`` channel while matched controls remain ``experimental``.
    # Metric-baseline validation is about the controlled experiment registry,
    # not the downstream claim-evidence channel. Include both halves only when
    # an explicit experiment id and baseline/treatment role prove membership in
    # a controlled experiment. This keeps standalone mutation observations out.
    experiment_records = [
        row
        for row in records
        if isinstance(row, dict)
        and _text(row.get("evidence_channel")).lower() in {"experimental", "perturbation"}
        and _text(row.get("telemetry_experiment_id"))
        and _role(row) in {"baseline", "treatment"}
    ]
    candidate_channel_counts = Counter(
        _text(row.get("evidence_channel")).lower() or "unknown"
        for row in experiment_records
    )
    canonical_runs, conflicts, unresolved_identity_count = (
        _canonical_experimental_runs(experiment_records)
    )
    completed = [
        row
        for row in canonical_runs
        if _text(row.get("telemetry_run_status")).lower()
        in {"completed", "imported"}
    ]
    independent = [
        row
        for row in completed
        if _text(row.get("feedback_metric_independence_status")).upper()
        == INDEPENDENT
    ]
    response_capable = [
        row
        for row in independent
        if (number(row.get("feedback_response_opportunity")) or 0.0) > 0.0
    ]

    parent_rules = sorted(
        {
            rid
            for row in response_capable
            if (rid := _rule_id(row)) is not None
        }
    )
    experiment_ids = sorted(
        {
            _text(row.get("telemetry_experiment_id"))
            for row in response_capable
            if _text(row.get("telemetry_experiment_id"))
        }
    )
    roles = Counter(_role(row) for row in response_capable)
    has_baseline = roles.get("baseline", 0) > 0
    has_treatment = roles.get("treatment", 0) > 0
    role_coverage = has_baseline and has_treatment

    sufficient = (
        len(response_capable) >= MINIMUM_BASELINE_PROFILES
        and len(parent_rules) >= MINIMUM_PARENT_RULES
        and role_coverage
    )

    return {
        "schema": "archon_feedback_v2_experimental_validation_v3",
        "status": "BASELINE_SUFFICIENT" if sufficient else "BASELINE_INSUFFICIENT",
        "profile_records_seen": len(experiment_records),
        "candidate_channel_record_counts": dict(sorted(candidate_channel_counts.items())),
        "unique_physical_runs_seen": len(canonical_runs),
        "duplicate_profile_records": max(
            0,
            len(experiment_records) - len(canonical_runs) - sum(
                item["record_count"] for item in conflicts
            ) - unresolved_identity_count,
        ) + sum(max(0, item["record_count"] - 1) for item in conflicts),
        "identity_conflict_run_count": len(conflicts),
        "unresolved_run_identity_record_count": unresolved_identity_count,
        "identity_conflicts": conflicts,
        "completed_run_count": len(completed),
        "independent_v2_run_count": len(independent),
        "nonzero_response_opportunity_run_count": len(response_capable),
        "eligible_run_count": len(response_capable),
        # Backward-compatible planner key. From v2 onward this is explicitly a
        # unique physical-run count, not a raw retained-profile count.
        "eligible_profile_count": len(response_capable),
        "minimum_profile_count": MINIMUM_BASELINE_PROFILES,
        "unique_parent_rule_count": len(parent_rules),
        "minimum_parent_rule_count": MINIMUM_PARENT_RULES,
        "parent_rules": parent_rules,
        "unique_experiment_count": len(experiment_ids),
        "experiment_ids": experiment_ids,
        "role_counts": dict(sorted(roles.items())),
        "matched_role_coverage": role_coverage,
        "requirements": {
            "completed_experimental_run": True,
            "feedback_metric_independence_status": INDEPENDENT,
            "feedback_response_opportunity_gt_zero": True,
            "multiple_parent_rules": True,
            "baseline_and_treatment_roles": True,
            "unit_of_counting": "physical_run",
        },
        "scientific_policy": {
            "counts_as_observational_claim_evidence": False,
            "counts_as_direct_perturbation_claim_evidence": False,
            "may_satisfy_metric_baseline_readiness": True,
            "automatic_claim_promotion": False,
            "duplicate_profile_records_are_independent": False,
            "metric_validation_channels": ["experimental", "perturbation"],
            "standalone_perturbations_without_experiment_identity": "EXCLUDED",
            "conflicting_duplicate_identities": "EXCLUDED_FAIL_CLOSED",
        },
    }


def build_report(payload, source, generated_at):
    rows = [r for r in payload.get("profiles", []) if isinstance(r, dict)]
    statuses = Counter(
        str(r.get("feedback_metric_independence_status") or "LEGACY_COUPLED_V1")
        for r in rows
    )
    versions = Counter(str(r.get("feedback_metric_version") or "1.0") for r in rows)
    independent = [
        r for r in rows if r.get("feedback_metric_independence_status") == INDEPENDENT
    ]
    legacy = [r for r in rows if r not in independent]
    report = {
        "schema": "archon_metric_independence_audit_v1",
        "version": VERSION if isinstance(payload.get("profile_records"), list) else "1.0",
        "generated_at": generated_at,
        "source": source,
        "status": "INDEPENDENT_METRIC_AVAILABLE" if independent else "LEGACY_COUPLING_CONFIRMED",
        "profile_count": len(rows),
        "metric_versions": dict(sorted(versions.items())),
        "independence_statuses": dict(sorted(statuses.items())),
        "empirical_diagnostics": {
            "knowledge_feedback_correlation_all": correlation(rows, "knowledge_score", "feedback_score"),
            "knowledge_feedback_correlation_legacy": correlation(legacy, "knowledge_score", "feedback_score"),
            "knowledge_feedback_correlation_independent_v2": correlation(independent, "knowledge_score", "feedback_score"),
            "independent_v2_profile_count": len(independent),
            "legacy_profile_count": len(legacy),
        },
        "structural_diagnostics": {
            "legacy_metric": {
                "status": "COUPLED_BY_CONSTRUCTION",
                "positive_score_terms_with_knowledge_path": 5,
                "positive_score_term_count": 6,
                "minimum_positive_weight_with_knowledge_path": 0.789,
                "note": "The lower bound excludes additional indirect paths through self_direction and upstream civilization axes.",
            },
            "v2_metric": {
                "status": INDEPENDENT,
                "score_inputs": [
                    "evo_adapt", "evo_recovery", "demo_survival_ratio",
                    "demo_replacement", "stability_index", "ecosystem_health",
                    "pressure", "stress", "risk", "mass_growth", "trade",
                    "cohesion", "conflict", "tech",
                ],
                "knowledge_inputs_in_score": [],
                "knowledge_impact_role": "DIAGNOSTIC_ONLY",
            },
        },
        "claim_routing": {
            "GP-102": {"legacy_profiles": "UNAVAILABLE", "independent_v2_profiles": "ELIGIBLE"},
            "GP-103": {"legacy_profiles": "UNAVAILABLE", "independent_v2_profiles": "ELIGIBLE"},
        },
        "interpretation": "Legacy KNOW/FB correlation cannot be treated as evidence for a world-level coupling. New v2 observations may test the claim, but correlation alone still does not establish causality.",
    }

    experimental_validation = _experimental_validation(payload)
    if experimental_validation is not None:
        report["experimental_validation"] = experimental_validation
        report["empirical_diagnostics"][
            "experimental_baseline_eligible_v2_profile_count"
        ] = experimental_validation["eligible_run_count"]
        report["empirical_diagnostics"][
            "experimental_baseline_eligible_v2_run_count"
        ] = experimental_validation["eligible_run_count"]

    return report


def render_markdown(report):
    d = report["empirical_diagnostics"]
    fmt = lambda v: "-" if v is None else f"{v:.6f}"
    lines = [
        "# ARCHON Metric Independence Audit",
        "",
        f"- Status: **{report['status']}**",
        f"- Profiles: **{report['profile_count']}**",
        f"- KNOW/FB correlation (legacy): **{fmt(d['knowledge_feedback_correlation_legacy'])}**",
        f"- KNOW/FB correlation (independent v2): **{fmt(d['knowledge_feedback_correlation_independent_v2'])}**",
        f"- Independent v2 coverage: **{d['independent_v2_profile_count']}**",
    ]
    validation = report.get("experimental_validation")
    if isinstance(validation, dict):
        lines.extend([
            "",
            "## Controlled Experimental Metric Validation",
            "",
            f"- Status: **{validation['status']}**",
            f"- Retained controlled-experiment profile records: **{validation['profile_records_seen']}**",
            f"- Candidate channels: **{validation.get('candidate_channel_record_counts', {})}**",
            f"- Unique resolved physical runs: **{validation['unique_physical_runs_seen']}**",
            f"- Duplicate profile records: **{validation['duplicate_profile_records']}**",
            f"- Conflicting run identities excluded: **{validation['identity_conflict_run_count']}**",
            f"- Eligible feedback-v2 runs: **{validation['eligible_run_count']}** / **{validation['minimum_profile_count']}** required",
            f"- Independent parent rules: **{validation['unique_parent_rule_count']}** / **{validation['minimum_parent_rule_count']}** required",
            f"- Parent rules: **{', '.join(validation['parent_rules']) if validation['parent_rules'] else '-'}**",
            f"- Baseline + treatment role coverage: **{'yes' if validation['matched_role_coverage'] else 'no'}**",
            "- Unit of experimental baseline counting: **physical run**, not retained passport/profile record.",
            "- These experimental runs validate metric readiness only; they do not become observational or direct perturbation claim support.",
        ])
    lines.extend([
        "",
        "Legacy GP-102/GP-103 evidence is routed to `UNAVAILABLE`. Only feedback metric v2 can contribute to these claims.",
        "",
    ])
    return "\n".join(lines)
