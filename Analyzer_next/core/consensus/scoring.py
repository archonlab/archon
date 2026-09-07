"""Coverage-adjusted consensus scoring and scientific status calculation."""
from __future__ import annotations

import math
from typing import Any

from .actions import build_consensus_action_signals, prioritize_consensus_action_signals
from .calibration import cap_status, metric_independence_calibration, opposing_regime_factor
from .constants import REPORT_SCHEMA
from .database import build_consensus_context
from .interpretation import interpret_channel_aware_consensus
from .numeric import clamp01, mean, sf, si, ss, now_iso

def compute_consensus_report(
    db: dict[str, Any],
    counterexample_coverage: dict[str, dict[str, Any]] | None = None,
    replication_context: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    principles = db.get("principles", {}) if isinstance(db, dict) else {}
    counterexample_coverage = counterexample_coverage or {}
    replication_context = replication_context or {}

    reports: list[dict[str, Any]] = []
    maturity = {
        "OBSERVATION": 0,
        "PROMISING": 0,
        "SUPPORTED": 0,
        "STRONG": 0,
        "CONSENSUS": 0,
        "FOUNDATIONAL": 0,
        "DISPUTED": 0,
        "NO_SIGNAL": 0,
    }

    for cid, p in principles.items():
        if not isinstance(p, dict):
            continue
        if p.get("active_in_current_evidence", True) is False:
            continue

        obs = (
            p.get("observations", {})
            if isinstance(p.get("observations"), dict)
            else {}
        )
        support_obs = [
            o for o in obs.values()
            if ss(o.get("status")) == "support"
        ]
        counter_obs = [
            o for o in obs.values()
            if ss(o.get("status")) == "counterexample"
        ]
        neutral_obs = [
            o for o in obs.values()
            if ss(o.get("status")) == "neutral"
        ]

        support = len(support_obs)
        counter = len(counter_obs)
        neutral = len(neutral_obs)
        total = support + counter + neutral
        support_ratio = support / max(1, support + counter)
        counter_ratio = counter / max(1, support + counter)

        mean_conf = sf(p.get("summary", {}).get("confidence_score"))
        mean_val = mean([sf(o.get("val")) for o in support_obs])
        mean_emg = mean([sf(o.get("emg")) for o in support_obs])
        mean_know = mean([sf(o.get("know")) for o in support_obs])
        mean_fb = mean([sf(o.get("fb")) for o in support_obs])
        mean_civ = mean([sf(o.get("civ")) for o in support_obs])
        strength_mean = mean([
            sf(o.get("strength")) for o in support_obs
        ])

        support_rules = sorted({
            ss(o.get("rule")) for o in support_obs
            if ss(o.get("rule"))
        })

        repeated_rules = 0
        multi_seed_rules = 0
        for rule in support_rules:
            context = replication_context.get(rule, {})
            if si(context.get("experiment_count")) >= 2:
                repeated_rules += 1
            if si(context.get("seed_count")) >= 2:
                multi_seed_rules += 1

        repeated_observation_coverage = (
            repeated_rules / max(1, len(support_rules))
        )
        independent_seed_coverage = (
            multi_seed_rules / max(1, len(support_rules))
        )

        audit = counterexample_coverage.get(cid, {})
        coverage_status = ss(
            audit.get("coverage_status"),
            "UNTESTED_REGIME",
        )
        opposing_factor = opposing_regime_factor(coverage_status)
        perturbation = (
            p.get("perturbation_evidence", {})
            if isinstance(p.get("perturbation_evidence"), dict)
            else {}
        )
        perturbation_status = ss(
            perturbation.get("status"),
            "INSUFFICIENT_CLAIM_SIGNAL",
        )
        perturbation_parent_count = si(
            perturbation.get("unique_parent_rule_count")
        )
        perturbation_run_count = si(
            perturbation.get("informative_run_count")
        )
        consensus_context = (
            p.get("consensus_context", {})
            if isinstance(p.get("consensus_context"), dict)
            else build_consensus_context(None)
        )
        context_flags = (
            consensus_context.get("flags", {})
            if isinstance(consensus_context.get("flags"), dict)
            else {}
        )

        # Claim-specific structural calibration. This estimates whether the
        # claim compares genuinely separate measurement channels or partially
        # reuses the same upstream signals and formulas.
        (
            metric_independence,
            metric_independence_detail,
        ) = metric_independence_calibration(cid)

        support_maturity = clamp01(
            math.log1p(support) / math.log1p(30)
        )
        diversity = clamp01(
            len(set(o.get("rule") for o in support_obs)) / 30.0
        )
        evidence_quality = clamp01(
            0.35 * mean_conf
            + 0.25 * mean_val
            + 0.20 * mean_emg
            + 0.20 * strength_mean
        )

        # Observed consistency answers only: among classified directional
        # observations, how often did the claim survive? This is not evidence
        # that adversarial regimes were actually explored.
        observed_consistency = clamp01(
            support_ratio * (1.0 - 0.65 * counter_ratio)
        )

        # Adversarial coverage is the independent question: how thoroughly
        # were the claim's declared opposing regimes searched? The audit factor
        # stays below 1.0 while target regimes remain absent or only near.
        adversarial_coverage = clamp01(opposing_factor)

        # Robustness requires both consistency and adversarial exposure.
        # The geometric mean prevents either axis from being hidden by the
        # other while avoiding a double penalty for the same audit signal.
        raw_robustness = clamp01(math.sqrt(
            observed_consistency * adversarial_coverage
        ))
        observational_coverage = clamp01(
            support / max(1, total)
        )

        # Repeat observations are useful, but are not independent replication.
        repeated_factor = 0.55 + 0.45 * repeated_observation_coverage

        # No recorded multi-seed evidence means uncertainty, not failure.
        seed_factor = (
            0.55 + 0.45 * independent_seed_coverage
        )

        # Opposing-regime coverage is already represented inside robustness.
        # The remaining validation dimensions are combined multiplicatively
        # rather than re-normalized after removing the adversarial component.
        # This prevents missing seed coverage or weak repeat coverage from being
        # diluted by weight redistribution.
        validation_factor = clamp01(
            (seed_factor * repeated_factor * metric_independence) ** (1.0 / 3.0)
        )

        robustness = clamp01(raw_robustness * validation_factor)
        repeatability = clamp01(
            0.65 * repeated_observation_coverage
            + 0.35 * independent_seed_coverage
        )
        novelty = 0.50
        # Diagnostic predictive-value proxy. It is reported for interpretation
        # but does not feed back into the consensus score, because its inputs
        # overlap with evidence quality, maturity, and diversity.
        predictive_value = clamp01(
            0.45 * evidence_quality
            + 0.30 * support_maturity
            + 0.15 * diversity
            + 0.10 * observational_coverage
        )

        # Orthogonal score components. Raw robustness contributes exactly once;
        # repeatability is kept separate from support/counterexample balance.
        score_weights = {
            "support_maturity": 0.30,
            "raw_robustness": 0.25,
            "evidence_quality": 0.20,
            "diversity": 0.15,
            "repeatability": 0.10,
        }
        score_components = {
            "support_maturity": support_maturity,
            "raw_robustness": raw_robustness,
            "evidence_quality": evidence_quality,
            "diversity": diversity,
            "repeatability": repeatability,
        }
        raw_consensus_score = clamp01(sum(
            score_weights[name] * score_components[name]
            for name in score_weights
        ))

        consensus_score = clamp01(
            raw_consensus_score * validation_factor
        )

        if counter > support and counter >= 2:
            status = "DISPUTED"
        elif support <= 0 and counter <= 0:
            status = "NO_SIGNAL"
        elif (
            support >= 100
            and consensus_score >= 0.92
            and counter <= max(2, support // 20)
        ):
            status = "FOUNDATIONAL"
        elif (
            support >= 50
            and consensus_score >= 0.86
            and counter <= max(3, support // 10)
        ):
            status = "CONSENSUS"
        elif support >= 20 and consensus_score >= 0.76:
            status = "STRONG"
        elif support >= 10 and consensus_score >= 0.58:
            status = "SUPPORTED"
        elif support >= 3 and consensus_score >= 0.38:
            status = "PROMISING"
        elif support >= 1:
            status = "OBSERVATION"
        elif counter >= 1:
            status = "DISPUTED"
        else:
            status = "NO_SIGNAL"

        # Explicit scientific caps. Absence of a tested opposing regime cannot
        # produce consensus, and no multi-seed evidence cannot be foundational.
        if coverage_status == "UNTESTED_REGIME":
            status = cap_status(status, "PROMISING")
        elif coverage_status == "NEAR_COUNTEREXAMPLES_ONLY":
            status = cap_status(status, "SUPPORTED")
        elif coverage_status == "COUNTEREXAMPLES_FOUND":
            status = cap_status(status, "STRONG")

        if independent_seed_coverage <= 0.0:
            status = cap_status(status, "STRONG")

        channel_interpretation = interpret_channel_aware_consensus(
            legacy_status=status,
            observational_strength=ss(
                consensus_context.get("observational_strength"),
                "NONE",
            ),
            experimental_picture=ss(
                consensus_context.get("experimental_picture"),
                "UNTESTED",
            ),
            perturbation_picture=ss(
                consensus_context.get("perturbation_picture"),
                "INSUFFICIENT",
            ),
            flags=context_flags,
            evidence_gaps=list(
                consensus_context.get("evidence_gaps", []) or []
            ),
        )
        context_counts = (
            consensus_context.get("channel_counts", {})
            if isinstance(consensus_context.get("channel_counts"), dict)
            else {}
        )
        action_signals = build_consensus_action_signals(
            principle_id=cid,
            legacy_status=status,
            channel_aware_status=ss(
                channel_interpretation.get("channel_aware_status"),
                "UNKNOWN",
            ),
            confidence_posture=ss(
                channel_interpretation.get("confidence_posture"),
                "CAUTIOUS",
            ),
            experimental_picture=ss(
                consensus_context.get("experimental_picture"),
                "UNTESTED",
            ),
            perturbation_picture=ss(
                consensus_context.get("perturbation_picture"),
                "INSUFFICIENT",
            ),
            evidence_gaps=list(
                consensus_context.get("evidence_gaps", []) or []
            ),
            flags=context_flags,
            counterexample_coverage_status=coverage_status,
            independent_seed_coverage=independent_seed_coverage,
            experimental_unique_experiments=si(
                context_counts.get("experimental_unique_experiments")
            ),
            experimental_unique_rules=si(
                context_counts.get("experimental_unique_rules")
            ),
        )
        prioritized_actions = prioritize_consensus_action_signals(
            action_signals,
            experimental_picture=ss(
                consensus_context.get("experimental_picture"),
                "UNTESTED",
            ),
            perturbation_picture=ss(
                consensus_context.get("perturbation_picture"),
                "INSUFFICIENT",
            ),
        )

        maturity[status] = maturity.get(status, 0) + 1
        reports.append({
            "id": cid,
            "title": ss(p.get("title"), cid),
            "status": status,
            "consensus_score": round(consensus_score, 4),
            "consensus_percent": round(consensus_score * 100.0, 2),
            "raw_consensus_score": round(raw_consensus_score, 4),
            "raw_consensus_percent": round(
                raw_consensus_score * 100.0,
                2,
            ),
            "validation_factor": round(validation_factor, 4),
            "support": support,
            "counterexamples": counter,
            "neutral": neutral,
            "total_observations": total,
            "support_ratio": round(support_ratio, 4),
            "mean_confidence": round(mean_conf, 4),
            "mean_val": round(mean_val, 4),
            "mean_emg": round(mean_emg, 4),
            "mean_knowledge": round(mean_know, 4),
            "mean_feedback": round(mean_fb, 4),
            "mean_civilization": round(mean_civ, 4),
            "rule_diversity": round(diversity, 4),
            "repeatability": round(repeatability, 4),
            "repeated_observation_coverage": round(
                repeated_observation_coverage,
                4,
            ),
            "independent_seed_coverage": round(
                independent_seed_coverage,
                4,
            ),
            "metric_independence": round(
                metric_independence,
                4,
            ),
            "metric_independence_detail": metric_independence_detail,
            "opposing_regime_factor": round(
                opposing_factor,
                4,
            ),
            "observed_consistency": round(
                observed_consistency,
                4,
            ),
            "adversarial_coverage": round(
                adversarial_coverage,
                4,
            ),
            "counterexample_coverage_status": coverage_status,
            "confirmed_counterexamples_in_audit": si(
                audit.get("confirmed_count")
            ),
            "near_counterexamples_in_audit": si(
                audit.get("near_count")
            ),
            "missing_regimes": list(
                audit.get("missing_regimes", []) or []
            ),
            "robustness": round(robustness, 4),
            "raw_robustness": round(raw_robustness, 4),
            "evidence_quality": round(evidence_quality, 4),
            "coverage": round(observational_coverage, 4),
            "novelty": round(novelty, 4),
            "predictive_value": round(predictive_value, 4),
            "predictive_value_role": "diagnostic_only",
            "score_model": "orthogonal_components_v5_metric_independence_calibrated",
            "score_weights": {
                key: round(value, 4)
                for key, value in score_weights.items()
            },
            "score_components": {
                key: round(value, 4)
                for key, value in score_components.items()
            },
            "score_contributions": {
                key: round(score_weights[key] * score_components[key], 4)
                for key in score_weights
            },
            "support_rules": support_rules,
            "counterexample_rules": sorted([
                ss(o.get("rule")) for o in counter_obs
            ]),
            "perturbation_status": perturbation_status,
            "perturbation_parent_count": perturbation_parent_count,
            "perturbation_run_count": perturbation_run_count,
            "perturbation_outcome_counts": dict(
                perturbation.get("outcome_counts", {}) or {}
            ),
            "consensus_context": consensus_context,
            "experimental_picture": consensus_context.get(
                "experimental_picture", "UNTESTED"
            ),
            "perturbation_picture": consensus_context.get(
                "perturbation_picture", "INSUFFICIENT"
            ),
            "evidence_gaps": list(
                consensus_context.get("evidence_gaps", []) or []
            ),
            "consensus_context_flags": context_flags,
            "score_effect_policy": {
                "evidence_profile_affects_score": False,
                "evidence_profile_affects_status": False,
            },
            "channel_interpretation": channel_interpretation,
            "channel_aware_status": channel_interpretation.get(
                "channel_aware_status"
            ),
            "confidence_posture": channel_interpretation.get(
                "confidence_posture"
            ),
            "interpretation_summary": channel_interpretation.get(
                "interpretation_summary"
            ),
            "action_signals": action_signals,
            "prioritized_actions": prioritized_actions,
            "action_signal_count": prioritized_actions.get(
                "active_signal_count", 0
            ),
            "raw_action_signal_count": prioritized_actions.get(
                "raw_signal_count", 0
            ),
            "blocked_action_signal_count": prioritized_actions.get(
                "blocked_signal_count", 0
            ),
            "highest_action_priority": prioritized_actions.get(
                "highest_priority", "NONE"
            ),
            "primary_action_signal": (
                prioritized_actions.get("primary_signal") or {}
            ).get("signal_type"),
        })

    reports.sort(
        key=lambda r: (
            sf(r.get("consensus_score")),
            si(r.get("support")),
            -si(r.get("counterexamples")),
        ),
        reverse=True,
    )
    interpretation_counts: dict[str, int] = {}
    action_signal_counts: dict[str, int] = {}
    principles_with_action_signals = 0
    for item in reports:
        label = ss(item.get("channel_aware_status"), "UNKNOWN")
        interpretation_counts[label] = (
            interpretation_counts.get(label, 0) + 1
        )
        bundle = item.get("prioritized_actions", {})
        if not isinstance(bundle, dict):
            bundle = {}
        primary = bundle.get("primary_signal")
        secondary = bundle.get("secondary_signals", [])
        signals = (
            ([primary] if isinstance(primary, dict) else [])
            + (
                secondary
                if isinstance(secondary, list)
                else []
            )
        )
        if signals:
            principles_with_action_signals += 1
        for signal in signals:
            signal_type = ss(signal.get("signal_type"), "unknown")
            action_signal_counts[signal_type] = (
                action_signal_counts.get(signal_type, 0) + 1
            )

    return {
        "schema": REPORT_SCHEMA,
        "generated": now_iso(),
        "principle_count": len(reports),
        "scientific_maturity": maturity,
        "channel_aware_status_counts": interpretation_counts,
        "action_signal_summary": {
            "principles_with_signals": principles_with_action_signals,
            "total_active_signals": sum(action_signal_counts.values()),
            "total_raw_signals": sum(
                si(item.get("raw_action_signal_count"))
                for item in reports
            ),
            "total_blocked_signals": sum(
                si(item.get("blocked_action_signal_count"))
                for item in reports
            ),
            "by_type": action_signal_counts,
            "policy": {
                "advisory_only": True,
                "automatic_execution": False,
                "director_priority_effect": False,
            },
        },
        "method": {
            "description": (
                "Consensus separates observed consistency from adversarial "
                "regime coverage. Their geometric mean forms robustness. "
                "Repeated-observation coverage, independent-seed coverage, "
                "and metric independence are combined multiplicatively without "
                "renormalizing away missing validation dimensions. Principles "
                "with entirely untested opposing regimes are capped at PROMISING; "
                "near-counterexample coverage permits SUPPORTED. Metric "
                "independence is calibrated per claim from an explicit "
                "structural audit of shared upstream signals and formula "
                "overlap. Controlled perturbations are reported as a "
                "separate causal-robustness channel and do not yet adjust the "
                "numerical consensus score. Stage 3.1 ingests Principle "
                "Evidence Profiles as channel-aware context. Their experimental "
                "and perturbation pictures, gaps, and tension flags do not "
                "change the numerical score or status. Stage 3.2 derives a "
                "separate channel-aware interpretation status and confidence "
                "posture from the preserved legacy status plus experimental "
                "and perturbation context. Stage 3.3 derives advisory "
                "Director-ready action signals from evidence gaps and "
                "channel-aware interpretation without executing or "
                "reprioritizing any research action. Stage 3.3.1 "
                "deduplicates signals by type, applies dependency rules, and "
                "selects one primary action plus ordered secondary and blocked "
                "actions for each principle."
            ),
            "status_caps": {
                "UNTESTED_REGIME": "PROMISING",
                "NEAR_COUNTEREXAMPLES_ONLY": "SUPPORTED",
                "COUNTEREXAMPLES_FOUND": "STRONG",
                "no_independent_seed_coverage": "STRONG",
            },
        },
        "principles": reports,
    }

