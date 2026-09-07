"""Pure generation of stable persistent-prediction candidates."""
from __future__ import annotations

from typing import Any

from .values import confidence_value


def known_rules(atlas: dict[str, Any], kb: dict[str, Any]) -> set[str]:
    if isinstance(kb.get("rules"), dict):
        return {str(rule).zfill(5) for rule in kb["rules"]}

    experiments = atlas.get("experiments", []) if isinstance(atlas, dict) else []
    return {
        str(item.get("rule")).zfill(5)
        for item in experiments
        if isinstance(item, dict) and item.get("rule") is not None
    }


def rule_lifetime(kb: dict[str, Any], rule_id: str) -> int:
    rule = kb.get("rules", {}).get(rule_id, {})
    passport = rule.get("passport", {}) if isinstance(rule, dict) else {}
    atlas = rule.get("atlas", {}) if isinstance(rule, dict) else {}
    value = passport.get("lifetime")
    if value in (None, ""):
        value = atlas.get("lifetime")
    if value in (None, ""):
        value = 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def make_candidate(
    prediction_id: str,
    *,
    based_on: str,
    prediction: str,
    expected_observation: str,
    test: str,
    success_criteria: str,
    priority: int,
    confidence: str,
    target_rules: list[str] | None = None,
    principle_ids: list[str] | None = None,
    category: str = "scientific",
) -> dict[str, Any]:
    return {
        "id": prediction_id,
        "based_on": based_on,
        "principle_ids": principle_ids or [],
        "target_rules": target_rules or [],
        "category": category,
        "prediction": prediction,
        "expected_observation": expected_observation,
        "test": test,
        "success_criteria": success_criteria,
        "priority": int(priority),
        "confidence": confidence,
        "confidence_score": confidence_value(confidence),
        "status": "Open",
    }


def generate_candidates(
    atlas: dict[str, Any],
    kb: dict[str, Any],
    principles: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Generate deterministic, stable-ID candidates from current knowledge."""
    rules = known_rules(atlas, kb)
    principle_ids = set(principles)
    candidates: dict[str, dict[str, Any]] = {}

    def add(item: dict[str, Any]) -> None:
        candidates[item["id"]] = item

    add(make_candidate(
        "P-003",
        based_on="General validation / benchmark controls",
        principle_ids=["GP-104"] if "GP-104" in principle_ids else [],
        category="counterexample",
        prediction=(
            "Weak or transient worlds should lack at least one key signature: "
            "long lifetime, high dynamic score, or no-collapse stability."
        ),
        expected_observation=(
            "Benchmark-control worlds should have lower research value, "
            "weaker emergence evidence, or earlier collapse."
        ),
        test=(
            "Analyze at least five weak, transient, collapsed, or decorative worlds "
            "with the same observer configuration used for strong candidates."
        ),
        success_criteria=(
            "At least four of five controls fail the stable-attractor criteria."
        ),
        priority=4,
        confidence="MEDIUM",
    ))

    add(make_candidate(
        "P-005",
        based_on="Atlas similarity",
        category="clustering",
        prediction=(
            "As more experiments are added, credible long-lived worlds should "
            "form recurring behavioural-family clusters rather than isolated singletons."
        ),
        expected_observation=(
            "Multiple high-value worlds should have reproducible similarity links."
        ),
        test="Recompute Atlas similarity after every substantial batch of new worlds.",
        success_criteria=(
            "At least one stable high-value cluster contains two or more rules "
            "with similarity >= 0.65."
        ),
        priority=3,
        confidence="LOW",
    ))

    if "00251" in rules:
        add(make_candidate(
            "P-006",
            based_on="Rule 00251 long-run",
            target_rules=["00251"],
            category="long_run",
            prediction=(
                "Rule 00251 should remain a strong candidate at 250k ticks "
                "if its observed behaviour is a true attractor."
            ),
            expected_observation=(
                "A passport at or beyond 250k ticks should show no collapse "
                "and bounded object turnover."
            ),
            test="Continue Rule 00251 to at least 250k ticks and save a passport.",
            success_criteria=(
                "Collapse = No, object range remains bounded, and dynamic "
                "classification remains stable."
            ),
            priority=5,
            confidence="LOW-MEDIUM",
        ))

    if "GP-101" in principle_ids:
        add(make_candidate(
            "P-GP101-01",
            based_on="GP-101: Validated emergence criterion",
            principle_ids=["GP-101"],
            category="replication",
            prediction=(
                "High emergence scores will remain credible only when observer "
                "validation is also high across unrelated rule families."
            ),
            expected_observation=(
                "Replicated high-EMG worlds with weak validation will show more "
                "false positives than worlds high on both EMG and VAL."
            ),
            test=(
                "Sample high-EMG candidates from at least three unrelated families "
                "and compare high-VAL versus low-VAL cases."
            ),
            success_criteria=(
                "The joint EMG+VAL criterion separates credible organization from "
                "controls better than EMG alone."
            ),
            priority=5,
            confidence="MEDIUM-HIGH",
        ))

    if "GP-102" in principle_ids:
        add(make_candidate(
            "P-GP102-01",
            based_on="GP-102: Knowledge-feedback coupling",
            principle_ids=["GP-102"],
            category="mechanism",
            prediction=(
                "Worlds where knowledge-like structure and adaptive feedback rise "
                "together will persist longer than worlds where only one rises."
            ),
            expected_observation=(
                "Joint high KNOW+FB worlds should have greater lifetime and lower "
                "collapse frequency than mismatched cases."
            ),
            test=(
                "Construct matched groups: high KNOW/high FB, high KNOW/low FB, "
                "low KNOW/high FB, and low/low."
            ),
            success_criteria=(
                "The joint-high group has the strongest persistence distribution."
            ),
            priority=5,
            confidence="MEDIUM-HIGH",
        ))

    if "GP-103" in principle_ids:
        add(make_candidate(
            "P-GP103-01",
            based_on="GP-103: Self-regulation marker",
            principle_ids=["GP-103"],
            category="mechanism",
            prediction=(
                "SELF_REGULATING or ADAPTIVE_LOOP feedback regimes will predict "
                "longer persistence after controlled perturbations."
            ),
            expected_observation=(
                "Self-regulating worlds should recover more often and lose less "
                "organization after equal disturbances."
            ),
            test=(
                "Apply standardized perturbations to matched self-regulating and "
                "non-self-regulating worlds."
            ),
            success_criteria=(
                "Recovery probability and post-stress stability are higher in the "
                "self-regulating group."
            ),
            priority=5,
            confidence="MEDIUM",
        ))

    if "GP-105" in principle_ids:
        add(make_candidate(
            "P-GP105-01",
            based_on="GP-105: Civilization requires knowledge scaffold",
            principle_ids=["GP-105"],
            category="classification",
            prediction=(
                "High civilization-like scores without a knowledge scaffold will "
                "be less stable and less reproducible than high-CIV/high-KNOW worlds."
            ),
            expected_observation=(
                "Structure-only civilization candidates should fail replication or "
                "show weaker long-term coordination."
            ),
            test=(
                "Search specifically for high-CIV/low-KNOW counterexamples and "
                "compare them with high-CIV/high-KNOW candidates."
            ),
            success_criteria=(
                "Knowledge-supported candidates have higher validation and persistence."
            ),
            priority=4,
            confidence="MEDIUM",
        ))

    return candidates


__all__ = [
    "generate_candidates",
    "known_rules",
    "make_candidate",
    "rule_lifetime",
]
