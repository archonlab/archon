"""Observer Queue integration for the BRIDGE5.8 authoritative lifecycle."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from Analyzer_next.execution.observer.shell2.queue1.model import retry_leaf_items
from Analyzer_next.research.cycle.authoritative_lifecycle import (
    AuthoritativeLifecycleError,
    AuthoritativeLifecyclePaths,
    canonical_hash,
    find_authoritative_cycle,
    transition_authoritative_cycle,
)


class ObserverAuthoritativeCycleError(RuntimeError):
    pass


def _context(item: Any) -> dict[str, Any]:
    try:
        value = item.prepared.run_spec.experimental_context
    except (AttributeError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _execution(item: Any) -> dict[str, Any]:
    value = _context(item).get("execution_attempt")
    return value if isinstance(value, dict) else {}


def _runtime_id(item: Any) -> str | None:
    execution = _execution(item)
    value = execution.get("source_runtime_id") or _context(item).get("runtime_id")
    return str(value or "").strip() or None


def _attempt_id(item: Any) -> str | None:
    return str(_execution(item).get("attempt_id") or "").strip() or None


def _attempt_receipt_path(item: Any) -> Path | None:
    runtime_id = _runtime_id(item)
    attempt_id = _attempt_id(item)
    try:
        output_dir = str(item.prepared.run_spec.output_dir or "").strip()
    except (AttributeError, TypeError, ValueError):
        return None
    if not runtime_id or not attempt_id or not output_dir:
        return None
    return (Path(output_dir).expanduser().resolve() / "ol2_execution_attempt.json")


def _status(item: Any) -> str:
    value = getattr(getattr(item, "status", None), "value", None)
    return str(value or getattr(item, "status", "")).upper()


class ObserverAuthoritativeCycleLifecycle:
    """Project aggregate Queue1 lifecycle into exactly one ResearchCycleRecord."""

    def __init__(self, project_root: Path, analysis_root: Path | None = None) -> None:
        root = Path(project_root).resolve()
        self.paths = AuthoritativeLifecyclePaths(
            project_root=root,
            analysis_root=Path(
                analysis_root or (root / "Results/Analysis")
            ).resolve(),
        )

    def _cycle_for_item(self, item: Any) -> dict[str, Any] | None:
        runtime_id = _runtime_id(item)
        if not runtime_id:
            return None
        return find_authoritative_cycle(self.paths, runtime_id=runtime_id)

    def _reference_for_attempt(self, item: Any, *, kind: str) -> dict[str, Any]:
        execution = _execution(item)
        attempt_id = _attempt_id(item) or str(getattr(item, "queue_id", "UNKNOWN"))
        path = _attempt_receipt_path(item)
        if path is not None and path.is_file():
            return {
                "kind": kind,
                "id": attempt_id,
                "path": str(path),
            }
        review_hash = str(getattr(getattr(item, "prepared", None), "review_hash", "") or "").strip()
        if not review_hash:
            try:
                review_hash = str(item.prepared.run_spec.content_hash or "").strip()
            except (AttributeError, TypeError, ValueError):
                review_hash = ""
        if not review_hash:
            raise ObserverAuthoritativeCycleError(
                f"queue item {getattr(item, 'queue_id', '?')} has no immutable preparation hash"
            )
        return {
            "kind": kind,
            "id": attempt_id,
            "receipt_hash": review_hash,
        }

    def mark_queued(self, items: Iterable[Any]) -> None:
        grouped: dict[str, list[Any]] = {}
        for item in items:
            runtime_id = _runtime_id(item)
            if runtime_id:
                grouped.setdefault(runtime_id, []).append(item)
        for runtime_id, rows in grouped.items():
            try:
                record = find_authoritative_cycle(self.paths, runtime_id=runtime_id)
                if record is None:
                    # Ad-hoc or legacy experimental rows stay outside the
                    # authoritative production-cycle contract.
                    continue
                state = str(record.get("lifecycle_state") or record.get("current_stage") or "")
                if state in {"QUEUED", "RUNNING", "OBSERVED", "ANALYZED", "EVIDENCE_UPDATED", "SCIENCE_REFRESHED", "DIRECTOR_REFRESHED", "CLOSED", "NON_DIAGNOSTIC"}:
                    continue
                if state != "MATERIALIZED":
                    raise ObserverAuthoritativeCycleError(
                        f"cycle {record.get('cycle_id')} cannot queue from {state}"
                    )
                queue_ids = sorted(str(getattr(item, "queue_id", "") or "") for item in rows)
                attempt_ids = sorted({value for value in (_attempt_id(item) for item in rows) if value})
                authorization_ids = sorted({
                    str(_execution(item).get("authorization_id") or "").strip()
                    for item in rows
                    if str(_execution(item).get("authorization_id") or "").strip()
                })
                if len(attempt_ids) != 1:
                    raise ObserverAuthoritativeCycleError(
                        f"runtime {runtime_id} queue rows do not share one attempt_id"
                    )
                if len(authorization_ids) != 1:
                    raise ObserverAuthoritativeCycleError(
                        f"runtime {runtime_id} queue rows do not share one authorization_id"
                    )
                transition_authoritative_cycle(
                    self.paths,
                    cycle_id=str(record["cycle_id"]),
                    to_state="QUEUED",
                    event_id=f"BRIDGE5.8:{record['cycle_id']}:QUEUED:{canonical_hash(queue_ids)[:16]}",
                    references=[
                        self._reference_for_attempt(item, kind="ExecutionAttemptReceipt")
                        for item in rows
                    ],
                    identity_updates={
                        "attempt_id": attempt_ids[0],
                        "authorization_id": authorization_ids[0],
                        "queue_ids": queue_ids,
                    },
                )
            except (AuthoritativeLifecycleError, ObserverAuthoritativeCycleError) as exc:
                raise ObserverAuthoritativeCycleError(str(exc)) from exc

    def mark_running(self, item: Any) -> None:
        try:
            record = self._cycle_for_item(item)
            if record is None:
                return
            state = str(record.get("lifecycle_state") or record.get("current_stage") or "")
            if state == "RUNNING":
                return
            if state != "QUEUED":
                raise ObserverAuthoritativeCycleError(
                    f"cycle {record.get('cycle_id')} cannot run from {state}"
                )
            transition_authoritative_cycle(
                self.paths,
                cycle_id=str(record["cycle_id"]),
                to_state="RUNNING",
                event_id=f"BRIDGE5.8:{record['cycle_id']}:RUNNING",
                references=[self._reference_for_attempt(item, kind="ObserverStartAuthorization")],
                identity_updates={"first_queue_id": str(getattr(item, "queue_id", "") or "")},
            )
        except (AuthoritativeLifecycleError, ObserverAuthoritativeCycleError) as exc:
            raise ObserverAuthoritativeCycleError(str(exc)) from exc

    def mark_launch_failure(self, item: Any, reason: str) -> None:
        try:
            record = self._cycle_for_item(item)
            if record is None:
                return
            state = str(record.get("lifecycle_state") or record.get("current_stage") or "")
            if state in {"FAILED", "CANCELLED", "BLOCKED"}:
                return
            transition_authoritative_cycle(
                self.paths,
                cycle_id=str(record["cycle_id"]),
                to_state="FAILED",
                event_id=f"BRIDGE5.8:{record['cycle_id']}:OBSERVER_LAUNCH_FAILED",
                references=[self._reference_for_attempt(item, kind="ObserverLaunchFailure")],
                reason=str(reason),
            )
        except (AuthoritativeLifecycleError, ObserverAuthoritativeCycleError) as exc:
            raise ObserverAuthoritativeCycleError(str(exc)) from exc

    def can_retry(self, item: Any) -> bool:
        """Return whether a Queue retry can remain inside this immutable cycle.

        A terminal ResearchCycleRecord is never reopened.  Startup recovery is
        intentionally left at RUNNING, so a recovery clone can still complete
        the same execution attempt without fabricating a new scientific cycle.
        """
        try:
            record = self._cycle_for_item(item)
        except Exception:
            return False
        if record is None:
            return True
        state = str(record.get("lifecycle_state") or record.get("current_stage") or "")
        return state not in {"BLOCKED", "FAILED", "CANCELLED", "CLOSED", "NON_DIAGNOSTIC"}

    def reconcile_terminal(self, items: Iterable[Any], *, runtime_id: str | None = None) -> None:
        rows = [item for item in items if _runtime_id(item)]
        runtime_ids = {runtime_id} if runtime_id else {_runtime_id(item) for item in rows}
        for rid in sorted(value for value in runtime_ids if value):
            group = [item for item in rows if _runtime_id(item) == rid]
            effective_group = list(retry_leaf_items(group))
            if not effective_group or any(
                _status(item) not in {"COMPLETED", "FAILED", "CANCELLED", "RECOVERY_REQUIRED"}
                for item in effective_group
            ):
                continue
            # RECOVERY_REQUIRED is a recoverable launcher-ownership loss, not a
            # scientific terminal result.  Keep the cycle at RUNNING until the
            # unresolved leaf is retried by clone.  The source row remains in
            # durable history and is superseded only by explicit retry lineage.
            if any(_status(item) == "RECOVERY_REQUIRED" for item in effective_group):
                continue
            try:
                record = find_authoritative_cycle(self.paths, runtime_id=rid)
                if record is None:
                    continue
                state = str(record.get("lifecycle_state") or record.get("current_stage") or "")
                if state in {"OBSERVED", "FAILED", "CANCELLED", "BLOCKED", "CLOSED", "NON_DIAGNOSTIC"}:
                    continue
                statuses = {_status(item) for item in effective_group}
                terminal_payload = [
                    {
                        "queue_id": str(getattr(item, "queue_id", "") or ""),
                        "status": _status(item),
                        "observer_run_id": str(getattr(item, "telemetry_run_id", "") or "") or None,
                        "exit_code": getattr(item, "exit_code", None),
                        "retry_of": str(getattr(item, "retry_of", "") or "") or None,
                    }
                    for item in effective_group
                ]
                terminal_hash = canonical_hash(terminal_payload)
                references = [
                    {
                        "kind": "ObserverQueueTerminalSet",
                        "id": rid,
                        "receipt_hash": terminal_hash,
                    }
                ]
                if "FAILED" in statuses:
                    target = "FAILED"
                    reason = "OBSERVER_RUN_FAILED"
                    scientific_result = None
                    updates = {}
                elif "RECOVERY_REQUIRED" in statuses:
                    target = "BLOCKED"
                    reason = "OBSERVER_RECOVERY_REQUIRED"
                    scientific_result = None
                    updates = {}
                elif "CANCELLED" in statuses:
                    target = "CANCELLED"
                    reason = "OBSERVER_RUN_CANCELLED"
                    scientific_result = None
                    updates = {}
                else:
                    observer_ids = sorted(
                        str(getattr(item, "telemetry_run_id", "") or "")
                        for item in effective_group
                        if getattr(item, "telemetry_run_id", None)
                    )
                    if len(observer_ids) != len(effective_group):
                        raise ObserverAuthoritativeCycleError(
                            f"runtime {rid} completed without telemetry_run_id coverage"
                        )
                    target = "OBSERVED"
                    reason = None
                    scientific_result = None
                    updates = {"observer_run_ids": observer_ids}
                transition_authoritative_cycle(
                    self.paths,
                    cycle_id=str(record["cycle_id"]),
                    to_state=target,
                    event_id=f"BRIDGE5.8:{record['cycle_id']}:{target}:{terminal_hash[:16]}",
                    references=references,
                    identity_updates=updates,
                    reason=reason,
                    scientific_result=scientific_result,
                )
            except (AuthoritativeLifecycleError, ObserverAuthoritativeCycleError) as exc:
                raise ObserverAuthoritativeCycleError(str(exc)) from exc


__all__ = [
    "ObserverAuthoritativeCycleError",
    "ObserverAuthoritativeCycleLifecycle",
]
