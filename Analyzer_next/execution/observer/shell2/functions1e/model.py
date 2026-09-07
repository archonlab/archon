"""OL2-FUNCTIONS1E Research Director proposal workflow value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DirectorProposalRow:
    proposal_id: str
    action_id: str
    title: str
    rationale: str
    suggested_target: str
    done_when: str
    expected_gain: str
    priority: str
    runtime: str
    validation_status: str
    decision: str
    resolution_type: str | None = None
    preferred_resolution: str | None = None
    issue_count: int = 0
    affected_principles: tuple[str, ...] = ()
    affected_signals: tuple[str, ...] = ()
    execution_readiness: str | None = None
    execution_readiness_reason: str | None = None

    @property
    def display_title(self) -> str:
        readiness = str(self.execution_readiness or "").upper()
        reason = str(self.execution_readiness_reason or "")
        if readiness == "NEEDS_REVISION" and "NON_DIAGNOSTIC" in reason.upper():
            prefix = "EXP-PERT-"
            target = self.action_id[len(prefix):] if self.action_id.startswith(prefix) else self.action_id
            return f"Revise non-diagnostic perturbation target for {target}"
        if readiness == "NEEDS_REVISION":
            return f"Revision required: {self.title}"
        return self.title

    @property
    def display_guidance(self) -> str:
        if self.execution_readiness_reason:
            return str(self.execution_readiness_reason)
        if self.preferred_resolution:
            return str(self.preferred_resolution)
        return "No additional Director guidance."

    @property
    def ui_status(self) -> str:
        decision = self.decision.upper()
        validation = self.validation_status.upper()
        if decision == "REJECTED":
            return "REJECTED"
        if decision == "DEFERRED":
            return "DEFERRED"
        if validation == "VALID":
            return "READY" if decision != "APPROVED" else "APPROVED"
        if validation == "CONFLICTING":
            return "NEEDS REVIEW"
        if validation == "BLOCKED":
            return "BLOCKED"
        return validation or "UNKNOWN"

    @property
    def can_prepare(self) -> bool:
        return self.validation_status.upper() == "VALID" and self.decision.upper() != "REJECTED"


@dataclass(frozen=True, slots=True)
class PreparedExperimentDraft:
    proposal_id: str
    action_id: str
    title: str
    rationale: str
    suggested_target: str
    done_when: str
    expected_gain: str
    priority: str
    runtime: str
    validation_status: str
    decision: str
    affected_principles: tuple[str, ...]
    affected_signals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProposalWorkflowSnapshot:
    proposals: tuple[DirectorProposalRow, ...] = ()
    selected_proposal_id: str | None = None
    prepared: PreparedExperimentDraft | None = None
    query: str = ""
    status_filter: str = "All"
    error: str | None = None
    revision: int = 0

    @property
    def selected(self) -> DirectorProposalRow | None:
        return next(
            (row for row in self.proposals if row.proposal_id == self.selected_proposal_id),
            None,
        )

    @property
    def visible_proposals(self) -> tuple[DirectorProposalRow, ...]:
        query = self.query.strip().casefold()
        status = self.status_filter.strip().casefold()
        rows = self.proposals
        if status and status != "all":
            rows = tuple(row for row in rows if row.ui_status.casefold() == status)
        if query:
            rows = tuple(
                row
                for row in rows
                if query in row.proposal_id.casefold()
                or query in row.action_id.casefold()
                or query in row.title.casefold()
                or query in row.display_title.casefold()
                or query in row.suggested_target.casefold()
                or query in row.rationale.casefold()
                or query in str(row.execution_readiness_reason or "").casefold()
            )
        return rows


__all__ = [
    "DirectorProposalRow",
    "PreparedExperimentDraft",
    "ProposalWorkflowSnapshot",
]
