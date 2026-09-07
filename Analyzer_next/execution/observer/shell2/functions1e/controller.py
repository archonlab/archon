"""Toolkit/storage-independent proposal workflow controller for OL2-FUNCTIONS1E."""
from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .model import DirectorProposalRow, PreparedExperimentDraft, ProposalWorkflowSnapshot


class DirectorProposalPort(Protocol):
    def list_proposals(self) -> tuple[DirectorProposalRow, ...]: ...


class ProposalWorkflowController:
    def __init__(self, port: DirectorProposalPort) -> None:
        self.port = port
        self._snapshot = ProposalWorkflowSnapshot()

    @property
    def snapshot(self) -> ProposalWorkflowSnapshot:
        return self._snapshot

    def _publish(self, **changes) -> ProposalWorkflowSnapshot:
        self._snapshot = replace(
            self._snapshot,
            **changes,
            revision=self._snapshot.revision + 1,
        )
        return self._snapshot

    def refresh(self) -> ProposalWorkflowSnapshot:
        try:
            proposals = self.port.list_proposals()
        except Exception as exc:
            return self._publish(error=f"{type(exc).__name__}: {exc}")
        selected = self._snapshot.selected_proposal_id
        ids = {row.proposal_id for row in proposals}
        if selected not in ids:
            selected = proposals[0].proposal_id if proposals else None
        prepared = self._snapshot.prepared
        if prepared is not None and prepared.proposal_id not in ids:
            prepared = None
        return self._publish(
            proposals=proposals,
            selected_proposal_id=selected,
            prepared=prepared,
            error=None,
        )

    def set_filters(self, *, query: str | None = None, status: str | None = None) -> ProposalWorkflowSnapshot:
        changes = {}
        if query is not None:
            changes["query"] = str(query)
        if status is not None:
            changes["status_filter"] = str(status)
        return self._publish(**changes)

    def select(self, proposal_id: str) -> ProposalWorkflowSnapshot:
        proposal_id = str(proposal_id).strip()
        if proposal_id not in {row.proposal_id for row in self._snapshot.proposals}:
            raise ValueError(f"unknown proposal_id: {proposal_id}")
        return self._publish(selected_proposal_id=proposal_id)

    def prepare_selected(self) -> ProposalWorkflowSnapshot:
        row = self._snapshot.selected
        if row is None:
            raise ValueError("select a Research Director proposal first")
        if not row.can_prepare:
            raise ValueError(
                f"proposal {row.proposal_id} is {row.ui_status}; only VALID proposals can be prepared"
            )
        draft = PreparedExperimentDraft(
            proposal_id=row.proposal_id,
            action_id=row.action_id,
            title=row.title,
            rationale=row.rationale,
            suggested_target=row.suggested_target,
            done_when=row.done_when,
            expected_gain=row.expected_gain,
            priority=row.priority,
            runtime=row.runtime,
            validation_status=row.validation_status,
            decision=row.decision,
            affected_principles=row.affected_principles,
            affected_signals=row.affected_signals,
        )
        return self._publish(prepared=draft)

    def clear_prepared(self) -> ProposalWorkflowSnapshot:
        return self._publish(prepared=None)


__all__ = ["DirectorProposalPort", "ProposalWorkflowController"]
