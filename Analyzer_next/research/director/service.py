"""Coordinate the complete Research Director use case."""
from __future__ import annotations

from pathlib import Path

from Analyzer_next.research.director.governance.patch_application import atomic_apply_research_action_patches, load_latest_patch_application_receipt, load_patch_application_request, verify_patch_application_receipt
from Analyzer_next.research.director.governance.patch_preview import apply_persisted_research_action_patches, build_approved_patch_application_preview, build_patch_application_manifest, load_research_action_patch_state
from Analyzer_next.research.director.governance.patch_rollback import atomic_rollback_research_action_patches, build_patch_lifecycle_closure, build_patch_rollback_readiness, close_application_lifecycle_after_verified_rollback, load_latest_patch_rollback_receipt, load_patch_rollback_request, verify_patch_rollback_receipt
from Analyzer_next.research.director.governance.proposals import build_integrity_recovery_revisions, build_patch_conflict_resolution_plan, build_recommendation_patch_proposals, promote_redundant_ready_proposals_to_direct_execution, validate_patch_proposals
from Analyzer_next.research.director.governance.review import build_human_review_audit_update, build_human_review_decision_template, build_human_review_queue, build_review_import_preview, build_safe_review_editing_interface, load_human_review_decisions, validate_human_review_records
from Analyzer_next.research.director.governance.review_transactions import build_review_commit_manifest, build_review_recovery_check, commit_human_review_decisions, load_latest_review_commit_receipt, verify_review_commit_receipt
from Analyzer_next.research.director.orchestrator import append_director_history, apply_director_trends, evaluate_state, finalize_action_strategy
from Analyzer_next.research.director.reporting import print_banner, write_report
from Analyzer_next.research.director.scoring import build_coverage_aware_recommendations, consolidate_coverage_recommendations, interpret_director_coverage_gaps, reconcile_consensus_signals_to_actions


def run_director(results_dir: Path, root: Path, knowledge_root: Path) -> int:
    if not results_dir.exists():
        print(f"[ERROR] Results folder does not exist: {results_dir}")
        return 1
    root.mkdir(parents=True, exist_ok=True)
    knowledge_root.mkdir(parents=True, exist_ok=True)

    state = evaluate_state(results_dir, root, knowledge_root)
    state = apply_director_trends(knowledge_root, state)
    state = finalize_action_strategy(state)
    persisted_patch_apply = apply_persisted_research_action_patches(
        state.actions,
        state.research_action_patch_state,
    )
    state.research_action_patch_state["apply_result"] = (
        persisted_patch_apply
    )
    target_integrity_invalidated_proposals = {
        str(row.get("source_proposal_id"))
        for row in persisted_patch_apply.get(
            "principle_integrity_rejections", []
        )
        if isinstance(row, dict) and row.get("source_proposal_id")
    }
    state.consensus_action_reconciliation = (
        reconcile_consensus_signals_to_actions(
            state.consensus_action_intake,
            state.actions,
        )
    )
    state.consensus_coverage_interpretation = (
        interpret_director_coverage_gaps(
            state.consensus_action_intake,
            state.consensus_action_reconciliation,
        )
    )
    state.coverage_aware_recommendations = (
        build_coverage_aware_recommendations(
            state.consensus_coverage_interpretation,
            state.consensus_action_reconciliation,
        )
    )
    state.consolidated_recommendations = (
        consolidate_coverage_recommendations(
            state.coverage_aware_recommendations
        )
    )
    state.recommendation_patch_proposals = (
        build_recommendation_patch_proposals(
            state.consolidated_recommendations,
            state.actions,
        )
    )
    state.recommendation_patch_proposals = (
        build_integrity_recovery_revisions(
            state.recommendation_patch_proposals,
            state.actions,
            state.research_action_patch_state,
            persisted_patch_apply.get(
                "principle_integrity_rejections", []
            ),
        )
    )
    state.patch_proposal_validation = (
        validate_patch_proposals(
            state.recommendation_patch_proposals,
            state.actions,
            state.coverage_aware_recommendations,
        )
    )
    # BRIDGE5.8.3: a Consensus refinement can become textually redundant
    # after an earlier Director refresh while the canonical ResearchAction is
    # still waiting for execution.  Do not let patch redundancy erase the
    # action from OL2.  Promote only undecided, execution-ready rows to a
    # snapshot-protected direct activation, then validate the changed proposal
    # semantics again before the review queue is built.
    promoted_bundle = promote_redundant_ready_proposals_to_direct_execution(
        state.recommendation_patch_proposals,
        state.patch_proposal_validation,
        state.actions,
        state.human_review_decisions,
    )
    if promoted_bundle != state.recommendation_patch_proposals:
        state.recommendation_patch_proposals = promoted_bundle
        state.patch_proposal_validation = (
            validate_patch_proposals(
                state.recommendation_patch_proposals,
                state.actions,
                state.coverage_aware_recommendations,
            )
        )
    state.patch_conflict_resolution_plan = (
        build_patch_conflict_resolution_plan(
            state.patch_proposal_validation,
            state.recommendation_patch_proposals,
            state.coverage_aware_recommendations,
        )
    )
    state.human_review_validation = (
        validate_human_review_records(
            state.human_review_decisions,
            state.recommendation_patch_proposals,
            state.human_review_audit_trail,
        )
    )
    state.human_review_audit_trail = (
        build_human_review_audit_update(
            state.human_review_decisions,
            state.human_review_validation,
            state.human_review_audit_trail,
        )
    )
    state.human_review_queue = (
        build_human_review_queue(
            state.recommendation_patch_proposals,
            state.patch_proposal_validation,
            state.patch_conflict_resolution_plan,
            state.human_review_decisions,
            target_integrity_invalidated_proposals,
        )
    )
    state.human_review_decision_template = (
        build_human_review_decision_template(
            state.human_review_queue
        )
    )
    state.human_review_editing_interface = (
        build_safe_review_editing_interface(
            state.human_review_queue,
            state.human_review_decision_template,
            state.human_review_decisions,
        )
    )
    import_candidate = (
        state.human_review_import_preview.get(
            "import_candidate", {}
        )
        if isinstance(
            state.human_review_import_preview, dict
        )
        else {}
    )
    state.human_review_import_preview = (
        build_review_import_preview(
            import_candidate,
            state.human_review_editing_interface,
            state.human_review_decisions,
        )
    )
    state.human_review_commit_manifest = (
        build_review_commit_manifest(
            import_candidate,
            state.human_review_import_preview,
            state.human_review_decisions,
        )
    )
    state.human_review_commit_result = (
        commit_human_review_decisions(
            root,
            state.human_review_commit_request,
            state.human_review_commit_manifest,
            import_candidate,
            state.human_review_import_preview,
            state.human_review_decisions,
        )
    )
    if state.human_review_commit_result.get("committed"):
        state.human_review_decisions = (
            load_human_review_decisions(root)
        )
        state.human_review_validation = (
            validate_human_review_records(
                state.human_review_decisions,
                state.recommendation_patch_proposals,
                state.human_review_audit_trail,
            )
        )
        state.human_review_audit_trail = (
            build_human_review_audit_update(
                state.human_review_decisions,
                state.human_review_validation,
                state.human_review_audit_trail,
            )
        )
        state.human_review_queue = (
            build_human_review_queue(
                state.recommendation_patch_proposals,
                state.patch_proposal_validation,
                state.patch_conflict_resolution_plan,
                state.human_review_decisions,
                target_integrity_invalidated_proposals,
            )
        )
        receipt_lookup = load_latest_review_commit_receipt(root)
    else:
        receipt_lookup = (
            state.human_review_receipt_verification.get(
                "receipt_lookup", {}
            )
            if isinstance(
                state.human_review_receipt_verification,
                dict,
            )
            else {}
        )

    state.human_review_receipt_verification = (
        verify_review_commit_receipt(
            root,
            receipt_lookup,
            state.human_review_decisions,
            state.human_review_audit_trail,
        )
    )
    state.human_review_recovery_check = (
        build_review_recovery_check(
            state.human_review_receipt_verification,
            state.human_review_decisions,
        )
    )
    state.approved_patch_application_preview = (
        build_approved_patch_application_preview(
            state.actions,
            state.recommendation_patch_proposals,
            state.patch_proposal_validation,
            state.human_review_decisions,
            state.human_review_receipt_verification,
        )
    )
    state.patch_application_manifest = (
        build_patch_application_manifest(
            state.actions,
            state.approved_patch_application_preview,
            state.recommendation_patch_proposals,
            state.human_review_receipt_verification,
        )
    )
    state.patch_application_result = (
        atomic_apply_research_action_patches(
            root,
            state.actions,
            state.patch_application_request,
            state.patch_application_manifest,
            state.research_action_patch_state,
        )
    )
    if state.patch_application_result.get("applied"):
        state.research_action_patch_state = (
            load_research_action_patch_state(root)
        )
        state.research_action_patch_state["apply_result"] = {
            "applied_count": state.patch_application_result.get(
                "applied_action_count", 0
            ),
            "applied_action_ids": state.patch_application_result.get(
                "applied_action_ids", []
            ),
        }
        patch_receipt_lookup = (
            load_latest_patch_application_receipt(root)
        )
        state.patch_application_request = (
            load_patch_application_request(root)
        )
    else:
        patch_receipt_lookup = (
            state.patch_application_receipt_verification.get(
                "receipt_lookup", {}
            )
            if isinstance(
                state.patch_application_receipt_verification,
                dict,
            )
            else {}
        )

    state.patch_application_receipt_verification = (
        verify_patch_application_receipt(
            root,
            state.actions,
            patch_receipt_lookup,
            state.research_action_patch_state,
            state.patch_application_request,
        )
    )
    state.patch_rollback_readiness = (
        build_patch_rollback_readiness(
            root,
            state.patch_application_receipt_verification,
            state.research_action_patch_state,
        )
    )
    state.patch_rollback_result = (
        atomic_rollback_research_action_patches(
            root,
            state.actions,
            state.patch_rollback_request,
            state.patch_rollback_readiness,
            state.research_action_patch_state,
        )
    )
    if state.patch_rollback_result.get("rolled_back"):
        state.research_action_patch_state = (
            load_research_action_patch_state(root)
        )
        state.patch_rollback_request = (
            load_patch_rollback_request(root)
        )
        rollback_receipt_lookup = (
            load_latest_patch_rollback_receipt(root)
        )
    else:
        rollback_receipt_lookup = (
            state.patch_rollback_receipt_verification.get(
                "receipt_lookup", {}
            )
            if isinstance(
                state.patch_rollback_receipt_verification,
                dict,
            )
            else {}
        )

    state.patch_rollback_receipt_verification = (
        verify_patch_rollback_receipt(
            root,
            state.actions,
            rollback_receipt_lookup,
            state.research_action_patch_state,
            state.patch_rollback_request,
        )
    )
    (
        state.patch_application_receipt_verification,
        state.patch_rollback_readiness,
    ) = close_application_lifecycle_after_verified_rollback(
        state.patch_application_receipt_verification,
        state.patch_rollback_readiness,
        state.patch_rollback_receipt_verification,
    )
    state.patch_lifecycle_closure = (
        build_patch_lifecycle_closure(
            state.patch_application_receipt_verification,
            state.patch_rollback_receipt_verification,
            state.research_action_patch_state,
        )
    )
    write_report(root, state)
    append_director_history(knowledge_root, state)
    print_banner(state, root)
    return 0
