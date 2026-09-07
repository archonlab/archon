"""Research Director report and console rendering."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from Analyzer_next.research.director.common import clamp, safe_num, write_json
from Analyzer_next.research.director.contracts import ResearchAction, ResearchDirectorState
from Analyzer_next.research.director.governance.review import EDITABLE_REVIEW_FIELDS, IMMUTABLE_REVIEW_FIELDS

def bar(x: float, width: int = 18) -> str:
    x = clamp(x)
    n = int(round(x * width))
    return "█" * n + "░" * (width - n)

def actions_to_json(actions: List[ResearchAction]) -> List[Dict[str, Any]]:
    return [asdict(a) for a in actions]

def write_report(root: Path, state: ResearchDirectorState) -> None:
    report = root / "research_director_report.md"
    data = root / "research_director_report.json"
    actions = root / "next_research_actions.json"
    history = root / "research_director_history.json"

    lines: List[str] = []
    lines.append("# Universe Search Research Director v37.6.3 — Stage 5.3 Commit Request Consumption Fix")
    lines.append("")
    lines.append(f"Generated: `{state.generated_at}`")
    lines.append("")
    lines.append("## Director Summary")
    lines.append("")
    lines.append(state.summary)
    lines.append("")
    lines.append("## Trend Memory")
    lines.append("")
    lines.append(f"- Trend: **{state.trend}**")
    lines.append(f"- Director note: {state.director_note}")
    lines.append(f"- Maturity delta: `{state.maturity_delta:+.3f}`")
    lines.append(f"- Risk delta: `{state.risk_delta:+.3f}`")
    lines.append(f"- Rules delta: `{state.rules_delta:+d}`")
    lines.append(f"- Consensus delta: `{state.consensus_delta:+d}`")
    lines.append(f"- Stagnation detected: **{state.stagnation}**")
    lines.append("")

    lines.append("## Scientific Scoreboard")
    lines.append("")
    lines.append(f"- Profiles analysed: **{state.profiles}**")
    lines.append(f"- Independent rules: **{state.rules}**")
    lines.append(f"- Principles tracked: **{state.principles}**")
    lines.append(f"- Evidence claims: **{state.evidence_claims}**")
    lines.append(f"- Supported principles: **{state.supported_principles}**")
    lines.append(f"- Consensus principles: **{state.consensus_principles}**")
    lines.append(f"- Foundational principles: **{state.foundational_principles}**")
    lines.append(f"- Disputed principles: **{state.disputed_principles}**")
    lines.append(f"- Predictions tracked: **{state.predictions}**")
    lines.append(f"- Confirmed predictions: **{state.confirmed_predictions}**")
    lines.append(f"- Testing predictions: **{state.testing_predictions}**")
    lines.append(f"- Planned experiments: **{state.planned_experiments}**")
    lines.append(f"- Mechanism coverage: **{state.mechanism_coverage * 100:.1f}%**")
    lines.append(f"- Discovery coverage: **{state.discovery_coverage * 100:.1f}%**")
    lines.append(f"- Knowledge integrity: **{'OK' if state.integrity_ok else 'FAILED'}**")
    lines.append("")
    lines.append("## Research State")
    lines.append("")
    lines.append(f"- Stage: **{state.stage}**")
    lines.append(f"- Maturity: `{state.maturity:.3f}` {bar(state.maturity)}")
    lines.append(f"- Evidence strength: `{state.evidence_strength:.3f}` {bar(state.evidence_strength)}")
    lines.append(f"- Consensus strength: `{state.consensus_strength:.3f}` {bar(state.consensus_strength)}")
    lines.append(f"- Rule diversity: `{state.diversity:.3f}` {bar(state.diversity)}")
    lines.append(f"- Knowledge velocity: `{state.velocity:.3f}` {bar(state.velocity)}")
    lines.append(f"- Knowledge efficiency: `{state.efficiency:.3f}` {bar(state.efficiency)}")
    lines.append(f"- Research risk: `{state.risk:.3f}` {bar(state.risk)}")
    lines.append("")

    lines.append("## Reference Control Coverage")
    lines.append("")
    rc = state.reference_controls if isinstance(state.reference_controls, dict) else {}
    rc_summary = rc.get("summary", {}) if isinstance(rc, dict) else {}
    rc_classes = rc.get("classes", {}) if isinstance(rc, dict) else {}
    if not rc_classes:
        lines.append("- Reference Control Registry has not been generated yet.")
    else:
        order = [
            "credible_emergence", "persistent_dynamics", "crisis_recovery",
            "fragmented", "crystal_static", "oscillator", "noise_like",
            "extinction",
        ]
        for cid in order:
            item = rc_classes.get(cid, {})
            status = str(item.get("status") or "unobserved")
            mark = "✓" if status == "qualified" else "⚠" if status == "observed" else "✗"
            lines.append(
                f"- {mark} {item.get('title', cid)}: "
                f"**{int(safe_num(item.get('candidate_count'), 0))}** candidate(s), "
                f"**{int(safe_num(item.get('qualified_count'), 0))}** qualified"
            )
        lines.append("")
        lines.append(
            f"- Observed coverage: **{int(safe_num(rc_summary.get('observed_classes'), 0))} / "
            f"{int(safe_num(rc_summary.get('class_count'), 8))}** classes"
        )
        lines.append(
            f"- Qualified coverage: **{int(safe_num(rc_summary.get('qualified_classes'), 0))} / "
            f"{int(safe_num(rc_summary.get('class_count'), 8))}** classes"
        )
    lines.append("")
    lines.append("## Strengths")
    lines.append("")
    if state.strengths:
        for item in state.strengths:
            lines.append(f"- {item}")
    else:
        lines.append("- No major strengths detected yet.")
    lines.append("")

    lines.append("## Bottlenecks")
    lines.append("")
    if state.bottlenecks:
        for item in state.bottlenecks:
            lines.append(f"- {item}")
    else:
        lines.append("- No major bottlenecks detected.")
    lines.append("")

    lines.append("## Risks")
    lines.append("")
    if state.risks:
        for item in state.risks:
            lines.append(f"- {item}")
    else:
        lines.append("- No critical research risks detected.")
    lines.append("")

    lines.append("## Consensus Action Intake")
    lines.append("")
    intake = (
        state.consensus_action_intake
        if isinstance(state.consensus_action_intake, dict)
        else {}
    )
    if not intake.get("available"):
        lines.append("- No prioritized Consensus action signals are available.")
    else:
        lines.append(
            f"- Principles received: **{int(safe_num(intake.get('principle_count'), 0))}**"
        )
        lines.append(
            f"- Signals: **{int(safe_num(intake.get('active_signal_count'), 0))} active** / "
            f"**{int(safe_num(intake.get('blocked_signal_count'), 0))} blocked** / "
            f"**{int(safe_num(intake.get('raw_signal_count'), 0))} raw**"
        )
        lines.append(
            "- Intake policy: **advisory only**; it does not create Director actions "
            "or modify strategic scores in Stage 4.1."
        )
        lines.append("")
        lines.append(
            "| Principle | Channel-aware status | Primary signal | Priority | Secondary | Blocked |"
        )
        lines.append(
            "| --- | --- | --- | --- | ---: | ---: |"
        )
        for item in intake.get("principles", []):
            primary = item.get("primary_signal")
            primary_type = (
                primary.get("signal_type")
                if isinstance(primary, dict)
                else "-"
            )
            lines.append(
                f"| {item.get('principle_id')} | "
                f"{item.get('channel_aware_status')} | "
                f"{primary_type or '-'} | "
                f"{item.get('highest_priority')} | "
                f"{len(item.get('secondary_signals', []))} | "
                f"{len(item.get('blocked_signals', []))} |"
            )
    lines.append("")

    lines.append("## Signal-to-Action Reconciliation")
    lines.append("")
    reconciliation = (
        state.consensus_action_reconciliation
        if isinstance(state.consensus_action_reconciliation, dict)
        else {}
    )
    if not reconciliation.get("available"):
        lines.append("- No Consensus signals were available for reconciliation.")
    else:
        counts = reconciliation.get("status_counts", {})
        lines.append(f"- Signals reconciled: **{int(safe_num(reconciliation.get('signal_count'), 0))}**")
        lines.append(f"- Covered: **{int(safe_num(counts.get('covered'), 0))}**")
        lines.append(f"- Partial: **{int(safe_num(counts.get('partial'), 0))}**")
        lines.append(f"- Uncovered: **{int(safe_num(counts.get('uncovered'), 0))}**")
        lines.append(f"- Blocked: **{int(safe_num(counts.get('blocked'), 0))}**")
        lines.append("- Reconciliation policy: **advisory only**; no actions are created and no Director scores are modified.")
        lines.append("")
        lines.append("| Principle | Role | Signal | Status | Scope | Best Director action | Match |")
        lines.append("| --- | --- | --- | --- | --- | --- | ---: |")
        for item in reconciliation.get("reconciliations", []):
            best = item.get("best_action")
            best_id = best.get("action_id") if isinstance(best, dict) else "-"
            best_score = safe_num(best.get("match_score"), 0.0) if isinstance(best, dict) else 0.0
            lines.append(
                f"| {item.get('principle_id')} | {item.get('signal_role')} | "
                f"{item.get('signal_type')} | **{item.get('status')}** | "
                f"{(best or {}).get('coverage_scope', '-') if isinstance(best, dict) else '-'} | "
                f"{best_id or '-'} | {best_score:.2f} |"
            )
    lines.append("")

    lines.append("## Director Coverage Gap Interpretation")
    lines.append("")
    coverage = (
        state.consensus_coverage_interpretation
        if isinstance(state.consensus_coverage_interpretation, dict)
        else {}
    )
    if not coverage.get("available"):
        lines.append("- No coverage interpretation is available.")
    else:
        counts = coverage.get("state_counts", {})
        lines.append(
            f"- Fully addressed: **{int(safe_num(counts.get('fully_addressed'), 0))}**"
        )
        lines.append(
            f"- Partially addressed: **{int(safe_num(counts.get('partially_addressed'), 0))}**"
        )
        lines.append(
            f"- Unaddressed: **{int(safe_num(counts.get('unaddressed'), 0))}**"
        )
        lines.append(
            f"- Blocked: **{int(safe_num(counts.get('blocked'), 0))}**"
        )
        lines.append(
            "- Interpretation policy: **read-only**; no actions or scores are modified."
        )
        lines.append("")
        lines.append(
            "| Principle | Coverage state | Ratio | Primary signal | Covered | Partial | Uncovered | Blocked |"
        )
        lines.append(
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |"
        )
        for item in coverage.get("principles", []):
            lines.append(
                f"| {item.get('principle_id')} | "
                f"**{item.get('coverage_state')}** | "
                f"{safe_num(item.get('coverage_ratio'), 0.0):.2f} | "
                f"{item.get('primary_signal_status')} | "
                f"{int(safe_num(item.get('covered_signal_count'), 0))} | "
                f"{int(safe_num(item.get('partial_signal_count'), 0))} | "
                f"{int(safe_num(item.get('uncovered_signal_count'), 0))} | "
                f"{int(safe_num(item.get('blocked_signal_count'), 0))} |"
            )
    lines.append("")

    lines.append("## Coverage-Aware Director Recommendations")
    lines.append("")
    recommendations = (
        state.coverage_aware_recommendations
        if isinstance(state.coverage_aware_recommendations, dict)
        else {}
    )
    if not recommendations.get("available"):
        lines.append("- No coverage-aware recommendations are required.")
    else:
        lines.append(
            f"- Recommendations: **{int(safe_num(recommendations.get('recommendation_count'), 0))}**"
        )
        lines.append(
            f"- Principles affected: **{len(recommendations.get('principles_with_recommendations', []))}**"
        )
        lines.append(
            "- Recommendation policy: **advisory only**; existing actions are "
            "not changed and new actions are not created."
        )
        lines.append("")
        lines.append(
            "| Priority | Principle | Signal | Recommendation | Target action | Scope |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | --- |"
        )
        for item in recommendations.get("recommendations", []):
            lines.append(
                f"| **{item.get('priority')}** | "
                f"{item.get('principle_id')} | "
                f"{item.get('signal_type')} | "
                f"{item.get('recommendation_type')} | "
                f"{item.get('target_action_id') or '-'} | "
                f"{item.get('match_scope')} |"
            )
            lines.append(
                f"|  |  |  | {item.get('recommended_refinement')} |  |  |"
            )
    lines.append("")

    lines.append("## Consolidated Recommendation Plan")
    lines.append("")
    consolidated = (
        state.consolidated_recommendations
        if isinstance(state.consolidated_recommendations, dict)
        else {}
    )
    if not consolidated.get("available"):
        lines.append("- No recommendations are available for consolidation.")
    else:
        lines.append(
            f"- Raw recommendations: **{int(safe_num(consolidated.get('raw_recommendation_count'), 0))}**"
        )
        lines.append(
            f"- Action groups: **{int(safe_num(consolidated.get('action_group_count'), 0))}**"
        )
        lines.append(
            f"- Principle groups: **{int(safe_num(consolidated.get('principle_group_count'), 0))}**"
        )
        primary = consolidated.get("primary_recommendation")
        if isinstance(primary, dict):
            lines.append(
                f"- Primary recommendation: **{primary.get('recommendation_id')}** "
                f"({primary.get('priority')})"
            )
        lines.append(
            "- Consolidation policy: **advisory only**; grouping does not alter actions."
        )
        lines.append("")
        lines.append(
            "| Target action | Priority | Recommendations | Principles | Signals |"
        )
        lines.append(
            "| --- | --- | ---: | --- | --- |"
        )
        for item in consolidated.get("recommendations_by_action", []):
            lines.append(
                f"| {item.get('target_action_id') or 'UNASSIGNED'} | "
                f"**{item.get('highest_priority')}** | "
                f"{int(safe_num(item.get('recommendation_count'), 0))} | "
                f"{', '.join(item.get('principles', [])) or '-'} | "
                f"{', '.join(item.get('signals', [])) or '-'} |"
            )
            for refinement in item.get("combined_refinements", []):
                lines.append(f"|  |  |  |  | {refinement} |")
    lines.append("")

    lines.append("## Recommendation-to-Action Patch Proposals")
    lines.append("")
    patch_bundle = (
        state.recommendation_patch_proposals
        if isinstance(state.recommendation_patch_proposals, dict)
        else {}
    )
    if not patch_bundle.get("available"):
        lines.append("- No patch proposals are available.")
    else:
        lines.append(
            f"- Patch proposals: **{int(safe_num(patch_bundle.get('proposal_count'), 0))}**"
        )
        lines.append(
            "- Patch policy: **proposal only**; no action is modified automatically."
        )
        lines.append("")
        lines.append(
            "| Proposal | Target action | Priority | Principles | Signals | Operations |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | ---: |"
        )
        for item in patch_bundle.get("proposals", []):
            lines.append(
                f"| {item.get('proposal_id')} | "
                f"{item.get('target_action_id')} | "
                f"**{item.get('highest_priority')}** | "
                f"{', '.join(item.get('affected_principles', [])) or '-'} | "
                f"{', '.join(item.get('affected_signals', [])) or '-'} | "
                f"{len(item.get('patch_operations', []))} |"
            )
            for operation in item.get("patch_operations", []):
                field_name = operation.get("field")
                if operation.get("op") == "replace":
                    detail = operation.get("proposed_value")
                else:
                    detail = "; ".join(operation.get("proposed_additions", []))
                lines.append(
                    f"|  |  |  |  | `{field_name}` | {detail} |"
                )
    lines.append("")

    lines.append("## Patch Proposal Validation and Conflict Detection")
    lines.append("")
    validation = (
        state.patch_proposal_validation
        if isinstance(state.patch_proposal_validation, dict)
        else {}
    )
    if not validation.get("available"):
        lines.append("- No patch proposals were available for validation.")
    else:
        counts = validation.get("status_counts", {})
        lines.append(
            f"- Valid: **{int(safe_num(counts.get('VALID'), 0))}**"
        )
        lines.append(
            f"- Redundant: **{int(safe_num(counts.get('REDUNDANT'), 0))}**"
        )
        lines.append(
            f"- Conflicting: **{int(safe_num(counts.get('CONFLICTING'), 0))}**"
        )
        lines.append(
            f"- Blocked: **{int(safe_num(counts.get('BLOCKED'), 0))}**"
        )
        lines.append(
            f"- Invalid target: **{int(safe_num(counts.get('INVALID_TARGET'), 0))}**"
        )
        lines.append(
            f"- Cross-proposal conflicts: **{int(safe_num(validation.get('cross_proposal_conflict_count'), 0))}**"
        )
        lines.append(
            "- Validation policy: **review required**; no patch is applied automatically."
        )
        lines.append("")
        lines.append(
            "| Proposal | Target action | Status | Issues | Application allowed |"
        )
        lines.append(
            "| --- | --- | --- | ---: | --- |"
        )
        for item in validation.get("validations", []):
            lines.append(
                f"| {item.get('proposal_id')} | "
                f"{item.get('target_action_id') or '-'} | "
                f"**{item.get('status')}** | "
                f"{int(safe_num(item.get('issue_count'), 0))} | "
                f"{item.get('application_allowed')} |"
            )
            for issue in item.get("issues", []):
                lines.append(
                    f"|  |  | {issue.get('severity')} |  | {issue.get('message')} |"
                )
    lines.append("")

    lines.append("## Patch Conflict Explanation and Resolution Plan")
    lines.append("")
    resolution_plan = (
        state.patch_conflict_resolution_plan
        if isinstance(state.patch_conflict_resolution_plan, dict)
        else {}
    )
    if not resolution_plan.get("available"):
        lines.append("- No conflicting or blocked proposals require resolution.")
    else:
        lines.append(
            f"- Problem proposals: **{int(safe_num(resolution_plan.get('problem_proposal_count'), 0))}**"
        )
        lines.append(
            f"- Merge possible: **{int(safe_num(resolution_plan.get('merge_possible_count'), 0))}**"
        )
        lines.append(
            f"- Manual decisions required: **{int(safe_num(resolution_plan.get('manual_decision_count'), 0))}**"
        )
        lines.append(
            "- Resolution policy: **explanation only**; no conflict is resolved automatically."
        )
        lines.append("")
        lines.append(
            "| Proposal | Status | Resolution | Merge | Manual decision | Fields |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | --- |"
        )
        for item in resolution_plan.get("plans", []):
            lines.append(
                f"| {item.get('proposal_id')} | "
                f"**{item.get('current_status')}** | "
                f"{item.get('resolution_type')} | "
                f"{item.get('merge_possible')} | "
                f"{item.get('manual_decision_required')} | "
                f"{', '.join(item.get('conflicting_fields', [])) or '-'} |"
            )
            lines.append(
                f"|  |  | {item.get('preferred_resolution')} |  |  |  |"
            )
            if item.get("blocked_dependencies"):
                lines.append(
                    f"|  |  | Blocked by: {', '.join(item.get('blocked_dependencies', []))} |  |  |  |"
                )
    lines.append("")

    lines.append("## Human Review Queue and Decision Records")
    lines.append("")
    review_queue = (
        state.human_review_queue
        if isinstance(state.human_review_queue, dict)
        else {}
    )
    if not review_queue.get("available"):
        lines.append("- No patch proposals are waiting for human review.")
    else:
        counts = review_queue.get("decision_counts", {})
        lines.append(
            f"- Queue entries: **{int(safe_num(review_queue.get('queue_count'), 0))}**"
        )
        lines.append(
            f"- Pending: **{int(safe_num(counts.get('PENDING_REVIEW'), 0))}**"
        )
        lines.append(
            f"- Approved: **{int(safe_num(counts.get('APPROVED'), 0))}**"
        )
        lines.append(
            f"- Rejected: **{int(safe_num(counts.get('REJECTED'), 0))}**"
        )
        lines.append(
            f"- Deferred: **{int(safe_num(counts.get('DEFERRED'), 0))}**"
        )
        lines.append(
            f"- Needs revision: **{int(safe_num(counts.get('NEEDS_REVISION'), 0))}**"
        )
        lines.append(
            "- Review policy: **approval records a decision only**; it does not apply a patch."
        )
        lines.append("")
        lines.append(
            "| Review | Proposal | Priority | Validation | Decision | Target action |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | --- |"
        )
        for item in review_queue.get("queue", []):
            lines.append(
                f"| {item.get('review_id')} | "
                f"{item.get('proposal_id')} | "
                f"**{item.get('review_priority')}** | "
                f"{item.get('validation_status')} | "
                f"**{item.get('decision')}** | "
                f"{item.get('target_action_id') or '-'} |"
            )
            if item.get("decision_reason"):
                lines.append(
                    f"|  |  |  |  | Reason: {item.get('decision_reason')} |  |"
                )
            if item.get("preferred_resolution"):
                lines.append(
                    f"|  |  |  |  | Resolution: {item.get('preferred_resolution')} |  |"
                )
    lines.append("")

    lines.append("## Review Record Validation and Audit Trail")
    lines.append("")
    review_validation = (
        state.human_review_validation
        if isinstance(state.human_review_validation, dict)
        else {}
    )
    review_audit = (
        state.human_review_audit_trail
        if isinstance(state.human_review_audit_trail, dict)
        else {}
    )
    validation_counts = review_validation.get("status_counts", {})
    lines.append(
        f"- Review records: **{int(safe_num(review_validation.get('record_count'), 0))}**"
    )
    lines.append(
        f"- Valid: **{int(safe_num(validation_counts.get('VALID'), 0))}**"
    )
    lines.append(
        f"- Invalid: **{int(safe_num(review_validation.get('invalid_record_count'), 0))}**"
    )
    lines.append(
        f"- Audit events: **{int(safe_num(review_audit.get('event_count'), 0))}**"
    )
    lines.append(
        f"- New audit events: **{int(safe_num(review_audit.get('appended_event_count'), 0))}**"
    )
    lines.append(
        "- Audit policy: **append only**; review history is preserved and patches remain unapplied."
    )
    lines.append("")
    if review_validation.get("validations"):
        lines.append(
            "| Review | Proposal | Decision | Previous | Status | Issues |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | ---: |"
        )
        for item in review_validation.get("validations", []):
            lines.append(
                f"| {item.get('review_id') or '-'} | "
                f"{item.get('proposal_id') or '-'} | "
                f"{item.get('decision') or '-'} | "
                f"{item.get('previous_decision') or '-'} | "
                f"**{item.get('status')}** | "
                f"{int(safe_num(item.get('issue_count'), 0))} |"
            )
    lines.append("")

    lines.append("## Review Decision Templates and Safe Editing Interface")
    lines.append("")
    template = (
        state.human_review_decision_template
        if isinstance(state.human_review_decision_template, dict)
        else {}
    )
    editing = (
        state.human_review_editing_interface
        if isinstance(state.human_review_editing_interface, dict)
        else {}
    )
    lines.append(
        f"- Template records: **{int(safe_num(template.get('record_count'), 0))}**"
    )
    lines.append(
        f"- Editing rows: **{int(safe_num(editing.get('row_count'), 0))}**"
    )
    lines.append(
        "- Template policy: **non-authoritative**; copying a record into "
        "`human_review_decisions.json` is required before validation."
    )
    lines.append(
        "- Safe editing policy: immutable identifiers stay read-only and "
        "patches remain unapplied."
    )
    lines.append("")
    if editing.get("rows"):
        lines.append(
            "| Review | Proposal | Priority | Validation | Current decision | Existing record |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | --- |"
        )
        for item in editing.get("rows", []):
            lines.append(
                f"| {item.get('review_id')} | "
                f"{item.get('proposal_id')} | "
                f"{item.get('review_priority')} | "
                f"{item.get('validation_status')} | "
                f"**{item.get('current_decision')}** | "
                f"{item.get('record_exists')} |"
            )
    lines.append("")

    lines.append("## Review Decision Import Preview and Diff")
    lines.append("")
    import_preview = (
        state.human_review_import_preview
        if isinstance(state.human_review_import_preview, dict)
        else {}
    )
    preview_counts = import_preview.get("category_counts", {})
    lines.append(
        f"- Candidate exists: **{bool(import_preview.get('candidate_exists'))}**"
    )
    lines.append(
        f"- Candidate rows: **{int(safe_num(import_preview.get('candidate_row_count'), 0))}**"
    )
    lines.append(
        f"- New records: **{int(safe_num(preview_counts.get('NEW_RECORD'), 0))}**"
    )
    lines.append(
        f"- Changed decisions: **{int(safe_num(preview_counts.get('CHANGED_DECISION'), 0))}**"
    )
    lines.append(
        f"- Unchanged: **{int(safe_num(preview_counts.get('UNCHANGED'), 0))}**"
    )
    lines.append(
        f"- Invalid edits: **{int(safe_num(preview_counts.get('INVALID_EDIT'), 0))}**"
    )
    lines.append(
        f"- Immutable-field changes: **{int(safe_num(preview_counts.get('IMMUTABLE_FIELD_CHANGE'), 0))}**"
    )
    lines.append(
        "- Import policy: **preview only**; no decision record is written automatically."
    )
    lines.append("")
    if import_preview.get("rows"):
        lines.append(
            "| Review | Proposal | Category | Current | Proposed | Diffs | Issues |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | ---: | ---: |"
        )
        for item in import_preview.get("rows", []):
            lines.append(
                f"| {item.get('review_id') or '-'} | "
                f"{item.get('proposal_id') or '-'} | "
                f"**{item.get('category')}** | "
                f"{item.get('current_decision') or '-'} | "
                f"{item.get('proposed_decision') or '-'} | "
                f"{int(safe_num(item.get('diff_count'), 0))} | "
                f"{int(safe_num(item.get('issue_count'), 0))} |"
            )
    lines.append("")

    lines.append("## Import Candidate Validation and Commit Manifest")
    lines.append("")
    commit_manifest = (
        state.human_review_commit_manifest
        if isinstance(state.human_review_commit_manifest, dict)
        else {}
    )
    lines.append(
        f"- Manifest available: **{bool(commit_manifest.get('available'))}**"
    )
    lines.append(
        f"- Commit ID: **{commit_manifest.get('commit_id') or '-'}**"
    )
    lines.append(
        f"- Importable rows: **{int(safe_num(commit_manifest.get('importable_row_count'), 0))}**"
    )
    lines.append(
        f"- Skipped rows: **{int(safe_num(commit_manifest.get('skipped_row_count'), 0))}**"
    )
    lines.append(
        f"- Candidate hash: `{commit_manifest.get('candidate_hash') or '-'}`"
    )
    lines.append(
        f"- Expected decision-store hash: `{commit_manifest.get('expected_decision_store_hash') or '-'}`"
    )
    lines.append(
        "- Commit policy: **manifest only**; decision records are not written."
    )
    lines.append("")
    if commit_manifest.get("rows"):
        lines.append(
            "| Review | Proposal | Operation | Decision | Source category |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- |"
        )
        for item in commit_manifest.get("rows", []):
            lines.append(
                f"| {item.get('review_id') or '-'} | "
                f"{item.get('proposal_id') or '-'} | "
                f"**{item.get('expected_operation')}** | "
                f"{item.get('decision')} | "
                f"{item.get('source_category')} |"
            )
    lines.append("")

    lines.append("## Atomic Decision Commit Gateway")
    lines.append("")
    commit_request = (
        state.human_review_commit_request
        if isinstance(state.human_review_commit_request, dict)
        else {}
    )
    commit_result = (
        state.human_review_commit_result
        if isinstance(state.human_review_commit_result, dict)
        else {}
    )
    lines.append(
        f"- Commit requested: **{bool(commit_request.get('commit'))}**"
    )
    lines.append(
        f"- Commit status: **{commit_result.get('status') or '-'}**"
    )
    lines.append(
        f"- Commit ID: **{commit_result.get('commit_id') or '-'}**"
    )
    lines.append(
        f"- Failed checks: **{int(safe_num(commit_result.get('failed_check_count'), 0))}**"
    )
    lines.append(
        f"- Inserted records: **{int(safe_num(commit_result.get('inserted_count'), 0))}**"
    )
    lines.append(
        f"- Updated records: **{int(safe_num(commit_result.get('updated_count'), 0))}**"
    )
    lines.append(
        "- Gateway policy: **decision store only**; Research Actions and patches remain unchanged."
    )
    lines.append("")
    if commit_result.get("checks"):
        lines.append(
            "| Check | Passed | Expected | Actual |"
        )
        lines.append(
            "| --- | --- | --- | --- |"
        )
        for item in commit_result.get("checks", []):
            lines.append(
                f"| {item.get('name')} | "
                f"**{item.get('passed')}** | "
                f"{item.get('expected')} | "
                f"{item.get('actual')} |"
            )
    lines.append("")

    lines.append("## Commit Receipt Verification and Recovery Check")
    lines.append("")
    receipt_verification = (
        state.human_review_receipt_verification
        if isinstance(state.human_review_receipt_verification, dict)
        else {}
    )
    recovery_check = (
        state.human_review_recovery_check
        if isinstance(state.human_review_recovery_check, dict)
        else {}
    )
    lines.append(
        f"- Receipt status: **{receipt_verification.get('status') or '-'}**"
    )
    lines.append(
        f"- Commit ID: **{receipt_verification.get('commit_id') or '-'}**"
    )
    lines.append(
        f"- Failed checks: **{int(safe_num(receipt_verification.get('failed_check_count'), 0))}**"
    )
    lines.append(
        f"- Warnings: **{int(safe_num(receipt_verification.get('warning_count'), 0))}**"
    )
    lines.append(
        f"- Audit matches: **{int(safe_num(receipt_verification.get('audit_match_count'), 0))}**"
    )
    lines.append(
        f"- Recovery status: **{recovery_check.get('status') or '-'}**"
    )
    lines.append(
        f"- Recovery ready: **{bool(recovery_check.get('recovery_ready'))}**"
    )
    lines.append(
        "- Recovery policy: **check only**; rollback is never automatic."
    )
    lines.append("")
    if receipt_verification.get("checks"):
        lines.append(
            "| Verification check | Passed | Severity | Expected | Actual |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- |"
        )
        for item in receipt_verification.get("checks", []):
            lines.append(
                f"| {item.get('name')} | "
                f"**{item.get('passed')}** | "
                f"{item.get('severity')} | "
                f"{item.get('expected')} | "
                f"{item.get('actual')} |"
            )
    lines.append("")

    lines.append("## Approved Decision to Patch Application Preview")
    lines.append("")
    application_preview = (
        state.approved_patch_application_preview
        if isinstance(state.approved_patch_application_preview, dict)
        else {}
    )
    counts = application_preview.get("status_counts", {})
    lines.append(
        f"- Proposals inspected: **{int(safe_num(application_preview.get('proposal_count'), 0))}**"
    )
    lines.append(
        f"- Eligible: **{int(safe_num(counts.get('ELIGIBLE'), 0))}**"
    )
    lines.append(
        f"- Not approved: **{int(safe_num(counts.get('NOT_APPROVED'), 0))}**"
    )
    lines.append(
        f"- Invalid proposal: **{int(safe_num(counts.get('INVALID_PROPOSAL'), 0))}**"
    )
    lines.append(
        f"- Receipt unverified: **{int(safe_num(counts.get('RECEIPT_UNVERIFIED'), 0))}**"
    )
    lines.append(
        f"- Already applied: **{int(safe_num(counts.get('ALREADY_APPLIED'), 0))}**"
    )
    lines.append(
        f"- Conflicting: **{int(safe_num(counts.get('CONFLICTING'), 0))}**"
    )
    lines.append(
        "- Application policy: **preview only**; no Research Action field is changed."
    )
    lines.append("")
    if application_preview.get("rows"):
        lines.append(
            "| Preview | Proposal | Decision | Validation | Receipt | Status | Diffs |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- | --- | ---: |"
        )
        for item in application_preview.get("rows", []):
            lines.append(
                f"| {item.get('application_preview_id')} | "
                f"{item.get('proposal_id')} | "
                f"{item.get('decision')} | "
                f"{item.get('validation_status')} | "
                f"{item.get('receipt_status')} | "
                f"**{item.get('status')}** | "
                f"{int(safe_num(item.get('diff_count'), 0))} |"
            )
    lines.append("")

    lines.append("## Patch Application Manifest and Final Safety Checks")
    lines.append("")
    application_manifest = (
        state.patch_application_manifest
        if isinstance(state.patch_application_manifest, dict)
        else {}
    )
    lines.append(
        f"- Manifest available: **{bool(application_manifest.get('available'))}**"
    )
    lines.append(
        f"- Manifest ID: **{application_manifest.get('application_manifest_id') or '-'}**"
    )
    lines.append(
        f"- Source commit: **{application_manifest.get('source_commit_id') or '-'}**"
    )
    lines.append(
        f"- Eligible rows: **{int(safe_num(application_manifest.get('eligible_row_count'), 0))}**"
    )
    lines.append(
        f"- Skipped rows: **{int(safe_num(application_manifest.get('skipped_row_count'), 0))}**"
    )
    lines.append(
        f"- Global safe: **{bool(application_manifest.get('global_safe'))}**"
    )
    lines.append(
        f"- Final ready: **{bool(application_manifest.get('final_ready'))}**"
    )
    lines.append(
        "- Application policy: **manifest only**; Research Actions are not modified."
    )
    lines.append("")
    if application_manifest.get("rows"):
        lines.append(
            "| Application | Proposal | Target action | Operations | Expected hash | Result hash |"
        )
        lines.append(
            "| --- | --- | --- | ---: | --- | --- |"
        )
        for item in application_manifest.get("rows", []):
            lines.append(
                f"| {item.get('application_id')} | "
                f"{item.get('proposal_id')} | "
                f"{item.get('target_action_id')} | "
                f"{len(item.get('operations', []))} | "
                f"`{item.get('expected_action_hash')}` | "
                f"`{item.get('resulting_action_hash')}` |"
            )
    lines.append("")

    lines.append("## Atomic ResearchAction Patch Application Gateway")
    lines.append("")
    patch_result = (
        state.patch_application_result
        if isinstance(state.patch_application_result, dict)
        else {}
    )
    patch_state = (
        state.research_action_patch_state
        if isinstance(state.research_action_patch_state, dict)
        else {}
    )
    lines.append(
        f"- Application status: **{patch_result.get('status') or '-'}**"
    )
    lines.append(
        f"- Application ID: **{patch_result.get('application_id') or '-'}**"
    )
    lines.append(
        f"- Applied actions: **{int(safe_num(patch_result.get('applied_action_count'), 0))}**"
    )
    lines.append(
        f"- Failed checks: **{int(safe_num(patch_result.get('failed_check_count'), 0))}**"
    )
    lines.append(
        f"- Persistent overrides: **{int(safe_num(patch_state.get('override_count'), 0))}**"
    )
    lines.append(
        "- Gateway policy: **explicit atomic application only**; scientific metrics remain unchanged."
    )
    lines.append("")
    if patch_result.get("checks"):
        lines.append(
            "| Application check | Passed | Expected | Actual |"
        )
        lines.append(
            "| --- | --- | --- | --- |"
        )
        for item in patch_result.get("checks", []):
            lines.append(
                f"| {item.get('name')} | "
                f"**{item.get('passed')}** | "
                f"{item.get('expected')} | "
                f"{item.get('actual')} |"
            )
    lines.append("")

    lines.append("## Patch Application Receipt Verification and Rollback Readiness")
    lines.append("")
    patch_receipt = (
        state.patch_application_receipt_verification
        if isinstance(state.patch_application_receipt_verification, dict)
        else {}
    )
    rollback = (
        state.patch_rollback_readiness
        if isinstance(state.patch_rollback_readiness, dict)
        else {}
    )
    lines.append(
        f"- Receipt status: **{patch_receipt.get('status') or '-'}**"
    )
    lines.append(
        f"- Application ID: **{patch_receipt.get('application_id') or '-'}**"
    )
    lines.append(
        f"- Verified actions: **{int(safe_num(patch_receipt.get('verified_action_count'), 0))}**"
    )
    lines.append(
        f"- Mismatched actions: **{int(safe_num(patch_receipt.get('mismatched_action_count'), 0))}**"
    )
    lines.append(
        f"- Failed checks: **{int(safe_num(patch_receipt.get('failed_check_count'), 0))}**"
    )
    lines.append(
        f"- Warnings: **{int(safe_num(patch_receipt.get('warning_count'), 0))}**"
    )
    lines.append(
        f"- Rollback status: **{rollback.get('status') or '-'}**"
    )
    lines.append(
        f"- Rollback actions: **{int(safe_num(rollback.get('rollback_action_count'), 0))}**"
    )
    lines.append(
        "- Rollback policy: **readiness only**; no automatic rollback is permitted."
    )
    lines.append("")
    if patch_receipt.get("checks"):
        lines.append(
            "| Verification check | Passed | Severity | Expected | Actual |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- |"
        )
        for item in patch_receipt.get("checks", []):
            lines.append(
                f"| {item.get('name')} | "
                f"**{item.get('passed')}** | "
                f"{item.get('severity')} | "
                f"{item.get('expected')} | "
                f"{item.get('actual')} |"
            )
    lines.append("")

    lines.append("## Explicit Atomic Patch Rollback Gateway")
    lines.append("")
    rollback_result = (
        state.patch_rollback_result
        if isinstance(state.patch_rollback_result, dict)
        else {}
    )
    patch_state = (
        state.research_action_patch_state
        if isinstance(state.research_action_patch_state, dict)
        else {}
    )
    lines.append(
        f"- Rollback status: **{rollback_result.get('status') or '-'}**"
    )
    lines.append(
        f"- Rollback ID: **{rollback_result.get('rollback_id') or '-'}**"
    )
    lines.append(
        f"- Restored actions: **{int(safe_num(rollback_result.get('rolled_back_action_count'), 0))}**"
    )
    lines.append(
        f"- Failed checks: **{int(safe_num(rollback_result.get('failed_check_count'), 0))}**"
    )
    lines.append(
        f"- Persistent overrides after rollback: **{int(safe_num(patch_state.get('override_count'), 0))}**"
    )
    lines.append(
        "- Rollback policy: **explicit atomic rollback only**; decision history and scientific metrics remain unchanged."
    )
    lines.append("")
    if rollback_result.get("checks"):
        lines.append(
            "| Rollback check | Passed | Expected | Actual |"
        )
        lines.append(
            "| --- | --- | --- | --- |"
        )
        for item in rollback_result.get("checks", []):
            lines.append(
                f"| {item.get('name')} | "
                f"**{item.get('passed')}** | "
                f"{item.get('expected')} | "
                f"{item.get('actual')} |"
            )
    lines.append("")

    lines.append("## Rollback Receipt Verification and Lifecycle Closure")
    lines.append("")
    rollback_receipt = (
        state.patch_rollback_receipt_verification
        if isinstance(state.patch_rollback_receipt_verification, dict)
        else {}
    )
    lifecycle = (
        state.patch_lifecycle_closure
        if isinstance(state.patch_lifecycle_closure, dict)
        else {}
    )
    lines.append(
        f"- Rollback receipt status: **{rollback_receipt.get('status') or '-'}**"
    )
    lines.append(
        f"- Rollback ID: **{rollback_receipt.get('rollback_id') or '-'}**"
    )
    lines.append(
        f"- Verified restored actions: **{int(safe_num(rollback_receipt.get('verified_action_count'), 0))}**"
    )
    lines.append(
        f"- Mismatched restored actions: **{int(safe_num(rollback_receipt.get('mismatched_action_count'), 0))}**"
    )
    lines.append(
        f"- Failed checks: **{int(safe_num(rollback_receipt.get('failed_check_count'), 0))}**"
    )
    lines.append(
        f"- Warnings: **{int(safe_num(rollback_receipt.get('warning_count'), 0))}**"
    )
    lines.append(
        f"- Lifecycle status: **{lifecycle.get('status') or '-'}**"
    )
    lines.append(
        f"- Lifecycle closed: **{bool(lifecycle.get('closed'))}**"
    )
    lines.append(
        f"- Persistent overrides: **{int(safe_num(lifecycle.get('persistent_override_count'), 0))}**"
    )
    lines.append(
        "- Lifecycle policy: **classification only**; no repair, reapply, or rollback is automatic."
    )
    lines.append("")
    if rollback_receipt.get("checks"):
        lines.append(
            "| Rollback receipt check | Passed | Severity | Expected | Actual |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- |"
        )
        for item in rollback_receipt.get("checks", []):
            lines.append(
                f"| {item.get('name')} | "
                f"**{item.get('passed')}** | "
                f"{item.get('severity')} | "
                f"{item.get('expected')} | "
                f"{item.get('actual')} |"
            )
    if lifecycle.get("reasons"):
        lines.append("")
        for reason in lifecycle.get("reasons", []):
            lines.append(f"- Lifecycle reason: {reason}")
    lines.append("")

    lines.append("## Director Priorities")
    lines.append("")
    for item in state.priorities:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Research Dependency Graph")
    lines.append("")
    graph = state.dependency_graph or {}
    lines.append(f"- Version: **{graph.get('version', 'Dependency Graph v1.0')}**")
    lines.append(f"- Nodes: **{graph.get('node_count', 0)}**")
    lines.append(f"- Required edges: **{graph.get('required_edge_count', 0)}**")
    lines.append(f"- Supporting edges: **{graph.get('supporting_edge_count', 0)}**")
    lines.append(f"- Root actions: **{', '.join(graph.get('roots', [])) or '-'}**")
    unlock_model = graph.get("unlock_model", {})
    lines.append(
        f"- Unlock model: **{unlock_model.get('version', 'Graph Unlock Model v1.0')}**"
    )
    lines.append(
        f"- Maximum raw unlock: **{safe_num(graph.get('maximum_raw_unlock')):.3f}**"
    )
    decision_model = graph.get("decision_model", {})
    lines.append(
        f"- Final decision model: **{decision_model.get('version', 'Decision Model v1.1')}**"
    )
    lines.append(
        "- Final scoring order: **graph → unlock → strategic score → sort**"
    )
    lines.append("")
    for edge in graph.get("required_edges", []):
        lines.append(
            f"- **REQUIRED:** `{edge.get('from')}` → `{edge.get('to')}`"
        )
    for edge in graph.get("supporting_edges", []):
        lines.append(
            f"- **SUPPORTING:** `{edge.get('from')}` → `{edge.get('to')}`"
        )
    lines.append("")

    lines.append("## Next Research Actions")
    lines.append("")
    for a in state.actions:
        lines.append(f"### Priority {a.priority}: {a.title}")
        lines.append("")
        lines.append(f"- Action ID: `{a.action_id}`")
        lines.append(f"- Effective priority: **{a.priority}**")
        lines.append(f"- Base Planner priority: **{a.base_priority}**")
        lines.append(f"- Kind: `{a.kind}`")
        lines.append(f"- Urgency: **{a.urgency}**")
        lines.append(f"- Expected gain: **{a.expected_gain}**")
        if a.bottleneck_component:
            lines.append(f"- Bottleneck: **{a.bottleneck_component}** (rank {a.bottleneck_rank})")
            lines.append(f"- Bottleneck severity: `{a.bottleneck_severity:.3f}`")
            lines.append(f"- Bottleneck directness: **{a.bottleneck_directness}**")
            lines.append(f"- Potential Scientific Health gain: `+{a.projected_health_gain:.3f}`")
        lines.append(f"- Strategic score: `{a.strategic_score:.3f}`")
        lines.append(f"- Decision model: **{a.decision_model_version}**")
        lines.append(f"- Estimated runtime: **{a.estimated_runtime}**")
        lines.append(f"- Estimated cost: **{a.estimated_cost}**")
        lines.append(f"- Automation: **{a.automation_level}**")
        lines.append(f"- Dependency level: **{a.dependency_level}**")
        lines.append(f"- Information gain score: `{a.expected_information_gain_score:.3f}`")
        lines.append(f"- Unlock score: `{a.unlock_score:.3f}`")
        lines.append(f"- Graph unlock raw: `{a.graph_unlock_raw:.3f}`")
        lines.append(f"- Dependency depth: **{a.dependency_depth}**")
        lines.append(f"- Depends on actions: **{', '.join(a.depends_on_actions) or '-'}**")
        lines.append(f"- Supporting actions: **{', '.join(a.supporting_actions) or '-'}**")
        lines.append(f"- Unlocks actions: **{', '.join(a.unlocks_actions) or '-'}**")
        lines.append(f"- Linked predictions: **{', '.join(a.linked_predictions) or '-'}**")
        if a.prerequisites:
            lines.append(f"- Prerequisites: {', '.join(a.prerequisites)}")
        lines.append(f"- Rationale: {a.rationale}")
        if a.suggested_target:
            lines.append(f"- Suggested target: {a.suggested_target}")
        if a.done_when:
            lines.append(f"- Done when: `{a.done_when}`")
        lines.append("")

    lines.append("## Machine-readable bridge")
    lines.append("")
    lines.append("`next_research_actions.json` is intended as the future bridge back into Universe Search.")
    lines.append("")

    report.write_text("\n".join(lines), encoding="utf-8")
    write_json(root / "research_dependency_graph.json", state.dependency_graph)
    decisions_path = root / "human_review_decisions.json"
    if not decisions_path.exists():
        write_json(decisions_path, {
            "schema": "archon_human_review_decisions_v1",
            "records": [],
            "scientific_policy": {
                "approval_does_not_apply_patch": True,
                "automatic_application": False,
            },
        })
    write_json(
        root / "human_review_audit_trail.json",
        {
            "schema": "archon_human_review_audit_trail_v1",
            "events": state.human_review_audit_trail.get("events", []),
            "scientific_policy": {
                "append_only": True,
                "automatic_decision_changes": False,
                "automatic_patch_application": False,
            },
        },
    )
    write_json(
        root / "human_review_decision_template.json",
        state.human_review_decision_template,
    )
    write_json(
        root / "human_review_editing_interface.json",
        state.human_review_editing_interface,
    )
    write_json(
        root / "human_review_import_preview.json",
        state.human_review_import_preview,
    )
    write_json(
        root / "human_review_commit_manifest.json",
        state.human_review_commit_manifest,
    )
    write_json(
        root / "human_review_commit_result.json",
        state.human_review_commit_result,
    )
    write_json(
        root / "human_review_receipt_verification.json",
        state.human_review_receipt_verification,
    )
    write_json(
        root / "human_review_recovery_check.json",
        state.human_review_recovery_check,
    )
    write_json(
        root / "approved_patch_application_preview.json",
        state.approved_patch_application_preview,
    )
    write_json(
        root / "patch_application_manifest.json",
        state.patch_application_manifest,
    )
    write_json(
        root / "patch_application_result.json",
        state.patch_application_result,
    )
    write_json(
        root / "patch_application_receipt_verification.json",
        state.patch_application_receipt_verification,
    )
    write_json(
        root / "patch_rollback_readiness.json",
        state.patch_rollback_readiness,
    )
    write_json(
        root / "patch_rollback_result.json",
        state.patch_rollback_result,
    )
    write_json(
        root / "patch_rollback_receipt_verification.json",
        state.patch_rollback_receipt_verification,
    )
    write_json(
        root / "patch_lifecycle_closure.json",
        state.patch_lifecycle_closure,
    )
    rollback_request_path = root / "patch_rollback_request.json"
    if not rollback_request_path.exists():
        write_json(rollback_request_path, {
            "schema": "archon_patch_rollback_request_v1",
            "rollback": False,
            "rollback_package_id": None,
            "rollback_package_hash": None,
            "application_id": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "last_consumed_commit_id": None,
            "instructions": {
                "confirmation_phrase": "ROLLBACK_RESEARCH_ACTION_PATCHES",
                "source": "Copy identifiers from patch_rollback_readiness.json.",
                "scope": "Restores ResearchAction rollback snapshots only.",
            },
        })
    application_request_path = root / "patch_application_request.json"
    if not application_request_path.exists():
        write_json(application_request_path, {
            "schema": "archon_patch_application_request_v1",
            "apply": False,
            "application_manifest_id": None,
            "manifest_hash": None,
            "source_commit_id": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "instructions": {
                "confirmation_phrase": "APPLY_RESEARCH_ACTION_PATCHES",
                "source": "Copy IDs and hashes from patch_application_manifest.json.",
                "scope": "Applies persistent ResearchAction field overrides only.",
            },
        })
    commit_request_path = root / "human_review_commit_request.json"
    if not commit_request_path.exists():
        write_json(commit_request_path, {
            "schema": "archon_review_commit_request_v1",
            "commit": False,
            "commit_id": None,
            "candidate_hash": None,
            "expected_decision_store_hash": None,
            "requested_at": None,
            "requested_by": None,
            "confirmation": None,
            "instructions": {
                "confirmation_phrase": "COMMIT_REVIEW_DECISIONS",
                "source": "Copy commit_id and hashes from human_review_commit_manifest.json.",
                "scope": "Writes human_review_decisions.json only.",
            },
        })
    candidate_path = root / "human_review_import_candidate.json"
    if not candidate_path.exists():
        write_json(candidate_path, {
            "schema": "archon_review_import_candidate_v1",
            "rows": [],
            "instructions": {
                "source": "Copy rows from human_review_editing_interface.json.",
                "editable_fields": sorted(EDITABLE_REVIEW_FIELDS),
                "immutable_fields": sorted(IMMUTABLE_REVIEW_FIELDS),
                "import_behavior": "PREVIEW_ONLY",
            },
        })
    write_json(data, asdict(state))
    write_json(actions, {
        "generated_at": state.generated_at,
        "stage": state.stage,
        "maturity": state.maturity,
        "risk": state.risk,
        "trend": state.trend,
        "maturity_delta": state.maturity_delta,
        "risk_delta": state.risk_delta,
        "rules_delta": state.rules_delta,
        "consensus_delta": state.consensus_delta,
        "stagnation": state.stagnation,
        "dependency_graph": state.dependency_graph,
        "consensus_action_intake": state.consensus_action_intake,
        "consensus_action_reconciliation": state.consensus_action_reconciliation,
        "consensus_coverage_interpretation": state.consensus_coverage_interpretation,
        "coverage_aware_recommendations": state.coverage_aware_recommendations,
        "consolidated_recommendations": state.consolidated_recommendations,
        "recommendation_patch_proposals": state.recommendation_patch_proposals,
        "patch_proposal_validation": state.patch_proposal_validation,
        "patch_conflict_resolution_plan": state.patch_conflict_resolution_plan,
        "human_review_queue": state.human_review_queue,
        "human_review_decisions": state.human_review_decisions,
        "human_review_validation": state.human_review_validation,
        "human_review_audit_trail": state.human_review_audit_trail,
        "human_review_decision_template": state.human_review_decision_template,
        "human_review_editing_interface": state.human_review_editing_interface,
        "human_review_import_preview": state.human_review_import_preview,
        "human_review_commit_manifest": state.human_review_commit_manifest,
        "human_review_commit_request": state.human_review_commit_request,
        "human_review_commit_result": state.human_review_commit_result,
        "human_review_receipt_verification": state.human_review_receipt_verification,
        "human_review_recovery_check": state.human_review_recovery_check,
        "approved_patch_application_preview": state.approved_patch_application_preview,
        "patch_application_manifest": state.patch_application_manifest,
        "research_action_patch_state": state.research_action_patch_state,
        "patch_application_request": state.patch_application_request,
        "patch_application_result": state.patch_application_result,
        "patch_application_receipt_verification": state.patch_application_receipt_verification,
        "patch_rollback_readiness": state.patch_rollback_readiness,
        "patch_rollback_request": state.patch_rollback_request,
        "patch_rollback_result": state.patch_rollback_result,
        "patch_rollback_receipt_verification": state.patch_rollback_receipt_verification,
        "patch_lifecycle_closure": state.patch_lifecycle_closure,
        "actions": actions_to_json(state.actions),
        "scientific_policy": {
            "consensus_intake_advisory_only": True,
            "consensus_intake_creates_actions": False,
            "consensus_intake_changes_priority": False,
            "consensus_intake_changes_strategic_score": False,
            "reconciliation_creates_actions": False,
            "reconciliation_changes_priority": False,
            "reconciliation_changes_strategic_score": False,
            "coverage_interpretation_creates_actions": False,
            "coverage_interpretation_changes_priority": False,
            "coverage_interpretation_changes_strategic_score": False,
            "coverage_recommendations_create_actions": False,
            "coverage_recommendations_modify_actions": False,
            "coverage_recommendations_change_priority": False,
            "coverage_recommendations_change_strategic_score": False,
            "recommendation_consolidation_creates_actions": False,
            "recommendation_consolidation_modifies_actions": False,
            "recommendation_consolidation_changes_priority": False,
            "recommendation_consolidation_changes_strategic_score": False,
            "patch_proposals_apply_automatically": False,
            "patch_proposals_modify_actions": False,
            "patch_proposals_create_actions": False,
            "patch_proposals_change_priority": False,
            "patch_proposals_change_strategic_score": False,
            "patch_validation_applies_patches": False,
            "patch_validation_modifies_actions": False,
            "patch_validation_changes_priority": False,
            "patch_validation_changes_strategic_score": False,
            "conflict_resolution_applies_changes": False,
            "conflict_resolution_modifies_actions": False,
            "conflict_resolution_changes_priority": False,
            "conflict_resolution_changes_strategic_score": False,
            "human_review_approval_applies_patch": False,
            "human_review_modifies_actions": False,
            "human_review_changes_priority": False,
            "human_review_changes_strategic_score": False,
            "review_validation_changes_decisions": False,
            "review_audit_is_append_only": True,
            "review_audit_applies_patches": False,
            "review_template_is_authoritative": False,
            "review_template_imports_automatically": False,
            "review_editing_interface_applies_patches": False,
            "review_import_preview_writes_decisions": False,
            "review_import_preview_applies_patches": False,
            "review_import_requires_explicit_step": True,
            "review_commit_manifest_writes_decisions": False,
            "review_commit_manifest_applies_patches": False,
            "review_commit_requires_hash_match": True,
            "atomic_commit_writes_decision_store_only": True,
            "atomic_commit_applies_patches": False,
            "atomic_commit_modifies_actions": False,
            "atomic_commit_requires_explicit_confirmation": True,
            "receipt_verification_repairs_state": False,
            "recovery_check_rolls_back_automatically": False,
            "recovery_check_modifies_actions": False,
            "approved_patch_preview_applies_patches": False,
            "approved_patch_preview_modifies_actions": False,
            "approved_patch_preview_requires_verified_receipt": True,
            "patch_application_manifest_applies_patches": False,
            "patch_application_manifest_modifies_actions": False,
            "patch_application_manifest_requires_action_hash_match": True,
            "atomic_patch_gateway_modifies_actions": True,
            "atomic_patch_gateway_changes_scientific_metrics": False,
            "atomic_patch_gateway_requires_explicit_confirmation": True,
            "atomic_patch_gateway_persists_overrides": True,
            "patch_receipt_verification_repairs_state": False,
            "patch_rollback_readiness_rolls_back": False,
            "patch_rollback_requires_explicit_gateway": True,
            "explicit_patch_rollback_modifies_actions": True,
            "explicit_patch_rollback_changes_metrics": False,
            "explicit_patch_rollback_changes_decision_history": False,
            "explicit_patch_rollback_requires_confirmation": True,
            "successful_commit_request_is_consumed": True,
            "rollback_receipt_verification_repairs_state": False,
            "patch_lifecycle_closure_changes_state": False,
            "patch_lifecycle_closure_changes_metrics": False,
        },
    })

def print_banner(state: ResearchDirectorState, root: Path) -> None:
    print("=" * 64)
    print("Universe Search Research Director v37.6.3 — Stage 5.3 Commit Request Consumption Fix")
    print("=" * 64)
    print(f"Output MD:    {root / 'research_director_report.md'}")
    print(f"Output JSON:  {root / 'research_director_report.json'}")
    print(f"Next actions: {root / 'next_research_actions.json'}")
    print("-" * 64)
    print(f"Stage:        {state.stage}")
    print(f"Maturity:     {state.maturity:.3f}")
    print(f"Risk:         {state.risk:.3f}")
    print(f"Trend:        {state.trend}")
    print(f"ΔMaturity:    {state.maturity_delta:+.3f}")
    print(f"ΔRisk:        {state.risk_delta:+.3f}")
    print(f"Rules:        {state.rules} ({state.rules_delta:+d})")
    print(f"Principles:   {state.principles}")
    print(f"Consensus:    {state.consensus_principles}")
    print(f"Predictions:  {state.predictions} ({state.confirmed_predictions} confirmed, {state.testing_predictions} testing)")
    print(f"Experiments:  {state.planned_experiments}")
    print(f"Integrity:    {'OK' if state.integrity_ok else 'FAILED'}")
    print(f"Actions:      {len(state.actions)}")
    intake = (
        state.consensus_action_intake
        if isinstance(state.consensus_action_intake, dict)
        else {}
    )
    print(
        "Consensus in: "
        f"{int(safe_num(intake.get('principle_count'), 0))} principles | "
        f"{int(safe_num(intake.get('active_signal_count'), 0))} active | "
        f"{int(safe_num(intake.get('blocked_signal_count'), 0))} blocked"
    )
    print("Intake mode:  ADVISORY_ONLY")
    reconciliation = (
        state.consensus_action_reconciliation
        if isinstance(state.consensus_action_reconciliation, dict)
        else {}
    )
    counts = reconciliation.get("status_counts", {})
    print(
        "Reconciled:   "
        f"{int(safe_num(counts.get('covered'), 0))} covered | "
        f"{int(safe_num(counts.get('partial'), 0))} partial | "
        f"{int(safe_num(counts.get('uncovered'), 0))} uncovered | "
        f"{int(safe_num(counts.get('blocked'), 0))} blocked"
    )
    print("Reconcile:    ADVISORY_ONLY")
    coverage = (
        state.consensus_coverage_interpretation
        if isinstance(state.consensus_coverage_interpretation, dict)
        else {}
    )
    coverage_counts = coverage.get("state_counts", {})
    print(
        "Coverage:     "
        f"{int(safe_num(coverage_counts.get('fully_addressed'), 0))} full | "
        f"{int(safe_num(coverage_counts.get('partially_addressed'), 0))} partial | "
        f"{int(safe_num(coverage_counts.get('unaddressed'), 0))} unaddressed | "
        f"{int(safe_num(coverage_counts.get('blocked'), 0))} blocked"
    )
    print("Coverage mode: INTERPRETATION_ONLY")
    recommendations = (
        state.coverage_aware_recommendations
        if isinstance(state.coverage_aware_recommendations, dict)
        else {}
    )
    rec_priorities = recommendations.get("priority_counts", {})
    print(
        "Recommendations: "
        f"{int(safe_num(recommendations.get('recommendation_count'), 0))} total | "
        f"{int(safe_num(rec_priorities.get('CRITICAL'), 0))} critical | "
        f"{int(safe_num(rec_priorities.get('HIGH'), 0))} high | "
        f"{int(safe_num(rec_priorities.get('MEDIUM'), 0))} medium"
    )
    print("Recommend:    ADVISORY_ONLY")
    consolidated = (
        state.consolidated_recommendations
        if isinstance(state.consolidated_recommendations, dict)
        else {}
    )
    primary = consolidated.get("primary_recommendation")
    print(
        "Consolidated: "
        f"{int(safe_num(consolidated.get('action_group_count'), 0))} action groups | "
        f"{int(safe_num(consolidated.get('principle_group_count'), 0))} principle groups"
    )
    print(
        "Primary rec:  "
        f"{primary.get('recommendation_id') if isinstance(primary, dict) else '-'}"
    )
    print("Consolidate:  ADVISORY_ONLY")
    patch_bundle = (
        state.recommendation_patch_proposals
        if isinstance(state.recommendation_patch_proposals, dict)
        else {}
    )
    print(
        "Patch proposals: "
        f"{int(safe_num(patch_bundle.get('proposal_count'), 0))}"
    )
    print("Patch mode:   PROPOSAL_ONLY")
    validation = (
        state.patch_proposal_validation
        if isinstance(state.patch_proposal_validation, dict)
        else {}
    )
    validation_counts = validation.get("status_counts", {})
    print(
        "Patch validate: "
        f"{int(safe_num(validation_counts.get('VALID'), 0))} valid | "
        f"{int(safe_num(validation_counts.get('REDUNDANT'), 0))} redundant | "
        f"{int(safe_num(validation_counts.get('CONFLICTING'), 0))} conflicting | "
        f"{int(safe_num(validation_counts.get('BLOCKED'), 0))} blocked | "
        f"{int(safe_num(validation_counts.get('INVALID_TARGET'), 0))} invalid"
    )
    print("Validation:   REVIEW_REQUIRED")
    resolution_plan = (
        state.patch_conflict_resolution_plan
        if isinstance(state.patch_conflict_resolution_plan, dict)
        else {}
    )
    print(
        "Resolution:   "
        f"{int(safe_num(resolution_plan.get('problem_proposal_count'), 0))} problems | "
        f"{int(safe_num(resolution_plan.get('merge_possible_count'), 0))} mergeable | "
        f"{int(safe_num(resolution_plan.get('manual_decision_count'), 0))} manual"
    )
    print("Resolve mode: EXPLANATION_ONLY")
    review_queue = (
        state.human_review_queue
        if isinstance(state.human_review_queue, dict)
        else {}
    )
    review_counts = review_queue.get("decision_counts", {})
    print(
        "Human review: "
        f"{int(safe_num(review_queue.get('queue_count'), 0))} queued | "
        f"{int(safe_num(review_counts.get('PENDING_REVIEW'), 0))} pending | "
        f"{int(safe_num(review_counts.get('APPROVED'), 0))} approved | "
        f"{int(safe_num(review_counts.get('REJECTED'), 0))} rejected"
    )
    print("Review mode:  DECISION_RECORD_ONLY")
    review_validation = (
        state.human_review_validation
        if isinstance(state.human_review_validation, dict)
        else {}
    )
    review_audit = (
        state.human_review_audit_trail
        if isinstance(state.human_review_audit_trail, dict)
        else {}
    )
    print(
        "Review valid: "
        f"{int(safe_num(review_validation.get('valid_record_count'), 0))} valid | "
        f"{int(safe_num(review_validation.get('invalid_record_count'), 0))} invalid"
    )
    print(
        "Audit trail:  "
        f"{int(safe_num(review_audit.get('event_count'), 0))} events | "
        f"{int(safe_num(review_audit.get('appended_event_count'), 0))} new"
    )
    print("Audit mode:   APPEND_ONLY")
    template = (
        state.human_review_decision_template
        if isinstance(state.human_review_decision_template, dict)
        else {}
    )
    editing = (
        state.human_review_editing_interface
        if isinstance(state.human_review_editing_interface, dict)
        else {}
    )
    print(
        "Review template: "
        f"{int(safe_num(template.get('record_count'), 0))} records"
    )
    print(
        "Safe editor:   "
        f"{int(safe_num(editing.get('row_count'), 0))} rows"
    )
    print("Template mode: NON_AUTHORITATIVE")
    import_preview = (
        state.human_review_import_preview
        if isinstance(state.human_review_import_preview, dict)
        else {}
    )
    preview_counts = import_preview.get("category_counts", {})
    print(
        "Import preview: "
        f"{int(safe_num(preview_counts.get('NEW_RECORD'), 0))} new | "
        f"{int(safe_num(preview_counts.get('CHANGED_DECISION'), 0))} changed | "
        f"{int(safe_num(preview_counts.get('UNCHANGED'), 0))} unchanged | "
        f"{int(safe_num(import_preview.get('blocked_count'), 0))} blocked"
    )
    print("Import mode:  PREVIEW_ONLY")
    commit_manifest = (
        state.human_review_commit_manifest
        if isinstance(state.human_review_commit_manifest, dict)
        else {}
    )
    print(
        "Commit manifest: "
        f"{int(safe_num(commit_manifest.get('importable_row_count'), 0))} importable | "
        f"{int(safe_num(commit_manifest.get('skipped_row_count'), 0))} skipped"
    )
    print(
        "Commit ID:     "
        f"{commit_manifest.get('commit_id') or '-'}"
    )
    print("Commit mode:   MANIFEST_ONLY")
    commit_result = (
        state.human_review_commit_result
        if isinstance(state.human_review_commit_result, dict)
        else {}
    )
    print(
        "Commit gateway: "
        f"{commit_result.get('status') or '-'} | "
        f"{int(safe_num(commit_result.get('inserted_count'), 0))} inserted | "
        f"{int(safe_num(commit_result.get('updated_count'), 0))} updated | "
        f"{int(safe_num(commit_result.get('failed_check_count'), 0))} failed checks"
    )
    print("Gateway mode:  EXPLICIT_ATOMIC_COMMIT")
    receipt_verification = (
        state.human_review_receipt_verification
        if isinstance(state.human_review_receipt_verification, dict)
        else {}
    )
    recovery_check = (
        state.human_review_recovery_check
        if isinstance(state.human_review_recovery_check, dict)
        else {}
    )
    print(
        "Receipt verify: "
        f"{receipt_verification.get('status') or '-'} | "
        f"{int(safe_num(receipt_verification.get('failed_check_count'), 0))} failed | "
        f"{int(safe_num(receipt_verification.get('warning_count'), 0))} warnings"
    )
    print(
        "Recovery check: "
        f"{recovery_check.get('status') or '-'}"
    )
    print("Recovery mode: CHECK_ONLY")
    application_preview = (
        state.approved_patch_application_preview
        if isinstance(state.approved_patch_application_preview, dict)
        else {}
    )
    application_counts = application_preview.get("status_counts", {})
    print(
        "Patch preview: "
        f"{int(safe_num(application_counts.get('ELIGIBLE'), 0))} eligible | "
        f"{int(safe_num(application_counts.get('NOT_APPROVED'), 0))} not approved | "
        f"{int(safe_num(application_counts.get('INVALID_PROPOSAL'), 0))} invalid | "
        f"{int(safe_num(application_preview.get('blocked_count'), 0))} blocked"
    )
    print("Apply mode:    PREVIEW_ONLY")
    application_manifest = (
        state.patch_application_manifest
        if isinstance(state.patch_application_manifest, dict)
        else {}
    )
    print(
        "Apply manifest: "
        f"{int(safe_num(application_manifest.get('eligible_row_count'), 0))} eligible | "
        f"{int(safe_num(application_manifest.get('skipped_row_count'), 0))} skipped | "
        f"ready={bool(application_manifest.get('final_ready'))}"
    )
    print(
        "Manifest ID:   "
        f"{application_manifest.get('application_manifest_id') or '-'}"
    )
    print("Manifest mode: FINAL_SAFETY_ONLY")
    patch_result = (
        state.patch_application_result
        if isinstance(state.patch_application_result, dict)
        else {}
    )
    patch_state = (
        state.research_action_patch_state
        if isinstance(state.research_action_patch_state, dict)
        else {}
    )
    print(
        "Patch gateway: "
        f"{patch_result.get('status') or '-'} | "
        f"{int(safe_num(patch_result.get('applied_action_count'), 0))} applied | "
        f"{int(safe_num(patch_result.get('failed_check_count'), 0))} failed checks"
    )
    print(
        "Patch state:   "
        f"{int(safe_num(patch_state.get('override_count'), 0))} persistent overrides"
    )
    print("Gateway mode:  EXPLICIT_ATOMIC_ACTION_PATCH")
    patch_receipt = (
        state.patch_application_receipt_verification
        if isinstance(state.patch_application_receipt_verification, dict)
        else {}
    )
    rollback = (
        state.patch_rollback_readiness
        if isinstance(state.patch_rollback_readiness, dict)
        else {}
    )
    print(
        "Patch receipt: "
        f"{patch_receipt.get('status') or '-'} | "
        f"{int(safe_num(patch_receipt.get('verified_action_count'), 0))} verified | "
        f"{int(safe_num(patch_receipt.get('failed_check_count'), 0))} failed"
    )
    print(
        "Rollback:      "
        f"{rollback.get('status') or '-'} | "
        f"{int(safe_num(rollback.get('rollback_action_count'), 0))} actions"
    )
    print("Rollback mode: READINESS_ONLY")
    rollback_result = (
        state.patch_rollback_result
        if isinstance(state.patch_rollback_result, dict)
        else {}
    )
    patch_state = (
        state.research_action_patch_state
        if isinstance(state.research_action_patch_state, dict)
        else {}
    )
    print(
        "Rollback gate: "
        f"{rollback_result.get('status') or '-'} | "
        f"{int(safe_num(rollback_result.get('rolled_back_action_count'), 0))} restored | "
        f"{int(safe_num(rollback_result.get('failed_check_count'), 0))} failed checks"
    )
    print(
        "Patch state:   "
        f"{int(safe_num(patch_state.get('override_count'), 0))} persistent overrides"
    )
    print("Rollback gate: EXPLICIT_ATOMIC_PATCH_ROLLBACK")
    rollback_receipt = (
        state.patch_rollback_receipt_verification
        if isinstance(state.patch_rollback_receipt_verification, dict)
        else {}
    )
    lifecycle = (
        state.patch_lifecycle_closure
        if isinstance(state.patch_lifecycle_closure, dict)
        else {}
    )
    print(
        "Rollback receipt: "
        f"{rollback_receipt.get('status') or '-'} | "
        f"{int(safe_num(rollback_receipt.get('verified_action_count'), 0))} verified | "
        f"{int(safe_num(rollback_receipt.get('failed_check_count'), 0))} failed"
    )
    print(
        "Patch lifecycle: "
        f"{lifecycle.get('status') or '-'} | "
        f"closed={bool(lifecycle.get('closed'))}"
    )
    print("Lifecycle mode: CLASSIFICATION_ONLY")
    graph = state.dependency_graph or {}
    print(
        f"Dependencies: {graph.get('required_edge_count', 0)} required, "
        f"{graph.get('supporting_edge_count', 0)} supporting"
    )
    print("-" * 64)
    for a in state.actions[:6]:
        bottleneck = (
            f" | bottleneck={a.bottleneck_component}"
            f"({a.bottleneck_directness})"
            if a.bottleneck_component
            else ""
        )
        print(
            f"P{a.priority} (base {a.base_priority}, strategic={a.strategic_score:.2f}): "
            f"{a.title} | {a.kind} | runtime={a.estimated_runtime} "
            f"| cost={a.estimated_cost} | automation={a.automation_level} "
            f"| info={a.expected_information_gain_score:.2f} "
            f"| unlock={a.unlock_score:.2f}"
            f"(raw={a.graph_unlock_raw:.2f}) "
            f"| deps={','.join(a.depends_on_actions) or '-'} "
            f"| opens={','.join(a.unlocks_actions) or '-'}{bottleneck}"
        )
    print("=" * 64)
