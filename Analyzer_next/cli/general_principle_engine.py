#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universe Search General Principle Engine v30

Reads:
- research_atlas.json
- theory_report.md (optional)
- mechanism_report_rule_*.md files from result folders (optional)

Writes:
- general_principles.md
- general_principles.json

v30 understands Atlas records produced from ObserverProfile v30:
- civilization_score / civilization_stage
- knowledge_score / knowledge_axis / knowledge_discoveries
- feedback_score / feedback_regime / feedback_self_direction
- emergence_score / emergence_confidence / emergence_evidence_count
- validation_quality / validation_grade / validation false-positive / false-negative risks

Goal:
Promote repeated single-world hypotheses into cross-rule candidate principles.

Usage:
    python general_principle_engine.py research_atlas.json --results ../universe_search_v23_results
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.scientific_view_adapter import scientific_atlas_records
from Analyzer_next.core.scientific_claims import CLAIM_SPECS


# -----------------------------------------------------------------------------
# Small safe helpers
# -----------------------------------------------------------------------------


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def norm_text(value: Any) -> str:
    return str(value or "").strip().upper()


def avg(values: Iterable[Any]) -> float:
    vals = [safe_float(v, None) for v in values]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def stars(score: int) -> str:
    score = max(1, min(5, int(score or 1)))
    return "★" * score + "☆" * (5 - score)


def is_high_conf(value: Any) -> bool:
    return norm_text(value) in {"HIGH", "VERY_HIGH"}


def is_very_high_conf(value: Any) -> bool:
    return norm_text(value) == "VERY_HIGH"


def has_v30_fields(e: dict[str, Any]) -> bool:
    keys = (
        "emergence_score",
        "validation_quality",
        "knowledge_score",
        "feedback_score",
        "civilization_score",
    )
    return any(k in e for k in keys)


# -----------------------------------------------------------------------------
# Confidence / status ladder
# -----------------------------------------------------------------------------


def confidence_from_support(support: int, counterexamples: int = 0, avg_validation: float = 0.0) -> str:
    """Conservative confidence ladder.

    With a tiny dataset, even good evidence remains LOW-MEDIUM. This prevents
    Analyzer from turning one cool world into a fake law with a golden hat.
    """
    if support >= 30 and counterexamples <= 2 and avg_validation >= 0.70:
        return "VERY_HIGH"
    if support >= 10 and counterexamples <= 1 and avg_validation >= 0.65:
        return "HIGH"
    if support >= 5 and counterexamples <= 1:
        return "MEDIUM-HIGH"
    if support >= 3 and counterexamples <= 2:
        return "MEDIUM"
    if support >= 2:
        return "LOW-MEDIUM"
    return "LOW"


def status_from_support(support: int, counterexamples: int = 0) -> str:
    if support >= 100 and counterexamples <= 5:
        return "General principle"
    if support >= 30 and counterexamples <= 3:
        return "General principle candidate"
    if support >= 10:
        return "Cross-rule principle candidate"
    if support >= 5:
        return "Strong recurring pattern"
    if support >= 2:
        return "Emerging multi-case pattern"
    return "Single-case principle seed"


def evidence_level(support: int) -> str:
    if support >= 100:
        return "general"
    if support >= 30:
        return "candidate_general"
    if support >= 10:
        return "cross_rule"
    if support >= 5:
        return "recurring"
    if support >= 2:
        return "multi_case_seed"
    if support >= 1:
        return "single_case"
    return "none"


# -----------------------------------------------------------------------------
# Mechanism report support, kept compatible with v29
# -----------------------------------------------------------------------------


def parse_mechanism_report(path: Path) -> dict[str, Any]:
    text = read_text(path)
    rule = None
    m = re.search(r"Rule:\s*\*\*(\d+)\*\*", text)
    if m:
        rule = m.group(1).zfill(5)
    else:
        m = re.search(r"mechanism_report_rule_(\d+)", path.name)
        if m:
            rule = m.group(1).zfill(5)

    scores: dict[str, float] = {}
    for label in [
        "Field memory",
        "Stochastic stability",
        "Oscillatory feedback",
        "Multi-scale feedback",
        "Genome complexity",
    ]:
        m = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*([0-9.]+)\s*\|", text)
        if m:
            scores[label.lower().replace(" ", "_")] = safe_float(m.group(1))

    mechanisms = []
    for m in re.finditer(r"###\s+(M-\d+):\s+(.+)", text):
        mechanisms.append({"id": m.group(1), "title": m.group(2).strip()})

    return {
        "rule": rule,
        "path": str(path),
        "scores": scores,
        "mechanisms": mechanisms,
    }


def collect_mechanism_reports(atlas_path: Path, explicit_results: list[Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    search_roots = [atlas_path.parent, *explicit_results]
    seen: set[Path] = set()
    for root in search_roots:
        if not root.exists():
            continue
        for p in root.rglob("mechanism_report_rule_*.md"):
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            try:
                reports.append(parse_mechanism_report(p))
            except Exception:
                pass
    return reports


# -----------------------------------------------------------------------------
# Principle building
# -----------------------------------------------------------------------------


def experiments_by_condition(experiments: list[dict[str, Any]], condition: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
    return [e for e in experiments if condition(e)]


def rule_list(experiments: list[dict[str, Any]]) -> list[str]:
    return [str(e.get("rule") or "?").zfill(5) for e in experiments]


def counter_rule_list(experiments: list[dict[str, Any]]) -> list[str]:
    return [str(e.get("rule") or "?").zfill(5) for e in experiments]


def unique_rules(experiments: list[dict[str, Any]]) -> set[str]:
    return {str(e.get("rule") or "?").zfill(5) for e in experiments}


def v30_summary(e: dict[str, Any]) -> str:
    return (
        f"rule {str(e.get('rule') or '?').zfill(5)}: "
        f"EMG={safe_float(e.get('emergence_score')):.3f} {e.get('emergence_confidence') or '-'}, "
        f"VAL={safe_float(e.get('validation_quality')):.3f} {e.get('validation_grade') or '-'}, "
        f"KNOW={safe_float(e.get('knowledge_score')):.3f}, "
        f"FB={safe_float(e.get('feedback_score')):.3f}, "
        f"CIV={safe_float(e.get('civilization_score')):.3f}"
    )


def build_principles(atlas: dict[str, Any], mechanism_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    experiments = scientific_atlas_records(atlas)
    v30 = [e for e in experiments if has_v30_fields(e)]
    principles: list[dict[str, Any]] = []
    total = len(experiments)
    total_unique_rules = len(unique_rules(experiments))

    def add(
        pid: str,
        name: str,
        claim: str,
        support_experiments: list[dict[str, Any]],
        evidence: list[str],
        next_test: str,
        impact: int = 4,
        counterexamples: list[dict[str, Any]] | None = None,
        mechanism_links: list[str] | None = None,
        family: str = "legacy",
    ) -> None:
        if not support_experiments:
            return
        counterexamples = counterexamples or []
        support = len(unique_rules(support_experiments))
        counter_count = len(unique_rules(counterexamples))
        avg_val = avg(e.get("validation_quality") for e in support_experiments)
        principles.append({
            "id": pid,
            "name": name,
            "family": family,
            "status": status_from_support(support, counter_count),
            "evidence_level": evidence_level(support),
            "confidence": confidence_from_support(support, counter_count, avg_val),
            "impact": impact,
            "support": support,
            "total_experiments": total,
            "total_unique_rules": total_unique_rules,
            "counterexamples": counter_count,
            "rules": sorted(unique_rules(support_experiments)),
            "counterexample_rules": sorted(unique_rules(counterexamples)),
            "average_validation": avg_val,
            "claim": claim,
            "evidence": evidence,
            "example_signals": [v30_summary(e) for e in support_experiments[:5]],
            "counterexample_signals": [v30_summary(e) for e in counterexamples[:5]],
            "mechanism_links": mechanism_links or [],
            "next_test": next_test,
        })

    # ------------------------------------------------------------------
    # Legacy principles retained for continuity
    # ------------------------------------------------------------------

    stable = experiments_by_condition(
        experiments,
        lambda e: safe_int(e.get("lifetime")) >= 100000
        and safe_float(e.get("dynamic_score")) >= 0.8
        and str(e.get("collapse") or "").lower() == "no",
    )
    if stable:
        add(
            "GP-001",
            "Persistence requires memory without disruptive noise",
            "Long-lived dynamic worlds may require strong state persistence and low random disruption.",
            stable,
            [
                f"{len(unique_rules(stable))} rule(s) survived >=100k ticks with dynamic score >=0.8 and no collapse.",
                "Mechanism reports can test whether those worlds share high field memory and stochastic stability.",
            ],
            "Compare all stable worlds against weak/transient worlds after at least 10 Atlas entries.",
            impact=5,
            mechanism_links=["M-001", "M-002"],
            family="legacy",
        )

    breathing = experiments_by_condition(experiments, lambda e: safe_float(e.get("breathing_score")) >= 0.7)
    if breathing:
        add(
            "GP-002",
            "Stable morphology may be dynamic replacement",
            "Some persistent morphologies may survive by replacing local components rather than becoming static.",
            breathing,
            [
                f"{len(unique_rules(breathing))} rule(s) have breathing score >=0.7.",
                "This supports the idea that stable-looking structures can remain internally active.",
            ],
            "Add event timeline autocorrelation and morphology snapshots to distinguish periodic, chaotic, and quasi-stable breathing.",
            impact=4,
            mechanism_links=["M-004"],
            family="legacy",
        )

    turnover = experiments_by_condition(
        experiments,
        lambda e: safe_int(e.get("objects")) > 0 and (safe_int(e.get("split_birth")) + safe_int(e.get("merge_death"))) >= 20,
    )
    if turnover:
        add(
            "GP-003",
            "Bounded object turnover suggests regulation",
            "A world that keeps object count bounded while split/merge events continue may contain a regulatory dynamic.",
            turnover,
            [
                f"{len(unique_rules(turnover))} rule(s) show bounded objects plus recurring split/merge events.",
                "This may separate structured ecology from runaway growth or dead fields.",
            ],
            "Add object lineage tracking to distinguish reproduction-like events from fragmentation.",
            impact=4,
            mechanism_links=["M-003", "M-004"],
            family="legacy",
        )

    families: dict[str, list[dict[str, Any]]] = {}
    for e in experiments:
        fam = e.get("family") or "Unclassified"
        families.setdefault(fam, []).append(e)
    for family_name, members in families.items():
        if family_name != "Unclassified" and members:
            add(
                f"GP-FAM-{family_name.upper().replace(' ', '-')[:20]}",
                f"{family_name} is a candidate behavioural family",
                f"The atlas currently groups {len(unique_rules(members))} rule(s) into the {family_name} family.",
                members,
                [
                    f"Family: {family_name}",
                    f"Rules: {', '.join(rule_list(members))}",
                ],
                "Add more experiments and compute similarity links to test whether this family is stable.",
                impact=3 if len(unique_rules(members)) == 1 else 4,
                family="legacy_family",
            )

    # ------------------------------------------------------------------
    # v30 cross-layer principles
    # ------------------------------------------------------------------

    credible_emergence = experiments_by_condition(
        v30,
        lambda e: safe_float(e.get("emergence_score")) >= 0.65
        and safe_float(e.get("validation_quality")) >= 0.70
        and is_high_conf(e.get("emergence_confidence"))
        and is_high_conf(e.get("validation_grade"))
        and safe_float(e.get("validation_false_positive_risk")) <= 0.20,
    )
    pattern_counterexamples = experiments_by_condition(
        v30,
        lambda e: safe_float(e.get("emergence_score")) < 0.20
        and safe_float(e.get("knowledge_score")) < 0.20
        and safe_float(e.get("feedback_score")) < 0.25
        and safe_float(e.get("civilization_score")) < 0.25,
    )
    if credible_emergence:
        add(
            "GP-101",
            "Validated emergence criterion",
            "High emergence evidence must be paired with high observer validation before a world is treated as a credible complex-organization candidate.",
            credible_emergence,
            [
                f"{len(unique_rules(credible_emergence))} supporting rule(s) have EMG>=0.65, VAL>=0.70, high confidence, and low false-positive risk.",
                f"Average EMG: {avg(e.get('emergence_score') for e in credible_emergence):.3f}.",
                f"Average VAL: {avg(e.get('validation_quality') for e in credible_emergence):.3f}.",
                f"Detected {len(unique_rules(pattern_counterexamples))} low-EMG pattern/world counterexample candidate(s) for contrast.",
            ],
            "Run at least 10 neighbouring rules and repeat 00252-like candidates to test whether EMG/VAL stay stable.",
            impact=5,
            counterexamples=[],
            family="v30_emergence",
        )

    independent_feedback = [
        entry
        for entry in v30
        if norm_text(
            entry.get("feedback_metric_independence_status")
        ) == "STRUCTURALLY_INDEPENDENT_V2"
    ]
    knowledge_feedback = experiments_by_condition(
        independent_feedback,
        lambda e: safe_float(e.get("knowledge_score")) >= 0.50
        and safe_float(e.get("feedback_score")) >= 0.50
        and safe_float(e.get("emergence_score")) >= 0.55,
    )
    k_without_fb = experiments_by_condition(
        independent_feedback,
        lambda e: safe_float(e.get("knowledge_score")) >= 0.50
        and safe_float(e.get("feedback_score")) < 0.25,
    )
    if knowledge_feedback:
        add(
            "GP-102",
            "Knowledge-feedback coupling",
            "Sustained emergence appears stronger when accumulated knowledge-like structure and adaptive feedback rise together.",
            knowledge_feedback,
            [
                f"{len(unique_rules(knowledge_feedback))} supporting rule(s) have KNOW>=0.50, FB>=0.50, and EMG>=0.55.",
                f"Average KNOW: {avg(e.get('knowledge_score') for e in knowledge_feedback):.3f}.",
                f"Average FB: {avg(e.get('feedback_score') for e in knowledge_feedback):.3f}.",
                f"Potential counterexamples with knowledge but weak feedback: {len(unique_rules(k_without_fb))}.",
            ],
            "Collect more rules where knowledge rises but feedback does not; check whether they fail to sustain high EMG.",
            impact=5,
            counterexamples=k_without_fb,
            family="v30_coupling",
        )

    self_regulating = experiments_by_condition(
        independent_feedback,
        lambda e: norm_text(e.get("feedback_regime")) in {"SELF_REGULATING", "ADAPTIVE_LOOP"}
        and safe_float(e.get("feedback_score")) >= 0.55
        and safe_float(e.get("validation_quality")) >= 0.55,
    )
    high_emg_low_fb = experiments_by_condition(
        independent_feedback,
        lambda e: safe_float(e.get("emergence_score")) >= 0.60
        and safe_float(e.get("feedback_score")) < 0.30,
    )
    if self_regulating:
        add(
            "GP-103",
            "Self-regulation marker",
            "Feedback regimes labelled SELF_REGULATING or ADAPTIVE_LOOP are candidate markers of systems where information begins to constrain future dynamics.",
            self_regulating,
            [
                f"{len(unique_rules(self_regulating))} supporting rule(s) have self-regulating feedback and non-trivial validation.",
                f"Average feedback score: {avg(e.get('feedback_score') for e in self_regulating):.3f}.",
                f"High-EMG but low-feedback counterexample candidates: {len(unique_rules(high_emg_low_fb))}.",
            ],
            "Compare high-EMG/high-FB worlds against high-EMG/low-FB worlds to test whether feedback predicts longer persistence.",
            impact=5,
            counterexamples=high_emg_low_fb,
            family="v30_feedback",
        )

    pattern_life_separation = experiments_by_condition(
        v30,
        lambda e: safe_float(e.get("validation_quality")) >= 0.50
        and safe_float(e.get("emergence_score")) < 0.20
        and safe_float(e.get("knowledge_score")) < 0.20
        and safe_float(e.get("feedback_score")) < 0.25,
    )
    if pattern_life_separation:
        add(
            "GP-104",
            "Pattern-life separation",
            "Visually rich or stable patterns should not be classified as emergent organization without life, knowledge, feedback, and validation support.",
            pattern_life_separation,
            [
                f"{len(unique_rules(pattern_life_separation))} rule(s) are treated as weak/none despite normalized analysis, providing false-positive guardrails.",
                "This principle protects the project from mistaking decorative texture for living organization.",
            ],
            "Add a Hall of Failure / beautiful-dead-world set and verify that EMG remains low while visual complexity can remain high.",
            impact=4,
            family="v30_validation",
        )

    civ_with_knowledge = experiments_by_condition(
        v30,
        lambda e: safe_float(e.get("civilization_score")) >= 0.45
        and safe_float(e.get("knowledge_score")) >= 0.45,
    )
    civ_without_knowledge = experiments_by_condition(
        v30,
        lambda e: safe_float(e.get("civilization_score")) >= 0.45
        and safe_float(e.get("knowledge_score")) < 0.25,
    )
    if civ_with_knowledge:
        add(
            "GP-105",
            "Civilization requires knowledge scaffold",
            "Civilization-like classification becomes more credible when it is supported by a knowledge scaffold rather than urban/colony structure alone.",
            civ_with_knowledge,
            [
                f"{len(unique_rules(civ_with_knowledge))} supporting rule(s) combine CIV>=0.45 and KNOW>=0.45.",
                f"Average civilization score: {avg(e.get('civilization_score') for e in civ_with_knowledge):.3f}.",
                f"Average knowledge score: {avg(e.get('knowledge_score') for e in civ_with_knowledge):.3f}.",
                f"Civilization-without-knowledge counterexample candidates: {len(unique_rules(civ_without_knowledge))}.",
            ],
            "Search for worlds with high CIV and low KNOW; if many exist, split civilization into structure-only and culture-supported forms.",
            impact=4,
            counterexamples=civ_without_knowledge,
            family="v30_civilization",
        )

    # ------------------------------------------------------------------
    # Mechanism-backed principle seeds from mechanism reports
    # ------------------------------------------------------------------

    if mechanism_reports:
        high_memory = [
            r for r in mechanism_reports
            if safe_float(r.get("scores", {}).get("field_memory")) >= 0.8
            and safe_float(r.get("scores", {}).get("stochastic_stability")) >= 0.9
        ]
        if high_memory:
            rule_set = {r.get("rule") for r in high_memory}
            linked_exps = [e for e in experiments if str(e.get("rule") or "").zfill(5) in rule_set]
            if linked_exps:
                add(
                    "GP-201",
                    "Memory-stability genome signature",
                    "High field memory combined with stochastic stability may be a genome-level signature of persistent worlds.",
                    linked_exps,
                    [
                        f"{len(high_memory)} mechanism report(s) show field_memory>=0.8 and stochastic_stability>=0.9.",
                        "This links rule genome structure to observed long-lived behaviour.",
                    ],
                    "Decode genomes for several unstable rules and check whether this signature is absent.",
                    impact=5,
                    mechanism_links=["M-001", "M-002"],
                    family="mechanism",
                )

    return principles


# -----------------------------------------------------------------------------
# Rendering
# -----------------------------------------------------------------------------



SCIENTIFIC_CLAIM_IDS = frozenset(CLAIM_SPECS)


def load_evidence_report(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8", errors="replace")
        )
    except Exception as exc:
        print(f"[WARN] Could not read evidence report {path}: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def evidence_level_from_claim(claim: dict[str, Any]) -> str:
    status = str(claim.get("status") or "")
    support = safe_int(claim.get("support"))
    if status == "contested":
        return "contested"
    if status == "supported_principle":
        return "cross_rule"
    if support >= 5:
        return "recurring"
    if support >= 2:
        return "multi_case_seed"
    if support >= 1:
        return "single_case"
    return "none"


def status_from_evidence_claim(
    claim: dict[str, Any],
    coverage_status: str,
) -> str:
    status = str(claim.get("status") or "unobserved")
    family = str(
        CLAIM_SPECS.get(str(claim.get("id"))).family
        if str(claim.get("id")) in CLAIM_SPECS
        else ""
    )

    if family == "validation_calibration":
        return "Calibration claim"

    if status == "contested":
        return "Contested principle candidate"
    if status == "supported_principle":
        if coverage_status == "COUNTEREXAMPLES_FOUND":
            return "Tested principle candidate"
        if coverage_status == "NEAR_COUNTEREXAMPLES_ONLY":
            return "Supported, near-counterexamples pending"
        return "Supported, opposing regime untested"
    if status == "multi_case_hypothesis":
        return "Multi-case hypothesis"
    if status == "single_case_seed":
        return "Single-case principle seed"
    return "Weak or unobserved claim"


def confidence_from_evidence_claim(
    claim: dict[str, Any],
    coverage_status: str,
) -> str:
    raw = str(claim.get("confidence_label") or "NONE").upper()

    # General Principle Engine must not present untested opposing regimes as
    # HIGH/VERY_HIGH scientific confidence.
    if coverage_status == "UNTESTED_REGIME":
        caps = {
            "VERY_HIGH": "MEDIUM",
            "HIGH": "MEDIUM",
            "MEDIUM": "LOW-MEDIUM",
        }
        return caps.get(raw, raw)

    if coverage_status == "NEAR_COUNTEREXAMPLES_ONLY":
        caps = {
            "VERY_HIGH": "MEDIUM-HIGH",
            "HIGH": "MEDIUM-HIGH",
        }
        return caps.get(raw, raw)

    return raw


def load_counterexample_coverage(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8", errors="replace")
        )
    except Exception as exc:
        print(f"[WARN] Could not read counterexample report {path}: {exc}")
        return {}

    audits = payload.get("audits", []) if isinstance(payload, dict) else []
    return {
        str(item.get("id")): str(
            item.get("coverage_status") or "UNTESTED_REGIME"
        )
        for item in audits
        if isinstance(item, dict) and item.get("id")
    }


def principles_from_evidence(
    evidence: dict[str, Any],
    coverage_by_claim: dict[str, str],
    atlas: dict[str, Any],
) -> list[dict[str, Any]]:
    claims = evidence.get("claims", []) if isinstance(evidence, dict) else []
    experiments = scientific_atlas_records(atlas)
    unique_rules = {
        str(record.get("rule") or "unknown").zfill(5)
        for record in experiments
    }

    by_rule: dict[str, list[dict[str, Any]]] = {}
    for record in experiments:
        rule = str(record.get("rule") or "unknown").zfill(5)
        by_rule.setdefault(rule, []).append(record)

    out: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue

        claim_id = str(claim.get("id") or "")
        spec = CLAIM_SPECS.get(claim_id)
        if spec is None:
            continue

        support_rules = [
            str(rule).zfill(5)
            for rule in claim.get("support_rules", []) or []
        ]
        counter_rules = [
            str(rule).zfill(5)
            for rule in claim.get("counterexample_rules", []) or []
        ]
        coverage = coverage_by_claim.get(
            claim_id,
            "UNTESTED_REGIME",
        )
        perturbation = (
            claim.get("perturbation_evidence", {})
            if isinstance(claim.get("perturbation_evidence"), dict)
            else {}
        )

        supporting_records = [
            record
            for rule in support_rules
            for record in by_rule.get(rule, [])
            if record.get("is_representative", True)
        ]
        counter_records = [
            record
            for rule in counter_rules
            for record in by_rule.get(rule, [])
            if record.get("is_representative", True)
        ]

        average_validation = avg(
            record.get("validation_quality")
            for record in supporting_records
        )

        out.append({
            "id": claim_id,
            "name": spec.title,
            "family": spec.family,
            "status": status_from_evidence_claim(claim, coverage),
            "evidence_level": evidence_level_from_claim(claim),
            "confidence": confidence_from_evidence_claim(claim, coverage),
            "raw_confidence": str(
                claim.get("confidence_label") or "NONE"
            ),
            "confidence_score": safe_float(
                claim.get("confidence_score")
            ),
            "impact": 4,
            "support": safe_int(claim.get("support")),
            "total_experiments": len(experiments),
            "total_unique_rules": len(unique_rules),
            "counterexamples": safe_int(
                claim.get("counterexamples")
            ),
            "neutral": safe_int(claim.get("neutral")),
            "rules": support_rules,
            "counterexample_rules": counter_rules,
            "average_validation": average_validation,
            "claim": spec.description,
            "interpretation": spec.interpretation,
            "coverage_status": coverage,
            "perturbation_status": str(
                perturbation.get("status")
                or "INSUFFICIENT_CLAIM_SIGNAL"
            ),
            "perturbation_parent_rules": list(
                perturbation.get("parent_rules", []) or []
            ),
            "perturbation_parent_count": safe_int(
                perturbation.get("unique_parent_rule_count")
            ),
            "perturbation_run_count": safe_int(
                perturbation.get("informative_run_count")
            ),
            "perturbation_evidence": perturbation,
            "evidence": [
                (
                    f"Evidence Engine: support={safe_int(claim.get('support'))}, "
                    f"counterexamples={safe_int(claim.get('counterexamples'))}, "
                    f"neutral={safe_int(claim.get('neutral'))}."
                ),
                (
                    f"Raw evidence confidence: "
                    f"{claim.get('confidence_label', 'NONE')} "
                    f"({safe_float(claim.get('confidence_score')):.3f})."
                ),
                f"Counterexample coverage: {coverage}.",
                (
                    "Controlled perturbation coverage: "
                    f"{perturbation.get('status', 'INSUFFICIENT_CLAIM_SIGNAL')} "
                    f"across {safe_int(perturbation.get('unique_parent_rule_count'))} "
                    "independent parent rule(s)."
                ),
                (
                    "Perturbation cases are kept separate from observational "
                    "support and do not automatically change confidence."
                ),
            ],
            "example_signals": [
                v30_summary(record)
                for record in supporting_records[:5]
            ],
            "counterexample_signals": [
                v30_summary(record)
                for record in counter_records[:5]
            ],
            "mechanism_links": [],
            "next_test": (
                "Run the explicit counterexample-search regimes defined in "
                "scientific_claims.py before promoting confidence further."
                if coverage == "UNTESTED_REGIME"
                else "Investigate near/confirmed counterexamples and repeat "
                "the claim across independent seeds."
            ),
            "claim_version": spec.version,
            "source": "evidence_report.json",
        })

    return out


def merge_evidence_principles(
    locally_built: list[dict[str, Any]],
    evidence_principles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Keep legacy GP-001... principles for continuity. Claims managed by the
    # registry are replaced by Evidence Engine results.
    retained = [
        principle
        for principle in locally_built
        if str(principle.get("id")) not in SCIENTIFIC_CLAIM_IDS
    ]
    return retained + evidence_principles


def render_markdown(atlas: dict[str, Any], principles: list[dict[str, Any]], mechanism_reports: list[dict[str, Any]]) -> str:
    experiments = scientific_atlas_records(atlas)
    v30_count = sum(1 for e in experiments if has_v30_fields(e))
    lines: list[str] = []

    lines.append("# Universe Search General Principles v30")
    lines.append("")
    lines.append(f"Generated: **{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
    unique_rule_count = len(unique_rules(experiments))
    v30_unique_rule_count = len(unique_rules([e for e in experiments if has_v30_fields(e)]))
    lines.append(f"Atlas experiment records: **{len(experiments)}**")
    lines.append(f"Atlas unique rules: **{unique_rule_count}**")
    lines.append(f"v30 ObserverProfile records: **{v30_count}**")
    lines.append(f"v30 unique rules: **{v30_unique_rule_count}**")
    lines.append(f"Mechanism reports: **{len(mechanism_reports)}**")
    lines.append(f"Principles generated: **{len(principles)}**")
    lines.append("")

    lines.append("## Important note")
    lines.append("")
    lines.append(
        "These are not final laws. They are candidate general principles. "
        "The engine is deliberately conservative: one rule remains a seed, several rules become a recurring pattern, "
        "and only broad replicated support can promote a claim toward a general principle."
    )
    lines.append("")

    if principles:
        lines.append("## Principle ladder")
        lines.append("")
        ladder = {
            "single_case": 0,
            "multi_case_seed": 0,
            "recurring": 0,
            "cross_rule": 0,
            "candidate_general": 0,
            "general": 0,
        }
        for p in principles:
            ladder[p.get("evidence_level", "none")] = ladder.get(p.get("evidence_level", "none"), 0) + 1
        lines.append(f"- Single-case seeds: **{ladder.get('single_case', 0)}**")
        lines.append(f"- Multi-case seeds: **{ladder.get('multi_case_seed', 0)}**")
        lines.append(f"- Recurring patterns: **{ladder.get('recurring', 0)}**")
        lines.append(f"- Cross-rule candidates: **{ladder.get('cross_rule', 0)}**")
        lines.append(f"- General candidates: **{ladder.get('candidate_general', 0)}**")
        lines.append(f"- General principles: **{ladder.get('general', 0)}**")
        lines.append("")

    lines.append("## Principle candidates")
    lines.append("")
    if not principles:
        lines.append("No principle candidates yet. Add more experiments to the atlas.")
        lines.append("")
    else:
        ordered = sorted(
            principles,
            key=lambda p: (p.get("support", 0), p.get("average_validation", 0), p.get("impact", 0)),
            reverse=True,
        )
        for p in ordered:
            lines.append(f"### {p['id']}: {p['name']}")
            lines.append("")
            lines.append(f"- Family: **{p.get('family', '-')}**")
            lines.append(f"- Status: **{p['status']}**")
            lines.append(f"- Evidence level: **{p.get('evidence_level', '-')}**")
            lines.append(f"- Confidence: **{p['confidence']}**")
            lines.append(f"- Impact: **{stars(p['impact'])}**")
            lines.append(
                f"- Support: **{p['support']} / {p.get('total_unique_rules', p['total_experiments'])} unique rule(s)** "
                f"from **{p['total_experiments']} experiment record(s)**"
            )
            lines.append(f"- Counterexamples: **{p['counterexamples']}**")
            lines.append(f"- Average validation: **{safe_float(p.get('average_validation')):.3f}**")
            lines.append(f"- Rules: **{', '.join(str(r) for r in p['rules']) or '-'}**")
            if p.get("counterexample_rules"):
                lines.append(f"- Counterexample rules: **{', '.join(str(r) for r in p['counterexample_rules'])}**")
            if p.get("mechanism_links"):
                lines.append(f"- Mechanism links: **{', '.join(p['mechanism_links'])}**")
            lines.append(
                f"- Perturbation status: **{p.get('perturbation_status', 'INSUFFICIENT_CLAIM_SIGNAL')}**"
            )
            lines.append(
                f"- Perturbation coverage: **{safe_int(p.get('perturbation_run_count'))} informative run(s)** "
                f"across **{safe_int(p.get('perturbation_parent_count'))} parent rule(s)**"
            )
            lines.append("")
            lines.append("**Claim**")
            lines.append("")
            lines.append(p["claim"])
            lines.append("")
            lines.append("**Evidence**")
            lines.append("")
            for item in p["evidence"]:
                lines.append(f"- {item}")
            if p.get("example_signals"):
                lines.append("")
                lines.append("**Example signals**")
                lines.append("")
                for item in p["example_signals"]:
                    lines.append(f"- {item}")
            if p.get("counterexample_signals"):
                lines.append("")
                lines.append("**Counterexample signals**")
                lines.append("")
                for item in p["counterexample_signals"]:
                    lines.append(f"- {item}")
            lines.append("")
            lines.append("**Next test**")
            lines.append("")
            lines.append(p["next_test"])
            lines.append("")

    lines.append("## Current limitation")
    lines.append("")
    if len(experiments) < 5:
        lines.append(
            "The dataset is still too small for real laws. Current v30 principles are mostly structured test prompts, not conclusions."
        )
    elif len(experiments) < 30:
        lines.append(
            "The dataset supports preliminary comparison, but still needs more neighbouring rules, repeated runs, and explicit counterexamples."
        )
    else:
        lines.append(
            "The dataset is large enough for early cross-rule principle discovery, but confidence still depends on replication and counterexample search."
        )
    lines.append("")

    lines.append("## Suggested next data")
    lines.append("")
    lines.append("1. Run neighbouring rules around top EMG/VAL candidates.")
    lines.append("2. Add beautiful-dead-world counterexamples with high visual complexity but low EMG.")
    lines.append("3. Repeat top candidates several times to test stability of EMG and VAL.")
    lines.append("4. Add mechanism reports for both strong and weak worlds.")
    lines.append("5. Promote principles only after repeated independent support.")
    lines.append("")

    return "\n".join(lines)


def save_json(
    principles: list[dict[str, Any]],
    out: Path,
    evidence_path: Path | None = None,
    counterexample_path: Path | None = None,
) -> None:
    payload = {
        "version": "Universe Search General Principle Engine v30.1",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scientific_claims_registry": {
            "module": "scientific_claims.py",
            "claim_versions": {
                claim_id: spec.version
                for claim_id, spec in CLAIM_SPECS.items()
            },
        },
        "inputs": {
            "evidence_report": str(evidence_path) if evidence_path else None,
            "counterexample_report": (
                str(counterexample_path)
                if counterexample_path
                else None
            ),
        },
        "principles": principles,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate v30 general principles from Universe Search Atlas.")
    parser.add_argument("atlas", help="Path to research_atlas.json")
    parser.add_argument("--results", action="append", default=[], help="Optional results folder(s) to search for mechanism reports")
    parser.add_argument("--out", default="general_principles.md", help="Output markdown file")
    parser.add_argument(
        "--evidence",
        default=None,
        help="Evidence report JSON. Default: next to --out.",
    )
    parser.add_argument(
        "--counterexamples",
        default=None,
        help="Counterexample report JSON. Default: next to --out.",
    )
    args = parser.parse_args()

    atlas_path = Path(args.atlas)
    if not atlas_path.exists():
        print(f"[ERROR] Atlas not found: {atlas_path}")
        return 1

    atlas = load_json(atlas_path)
    result_roots = [Path(p) for p in args.results]
    mechanism_reports = collect_mechanism_reports(
        atlas_path,
        result_roots,
    )
    locally_built = build_principles(atlas, mechanism_reports)

    out_md = Path(args.out)
    if not out_md.is_absolute():
        # A bare filename keeps the historical behavior and is written next
        # to the Atlas. A relative path containing directories is interpreted
        # from the current project working directory.
        if out_md.parent == Path("."):
            out_md = atlas_path.parent / out_md
        else:
            out_md = (Path.cwd() / out_md).resolve()
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json = out_md.with_suffix(".json")

    evidence_path = (
        Path(args.evidence).resolve()
        if args.evidence
        else out_md.parent / "evidence_report.json"
    )
    counterexample_path = (
        Path(args.counterexamples).resolve()
        if args.counterexamples
        else out_md.parent / "counterexample_report.json"
    )

    evidence = load_evidence_report(evidence_path)
    coverage = load_counterexample_coverage(counterexample_path)
    evidence_principles = principles_from_evidence(
        evidence,
        coverage,
        atlas,
    )

    if evidence_principles:
        principles = merge_evidence_principles(
            locally_built,
            evidence_principles,
        )
    else:
        print(
            "[WARN] Evidence report unavailable or empty; "
            "using locally derived principles."
        )
        principles = locally_built

    out_md.write_text(
        render_markdown(atlas, principles, mechanism_reports),
        encoding="utf-8",
    )
    save_json(
        principles,
        out_json,
        evidence_path,
        counterexample_path,
    )

    print("")
    print("=" * 64)
    print("Universe Search General Principle Engine v30")
    print("=" * 64)
    print(f"Atlas:              {atlas_path}")
    print(f"Mechanism reports:  {len(mechanism_reports)}")
    print(f"Evidence report:    {evidence_path}")
    print(f"Counterexamples:    {counterexample_path}")
    print(f"Principles:         {len(principles)}")
    print(f"Output MD:          {out_md}")
    print(f"Output JSON:        {out_json}")
    print("-" * 64)
    for p in sorted(principles, key=lambda x: (x.get("support", 0), x.get("average_validation", 0)), reverse=True):
        print(
            f"{p['id']}: {p['name']} | {p['status']} | "
            f"support={p['support']} | confidence={p['confidence']}"
        )
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
