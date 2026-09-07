"""EXPERIMENTS-FIX3 compatibility layer over the audited experiment pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from Analyzer_next.adapters.observer.experiment_runtime_policy_compat import repair_runtime_policy
from Analyzer_next.adapters.observer.research_experiment_pipeline import (
    AuditedResearchExperimentPipeline,
    ResearchExperimentPipelineError,
    _load,
)
from Analyzer_next.research.director.common import canonical_json_hash
from Analyzer_next.execution.observer.shell2.functions1f.model import ExperimentPipelineResult


class AuditedResearchExperimentPipelineFix3(AuditedResearchExperimentPipeline):
    """Preserve audited owners while repairing legacy derived-state compatibility."""

    def __init__(self, project_root: Path, telemetry_database: Path, **kwargs: Any) -> None:
        super().__init__(project_root, telemetry_database, **kwargs)
        self.planner_intake = (
            self.project_root / "Analyzer_next" / "cli" / "approved_action_planner_intake_compat.py"
        )
        self.planner_review = (
            self.project_root / "Analyzer_next" / "cli" / "experiment_planner_review.py"
        )
        self.plan_commit = (
            self.project_root / "Analyzer_next" / "cli" / "experiment_plan_commit.py"
        )
        # BRIDGE5.1 keeps the frozen Analyzer resolver untouched while the
        # candidate pipeline resolves deterministic indirect perturbation
        # program bindings in Analyzer_next.
        self.protocol_resolver = (
            self.project_root / "Analyzer_next" / "cli" / "scientific_protocol_resolver.py"
        )

    @property
    def runtime_policy_path(self) -> Path:
        return self.experiments_root / "runtime_materialization_policy.json"

    def approve_and_materialize(self, proposal_id: str, *, decision_reason: str, progress=None):
        repair = repair_runtime_policy(self.runtime_policy_path)
        self._emit(progress, "policy", repair.message)
        status = self._proposal_validation_status(proposal_id)
        if status == "REDUNDANT":
            reuse = self._verified_redundant_governance(proposal_id)
            self._emit(
                progress,
                "governance",
                f"Governance already satisfied for {proposal_id}; reusing verified ACTIVE override "
                f"{reuse['application_id']} without reapplying the patch",
            )
            return self.rebuild_approved(proposal_id, progress=progress)
        return super().approve_and_materialize(
            proposal_id,
            decision_reason=decision_reason,
            progress=progress,
        )

    def _proposal_validation_status(self, proposal_id: str) -> str:
        report = _load(self.analysis_root / "research_director_report.json", {})
        for row in ((report.get("patch_proposal_validation") or {}).get("validations") or []):
            if not isinstance(row, dict):
                continue
            if str(row.get("proposal_id") or "") == str(proposal_id):
                return str(row.get("status") or "UNKNOWN").upper()
        return "UNKNOWN"

    def _verified_redundant_governance(self, proposal_id: str) -> dict[str, str]:
        """Return reusable governance identity for an already-satisfied proposal.

        REDUNDANT alone is never enough.  Reuse is allowed only when the same
        target action already has an explicit APPROVED review decision, the
        current Research Director action snapshot exactly matches an ACTIVE
        persisted override, and the latest patch receipt is VERIFIED.
        """
        proposal_id = str(proposal_id).strip()
        report = _load(self.analysis_root / "research_director_report.json", {})
        if self._proposal_validation_status(proposal_id) != "REDUNDANT":
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} is not REDUNDANT and cannot reuse satisfied governance"
            )

        proposals = (report.get("recommendation_patch_proposals") or {}).get("proposals") or []
        proposal = next(
            (row for row in proposals if isinstance(row, dict) and str(row.get("proposal_id") or "") == proposal_id),
            None,
        )
        action_id = str((proposal or {}).get("target_action_id") or "").strip()
        if not action_id:
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} has no target_action_id for redundant-governance verification"
            )

        decisions_file = _load(self.analysis_root / "human_review_decisions.json", {})
        decisions = decisions_file.get("records", []) if isinstance(decisions_file, dict) else []
        if not decisions:
            decisions = (report.get("human_review_decisions") or {}).get("records", []) or []
        approved = any(
            isinstance(row, dict)
            and str(row.get("proposal_id") or "") == proposal_id
            and str(row.get("decision") or "").upper() == "APPROVED"
            for row in decisions
        )
        if not approved:
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} is REDUNDANT but has no committed APPROVED human review decision"
            )

        lifecycle = _load(self.analysis_root / "patch_lifecycle_closure.json", {})
        receipt = _load(self.analysis_root / "patch_application_receipt_verification.json", {})
        if str(lifecycle.get("status") or "").upper() != "ACTIVE":
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} is REDUNDANT but governance lifecycle is not ACTIVE"
            )
        if str(receipt.get("status") or "").upper() not in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}:
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} is REDUNDANT but patch receipt is not VERIFIED"
            )

        action = next(
            (row for row in report.get("actions", []) if isinstance(row, dict) and str(row.get("action_id") or "") == action_id),
            None,
        )
        if action is None:
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} targets {action_id}, but that action is absent from the current Director report"
            )
        snapshot = {
            "action_id": str(action.get("action_id") or ""),
            "title": str(action.get("title") or ""),
            "suggested_target": str(action.get("suggested_target") or ""),
            "done_when": str(action.get("done_when") or ""),
            "rationale": str(action.get("rationale") or ""),
        }
        snapshot_hash = canonical_json_hash(snapshot)

        patch_state = _load(self.analysis_root / "research_action_patch_state.json", {})
        overrides = patch_state.get("overrides", []) if isinstance(patch_state, dict) else []
        override = next(
            (
                row
                for row in overrides
                if isinstance(row, dict)
                and str(row.get("action_id") or "") == action_id
                and str(row.get("snapshot_hash") or "") == snapshot_hash
            ),
            None,
        )
        if override is None:
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} is REDUNDANT but no ACTIVE override exactly matches current action {action_id}"
            )
        application_id = str(override.get("application_id") or "").strip()
        if not application_id:
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} matched an override without application_id"
            )
        return {
            "proposal_id": proposal_id,
            "action_id": action_id,
            "application_id": application_id,
            "snapshot_hash": snapshot_hash,
        }

    def reconcile_existing(self, *, progress=None):
        repair = repair_runtime_policy(self.runtime_policy_path)
        self._emit(progress, "policy", repair.message)
        return super().reconcile_existing(progress=progress)

    def _assert_proposal_approved(self, proposal_id: str) -> None:
        report = _load(self.analysis_root / "research_director_report.json", {})
        decisions = (
            (report.get("human_review_decisions") or {}).get("records", [])
            if isinstance(report, dict)
            else []
        )
        approved = [
            row
            for row in decisions
            if isinstance(row, dict)
            and str(row.get("proposal_id") or "") == proposal_id
            and str(row.get("decision") or "").upper() == "APPROVED"
        ]
        if not approved:
            raise ResearchExperimentPipelineError(
                f"proposal {proposal_id} has no committed APPROVED human review decision"
            )
        lifecycle = _load(self.analysis_root / "patch_lifecycle_closure.json", {})
        receipt = _load(
            self.analysis_root / "patch_application_receipt_verification.json", {}
        )
        if (
            str(lifecycle.get("status") or "") != "ACTIVE"
            or str(receipt.get("status") or "")
            not in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}
        ):
            raise ResearchExperimentPipelineError(
                "approved proposal cannot be rebuilt because verified governance patch lifecycle is not ACTIVE"
            )

    def rebuild_approved(self, proposal_id: str, *, progress=None) -> ExperimentPipelineResult:
        """Create/reuse a downstream plan revision without recommitting governance."""
        proposal_id = str(proposal_id).strip()
        if not proposal_id:
            raise ResearchExperimentPipelineError("proposal_id is required")
        status = self._proposal_validation_status(proposal_id)
        if status == "REDUNDANT":
            self._verified_redundant_governance(proposal_id)
        else:
            self._assert_proposal_valid(proposal_id)
            self._assert_proposal_approved(proposal_id)

        self._emit(
            progress,
            "planner",
            "Rebuilding approved proposal through kind-stable planner intake",
        )
        self._run_stage(
            self.planner_intake,
            ["--analysis-root", str(self.analysis_root)],
            "planner intake compatibility revision",
            progress,
        )
        self._run_stage(
            self.planner_review,
            ["--analysis-root", str(self.analysis_root)],
            "planner review compatibility revision",
            progress,
        )
        draft_ids = self._approve_matching_planner_drafts(proposal_id)
        if not draft_ids:
            raise ResearchExperimentPipelineError(
                f"no active valid planner draft was produced for approved proposal {proposal_id}"
            )
        self._run_stage(
            self.planner_review,
            ["--analysis-root", str(self.analysis_root)],
            "planner approval reconciliation",
            progress,
        )
        self._emit(
            progress,
            "commit",
            f"Committing/reusing {len(draft_ids)} approved plan revision(s)",
        )
        plan_ids = self._commit_matching_plans(proposal_id, draft_ids, progress)
        if not plan_ids:
            raise ResearchExperimentPipelineError(
                f"no experiment plan revision exists for approved proposal {proposal_id}"
            )
        self._sync_authoritative_cycle(
            proposal_id, through_state="PLANNED", plan_ids=plan_ids
        )

        repair = repair_runtime_policy(self.runtime_policy_path)
        self._emit(progress, "policy", repair.message)

        self._emit(progress, "targets", "Reconciling all committed target identities")
        self._run_stage(
            self.target_resolver,
            [
                "--analysis-root",
                str(self.analysis_root),
                "--telemetry-database",
                str(self.telemetry_database),
                "--confirmation",
                "RESOLVE_SCIENTIFIC_TARGETS",
            ],
            "scientific target resolver (approved revision full reconciliation)",
            progress,
            accepted=(0, 1),
        )
        self._emit(progress, "protocol", "Reconciling all committed scientific protocols")
        self._run_stage(
            self.protocol_resolver,
            [
                "--analysis-root",
                str(self.analysis_root),
                "--confirmation",
                "RESOLVE_SCIENTIFIC_PROTOCOLS",
            ],
            "scientific protocol resolver (approved revision full reconciliation)",
            progress,
            accepted=(0, 1),
        )
        self._emit(
            progress,
            "materialize",
            "Re-materializing runtime packages; launch remains unauthorized",
        )
        self._run_stage(
            self.runtime_materializer,
            ["--analysis-root", str(self.analysis_root)],
            "runtime materializer (approved revision full reconciliation)",
            progress,
            accepted=(0, 1),
        )

        experiment_ids, target_status = self._target_identities(plan_ids)
        runtime_ids, runtime_status = self._runtime_ids(plan_ids)
        self._sync_authoritative_cycle(
            proposal_id,
            through_state="MATERIALIZED",
            plan_ids=plan_ids,
            experiment_ids=experiment_ids,
            runtime_ids=runtime_ids,
        )
        overall = (
            "MATERIALIZED"
            if runtime_status == "READY_FOR_LAUNCH_REVIEW"
            else runtime_status
        )
        message = (
            f"{proposal_id}: approved plan revision reconciled • plans={len(plan_ids)} • "
            f"experiments={len(experiment_ids)} • runtimes={len(runtime_ids)} • "
            f"{overall} • launch not authorized"
        )
        if not experiment_ids:
            message += f" • target={target_status}"
        self._emit(progress, "done", message)
        return ExperimentPipelineResult(
            proposal_id=proposal_id,
            status=overall,
            plan_ids=tuple(plan_ids),
            experiment_ids=tuple(experiment_ids),
            runtime_ids=tuple(runtime_ids),
            message=message,
        )


__all__ = ["AuditedResearchExperimentPipelineFix3"]
