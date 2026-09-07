"""Pure Prediction Validation Engine rules ported from the protected legacy engine."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.scientific_claims import evaluate_claim

def stars(score: int) -> str:
    score = max(1, min(5, score))
    return "*" * score + "." * (5 - score)


def get_experiments(atlas: dict[str, Any]) -> list[dict[str, Any]]:
    return atlas.get("experiments", [])


def stable_world(e: dict[str, Any]) -> bool:
    return (
        (e.get("lifetime") or 0) >= 100000
        and (e.get("dynamic_score") or 0) >= 0.8
        and e.get("collapse") == "No"
    )


def has_turnover(e: dict[str, Any]) -> bool:
    events = (e.get("split_birth") or 0) + (e.get("merge_death") or 0)
    return events >= 20 and bool(e.get("objects"))


def weak_or_transient(e: dict[str, Any]) -> bool:
    return not stable_world(e)


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def rule_id(e: dict[str, Any]) -> str:
    raw = str(e.get("rule", "")).strip()
    return raw.zfill(5) if raw.isdigit() else raw or "unknown"


def canonical_rule_id(e: dict[str, Any], aliases: dict[str, str]) -> str:
    current = rule_id(e)
    seen: set[str] = set()
    while current in aliases and current not in seen:
        seen.add(current)
        current = aliases[current]
    return current




def experiment_seed(e: dict[str, Any]) -> str | None:
    """Return an explicit seed only; never invent one from timestamps or IDs."""
    for key in (
        "seed", "random_seed", "initial_seed", "world_seed",
        "observer_seed", "simulation_seed", "rng_seed",
    ):
        value = e.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"none", "unknown", "n/a"}:
            return text
    return None


def experiment_family(e: dict[str, Any]) -> str | None:
    for key in (
        "family", "behavioural_family", "behavioral_family",
        "analyzer_category", "template_category", "category",
    ):
        value = e.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"none", "unknown", "unclassified"}:
            return text
    return None


def cohort_statistics(
    items: list[dict[str, Any]],
    aliases: dict[str, str],
) -> dict[str, Any]:
    """Describe observational independence without treating runs as replicas."""
    rules = {canonical_rule_id(e, aliases) for e in items}
    rules.discard("unknown")

    seed_pairs: set[tuple[str, str]] = set()
    seed_observed_runs = 0
    families: set[str] = set()
    unknown_family_runs = 0
    for e in items:
        rid = canonical_rule_id(e, aliases)
        seed = experiment_seed(e)
        if seed is not None:
            seed_observed_runs += 1
            seed_pairs.add((rid, seed))
        family = experiment_family(e)
        if family is None:
            unknown_family_runs += 1
        else:
            families.add(family)

    run_count = len(items)
    return {
        "run_count": run_count,
        "unique_rule_count": len(rules),
        "canonical_rule_count": len(rules),
        "independent_seed_count": len(seed_pairs) if seed_observed_runs else None,
        "seed_observed_run_count": seed_observed_runs,
        "seed_coverage": round(seed_observed_runs / run_count, 4) if run_count else 0.0,
        "behavioural_family_count": len(families),
        "unknown_family_run_count": unknown_family_runs,
        "representative_profile_count": len(rules),
    }


def claim_evaluation(
    claim_id: str,
    experiment: dict[str, Any],
) -> tuple[str, float, str]:
    """Evaluate one Atlas experiment through the canonical claim registry."""
    return evaluate_claim(claim_id, experiment)


def claim_status(
    claim_id: str,
    experiment: dict[str, Any],
) -> str:
    return claim_evaluation(claim_id, experiment)[0]


def claim_members(
    claim_id: str,
    experiments: list[dict[str, Any]],
    status: str,
) -> list[dict[str, Any]]:
    return [
        experiment
        for experiment in experiments
        if claim_status(claim_id, experiment) == status
    ]


def validate_prediction(
    prediction: dict[str, Any],
    experiments: list[dict[str, Any]],
    aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    aliases = aliases or {}
    pid = prediction.get("id")
    result = {
        "id": pid,
        "based_on": prediction.get("based_on"),
        "prediction": prediction.get("prediction"),
        "status_before": prediction.get("status", "Open"),
        "status_after": "Open",
        "verdict": "Insufficient data",
        # Explicit scientific accounting. These fields must not be conflated:
        # - support_count: cases that satisfy the prediction outcome;
        # - negative_cohort_count: comparison-group members;
        # - claim_counterexample_count: canonical claim contradictions;
        # - failed_prediction_count: eligible cases where the expected outcome failed.
        "support_count": 0,
        "negative_cohort_count": 0,
        "claim_counterexample_count": 0,
        "failed_prediction_count": 0,
        # Legacy aliases are synchronized before returning.
        "support": 0,
        "counterexamples": 0,
        "evidence": [],
        "next_action": None,
    }

    stable = [e for e in experiments if stable_world(e)]
    turnover = [e for e in experiments if has_turnover(e)]
    weak = [e for e in experiments if weak_or_transient(e)]

    if pid == "P-001":
        # Success: at least 2 stable worlds excluding/including current Atlas.
        result["support_count"] = len(stable)
        result["_support_cases"] = stable
        result["evidence"].append(f"Stable worlds found: {len(stable)}")
        result["evidence"].append("Criteria: lifetime>=100k, dynamic_score>=0.8, collapse=No")

        if len(stable) >= 2:
            result["status_after"] = "Confirmed"
            result["verdict"] = "Confirmed by multiple stable worlds"
        elif len(stable) == 1:
            result["status_after"] = "Still testing"
            result["verdict"] = "Single supporting case only"
            result["next_action"] = "Add at least one more stable world candidate."
        else:
            result["status_after"] = "Open"
            result["verdict"] = "No supporting stable worlds yet"

    elif pid == "P-002":
        support_cases = [e for e in stable if has_turnover(e)]
        counter_cases = [e for e in stable if not has_turnover(e)]
        result["support_count"] = len(support_cases)
        result["claim_counterexample_count"] = len(counter_cases)
        result["_support_cases"] = support_cases
        result["_counterexample_cases"] = counter_cases
        result["evidence"].append(f"Stable worlds with turnover: {result['support_count']}")
        result["evidence"].append(f"Stable worlds without turnover: {result['claim_counterexample_count']}")

        if result["support_count"] >= 2 and result["claim_counterexample_count"] == 0:
            result["status_after"] = "Confirmed"
            result["verdict"] = "Stable worlds repeatedly show bounded turnover"
        elif result["support_count"] >= 1:
            result["status_after"] = "Still testing"
            result["verdict"] = "Supported by current case, needs replication"
            result["next_action"] = "Run more stable worlds with event tracking."
        else:
            result["status_after"] = "Open"
            result["verdict"] = "No turnover evidence yet"

    elif pid == "P-003":
        # Counterexample validation needs weak/transient worlds.
        result["support_count"] = len(weak)
        result["_support_cases"] = weak
        result["evidence"].append(f"Weak/transient worlds in atlas: {len(weak)}")

        if len(weak) >= 5:
            result["status_after"] = "Confirmed"
            result["verdict"] = "Counterexample set exists"
        elif len(weak) > 0:
            result["status_after"] = "Still testing"
            result["verdict"] = "Some counterexamples exist, not enough"
            result["next_action"] = "Add weak/transient worlds until count >= 5."
        else:
            result["status_after"] = "Open"
            result["verdict"] = "No counterexamples in atlas"
            result["next_action"] = "Analyze 5 weak/transient worlds."

    elif pid == "P-004":
        # Genome signature cannot be fully validated unless atlas stores mechanism/genome scores.
        # For now, infer indirectly from stable worlds and mechanism reports existing.
        result["support_count"] = len(stable)
        result["_support_cases"] = stable
        result["evidence"].append(f"Stable worlds available for genome comparison: {len(stable)}")
        result["status_after"] = "Still testing" if stable else "Open"
        result["verdict"] = "Needs genome/mechanism features stored in Atlas"
        result["next_action"] = "Add mechanism scores directly into Atlas records."

    elif pid == "P-005":
        links = 0
        for e in experiments:
            links += len(e.get("similar_to") or [])
        result["support_count"] = links
        # Similarity links are relations, not independent observational runs.
        result["evidence"].append(f"Similarity links in Atlas: {links}")

        if links >= 1:
            result["status_after"] = "Confirmed"
            result["verdict"] = "Atlas formed at least one similarity link"
        else:
            result["status_after"] = "Still testing"
            result["verdict"] = "No similarity links yet"
            result["next_action"] = "Add more experiments to create possible clusters."

    elif pid == "P-006":
        # Specific to rule 00251 long-run 250k.
        rule_251 = [e for e in experiments if str(e.get("rule")).zfill(5) == "00251"]
        best_lifetime = max([(e.get("lifetime") or 0) for e in rule_251], default=0)
        result["support_count"] = len(rule_251)
        result["_support_cases"] = rule_251
        result["evidence"].append(f"Rule 00251 records: {len(rule_251)}")
        result["evidence"].append(f"Best observed lifetime: {best_lifetime}")

        if best_lifetime >= 250000:
            result["status_after"] = "Confirmed"
            result["verdict"] = "Rule 00251 reached 250k ticks"
        elif best_lifetime >= 100000:
            result["status_after"] = "Still testing"
            result["verdict"] = "Rule 00251 passed 100k but not 250k yet"
            result["next_action"] = "Continue rule 00251 to 250k ticks."
        else:
            result["status_after"] = "Open"
            result["verdict"] = "Rule 00251 long-run not available"

    elif pid == "P-GP101-01":
        # Claim membership comes from scientific_claims.py. The high-EMG
        # count remains descriptive context for this prediction.
        high_emg = [e for e in experiments if fnum(e.get("emergence_score")) >= 0.65]
        supported = claim_members("GP-101", experiments, "support")
        counter = claim_members("GP-101", experiments, "counterexample")
        families = {
            str(e.get("family") or e.get("analyzer_category") or "unknown")
            for e in supported
        }
        result["support_count"] = len(supported)
        result["claim_counterexample_count"] = len(counter)
        result["_support_cases"] = supported
        result["_counterexample_cases"] = counter
        result["evidence"].extend([
            f"High-EMG worlds: {len(high_emg)}",
            f"High-EMG + high-validation worlds: {len(supported)}",
            f"High-EMG but weak-validation candidates: {len(counter)}",
            f"Supporting behavioural families: {len(families)}",
        ])

        if len(supported) >= 10 and len(families) >= 3 and len(counter) <= max(2, len(supported) // 5):
            result["status_after"] = "Confirmed"
            result["verdict"] = "Joint EMG+VAL criterion is supported across multiple families"
        elif len(supported) >= 3:
            result["status_after"] = "Still testing"
            result["verdict"] = "Preliminary cross-rule support, but family diversity is insufficient"
            result["next_action"] = "Add unrelated high-EMG rules with both high and low validation."
        else:
            result["status_after"] = "Open"
            result["verdict"] = "Insufficient high-EMG validated cases"
            result["next_action"] = "Collect at least 10 high-EMG candidates across 3 families."

    elif pid == "P-GP102-01":
        # Canonical claim support defines the joint group; canonical claim
        # counterexamples define genuine decoupling controls.
        joint = claim_members("GP-102", experiments, "support")
        mismatched = claim_members("GP-102", experiments, "counterexample")
        joint_lifetimes = [fnum(e.get("lifetime")) for e in joint]
        mismatch_lifetimes = [fnum(e.get("lifetime")) for e in mismatched]
        joint_mean = sum(joint_lifetimes) / len(joint_lifetimes) if joint_lifetimes else 0.0
        mismatch_mean = sum(mismatch_lifetimes) / len(mismatch_lifetimes) if mismatch_lifetimes else 0.0
        result["support_count"] = len(joint)
        result["negative_cohort_count"] = len(mismatched)
        result["claim_counterexample_count"] = len(mismatched)
        result["_support_cases"] = joint
        result["_negative_cases"] = mismatched
        result["_counterexample_cases"] = mismatched
        failed_joint = [
            e for e in joint
            if str(e.get("collapse")) not in {"No", "None", ""}
        ]
        result["failed_prediction_count"] = len(failed_joint)
        result["_failed_cases"] = failed_joint
        result["evidence"].extend([
            f"Joint high KNOW+FB worlds: {len(joint)}",
            f"Mismatched KNOW/FB controls: {len(mismatched)}",
            f"Mean joint-group lifetime: {joint_mean:.1f}",
            f"Mean mismatch-group lifetime: {mismatch_mean:.1f}",
            f"Collapsed joint-group worlds: {result['failed_prediction_count']}",
        ])

        if len(joint) >= 10 and len(mismatched) >= 5 and joint_mean > mismatch_mean * 1.20:
            result["status_after"] = "Confirmed"
            result["verdict"] = "Joint knowledge-feedback group shows stronger persistence"
        elif len(joint) >= 5:
            result["status_after"] = "Still testing"
            result["verdict"] = "Joint group exists, but matched control coverage is insufficient"
            result["next_action"] = "Search specifically for high-KNOW/low-FB and low-KNOW/high-FB worlds."
        else:
            result["status_after"] = "Open"
            result["verdict"] = "Too few joint knowledge-feedback cases"
            result["next_action"] = "Collect matched KNOW/FB groups."

    elif pid == "P-GP103-01":
        # Existing Atlas can establish the cohort, but cannot validate recovery
        # after perturbation because no standardized stress-test observations exist.
        cohort = claim_members("GP-103", experiments, "support")
        persistent = [
            e for e in cohort
            if fnum(e.get("lifetime")) >= 100000 and str(e.get("collapse")) == "No"
        ]
        claim_counterexamples = claim_members("GP-103", experiments, "counterexample")
        failed_persistence = [e for e in cohort if e not in persistent]
        result["support_count"] = len(persistent)
        result["claim_counterexample_count"] = len(claim_counterexamples)
        result["failed_prediction_count"] = len(failed_persistence)
        result["_support_cases"] = persistent
        result["_counterexample_cases"] = claim_counterexamples
        result["_failed_cases"] = failed_persistence
        result["evidence"].extend([
            f"Self-regulating/adaptive-loop worlds: {len(cohort)}",
            f"Long-lived no-collapse members: {len(persistent)}",
            f"Eligible cohort members without the predicted persistence outcome: {result['failed_prediction_count']}",
            f"Canonical GP-103 counterexamples: {result['claim_counterexample_count']}",
            "Standardized perturbation recovery data: 0",
        ])
        result["status_after"] = "Still testing" if cohort else "Open"
        result["verdict"] = (
            "Observational cohort exists, but perturbation recovery has not been measured"
            if cohort else
            "No self-regulating cohort available"
        )
        result["next_action"] = (
            "Apply identical perturbations to matched self-regulating and "
            "non-self-regulating worlds; record recovery time and post-stress stability."
        )

    elif pid == "P-GP105-01":
        scaffold = claim_members("GP-105", experiments, "support")
        no_scaffold = claim_members("GP-105", experiments, "counterexample")
        scaffold_valid = [
            e for e in scaffold if fnum(e.get("validation_quality")) >= 0.70
        ]
        result["support_count"] = len(scaffold_valid)
        result["negative_cohort_count"] = len(no_scaffold)
        result["claim_counterexample_count"] = len(no_scaffold)
        result["_support_cases"] = scaffold_valid
        result["_negative_cases"] = no_scaffold
        result["_counterexample_cases"] = no_scaffold
        result["evidence"].extend([
            f"High-CIV/high-KNOW worlds: {len(scaffold)}",
            f"Validated high-CIV/high-KNOW worlds: {len(scaffold_valid)}",
            f"High-CIV/low-KNOW counterexample candidates: {len(no_scaffold)}",
        ])

        if len(scaffold_valid) >= 10 and len(no_scaffold) == 0:
            result["status_after"] = "Still testing"
            result["verdict"] = "Strong positive support, but no negative cohort exists"
            result["next_action"] = "Search deliberately for high-CIV/low-KNOW worlds."
        elif len(scaffold_valid) >= 10 and len(no_scaffold) >= 3:
            result["status_after"] = "Confirmed"
            result["verdict"] = "Knowledge-supported civilization candidates outperform a negative cohort"
        elif scaffold_valid:
            result["status_after"] = "Still testing"
            result["verdict"] = "Preliminary support with insufficient sample size"
            result["next_action"] = "Expand both scaffold and no-scaffold cohorts."
        else:
            result["status_after"] = "Open"
            result["verdict"] = "No validated civilization-scaffold cases"
            result["next_action"] = "Collect high-CIV candidates and measure KNOW."

    else:
        result["status_after"] = "Open"
        result["verdict"] = "No validator implemented for this prediction"
        result["next_action"] = "Add validation rule."

    # Attach explicit independence statistics. Branches may provide the exact
    # case lists; otherwise counts remain available but statistics are based
    # on empty cohorts rather than fabricated identities.
    support_cases = result.pop("_support_cases", [])
    negative_cases = result.pop("_negative_cases", [])
    counterexample_cases = result.pop("_counterexample_cases", [])
    failed_cases = result.pop("_failed_cases", [])
    result["support_statistics"] = cohort_statistics(support_cases, aliases)
    result["negative_cohort_statistics"] = cohort_statistics(negative_cases, aliases)
    result["claim_counterexample_statistics"] = cohort_statistics(
        counterexample_cases, aliases
    )
    result["failed_prediction_statistics"] = cohort_statistics(
        failed_cases, aliases
    )

    # Backward-compatible aliases. From v2.2 onward, ``counterexamples``
    # means canonical claim contradictions only, never failed outcomes or
    # generic negative-cohort members.
    result["support"] = int(result.get("support_count", 0))
    result["counterexamples"] = int(
        result.get("claim_counterexample_count", 0)
    )
    return result

