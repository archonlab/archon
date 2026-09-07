"""BRIDGE5.7 Queue-finished to Analyzer scientific-refresh handoff."""
from __future__ import annotations

from Analyzer_next.adapters.observer.automatic_scientific_refresh import (
    BLOCKED,
    COMPLETED,
    FAILED,
    RUNNING,
    AutomaticScientificRefreshHandoff,
    automatic_refresh_rows_from_queue,
    completed_refresh_run_ids,
)
from Analyzer_next.execution.observer.shell2.queue1.model import (
    QueueItemStatus,
    QueuePhase,
    retry_leaf_items,
)
from Analyzer_next.execution.observer.shell2.theme import palette_for
from Analyzer_next.execution.observer.shell2.vis1.app import (
    ObserverLauncher2VisShell,
)


MANUAL_FULL_ANALYSIS = "FULL_ANALYSIS"
MANUAL_SCIENTIFIC_REFRESH = "SCIENTIFIC_REFRESH"
MANUAL_ANALYSIS_BLOCKED = "BLOCKED"


def manual_post_run_analysis_route(
    *,
    queue_phase: QueuePhase,
    pending_refresh_rows: int,
    automatic_state: str,
    experimental_queue_active: bool = False,
) -> str:
    """Choose one fail-closed Analyze Results route.

    A finished experimental Queue with uncovered completed runs must converge on
    the exact BRIDGE5.7 durable refresh path.  It must never race a full Analyzer
    process or interpret a partially completed experimental Queue.
    """
    if automatic_state == RUNNING or experimental_queue_active:
        return MANUAL_ANALYSIS_BLOCKED
    if pending_refresh_rows > 0:
        if queue_phase is QueuePhase.FINISHED:
            return MANUAL_SCIENTIFIC_REFRESH
        return MANUAL_ANALYSIS_BLOCKED
    return MANUAL_FULL_ANALYSIS


class ObserverLauncher2ScientificRefreshShell(ObserverLauncher2VisShell):
    """Observe QUEUE1 terminal transitions without changing Queue ownership."""

    def __init__(
        self,
        *args,
        automatic_refresh_handoff: AutomaticScientificRefreshHandoff,
        **kwargs,
    ) -> None:
        self.automatic_refresh_handoff = automatic_refresh_handoff
        self._last_automatic_queue_revision = -1
        self._last_automatic_handoff_revision = -1
        super().__init__(*args, **kwargs)
        # Installation must not reinterpret an already-terminal historical
        # Queue merely because OL2 restarted.  Only a revision produced after
        # this shell begins observing can trigger BRIDGE5.7.
        self._last_automatic_queue_revision = self.queue_controller.snapshot.revision
        self._last_automatic_handoff_revision = self.automatic_refresh_handoff.snapshot.revision
        self.root.title("ARCHON Observer Launcher 2.0 — SCIENTIFIC REFRESH1")


    @staticmethod
    def _experimental_queue_active(items) -> bool:
        for item in retry_leaf_items(items):
            try:
                context = item.prepared.run_spec.experimental_context
            except (AttributeError, TypeError, ValueError):
                continue
            if not isinstance(context, dict) or not context.get("experiment_id"):
                continue
            status = getattr(item, "status", None)
            if (
                status is QueueItemStatus.RECOVERY_REQUIRED
                or not bool(getattr(status, "terminal", False))
            ):
                return True
        return False

    def _pending_manual_refresh_rows(self):
        snapshot = self.queue_controller.snapshot
        return automatic_refresh_rows_from_queue(
            snapshot.items,
            covered_run_ids=completed_refresh_run_ids(
                self.automatic_refresh_handoff.paths
            ),
        )

    def _write_analysis_notice(self, text: str) -> None:
        if not self.analysis_route_active:
            return
        if not hasattr(self, "analysis_console"):
            return
        try:
            if not self.analysis_console.winfo_exists():
                return
        except Exception:
            return
        self.analysis_console.configure(state="normal")
        self.analysis_console.insert("end", text.rstrip() + "\n")
        self.analysis_console.see("end")
        self.analysis_console.configure(state="disabled")

    def _start_analysis(self) -> None:
        """Converge manual post-run analysis on BRIDGE5.7 when required."""
        queue = self.queue_controller.snapshot
        pending = self._pending_manual_refresh_rows()
        route = manual_post_run_analysis_route(
            queue_phase=queue.phase,
            pending_refresh_rows=len(pending),
            automatic_state=self.automatic_refresh_handoff.snapshot.state,
            experimental_queue_active=self._experimental_queue_active(queue.items),
        )
        if route == MANUAL_ANALYSIS_BLOCKED:
            if self.automatic_refresh_handoff.snapshot.state == RUNNING:
                message = (
                    "Analyze Results is already covered by the active BRIDGE5.7 "
                    "scientific refresh; a second Analyzer process was not started."
                )
            else:
                message = (
                    "Analyze Results is blocked while an experimental Queue is still "
                    "active or has uncovered completed runs before FINISHED; partial "
                    "experimental interpretation is not allowed."
                )
            self.footer_hint.set(message)
            self._write_analysis_notice("[parity] " + message)
            return
        if route == MANUAL_SCIENTIFIC_REFRESH:
            handoff = self.automatic_refresh_handoff.schedule_queue_items(queue.items)
            if handoff is None:
                message = (
                    "BRIDGE5.7 coverage changed before manual dispatch; no duplicate "
                    "Analyzer process was started. Press Start Analysis again for a "
                    "separate full technical rerun if desired."
                )
            else:
                message = handoff.message or (
                    f"Manual Analyze Results routed to BRIDGE5.7 scientific refresh "
                    f"{handoff.refresh_id}."
                )
            self.footer_hint.set(message)
            self._write_analysis_notice(
                "[parity] Manual post-run Analyze Results uses the same durable "
                "BRIDGE5.7 intake → scientific-refresh → attested-receipt path as "
                "automatic Queue completion."
            )
            if handoff is not None:
                self._write_analysis_notice(
                    f"[parity] refresh_id={handoff.refresh_id} "
                    f"request={handoff.request_path or '—'} "
                    f"receipt={handoff.receipt_path or '—'} "
                    f"log={handoff.log_path or '—'}"
                )
            self._refresh_automatic_handoff_status()
            self._refresh_analysis_status()
            return
        super()._start_analysis()

    def _refresh_analysis_status(self) -> None:
        super()._refresh_analysis_status()
        if not self.analysis_route_active:
            return
        handoff = self.automatic_refresh_handoff.snapshot
        if handoff.state != RUNNING:
            return
        try:
            if not self.analysis_status_label.winfo_exists():
                return
        except Exception:
            return
        palette = palette_for(self.snapshot.resolved_theme)
        self.analysis_status_label.configure(
            text="●  Scientific Refresh",
            foreground=palette["status.running"],
        )
        self.analysis_attempt_label.configure(
            text=f"BRIDGE5.7  ·  {handoff.refresh_id or 'active'}"
        )
        self.analysis_start_button.configure(state="disabled")
        self.analysis_stop_button.configure(state="disabled")

    def _poll_queue(self) -> None:
        """Let QUEUE1 advance, then react to its immutable FINISHED snapshot."""
        super()._poll_queue()
        snapshot = self.queue_controller.snapshot
        if (
            snapshot.phase is QueuePhase.FINISHED
            and snapshot.revision != self._last_automatic_queue_revision
        ):
            if self.analysis_controller.record.active:
                self.footer_hint.set(
                    "Queue finished • BRIDGE5.7 scientific refresh is waiting for "
                    "the manually started Analyzer process to finish"
                )
            else:
                self._last_automatic_queue_revision = snapshot.revision
                self.automatic_refresh_handoff.schedule_queue_items(snapshot.items)
        self._refresh_automatic_handoff_status()

    def _refresh_automatic_handoff_status(self) -> None:
        handoff = self.automatic_refresh_handoff.snapshot
        if handoff.revision == self._last_automatic_handoff_revision:
            return
        self._last_automatic_handoff_revision = handoff.revision
        if handoff.state == RUNNING:
            self.footer_hint.set(
                f"Queue finished • scientific refresh {handoff.refresh_id} is running"
            )
        elif handoff.state == COMPLETED:
            self.footer_hint.set(
                f"Scientific refresh {handoff.refresh_id} completed • Director products attested"
            )
        elif handoff.state in {FAILED, BLOCKED}:
            self.footer_hint.set(handoff.message)

    def _refresh_content(self) -> None:
        super()._refresh_content()
        if self.snapshot.route.value == "queue":
            self.footer_right.configure(
                text="Observer QUEUE1  •  automatic scientific refresh  •  BRIDGE5.7"
            )


__all__ = [
    "MANUAL_ANALYSIS_BLOCKED",
    "MANUAL_FULL_ANALYSIS",
    "MANUAL_SCIENTIFIC_REFRESH",
    "ObserverLauncher2ScientificRefreshShell",
    "manual_post_run_analysis_route",
]
