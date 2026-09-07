#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universe Search Theory Engine v30

Reads research_atlas.json and generates theory_report.md.

v30 understands ObserverProfile / Atlas v30 fields:
- civilization_score / civilization_stage
- knowledge_score / knowledge_axis
- feedback_score / feedback_regime
- emergence_score / emergence_confidence / emergence_evidence_count
- validation_quality / validation_grade / validation false-positive / false-negative risks

Usage:
    python theory_engine.py research_atlas.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.scientific_claims import CLAIM_SPECS
from archon_paths import ANALYSIS_RESULTS_DIR, KNOWLEDGE_ATLAS_DIR


def analysis_results_dir() -> Path:
    return ANALYSIS_RESULTS_DIR


def knowledge_atlas_dir() -> Path:
    return KNOWLEDGE_ATLAS_DIR


def load_atlas(path: Path) -> dict[str, Any]:
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


def stars(score: int) -> str:
    score = max(1, min(5, int(score or 1)))
    return "★" * score + "☆" * (5 - score)


def avg(values: Iterable[Any]) -> float:
    vals = [safe_float(v, None) for v in values]
    vals = [v for v in vals if v is not None]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def confidence_from_support(support: int, avg_value: float, validation: float = 0.0) -> str:
    if support >= 5 and (avg_value >= 8.0 or validation >= 0.75):
        return "HIGH"
    if support >= 2 and (avg_value >= 7.0 or validation >= 0.65):
        return "MEDIUM"
    if support >= 1 and (avg_value >= 8.5 or validation >= 0.85):
        return "LOW-MEDIUM"
    return "LOW"


def theory_status(support: int) -> str:
    if support >= 5:
        return "Candidate principle"
    if support >= 2:
        return "Emerging pattern"
    return "Single-case hypothesis"


def rule_list(experiments: list[dict[str, Any]]) -> list[str]:
    return sorted({str(e.get("rule") or "?").zfill(5) for e in experiments})


def unique_support(experiments: list[dict[str, Any]]) -> int:
    return len(rule_list(experiments))


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


def build_theories(atlas: dict[str, Any]) -> list[dict[str, Any]]:
    experiments = atlas.get("experiments", []) or []
    theories: list[dict[str, Any]] = []

    # Legacy continuity: keep old hypotheses alive for older atlas files.
    stable = [
        e for e in experiments
        if e.get("family") == "Stable Dynamic Attractor"
        or (
            safe_int(e.get("lifetime")) >= 100000
            and safe_float(e.get("dynamic_score")) >= 0.8
            and str(e.get("collapse") or "").lower() == "no"
        )
    ]
    if stable:
        avg_value = avg(e.get("research_value") for e in stable)
        theories.append({
            "id": "T-001",
            "title": "Stable dynamic attractor principle",
            "status": theory_status(unique_support(stable)),
            "confidence": confidence_from_support(unique_support(stable), avg_value),
            "claim": (
                "Some rules can sustain long-lived non-static organization when high dynamic score, "
                "no collapse, and bounded object turnover occur together."
            ),
            "support": unique_support(stable),
            "rules": rule_list(stable),
            "evidence": [
                f"{unique_support(stable)} unique rule(s) in Stable Dynamic Attractor family",
                f"Average research value: {avg_value:.2f}/10",
                "Observed combination: long lifetime + high dynamic score + no collapse",
            ],
            "risk": "Legacy dynamic-score theory. It should be rechecked against v30 emergence and validation fields.",
            "next_test": "Compare legacy dynamic attractors against EMG/VAL rankings in Atlas v30.",
            "impact": 4,
        })

    turnover = [
        e for e in experiments
        if safe_int(e.get("split_birth")) + safe_int(e.get("merge_death")) >= 20
        and safe_int(e.get("objects")) > 0
    ]
    if turnover:
        avg_value = avg(e.get("research_value") for e in turnover)
        theories.append({
            "id": "T-002",
            "title": "Bounded turnover regulation",
            "status": theory_status(unique_support(turnover)),
            "confidence": confidence_from_support(unique_support(turnover), avg_value),
            "claim": (
                "Stable worlds may regulate themselves through repeated split/birth and merge/death events "
                "while keeping object count within a bounded range."
            ),
            "support": unique_support(turnover),
            "rules": rule_list(turnover),
            "evidence": [
                f"{unique_support(turnover)} unique rule(s) show object turnover",
                "Object count remains bounded while events continue",
            ],
            "risk": "Turnover may be fragmentation noise rather than reproduction-like dynamics.",
            "next_test": "Use lineage and family metrics from Observer v4.x to distinguish reproduction from fragmentation.",
            "impact": 4,
        })

    # v30 theories: ObserverProfile layers.
    v30 = [e for e in experiments if has_v30_fields(e)]

    credible_emergence = [
        e for e in v30
        if safe_float(e.get("emergence_score")) >= 0.65
        and safe_float(e.get("validation_quality")) >= 0.70
        and is_high_conf(e.get("emergence_confidence"))
        and is_high_conf(e.get("validation_grade"))
        and safe_float(e.get("validation_false_positive_risk")) <= 0.20
    ]
    if credible_emergence:
        avg_emg = avg(e.get("emergence_score") for e in credible_emergence)
        avg_val = avg(e.get("validation_quality") for e in credible_emergence)
        theories.append({
            "id": "T-101",
            "title": "Validated emergence criterion",
            "status": theory_status(unique_support(credible_emergence)),
            "confidence": confidence_from_support(unique_support(credible_emergence), avg(e.get("research_value") for e in credible_emergence), avg_val),
            "claim": (
                "Rules with high emergence evidence and high observer validation are credible candidates "
                "for complex self-organized structures, not merely visually complex textures."
            ),
            "support": unique_support(credible_emergence),
            "rules": rule_list(credible_emergence),
            "evidence": [
                f"Average EMG score: {avg_emg:.3f}",
                f"Average validation quality: {avg_val:.3f}",
                "Low false-positive risk across supporting entries",
                "Support requires both EMG and VAL, reducing pure-pattern false positives",
            ],
            "risk": "Thresholds are still hand-calibrated. Needs more rules and repeated runs.",
            "next_test": "Run neighbouring rules and repeated seeds; check whether EMG/VAL stay stable for the same rule family.",
            "impact": 5,
        })

    knowledge_feedback = [
        e for e in v30
        if safe_float(e.get("knowledge_score")) >= 0.50
        and safe_float(e.get("feedback_score")) >= 0.50
        and safe_float(e.get("emergence_score")) >= 0.55
    ]
    if knowledge_feedback:
        avg_k = avg(e.get("knowledge_score") for e in knowledge_feedback)
        avg_fb = avg(e.get("feedback_score") for e in knowledge_feedback)
        theories.append({
            "id": "T-102",
            "title": "Knowledge-feedback coupling hypothesis",
            "status": theory_status(unique_support(knowledge_feedback)),
            "confidence": confidence_from_support(unique_support(knowledge_feedback), avg(e.get("research_value") for e in knowledge_feedback), avg(e.get("validation_quality") for e in knowledge_feedback)),
            "claim": (
                "In promising worlds, knowledge accumulation and feedback strength tend to appear together. "
                "This suggests that persistent complexity may require information to become part of the system's own regulation."
            ),
            "support": unique_support(knowledge_feedback),
            "rules": rule_list(knowledge_feedback),
            "evidence": [
                f"Average knowledge score: {avg_k:.3f}",
                f"Average feedback score: {avg_fb:.3f}",
                "Candidate rules exceed knowledge, feedback, and emergence thresholds together",
            ],
            "risk": "Knowledge and feedback are both derived observer layers; correlation may be partly metric-coupling.",
            "next_test": "Compare rules with high knowledge but low feedback, and high feedback but low knowledge.",
            "impact": 5,
        })

    self_regulating = [
        e for e in v30
        if safe_float(e.get("feedback_score")) >= 0.60
        and "SELF" in norm_text(e.get("feedback_regime"))
        and safe_float(e.get("validation_quality")) >= 0.60
    ]
    if self_regulating:
        theories.append({
            "id": "T-103",
            "title": "Self-regulation marker",
            "status": theory_status(unique_support(self_regulating)),
            "confidence": confidence_from_support(unique_support(self_regulating), avg(e.get("research_value") for e in self_regulating), avg(e.get("validation_quality") for e in self_regulating)),
            "claim": (
                "A SELF_REGULATING feedback regime may be a useful marker for worlds where internal organization "
                "buffers environmental pressure instead of merely surviving by static stability."
            ),
            "support": unique_support(self_regulating),
            "rules": rule_list(self_regulating),
            "evidence": [
                f"{unique_support(self_regulating)} unique rule(s) reached SELF_REGULATING feedback regime",
                f"Average feedback score: {avg(e.get('feedback_score') for e in self_regulating):.3f}",
                f"Average validation quality: {avg(e.get('validation_quality') for e in self_regulating):.3f}",
            ],
            "risk": "Current feedback is interpretive and does not yet modify base cellular dynamics.",
            "next_test": "Track whether SELF_REGULATING worlds maintain lower effective pressure and longer survival than comparable controls.",
            "impact": 4,
        })

    validated_negative_controls = [
        e for e in v30
        if safe_float(e.get("emergence_score")) <= 0.10
        and safe_float(e.get("knowledge_score")) <= 0.10
        and safe_float(e.get("feedback_score")) <= 0.15
        and (safe_float(e.get("validation_quality")) >= 0.50 or norm_text(e.get("emergence_confidence")) in {"NONE", "LOW"})
    ]
    if validated_negative_controls:
        theories.append({
            "id": "T-104",
            "title": "Pattern-life separation test",
            "status": theory_status(unique_support(validated_negative_controls)),
            "confidence": confidence_from_support(unique_support(validated_negative_controls), avg(e.get("research_value") for e in validated_negative_controls), avg(e.get("validation_quality") for e in validated_negative_controls)),
            "claim": (
                "The v30 Observer/Analyzer stack can reject visually structured but non-living or collapsed worlds, "
                "separating decorative texture from emergent organization."
            ),
            "support": unique_support(validated_negative_controls),
            "rules": rule_list(validated_negative_controls),
            "evidence": [
                "Low EMG, knowledge, and feedback scores in negative-control entries",
                "Atlas keeps these rules below credible emergence status",
            ],
            "risk": "A low score can still be a false negative if the observer misses a non-standard form of organization.",
            "next_test": "Build a Hall of Failure / negative-control set with beautiful dead worlds and collapsed seeds.",
            "impact": 4,
        })

    false_positive_risk = [
        e for e in v30
        if safe_float(e.get("emergence_score")) >= 0.55
        and (
            safe_float(e.get("validation_quality")) < 0.45
            or safe_float(e.get("validation_false_positive_risk")) >= 0.35
            or norm_text(e.get("validation_warning")) not in {"", "OK", "NONE"}
        )
    ]
    if false_positive_risk:
        theories.append({
            "id": "T-105",
            "title": "Emergence false-positive boundary",
            "status": theory_status(len(false_positive_risk)),
            "confidence": "LOW" if len(false_positive_risk) < 3 else "LOW-MEDIUM",
            "claim": (
                "Some worlds may produce high emergence-like readings while failing validation checks. "
                "These cases define the boundary where Observer interpretation becomes risky."
            ),
            "support": len(false_positive_risk),
            "rules": rule_list(false_positive_risk),
            "evidence": [
                "High-ish EMG combined with weak validation or high false-positive risk",
                "These entries should not be promoted to credible emergence candidates",
            ],
            "risk": "This theory needs actual boundary cases; with few rules it may be empty or unstable.",
            "next_test": "Search for rules with EMG 0.55-0.70 and VAL below 0.45, then inspect visually.",
            "impact": 3,
        })

    civilization_knowledge = [
        e for e in v30
        if safe_float(e.get("civilization_score")) >= 0.45
        and safe_float(e.get("knowledge_score")) >= 0.45
    ]
    if civilization_knowledge:
        axes = {}
        for e in civilization_knowledge:
            axis = str(e.get("knowledge_axis") or "unknown")
            axes[axis] = axes.get(axis, 0) + 1
        dominant_axis = max(axes.items(), key=lambda kv: kv[1])[0] if axes else "unknown"
        theories.append({
            "id": "T-106",
            "title": "Civilization requires knowledge scaffold",
            "status": theory_status(unique_support(civilization_knowledge)),
            "confidence": confidence_from_support(unique_support(civilization_knowledge), avg(e.get("research_value") for e in civilization_knowledge), avg(e.get("validation_quality") for e in civilization_knowledge)),
            "claim": (
                "Civilization-like readings become more meaningful when paired with knowledge accumulation. "
                "The civilization layer alone should be treated as weaker evidence than civilization plus knowledge."
            ),
            "support": unique_support(civilization_knowledge),
            "rules": rule_list(civilization_knowledge),
            "evidence": [
                f"{unique_support(civilization_knowledge)} unique rule(s) combine civilization and knowledge scores above threshold",
                f"Dominant knowledge axis among supports: {dominant_axis}",
                f"Average civilization score: {avg(e.get('civilization_score') for e in civilization_knowledge):.3f}",
            ],
            "risk": "Civilization score is still an interpretive layer over cellular patterns, not a direct social simulation.",
            "next_test": "Compare civilization-like worlds with and without knowledge growth to see which survive longer.",
            "impact": 4,
        })

    return theories



THEORY_TO_CLAIM = {
    "T-101": "GP-101",
    "T-102": "GP-102",
    "T-103": "GP-103",
    "T-104": "GP-104",
    "T-106": "GP-105",
}
CLAIM_TO_THEORY = {
    claim_id: theory_id
    for theory_id, claim_id in THEORY_TO_CLAIM.items()
}


def load_general_principles(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8", errors="replace")
        )
    except Exception as exc:
        print(f"[WARN] Could not read general principles {path}: {exc}")
        return []

    principles = (
        payload.get("principles", [])
        if isinstance(payload, dict)
        else []
    )
    return [
        principle
        for principle in principles
        if isinstance(principle, dict)
    ]


def theory_status_from_principle(principle: dict[str, Any]) -> str:
    status = str(principle.get("status") or "Working hypothesis")
    if status == "Calibration claim":
        return "Calibration hypothesis"
    if "untested" in status.lower():
        return "Supported hypothesis, opposing regime untested"
    if "near-counterexamples" in status.lower():
        return "Supported hypothesis, near-counterexamples pending"
    if "contested" in status.lower():
        return "Contested hypothesis"
    if "supported" in status.lower():
        return "Supported hypothesis"
    if "multi-case" in status.lower():
        return "Multi-case hypothesis"
    return status


def theory_from_principle(
    principle: dict[str, Any],
) -> dict[str, Any] | None:
    claim_id = str(principle.get("id") or "")
    theory_id = CLAIM_TO_THEORY.get(claim_id)
    spec = CLAIM_SPECS.get(claim_id)
    if theory_id is None or spec is None:
        return None

    evidence = list(principle.get("evidence", []) or [])
    coverage = str(
        principle.get("coverage_status") or "UNTESTED_REGIME"
    )
    evidence.append(f"Counterexample coverage: {coverage}.")
    evidence.append(
        "Theory confidence is inherited from General Principles and is "
        "not recalculated from Atlas thresholds."
    )
    perturbation_status = str(
        principle.get("perturbation_status")
        or "INSUFFICIENT_CLAIM_SIGNAL"
    )
    perturbation_parent_count = safe_int(
        principle.get("perturbation_parent_count")
    )
    evidence.append(
        "Controlled perturbation coverage: "
        f"{perturbation_status} across "
        f"{perturbation_parent_count} independent parent rule(s)."
    )
    evidence.append(
        "Perturbation evidence is a separate robustness channel and does "
        "not automatically change observational confidence."
    )

    rules = [
        str(rule).zfill(5)
        for rule in principle.get("rules", []) or []
    ]

    return {
        "id": theory_id,
        "claim_id": claim_id,
        "title": spec.title,
        "status": theory_status_from_principle(principle),
        "confidence": str(
            principle.get("confidence") or "NONE"
        ),
        "raw_confidence": str(
            principle.get("raw_confidence")
            or principle.get("confidence")
            or "NONE"
        ),
        "coverage_status": coverage,
        "perturbation_status": perturbation_status,
        "perturbation_parent_count": perturbation_parent_count,
        "perturbation_run_count": safe_int(
            principle.get("perturbation_run_count")
        ),
        "perturbation_evidence": (
            principle.get("perturbation_evidence", {})
            if isinstance(principle.get("perturbation_evidence"), dict)
            else {}
        ),
        "claim": spec.description,
        "support": safe_int(principle.get("support")),
        "counterexamples": safe_int(
            principle.get("counterexamples")
        ),
        "neutral": safe_int(principle.get("neutral")),
        "rules": rules,
        "evidence": evidence,
        "risk": spec.interpretation,
        "next_test": str(
            principle.get("next_test")
            or "Run the explicit counterexample regimes and independent "
               "seed tests before promoting this theory."
        ),
        "impact": safe_int(principle.get("impact"), 4),
        "source": "general_principles.json",
        "claim_version": spec.version,
    }


def merge_principle_theories(
    locally_built: list[dict[str, Any]],
    principles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    managed_theory_ids = set(THEORY_TO_CLAIM)
    retained = [
        theory
        for theory in locally_built
        if str(theory.get("id")) not in managed_theory_ids
    ]

    converted = []
    for principle in principles:
        theory = theory_from_principle(principle)
        if theory is not None:
            converted.append(theory)

    return retained + converted if converted else locally_built


def render_markdown(atlas: dict[str, Any], theories: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    experiments = atlas.get("experiments", []) or []
    v30_count = sum(1 for e in experiments if has_v30_fields(e))

    lines.append("# Universe Search Theory Report v30")
    lines.append("")
    lines.append(f"Generated: **{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
    lines.append(f"Experiment records in atlas: **{len(experiments)}**")
    lines.append(f"Unique rules in atlas: **{len(rule_list(experiments))}**")
    lines.append(f"Experiments with ObserverProfile v30 fields: **{v30_count}**")
    lines.append(f"Theories generated: **{len(theories)}**")
    lines.append("")

    lines.append("## Important note")
    lines.append("")
    lines.append(
        "These are not proven laws. Registry-managed theories inherit their status and confidence "
        "from General Principles, Evidence, and Counterexample coverage. A theory becomes stronger "
        "only after independent-seed replication, matched controls, and explicit opposing-regime tests."
    )
    lines.append("")

    if experiments:
        best_emg = max(experiments, key=lambda e: safe_float(e.get("emergence_score")))
        best_val = max(experiments, key=lambda e: safe_float(e.get("validation_quality")))
        best_value = max(experiments, key=lambda e: safe_float(e.get("research_value")))
        lines.append("## v30 signal summary")
        lines.append("")
        lines.append(f"- Best EMG: **Rule {best_emg.get('rule')}** with EMG={safe_float(best_emg.get('emergence_score')):.3f} ({best_emg.get('emergence_confidence') or '-'})")
        lines.append(f"- Best VAL: **Rule {best_val.get('rule')}** with VAL={safe_float(best_val.get('validation_quality')):.3f} ({best_val.get('validation_grade') or '-'})")
        lines.append(f"- Highest research value: **Rule {best_value.get('rule')}** with value={safe_float(best_value.get('research_value')):.2f}/10")
        lines.append("")

    lines.append("## Theory candidates")
    lines.append("")

    if not theories:
        lines.append("No theory candidates yet. Add more experiments to the atlas.")
        lines.append("")
    else:
        for t in theories:
            lines.append(f"### {t['id']}: {t['title']}")
            lines.append("")
            lines.append(f"- Status: **{t['status']}**")
            lines.append(f"- Confidence: **{t['confidence']}**")
            if t.get("raw_confidence"):
                lines.append(
                    f"- Raw evidence confidence: **{t['raw_confidence']}**"
                )
            if t.get("coverage_status"):
                lines.append(
                    f"- Counterexample coverage: **{t['coverage_status']}**"
                )
            lines.append(
                f"- Perturbation status: **{t.get('perturbation_status', 'INSUFFICIENT_CLAIM_SIGNAL')}**"
            )
            lines.append(
                f"- Perturbation coverage: **{safe_int(t.get('perturbation_run_count'))} informative run(s)** "
                f"across **{safe_int(t.get('perturbation_parent_count'))} parent rule(s)**"
            )
            lines.append(f"- Impact: **{stars(t['impact'])}**")
            lines.append(f"- Support: **{t['support']} unique rule(s)**")
            lines.append(f"- Rules: **{', '.join(str(r) for r in t['rules'])}**")
            lines.append("")
            lines.append("**Claim**")
            lines.append("")
            lines.append(t["claim"])
            lines.append("")
            lines.append("**Evidence**")
            lines.append("")
            for e in t["evidence"]:
                lines.append(f"- {e}")
            lines.append("")
            lines.append("**Risk / Weakness**")
            lines.append("")
            lines.append(t["risk"])
            lines.append("")
            lines.append("**Next test**")
            lines.append("")
            lines.append(t["next_test"])
            lines.append("")

    lines.append("## Recommended next experiments")
    lines.append("")
    lines.append("1. Replicate the current strongest emergence candidate with several independent runs.")
    lines.append("2. Add negative-control rules: collapsed seeds, static textures, chaotic noise, and visually pretty dead worlds.")
    lines.append("3. Search for boundary cases: medium EMG with low VAL, and high visual complexity with EMG near zero.")
    lines.append("4. Compare rules by the chain: pressure → knowledge → feedback → emergence → validation.")
    lines.append("5. Add at least 20 Atlas entries before treating any v30 pattern as more than a working hypothesis.")
    lines.append("")

    lines.append("## Current theory status")
    lines.append("")
    if len(experiments) < 5:
        lines.append("Dataset is still very small. Current theories are early research hypotheses, not conclusions.")
    elif len(experiments) < 20:
        lines.append("Dataset is large enough for preliminary comparison, but still needs broader sampling.")
    else:
        lines.append("Dataset is large enough for first-pass pattern mining. Statistical validation is now worthwhile.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate v30 theory report from Universe Search Research Atlas.")
    parser.add_argument("atlas", nargs="?", default=None, help="Path to research_atlas.json. Default: Atlas/Knowledge/research_atlas.json")
    parser.add_argument("--out", default=None, help="Output markdown file")
    parser.add_argument(
        "--principles",
        default=None,
        help=(
            "Path to general_principles.json. "
            "Default: next to the output report."
        ),
    )
    args = parser.parse_args()

    atlas_path = Path(args.atlas).expanduser() if args.atlas else knowledge_atlas_dir() / "research_atlas.json"
    if not atlas_path.is_absolute():
        atlas_path = (Path.cwd() / atlas_path).resolve()
    if not atlas_path.exists():
        print(f"[ERROR] Atlas not found: {atlas_path}")
        return 1

    atlas = load_atlas(atlas_path)

    out = (
        Path(args.out).expanduser()
        if args.out
        else analysis_results_dir() / "theory_report.md"
    )
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    principles_path = (
        Path(args.principles).expanduser()
        if args.principles
        else out.parent / "general_principles.json"
    )
    if not principles_path.is_absolute():
        principles_path = (Path.cwd() / principles_path).resolve()

    locally_built = build_theories(atlas)
    principles = load_general_principles(principles_path)
    theories = merge_principle_theories(
        locally_built,
        principles,
    )
    md = render_markdown(atlas, theories)
    out.write_text(md, encoding="utf-8")

    print("")
    print("=" * 64)
    print("Universe Search Theory Engine v30")
    print("=" * 64)
    print(f"Atlas:       {atlas_path}")
    print(f"Output:      {out}")
    print(f"Principles:  {principles_path}")
    print(f"Theories:    {len(theories)}")
    print("-" * 64)
    for t in theories:
        print(f"{t['id']}: {t['title']} | {t['status']} | confidence={t['confidence']}")
    print("=" * 64)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
