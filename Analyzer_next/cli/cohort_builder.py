#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project ARCHON Cohort Builder v1.1.1.

Builds conservative scientific cohorts from Observer Profile v30 data.

Primary functions:
- evaluate every search target from scientific_claims.py;
- construct the four GP-102 KNOW/FB quadrants;
- identify exact, near, and missing regimes;
- rank matched controls using morphology, behaviour, dynamics, family,
  lifetime, emergence, validation, and stability;
- avoid pseudo-replication by using one representative profile per rule;
- emit machine-readable and Markdown reports for later engines.

Outputs:
- cohort_report.json
- cohort_report.md
- cohort_targets.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Analyzer_next.core.scientific_claims import CLAIM_SPECS, TARGETS, sf, ss
from archon_paths import ANALYSIS_RESULTS_DIR, KNOWLEDGE_ATLAS_DIR, PROJECT_ROOT, SEARCH_RESULTS_DIR

def analysis_results_dir() -> Path: return ANALYSIS_RESULTS_DIR

def knowledge_atlas_dir() -> Path: return KNOWLEDGE_ATLAS_DIR

def resolve_results_dir(value=None) -> Path:
    if value is None or not str(value).strip(): return SEARCH_RESULTS_DIR.resolve()
    raw=Path(value).expanduser(); candidates=[raw] if raw.is_absolute() else [Path.cwd()/raw,PROJECT_ROOT/raw,SEARCH_RESULTS_DIR/raw]
    for candidate in candidates:
        if candidate.exists(): return candidate.resolve()
    raise FileNotFoundError(f"Results folder not found: {value}")

SCHEMA = "archon_cohort_report_v1_1_1"
VERSION = "Project ARCHON Cohort Builder v1.1.1"

ALIASES = {
    "EMG": "emergence_score",
    "VAL": "validation_quality",
    "FP": "validation_false_positive_risk",
    "FN": "validation_false_negative_risk",
    "KNOW": "knowledge_score",
    "FB": "feedback_score",
    "CIV": "civilization_score",
    # Counterexample search uses the strongest observed memory state, not only
    # the terminal value after a collapse may already have erased it.
    "memory": "knowledge_memory_peak",
    "memory_peak": "knowledge_memory_peak",
    "stability": "stability_index",
    "effective_risk": "feedback_effective_risk",
    "self_direction": "feedback_self_direction",
    "collapsed": "collapsed",
}

NON_MATCH_FEATURES_BY_CLAIM = {
    "GP-101": {"emergence_score", "validation_quality",
               "validation_false_positive_risk",
               "validation_false_negative_risk"},
    "GP-102": {"knowledge_score", "feedback_score"},
    "GP-103": {"feedback_score", "feedback_effective_risk",
               "feedback_self_direction"},
    "GP-104": {"emergence_score", "validation_quality"},
    "GP-105": {"civilization_score", "knowledge_score"},
    "GP-201": {
        "knowledge_memory",
        "knowledge_memory_peak",
        "stability_index",
        "collapsed",
    },
}

MATCH_FEATURES = (
    "final_tick",
    "stability_index",
    "emergence_score",
    "validation_quality",
    "civilization_score",
    "knowledge_score",
    "feedback_score",
    "feedback_effective_risk",
    "emergence_complexity",
    "family_count",
    "deepest_generation",
    "peak_objects",
)

LOG_FEATURES = {"final_tick", "peak_objects", "deepest_generation"}

# Claim-target calibrations are kept here rather than silently changing
# scientific_claims.py. The report records both declared and effective
# constraints.
TARGET_CALIBRATIONS: dict[tuple[str, str], dict[str, str]] = {
    # "Persistent" must describe a surviving long-run world, not a short
    # collapsed transient that happens to sit near an EMG threshold.
    ("GP-104", "persistent_under_scored"): {
        "collapsed": "false",
        "final_tick": ">=50000",
    },
}


def calibrated_constraints(
    claim_id: str,
    target_name: str,
    declared: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    effective = dict(declared)
    applied: dict[str, Any] = {}
    for alias, expression in TARGET_CALIBRATIONS.get(
        (claim_id, target_name), {}
    ).items():
        if alias not in effective:
            effective[alias] = expression
            applied[alias] = expression
    return effective, applied


@dataclass
class CohortMember:
    rule: str
    experiment_id: str
    source_file: str
    family: str
    analyzer_category: str
    final_tick: int
    collapsed: bool
    emg: float
    val: float
    know: float
    fb: float
    civ: float
    stability: float
    effective_risk: float
    target_margin: float = 0.0
    failed_constraint_count: int = 0
    total_deficit: float = 0.0
    failed_constraints: list[str] | None = None


@dataclass
class MatchPair:
    target_rule: str
    control_rule: str
    score: float
    profile_distance: float
    morphology_distance: float | None
    behaviour_distance: float | None
    dynamic_distance: float | None
    same_family: bool
    same_template_category: bool
    reason: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def rule_id(value: Any) -> str:
    raw = ss(value).strip()
    return raw.zfill(5) if raw.isdigit() else raw


def collapsed(profile: dict[str, Any]) -> bool:
    if profile.get("collapse_tick") is not None:
        return True
    category = ss(profile.get("analyzer_category")).lower()
    warnings = {ss(x).lower() for x in profile.get("warnings", [])}
    return category == "collapsed_world" or "collapsed" in warnings


def representative_profiles(data: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = data.get("profiles", [])
    if not isinstance(profiles, list):
        return []
    # observer_profiles_v30 already provides one representative per rule.
    # Defensive de-duplication protects older files.
    best: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        rid = rule_id(profile.get("rule"))
        if not rid:
            continue
        current = best.get(rid)
        if current is None:
            best[rid] = profile
            continue
        key = (
            int(sf(profile.get("final_tick"))),
            ss(profile.get("created")),
        )
        old_key = (
            int(sf(current.get("final_tick"))),
            ss(current.get("created")),
        )
        if key > old_key:
            best[rid] = profile
    return [best[k] for k in sorted(best)]


def atlas_maps(atlas: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    family: dict[str, str] = {}
    category: dict[str, str] = {}
    for item in atlas.get("experiments", []):
        if not isinstance(item, dict):
            continue
        rid = rule_id(item.get("rule"))
        if not rid:
            continue
        if item.get("is_representative") or rid not in family:
            family[rid] = ss(item.get("family"), "Unknown")
            category[rid] = ss(item.get("analyzer_category"), "")
    return family, category


def matrix_map(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    raw = payload.get("distance_matrix", {})
    result: dict[str, dict[str, float]] = {}
    if not isinstance(raw, dict):
        return result
    for left, row in raw.items():
        if not isinstance(row, dict):
            continue
        result[rule_id(left)] = {
            rule_id(right): sf(value, 1.0)
            for right, value in row.items()
        }
    return result


def combined_map(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    groups = payload.get("similar_worlds", {})
    if not isinstance(groups, dict):
        return result
    for left, info in groups.items():
        rid = rule_id(left)
        row: dict[str, float] = {}
        if isinstance(info, dict):
            for bucket in ("most_similar", "most_different"):
                for item in info.get(bucket, []):
                    if isinstance(item, dict):
                        row[rule_id(item.get("rule_id"))] = sf(
                            item.get("combined_distance"), 1.0
                        )
        result[rid] = row
    return result


def template_categories(payload: dict[str, Any]) -> dict[str, str]:
    rules = payload.get("rules", {})
    if not isinstance(rules, dict):
        return {}
    return {
        rule_id(rid): ss(info.get("dominant_template_category"), "")
        for rid, info in rules.items()
        if isinstance(info, dict)
    }


def value_for(profile: dict[str, Any], alias: str) -> Any:
    field = ALIASES.get(alias, alias)
    if field == "collapsed":
        return collapsed(profile)
    return profile.get(field)


_TERM = re.compile(r"^\s*(>=|<=|>|<|==|=)\s*(-?\d+(?:\.\d+)?)\s*$")
_NAMED_TERM = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*"
    r"(>=|<=|>|<|==|=)\s*(-?\d+(?:\.\d+)?)\s*$"
)


def term_margin(value: Any, expression: str) -> tuple[bool, float]:
    """Return (satisfied, signed normalized margin).

    Positive margin means the condition is satisfied. Negative means distance
    to the boundary. Numeric scales are expected mostly in [0, 1].
    """
    if isinstance(value, bool):
        expected = expression.strip().lower() in {"true", "1", "yes"}
        return value == expected, 1.0 if value == expected else -1.0

    match = _TERM.match(expression)
    if not match:
        return False, -1.0
    op, raw = match.groups()
    threshold = float(raw)
    x = sf(value)
    scale = max(1.0, abs(threshold))
    if op == ">=":
        return x >= threshold, (x - threshold) / scale
    if op == ">":
        return x > threshold, (x - threshold) / scale
    if op == "<=":
        return x <= threshold, (threshold - x) / scale
    if op == "<":
        return x < threshold, (threshold - x) / scale
    return x == threshold, -abs(x - threshold) / scale if x != threshold else 1.0


def resolve_alternative(
    profile: dict[str, Any],
    outer_alias: str,
    alternative: str,
) -> tuple[str, str, Any]:
    """Resolve an OR branch to its own alias, expression, and value.

    Examples:
    - outer VAL with "<0.35" uses VAL;
    - outer VAL with "FP>0.45" uses FP;
    - outer peak_objects with "final_mass<=0" uses final_mass.
    """
    named = _NAMED_TERM.match(alternative)
    if named:
        branch_alias, op, raw = named.groups()
        normalized_expression = f"{op}{raw}"
        return (
            branch_alias,
            normalized_expression,
            value_for(profile, branch_alias),
        )
    return (
        outer_alias,
        alternative,
        value_for(profile, outer_alias),
    )


def evaluate_constraint(
    profile: dict[str, Any],
    alias: str,
    expression: str,
) -> tuple[bool, float]:
    alternatives = [x.strip() for x in re.split(r"\s+or\s+", expression)]
    evaluations = []
    for part in alternatives:
        _, normalized, value = resolve_alternative(profile, alias, part)
        evaluations.append(term_margin(value, normalized))
    satisfied = any(ok for ok, _ in evaluations)
    return satisfied, max(margin for _, margin in evaluations)


def constraint_diagnostic(
    profile: dict[str, Any],
    alias: str,
    expression: str,
) -> dict[str, Any]:
    alternatives = [x.strip() for x in re.split(r"\s+or\s+", expression)]
    evaluations: list[dict[str, Any]] = []
    for part in alternatives:
        branch_alias, normalized, value = resolve_alternative(
            profile, alias, part
        )
        ok, margin = term_margin(value, normalized)
        evaluations.append({
            "alias": branch_alias,
            "field": ALIASES.get(branch_alias, branch_alias),
            "value": value,
            "expression": part,
            "normalized_expression": normalized,
            "satisfied": ok,
            "margin": round(margin, 6),
        })

    best = max(evaluations, key=lambda item: item["margin"])
    return {
        "alias": alias,
        "field": ALIASES.get(alias, alias),
        "value": value_for(profile, alias),
        "expression": expression,
        "satisfied": any(item["satisfied"] for item in evaluations),
        "margin": best["margin"],
        "deficit": round(max(0.0, -float(best["margin"])), 6),
        "winning_alternative_alias": best["alias"],
        "alternatives": evaluations,
    }


def evaluate_target(
    profile: dict[str, Any],
    constraints: dict[str, Any],
) -> tuple[bool, float, list[dict[str, Any]], int, float]:
    diagnostics = [
        constraint_diagnostic(profile, alias, ss(expression))
        for alias, expression in constraints.items()
    ]
    failed = [item for item in diagnostics if not item["satisfied"]]
    exact = not failed
    total_deficit = round(
        sum(float(item["deficit"]) for item in failed),
        6,
    )
    if exact:
        target_margin = min(
            (float(item["margin"]) for item in diagnostics),
            default=1.0,
        )
    else:
        # A negative aggregate distance remains backward-compatible with the
        # previous target_margin convention, while diagnostics preserve the
        # reason for the miss.
        target_margin = -total_deficit
    return (
        exact,
        round(target_margin, 6),
        diagnostics,
        len(failed),
        total_deficit,
    )


def member(
    profile: dict[str, Any],
    family_map: dict[str, str],
    category_map: dict[str, str],
    margin: float = 0.0,
    failed_constraint_count: int = 0,
    total_deficit: float = 0.0,
    failed_constraints: list[str] | None = None,
) -> CohortMember:
    rid = rule_id(profile.get("rule"))
    return CohortMember(
        rule=rid,
        experiment_id=ss(profile.get("experiment_id")),
        source_file=ss(profile.get("source_file")),
        family=family_map.get(rid, "Unknown"),
        analyzer_category=category_map.get(
            rid, ss(profile.get("analyzer_category"))
        ),
        final_tick=int(sf(profile.get("final_tick"))),
        collapsed=collapsed(profile),
        emg=round(sf(profile.get("emergence_score")), 6),
        val=round(sf(profile.get("validation_quality")), 6),
        know=round(sf(profile.get("knowledge_score")), 6),
        fb=round(sf(profile.get("feedback_score")), 6),
        civ=round(sf(profile.get("civilization_score")), 6),
        stability=round(sf(profile.get("stability_index")), 6),
        effective_risk=round(
            sf(profile.get("feedback_effective_risk")), 6
        ),
        target_margin=round(margin, 6),
        failed_constraint_count=int(failed_constraint_count),
        total_deficit=round(total_deficit, 6),
        failed_constraints=list(failed_constraints or []),
    )


def scaled_distance(field: str, a: Any, b: Any) -> float:
    x, y = sf(a), sf(b)
    if field in LOG_FEATURES:
        return abs(math.log1p(max(0.0, x)) - math.log1p(max(0.0, y))) / 12.0
    return abs(x - y)


def profile_distance(
    a: dict[str, Any],
    b: dict[str, Any],
    excluded: set[str],
) -> float:
    distances = [
        scaled_distance(field, a.get(field), b.get(field))
        for field in MATCH_FEATURES
        if field not in excluded
    ]
    return sum(distances) / max(1, len(distances))


def lookup(
    matrix: dict[str, dict[str, float]],
    left: str,
    right: str,
) -> float | None:
    if right in matrix.get(left, {}):
        return matrix[left][right]
    if left in matrix.get(right, {}):
        return matrix[right][left]
    return None


def pair_score(
    target: dict[str, Any],
    control: dict[str, Any],
    claim_id: str,
    family_map: dict[str, str],
    templates: dict[str, str],
    combined: dict[str, dict[str, float]],
    behaviour: dict[str, dict[str, float]],
    dynamic: dict[str, dict[str, float]],
) -> MatchPair:
    left = rule_id(target.get("rule"))
    right = rule_id(control.get("rule"))
    excluded = NON_MATCH_FEATURES_BY_CLAIM.get(claim_id, set())
    pd = profile_distance(target, control, excluded)
    md = lookup(combined, left, right)
    bd = lookup(behaviour, left, right)
    dd = lookup(dynamic, left, right)
    same_family = (
        family_map.get(left, "Unknown") == family_map.get(right, "Unknown")
    )
    same_template = (
        bool(templates.get(left))
        and templates.get(left) == templates.get(right)
    )

    components = [(pd, 0.50)]
    if md is not None:
        components.append((md, 0.20))
    if bd is not None:
        components.append((bd, 0.15))
    if dd is not None:
        components.append((dd, 0.15))
    weighted = sum(value * weight for value, weight in components)
    total_weight = sum(weight for _, weight in components)
    distance = weighted / total_weight
    if same_family:
        distance *= 0.88
    if same_template:
        distance *= 0.92
    score = max(0.0, min(1.0, 1.0 - distance))

    reason_bits = [
        f"profile={pd:.3f}",
        f"family={'same' if same_family else 'different'}",
    ]
    if md is not None:
        reason_bits.append(f"combined_morph={md:.3f}")
    if bd is not None:
        reason_bits.append(f"behaviour={bd:.3f}")
    if dd is not None:
        reason_bits.append(f"dynamic={dd:.3f}")
    if same_template:
        reason_bits.append("same_template")

    return MatchPair(
        target_rule=left,
        control_rule=right,
        score=round(score, 6),
        profile_distance=round(pd, 6),
        morphology_distance=None if md is None else round(md, 6),
        behaviour_distance=None if bd is None else round(bd, 6),
        dynamic_distance=None if dd is None else round(dd, 6),
        same_family=same_family,
        same_template_category=same_template,
        reason=", ".join(reason_bits),
    )


def make_matches(
    targets: list[dict[str, Any]],
    controls: list[dict[str, Any]],
    claim_id: str,
    family_map: dict[str, str],
    templates: dict[str, str],
    combined: dict[str, dict[str, float]],
    behaviour: dict[str, dict[str, float]],
    dynamic: dict[str, dict[str, float]],
    limit: int,
) -> list[MatchPair]:
    pairs: list[MatchPair] = []
    used_controls: set[str] = set()
    for target in targets:
        candidates = [
            pair_score(
                target, control, claim_id, family_map, templates,
                combined, behaviour, dynamic,
            )
            for control in controls
            if rule_id(control.get("rule")) != rule_id(target.get("rule"))
            and rule_id(control.get("rule")) not in used_controls
        ]
        candidates.sort(key=lambda x: (-x.score, x.control_rule))
        if candidates:
            best = candidates[0]
            used_controls.add(best.control_rule)
            pairs.append(best)
        if len(pairs) >= limit:
            break
    return pairs


def gp102_quadrants(
    profiles: list[dict[str, Any]],
    family_map: dict[str, str],
    category_map: dict[str, str],
) -> dict[str, Any]:
    profiles = [
        profile
        for profile in profiles
        if ss(
            profile.get("feedback_metric_independence_status")
        ).upper() == "STRUCTURALLY_INDEPENDENT_V2"
    ]
    definitions = {
        "high_know_high_fb": lambda p: sf(p.get("knowledge_score")) >= 0.65
                                     and sf(p.get("feedback_score")) >= 0.65,
        "high_know_low_fb": lambda p: sf(p.get("knowledge_score")) >= 0.65
                                    and sf(p.get("feedback_score")) < 0.20,
        "low_know_high_fb": lambda p: sf(p.get("knowledge_score")) < 0.20
                                    and sf(p.get("feedback_score")) >= 0.65,
        "low_know_low_fb": lambda p: sf(p.get("knowledge_score")) < 0.20
                                   and sf(p.get("feedback_score")) < 0.20,
    }
    result: dict[str, Any] = {}
    for name, predicate in definitions.items():
        selected = [p for p in profiles if predicate(p)]
        result[name] = {
            "count": len(selected),
            "members": [
                asdict(member(p, family_map, category_map))
                for p in selected
            ],
        }
    return result


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ARCHON Cohort Report v1.1.1",
        "",
        f"- Created: `{report['generated_at']}`",
        f"- Representative rules: **{report['representative_rule_count']}**",
        f"- Atlas families available: **{report['source_coverage']['atlas_families']}**",
        f"- Behaviour matrix rules: **{report['source_coverage']['behaviour_matrix_rules']}**",
        f"- Dynamic matrix rules: **{report['source_coverage']['dynamic_matrix_rules']}**",
        "",
        "## GP-102 knowledge / feedback quadrants",
        "",
        "| Cohort | Count |",
        "| --- | ---: |",
    ]
    for name, info in report["gp102_quadrants"].items():
        lines.append(f"| `{name}` | {info['count']} |")

    lines += ["", "## Scientific target coverage", ""]
    for claim in report["claims"]:
        lines += [
            f"### {claim['claim_id']}: {claim['title']}",
            "",
            "| Target regime | Exact | Near | Status |",
            "| --- | ---: | ---: | --- |",
        ]
        for target in claim["targets"]:
            lines.append(
                f"| `{target['name']}` | {target['exact_count']} | "
                f"{target['near_count']} | **{target['status']}** |"
            )
            if target.get("applied_calibration"):
                calibration = ", ".join(
                    f"`{alias} {expression}`"
                    for alias, expression in
                    target["applied_calibration"].items()
                )
                lines += [
                    "",
                    f"Applied calibration: {calibration}",
                    "",
                ]
            if target["exact_members"]:
                rules = ", ".join(
                    f"`{x['rule']}`" for x in target["exact_members"][:12]
                )
                lines += ["", f"Exact members: {rules}", ""]
            elif target["near_members"]:
                rules = ", ".join(
                    f"`{x['rule']}` ({x['target_margin']:.3f}; "
                    f"failed={x['failed_constraint_count']})"
                    for x in target["near_members"][:8]
                )
                lines += ["", f"Closest candidates: {rules}", ""]
                lines += [
                    "| Rule | Failed constraints | Total deficit |",
                    "| --- | --- | ---: |",
                ]
                for item in target["near_members"][:8]:
                    failed = ", ".join(item.get("failed_constraints") or []) or "-"
                    lines.append(
                        f"| `{item['rule']}` | {failed} | "
                        f"{item.get('total_deficit', 0.0):.3f} |"
                    )
                lines.append("")
            if target["matched_pairs"]:
                lines += [
                    "| Target | Matched control | Match score | Reason |",
                    "| --- | --- | ---: | --- |",
                ]
                for pair in target["matched_pairs"][:10]:
                    lines.append(
                        f"| `{pair['target_rule']}` | `{pair['control_rule']}` | "
                        f"{pair['score']:.3f} | {pair['reason']} |"
                    )
                lines.append("")

    lines += [
        "## Interpretation",
        "",
        "An exact empty cohort means the required regime is absent from the "
        "current representative dataset. Near candidates are ranked by their "
        "distance to the claim boundary. Matching deliberately excludes the "
        "claim variables themselves, reducing circular control selection.",
        "",
    ]
    return "\n".join(lines)


def build_report(
    results: Path,
    root: Path,
    atlas_path: Path,
    similar_path: Path,
    behaviour_path: Path,
    dynamic_path: Path,
    template_path: Path,
    near_limit: int,
    match_limit: int,
) -> dict[str, Any]:
    profile_payload = load_json(results / "observer_profiles_v30.json", {})
    profiles = representative_profiles(profile_payload)
    atlas = load_json(atlas_path, {})
    family_map, category_map = atlas_maps(atlas)
    combined = combined_map(load_json(similar_path, {}))
    behaviour = matrix_map(load_json(behaviour_path, {}))
    dynamic = matrix_map(load_json(dynamic_path, {}))
    templates = template_categories(load_json(template_path, {}))

    claims: list[dict[str, Any]] = []
    target_queue: list[dict[str, Any]] = []

    for claim_id, spec in CLAIM_SPECS.items():
        target_reports: list[dict[str, Any]] = []
        claim_targets = list(TARGETS.get(claim_id, []))
        for target in claim_targets:
            target_name = ss(target.get("name"))
            declared_constraints = target.get("constraints", {})
            constraints, applied_calibration = calibrated_constraints(
                claim_id,
                target_name,
                declared_constraints,
            )
            scored: list[dict[str, Any]] = []
            for profile in profiles:
                (
                    exact,
                    margin,
                    diagnostics,
                    failed_count,
                    total_deficit,
                ) = evaluate_target(profile, constraints)
                scored.append({
                    "profile": profile,
                    "margin": margin,
                    "exact": exact,
                    "diagnostics": diagnostics,
                    "failed_count": failed_count,
                    "total_deficit": total_deficit,
                    "failed_constraints": [
                        item["alias"]
                        for item in diagnostics
                        if not item["satisfied"]
                    ],
                })

            exact_profiles = [
                item["profile"] for item in scored if item["exact"]
            ]
            near_profiles = [
                item for item in scored if not item["exact"]
            ]
            # Prefer candidates that fail fewer target conditions. Within that
            # group, prefer the smallest aggregate deficit. This prevents a
            # failed boolean condition from flattening every candidate to the
            # same rank.
            near_profiles.sort(
                key=lambda item: (
                    int(item["failed_count"]),
                    float(item["total_deficit"]),
                    -float(item["margin"]),
                    rule_id(item["profile"].get("rule")),
                )
            )
            near_profiles = near_profiles[:near_limit]

            # Controls are profiles outside the target regime. Matching does
            # not use the variables that define the claim.
            controls = [
                item["profile"] for item in scored if not item["exact"]
            ]
            matched_pairs = make_matches(
                exact_profiles,
                controls,
                claim_id,
                family_map,
                templates,
                combined,
                behaviour,
                dynamic,
                match_limit,
            )

            if exact_profiles:
                status = "EXACT_COHORT_AVAILABLE"
            elif (
                near_profiles
                and near_profiles[0]["failed_count"] <= 1
                and near_profiles[0]["total_deficit"] <= 0.15
            ):
                status = "NEAR_COHORT_ONLY"
            else:
                status = "MISSING_REGIME"

            entry = {
                "name": target_name,
                "declared_constraints": declared_constraints,
                "constraints": constraints,
                "applied_calibration": applied_calibration,
                "status": status,
                "exact_count": len(exact_profiles),
                "near_count": len(near_profiles),
                "exact_members": [
                    asdict(member(
                        item["profile"],
                        family_map,
                        category_map,
                        item["margin"],
                        item["failed_count"],
                        item["total_deficit"],
                        item["failed_constraints"],
                    ))
                    for item in scored
                    if item["exact"]
                ],
                "near_members": [
                    {
                        **asdict(member(
                            item["profile"],
                            family_map,
                            category_map,
                            item["margin"],
                            item["failed_count"],
                            item["total_deficit"],
                            item["failed_constraints"],
                        )),
                        "constraint_diagnostics": item["diagnostics"],
                    }
                    for item in near_profiles
                ],
                "matched_pairs": [asdict(x) for x in matched_pairs],
            }
            target_reports.append(entry)
            target_queue.append({
                "claim_id": claim_id,
                "target_name": entry["name"],
                "declared_constraints": declared_constraints,
                "constraints": constraints,
                "applied_calibration": applied_calibration,
                "status": status,
                "exact_count": entry["exact_count"],
                "exact_rules": [
                    x["rule"] for x in entry["exact_members"]
                ],
                "best_near_rules": [
                    x["rule"] for x in entry["near_members"][:5]
                ],
                "best_near_candidates": [
                    {
                        "rule": x["rule"],
                        "target_margin": x["target_margin"],
                        "failed_constraint_count": x[
                            "failed_constraint_count"
                        ],
                        "total_deficit": x["total_deficit"],
                        "failed_constraints": x["failed_constraints"],
                        "constraint_diagnostics": x.get(
                            "constraint_diagnostics", []
                        ),
                    }
                    for x in entry["near_members"][:5]
                ],
                "recommended_search_mode": "cohort_target",
                "recommended_mutation_mode": "cohort_directed",
                "priority": (
                    1 if status == "MISSING_REGIME"
                    else 2 if status == "NEAR_COHORT_ONLY"
                    else 3
                ),
            })

        claims.append({
            "claim_id": claim_id,
            "title": spec.title,
            "family": spec.family,
            "interpretation": spec.interpretation,
            "targets": target_reports,
        })

    return {
        "schema": SCHEMA,
        "version": VERSION,
        "generated_at": now_iso(),
        "results_folder": str(results),
        "analysis_root": str(root),
        "representative_rule_count": len(profiles),
        "source_coverage": {
            "atlas_families": len(family_map),
            "combined_similarity_rules": len(combined),
            "behaviour_matrix_rules": len(behaviour),
            "dynamic_matrix_rules": len(dynamic),
            "template_rules": len(templates),
        },
        "gp102_quadrants": gp102_quadrants(
            profiles, family_map, category_map
        ),
        "gp102_metric_contract": {
            "required_feedback_metric": "STRUCTURALLY_INDEPENDENT_V2",
            "eligible_profile_count": sum(
                1
                for profile in profiles
                if ss(
                    profile.get("feedback_metric_independence_status")
                ).upper() == "STRUCTURALLY_INDEPENDENT_V2"
            ),
        },
        "claims": claims,
        "target_queue": sorted(
            target_queue,
            key=lambda x: (x["priority"], x["claim_id"], x["target_name"]),
        ),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=VERSION)
    parser.add_argument("results_folder", nargs="?")
    parser.add_argument("--root")
    parser.add_argument("--atlas")
    parser.add_argument("--similar")
    parser.add_argument("--behaviour-matrix")
    parser.add_argument("--dynamic-matrix")
    parser.add_argument("--template-map")
    parser.add_argument("--json-out")
    parser.add_argument("--md-out")
    parser.add_argument("--targets-out")
    parser.add_argument("--near-limit", type=int, default=12)
    parser.add_argument("--match-limit", type=int, default=12)
    args = parser.parse_args(argv)

    results = resolve_results_dir(args.results_folder)
    root = (
        Path(args.root).expanduser().resolve()
        if args.root else analysis_results_dir().resolve()
    )
    knowledge = knowledge_atlas_dir().resolve()

    atlas_path = Path(args.atlas).expanduser().resolve() if args.atlas else (
        knowledge / "research_atlas.json"
    )
    similar_path = Path(args.similar).expanduser().resolve() if args.similar else (
        results / "similar_worlds.json"
    )
    behaviour_path = (
        Path(args.behaviour_matrix).expanduser().resolve()
        if args.behaviour_matrix
        else results / "morphology_behaviour_distance_matrix.json"
    )
    dynamic_path = (
        Path(args.dynamic_matrix).expanduser().resolve()
        if args.dynamic_matrix
        else results / "morphology_dynamic_distance_matrix.json"
    )
    template_path = (
        Path(args.template_map).expanduser().resolve()
        if args.template_map
        else results / "template_rule_map.json"
    )

    report = build_report(
        results=results,
        root=root,
        atlas_path=atlas_path,
        similar_path=similar_path,
        behaviour_path=behaviour_path,
        dynamic_path=dynamic_path,
        template_path=template_path,
        near_limit=max(1, args.near_limit),
        match_limit=max(1, args.match_limit),
    )

    json_out = Path(args.json_out).expanduser().resolve() if args.json_out else (
        root / "cohort_report.json"
    )
    md_out = Path(args.md_out).expanduser().resolve() if args.md_out else (
        root / "cohort_report.md"
    )
    targets_out = (
        Path(args.targets_out).expanduser().resolve()
        if args.targets_out else root / "cohort_targets.json"
    )

    write_json(json_out, report)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(render_markdown(report), encoding="utf-8")
    write_json(targets_out, {
        "schema": "archon_cohort_targets_v1_1_1",
        "generated_at": report["generated_at"],
        "targets": report["target_queue"],
    })

    print(f"[cohort] representative rules: {report['representative_rule_count']}")
    print(f"[cohort] JSON: {json_out}")
    print(f"[cohort] Markdown: {md_out}")
    print(f"[cohort] targets: {targets_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

