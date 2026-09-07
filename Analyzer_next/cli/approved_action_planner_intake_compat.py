#!/usr/bin/env python3
"""OL2 compatibility wrapper for audited approved-action planner intake.

Keeps the legacy Stage 6.1 implementation frozen while preventing explicit
ResearchAction kinds from being reclassified by incidental words in rationale
or suggested-target prose.  The legacy module still owns persistence,
provenance, validation, and intake schema.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

legacy = importlib.import_module(
    "Analyzer_next.compatibility.legacy_analyzer.approved_action_planner_intake"
)
from Analyzer_next.core.experimental_evidence.targeting import (  # noqa: E402
    build_scientific_target,
)

_ORIGINAL_BUILD = legacy.build_experiment_shape
_ORIGINAL_BUILD_INTAKE = legacy.build_intake


def _metric_validation_baseline_shape(
    action: Dict[str, Any],
    proposal: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a non-perturbation baseline intent from an explicit action kind.

    The action is a metric baseline collection task.  Words such as
    ``response`` or ``recovery`` may legitimately occur in its rationale, but
    they must not silently convert the scientific type into a perturbation
    experiment.
    """
    title = str(action.get("title") or "")
    affected_principles = [
        str(item)
        for item in legacy.as_list(proposal.get("affected_principles"))
        if item
    ]
    affected_signals = [
        str(item)
        for item in legacy.as_list(proposal.get("affected_signals"))
        if item
    ]
    evidence_channels = ["metric_validation", "replication", "action_validation"]
    for signal in affected_signals:
        if signal not in evidence_channels:
            evidence_channels.append(signal)
    return {
        "experiment_type": "metric_validation_baseline",
        "hypothesis_prompt": (
            f"Does the approved action '{title}' produce the evidence "
            "required by its declared success criteria?"
        ),
        "variables": [
            {
                "name": "experimental_condition",
                "role": "independent",
                "required": True,
            },
            {
                "name": "replicate_seed",
                "role": "replication",
                "required": True,
            },
        ],
        "required_controls": [
            {
                "type": "matched_baseline",
                "match_on": ["rule_id", "field_size", "topology", "duration"],
                "required": True,
            }
        ],
        "protocol_requirements": [
            "Collect the declared metric under reproducible matched observation settings.",
            "Use independent replicate seeds rather than canonical-seed pseudoreplication.",
            "Preserve the canonical parent rule and report eligibility/null outcomes.",
        ],
        "success_criteria": legacy.split_criteria(action.get("done_when")),
        "target_description": legacy.normalized_text(action.get("suggested_target")),
        "evidence_channels": evidence_channels,
        "affected_principles": affected_principles,
        "affected_signals": affected_signals,
        "runtime_hint": action.get("estimated_runtime"),
        "cost_hint": action.get("estimated_cost"),
        "automation_hint": action.get("automation_level"),
        "priority": action.get("priority"),
        "strategic_score": action.get("strategic_score"),
    }



def _cohort_gap_program_shape(
    action: Dict[str, Any],
    proposal: Dict[str, Any],
) -> Dict[str, Any]:
    """Preserve Planner cohort-gap semantics instead of flattening to BASE/TEST."""
    title = str(action.get("title") or "")
    action_id = str(action.get("action_id") or "").strip().upper()
    suffix = action_id[len("EXP-COHORT-"):] if action_id.startswith("EXP-COHORT-") else ""
    search_job_id = f"SEARCH-{suffix}" if suffix else None
    mutation_job_id = f"MUTATE-{suffix}" if suffix else None
    affected_principles = [
        str(item)
        for item in legacy.as_list(proposal.get("affected_principles"))
        if item
    ]
    affected_signals = [
        str(item)
        for item in legacy.as_list(proposal.get("affected_signals"))
        if item
    ]
    evidence_channels = [
        "cohort_discovery",
        "counterexample",
        "negative_evidence",
        "scope_boundary",
        "isolated_mutation_evidence",
    ]
    for signal in affected_signals:
        if signal not in evidence_channels:
            evidence_channels.append(signal)
    return {
        "experiment_type": "cohort_gap_program",
        "hypothesis_prompt": (
            f"Does the approved cohort-gap program '{title}' find a reproducible "
            "member of the declared missing regime, or document persistent absence "
            "under a pinned Search budget?"
        ),
        "variables": [
            {
                "name": "search_mode",
                "role": "search_execution",
                "required": True,
                "value": "cohort_target",
            },
            {
                "name": "search_job_id",
                "role": "search_execution",
                "required": True,
                "value": search_job_id,
            },
            {
                "name": "search_budget",
                "role": "search_control",
                "required": True,
                "value": {"mode": "ENGINE_DEFAULT_PINNED_AT_MATERIALIZATION"},
            },
            {
                "name": "mutation_job_id",
                "role": "separate_intervention_branch",
                "required": False,
                "value": mutation_job_id,
            },
        ],
        "required_controls": [
            {
                "type": "positive_reference_cohort",
                "role": "reference_input",
                "match_on": ["runtime", "field_size", "search_mode"],
                "required": True,
                "creates_treatment_arm": False,
            }
        ],
        "protocol_requirements": [
            "Run Universe Search in cohort_target mode using the matching Planner Search job.",
            "Pin the effective Search engine budget before launch and preserve all null/candidate outcomes.",
            "Treat reference rules as Search seeds/controls, not synthetic Observer treatment arms.",
            "Keep Observer mutation work in a separate isolated intervention branch.",
            "Promote a mutation only after reproducible validation; never overwrite parent rules.",
        ],
        "success_criteria": legacy.split_criteria(action.get("done_when")),
        "target_description": legacy.normalized_text(action.get("suggested_target")),
        "evidence_channels": evidence_channels,
        "affected_principles": affected_principles,
        "affected_signals": affected_signals,
        "runtime_hint": action.get("estimated_runtime"),
        "cost_hint": action.get("estimated_cost"),
        "automation_hint": action.get("automation_level"),
        "priority": action.get("priority"),
        "strategic_score": action.get("strategic_score"),
    }

def build_experiment_shape_compat(
    action: Dict[str, Any],
    proposal: Dict[str, Any],
) -> Dict[str, Any]:
    kind = str(action.get("kind") or "").strip().lower()
    if kind == "metric_validation_baseline":
        return _metric_validation_baseline_shape(action, proposal)
    if kind == "cohort_gap_program":
        return _cohort_gap_program_shape(action, proposal)
    return _ORIGINAL_BUILD(action, proposal)


def build_intake_compat(
    analysis_root: Path,
    existing: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach one hash-protected semantic target to eligible intents.

    Non-targeted and ambiguous Director actions retain their frozen v1 bytes.
    """
    payload = _ORIGINAL_BUILD_INTAKE(analysis_root, existing)
    targeted = 0
    for record in legacy.as_list(payload.get("records")):
        if not isinstance(record, dict) or record.get("active") is not True:
            continue
        action = legacy.as_dict(record.get("action"))
        intent = legacy.as_dict(record.get("experiment_intent"))
        provenance = legacy.as_dict(record.get("provenance"))
        target = build_scientific_target(
            action=action,
            experiment_intent=intent,
            provenance=provenance,
        )
        if target is None:
            continue
        record["scientific_target"] = target
        record["scientific_target_hash"] = target["target_hash"]
        intent["scientific_target"] = target
        record["experiment_intent"] = intent
        targeted += 1
    if not targeted:
        return payload
    summary = legacy.as_dict(payload.get("summary"))
    summary["targeted_intent_count"] = targeted
    payload["summary"] = summary
    policy = legacy.as_dict(payload.get("policy"))
    policy.update({
        "scientific_target_immutable": True,
        "target_intent_is_not_support": True,
    })
    payload["policy"] = policy
    payload["content_hash"] = legacy.canonical_hash({
        "summary": summary,
        "records": legacy.as_list(payload.get("records")),
        "blocked_records": legacy.as_list(payload.get("blocked_records")),
        "source_state": legacy.as_dict(payload.get("source_state")),
    })
    return payload


def main() -> int:
    legacy.build_experiment_shape = build_experiment_shape_compat
    legacy.build_intake = build_intake_compat
    return int(legacy.main())


if __name__ == "__main__":
    raise SystemExit(main())
