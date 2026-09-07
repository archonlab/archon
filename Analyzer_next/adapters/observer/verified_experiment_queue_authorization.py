"""QUEUE1 authorization adapter that recognizes VERIFIED Stage 6.5 receipts."""
from __future__ import annotations

from Analyzer_next.execution.observer.shell2.config1.model import PreparedConfiguration
from Analyzer_next.execution.observer.shell2.queue1.contracts import (
    FailClosedQueueAuthorization,
    QueueAuthorizationDecision,
)

from .experiment_runtime_handoff import AuditedExperimentRuntimeHandoff


class VerifiedExperimentQueueAuthorization:
    """Keep manual QUEUE1 policy and add durable verification for experiments."""

    def __init__(self, handoff: AuditedExperimentRuntimeHandoff) -> None:
        self.handoff = handoff
        self.fallback = FailClosedQueueAuthorization()

    def authorize(self, prepared: PreparedConfiguration) -> QueueAuthorizationDecision:
        if prepared.run_spec.mode != "experimental":
            return self.fallback.authorize(prepared)
        try:
            authorized, code, reason = self.handoff.verify_prepared_authorization(prepared)
        except Exception as exc:
            return QueueAuthorizationDecision(
                authorized=False,
                code="EXPERIMENT_AUTHORIZATION_VERIFICATION_ERROR",
                reason=f"{type(exc).__name__}: {exc}",
            )
        return QueueAuthorizationDecision(
            authorized=bool(authorized),
            code=str(code),
            reason=str(reason),
        )


__all__ = ["VerifiedExperimentQueueAuthorization"]
