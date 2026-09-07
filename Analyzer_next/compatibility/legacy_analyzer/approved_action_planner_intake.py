#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


VERSION = "1.0"
TITLE = (
    "ARCHON Stage 6.1 Approved Actions → Experiment Planner Intake"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def normalized_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def split_criteria(value: Any) -> List[str]:
    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    text = str(value or "").strip()
    if not text:
        return []

    separators = ("\n", " | ", "; ")
    parts = [text]
    for separator in separators:
        expanded: List[str] = []
        for item in parts:
            expanded.extend(item.split(separator))
        parts = expanded

    result: List[str] = []
    for item in parts:
        clean = item.strip(" \t-*•")
        if clean and clean not in result:
            result.append(clean)
    return result


def action_snapshot(action: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "action_id": action.get("action_id"),
        "title": action.get("title"),
        "suggested_target": action.get("suggested_target"),
        "done_when": action.get("done_when"),
        "rationale": action.get("rationale"),
    }


def build_experiment_shape(
    action: Dict[str, Any],
    proposal: Dict[str, Any],
) -> Dict[str, Any]:
    """Translate an approved ResearchAction into a planner-facing intent."""
    kind = str(action.get("kind") or "unspecified").lower()
    title = str(action.get("title") or "")
    target = str(action.get("suggested_target") or "")
    rationale = str(action.get("rationale") or "")
    combined = " ".join((kind, title, target, rationale)).lower()

    affected_principles = [
        str(item)
        for item in as_list(proposal.get("affected_principles"))
        if item
    ]
    affected_signals = [
        str(item)
        for item in as_list(proposal.get("affected_signals"))
        if item
    ]

    experiment_type = "controlled_action_validation"
    variables: List[Dict[str, Any]] = []
    controls: List[Dict[str, Any]] = []
    protocols: List[str] = []
    evidence_channels: List[str] = []

    if "perturb" in combined or "recovery" in combined:
        experiment_type = "perturbation_recovery_test"
        variables.extend([
            {
                "name": "perturbation_type",
                "role": "independent",
                "required": True,
            },
            {
                "name": "perturbation_strength",
                "role": "independent",
                "required": True,
            },
            {
                "name": "perturbation_tick",
                "role": "independent",
                "required": True,
            },
            {
                "name": "recovery_window",
                "role": "observation",
                "required": True,
            },
        ])
        controls.append({
            "type": "matched_unperturbed_control",
            "match_on": [
                "rule_id",
                "seed",
                "field_size",
                "topology",
                "duration",
            ],
            "required": True,
        })
        protocols.extend([
            "Run matched baseline and perturbed worlds.",
            "Record pre-perturbation, perturbation, and recovery phases.",
            "Compare recovery trajectory against the matched control.",
        ])
        evidence_channels.extend([
            "perturbation_response",
            "recovery_dynamics",
            "state_resilience",
        ])

    elif "cross_family" in combined or "cross-family" in combined:
        experiment_type = "cross_family_replication"
        variables.extend([
            {
                "name": "rule_family",
                "role": "stratification",
                "required": True,
            },
            {
                "name": "replicate_seed",
                "role": "independent",
                "required": True,
            },
        ])
        controls.append({
            "type": "within_family_reference_control",
            "match_on": ["duration", "field_size", "topology"],
            "required": True,
        })
        protocols.extend([
            "Use multiple rule families and matched run conditions.",
            "Report within-family and between-family effects separately.",
        ])
        evidence_channels.extend([
            "replication",
            "cross_family_scope",
            "generalization",
        ])

    elif "counterexample" in combined or "negative_cohort" in combined:
        experiment_type = "counterexample_search"
        variables.extend([
            {
                "name": "selection_constraints",
                "role": "search_filter",
                "required": True,
            },
            {
                "name": "search_budget",
                "role": "search_control",
                "required": True,
            },
        ])
        controls.append({
            "type": "positive_reference_cohort",
            "match_on": ["runtime", "field_size", "search_mode"],
            "required": True,
        })
        protocols.extend([
            "Declare the target claim before search.",
            "Search for violating cases under matched observation conditions.",
            "Preserve all candidates, including null results.",
        ])
        evidence_channels.extend([
            "counterexample",
            "negative_evidence",
            "scope_boundary",
        ])

    elif "control" in combined or "matched" in combined:
        experiment_type = "matched_control_study"
        variables.extend([
            {
                "name": "treatment_condition",
                "role": "independent",
                "required": True,
            },
            {
                "name": "matching_variables",
                "role": "control_definition",
                "required": True,
            },
        ])
        controls.append({
            "type": "matched_control_group",
            "match_on": [
                "rule_family",
                "seed",
                "field_size",
                "topology",
                "duration",
            ],
            "required": True,
        })
        protocols.extend([
            "Define treatment and control assignment before execution.",
            "Hold declared matching variables constant.",
            "Report effect size and uncertainty.",
        ])
        evidence_channels.extend([
            "matched_control",
            "causal_comparison",
            "knowledge_feedback",
        ])

    elif "scope" in combined or "topology" in combined or "field" in combined:
        experiment_type = "scope_condition_test"
        variables.extend([
            {
                "name": "field_size",
                "role": "independent",
                "required": False,
            },
            {
                "name": "topology",
                "role": "independent",
                "required": False,
            },
            {
                "name": "boundary_condition",
                "role": "independent",
                "required": False,
            },
            {
                "name": "seed",
                "role": "replication",
                "required": True,
            },
        ])
        controls.append({
            "type": "canonical_condition_control",
            "match_on": ["rule_id", "duration"],
            "required": True,
        })
        protocols.extend([
            "Vary one declared environmental condition at a time.",
            "Use the canonical Observer condition as control.",
            "Separate condition-sensitive and condition-invariant findings.",
        ])
        evidence_channels.extend([
            "scope",
            "condition_sensitivity",
            "replication",
        ])

    else:
        variables.extend([
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
        ])
        controls.append({
            "type": "matched_baseline",
            "match_on": [
                "rule_id",
                "field_size",
                "topology",
                "duration",
            ],
            "required": True,
        })
        protocols.extend([
            "Declare the hypothesis and controlled variables.",
            "Run a matched baseline.",
            "Report pass, fail, and inconclusive outcomes.",
        ])
        evidence_channels.append("action_validation")

    for signal in affected_signals:
        if signal not in evidence_channels:
            evidence_channels.append(signal)

    return {
        "experiment_type": experiment_type,
        "hypothesis_prompt": (
            f"Does the approved action '{title}' produce the evidence "
            "required by its declared success criteria?"
        ),
        "variables": variables,
        "required_controls": controls,
        "protocol_requirements": protocols,
        "success_criteria": split_criteria(action.get("done_when")),
        "target_description": normalized_text(
            action.get("suggested_target")
        ),
        "evidence_channels": evidence_channels,
        "affected_principles": affected_principles,
        "affected_signals": affected_signals,
        "runtime_hint": action.get("estimated_runtime"),
        "cost_hint": action.get("estimated_cost"),
        "automation_hint": action.get("automation_level"),
        "priority": action.get("priority"),
        "strategic_score": action.get("strategic_score"),
    }


def load_sources(analysis_root: Path) -> Dict[str, Any]:
    report_path = analysis_root / "research_director_report.json"
    report = load_json(report_path, {})
    if not isinstance(report, dict) or not report:
        raise RuntimeError(
            f"Missing or invalid Director report: {report_path}"
        )

    decisions = as_dict(report.get("human_review_decisions"))
    if not decisions:
        decisions = load_json(
            analysis_root / "human_review_decisions.json",
            {},
        )

    patch_state = as_dict(
        report.get("research_action_patch_state")
    )
    if not patch_state:
        patch_state = load_json(
            analysis_root / "research_action_patch_state.json",
            {},
        )

    lifecycle = as_dict(report.get("patch_lifecycle_closure"))
    if not lifecycle:
        lifecycle = load_json(
            analysis_root / "patch_lifecycle_closure.json",
            {},
        )

    application_receipt = as_dict(
        report.get("patch_application_receipt_verification")
    )
    if not application_receipt:
        application_receipt = load_json(
            analysis_root
            / "patch_application_receipt_verification.json",
            {},
        )

    return {
        "report_path": str(report_path),
        "report": report,
        "decisions": as_dict(decisions),
        "patch_state": as_dict(patch_state),
        "lifecycle": as_dict(lifecycle),
        "application_receipt": as_dict(application_receipt),
    }


def build_intake(
    analysis_root: Path,
    existing: Dict[str, Any],
) -> Dict[str, Any]:
    sources = load_sources(analysis_root)
    report = sources["report"]
    decisions = sources["decisions"]
    patch_state = sources["patch_state"]
    lifecycle = sources["lifecycle"]
    application_receipt = sources["application_receipt"]

    actions = {
        str(item.get("action_id")): item
        for item in as_list(report.get("actions"))
        if isinstance(item, dict) and item.get("action_id")
    }
    proposals = {
        str(item.get("proposal_id")): item
        for item in as_list(
            as_dict(
                report.get("recommendation_patch_proposals")
            ).get("proposals")
        )
        if isinstance(item, dict) and item.get("proposal_id")
    }
    overrides = {
        str(item.get("action_id")): item
        for item in as_list(patch_state.get("overrides"))
        if isinstance(item, dict) and item.get("action_id")
    }

    existing_records = {
        str(item.get("intake_id")): item
        for item in as_list(existing.get("records"))
        if isinstance(item, dict) and item.get("intake_id")
    }

    lifecycle_status = str(
        lifecycle.get("status") or "INACTIVE"
    )
    application_status = str(
        application_receipt.get("status") or "NO_RECEIPT"
    )
    active_application = (
        lifecycle_status == "ACTIVE"
        and application_status
        in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}
    )

    current_records: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []

    decision_records = [
        item
        for item in as_list(decisions.get("records"))
        if isinstance(item, dict)
    ]

    for decision in decision_records:
        proposal_id = str(decision.get("proposal_id") or "")
        decision_value = str(
            decision.get("decision") or ""
        ).upper()

        if decision_value != "APPROVED":
            continue

        proposal = proposals.get(proposal_id)
        if proposal is None:
            blocked.append({
                "proposal_id": proposal_id,
                "review_id": decision.get("review_id"),
                "reason": "PROPOSAL_NOT_FOUND",
            })
            continue

        action_id = str(
            proposal.get("target_action_id") or ""
        )
        action = actions.get(action_id)
        override = overrides.get(action_id)

        reasons: List[str] = []
        if not active_application:
            reasons.append(
                "PATCH_LIFECYCLE_NOT_ACTIVE_OR_UNVERIFIED"
            )
        if action is None:
            reasons.append("ACTION_NOT_FOUND")
        if override is None:
            reasons.append("PERSISTENT_OVERRIDE_NOT_FOUND")

        if action is not None and override is not None:
            expected_hash = override.get("snapshot_hash")
            actual_hash = canonical_hash(action_snapshot(action))
            if expected_hash != actual_hash:
                reasons.append("ACTION_OVERRIDE_HASH_MISMATCH")

        if reasons:
            blocked.append({
                "proposal_id": proposal_id,
                "review_id": decision.get("review_id"),
                "action_id": action_id or None,
                "reasons": reasons,
                "lifecycle_status": lifecycle_status,
                "application_receipt_status": application_status,
            })
            continue

        experiment_shape = build_experiment_shape(
            action,
            proposal,
        )
        provenance = {
            "source_action_id": action_id,
            "source_proposal_id": proposal_id,
            "source_review_id": decision.get("review_id"),
            "source_commit_id": patch_state.get(
                "source_commit_id"
            ),
            "source_application_id": (
                override.get("application_id")
                or patch_state.get("last_application_id")
            ),
            "source_manifest_id": patch_state.get(
                "last_manifest_id"
            ),
            "source_recommendation_ids": as_list(
                proposal.get("source_recommendations")
            ),
            "source_principle_ids": as_list(
                proposal.get("affected_principles")
            ),
            "source_consensus_signals": as_list(
                proposal.get("affected_signals")
            ),
            "decision_reviewed_at": decision.get(
                "reviewed_at"
            ),
            "decision_reviewed_by": decision.get(
                "reviewed_by"
            ),
            "decision_reason": decision.get(
                "decision_reason"
            ),
            "action_snapshot_hash": override.get(
                "snapshot_hash"
            ),
            "director_report_path": sources["report_path"],
        }

        fingerprint_payload = {
            "action_id": action_id,
            "proposal_id": proposal_id,
            "application_id": provenance[
                "source_application_id"
            ],
            "action_snapshot_hash": provenance[
                "action_snapshot_hash"
            ],
            "experiment_shape": experiment_shape,
        }
        fingerprint = canonical_hash(fingerprint_payload)
        intake_id = f"EPI-{fingerprint[:16].upper()}"

        prior = existing_records.get(intake_id, {})
        planner_state = as_dict(
            prior.get("planner_state")
        ) or {
            "status": "PENDING_PLANNER_REVIEW",
            "planner_experiment_id": None,
            "reviewed_at": None,
            "reviewed_by": None,
            "notes": None,
        }

        current_records.append({
            "intake_id": intake_id,
            "fingerprint": fingerprint,
            "status": "READY_FOR_PLANNER_REVIEW",
            "active": True,
            "created_at": prior.get(
                "created_at"
            ) or now_iso(),
            "updated_at": now_iso(),
            "action": {
                "action_id": action_id,
                "title": action.get("title"),
                "kind": action.get("kind"),
                "rationale": action.get("rationale"),
                "suggested_target": action.get(
                    "suggested_target"
                ),
                "done_when": action.get("done_when"),
                "priority": action.get("priority"),
                "strategic_score": action.get(
                    "strategic_score"
                ),
                "depends_on_actions": as_list(
                    action.get("depends_on_actions")
                ),
                "supporting_actions": as_list(
                    action.get("supporting_actions")
                ),
            },
            "experiment_intent": experiment_shape,
            "provenance": provenance,
            "planner_state": planner_state,
            "policy": {
                "planner_may_edit_experiment_design": True,
                "planner_may_change_governance_decision": False,
                "planner_may_apply_action_patch": False,
                "execution_authorized": False,
                "human_planner_review_required": True,
            },
        })

    # Preserve historical records, but deactivate those no longer backed by an
    # active verified patch lifecycle.
    current_ids = {
        str(item.get("intake_id"))
        for item in current_records
    }
    archived_records: List[Dict[str, Any]] = []
    for intake_id, prior in existing_records.items():
        if intake_id in current_ids:
            continue
        archived = dict(prior)
        archived["active"] = False
        archived["status"] = (
            "INACTIVE_AFTER_ROLLBACK"
            if lifecycle_status == "ROLLED_BACK"
            else "SUPERSEDED_OR_NO_LONGER_ELIGIBLE"
        )
        archived["deactivated_at"] = now_iso()
        archived_records.append(archived)

    records = sorted(
        current_records + archived_records,
        key=lambda item: (
            not bool(item.get("active")),
            str(item.get("intake_id")),
        ),
    )

    summary = {
        "approved_decision_count": sum(
            1
            for item in decision_records
            if str(item.get("decision") or "").upper()
            == "APPROVED"
        ),
        "active_eligible_count": len(current_records),
        "blocked_count": len(blocked),
        "archived_count": len(archived_records),
        "record_count": len(records),
        "lifecycle_status": lifecycle_status,
        "application_receipt_status": application_status,
    }

    payload = {
        "schema": "archon_experiment_planner_intake_v1",
        "version": VERSION,
        "generated_at": now_iso(),
        "mode": "GOVERNANCE_VERIFIED_INTAKE_ONLY",
        "summary": summary,
        "records": records,
        "blocked_records": blocked,
        "source_state": {
            "director_report": sources["report_path"],
            "patch_lifecycle_status": lifecycle_status,
            "application_receipt_status": application_status,
            "last_application_id": patch_state.get(
                "last_application_id"
            ),
            "last_rollback_id": patch_state.get(
                "last_rollback_id"
            ),
            "source_commit_id": patch_state.get(
                "source_commit_id"
            ),
        },
        "policy": {
            "non_authoritative": True,
            "does_not_create_experiments": True,
            "does_not_execute_experiments": True,
            "does_not_change_governance_state": True,
            "does_not_change_scientific_metrics": True,
            "requires_active_verified_patch": True,
            "requires_human_planner_review": True,
        },
    }
    payload["content_hash"] = canonical_hash({
        "summary": summary,
        "records": records,
        "blocked_records": blocked,
        "source_state": payload["source_state"],
    })
    return payload


def render_markdown(payload: Dict[str, Any]) -> str:
    summary = as_dict(payload.get("summary"))
    lines = [
        f"# {TITLE}",
        "",
        f"- Generated: `{payload.get('generated_at')}`",
        f"- Mode: **{payload.get('mode')}**",
        f"- Lifecycle: **{summary.get('lifecycle_status')}**",
        (
            "- Application receipt: "
            f"**{summary.get('application_receipt_status')}**"
        ),
        f"- Approved decisions: **{summary.get('approved_decision_count', 0)}**",
        f"- Active eligible intents: **{summary.get('active_eligible_count', 0)}**",
        f"- Blocked: **{summary.get('blocked_count', 0)}**",
        f"- Archived: **{summary.get('archived_count', 0)}**",
        "",
        "## Planner intake",
        "",
    ]

    records = [
        item
        for item in as_list(payload.get("records"))
        if isinstance(item, dict) and item.get("active")
    ]
    if not records:
        lines.append(
            "No active governance-verified actions are currently eligible "
            "for Experiment Planner intake."
        )
    else:
        lines.extend([
            "| Intake | Action | Experiment type | Planner status |",
            "| --- | --- | --- | --- |",
        ])
        for item in records:
            action = as_dict(item.get("action"))
            intent = as_dict(item.get("experiment_intent"))
            planner = as_dict(item.get("planner_state"))
            lines.append(
                f"| `{item.get('intake_id')}` | "
                f"`{action.get('action_id')}` {action.get('title')} | "
                f"{intent.get('experiment_type')} | "
                f"{planner.get('status')} |"
            )

    blocked = as_list(payload.get("blocked_records"))
    if blocked:
        lines.extend([
            "",
            "## Blocked approved decisions",
            "",
        ])
        for item in blocked:
            reasons = item.get("reasons") or [
                item.get("reason")
            ]
            lines.append(
                f"- `{item.get('proposal_id')}` / "
                f"`{item.get('action_id') or '-'}`: "
                f"{', '.join(str(x) for x in reasons if x)}"
            )

    lines.extend([
        "",
        "## Safety boundary",
        "",
        "- This intake does not create or execute experiments.",
        "- Planner review is required before conversion into an experiment plan.",
        "- Planner cannot modify governance decisions or apply ResearchAction patches.",
        "- Rolled-back or unverified actions are not active planner inputs.",
        "",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument(
        "--analysis-root",
        required=True,
        help="Path to Results/Analysis",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output JSON. Default: "
            "<analysis-root>/Experiments/experiment_planner_intake.json"
        ),
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help=(
            "Output Markdown. Default: "
            "<analysis-root>/Experiments/experiment_planner_intake.md"
        ),
    )
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).resolve()
    output = (
        Path(args.output).resolve()
        if args.output
        else analysis_root
        / "Experiments"
        / "experiment_planner_intake.json"
    )
    markdown_output = (
        Path(args.markdown_output).resolve()
        if args.markdown_output
        else analysis_root
        / "Experiments"
        / "experiment_planner_intake.md"
    )

    existing = load_json(output, {})
    if not isinstance(existing, dict):
        existing = {}

    payload = build_intake(analysis_root, existing)
    atomic_write_json(output, payload)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(
        render_markdown(payload),
        encoding="utf-8",
    )

    summary = as_dict(payload.get("summary"))
    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(
        f"Lifecycle:    {summary.get('lifecycle_status')} | "
        f"receipt={summary.get('application_receipt_status')}"
    )
    print(
        f"Decisions:    {summary.get('approved_decision_count', 0)} approved"
    )
    print(
        f"Planner in:   {summary.get('active_eligible_count', 0)} active | "
        f"{summary.get('blocked_count', 0)} blocked | "
        f"{summary.get('archived_count', 0)} archived"
    )
    print("Intake mode:  GOVERNANCE_VERIFIED_INTAKE_ONLY")
    print(f"Output JSON:  {output}")
    print(f"Output MD:    {markdown_output}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
