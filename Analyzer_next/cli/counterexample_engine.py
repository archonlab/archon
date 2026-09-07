#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Universe Search Counterexample Engine v1.1

Reads observer_profiles_v30.json and audits the principle tests defined by
Evidence Engine. It separates:
- confirmed counterexamples already present in the dataset;
- near-counterexamples that almost violate a claim;
- missing counterexample regimes that should be targeted by future search.

Writes:
- counterexample_report.json
- counterexample_report.md
- counterexample_targets.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from archon_paths import ANALYSIS_RESULTS_DIR, PROJECT_ROOT, SEARCH_RESULTS_DIR

def analysis_results_dir() -> Path:
    return ANALYSIS_RESULTS_DIR

def default_results_dir() -> Path:
    return SEARCH_RESULTS_DIR

def resolve_results_dir(value=None) -> Path:
    if value is None or not str(value).strip(): return SEARCH_RESULTS_DIR.resolve()
    raw=Path(value).expanduser(); candidates=[raw] if raw.is_absolute() else [Path.cwd()/raw, PROJECT_ROOT/raw, SEARCH_RESULTS_DIR/raw]
    for candidate in candidates:
        if candidate.exists(): return candidate.resolve()
    checked="\n".join(f"  - {p}" for p in candidates)
    raise FileNotFoundError(f"Results folder not found: {value}\nChecked:\n{checked}")


from Analyzer_next.core.scientific_claims import (
    CLAIMS,
    CLAIM_SPECS,
    POTENTIAL,
    TARGETS,
    sf,
    si,
    ss,
)




@dataclass
class Candidate:
    rule: str
    score: float
    reason: str
    emg: float
    val: float
    know: float
    fb: float
    civ: float
    source_file: str
    matched_regimes: list[str] | None = None


@dataclass
class Audit:
    id: str
    title: str
    confirmed_count: int
    near_count: int
    coverage_status: str
    regime_coverage_status: str
    confirmed: list[Candidate]
    near_candidates: list[Candidate]
    covered_regimes: list[str]
    missing_regimes: list[str]
    target_coverage: list[dict[str, Any]]
    search_targets: list[dict[str, Any]]



TARGET_ALIASES = {
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
    "peak_objects": "peak_objects",
    "final_mass": "final_mass",
    "longest_age": "longest_age",
}


def profile_value(profile: dict[str, Any], alias: str) -> Any:
    key = TARGET_ALIASES.get(alias, alias)
    if alias == "collapsed":
        if profile.get("collapse_tick") is not None:
            return True
        category = ss(profile.get("analyzer_category")).lower()
        warnings = {ss(x).lower() for x in profile.get("warnings", [])}
        return category == "collapsed_world" or "collapsed" in warnings
    return profile.get(key)


def _compare(value: Any, operator: str, threshold: float) -> bool:
    number = sf(value, float("nan"))
    if number != number:
        return False
    if operator == ">=":
        return number >= threshold
    if operator == "<=":
        return number <= threshold
    if operator == ">":
        return number > threshold
    if operator == "<":
        return number < threshold
    if operator == "==":
        return number == threshold
    return False


def evaluate_target_expression(
    profile: dict[str, Any],
    default_alias: str,
    expression: Any,
) -> bool:
    if isinstance(expression, bool):
        return bool(profile_value(profile, default_alias)) is expression
    text = ss(expression).strip()
    clauses = [part.strip() for part in text.split(" or ")]
    for clause in clauses:
        match = re.fullmatch(
            r"(?:(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\s*)?"
            r"(?P<op>>=|<=|==|>|<)\s*"
            r"(?P<number>-?\d+(?:\.\d+)?)",
            clause,
        )
        if not match:
            continue
        alias = match.group("alias") or default_alias
        if _compare(
            profile_value(profile, alias),
            match.group("op"),
            float(match.group("number")),
        ):
            return True
    return False


def profile_matches_target(
    profile: dict[str, Any],
    target: dict[str, Any],
) -> bool:
    constraints = target.get("constraints", {})
    if not isinstance(constraints, dict):
        return False
    return all(
        evaluate_target_expression(profile, ss(alias), expression)
        for alias, expression in constraints.items()
    )


def load_profiles(results: Path) -> list[dict[str, Any]]:
    path = results / "observer_profiles_v30.json"
    if not path.exists():
        raise SystemExit(f"observer_profiles_v30.json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    profiles = data.get("profiles", [])
    if not isinstance(profiles, list):
        raise SystemExit("Invalid observer_profiles_v30.json: profiles is not a list")
    return profiles


def base_candidate(
    p: dict[str, Any],
    score: float,
    reason: str,
    matched_regimes: list[str] | None = None,
) -> Candidate:
    rule_raw = ss(p.get("rule"), "")
    rule = rule_raw.zfill(5) if rule_raw else "unknown"
    return Candidate(
        rule=rule,
        score=round(max(0.0, min(1.0, score)), 4),
        reason=reason,
        emg=round(sf(p.get("emergence_score")), 4),
        val=round(sf(p.get("validation_quality")), 4),
        know=round(sf(p.get("knowledge_score")), 4),
        fb=round(sf(p.get("feedback_score")), 4),
        civ=round(sf(p.get("civilization_score")), 4),
        source_file=ss(p.get("source_file"), ""),
        matched_regimes=matched_regimes or [],
    )


# ---------------------------------------------------------------------------
# Near-counterexample scoring and search targets
# ---------------------------------------------------------------------------
#
# Imported from scientific_claims.py so Evidence Engine and Counterexample
# Engine use the same claim definitions, contradiction logic, and target
# regimes.
#
def build_audits(profiles: list[dict[str, Any]], near_limit: int) -> list[Audit]:
    audits: list[Audit] = []
    for cid, title, _description, test_fn in CLAIMS:
        targets = TARGETS.get(cid, [])
        target_profiles: dict[str, list[dict[str, Any]]] = {
            ss(target.get("name")): [] for target in targets
        }
        confirmed: list[Candidate] = []
        near: list[Candidate] = []

        for p in profiles:
            status, strength, reason = test_fn(p)
            if status == "counterexample":
                matched = []
                for target in targets:
                    name = ss(target.get("name"))
                    if name and profile_matches_target(p, target):
                        matched.append(name)
                        target_profiles[name].append(p)
                confirmed.append(
                    base_candidate(p, strength, reason, matched)
                )
            elif status == "neutral":
                score, near_reason = POTENTIAL[cid](p)
                if score >= 0.08:
                    near.append(base_candidate(p, score, near_reason))

        confirmed.sort(key=lambda x: (-x.score, x.rule))
        near.sort(key=lambda x: (-x.score, x.rule))

        target_coverage = []
        covered = []
        for target in targets:
            name = ss(target.get("name"))
            members = target_profiles.get(name, [])
            rules = sorted({
                ss(p.get("rule")).zfill(5)
                for p in members
                if ss(p.get("rule"))
            })
            is_covered = bool(members)
            if is_covered:
                covered.append(name)
            target_coverage.append({
                "name": name,
                "status": "COVERED" if is_covered else "MISSING",
                "confirmed_count": len(members),
                "confirmed_rules": rules,
                "constraints": dict(target.get("constraints", {})),
            })

        missing = [
            ss(target.get("name"))
            for target in targets
            if ss(target.get("name")) not in covered
        ]

        if confirmed:
            coverage = "COUNTEREXAMPLES_FOUND"
            if not missing:
                regime_coverage = "ALL_TARGET_REGIMES_COVERED"
            elif covered:
                regime_coverage = "PARTIAL_TARGET_REGIME_COVERAGE"
            else:
                regime_coverage = "UNCLASSIFIED_COUNTEREXAMPLES_FOUND"
        elif near:
            coverage = "NEAR_COUNTEREXAMPLES_ONLY"
            regime_coverage = "NO_TARGET_REGIME_CONFIRMED"
        else:
            coverage = "UNTESTED_REGIME"
            regime_coverage = "NO_TARGET_REGIME_CONFIRMED"

        audits.append(Audit(
            id=cid,
            title=title,
            confirmed_count=len(confirmed),
            near_count=len(near),
            coverage_status=coverage,
            regime_coverage_status=regime_coverage,
            confirmed=confirmed,
            near_candidates=near[:near_limit],
            covered_regimes=covered,
            missing_regimes=missing,
            target_coverage=target_coverage,
            search_targets=targets,
        ))
    return audits


def render_md(audits: list[Audit], profiles: list[dict[str, Any]], results: Path) -> str:
    lines = [
        "# Counterexample Audit v1.1", "",
        "This report actively searches for observations that violate or nearly violate current principle definitions.", "",
        "## Run metadata", "",
        f"- Created: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Results folder: `{results}`",
        f"- Unique profiles audited: **{len(profiles)}**", "",
        "## Summary", "",
        "| ID | Principle | Confirmed | Near candidates | Coverage |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for a in audits:
        lines.append(f"| {a.id} | {a.title} | {a.confirmed_count} | {a.near_count} | {a.coverage_status} |")
    lines += ["", "## Principle audits", ""]
    for a in audits:
        lines += [f"### {a.id}: {a.title}", "", f"- Coverage: **{a.coverage_status}**", f"- Regime coverage: **{a.regime_coverage_status}**", f"- Covered regimes: **{", ".join(a.covered_regimes) or "none"}**", f"- Missing regimes: **{", ".join(a.missing_regimes) or "none"}**", f"- Confirmed counterexamples: **{a.confirmed_count}**", f"- Near-counterexample candidates: **{a.near_count}**", ""]
        if a.confirmed:
            lines += ["#### Confirmed counterexamples", "", "| Rule | Score | Reason | EMG | VAL | KNOW | FB | CIV |", "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
            for c in a.confirmed[:20]:
                lines.append(f"| {c.rule} | {c.score:.3f} | {c.reason} [{", ".join(c.matched_regimes or []) or "unclassified"}] | {c.emg:.3f} | {c.val:.3f} | {c.know:.3f} | {c.fb:.3f} | {c.civ:.3f} |")
            lines.append("")
        if a.near_candidates:
            lines += ["#### Nearest candidates", "", "| Rule | Potential | Why it matters | EMG | VAL | KNOW | FB | CIV |", "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
            for c in a.near_candidates:
                lines.append(f"| {c.rule} | {c.score:.3f} | {c.reason} [{", ".join(c.matched_regimes or []) or "unclassified"}] | {c.emg:.3f} | {c.val:.3f} | {c.know:.3f} | {c.fb:.3f} | {c.civ:.3f} |")
            lines.append("")
        lines += ["#### Search targets", ""]
        for target in a.target_coverage:
            constraints = ", ".join(
                f"{k}={v}" for k, v in target["constraints"].items()
            )
            lines.append(
                f"- **{target['name']}**: `{constraints}` "
                f"=> **{target['status']}** "
                f"({target['confirmed_count']} confirmed)"
            )
        lines.append("")
    lines += ["## Interpretation", "", "A zero count is not positive evidence by itself. It can mean the violating regime has not been sampled. Near candidates are the best current worlds for stress tests, repeated seeds, or local mutations.", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit principles for counterexamples and near-counterexamples.")
    ap.add_argument(
        "results_folder",
        nargs="?",
        default=None,
        help="Raw Universe Search results folder. Default: Project ARCHON/Results/Universe_Search",
    )
    ap.add_argument(
        "--root",
        default=None,
        help="Output directory for counterexample reports. Default: Project ARCHON/Results/Analysis",
    )
    ap.add_argument("--near-limit", type=int, default=10)
    args = ap.parse_args()

    try:
        results = resolve_results_dir(args.results_folder)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    if args.root:
        raw_root = Path(args.root).expanduser()
        root = raw_root if raw_root.is_absolute() else PROJECT_ROOT / raw_root
        root = root.resolve()
    else:
        root = analysis_results_dir()
    root.mkdir(parents=True, exist_ok=True)
    profiles = load_profiles(results)
    audits = build_audits(profiles, max(1, args.near_limit))

    payload = {
        "schema": "counterexample_audit_v1_1",
        "created": datetime.now().isoformat(timespec="seconds"),
        "results_folder": str(results),
        "profile_count": len(profiles),
        "audits": [asdict(a) for a in audits],
    }
    targets_payload = {
        "schema": "counterexample_targets_v1_1",
        "created": payload["created"],
        "targets": [
            {
                "principle_id": a.id,
                "principle": a.title,
                "coverage_status": a.coverage_status,
                "regime_coverage_status": a.regime_coverage_status,
                "covered_regimes": a.covered_regimes,
                "missing_regimes": a.missing_regimes,
                "targets": [
                    target
                    for target in a.target_coverage
                    if target["status"] == "MISSING"
                ],
                "priority_rules": [c.rule for c in a.near_candidates[:5]],
            }
            for a in audits
        ],
    }

    (root / "counterexample_report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (root / "counterexample_report.md").write_text(render_md(audits, profiles, results), encoding="utf-8")
    (root / "counterexample_targets.json").write_text(json.dumps(targets_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 72)
    print("Universe Search Counterexample Engine v1.1")
    print("=" * 72)
    print(f"Profiles: {len(profiles)}")
    for a in audits:
        print(
            f"{a.id}: confirmed={a.confirmed_count} near={a.near_count} "
            f"coverage={a.coverage_status} "
            f"regimes={a.regime_coverage_status}"
        )
    print(f"Report:  {root / 'counterexample_report.md'}")
    print(f"Targets: {root / 'counterexample_targets.json'}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

