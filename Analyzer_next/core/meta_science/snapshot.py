"""Knowledge-evolution snapshot construction without filesystem access."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.meta_science.bottlenecks import compute_bottlenecks
from Analyzer_next.core.meta_science.constants import MATURITY_BUCKETS, SCHEMA
from Analyzer_next.core.meta_science.contracts import MetaScienceInputs, MetaSciencePaths
from Analyzer_next.core.meta_science.health import compute_scientific_health
from Analyzer_next.core.meta_science.laboratory import build_laboratory_state
from Analyzer_next.core.meta_science.numeric import clamp01, mean, sf, si, ss, status_bucket
from Analyzer_next.core.meta_science.scope import describe_rules, evidence_rule_set, profile_info


def _atlas_record_count(atlas: dict[str, Any]) -> int:
    if isinstance(atlas.get("records"), list):
        return len(atlas["records"])
    if isinstance(atlas.get("rules"), dict):
        return len(atlas["rules"])
    if isinstance(atlas.get("entries"), list):
        return len(atlas["entries"])
    if isinstance(atlas.get("experiments"), list):
        return len(atlas["experiments"])
    return 0


def build_snapshot(
    paths: MetaSciencePaths,
    inputs: MetaScienceInputs,
    generated_at: str,
) -> dict[str, Any]:
    consensus = inputs.consensus
    database = inputs.consensus_database
    evidence = inputs.evidence
    principles_src = inputs.general_principles
    atlas = inputs.research_atlas
    theory_text = inputs.theory_report
    profiles = profile_info(inputs.profiles)
    laboratory_state = build_laboratory_state(inputs)
    reference_controls = laboratory_state.get("reference_controls", {})

    principles = consensus.get("principles", []) if isinstance(consensus, dict) else []
    if not isinstance(principles, list):
        principles = []

    maturity: dict[str, int] = {bucket: 0 for bucket in MATURITY_BUCKETS}
    for principle in principles:
        if isinstance(principle, dict):
            maturity[status_bucket(ss(principle.get("status"), "NO_SIGNAL"))] += 1

    support_total = sum(si(item.get("support")) for item in principles if isinstance(item, dict))
    counter_total = sum(si(item.get("counterexamples")) for item in principles if isinstance(item, dict))
    consensus_scores = [sf(item.get("consensus_score")) for item in principles if isinstance(item, dict)]
    quality_scores = [sf(item.get("evidence_quality")) for item in principles if isinstance(item, dict)]
    robustness_scores = [sf(item.get("robustness")) for item in principles if isinstance(item, dict)]
    predictive_scores = [sf(item.get("predictive_value")) for item in principles if isinstance(item, dict)]

    claims = evidence.get("claims", []) if isinstance(evidence, dict) else []
    if not isinstance(claims, list):
        claims = []
    profile_rules = set(profiles["rules"])
    evidence_rules = evidence_rule_set(evidence)
    scientific_rules = evidence_rules or profile_rules
    scientific_view = describe_rules(scientific_rules)
    scientific_view["profile_rule_count"] = len(profile_rules)
    scientific_view["evidence_rule_count"] = len(evidence_rules)
    scientific_view["profile_evidence_match"] = not evidence_rules or profile_rules == evidence_rules

    gp_items = principles_src.get("principles", []) if isinstance(principles_src, dict) else []
    if not isinstance(gp_items, list):
        gp_items = []
    db_principles = database.get("principles", {}) if isinstance(database, dict) else {}
    if not isinstance(db_principles, dict):
        db_principles = {}
    run_history = database.get("run_history", []) if isinstance(database, dict) else []
    if not isinstance(run_history, list):
        run_history = []

    total_principles = len(principles)
    mature_count = (
        maturity["SUPPORTED"] + maturity["STRONG"]
        + maturity["CONSENSUS"] + maturity["FOUNDATIONAL"]
    )
    contested_count = maturity["DISPUTED"]
    observation_count = maturity["OBSERVATION"]
    consensus_count = maturity["CONSENSUS"] + maturity["FOUNDATIONAL"]

    knowledge_maturity_score = clamp01(
        0.18 * (maturity["PROMISING"] / max(1, total_principles))
        + 0.28 * (mature_count / max(1, total_principles))
        + 0.22 * (consensus_count / max(1, total_principles))
        + 0.17 * mean(consensus_scores)
        + 0.15 * mean(quality_scores)
    )
    stability_score = clamp01(
        0.45 * (1.0 - counter_total / max(1, support_total + counter_total))
        + 0.30 * mean(robustness_scores)
        + 0.25 * (1.0 - contested_count / max(1, total_principles))
    )
    research_velocity = clamp01(
        0.35 * (len(claims) / max(1, total_principles))
        + 0.25 * (len(run_history) / 20.0)
        + 0.20 * (profiles["count"] / 50.0)
        + 0.20 * mean(predictive_scores)
    )
    knowledge_efficiency = clamp01(
        0.45 * (support_total / max(1, support_total + counter_total + observation_count))
        + 0.25 * mean(quality_scores)
        + 0.15 * mean(consensus_scores)
        + 0.15 * (mature_count / max(1, total_principles))
    )

    top = [
        {
            "id": ss(principle.get("id")),
            "title": ss(principle.get("title")),
            "status": ss(principle.get("status")),
            "consensus_percent": round(sf(principle.get("consensus_percent")), 2),
            "support": si(principle.get("support")),
            "counterexamples": si(principle.get("counterexamples")),
        }
        for principle in sorted(
            [item for item in principles if isinstance(item, dict)],
            key=lambda item: (sf(item.get("consensus_score")), si(item.get("support"))),
            reverse=True,
        )[:10]
    ]

    signals: list[dict[str, str]] = []
    if total_principles and contested_count / max(1, total_principles) > 0.25:
        signals.append({
            "level": "warning",
            "signal": "High disputed-principle ratio",
            "note": "Current theories may need revision or more careful conditions.",
        })
    if total_principles >= 5 and mature_count == 0:
        signals.append({
            "level": "info",
            "signal": "Young science phase",
            "note": "Most principles remain observations; this is expected with low rule count.",
        })
    if support_total >= 10 and counter_total == 0:
        signals.append({
            "level": "warning",
            "signal": "No counterexamples yet",
            "note": "Support is broad but the counterexample channel may be under-tested or asymmetric.",
        })
    if profiles["count"] < 10:
        signals.append({
            "level": "info",
            "signal": "Low sample regime",
            "note": "Consensus should stay conservative until more rules are analyzed.",
        })

    research_metrics = {
        "principles_total": total_principles,
        "support_total": support_total,
        "counterexamples_total": counter_total,
        "mean_consensus": round(mean(consensus_scores), 4),
        "mean_evidence_quality": round(mean(quality_scores), 4),
        "mean_robustness": round(mean(robustness_scores), 4),
        "mean_predictive_value": round(mean(predictive_scores), 4),
        "knowledge_maturity_score": round(knowledge_maturity_score, 4),
        "scientific_stability_score": round(stability_score, 4),
        "research_velocity_score": round(research_velocity, 4),
        "knowledge_efficiency_score": round(knowledge_efficiency, 4),
    }
    scientific_health = compute_scientific_health(laboratory_state, research_metrics)
    bottlenecks = compute_bottlenecks(laboratory_state, scientific_health)

    return {
        "schema": SCHEMA,
        "generated": generated_at,
        "root": str(paths.root),
        "results_folder": str(paths.results),
        "inputs_seen": {
            "observer_profiles": profiles["count"],
            "observer_rules": profiles["rules"],
            "atlas_records": _atlas_record_count(atlas),
            "theory_report_chars": len(theory_text),
            "general_principles": len(gp_items),
            "evidence_claims": len(claims),
            "consensus_principles": total_principles,
            "consensus_db_principles": len(db_principles),
            "consensus_db_runs": len(run_history),
        },
        "scientific_view": scientific_view,
        "knowledge_age": {
            "observations": maturity["OBSERVATION"],
            "promising": maturity["PROMISING"],
            "supported": maturity["SUPPORTED"],
            "strong": maturity["STRONG"],
            "consensus": maturity["CONSENSUS"],
            "foundational": maturity["FOUNDATIONAL"],
            "disputed": maturity["DISPUTED"],
            "no_signal": maturity["NO_SIGNAL"],
        },
        "research_metrics": research_metrics,
        "scientific_health": scientific_health,
        "bottlenecks": bottlenecks,
        "top_principles": top,
        "meta_signals": signals,
        "laboratory_health": laboratory_state["laboratory_health"],
        "coverage": laboratory_state["coverage"],
        "prediction_pipeline": laboratory_state["prediction_pipeline"],
        "experiment_queue": laboratory_state["experiment_queue"],
        "research_debt": laboratory_state["research_debt"],
        "knowledge_integrity": laboratory_state["knowledge_integrity"],
        "reference_controls": reference_controls,
    }
