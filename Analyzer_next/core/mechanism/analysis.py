"""Deterministic genome projection and mechanism inference."""
from __future__ import annotations

from collections import Counter
from typing import Any


def classify_low_mid_high(
    value: float,
    low: float,
    high: float,
    reverse: bool = False,
) -> str:
    if reverse:
        if value <= low:
            return "High"
        if value >= high:
            return "Low"
        return "Medium"
    if value < low:
        return "Low"
    if value > high:
        return "High"
    return "Medium"


def analyze_rule_genome(rule: dict[str, Any]) -> dict[str, Any]:
    terms = rule.get("terms", []) or []
    kinds = Counter(term.get("kind", "unknown") for term in terms)

    weights = [float(term.get("weight", 0.0)) for term in terms]
    freqs = [float(term.get("freq", 0.0)) for term in terms]
    widths = [float(term.get("width", 0.0)) for term in terms]

    damping = float(rule.get("damping", 0.0))
    noise = float(rule.get("noise", 0.0))
    decay = float(rule.get("decay", 0.0))
    diffusion = float(rule.get("diffusion", 0.0))
    inertia = float(rule.get("inertia", 0.0))
    spatial = {
        "w_avg_r1": float(rule.get("w_avg_r1", 0.0)),
        "w_avg_r4": float(rule.get("w_avg_r4", 0.0)),
        "w_avg_r12": float(rule.get("w_avg_r12", 0.0)),
        "w_var_r1": float(rule.get("w_var_r1", 0.0)),
        "w_var_r4": float(rule.get("w_var_r4", 0.0)),
        "w_lap_r1": float(rule.get("w_lap_r1", 0.0)),
        "w_lap_r4": float(rule.get("w_lap_r4", 0.0)),
    }
    genome = {
        "rule_id": str(rule.get("rule_id", "unknown")).zfill(5),
        "parents": [rule.get("parent_a"), rule.get("parent_b")],
        "seed": rule.get("seed"),
        "diffusion": diffusion,
        "inertia": inertia,
        "damping": damping,
        "decay": decay,
        "noise": noise,
        "bias": float(rule.get("bias", 0.0)),
        "sharpen": float(rule.get("sharpen", 0.0)),
        "threshold_push": float(rule.get("threshold_push", 0.0)),
        "spatial": spatial,
        "term_count": len(terms),
        "term_kinds": dict(kinds),
        "positive_terms": sum(1 for weight in weights if weight > 0),
        "negative_terms": sum(1 for weight in weights if weight < 0),
        "mean_abs_weight": (
            sum(abs(weight) for weight in weights) / len(weights)
            if weights
            else 0.0
        ),
        "mean_freq": sum(freqs) / len(freqs) if freqs else 0.0,
        "mean_width": sum(widths) / len(widths) if widths else 0.0,
        "memory_level": classify_low_mid_high(damping, 0.98, 0.995),
        "noise_level": classify_low_mid_high(
            noise, 1e-5, 1e-3, reverse=True
        ),
        "decay_level": classify_low_mid_high(
            decay, 0.02, 0.08, reverse=True
        ),
        "diffusion_level": classify_low_mid_high(diffusion, 0.03, 0.12),
        "inertia_level": classify_low_mid_high(inertia, 0.2, 0.6),
        "multi_scale_strength": sum(
            abs(value)
            for key, value in spatial.items()
            if "r4" in key or "r12" in key
        ),
        "local_strength": sum(
            abs(value) for key, value in spatial.items() if "r1" in key
        ),
    }
    genome["field_memory_score"] = round(
        min(1.0, max(0.0, (damping - 0.95) / 0.05)) * 0.7
        + min(1.0, max(0.0, (0.05 - decay) / 0.05)) * 0.3,
        3,
    )
    genome["stochastic_stability_score"] = round(
        1.0 - min(noise / 0.001, 1.0), 3
    )
    genome["oscillatory_feedback_score"] = round(
        min(
            (
                kinds.get("sin", 0)
                + kinds.get("cos", 0)
                + kinds.get("ring", 0)
            )
            / 5.0,
            1.0,
        ),
        3,
    )
    genome["multi_scale_score"] = round(
        min(genome["multi_scale_strength"] / 0.8, 1.0), 3
    )
    genome["genome_complexity_score"] = round(
        min(len(terms) / 8.0, 1.0) * 0.4
        + min(len(kinds) / 4.0, 1.0) * 0.3
        + min(genome["multi_scale_strength"] / 0.8, 1.0) * 0.3,
        3,
    )
    return genome


def infer_mechanisms(
    genome: dict[str, Any],
    behaviour: dict[str, Any],
) -> list[dict[str, Any]]:
    mechanisms: list[dict[str, Any]] = []

    def add(
        mechanism_id: str,
        title: str,
        confidence: str,
        claim: str,
        evidence: list[str],
        link: str,
    ) -> None:
        mechanisms.append({
            "id": mechanism_id,
            "title": title,
            "confidence": confidence,
            "claim": claim,
            "evidence": evidence,
            "behaviour_link": link,
        })

    if genome["field_memory_score"] >= 0.8:
        add(
            "M-001",
            "Field memory preservation",
            "Medium",
            "High damping combined with low decay may allow structures to persist across many updates.",
            [
                f"damping={genome['damping']:.6f}",
                f"decay={genome['decay']:.6f}",
                f"field_memory_score={genome['field_memory_score']:.3f}",
            ],
            "Consistent with long lifetime if the observed world does not collapse.",
        )
    if genome["stochastic_stability_score"] >= 0.95:
        add(
            "M-002",
            "Low stochastic disruption",
            "Medium",
            "Very low noise may prevent persistent structures from being destroyed by random perturbation.",
            [
                f"noise={genome['noise']:.10f}",
                f"stochastic_stability_score={genome['stochastic_stability_score']:.3f}",
            ],
            "Consistent with stable long-run morphology.",
        )
    if genome["multi_scale_score"] >= 0.5:
        add(
            "M-003",
            "Multi-scale spatial feedback",
            "Low-Medium",
            "Interactions at multiple radii may help create scaffold-like structures instead of purely local noise.",
            [
                f"multi_scale_strength={genome['multi_scale_strength']:.3f}",
                f"local_strength={genome['local_strength']:.3f}",
                "spatial terms include r1, r4 and r12 channels",
            ],
            "May explain large-scale rails/scaffolds observed visually.",
        )
    if genome["oscillatory_feedback_score"] >= 0.8:
        add(
            "M-004",
            "Oscillatory / ring feedback",
            "Low-Medium",
            "Sin/cos/ring terms may create recurring activation windows and breathing-like turnover.",
            [
                f"term_kinds={genome['term_kinds']}",
                f"oscillatory_feedback_score={genome['oscillatory_feedback_score']:.3f}",
            ],
            "Consistent with split/merge turnover and breathing score.",
        )
    if genome["genome_complexity_score"] >= 0.7:
        add(
            "M-005",
            "Moderate-high rule genome complexity",
            "Low",
            "A mixture of nonlinear terms may support richer behaviour than a simple single-threshold rule.",
            [
                f"term_count={genome['term_count']}",
                f"term_kinds={genome['term_kinds']}",
                f"genome_complexity_score={genome['genome_complexity_score']:.3f}",
            ],
            "May support multiple behavioural regimes in the same world.",
        )

    lifetime = behaviour.get("lifetime") or 0
    dynamic = behaviour.get("dynamic_score") or 0.0
    collapse = behaviour.get("collapse")
    if lifetime >= 100000 and dynamic >= 0.8 and collapse == "No":
        for mechanism in mechanisms:
            if mechanism["id"] in {"M-001", "M-002", "M-003", "M-004"}:
                mechanism["confidence"] = "Medium"
    return mechanisms
