#!/usr/bin/env python3
"""Cross-stage integrity audit for the active ARCHON scientific view."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.scientific_view_adapter import (
    SCIENTIFIC_VIEW_SCHEMA,
    eligible_profiles,
    evidence_rule_set,
    rule_set,
    scientific_atlas_records,
)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def audit(results: Path, analysis: Path, knowledge: Path) -> dict[str, Any]:
    profiles = eligible_profiles(results)
    profile_rules = rule_set(profiles)
    evidence = load_json(analysis / "evidence_report.json")
    evidence_rules = evidence_rule_set(evidence)
    atlas = load_json(knowledge / "research_atlas.json")
    atlas_rules = rule_set(scientific_atlas_records(atlas))
    principles = load_json(analysis / "general_principles.json").get(
        "principles", []
    )
    consensus = load_json(analysis / "consensus_report.json").get(
        "principles", []
    )
    meta = load_json(analysis / "meta_science_report.json")
    director = load_json(analysis / "research_director_report.json")

    issues: list[dict[str, Any]] = []

    def compare(label: str, actual: set[str], expected: set[str]) -> None:
        if actual != expected:
            issues.append({
                "code": f"{label}_RULE_SET_MISMATCH",
                "expected_count": len(expected),
                "actual_count": len(actual),
                "missing_rules": sorted(expected - actual),
                "extra_rules": sorted(actual - expected),
            })

    compare("EVIDENCE", evidence_rules, profile_rules)
    compare("ATLAS", atlas_rules, profile_rules)

    expected_count = len(profile_rules)
    evidence_claims = {
        str(claim.get("id")): claim
        for claim in evidence.get("claims", [])
        if isinstance(claim, dict) and claim.get("id")
    }
    claim_ids = set(evidence_claims)
    claim_eligible_counts = {
        claim_id: sum(
            1
            for case in claim.get("cases", [])
            if isinstance(case, dict)
            and str(case.get("status") or "") != "unavailable"
        )
        for claim_id, claim in evidence_claims.items()
    }
    claim_unavailable_counts = {
        claim_id: sum(
            1
            for case in claim.get("cases", [])
            if isinstance(case, dict)
            and str(case.get("status") or "") == "unavailable"
        )
        for claim_id, claim in evidence_claims.items()
    }
    for principle in principles if isinstance(principles, list) else []:
        if not isinstance(principle, dict):
            continue
        total = principle.get("total_unique_rules")
        if total is not None and int(total) != expected_count:
            issues.append({
                "code": "GENERAL_PRINCIPLE_DENOMINATOR_MISMATCH",
                "principle_id": principle.get("id"),
                "expected": expected_count,
                "actual": int(total),
            })
        if str(principle.get("id")) in claim_ids:
            principle_id = str(principle.get("id"))
            case_total = (
                int(principle.get("support") or 0)
                + int(principle.get("counterexamples") or 0)
                + int(principle.get("neutral") or 0)
            )
            expected_cases = claim_eligible_counts.get(
                principle_id, expected_count
            )
            if case_total != expected_cases:
                issues.append({
                    "code": "GENERAL_PRINCIPLE_CASE_COUNT_MISMATCH",
                    "principle_id": principle_id,
                    "expected": expected_cases,
                    "actual": case_total,
                })

    for principle in consensus if isinstance(consensus, list) else []:
        if not isinstance(principle, dict):
            continue
        principle_id = str(principle.get("id") or "")
        actual = int(principle.get("total_observations") or 0)
        expected_observations = claim_eligible_counts.get(
            principle_id, expected_count
        )
        if actual != expected_observations:
            issues.append({
                "code": "CONSENSUS_OBSERVATION_COUNT_MISMATCH",
                "principle_id": principle_id,
                "expected": expected_observations,
                "actual": actual,
            })

    meta_view = meta.get("scientific_view", {})
    if int(meta_view.get("rule_count") or 0) != expected_count:
        issues.append({
            "code": "META_SCIENCE_RULE_COUNT_MISMATCH",
            "expected": expected_count,
            "actual": int(meta_view.get("rule_count") or 0),
        })
    if meta_view.get("profile_evidence_match") is not True:
        issues.append({"code": "META_SCIENCE_PROFILE_EVIDENCE_MISMATCH"})

    if int(director.get("rules") or 0) != expected_count:
        issues.append({
            "code": "DIRECTOR_RULE_COUNT_MISMATCH",
            "expected": expected_count,
            "actual": int(director.get("rules") or 0),
        })
    if int(director.get("profiles") or 0) != len(profiles):
        issues.append({
            "code": "DIRECTOR_PROFILE_COUNT_MISMATCH",
            "expected": len(profiles),
            "actual": int(director.get("profiles") or 0),
        })

    return {
        "schema": "archon_scientific_view_integrity_v1",
        "generated": datetime.now(timezone.utc).replace(
            microsecond=0
        ).isoformat(),
        "status": "PASS" if not issues else "FAIL",
        "scientific_view_schema": SCIENTIFIC_VIEW_SCHEMA,
        "profile_count": len(profiles),
        "rule_count": expected_count,
        "checks": {
            "profile_rules": len(profile_rules),
            "evidence_rules": len(evidence_rules),
            "atlas_rules": len(atlas_rules),
            "general_principles": len(principles)
            if isinstance(principles, list) else 0,
            "consensus_principles": len(consensus)
            if isinstance(consensus, list) else 0,
            "claim_eligible_counts": claim_eligible_counts,
            "claim_unavailable_counts": claim_unavailable_counts,
            "director_rules": int(director.get("rules") or 0),
        },
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results")
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--knowledge-root", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = audit(
        Path(args.results).resolve(),
        Path(args.analysis_root).resolve(),
        Path(args.knowledge_root).resolve(),
    )
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"Scientific View Integrity: {report['status']} | "
        f"rules={report['rule_count']} | issues={report['issue_count']}"
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
