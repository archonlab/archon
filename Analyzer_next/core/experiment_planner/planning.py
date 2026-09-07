"""Pure scientific planning policy for Experiment Planner Engine v4.4."""
from __future__ import annotations

import json
import re
from typing import Any

ENGINE_VERSION = "Universe Search Experiment Planner Engine v4.4"


CLAIM_INTERVENTIONS: dict[str, dict[str, Any]] = {
    "GP-101": {
        "parameters": ["diffusion", "noise", "threshold_push", "sharpen"],
        "endpoints": [
            "emergence_score",
            "validation_quality",
            "validation_false_positive_risk",
            "validation_false_negative_risk",
        ],
        "question": (
            "Which perturbations separate genuine validated emergence from "
            "visual complexity or validation failure?"
        ),
    },
    "GP-102": {
        "parameters": ["diffusion", "inertia", "damping", "w_avg_r4"],
        "endpoints": [
            "knowledge_score",
            "feedback_score",
            "knowledge_transfer",
            "feedback_knowledge_impact",
            "feedback_regime",
        ],
        "question": (
            "Which perturbations preserve or decouple knowledge accumulation "
            "and feedback?"
        ),
    },
    "GP-103": {
        "parameters": ["inertia", "damping", "decay", "noise"],
        "endpoints": [
            "feedback_score",
            "feedback_self_direction",
            "feedback_effective_pressure",
            "feedback_effective_risk",
            "evo_recovery",
        ],
        "question": (
            "Which perturbations preserve self-regulation and which destroy "
            "risk reduction or recovery?"
        ),
    },
    "GP-104": {
        "parameters": ["sharpen", "threshold_push", "diffusion", "decay"],
        "endpoints": [
            "emergence_score",
            "validation_quality",
            "total_living_mass",
            "peak_objects",
            "post_collapse_structure",
        ],
        "question": (
            "Which perturbations make pattern richness diverge from evidence "
            "of living or persistent organization?"
        ),
    },
    "GP-105": {
        "parameters": ["inertia", "noise", "diffusion", "w_avg_r12"],
        "endpoints": [
            "civ_score",
            "knowledge_score",
            "knowledge_transfer",
            "civ_stage",
            "knowledge_dominant_axis",
        ],
        "question": (
            "Can civilization-like organization persist after its knowledge "
            "scaffold is weakened?"
        ),
    },
    "GP-201": {
        "parameters": ["inertia", "damping", "noise", "diffusion"],
        "endpoints": [
            "knowledge_memory",
            "stability_index",
            "identity_persistence",
            "information_survival",
            "evo_recovery",
        ],
        "question": (
            "Does memory remain associated with stability and recovery under "
            "controlled perturbation?"
        ),
    },
}

PERTURBATION_TARGETS = {
    "MIXED_PERTURBATION_RESPONSE": {
        "parents": 4,
        "priority": 5,
        "goal": "resolve_direction_boundary",
        "required_outcomes": {
            "corroborating_parent_rules": 2,
            "challenging_parent_rules": 2,
        },
    },
    "INSUFFICIENT_CLAIM_SIGNAL": {
        "parents": 3,
        "priority": 5,
        "goal": "create_direct_claim_signal",
        "required_outcomes": {
            "informative_parent_rules": 2,
        },
    },
    "CHALLENGE_SIGNAL_SINGLE_PARENT": {
        "parents": 3,
        "priority": 5,
        "goal": "replicate_challenge_across_parents",
        "required_outcomes": {
            "challenging_parent_rules": 2,
        },
    },
    "ROBUSTNESS_SIGNAL_SINGLE_PARENT": {
        "parents": 3,
        "priority": 4,
        "goal": "replicate_robustness_across_parents",
        "required_outcomes": {
            "corroborating_parent_rules": 2,
        },
    },
    "COUNTEREXAMPLE_PERSISTS": {
        "parents": 3,
        "priority": 5,
        "goal": "test_counterexample_generality",
        "required_outcomes": {
            "persistent_counterexample_parent_rules": 2,
        },
    },
    "CHALLENGED_ACROSS_PARENTS": {
        "parents": 4,
        "priority": 4,
        "goal": "map_challenge_boundary",
        "required_outcomes": {
            "challenging_parent_rules": 3,
        },
    },
    "ROBUST_ACROSS_PARENTS": {
        "parents": 4,
        "priority": 3,
        "goal": "probe_robustness_limit",
        "required_outcomes": {
            "corroborating_parent_rules": 3,
        },
    },
}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def stars(score: int) -> str:
    score = max(1, min(5, int(score)))
    return "*" * score + "." * (5 - score)


def normalize_status(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "confirmed": "Confirmed",
        "passed": "Confirmed",
        "supported": "Confirmed",
        "still_testing": "Still testing",
        "testing": "Still testing",
        "in_progress": "Still testing",
        "open": "Open",
        "rejected": "Rejected",
        "failed": "Rejected",
        "inconclusive": "Inconclusive",
    }
    return aliases.get(raw, str(value or "Open"))


def add_task(
    tasks: list[dict[str, Any]],
    *,
    task_id: str,
    title: str,
    priority: int,
    experiment_type: str,
    target_rules: list[str],
    based_on_prediction: str | None,
    reason: str,
    tests: list[str],
    expected_gain: str,
    success_criteria: str,
) -> None:
    tasks.append({
        "id": task_id,
        "title": title,
        "priority": priority,
        "type": experiment_type,
        "target_rules": target_rules,
        "based_on_prediction": based_on_prediction,
        "reason": reason,
        "tests": tests,
        "expected_information_gain": expected_gain,
        "success_criteria": success_criteria,
        "status": "Planned",
    })


def task_from_validation(
    validation: dict[str, Any],
    prediction: dict[str, Any],
) -> dict[str, Any] | None:
    pid = str(validation.get("id") or prediction.get("id") or "")
    status = normalize_status(validation.get("status_after") or prediction.get("status"))

    if status in {"Confirmed", "Rejected"}:
        return None

    next_action = str(validation.get("next_action") or "").strip()
    verdict = str(validation.get("verdict") or "Unresolved prediction").strip()
    target_rules = [
        str(rule).zfill(5)
        for rule in (prediction.get("target_rules") or [])
        if str(rule).strip()
    ]

    mappings = {
        "P-GP101-01": {
            "id": "EXP-GP101",
            "title": "Expand cross-family EMG and validation sample",
            "priority": 5,
            "type": "cross_family_replication",
            "tests": [
                "Select high-EMG candidates from at least three unrelated behavioural families.",
                "Include both high-VAL and low-VAL cases.",
                "Run identical observer settings for every selected rule.",
                "Compare false-positive rate of EMG alone against joint EMG+VAL.",
            ],
            "gain": "Very high: tests whether validated emergence generalizes beyond one family.",
            "success": "At least 10 high-EMG rules across 3 families, with a usable high-VAL/low-VAL contrast.",
        },
        "P-GP102-01": {
            "id": "EXP-GP102",
            "title": "Build matched knowledge-feedback control groups",
            "priority": 5,
            "type": "matched_control_study",
            "tests": [
                "Find high-KNOW/high-FB worlds.",
                "Find high-KNOW/low-FB controls.",
                "Find low-KNOW/high-FB controls.",
                "Compare lifetime, collapse rate, and post-run stability across groups.",
            ],
            "gain": "Very high: directly tests whether KNOW and FB act jointly rather than independently.",
            "success": "Each comparison group contains enough cases for a meaningful persistence comparison.",
        },
        "P-GP103-01": {
            "id": "EXP-GP103",
            "title": "Run standardized perturbation recovery test",
            "priority": 5,
            "type": "perturbation_test",
            "tests": [
                "Select matched self-regulating and non-self-regulating worlds.",
                "Apply the same perturbation strength and geometry.",
                "Measure recovery time, morphology loss, and post-stress survival.",
                "Repeat each perturbation at least three times.",
            ],
            "gain": "Very high: converts a correlation into a causal stress-response test.",
            "success": "Self-regulating worlds show higher recovery probability or lower post-stress damage.",
        },
        "P-GP105-01": {
            "id": "EXP-GP105",
            "title": "Search for high-CIV low-KNOW counterexamples",
            "priority": 4,
            "type": "negative_cohort_search",
            "tests": [
                "Search Atlas and new runs for high civilization score with low knowledge score.",
                "Observe candidates long enough to assess persistence and reproducibility.",
                "Compare against high-CIV/high-KNOW worlds.",
            ],
            "gain": "High: tests whether the knowledge scaffold is necessary or merely correlated.",
            "success": "A negative cohort is found, or the search documents its persistent absence across a larger sample.",
        },
        "P-003": {
            "id": "EXP-P003",
            "title": "Expand benchmark-control library",
            "priority": 4,
            "type": "benchmark_control",
            "tests": [
                "Select collapsed, weak, transient, and decorative worlds.",
                "Run them through the same observer and Analyzer configuration.",
                "Compare their emergence, validation, mechanism, and persistence scores.",
            ],
            "gain": "High: protects the laboratory against false positives.",
            "success": "At least five diverse controls are stored and reproducibly fail strong-candidate criteria.",
        },
        "P-005": {
            "id": "EXP-P005",
            "title": "Strengthen behavioural similarity clusters",
            "priority": 3,
            "type": "cluster_replication",
            "tests": [
                "Add new worlds from several rule families.",
                "Recompute Atlas similarity.",
                "Check whether existing links remain stable after the sample grows.",
            ],
            "gain": "Medium-high: tests whether observed clusters are robust or accidental.",
            "success": "At least one multi-rule cluster remains stable across successive Atlas updates.",
        },
        "P-006": {
            "id": "EXP-P006",
            "title": "Continue Rule 00251 long run",
            "priority": 5,
            "type": "long_run_replication",
            "tests": [
                "Continue Rule 00251 to the requested lifetime.",
                "Save a new passport.",
                "Rerun prediction validation.",
            ],
            "gain": "High: directly tests long-term attractor persistence.",
            "success": "The requested lifetime is reached without collapse.",
        },
    }

    spec = mappings.get(pid)
    if spec is None:
        return {
            "id": f"EXP-{pid or 'UNRESOLVED'}",
            "title": f"Resolve {pid or 'unidentified prediction'}",
            "priority": int(prediction.get("priority") or 3),
            "type": "prediction_followup",
            "target_rules": target_rules,
            "based_on_prediction": pid or None,
            "reason": verdict,
            "tests": [next_action or "Design and run the missing validation experiment."],
            "expected_information_gain": "Unknown until the missing validator or experiment is specified.",
            "success_criteria": str(prediction.get("success_criteria") or "Prediction becomes testable."),
            "status": "Planned",
        }

    return {
        "id": spec["id"],
        "title": spec["title"],
        "priority": spec["priority"],
        "type": spec["type"],
        "target_rules": target_rules,
        "based_on_prediction": pid,
        "reason": verdict,
        "tests": spec["tests"],
        "expected_information_gain": spec["gain"],
        "success_criteria": spec["success"],
        "status": "Planned",
    }


def mechanism_coverage_task(kb: dict[str, Any]) -> dict[str, Any] | None:
    summary = kb.get("summary", {})
    rules = int(summary.get("rules") or 0)
    rules_with_mechanisms = int(summary.get("rules_with_mechanisms") or 0)

    if rules <= 0 or rules_with_mechanisms >= rules:
        return None

    missing = rules - rules_with_mechanisms
    return {
        "id": "EXP-INFRA-MECH",
        "title": "Increase mechanism-report coverage",
        "priority": 4,
        "type": "infrastructure_upgrade",
        "target_rules": ["rules without mechanism reports"],
        "based_on_prediction": None,
        "reason": (
            f"Knowledge Base contains mechanism reports for only "
            f"{rules_with_mechanisms}/{rules} rules."
        ),
        "tests": [
            "Generate mechanism reports for high-value rules that currently lack them.",
            "Prioritize rules used by open predictions.",
            "Rebuild Knowledge Base and verify mechanism relations.",
        ],
        "expected_information_gain": "High: improves mechanism-level comparison and future causal validation.",
        "success_criteria": "Mechanism coverage rises substantially and all new links pass integrity checks.",
        "status": "Planned",
    }


def build_plan(
    kb: dict[str, Any],
    validations: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for validation in validations:
        pid = str(validation.get("id") or "")
        prediction = predictions.get(pid, {})
        task = task_from_validation(validation, prediction)
        if task and task["id"] not in seen_ids:
            tasks.append(task)
            seen_ids.add(task["id"])

    infra = mechanism_coverage_task(kb)
    if infra and infra["id"] not in seen_ids:
        tasks.append(infra)

    return sorted(
        tasks,
        key=lambda item: (
            int(item.get("priority", 0)),
            item.get("based_on_prediction") is not None,
            item.get("id", ""),
        ),
        reverse=True,
    )



def slug(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw or "target"


def normalize_rule_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if text.isdigit():
            if int(text) <= 0:
                continue
            text = text.zfill(5)
        if text not in result:
            result.append(text)
    return result


def build_cohort_jobs(
    cohort_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    targets = cohort_payload.get("targets", [])
    if not isinstance(targets, list):
        return [], [], []

    search_jobs: list[dict[str, Any]] = []
    mutation_jobs: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []

    for target in targets:
        if not isinstance(target, dict):
            continue
        status = str(target.get("status") or "")
        if status == "EXACT_COHORT_AVAILABLE":
            continue

        claim_id = str(target.get("claim_id") or "UNSPECIFIED")
        target_name = str(target.get("target_name") or "unnamed_target")
        constraints = target.get("constraints", {})
        seed_rules = normalize_rule_list(target.get("best_near_rules"))
        candidates = target.get("best_near_candidates", [])
        priority = int(target.get("priority") or 2)
        job_slug = f"{claim_id.lower()}-{slug(target_name)}"

        search_job_id = f"SEARCH-{job_slug.upper()}"
        mutation_job_id = f"MUTATE-{job_slug.upper()}"

        search_jobs.append({
            "id": search_job_id,
            "job_type": "search",
            "search_mode": str(
                target.get("recommended_search_mode") or "cohort_target"
            ),
            "claim_id": claim_id,
            "target_regime": target_name,
            "constraints": constraints,
            "seed_rules": seed_rules,
            "priority": priority,
            "output_policy": {
                "creates_canonical_rules": True,
                "preserve_parent_rules": True,
                "record_provenance": True,
            },
            "status": "Planned",
        })

        mutation_jobs.append({
            "id": mutation_job_id,
            "job_type": "observer_mutation",
            "mutation_mode": str(
                target.get("recommended_mutation_mode")
                or "cohort_directed"
            ),
            "claim_id": claim_id,
            "target_regime": target_name,
            "constraints": constraints,
            "parent_rules": seed_rules,
            "candidate_diagnostics": (
                candidates if isinstance(candidates, list) else []
            ),
            "priority": priority,
            "isolation_policy": {
                "modify_original_rule": False,
                "canonical_rule_created_automatically": False,
                "write_original_snapshot": True,
                "write_mutated_rule": True,
                "write_mutation_diff": True,
                "output_root": (
                    "Results/Universe_Search/mutation_runs/"
                    "<parent_rule>/<mutation_id>/"
                ),
                "promotion_required": True,
            },
            "status": "Planned",
        })

        tasks.append({
            "id": f"EXP-COHORT-{job_slug.upper()}",
            "title": f"Fill cohort regime: {claim_id} / {target_name}",
            "priority": max(3, 6 - priority),
            "type": "cohort_gap_program",
            "target_rules": seed_rules,
            "based_on_prediction": claim_id,
            "reason": (
                f"Cohort Builder reports {status} for {target_name}. "
                "The search and mutation branches are kept separate."
            ),
            "tests": [
                f"Run Search in cohort_target mode for {target_name}.",
                "Create new canonical rules only from Search results.",
                "Run isolated Observer mutations around the nearest parent rules.",
                "Do not alter or overwrite any Atlas parent rule.",
                "Promote a mutation only after reproducible validation.",
            ],
            "expected_information_gain": (
                "High: targets a missing or near-missing scientific regime "
                "without mixing discovery with intervention."
            ),
            "success_criteria": (
                "At least one reproducible exact cohort member is found, "
                "or the expanded search documents persistent absence."
            ),
            "status": "Planned",
        })

    return search_jobs, mutation_jobs, tasks


def claim_items(payload: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    items = payload.get(key, []) if isinstance(payload, dict) else []
    if isinstance(items, dict):
        return {
            str(cid): item
            for cid, item in items.items()
            if isinstance(item, dict)
        }
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("id") or item.get("claim_id")): item
        for item in items
        if isinstance(item, dict)
        and (item.get("id") or item.get("claim_id"))
    }


def perturbation_claims(
    evidence_payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    claims = claim_items(evidence_payload, "claims")
    return {
        cid: (
            item.get("perturbation_evidence", {})
            if isinstance(item.get("perturbation_evidence"), dict)
            else {}
        )
        for cid, item in claims.items()
    }


def cohort_parent_candidates(
    cohort_payload: dict[str, Any],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    targets = cohort_payload.get("targets", [])
    if not isinstance(targets, list):
        return result
    for target in targets:
        if not isinstance(target, dict):
            continue
        cid = str(target.get("claim_id") or "")
        if not cid:
            continue
        for rid in normalize_rule_list([
            *(
                target.get("exact_rules")
                if isinstance(target.get("exact_rules"), list)
                else []
            ),
            *(
                target.get("best_near_rules")
                if isinstance(target.get("best_near_rules"), list)
                else []
            ),
        ]):
            if rid not in result.setdefault(cid, []):
                result[cid].append(rid)
    return result


def outcome_parent_sets(
    perturbation: dict[str, Any],
) -> dict[str, list[str]]:
    groups = {
        "corroborating_parent_rules": set(),
        "challenging_parent_rules": set(),
        "persistent_counterexample_parent_rules": set(),
        "informative_parent_rules": set(),
    }
    corroborating = {
        "preserved_support",
        "induced_support",
        "counterexample_resolved",
    }
    challenging = {"disrupted_support", "induced_counterexample"}
    for case in perturbation.get("cases", []) or []:
        if not isinstance(case, dict):
            continue
        rid = str(case.get("parent_rule_id") or "").strip()
        outcome = str(case.get("outcome") or "")
        if not rid or outcome == "no_claim_transition":
            continue
        rid = rid.zfill(5) if rid.isdigit() else rid
        groups["informative_parent_rules"].add(rid)
        if outcome in corroborating:
            groups["corroborating_parent_rules"].add(rid)
        if outcome in challenging:
            groups["challenging_parent_rules"].add(rid)
        if outcome == "preserved_counterexample":
            groups["persistent_counterexample_parent_rules"].add(rid)
    return {
        key: sorted(values)
        for key, values in groups.items()
    }



def outcome_resolution_state(
    status: str,
    outcome_groups: dict[str, list[str]],
    required_outcomes: dict[str, int],
) -> dict[str, Any]:
    """Separate parent coverage from scientific outcome resolution.

    Parent coverage answers whether enough independent canonical parents have
    been tested. Outcome resolution answers whether the required directional
    evidence exists. MIXED_PERTURBATION_RESPONSE remains unresolved even when
    the minimum corroborating/challenging counts are present because the next
    experiment must map or replicate the transition boundary.
    """
    observed = {
        key: len(set(outcome_groups.get(key, [])))
        for key in required_outcomes
    }
    gaps = {
        key: max(0, int(required) - observed.get(key, 0))
        for key, required in required_outcomes.items()
    }
    requirements_met = all(gap == 0 for gap in gaps.values())
    boundary_unresolved = status == "MIXED_PERTURBATION_RESPONSE"
    complete = requirements_met and not boundary_unresolved
    return {
        "complete": complete,
        "requirements_met": requirements_met,
        "boundary_unresolved": boundary_unresolved,
        "observed_parent_counts": observed,
        "required_parent_counts": {
            key: int(value) for key, value in required_outcomes.items()
        },
        "outcome_gaps": gaps,
    }


def boundary_replication_parents(
    outcome_groups: dict[str, list[str]],
    tested_parents: list[str],
    *,
    limit: int = 4,
) -> list[str]:
    """Choose already-tested parents that discriminate opposing outcomes."""
    selected: list[str] = []
    groups = (
        outcome_groups.get("corroborating_parent_rules", []),
        outcome_groups.get("challenging_parent_rules", []),
        outcome_groups.get("persistent_counterexample_parent_rules", []),
        outcome_groups.get("informative_parent_rules", []),
        tested_parents,
    )
    # Round-robin keeps opposing outcome classes represented rather than
    # filling the list from only the largest group.
    max_len = max((len(group) for group in groups), default=0)
    for index in range(max_len):
        for group in groups:
            if index >= len(group):
                continue
            rid = group[index]
            if rid not in selected:
                selected.append(rid)
            if len(selected) >= limit:
                return selected
    return selected

def observed_parameter_priority(
    perturbation: dict[str, Any],
    defaults: list[str],
) -> list[str]:
    counts: dict[str, int] = {}
    for case in perturbation.get("cases", []) or []:
        if not isinstance(case, dict):
            continue
        parameter = str(case.get("mutation_parameter") or "").strip()
        if not parameter or parameter == "unknown":
            continue
        counts[parameter] = counts.get(parameter, 0) + 1
    observed = sorted(counts, key=lambda key: (-counts[key], key))
    return list(dict.fromkeys([*observed, *defaults]))[:4]


def information_gain_score(
    status: str,
    current_parents: int,
    target_parents: int,
    consensus_score: float,
) -> float:
    ambiguity = {
        "MIXED_PERTURBATION_RESPONSE": 1.0,
        "INSUFFICIENT_CLAIM_SIGNAL": 0.95,
        "CHALLENGE_SIGNAL_SINGLE_PARENT": 0.90,
        "ROBUSTNESS_SIGNAL_SINGLE_PARENT": 0.80,
        "COUNTEREXAMPLE_PERSISTS": 0.90,
        "CHALLENGED_ACROSS_PARENTS": 0.70,
        "ROBUST_ACROSS_PARENTS": 0.55,
    }.get(status, 0.50)
    coverage_gap = max(
        0.0,
        min(1.0, (target_parents - current_parents) / max(1, target_parents)),
    )
    consensus_uncertainty = max(
        0.0,
        min(1.0, 1.0 - abs(float(consensus_score) - 0.5) * 2.0),
    )
    return round(
        0.55 * ambiguity
        + 0.30 * coverage_gap
        + 0.15 * consensus_uncertainty,
        4,
    )


def _target_revision_continuation(
    evidence_payload: dict[str, Any],
    *,
    claim_id: str,
    action_id: str,
) -> dict[str, Any] | None:
    """Return fail-closed continuation state after a targeted non-result.

    Direct target evidence is authoritative for whether an immutable
    ScientificTarget already ran.  The perturbation lane may still report zero
    independently aggregated parent rules, but that must not cause Planner to
    silently repeat the same target after a controlled experiment was already
    classified NON_DIAGNOSTIC/INSUFFICIENT_DATA.
    """
    channel = evidence_payload.get("experimental_evidence", {})
    if not isinstance(channel, dict):
        return None
    records = channel.get("target_evidence_records", [])
    if not isinstance(records, list):
        return None

    matching: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("target_id") or "") != claim_id:
            continue
        context = record.get("context", {})
        if not isinstance(context, dict):
            context = {}
        if str(context.get("action_id") or "") != action_id:
            continue
        eligibility = record.get("eligibility", {})
        if isinstance(eligibility, dict) and str(eligibility.get("status") or "").upper() != "ELIGIBLE":
            continue
        matching.append(record)

    if not matching:
        return None

    # A diagnostic target result supersedes prior non-diagnostic attempts.
    statuses = {
        str((record.get("effect") or {}).get("status") or "").upper()
        for record in matching
        if isinstance(record.get("effect"), dict)
    }
    if statuses & {"SUPPORTED", "CONTRADICTED"}:
        return None

    blockers = [
        record for record in matching
        if str((record.get("effect") or {}).get("status") or "").upper()
        in {"NON_DIAGNOSTIC", "INSUFFICIENT_DATA"}
    ]
    if not blockers:
        return None

    record = blockers[-1]
    effect = record.get("effect", {}) if isinstance(record.get("effect"), dict) else {}
    context = record.get("context", {}) if isinstance(record.get("context"), dict) else {}

    profile_gaps: list[str] = []
    profiles = evidence_payload.get("principle_evidence_profiles", {})
    if isinstance(profiles, dict):
        by_id = profiles.get("profiles", {})
        if isinstance(by_id, dict):
            profile = by_id.get(claim_id, {})
            overall = profile.get("overall_picture", {}) if isinstance(profile, dict) else {}
            if isinstance(overall, dict):
                profile_gaps = [
                    str(value) for value in overall.get("evidence_gaps", [])
                    if str(value).strip()
                ]

    return {
        "schema": "archon_target_revision_continuation_v1",
        "status": "TARGET_REVISION_REQUIRED",
        "prior_experiment_id": str(record.get("experiment_id") or ""),
        "prior_evidence_record_id": str(record.get("evidence_record_id") or ""),
        "prior_target_hash": str(context.get("target_hash") or ""),
        "prior_target_rules": normalize_rule_list(context.get("rule_ids")),
        "prior_result": str(effect.get("status") or "").upper(),
        "reason_codes": [str(value) for value in effect.get("reason_codes", [])],
        "replication_status": str(record.get("replication_status") or ""),
        "matched_control_status": str(record.get("matched_control_status") or ""),
        "evidence_gaps": profile_gaps,
        "revision_requirements": [
            "revise_target_metrics_or_success_criteria",
            "change_at_least_one_precommitted_design_axis",
            "materialize_a_new_scientific_target_hash",
            "do_not_repeat_the_previous_immutable_target",
        ],
    }


def build_perturbation_programs(
    consensus_payload: dict[str, Any],
    evidence_payload: dict[str, Any],
    cohort_payload: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    consensus = claim_items(consensus_payload, "principles")
    perturbations = perturbation_claims(evidence_payload)
    cohort_candidates = cohort_parent_candidates(cohort_payload)
    programs: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []

    for cid in sorted(consensus):
        principle = consensus[cid]
        status = str(
            principle.get("perturbation_status")
            or "INSUFFICIENT_CLAIM_SIGNAL"
        )
        target = PERTURBATION_TARGETS.get(status)
        intervention = CLAIM_INTERVENTIONS.get(cid)
        if target is None or intervention is None:
            continue

        action_id = f"EXP-PERT-{cid}"
        continuation = _target_revision_continuation(
            evidence_payload,
            claim_id=cid,
            action_id=action_id,
        )

        perturbation = perturbations.get(cid, {})
        outcome_groups = outcome_parent_sets(perturbation)
        tested_parents = sorted(set(
            normalize_rule_list(perturbation.get("parent_rules"))
            or outcome_groups["informative_parent_rules"]
        ))
        # Near-counterexample cohorts are the most informative perturbation
        # parents.  Generic support rules are reserves, not the first choice.
        observational_candidates = normalize_rule_list([
            *cohort_candidates.get(cid, []),
            *(principle.get("counterexample_rules") or []),
            *(principle.get("support_rules") or []),
        ])
        new_parent_candidates = [
            rid for rid in dict.fromkeys(observational_candidates)
            if rid not in tested_parents
        ]
        target_parent_count = int(target["parents"])
        required_new_parents = max(
            0,
            target_parent_count - len(tested_parents),
        )
        coverage_complete = required_new_parents == 0
        resolution = outcome_resolution_state(
            status,
            outcome_groups,
            dict(target["required_outcomes"]),
        )
        if continuation is not None:
            # The exact immutable target already produced a direct, eligible
            # non-diagnostic result.  Do not silently rematerialize it merely
            # because the separate perturbation channel still has zero
            # independently aggregated parent rules.
            selected_parents = []
            selection_mode = "target_revision"
        elif required_new_parents > 0:
            selected_parents = new_parent_candidates[:required_new_parents]
            selection_mode = "new_independent_parents"
        elif not resolution["complete"]:
            selected_parents = boundary_replication_parents(
                outcome_groups,
                tested_parents,
                limit=max(2, min(4, len(tested_parents))),
            )
            selection_mode = (
                "boundary_replication"
                if resolution["boundary_unresolved"]
                else "outcome_replication"
            )
        else:
            selected_parents = []
            selection_mode = "none"
        missing_parent_count = max(
            0,
            required_new_parents
            - len([rid for rid in selected_parents if rid in new_parent_candidates]),
        )
        parameter_priority = observed_parameter_priority(
            perturbation,
            list(intervention["parameters"]),
        )
        gain = information_gain_score(
            status,
            len(tested_parents),
            target_parent_count,
            float(principle.get("consensus_score") or 0.0),
        )
        program_id = f"PERT-{cid}"
        selection_status = (
            "TARGET_REVISION_REQUIRED"
            if continuation is not None
            else "COVERAGE_COMPLETE_OUTCOME_RESOLVED"
            if coverage_complete and resolution["complete"]
            else "BOUNDARY_REPLICATION_READY"
            if coverage_complete and resolution["boundary_unresolved"]
            and selected_parents
            else "OUTCOME_REPLICATION_READY"
            if coverage_complete and selected_parents
            else "CANDIDATES_READY"
            if missing_parent_count == 0
            else "SEARCH_REQUIRED"
        )
        program = {
            "schema": "archon_perturbation_program_v1",
            "id": program_id,
            "claim_id": cid,
            "claim_title": str(principle.get("title") or cid),
            "trigger_status": status,
            "scientific_question": intervention["question"],
            "goal": target["goal"],
            "priority": int(target["priority"]),
            "expected_information_gain_score": gain,
            "existing_evidence": {
                "informative_run_count": int(
                    _first_present(
                        perturbation.get("informative_run_count"),
                        principle.get("perturbation_run_count"),
                        0,
                    )
                ),
                "independent_parent_count": len(tested_parents),
                "tested_parent_rules": tested_parents,
                "outcome_parent_groups": outcome_groups,
                "outcome_counts": dict(
                    _first_present(
                        perturbation.get("outcome_counts"),
                        principle.get("perturbation_outcome_counts"),
                        {},
                    )
                ),
            },
            "independence_requirement": {
                "unit": "canonical_parent_rule",
                "target_independent_parent_count": target_parent_count,
                "required_new_parent_count": required_new_parents,
                "repeated_mutations_same_parent_are_independent": False,
                "required_outcomes": dict(target["required_outcomes"]),
                "coverage_complete": coverage_complete,
                "outcome_resolution_complete": resolution["complete"],
            },
            "parent_selection": {
                "status": selection_status,
                "selection_mode": selection_mode,
                "selected_parent_rules": selected_parents,
                "selected_new_parent_rules": [
                    rid for rid in selected_parents
                    if rid in new_parent_candidates
                ],
                "selected_retest_parent_rules": [
                    rid for rid in selected_parents
                    if rid in tested_parents
                ],
                "reserve_parent_rules": new_parent_candidates[
                    required_new_parents:
                ],
                "missing_parent_count": missing_parent_count,
                "exclude_already_tested": tested_parents,
                "selection_basis": (
                    [
                        "opposing perturbation outcome groups",
                        "already-tested informative parent rules",
                        "boundary replication across parameter intensities",
                    ]
                    if selection_mode in {"boundary_replication", "outcome_replication"}
                    else [
                        "nearest cohort candidates",
                        "observational counterexample rules",
                        "observational support rules",
                    ]
                ),
            },
            "resolution_state": resolution,
            "intervention_design": {
                "mode": "single_parameter",
                "parameter_priority": parameter_priority,
                "intensity_sweep": [0.25, 0.5, 1.0],
                "screening_rule": (
                    "Screen all priority parameters at intensity 0.5; "
                    "expand parameters producing a claim transition to the "
                    "0.25/0.5/1.0 dose-response sweep."
                ),
                "primary_endpoints": list(intervention["endpoints"]),
                "shared_analysis_horizon": True,
            },
            "matched_control_policy": {
                "required": True,
                "control_type": "exact_parent_unmodified",
                "same_parent_rule": True,
                "same_initial_state_and_seed": True,
                "same_tick_horizon": True,
                "same_sampling_and_observer_configuration": True,
                "minimum_comparison_confidence": "HIGH",
                "unresolved_control_blocks_ingestion": True,
            },
            "success_criteria": {
                "coverage": (
                    f"Reach {target_parent_count} independent canonical "
                    "parent rules."
                ),
                "coverage_complete": coverage_complete,
                "outcome_resolution_complete": resolution["complete"],
                "outcome": dict(target["required_outcomes"]),
                "outcome_gaps": dict(resolution["outcome_gaps"]),
                "boundary_resolution": (
                    "Replicate both corroborating and challenging transitions "
                    "and map the parameter-by-intensity boundary."
                    if resolution["boundary_unresolved"]
                    else None
                ),
                "quality": (
                    "Every ingested comparison has a closed matched control "
                    "and HIGH or VERY_HIGH comparison confidence."
                ),
                "interpretation": (
                    "Report parameter-by-intensity transition rates by "
                    "independent parent; do not pool repeated mutations as "
                    "independent confirmations."
                ),
            },
            "safety_policy": {
                "modify_original_rule": False,
                "canonical_rule_created_automatically": False,
                "automatic_confidence_adjustment": False,
                "promotion_required": True,
            },
            "status": "NeedsRevision" if continuation is not None else "Planned",
        }
        if continuation is not None:
            program["continuation"] = continuation
            program["success_criteria"]["revision"] = (
                "Precommit a revised ScientificTarget before execution. The "
                "new target must change at least one diagnostic design axis "
                "and must have a new target_hash."
            )
        programs.append(program)
        if continuation is None:
            jobs.append({
            "id": f"MUTATE-{program_id}",
            "job_type": "observer_mutation",
            "mutation_mode": "single_parameter",
            "claim_id": cid,
            "target_regime": status,
            "parent_rules": selected_parents,
            "required_new_parent_count": required_new_parents,
            "coverage_complete": coverage_complete,
            "outcome_resolution_complete": resolution["complete"],
            "selection_mode": selection_mode,
            "missing_parent_count": missing_parent_count,
            "parameter_priority": parameter_priority,
            "intensity_sweep": [0.25, 0.5, 1.0],
            "program_id": program_id,
            "priority": int(target["priority"]),
            "isolation_policy": {
                "modify_original_rule": False,
                "canonical_rule_created_automatically": False,
                "write_original_snapshot": True,
                "write_mutated_rule": True,
                "write_mutation_diff": True,
                "output_root": (
                    "Results/Universe_Search/mutation_runs/"
                    "<parent_rule>/<mutation_id>/"
                ),
                "promotion_required": True,
            },
            "status": "Planned",
            })
        tasks.append({
            "id": action_id,
            "title": (
                f"Revise non-diagnostic perturbation target for {cid}"
                if continuation is not None
                else f"Resolve perturbation response for {cid}"
            ),
            "priority": int(target["priority"]),
            "type": "perturbation_evidence_program",
            "target_rules": selected_parents,
            "based_on_prediction": cid,
            **(
                {
                    "requires_target_revision": True,
                    "continuation": continuation,
                }
                if continuation is not None
                else {}
            ),
            "reason": (
                (
                    f"{cid} already has an eligible direct target result "
                    f"{continuation['prior_result']} from "
                    f"{continuation['prior_experiment_id']}. Repeating the "
                    "same immutable ScientificTarget is forbidden until its "
                    "metrics, success criteria, horizon, intervention, or other "
                    "precommitted diagnostic design axis is revised."
                )
                if continuation is not None
                else (
                (
                    f"{cid} has perturbation status {status} across "
                    f"{len(tested_parents)} independent parent rule(s); "
                    "parent coverage is complete, but opposing outcomes remain unresolved."
                )
                if selection_mode == "boundary_replication"
                else (
                    f"{cid} has perturbation status {status} across "
                    f"{len(tested_parents)} independent parent rule(s); "
                    "coverage is complete, but required outcome replication remains incomplete."
                )
                if selection_mode == "outcome_replication"
                else (
                    f"{cid} has perturbation status {status} across "
                    f"{len(tested_parents)} independent parent rule(s); "
                    f"{required_new_parents} additional independent parent rule(s) are required."
                )
            )),
            "tests": (
                [
                    "Review the prior target-specific NON_DIAGNOSTIC/INSUFFICIENT_DATA interpretation.",
                    "Revise target metrics or success criteria without changing the prior immutable record.",
                    "Change at least one precommitted diagnostic design axis before rematerialization.",
                    "Record a new ScientificTarget hash and preserve provenance to the prior target.",
                    "Do not queue the previous target unchanged.",
                ]
                if continuation is not None
                else (
                [
                    "Re-test discriminating parents from opposing outcome groups.",
                    "Repeat the same parameter and intensity settings that produced opposite transitions.",
                    "Run matched unmodified controls at the same horizon.",
                    "Expand the transition region into a denser dose-response sweep.",
                    "Map the parameter-by-intensity boundary by independent parent rule.",
                ]
                if selection_mode == "boundary_replication"
                else [
                    "Re-test already informative parents needed to satisfy unresolved outcome requirements.",
                    "Repeat the outcome-producing parameter settings with matched controls.",
                    "Expand informative parameters into a dose-response sweep.",
                    "Aggregate replicated outcomes by independent parent rule.",
                    "Do not count repeated mutations of one parent as independent confirmation.",
                ]
                if selection_mode == "outcome_replication"
                else [
                    "Select only previously untested canonical parent rules.",
                    "Screen the planned single-parameter interventions.",
                    "Run a matched unmodified control at the same horizon.",
                    "Expand informative parameters into a dose-response sweep.",
                    "Aggregate outcomes by independent parent rule.",
                ]
            )),
            "expected_information_gain": (
                (
                    "High: prevents an identical non-diagnostic rerun and "
                    "forces the next experiment to add diagnostic information."
                )
                if continuation is not None
                else (
                (
                    f"Score {gain:.2f}: resolves an observed causal boundary after "
                    "independent-parent coverage has already been achieved."
                )
                if selection_mode == "boundary_replication"
                else (
                    f"Score {gain:.2f}: resolves missing outcome replication after "
                    "independent-parent coverage has already been achieved."
                )
                if selection_mode == "outcome_replication"
                else (
                    f"Score {gain:.2f}: targets ambiguity and missing independent "
                    "parent coverage in the causal evidence channel."
                )
            )),
            "success_criteria": (
                (
                    "A revised precommitted ScientificTarget exists with a new "
                    "target_hash, explicit provenance to the prior target, and "
                    "at least one changed diagnostic design axis."
                )
                if continuation is not None
                else (
                program["success_criteria"]["boundary_resolution"]
                if selection_mode == "boundary_replication"
                else (
                    "Satisfy all required outcome counts across independent parent rules."
                    if selection_mode == "outcome_replication"
                    else program["success_criteria"]["coverage"]
                )
            )),
            "status": "NeedsRevision" if continuation is not None else "Planned",
        })

    programs.sort(
        key=lambda item: (
            float(item["expected_information_gain_score"]),
            int(item["priority"]),
            item["claim_id"],
        ),
        reverse=True,
    )
    rank = {
        item["id"]: index
        for index, item in enumerate(programs, start=1)
    }
    for item in programs:
        item["information_gain_rank"] = rank[item["id"]]
    jobs.sort(
        key=lambda item: (
            next(
                (
                    p["information_gain_rank"]
                    for p in programs
                    if p["id"] == item["program_id"]
                ),
                999,
            ),
            item["id"],
        )
    )
    return programs, jobs, tasks


def apply_feedback_metric_readiness(
    *,
    plan: list[dict[str, Any]],
    search_jobs: list[dict[str, Any]],
    mutation_jobs: list[dict[str, Any]],
    perturbation_programs: list[dict[str, Any]],
    metric_audit: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    diagnostics = (
        metric_audit.get("empirical_diagnostics", {})
        if isinstance(metric_audit, dict)
        else {}
    )
    independent_count = int(
        diagnostics.get("independent_v2_profile_count") or 0
    )
    minimum_baseline = 10

    raw_experimental_validation = (
        metric_audit.get("experimental_validation")
        if isinstance(metric_audit, dict)
        else None
    )
    if isinstance(raw_experimental_validation, dict):
        experimental_validation = raw_experimental_validation
        experimental_count = int(
            _first_present(
                experimental_validation.get("eligible_run_count"),
                experimental_validation.get("eligible_profile_count"),
                0,
            )
        )
        experimental_ready = (
            experimental_validation.get("status") == "BASELINE_SUFFICIENT"
        )
        ready = independent_count >= minimum_baseline or experimental_ready
        readiness_source = (
            "CANONICAL_OBSERVATIONAL"
            if independent_count >= minimum_baseline
            else (
                "CONTROLLED_EXPERIMENTAL_BASELINE"
                if experimental_ready
                else "INSUFFICIENT"
            )
        )
        state = {
            "required_feedback_metric": "STRUCTURALLY_INDEPENDENT_V2",
            "independent_v2_profile_count": independent_count,
            "experimental_baseline_profile_count": experimental_count,
            "experimental_baseline_run_count": experimental_count,
            "experimental_baseline_status": experimental_validation.get("status"),
            "readiness_source": readiness_source,
            "minimum_baseline_profile_count": minimum_baseline,
            "status": "READY" if ready else "BASELINE_REQUIRED",
            "blocked_claims": [] if ready else ["GP-102", "GP-103"],
            "blocked_work_items": {
                "plan_items": 0,
                "search_jobs": 0,
                "mutation_jobs": 0,
            },
        }
    else:
        # Preserve protected planner output byte-for-byte for legacy metric
        # audit payloads that predate the experimental validation lane.
        ready = independent_count >= minimum_baseline
        state = {
            "required_feedback_metric": "STRUCTURALLY_INDEPENDENT_V2",
            "independent_v2_profile_count": independent_count,
            "minimum_baseline_profile_count": minimum_baseline,
            "status": "READY" if ready else "BASELINE_REQUIRED",
            "blocked_claims": [] if ready else ["GP-102", "GP-103"],
            "blocked_work_items": {
                "plan_items": 0,
                "search_jobs": 0,
                "mutation_jobs": 0,
            },
        }
    if ready:
        return plan, search_jobs, mutation_jobs, state

    blocked_claims = {"GP-102", "GP-103"}

    def routes_blocked_claim(item: dict[str, Any]) -> bool:
        claim_id = str(
            item.get("claim_id")
            or item.get("based_on_prediction")
            or ""
        ).upper()
        if claim_id in blocked_claims:
            return True
        compact_id = re.sub(
            r"[^A-Z0-9]+",
            "",
            str(item.get("id") or "").upper(),
        )
        return any(
            claim_id.replace("-", "") in compact_id
            for claim_id in blocked_claims
        )

    blocked_plan_count = sum(
        routes_blocked_claim(task) for task in plan
    )
    blocked_search_job_count = sum(
        routes_blocked_claim(job) for job in search_jobs
    )
    blocked_mutation_job_count = sum(
        routes_blocked_claim(job) for job in mutation_jobs
    )
    plan = [
        task for task in plan
        if not routes_blocked_claim(task)
    ]
    search_jobs = [
        job for job in search_jobs
        if not routes_blocked_claim(job)
    ]
    mutation_jobs = [
        job for job in mutation_jobs
        if not routes_blocked_claim(job)
    ]
    for program in perturbation_programs:
        if str(program.get("claim_id")) not in {"GP-102", "GP-103"}:
            continue
        program["status"] = "Blocked"
        program["blocking_reason"] = (
            "Independent feedback metric v2 baseline is insufficient."
        )
        selection = program.get("parent_selection")
        if isinstance(selection, dict):
            selection["status"] = "METRIC_V2_BASELINE_REQUIRED"
            selection["selected_parent_rules"] = []
            selection["selected_new_parent_rules"] = []
            selection["selected_retest_parent_rules"] = []

    gp201_rules: list[str] = []
    for program in perturbation_programs:
        if str(program.get("claim_id")) != "GP-201":
            continue
        selection = program.get("parent_selection")
        if isinstance(selection, dict):
            gp201_rules = normalize_rule_list(
                selection.get("selected_parent_rules")
            )
        break
    plan.append({
        "id": "EXP-METRIC-FB-V2-BASELINE",
        "title": "Establish independent feedback v2 baseline",
        "priority": 5,
        "type": "metric_validation_baseline",
        "target_rules": gp201_rules,
        "based_on_prediction": None,
        "reason": (
            f"Only {independent_count} independent-v2 profile(s) exist; "
            f"{minimum_baseline} are required before GP-102/GP-103 routing."
        ),
        "tests": [
            "Collect feedback v2 in matched GP-201 controls and treatments.",
            "Keep feedback_knowledge_impact diagnostic-only.",
            "Re-run the metric independence audit after observation.",
            "Do not promote GP-102 or GP-103 from legacy feedback v1.",
        ],
        "expected_information_gain": (
            "Very high: converts previously circular metrics into a testable "
            "knowledge/feedback relationship."
        ),
        "success_criteria": (
            "At least 10 eligible feedback-v2 profiles across multiple "
            "parents and non-zero response opportunity."
        ),
        "status": "Planned",
    })
    state["blocked_work_items"] = {
        "plan_items": blocked_plan_count,
        "search_jobs": blocked_search_job_count,
        "mutation_jobs": blocked_mutation_job_count,
    }
    return plan, search_jobs, mutation_jobs, state


def render_markdown(
    plan: list[dict[str, Any]],
    kb: dict[str, Any],
    validation_count: int,
    search_jobs: list[dict[str, Any]],
    mutation_jobs: list[dict[str, Any]],
    perturbation_programs: list[dict[str, Any]],
    generated: str,
) -> str:
    summary = kb.get("summary", {})
    lines = [
        "# Universe Search Experiment Plan v4.2",
        "",
        f"Generated: **{generated.replace('T', ' ')}**",
        "",
        "## Current Knowledge State",
        "",
        f"- Rules in Knowledge Base: **{summary.get('rules', 0)}**",
        f"- Principles: **{summary.get('principles', 0)}**",
        f"- Predictions: **{summary.get('predictions', 0)}**",
        f"- Validation results loaded: **{validation_count}**",
        f"- Discoveries: **{summary.get('discoveries', 0)}**",
        f"- Mechanisms: **{summary.get('mechanisms', 0)}**",
        f"- Perturbation programs: **{len(perturbation_programs)}**",
        "",
        "## Recommended Experiments",
        "",
    ]

    if not plan:
        lines.extend([
            "No unresolved predictions currently require experiments.",
            "",
        ])

    for task in plan:
        lines.extend([
            f"### {task['id']}: {task['title']}",
            "",
            f"- Priority: **{stars(task['priority'])}**",
            f"- Type: **{task['type']}**",
            f"- Based on prediction: **{task.get('based_on_prediction') or '-'}**",
            f"- Target rules: **{', '.join(task['target_rules']) or '-'}**",
            f"- Status: **{task['status']}**",
            "",
            "**Reason**",
            "",
            task["reason"],
            "",
            "**Tests**",
            "",
        ])
        for test in task["tests"]:
            lines.append(f"- [ ] {test}")

        lines.extend([
            "",
            "**Expected information gain**",
            "",
            task["expected_information_gain"],
            "",
            "**Success criteria**",
            "",
            task["success_criteria"],
            "",
        ])

    lines.extend([
        "## Perturbation-aware programs",
        "",
        "Programs are ranked by expected information gain. Their independent "
        "unit is the canonical parent rule, not the number of mutation runs.",
        "",
    ])
    if not perturbation_programs:
        lines.extend([
            "No actionable perturbation status is currently available.",
            "",
        ])
    for program in perturbation_programs:
        selection = program["parent_selection"]
        design = program["intervention_design"]
        requirement = program["independence_requirement"]
        lines.extend([
            f"### {program['information_gain_rank']}. {program['id']}",
            "",
            f"- Claim: **{program['claim_id']} / {program['claim_title']}**",
            f"- Trigger: **{program['trigger_status']}**",
            f"- Information gain: **{program['expected_information_gain_score']:.2f}**",
            f"- Parent selection: **{selection['status']}**",
            f"- Independent parents: **{program['existing_evidence']['independent_parent_count']} / {requirement['target_independent_parent_count']}**",
            f"- New parents: **{', '.join(selection['selected_new_parent_rules']) or '-'}**",
            f"- Missing parents: **{selection['missing_parent_count']}**",
            f"- Parameters: **{', '.join(design['parameter_priority'])}**",
            f"- Intensities: **{', '.join(str(x) for x in design['intensity_sweep'])}**",
            "",
            program["scientific_question"],
            "",
        ])

    lines.extend([
        "## Search jobs",
        "",
        "Search jobs create new canonical rules and record their provenance.",
        "",
    ])
    if not search_jobs:
        lines.extend(["No cohort-directed Search jobs are currently required.", ""])
    for job in search_jobs:
        lines.extend([
            f"### {job['id']}",
            "",
            f"- Mode: **{job['search_mode']}**",
            f"- Target: **{job['claim_id']} / {job['target_regime']}**",
            f"- Seed rules: **{', '.join(job['seed_rules']) or '-'}**",
            f"- Constraints: `{json.dumps(job['constraints'], ensure_ascii=False)}`",
            "",
        ])

    lines.extend([
        "## Observer mutation jobs",
        "",
        "Mutation jobs are isolated experiments. They never overwrite the "
        "parent rule and require explicit promotion before entering Atlas.",
        "",
    ])
    if not mutation_jobs:
        lines.extend(["No cohort-directed mutation jobs are currently required.", ""])
    for job in mutation_jobs:
        policy = job["isolation_policy"]
        lines.extend([
            f"### {job['id']}",
            "",
            f"- Mode: **{job['mutation_mode']}**",
            f"- Target: **{job['claim_id']} / {job['target_regime']}**",
            f"- Parent rules: **{', '.join(job['parent_rules']) or '-'}**",
            f"- Output: `{policy['output_root']}`",
            f"- Modify original: **{policy['modify_original_rule']}**",
            f"- Promotion required: **{policy['promotion_required']}**",
            "",
        ])

    lines.extend([
        "## Suggested order",
        "",
    ])
    for index, task in enumerate(plan, start=1):
        lines.append(f"{index}. **{task['id']}**: {task['title']}")
    lines.append("")

    return "\n".join(lines)



