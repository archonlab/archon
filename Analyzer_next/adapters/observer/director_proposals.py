"""Read-only adapter for Research Director proposals shown by OL2-FUNCTIONS1E."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from Analyzer_next.execution.observer.shell2.functions1e.model import DirectorProposalRow


class JSONResearchDirectorProposalAdapter:
    """Project the existing Research Director report into simple UI rows.

    This adapter never writes governance files. Human approval/application remains
    owned by the audited Research Director pipeline.
    """

    def __init__(self, report_path: Path) -> None:
        self.report_path = Path(report_path).expanduser().resolve()

    def _load(self) -> dict[str, Any]:
        if not self.report_path.is_file():
            return {}
        payload = json.loads(self.report_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def list_proposals(self) -> tuple[DirectorProposalRow, ...]:
        report = self._load()
        if not report:
            return ()

        actions = {
            str(row.get("action_id")): row
            for row in report.get("actions", [])
            if isinstance(row, dict) and row.get("action_id")
        }
        proposal_container = report.get("recommendation_patch_proposals", {})
        proposals = proposal_container.get("proposals", []) if isinstance(proposal_container, dict) else []
        validation_container = report.get("patch_proposal_validation", {})
        validations = {
            str(row.get("proposal_id")): row
            for row in (validation_container.get("validations", []) if isinstance(validation_container, dict) else [])
            if isinstance(row, dict) and row.get("proposal_id")
        }
        resolution_container = report.get("patch_conflict_resolution_plan", {})
        resolutions = {
            str(row.get("proposal_id")): row
            for row in (resolution_container.get("plans", []) if isinstance(resolution_container, dict) else [])
            if isinstance(row, dict) and row.get("proposal_id")
        }
        review_container = report.get("human_review_queue", {})
        reviews = {
            str(row.get("proposal_id")): row
            for row in (review_container.get("queue", []) if isinstance(review_container, dict) else [])
            if isinstance(row, dict) and row.get("proposal_id")
        }

        rows: list[DirectorProposalRow] = []
        for proposal in proposals if isinstance(proposals, list) else []:
            if not isinstance(proposal, dict):
                continue
            proposal_id = str(proposal.get("proposal_id") or "").strip()
            if not proposal_id:
                continue
            action_id = str(proposal.get("target_action_id") or "").strip()
            action = actions.get(action_id, {})
            validation = validations.get(proposal_id, {})
            resolution = resolutions.get(proposal_id, {})
            review = reviews.get(proposal_id, {})
            decision = str(review.get("decision") or "PENDING_REVIEW").upper()
            if decision == "REJECTED":
                continue
            validation_status = str(
                validation.get("status") or review.get("validation_status") or "UNKNOWN"
            ).upper()
            priority = str(
                review.get("review_priority")
                or proposal.get("highest_priority")
                or action.get("priority")
                or "MEDIUM"
            )
            runtime = str(action.get("estimated_runtime") or action.get("runtime") or "—")
            rows.append(
                DirectorProposalRow(
                    proposal_id=proposal_id,
                    action_id=action_id,
                    title=str(action.get("title") or proposal.get("target_action_title") or proposal_id),
                    rationale=str(action.get("rationale") or "No rationale supplied."),
                    suggested_target=str(action.get("suggested_target") or "Not declared."),
                    done_when=str(action.get("done_when") or "Not declared."),
                    expected_gain=str(action.get("expected_gain") or "Not declared."),
                    priority=priority,
                    runtime=runtime,
                    validation_status=validation_status,
                    decision=decision,
                    resolution_type=(str(resolution.get("resolution_type")) if resolution.get("resolution_type") else None),
                    preferred_resolution=(
                        str(resolution.get("preferred_resolution") or review.get("preferred_resolution"))
                        if (resolution.get("preferred_resolution") or review.get("preferred_resolution"))
                        else None
                    ),
                    issue_count=int(validation.get("issue_count") or review.get("issue_count") or 0),
                    affected_principles=tuple(str(x) for x in proposal.get("affected_principles", []) if str(x)),
                    affected_signals=tuple(str(x) for x in proposal.get("affected_signals", []) if str(x)),
                    execution_readiness=(
                        str(action.get("execution_readiness"))
                        if action.get("execution_readiness") is not None
                        else None
                    ),
                    execution_readiness_reason=(
                        str(action.get("execution_readiness_reason"))
                        if action.get("execution_readiness_reason")
                        else None
                    ),
                )
            )

        status_order = {"READY": 6, "APPROVED": 5, "NEEDS REVIEW": 4, "BLOCKED": 3, "DEFERRED": 2}
        priority_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        rows.sort(
            key=lambda row: (
                status_order.get(row.ui_status, 0),
                priority_order.get(row.priority.upper(), 0),
                row.proposal_id,
            ),
            reverse=True,
        )
        return tuple(rows)


__all__ = ["JSONResearchDirectorProposalAdapter"]
