#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universe Search Evidence Engine v31.4 — Stage 2C.1

Reads:
- observer_profiles_v30.json from the shared results workspace
- research_atlas.json from Analyzer root, if present
- general_principles.json from Analyzer root, if present

Writes:
- evidence_report.md
- evidence_report.json

Goal:
Collect support and counterexamples for principle-level claims using the
normalized ObserverProfile v30 bridge: CIV / KNOW / FB / EMG / VAL.

Controlled mutations are ingested as a separate perturbation-evidence channel.
Experiment Knowledge is ingested as a separate experimental-evidence channel.
Neither channel increments observational support/counterexample counts or
automatically changes principle confidence.

Usage:
    python evidence_engine.py ../universe_search_v23_results --root .
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.scientific_claims import CLAIMS, CLAIM_SPECS
from Analyzer_next.core.experimental_evidence.contract import (
    TARGET_DIRECTIONS,
    contract_records,
)

from archon_paths import ANALYSIS_RESULTS_DIR, KNOWLEDGE_ATLAS_DIR

def analysis_results_dir() -> Path:
    return ANALYSIS_RESULTS_DIR

def knowledge_atlas_dir() -> Path:
    return KNOWLEDGE_ATLAS_DIR


CONF_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "VERY_HIGH": 4}


def sf(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def si(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def ss(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def conf(value: Any) -> str:
    c = ss(value, "NONE").strip().upper().replace(" ", "_")
    return c if c in CONF_RANK else "NONE"


def has_word(items: Any, word: str) -> bool:
    if not items:
        return False
    if isinstance(items, str):
        text = items.lower()
        return word.lower() in text
    if isinstance(items, list):
        return any(word.lower() in ss(x).lower() for x in items)
    return False


@dataclass
class EvidenceCase:
    rule: str
    status: str
    strength: float
    reason: str
    emg: float
    val: float
    know: float
    fb: float
    civ: float


@dataclass
class EvidenceClaim:
    id: str
    title: str
    description: str
    support: int
    counterexamples: int
    neutral: int
    confidence_score: float
    confidence_label: str
    status: str
    support_rules: list[str]
    counterexample_rules: list[str]
    cases: list[EvidenceCase]


def load_profiles(results_folder: Path) -> list[dict[str, Any]]:
    path = results_folder / "observer_profiles_v30.json"
    if not path.exists():
        raise SystemExit(f"observer_profiles_v30.json not found: {path}\nRun: python analyze_results_v30.py --profiles-only")
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    profiles = data.get("profiles", [])
    if not isinstance(profiles, list):
        raise SystemExit(f"Invalid observer_profiles_v30.json: profiles is not a list")
    # Defense in depth: modern profile files carry explicit evidence routing.
    # Legacy files without these additive fields remain readable.
    return [
        profile
        for profile in profiles
        if isinstance(profile, dict)
        and profile.get("observational_eligible", True) is not False
        and str(
            profile.get(
                "evidence_channel",
                "legacy_unverified_observational",
            )
        ) not in {"experimental", "perturbation", "excluded"}
    ]


def load_optional_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


EXPERIMENT_PRINCIPLE_MAPPING_POLICY: tuple[dict[str, Any], ...] = (
    {
        "mapping_id": "EPM-001A",
        "claim_type": "qualitative_state_preservation",
        "principle_id": "GP-101",
        "relation": "scope_challenge_signal",
        "required_supporting_metrics": ("validation_grade",),
        "required_contradicting_metrics": ("emergence_confidence",),
        "allowed_claim_statuses": ("mixed",),
        "rationale": (
            "Validation grade remained stable while emergence confidence "
            "changed across controlled arms. This does not refute the "
            "criterion, but signals that its scope or calibration may depend "
            "on initial-state conditions."
        ),
    },
    {
        "mapping_id": "EPM-001B",
        "claim_type": "qualitative_state_preservation",
        "principle_id": "GP-101",
        "relation": "corroborates",
        "required_supporting_metrics": (
            "emergence_confidence",
            "validation_grade",
        ),
        "required_contradicting_metrics": (),
        "allowed_claim_statuses": ("supported",),
        "rationale": (
            "Preserved emergence and validation classifications under a "
            "controlled condition are consistent with the joint "
            "emergence-validation criterion."
        ),
    },
    {
        "mapping_id": "EPM-002A",
        "claim_type": "qualitative_state_preservation",
        "principle_id": "GP-104",
        "relation": "contextualizes",
        "required_supporting_metrics": ("life_state",),
        "required_contradicting_metrics": ("emergence_confidence",),
        "allowed_claim_statuses": ("mixed",),
        "rationale": (
            "Life state remained stable while emergence confidence changed. "
            "This is relevant to pattern-life separation because biological "
            "or organizational classification appears more stable than one "
            "higher-level emergence assessment under the tested condition."
        ),
    },
    {
        "mapping_id": "EPM-002B",
        "claim_type": "qualitative_state_preservation",
        "principle_id": "GP-104",
        "relation": "calibration_consistent",
        "required_supporting_metrics": (
            "life_state",
            "emergence_confidence",
        ),
        "required_contradicting_metrics": (),
        "allowed_claim_statuses": ("supported",),
        "rationale": (
            "Joint preservation of life-state and emergence classification "
            "is consistent with separation of living organization from "
            "merely visual pattern."
        ),
    },
    {
        "mapping_id": "EPM-003",
        "claim_type": "observed_horizon_preservation",
        "principle_id": "GP-201",
        "relation": "contextualizes",
        "required_supporting_metrics": ("longest_age",),
        "required_contradicting_metrics": (),
        "allowed_claim_statuses": ("supported", "not_supported"),
        "rationale": (
            "Observed-horizon preservation is relevant context for the "
            "memory-stability principle, but does not test memory or "
            "repeatability by itself."
        ),
    },
    {
        "mapping_id": "EPM-004",
        "claim_type": "quantitative_sensitivity",
        "principle_id": "GP-201",
        "relation": "scope_challenge_signal",
        "required_supporting_metrics": ("stability_index",),
        "required_contradicting_metrics": (),
        "allowed_claim_statuses": ("supported",),
        "rationale": (
            "Sensitivity of stability_index across controlled arms may "
            "challenge the scope of a memory-stability interpretation. "
            "Memory measurements are still required before it can count as "
            "support or counterevidence."
        ),
    },
)


TARGET_DIRECTION = TARGET_DIRECTIONS


def build_target_evidence_records(
    knowledge_payload: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Select producer-normalized principle signals from a valid contract."""
    records, rejected, contract = contract_records(knowledge_payload)
    if contract is None or contract.get("source_kind") != "experiment_knowledge":
        return [], rejected
    target_records = [
        record
        for record in records
        if record.get("interpretation_level") == "PRINCIPLE_SIGNAL"
        and record.get("relevance") == "DIRECT_TARGET"
    ]
    return target_records, rejected


def build_experiment_principle_mappings(
    experimental_evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create explicit, non-promotional links to principle claims."""
    claims = experimental_evidence.get("claims", [])
    if not isinstance(claims, list):
        claims = []

    target_records = experimental_evidence.get("target_evidence_records", [])
    if not isinstance(target_records, list):
        target_records = []
    mappings: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for record in target_records:
        if not isinstance(record, dict):
            continue
        context = record.get("context", {})
        if not isinstance(context, dict):
            context = {}
        status = ss(record.get("effect", {}).get("status")).upper()
        direction = TARGET_DIRECTION.get(status, "non_diagnostic")
        mappings.append({
            "mapping_id": (
                f"EPM-TARGET::{record.get('evidence_record_id')}::"
                f"{record.get('target_id')}"
            ),
            "policy_id": "TARGET-SPECIFIC-INTERPRETATION-V1",
            "experiment_claim_id": record.get("claim_id"),
            "experiment_id": record.get("experiment_id"),
            "principle_id": record.get("target_id"),
            "relation": f"target_{status.lower()}",
            "direction": direction,
            "claim_status": status,
            "claim_confidence": record.get("confidence"),
            "design_confidence": record.get("confidence"),
            "rule_ids": list(context.get("rule_ids", [])),
            "matched_metrics": list(record.get("supporting_metrics", [])),
            "matched_contradicting_metrics": list(
                record.get("contradicting_metrics", [])
            ),
            "supporting_metrics": list(record.get("supporting_metrics", [])),
            "contradicting_metrics": list(record.get("contradicting_metrics", [])),
            "target_interpretation_id": context.get("target_interpretation_id"),
            "evidence_record_id": record.get("evidence_record_id"),
            "rationale": (
                "Direct mapping from the experiment's hash-protected "
                "target-specific interpretation. Target provenance alone "
                "does not determine direction."
            ),
            "scientific_effect": {
                "observational_counts_changed": False,
                "principle_confidence_changed": False,
                "automatic_promotion": False,
                "consensus_effect": False,
            },
        })

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = ss(claim.get("claim_id"), "unknown")
        claim_type = ss(claim.get("claim_type"), "unknown")
        claim_status = ss(claim.get("status"), "unknown")
        supporting = {
            str(value) for value in claim.get("supporting_metrics", [])
        }
        contradicting = {
            str(value) for value in claim.get("contradicting_metrics", [])
        }

        target_ref = claim.get("scientific_target_ref")
        if isinstance(target_ref, dict) and target_ref.get("target_id"):
            matched = True
            mappings.append({
                "mapping_id": (
                    f"EPM-TARGET-COMPONENT::{claim_id}::"
                    f"{target_ref.get('target_id')}"
                ),
                "policy_id": "TARGET-DESCRIPTIVE-COMPONENT-V1",
                "experiment_claim_id": claim_id,
                "experiment_id": claim.get("experiment_id"),
                "principle_id": target_ref.get("target_id"),
                "relation": "descriptive_component",
                "direction": "component",
                "claim_status": claim_status,
                "claim_confidence": conf(claim.get("confidence")),
                "design_confidence": conf(claim.get("design_confidence")),
                "rule_ids": list(claim.get("rule_ids", [])),
                "matched_metrics": [],
                "matched_contradicting_metrics": [],
                "supporting_metrics": sorted(supporting),
                "contradicting_metrics": sorted(contradicting),
                "target_interpretation_id": target_ref.get(
                    "target_interpretation_id"
                ),
                "rationale": (
                    "Generic claim retained as a CLAIM_SIGNAL component; "
                    "the separate PRINCIPLE_SIGNAL owns scientific direction."
                ),
                "scientific_effect": {
                    "observational_counts_changed": False,
                    "principle_confidence_changed": False,
                    "automatic_promotion": False,
                    "consensus_effect": False,
                },
            })
            continue

        matched = False
        for policy in EXPERIMENT_PRINCIPLE_MAPPING_POLICY:
            if claim_type != policy["claim_type"]:
                continue
            required = set(policy["required_supporting_metrics"])
            required_contradicting = set(
                policy.get("required_contradicting_metrics", ())
            )
            if not required.issubset(supporting):
                continue
            if not required_contradicting.issubset(contradicting):
                continue
            if claim_status not in policy["allowed_claim_statuses"]:
                continue

            matched = True
            relation = str(policy["relation"])
            direction = (
                "supportive"
                if relation in {"corroborates", "calibration_consistent"}
                else "contextual"
                if relation == "contextualizes"
                else "challenging"
            )
            mappings.append({
                "mapping_id": (
                    f"{policy['mapping_id']}::{claim_id}::"
                    f"{policy['principle_id']}"
                ),
                "policy_id": policy["mapping_id"],
                "experiment_claim_id": claim_id,
                "experiment_id": claim.get("experiment_id"),
                "principle_id": policy["principle_id"],
                "relation": relation,
                "direction": direction,
                "claim_status": claim_status,
                "claim_confidence": conf(claim.get("confidence")),
                "design_confidence": conf(
                    claim.get("design_confidence")
                ),
                "rule_ids": list(claim.get("rule_ids", [])),
                "matched_metrics": sorted(required),
                "matched_contradicting_metrics": sorted(
                    required_contradicting
                ),
                "supporting_metrics": sorted(supporting),
                "contradicting_metrics": sorted(contradicting),
                "rationale": policy["rationale"],
                "scientific_effect": {
                    "observational_counts_changed": False,
                    "principle_confidence_changed": False,
                    "automatic_promotion": False,
                    "consensus_effect": False,
                },
            })

        if not matched:
            rejected.append({
                "claim_id": claim_id,
                "reason": "no_explicit_mapping_rule_matched",
            })

    by_principle: dict[str, dict[str, Any]] = {}
    for mapping in mappings:
        principle_id = str(mapping["principle_id"])
        bucket = by_principle.setdefault(principle_id, {
            "principle_id": principle_id,
            "mapping_count": 0,
            "supportive_count": 0,
            "contextual_count": 0,
            "challenging_count": 0,
            "mixed_count": 0,
            "non_diagnostic_count": 0,
            "insufficient_count": 0,
            "component_count": 0,
            "experiment_ids": set(),
            "rule_ids": set(),
            "mapping_ids": [],
        })
        bucket["mapping_count"] += 1
        count_key = f"{mapping['direction']}_count"
        bucket[count_key] = int(bucket.get(count_key, 0)) + 1
        if mapping.get("experiment_id"):
            bucket["experiment_ids"].add(mapping["experiment_id"])
        bucket["rule_ids"].update(mapping.get("rule_ids", []))
        bucket["mapping_ids"].append(mapping["mapping_id"])

    normalized_by_principle: dict[str, dict[str, Any]] = {}
    for principle_id, bucket in by_principle.items():
        normalized_by_principle[principle_id] = {
            **bucket,
            "experiment_ids": sorted(bucket["experiment_ids"]),
            "rule_ids": sorted(bucket["rule_ids"]),
            "unique_experiment_count": len(bucket["experiment_ids"]),
            "unique_rule_count": len(bucket["rule_ids"]),
        }

    summary = {
        "policy_schema": "archon_experiment_principle_mapping_policy_v1",
        "policy_rule_count": len(EXPERIMENT_PRINCIPLE_MAPPING_POLICY),
        "claims_seen": len(claims),
        "mappings_created": len(mappings),
        "claims_without_mapping": len(rejected),
        "principles_linked": len(normalized_by_principle),
        "rejections": rejected,
        "by_principle": normalized_by_principle,
        "scientific_policy": {
            "explicit_rules_only": True,
            "llm_mapping": False,
            "observational_counts_changed": False,
            "principle_confidence_changed": False,
            "automatic_promotion": False,
            "consensus_effect": False,
        },
    }
    if target_records:
        summary["target_evidence_record_count"] = len(target_records)
        summary["targeted_experiments_without_mapping"] = len({
            str(record.get("experiment_id"))
            for record in target_records
            if isinstance(record, dict)
            and not any(
                mapping.get("evidence_record_id")
                == record.get("evidence_record_id")
                for mapping in mappings
            )
        })
    return mappings, summary

def build_experimental_evidence(
    knowledge_payload: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ingest only producer-normalized Experiment Knowledge records."""
    if not isinstance(knowledge_payload, dict):
        return {
            "schema": "archon_experimental_evidence_channel_v2",
            "status": "SOURCE_NOT_AVAILABLE",
            "claims": [],
            "target_evidence_records": [],
            "scientific_policy": {
                "separate_from_observational_counts": True,
                "unit_of_independence": "experiment",
                "automatic_confidence_adjustment": False,
                "automatic_promotion": False,
                "principle_mapping_enabled": True,
                "raw_source_ingestion": False,
            },
        }, {
            "source_schema": None,
            "contract_schema": None,
            "contract_status": "SOURCE_NOT_AVAILABLE",
            "claims_seen": 0,
            "eligible_claims": 0,
            "rejected_claims": 0,
            "experiments": 0,
            "unique_rules": 0,
            "rejections": [],
        }

    records, contract_rejections, contract = contract_records(knowledge_payload)
    contract_source_ok = bool(
        contract is not None
        and contract.get("source_kind") == "experiment_knowledge"
    )
    if not contract_source_ok and contract is not None:
        contract_rejections.append({
            "record_id": "*",
            "reason": "experimental_evidence_contract_source_kind_invalid",
        })
        records = []

    normalization_rejections = (
        list(contract.get("normalization_rejections", []))
        if contract_source_ok and isinstance(contract, dict)
        else []
    )
    target_records = [
        record
        for record in records
        if record.get("interpretation_level") == "PRINCIPLE_SIGNAL"
        and record.get("relevance") == "DIRECT_TARGET"
        and record.get("eligibility", {}).get("status") == "ELIGIBLE"
    ]
    observed_records = [
        record
        for record in records
        if record.get("interpretation_level") == "OBSERVED_EFFECT"
    ]
    target_claim_records = [
        record
        for record in records
        if record.get("interpretation_level") == "CLAIM_SIGNAL"
        and record.get("relevance") == "TARGET_INTERPRETATION"
    ]
    claim_records = [
        record
        for record in records
        if record.get("interpretation_level") == "CLAIM_SIGNAL"
        and record.get("relevance") != "TARGET_INTERPRETATION"
    ]
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for record in claim_records:
        claim_id = ss(record.get("claim_id"), "unknown")
        eligibility = record.get("eligibility", {})
        if eligibility.get("status") != "ELIGIBLE":
            rejected.append({
                "claim_id": claim_id,
                "reason": ss(eligibility.get("reason"), "producer_rejected"),
            })
            continue
        effect = record.get("effect", {})
        context = record.get("context", {})
        status = {
            "SUPPORTED": "supported",
            "MIXED": "mixed",
            "NOT_SUPPORTED": "not_supported",
        }.get(ss(effect.get("status")).upper())
        if status is None:
            rejected.append({
                "claim_id": claim_id,
                "reason": "contract_claim_effect_status_invalid",
            })
            continue
        eligible.append({
            "claim_id": claim_id,
            "experiment_id": record.get("experiment_id"),
            "claim_type": ss(context.get("claim_type"), "unknown"),
            "statement": ss(context.get("statement")),
            "status": status,
            "confidence": conf(record.get("confidence")),
            "rule_ids": list(context.get("rule_ids", [])),
            "horizon": context.get("horizon"),
            "geometries": list(context.get("geometries", [])),
            "initial_state_modes": list(context.get("initial_state_modes", [])),
            "outcome_ids": list(context.get("outcome_ids", [])),
            "supporting_metrics": list(record.get("supporting_metrics", [])),
            "contradicting_metrics": list(record.get("contradicting_metrics", [])),
            "limitations": list(record.get("limitations", [])),
            "design_confidence": conf(context.get("design_confidence")),
            "experiment_type": context.get("experiment_type"),
            "run_ids": list(context.get("run_ids", [])),
            "condition_ids": list(context.get("condition_ids", [])),
            "provenance": dict(record.get("provenance", {})),
            "provenance_hash": record.get("provenance_hash"),
            "record_hash": record.get("record_hash"),
            "evidence_record_id": record.get("evidence_record_id"),
            "interpretation_level": "CLAIM_SIGNAL",
            "scientific_target_ref": context.get("scientific_target_ref"),
        })

    experiment_ids = sorted({
        item["experiment_id"] for item in eligible
    })
    rule_ids = sorted({
        rule_id
        for item in eligible
        for rule_id in item["rule_ids"]
    })
    status_counts: dict[str, int] = {}
    for item in eligible:
        status_counts[item["status"]] = (
            status_counts.get(item["status"], 0) + 1
        )

    if not eligible:
        if contract_rejections:
            channel_status = "CONTRACT_REJECTED"
        elif claim_records:
            channel_status = "NO_ELIGIBLE_EXPERIMENT_CLAIMS"
        else:
            channel_status = "NO_EXPERIMENT_CLAIMS"
    elif rejected or normalization_rejections:
        channel_status = "AVAILABLE_WITH_REJECTIONS"
    else:
        channel_status = "AVAILABLE"

    channel = {
        "schema": "archon_experimental_evidence_channel_v2",
        "status": channel_status,
        "claim_count": len(eligible),
        "experiment_count": len(experiment_ids),
        "unique_rule_count": len(rule_ids),
        "experiment_ids": experiment_ids,
        "rule_ids": rule_ids,
        "status_counts": status_counts,
        "claims": eligible,
        "target_evidence_records": target_records,
        "layer_counts": {
            "OBSERVED_EFFECT": len(observed_records),
            "CLAIM_SIGNAL": len(claim_records) + len(target_claim_records),
            "PRINCIPLE_SIGNAL": len(target_records),
        },
        "contract_hash": contract.get("contract_hash") if contract else None,
        "scientific_policy": {
            "separate_from_observational_counts": True,
            "unit_of_independence": "experiment",
            "independent_rule_count_reported_separately": True,
            "automatic_confidence_adjustment": False,
            "automatic_promotion": False,
            "causal_interpretation": False,
            "principle_mapping_enabled": True,
            "normalized_contract_only": True,
            "raw_source_ingestion": False,
            "adjacent_lineage_required": True,
            "observed_effect_reinterpretation": False,
        },
    }
    summary = {
        "source_schema": (
            contract.get("source_schema") if contract else knowledge_payload.get("schema")
        ),
        "contract_schema": contract.get("schema") if contract else None,
        "contract_hash": contract.get("contract_hash") if contract else None,
        "contract_status": "VALID" if contract_source_ok and not contract_rejections else "REJECTED",
        "claims_seen": len(claim_records),
        "eligible_claims": len(eligible),
        "rejected_claims": len(rejected) + len(normalization_rejections),
        "experiments": len(experiment_ids),
        "unique_rules": len(rule_ids),
        "status_counts": status_counts,
        "rejections": [
            *contract_rejections,
            *normalization_rejections,
            *rejected,
        ],
        "target_evidence_records": len(target_records),
        "observed_effect_records": len(observed_records),
        "target_claim_signal_records": len(target_claim_records),
        "principle_signal_records": len(target_records),
        "target_evidence_rejections": contract_rejections,
        "raw_source_records_read": 0,
    }
    return channel, summary


def perturbation_outcome(
    baseline_status: str,
    mutant_status: str,
) -> str:
    pair = (baseline_status, mutant_status)
    outcomes = {
        ("support", "support"): "preserved_support",
        ("support", "neutral"): "disrupted_support",
        ("support", "counterexample"): "induced_counterexample",
        ("neutral", "support"): "induced_support",
        ("neutral", "counterexample"): "induced_counterexample",
        ("counterexample", "counterexample"): "preserved_counterexample",
        ("counterexample", "neutral"): "counterexample_resolved",
        ("counterexample", "support"): "counterexample_resolved",
    }
    return outcomes.get(pair, "no_claim_transition")


def perturbation_status(cases: list[dict[str, Any]]) -> str:
    challenge_outcomes = {"disrupted_support", "induced_counterexample"}
    corroborating_outcomes = {
        "preserved_support",
        "induced_support",
        "counterexample_resolved",
    }
    challenge_parents = {
        c["parent_rule_id"]
        for c in cases
        if c["outcome"] in challenge_outcomes
    }
    corroborating_parents = {
        c["parent_rule_id"]
        for c in cases
        if c["outcome"] in corroborating_outcomes
    }
    persistent_parents = {
        c["parent_rule_id"]
        for c in cases
        if c["outcome"] == "preserved_counterexample"
    }
    if (
        (challenge_parents and corroborating_parents)
        or (persistent_parents and (challenge_parents or corroborating_parents))
    ):
        return "MIXED_PERTURBATION_RESPONSE"
    if len(challenge_parents) >= 2:
        return "CHALLENGED_ACROSS_PARENTS"
    if challenge_parents:
        return "CHALLENGE_SIGNAL_SINGLE_PARENT"
    if len(corroborating_parents) >= 2:
        return "ROBUST_ACROSS_PARENTS"
    if corroborating_parents:
        return "ROBUSTNESS_SIGNAL_SINGLE_PARENT"
    if persistent_parents:
        return "COUNTEREXAMPLE_PERSISTS"
    return "INSUFFICIENT_CLAIM_SIGNAL"


def build_perturbation_evidence(
    mutation_payload: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Aggregate producer-normalized claim signals, never raw observations."""
    records, contract_rejections, contract = contract_records(mutation_payload)
    contract_source_ok = bool(
        contract is not None
        and contract.get("source_kind") == "mutation_analysis"
    )
    if not contract_source_ok and contract is not None:
        contract_rejections.append({
            "record_id": "*",
            "reason": "experimental_evidence_contract_source_kind_invalid",
        })
        records = []
    normalization_rejections = (
        list(contract.get("normalization_rejections", []))
        if contract_source_ok and isinstance(contract, dict)
        else []
    )
    observed_records = [
        record for record in records
        if record.get("interpretation_level") == "OBSERVED_EFFECT"
    ]
    claim_records = [
        record for record in records
        if record.get("interpretation_level") == "CLAIM_SIGNAL"
    ]
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for record in observed_records:
        if record.get("source_kind") != "mutation_analysis":
            rejected.append({
                "mutation_id": ss(record.get("evidence_record_id"), "unknown"),
                "reason": "record_source_kind_invalid",
            })
            continue
        eligibility = record.get("eligibility", {})
        if eligibility.get("status") != "ELIGIBLE":
            context = record.get("context", {})
            rejected.append({
                "mutation_id": ss(context.get("mutation_id"), "unknown"),
                "reason": ss(eligibility.get("reason"), "producer_rejected"),
            })
    for record in claim_records:
        if record.get("source_kind") != "mutation_analysis":
            continue
        if record.get("eligibility", {}).get("status") == "ELIGIBLE":
            eligible.append(record)

    by_claim: dict[str, dict[str, Any]] = {}
    for cid in CLAIM_SPECS:
        cases: list[dict[str, Any]] = []
        for record in eligible:
            if ss(record.get("claim_id")).strip() != cid:
                continue
            effect = record.get("effect", {})
            baseline_claim = effect.get("baseline_claim", {})
            treatment_claim = effect.get("treatment_claim", {})
            if not isinstance(baseline_claim, dict):
                baseline_claim = {}
            if not isinstance(treatment_claim, dict):
                treatment_claim = {}
            baseline_status = ss(baseline_claim.get("status"), "unavailable")
            mutant_status = ss(treatment_claim.get("status"), "unavailable")
            outcome = ss(effect.get("outcome"), "no_claim_transition")
            context = record.get("context", {})
            cases.append({
                "mutation_id": ss(context.get("mutation_id"), "unknown"),
                "parent_rule_id": ss(
                    context.get("parent_rule_id"), "unknown"
                ).zfill(5),
                "mutation_parameter": ss(
                    context.get("mutation_parameter"), "unknown"
                ),
                "mutation_mode": ss(
                    context.get("mutation_mode"), "unknown"
                ),
                "effect": ss(effect.get("primary"), "unknown"),
                "comparison_confidence": conf(record.get("confidence")),
                "comparison_score": round(
                    sf(context.get("comparison_score")),
                    4,
                ),
                "baseline_match": record.get("matched_control_status"),
                "baseline_claim_status": baseline_status,
                "baseline_claim_strength": round(
                    max(0.0, min(1.0, sf(baseline_claim.get("strength")))), 4
                ),
                "baseline_reason": ss(baseline_claim.get("reason")),
                "mutant_claim_status": mutant_status,
                "mutant_claim_strength": round(
                    max(0.0, min(1.0, sf(treatment_claim.get("strength")))), 4
                ),
                "mutant_reason": ss(treatment_claim.get("reason")),
                "outcome": outcome,
                "evidence_record_id": record.get("evidence_record_id"),
                "observed_effect_record_ids": list(
                    record.get("lineage", {}).get("parent_record_ids", [])
                ),
                "provenance_hash": record.get("provenance_hash"),
            })

        informative = [
            case
            for case in cases
            if case["outcome"] != "no_claim_transition"
        ]
        parent_rules = sorted({
            case["parent_rule_id"] for case in informative
        })
        outcome_counts: dict[str, int] = {}
        for case in informative:
            outcome = case["outcome"]
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        by_claim[cid] = {
            "schema": "archon_perturbation_claim_evidence_v1",
            "status": perturbation_status(informative),
            "eligible_run_count": len(cases),
            "informative_run_count": len(informative),
            "unique_parent_rule_count": len(parent_rules),
            "parent_rules": parent_rules,
            "outcome_counts": outcome_counts,
            "cases": informative,
            "scientific_policy": {
                "separate_from_observational_counts": True,
                "independent_replication": False,
                "automatic_confidence_adjustment": False,
                "automatic_promotion": False,
            },
        }

    seen_reports = {
        ss(record.get("context", {}).get("mutation_id"), "unknown")
        for record in observed_records
    }
    eligible_reports = {
        ss(record.get("context", {}).get("mutation_id"), "unknown")
        for record in eligible
    }
    summary = {
        "source_schema": contract.get("source_schema") if contract else None,
        "contract_schema": contract.get("schema") if contract else None,
        "contract_hash": contract.get("contract_hash") if contract else None,
        "contract_status": (
            "VALID"
            if contract_source_ok and not contract_rejections
            else "REJECTED"
        ),
        "reports_seen": len(seen_reports),
        "eligible_reports": len(eligible_reports),
        "observed_effect_records": len(observed_records),
        "claim_signal_records": len(claim_records),
        "eligible_claim_signals": len(eligible),
        "rejected_reports": (
            len(rejected)
            + len(normalization_rejections)
            + len(contract_rejections)
        ),
        "rejections": [
            *contract_rejections,
            *normalization_rejections,
            *rejected,
        ],
        "raw_source_records_read": 0,
        "policy": {
            "minimum_comparison_confidence": "HIGH",
            "required_controls_must_be_closed": True,
            "unit_of_independence": "canonical_parent_rule",
            "observational_confidence_unchanged": True,
            "normalized_contract_only": True,
            "raw_source_ingestion": False,
            "producer_claim_interpretation_only": True,
            "observed_effect_reinterpretation": False,
        },
    }
    return by_claim, summary


# -----------------------------------------------------------------------------
# Scientific claim definitions
# -----------------------------------------------------------------------------
#
# All support / counterexample / neutral criteria are imported from
# scientific_claims.py. Evidence Engine only evaluates profiles and aggregates
# the resulting cases.
#
def label_confidence(score: float, support: int, counter: int) -> str:
    if support <= 0 and counter <= 0:
        return "NONE"
    if score >= 0.82 and support >= 10 and counter <= max(1, support // 8):
        return "VERY_HIGH"
    if score >= 0.68 and support >= 5 and counter <= max(2, support // 4):
        return "HIGH"
    if score >= 0.50 and support >= 2:
        return "MEDIUM"
    if support >= 1:
        return "LOW"
    return "NONE"


def status_from_evidence(support: int, counter: int, confidence: str) -> str:
    if support == 0 and counter == 0:
        return "unobserved"
    if counter > support and counter >= 2:
        return "contested"
    if confidence in {"HIGH", "VERY_HIGH"}:
        return "supported_principle"
    if support >= 2:
        return "multi_case_hypothesis"
    if support == 1:
        return "single_case_seed"
    return "weak_or_unclear"


def build_claims(profiles: list[dict[str, Any]]) -> list[EvidenceClaim]:
    out: list[EvidenceClaim] = []
    for cid, title, description, fn in CLAIMS:
        cases: list[EvidenceCase] = []
        for p in profiles:
            status, strength, reason = fn(p)
            rule = ss(p.get("rule"), "unknown").zfill(5) if ss(p.get("rule"), "") else "unknown"
            cases.append(
                EvidenceCase(
                    rule=rule,
                    status=status,
                    strength=round(max(0.0, min(1.0, strength)), 4),
                    reason=reason,
                    emg=round(sf(p.get("emergence_score")), 4),
                    val=round(sf(p.get("validation_quality")), 4),
                    know=round(sf(p.get("knowledge_score")), 4),
                    fb=round(sf(p.get("feedback_score")), 4),
                    civ=round(sf(p.get("civilization_score")), 4),
                )
            )
        support_cases = [c for c in cases if c.status == "support"]
        counter_cases = [c for c in cases if c.status == "counterexample"]
        neutral_cases = [c for c in cases if c.status == "neutral"]
        s_strength = sum(c.strength for c in support_cases)
        c_strength = sum(c.strength for c in counter_cases)
        # Bayesian-ish conservative score: starts uncertain, grows with support, drops with counterexamples.
        confidence_score = (1.0 + s_strength) / (2.0 + s_strength + c_strength + 0.25 * len(neutral_cases))
        confidence_score = round(max(0.0, min(1.0, confidence_score)), 4)
        conf_label = label_confidence(confidence_score, len(support_cases), len(counter_cases))
        out.append(
            EvidenceClaim(
                id=cid,
                title=title,
                description=description,
                support=len(support_cases),
                counterexamples=len(counter_cases),
                neutral=len(neutral_cases),
                confidence_score=confidence_score,
                confidence_label=conf_label,
                status=status_from_evidence(len(support_cases), len(counter_cases), conf_label),
                support_rules=[c.rule for c in sorted(support_cases, key=lambda x: x.strength, reverse=True)],
                counterexample_rules=[c.rule for c in sorted(counter_cases, key=lambda x: x.strength, reverse=True)],
                cases=sorted(cases, key=lambda x: (x.status != "support", x.status != "counterexample", -x.strength, x.rule)),
            )
        )
    return out



def _experimental_picture(
    supportive: int,
    contextual: int,
    challenging: int,
    experiment_count: int,
    unique_rule_count: int,
    mixed: int = 0,
    non_diagnostic: int = 0,
    insufficient: int = 0,
) -> str:
    if experiment_count == 0:
        return "UNTESTED"
    if mixed > 0:
        return "MIXED"
    if non_diagnostic > 0 and supportive == 0 and challenging == 0:
        return "NON_DIAGNOSTIC"
    if insufficient > 0 and supportive == 0 and challenging == 0:
        return "INSUFFICIENT_DATA"
    if unique_rule_count <= 1:
        if challenging > 0:
            return "LIMITED_SCOPE_WITH_CHALLENGE"
        if supportive > 0:
            return "LIMITED_SCOPE_SUPPORT"
        return "LIMITED_SCOPE_CONTEXT"
    if challenging > supportive:
        return "CHALLENGED"
    if supportive > 0 and challenging > 0:
        return "MIXED"
    if supportive > 0:
        return "CORROBORATED"
    if challenging > 0:
        return "CHALLENGED"
    if non_diagnostic > 0:
        return "NON_DIAGNOSTIC"
    if insufficient > 0:
        return "INSUFFICIENT_DATA"
    return "CONTEXT_ONLY"


def _perturbation_picture(status: str) -> str:
    normalized = ss(status, "INSUFFICIENT_CLAIM_SIGNAL")
    mapping = {
        "ROBUST_ACROSS_PARENTS": "ROBUST",
        "ROBUSTNESS_SIGNAL_SINGLE_PARENT": "LIMITED_ROBUSTNESS_SIGNAL",
        "MIXED_PERTURBATION_RESPONSE": "MIXED",
        "CHALLENGED_ACROSS_PARENTS": "CHALLENGED",
        "CHALLENGE_SIGNAL_SINGLE_PARENT": "LIMITED_CHALLENGE_SIGNAL",
        "COUNTEREXAMPLE_PERSISTS": "PERSISTENT_COUNTEREXAMPLE",
        "INSUFFICIENT_CLAIM_SIGNAL": "INSUFFICIENT",
    }
    return mapping.get(normalized, normalized)


def _build_evidence_gaps(
    *,
    observational_support: int,
    observational_counterexamples: int,
    observational_confidence: str,
    experiment_count: int,
    unique_rule_count: int,
    experimental_challenges: int,
    perturbation_status: str,
    experimental_non_diagnostic: int = 0,
    experimental_insufficient: int = 0,
) -> list[str]:
    gaps: list[str] = []
    if observational_support < 5:
        gaps.append("increase_independent_observational_support")
    if observational_counterexamples == 0:
        gaps.append("targeted_counterexample_search")
    if observational_confidence in {"NONE", "LOW", "MEDIUM"}:
        gaps.append("strengthen_observational_confidence")
    if experiment_count == 0:
        gaps.append("run_controlled_experiment")
    else:
        if unique_rule_count < 3:
            gaps.append("test_additional_independent_rules")
        if experimental_challenges > 0:
            gaps.append("resolve_experimental_scope_challenge")
        if experimental_non_diagnostic > 0:
            gaps.append("revise_target_metrics_or_success_criteria")
        if experimental_insufficient > 0:
            gaps.append("complete_target_metric_collection")
        gaps.append("extend_experimental_horizon")
        gaps.append("test_additional_conditions")
    if perturbation_status == "INSUFFICIENT_CLAIM_SIGNAL":
        gaps.append("collect_informative_perturbation_evidence")
    return sorted(set(gaps))


def _scientific_summary(
    *,
    observational_confidence: str,
    observational_support: int,
    observational_counterexamples: int,
    experimental_picture: str,
    supportive: int,
    contextual: int,
    challenging: int,
    perturbation_picture: str,
) -> str:
    sentences: list[str] = []

    if observational_support == 0 and observational_counterexamples == 0:
        sentences.append("No direct observational evidence is available.")
    else:
        sentences.append(
            f"Observational evidence is {observational_confidence.lower()} "
            f"with {observational_support} supporting cases and "
            f"{observational_counterexamples} counterexamples."
        )

    if experimental_picture == "UNTESTED":
        sentences.append("No controlled experimental mapping is available.")
    elif experimental_picture.startswith("LIMITED_SCOPE"):
        sentences.append(
            "Controlled experimental evidence is limited in scope "
            f"({supportive} supportive, {contextual} contextual, "
            f"{challenging} challenging links)."
        )
    elif experimental_picture == "CORROBORATED":
        sentences.append(
            "Controlled experiments provide corroborating evidence across "
            "multiple independent rules."
        )
    elif experimental_picture == "CHALLENGED":
        sentences.append(
            "Controlled experiments currently contain more challenge signals "
            "than supportive signals."
        )
    elif experimental_picture == "MIXED":
        sentences.append(
            "Controlled experiments provide a mixed evidence picture."
        )
    elif experimental_picture == "NON_DIAGNOSTIC":
        sentences.append(
            "The controlled experiment reached its declared target, but the "
            "result is non-diagnostic for the principle."
        )
    elif experimental_picture == "INSUFFICIENT_DATA":
        sentences.append(
            "The controlled experiment is target-linked but lacks the "
            "measurements required for interpretation."
        )
    else:
        sentences.append(
            "Controlled experiments currently provide contextual evidence only."
        )

    if perturbation_picture == "INSUFFICIENT":
        sentences.append("Perturbation evidence is currently insufficient.")
    elif perturbation_picture == "MIXED":
        sentences.append("Perturbation tests show a mixed response.")
    elif perturbation_picture in {"ROBUST", "LIMITED_ROBUSTNESS_SIGNAL"}:
        sentences.append("Perturbation tests provide a robustness signal.")
    elif perturbation_picture in {
        "CHALLENGED",
        "LIMITED_CHALLENGE_SIGNAL",
        "PERSISTENT_COUNTEREXAMPLE",
    }:
        sentences.append("Perturbation tests provide a challenge signal.")
    else:
        sentences.append(
            f"Perturbation evidence status is {perturbation_picture.lower()}."
        )

    return " ".join(sentences)


def build_principle_evidence_profiles(
    claims: list[EvidenceClaim],
    perturbation_by_claim: dict[str, dict[str, Any]],
    experiment_mapping_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic evidence dossiers for each General Principle.

    Stage 2C.1 synthesizes channel status and evidence gaps. It does not alter
    observational confidence, promote principles, or produce consensus.
    """
    experiment_by_principle = experiment_mapping_summary.get(
        "by_principle", {}
    )
    if not isinstance(experiment_by_principle, dict):
        experiment_by_principle = {}

    profiles: dict[str, Any] = {}

    for claim in claims:
        principle_id = claim.id
        experimental = experiment_by_principle.get(principle_id, {})
        if not isinstance(experimental, dict):
            experimental = {}

        supportive = si(experimental.get("supportive_count"))
        contextual = si(experimental.get("contextual_count"))
        challenging = si(experimental.get("challenging_count"))
        mixed = si(experimental.get("mixed_count"))
        non_diagnostic = si(experimental.get("non_diagnostic_count"))
        insufficient = si(experimental.get("insufficient_count"))
        experiment_count = si(experimental.get("unique_experiment_count"))
        unique_rule_count = si(experimental.get("unique_rule_count"))

        perturbation = perturbation_by_claim.get(principle_id, {})
        perturbation_status = ss(
            perturbation.get("status"),
            "INSUFFICIENT_CLAIM_SIGNAL",
        )
        perturbation_picture = _perturbation_picture(
            perturbation_status
        )

        experimental_picture = _experimental_picture(
            supportive,
            contextual,
            challenging,
            experiment_count,
            unique_rule_count,
            mixed,
            non_diagnostic,
            insufficient,
        )

        evidence_gaps = _build_evidence_gaps(
            observational_support=claim.support,
            observational_counterexamples=claim.counterexamples,
            observational_confidence=claim.confidence_label,
            experiment_count=experiment_count,
            unique_rule_count=unique_rule_count,
            experimental_challenges=challenging,
            experimental_non_diagnostic=non_diagnostic,
            experimental_insufficient=insufficient,
            perturbation_status=perturbation_status,
        )

        summary = _scientific_summary(
            observational_confidence=claim.confidence_label,
            observational_support=claim.support,
            observational_counterexamples=claim.counterexamples,
            experimental_picture=experimental_picture,
            supportive=supportive,
            contextual=contextual,
            challenging=challenging,
            perturbation_picture=perturbation_picture,
        )

        experimental_profile = {
            "picture": experimental_picture,
            "supportive_links": supportive,
            "contextual_links": contextual,
            "challenging_links": challenging,
            "unique_experiment_count": experiment_count,
            "unique_rule_count": unique_rule_count,
            "experiment_ids": list(
                experimental.get("experiment_ids", [])
            ),
            "rule_ids": list(experimental.get("rule_ids", [])),
            "mapping_ids": list(
                experimental.get("mapping_ids", [])
            ),
        }
        if mixed or non_diagnostic or insufficient:
            experimental_profile.update({
                "mixed_links": mixed,
                "non_diagnostic_links": non_diagnostic,
                "insufficient_links": insufficient,
            })

        profiles[principle_id] = {
            "schema": "archon_principle_evidence_profile_v1",
            "principle_id": principle_id,
            "title": claim.title,
            "observational": {
                "status": claim.status,
                "support": claim.support,
                "counterexamples": claim.counterexamples,
                "neutral": claim.neutral,
                "confidence_score": claim.confidence_score,
                "confidence_label": claim.confidence_label,
                "support_rules": list(claim.support_rules),
                "counterexample_rules": list(
                    claim.counterexample_rules
                ),
            },
            "experimental": experimental_profile,
            "perturbation": {
                "picture": perturbation_picture,
                "raw_status": perturbation_status,
                "informative_run_count": si(
                    perturbation.get("informative_run_count")
                ),
                "unique_parent_rule_count": si(
                    perturbation.get("unique_parent_rule_count")
                ),
                "parent_rules": list(
                    perturbation.get("parent_rules", [])
                ),
                "outcome_counts": dict(
                    perturbation.get("outcome_counts", {})
                ),
            },
            "overall_picture": {
                "observational_strength": claim.confidence_label,
                "experimental_picture": experimental_picture,
                "perturbation_picture": perturbation_picture,
                "scientific_summary": summary,
                "evidence_gaps": evidence_gaps,
            },
            "scientific_policy": {
                "observational_confidence_changed": False,
                "automatic_promotion": False,
                "consensus_effect": False,
                "deterministic_templates": True,
                "llm_summary": False,
            },
        }

    summary = {
        "schema": "archon_principle_evidence_profiles_v1",
        "profile_count": len(profiles),
        "principles_with_experiments": sum(
            1
            for profile in profiles.values()
            if profile["experimental"]["unique_experiment_count"] > 0
        ),
        "principles_with_perturbation_signal": sum(
            1
            for profile in profiles.values()
            if profile["perturbation"]["picture"] != "INSUFFICIENT"
        ),
        "principles_with_experimental_challenges": sum(
            1
            for profile in profiles.values()
            if profile["experimental"]["challenging_links"] > 0
        ),
        "profiles": profiles,
        "scientific_policy": {
            "observational_confidence_changed": False,
            "automatic_promotion": False,
            "consensus_effect": False,
            "profile_is_input_for_future_consensus": True,
        },
    }
    return summary

def render_md(
    claims: list[EvidenceClaim],
    profiles: list[dict[str, Any]],
    root: Path,
    results: Path,
    perturbation_by_claim: dict[str, dict[str, Any]],
    perturbation_summary: dict[str, Any],
    experimental_evidence: dict[str, Any],
    experimental_summary: dict[str, Any],
    experiment_principle_mappings: list[dict[str, Any]],
    experiment_mapping_summary: dict[str, Any],
    principle_evidence_profiles: dict[str, Any],
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target_records = experimental_evidence.get("target_evidence_records", [])
    target_lines: list[str] = []
    if target_records:
        target_lines = [
            "## Target-Aware Experimental Interpretation",
            "",
            "| Experiment | Target | Effect | Relevance | Confidence | Matched control | Limitations |",
            "| --- | --- | --- | --- | --- | --- | --- |",
            *[
                (
                    f"| {item.get('experiment_id')} | {item.get('target_id')} | "
                    f"{item.get('effect')} | {item.get('relevance')} | "
                    f"{item.get('confidence')} | "
                    f"{item.get('matched_control_status')} | "
                    f"{'; '.join(item.get('limitations', [])) or '-'} |"
                )
                for item in target_records
            ],
            "",
            "Target provenance records experimental intent only; it never implies support.",
            "",
        ]
    lines: list[str] = [
        "# Evidence Report v31.1",
        "",
        "Evidence Engine collects support and counterexamples for principle-level claims using `observer_profiles_v30.json`.",
        "",
        "## Run Metadata",
        "",
        f"- Created: `{now}`",
        f"- Analyzer root: `{root}`",
        f"- Results folder: `{results}`",
        f"- Profiles analyzed: **{len(profiles)}**",
        f"- Mutation reports eligible: **{si(perturbation_summary.get('eligible_reports'))}** / **{si(perturbation_summary.get('reports_seen'))}**",
        f"- Experiment claims eligible: **{si(experimental_summary.get('eligible_claims'))}** / **{si(experimental_summary.get('claims_seen'))}**",
        "- Perturbation and experimental evidence are tracked separately and do not increment observational support.",
        "",
        "## Experimental Evidence Channel",
        "",
        f"- Status: **{experimental_evidence.get('status', 'SOURCE_NOT_AVAILABLE')}**",
        f"- Scoped claims: **{si(experimental_evidence.get('claim_count'))}**",
        f"- Experiments: **{si(experimental_evidence.get('experiment_count'))}**",
        f"- Unique rules: **{si(experimental_evidence.get('unique_rule_count'))}**",
        "- Principle mapping: **explicit rules enabled in Stage 2B**",
        "- Automatic confidence adjustment: **disabled**",
        "",
        "| Claim | Experiment | Type | Status | Confidence | Rules | Horizon |",
        "| --- | --- | --- | --- | --- | --- | ---: |",
        *[
            (
                f"| {item.get('claim_id')} | {item.get('experiment_id')} | "
                f"{item.get('claim_type')} | {item.get('status')} | "
                f"{item.get('confidence')} | "
                f"{', '.join(item.get('rule_ids', [])) or '-'} | "
                f"{item.get('horizon') if item.get('horizon') is not None else '-'} |"
            )
            for item in experimental_evidence.get("claims", [])
        ],
        "",
        *target_lines,
        "## Experiment → Principle Mapping",
        "",
        f"- Mappings created: **{si(experiment_mapping_summary.get('mappings_created'))}**",
        f"- Principles linked: **{si(experiment_mapping_summary.get('principles_linked'))}**",
        f"- Claims without mapping: **{si(experiment_mapping_summary.get('claims_without_mapping'))}**",
        "- Policy: mappings classify relevance only; they do not change principle confidence.",
        "",
        "| Experiment claim | Principle | Relation | Direction | Preserved | Changed | Rules |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *[
            (
                f"| {item.get('experiment_claim_id')} | "
                f"{item.get('principle_id')} | {item.get('relation')} | "
                f"{item.get('direction')} | "
                f"{', '.join(item.get('matched_metrics', [])) or '-'} | "
                f"{', '.join(item.get('matched_contradicting_metrics', [])) or '-'} | "
                f"{', '.join(item.get('rule_ids', [])) or '-'} |"
            )
            for item in experiment_principle_mappings
        ],
        "",
        "## Principle Evidence Summary",
        "",
        "| ID | Claim | Status | Support | Counterexamples | Neutral | Confidence | Score | Perturbation status | Parents |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- | ---: |",
    ]
    for c in claims:
        perturbation = perturbation_by_claim.get(c.id, {})
        lines.append(
            f"| {c.id} | {c.title} | {c.status} | {c.support} | {c.counterexamples} | {c.neutral} | {c.confidence_label} | {c.confidence_score:.3f} | "
            f"{perturbation.get('status', 'INSUFFICIENT_CLAIM_SIGNAL')} | "
            f"{si(perturbation.get('unique_parent_rule_count'))} |"
        )

    lines.extend(["", "## Claim Details", ""])
    for c in claims:
        support = ", ".join(c.support_rules[:20]) if c.support_rules else "-"
        counters = ", ".join(c.counterexample_rules[:20]) if c.counterexample_rules else "-"
        lines.extend([
            f"### {c.id}: {c.title}",
            "",
            c.description,
            "",
            f"- Status: **{c.status}**",
            f"- Confidence: **{c.confidence_label}** ({c.confidence_score:.3f})",
            f"- Support: **{c.support}**",
            f"- Counterexamples: **{c.counterexamples}**",
            f"- Support rules: {support}",
            f"- Counterexample rules: {counters}",
            "",
            "| Rule | Case | Strength | Reason | EMG | VAL | KNOW | FB | CIV |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for case in c.cases[:25]:
            if case.status == "neutral" and case.strength < 0.20:
                continue
            lines.append(
                f"| {case.rule} | {case.status} | {case.strength:.3f} | {case.reason} | {case.emg:.3f} | {case.val:.3f} | {case.know:.3f} | {case.fb:.3f} | {case.civ:.3f} |"
            )
        lines.append("")
        perturbation = perturbation_by_claim.get(c.id, {})
        lines.extend([
            "#### Controlled perturbation evidence",
            "",
            f"- Status: **{perturbation.get('status', 'INSUFFICIENT_CLAIM_SIGNAL')}**",
            f"- Informative runs: **{si(perturbation.get('informative_run_count'))}**",
            f"- Independent parent rules: **{si(perturbation.get('unique_parent_rule_count'))}**",
            "- Policy: perturbation cases test robustness but do not alter observational counts or confidence.",
            "",
        ])
        perturbation_cases = perturbation.get("cases", [])
        if perturbation_cases:
            lines.extend([
                "| Mutation | Parent | Parameter | Baseline claim | Mutant claim | Outcome | Confidence |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ])
            for case in perturbation_cases[:20]:
                lines.append(
                    f"| {case.get('mutation_id')} | {case.get('parent_rule_id')} | "
                    f"{case.get('mutation_parameter')} | {case.get('baseline_claim_status')} | "
                    f"{case.get('mutant_claim_status')} | {case.get('outcome')} | "
                    f"{case.get('comparison_confidence')} |"
                )
            lines.append("")

    lines.extend([
        "## Principle Evidence Profiles",
        "",
    ])
    for principle_id, profile in (
        principle_evidence_profiles.get("profiles", {}).items()
    ):
        overall = profile.get("overall_picture", {})
        observational = profile.get("observational", {})
        experimental = profile.get("experimental", {})
        perturbation = profile.get("perturbation", {})
        gaps = overall.get("evidence_gaps", [])
        lines.extend([
            f"### {principle_id}: {profile.get('title', '')}",
            "",
            f"- Observational: **{overall.get('observational_strength', 'NONE')}** "
            f"({observational.get('support', 0)} support / "
            f"{observational.get('counterexamples', 0)} counterexamples)",
            f"- Experimental: **{overall.get('experimental_picture', 'UNTESTED')}** "
            f"({experimental.get('supportive_links', 0)} supportive / "
            f"{experimental.get('contextual_links', 0)} contextual / "
            f"{experimental.get('challenging_links', 0)} challenging)",
            f"- Perturbation: **{overall.get('perturbation_picture', 'INSUFFICIENT')}**",
            f"- Scientific picture: {overall.get('scientific_summary', '')}",
            f"- Evidence gaps: {', '.join(gaps) if gaps else 'none'}",
            "",
        ])

    lines.extend([
        "## How to read this",
        "",
        "- `support=1` means a principle is still a seed, not a law.",
        "- Counterexamples are valuable: they show where the current hypothesis may be too broad.",
        "- Confidence is intentionally conservative until many independent rules support the same claim.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build evidence report from ObserverProfile v30.")
    parser.add_argument("results_folder", help="Shared Universe Search results folder")
    parser.add_argument("--root", default=None, help="Analysis report folder. Default: Results/Analysis")
    parser.add_argument("--json-out", default=None, help="Output JSON path. Default: ROOT/evidence_report.json")
    parser.add_argument("--md-out", default=None, help="Output Markdown path. Default: ROOT/evidence_report.md")
    parser.add_argument(
        "--mutations",
        default=None,
        help=(
            "Mutation analysis JSON. "
            "Default: ROOT/Mutations/mutation_analysis.json"
        ),
    )
    parser.add_argument(
        "--experiment-knowledge",
        default=None,
        help=(
            "Experiment Knowledge JSON. "
            "Default: ROOT/Experiments/experiment_knowledge.json"
        ),
    )
    args = parser.parse_args()

    results = Path(args.results_folder).resolve()
    root = Path(args.root).resolve() if args.root else analysis_results_dir().resolve()
    root.mkdir(parents=True, exist_ok=True)
    knowledge_root = knowledge_atlas_dir().resolve()
    profiles = load_profiles(results)
    claims = build_claims(profiles)
    mutation_path = (
        Path(args.mutations).resolve()
        if args.mutations
        else root / "Mutations" / "mutation_analysis.json"
    )
    mutation_payload = load_optional_json(mutation_path)
    perturbation_by_claim, perturbation_summary = (
        build_perturbation_evidence(mutation_payload)
    )
    experiment_knowledge_path = (
        Path(args.experiment_knowledge).resolve()
        if args.experiment_knowledge
        else root / "Experiments" / "experiment_knowledge.json"
    )
    experiment_knowledge_payload = load_optional_json(
        experiment_knowledge_path
    )
    experimental_evidence, experimental_summary = (
        build_experimental_evidence(experiment_knowledge_payload)
    )
    experiment_principle_mappings, experiment_mapping_summary = (
        build_experiment_principle_mappings(experimental_evidence)
    )
    principle_evidence_profiles = build_principle_evidence_profiles(
        claims,
        perturbation_by_claim,
        experiment_mapping_summary,
    )

    payload = {
        "schema": "evidence_report_v31_4_stage2c1",
        "created": datetime.now().isoformat(timespec="seconds"),
        "results_folder": str(results),
        "analyzer_root": str(root),
        "profile_count": len(profiles),
        "scientific_claims_registry": {
            "module": "scientific_claims.py",
            "claim_versions": {
                claim_id: spec.version
                for claim_id, spec in CLAIM_SPECS.items()
            },
            "claim_families": {
                claim_id: spec.family
                for claim_id, spec in CLAIM_SPECS.items()
            },
        },
        "claims": [
            {
                **asdict(c),
                "perturbation_evidence": perturbation_by_claim.get(
                    c.id, {}
                ),
            }
            for c in claims
        ],
        "perturbation_evidence_summary": perturbation_summary,
        "experimental_evidence": experimental_evidence,
        "experimental_evidence_summary": experimental_summary,
        "experiment_principle_mappings": experiment_principle_mappings,
        "experiment_principle_mapping_summary": experiment_mapping_summary,
        "principle_evidence_profiles": principle_evidence_profiles,
        "inputs": {
            "observer_profiles_v30": str(results / "observer_profiles_v30.json"),
            "research_atlas": str(knowledge_root / "research_atlas.json"),
            "general_principles": str(root / "general_principles.json"),
        "scientific_claims": str(
            PROJECT_ROOT / "Analyzer_next" / "core" / "scientific_claims.py"
        ),
            "mutation_analysis": str(mutation_path),
            "experiment_knowledge": str(experiment_knowledge_path),
        },
    }

    json_out = Path(args.json_out).resolve() if args.json_out else root / "evidence_report.json"
    md_out = Path(args.md_out).resolve() if args.md_out else root / "evidence_report.md"
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_out.write_text(
        render_md(
            claims,
            profiles,
            root,
            results,
            perturbation_by_claim,
            perturbation_summary,
            experimental_evidence,
            experimental_summary,
            experiment_principle_mappings,
            experiment_mapping_summary,
            principle_evidence_profiles,
        ),
        encoding="utf-8",
    )

    print("")
    print("=" * 64)
    print("Universe Search Evidence Engine v31.4 — Stage 2C.1")
    print("=" * 64)
    print(f"Profiles:      {len(profiles)}")
    print(f"Claims:        {len(claims)}")
    print(
        "Perturbations: "
        f"{si(perturbation_summary.get('eligible_reports'))} eligible / "
        f"{si(perturbation_summary.get('reports_seen'))} seen"
    )
    print(
        "Experiments:   "
        f"{si(experimental_summary.get('eligible_claims'))} claims / "
        f"{si(experimental_summary.get('experiments'))} experiments / "
        f"{si(experimental_summary.get('unique_rules'))} unique rules"
    )
    print(
        "Exp channel:   "
        f"{experimental_evidence.get('status', 'SOURCE_NOT_AVAILABLE')}"
    )
    print(
        "Exp mappings:  "
        f"{si(experiment_mapping_summary.get('mappings_created'))} links / "
        f"{si(experiment_mapping_summary.get('principles_linked'))} principles / "
        f"{si(experiment_mapping_summary.get('claims_without_mapping'))} unmapped"
    )
    print(
        "Ev profiles:   "
        f"{si(principle_evidence_profiles.get('profile_count'))} principles / "
        f"{si(principle_evidence_profiles.get('principles_with_experiments'))} experimental / "
        f"{si(principle_evidence_profiles.get('principles_with_perturbation_signal'))} perturbation signals"
    )
    print(f"Output MD:     {md_out}")
    print(f"Output JSON:   {json_out}")
    print("-" * 64)
    for c in claims:
        print(
            f"{c.id}: {c.title} | {c.status} | support={c.support} | "
            f"counter={c.counterexamples} | confidence={c.confidence_label} "
            f"({c.confidence_score:.2f}) | perturbation="
            f"{perturbation_by_claim.get(c.id, {}).get('status', 'INSUFFICIENT_CLAIM_SIGNAL')}"
        )
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
