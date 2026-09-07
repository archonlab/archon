"""OL2-QUEUE2: useful cleanup controls and explicit save-policy visibility."""
from __future__ import annotations

from Analyzer_next.execution.observer.shell2.campaigns1.app import ObserverLauncher2CampaignsShell
from Analyzer_next.execution.observer.shell2.queue1.model import QueueItemStatus
from .controller import ObserverQueue2Controller


class ObserverLauncher2Queue2Shell(ObserverLauncher2CampaignsShell):
    """Keep QUEUE1 dispatch frozen while making terminal queue controls useful."""

    def __init__(self, root, *args, **kwargs):
        queue_controller = kwargs.get("queue_controller")
        if queue_controller is None and len(args) >= 5:
            queue_controller = args[4]
        if not isinstance(queue_controller, ObserverQueue2Controller):
            raise TypeError("QUEUE2 requires ObserverQueue2Controller")
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — QUEUE2")

    def _build_queue_route(self) -> None:
        super()._build_queue_route()
        clear_button = getattr(self, "queue_clear_button", None)
        if clear_button is not None:
            self.queue_clear_completed_button = self._button(
                clear_button.master,
                "Clear Completed",
                self._clear_completed,
            )
            self.queue_clear_completed_button.pack(
                side="right", padx=4, pady=6, before=clear_button
            )
        tree = getattr(self, "queue_tree", None)
        if tree is not None:
            try:
                tree.heading("horizon", text="Horizon / autosave")
            except Exception:
                pass
        self._refresh_queue_route()
        self._refresh_queue_buttons()

    def _clear_completed(self) -> None:
        before = self.queue_controller.snapshot.completed_count
        self.queue_controller.clear_completed()
        self.footer_hint.set(
            f"Cleared {before} completed Queue row(s) from the active view; durable history retained"
        )
        self._refresh_queue_route()
        self._refresh_queue_buttons()

    def _refresh_queue_route(self, *, select_queue_id: str | None = None) -> None:
        super()._refresh_queue_route(select_queue_id=select_queue_id)
        tree = getattr(self, "queue_tree", None)
        if tree is None:
            return
        for item in self.queue_controller.snapshot.items:
            try:
                if not tree.exists(item.queue_id):
                    continue
                autosave = int(item.prepared.effective_draft.autosave_every)
                policy = "off" if autosave == 0 else f"{autosave:,}"
                final = " + final" if item.prepared.run_spec.max_ticks > 0 else ""
                tree.set(
                    item.queue_id,
                    "horizon",
                    f"{item.prepared.run_spec.max_ticks:,} / {policy}{final}",
                )
            except Exception:
                continue

    def _cancel_all_waiting(self) -> None:
        before = self.queue_controller.snapshot
        self.queue_controller.clear_queue_view()
        if before.active_queue_id is not None:
            self.footer_hint.set(
                "Queue cleared: WAITING rows cancelled and finished rows removed from view; active run preserved. Durable history retained."
            )
        else:
            self.footer_hint.set(
                "Queue cleared from active view. Completed/cancelled history remains in the durable Queue journal."
            )
        self._refresh_queue_route()
        self._refresh_queue_buttons()

    def _cancel_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            self.footer_hint.set("Select a queue row first")
            return
        try:
            if item.status is QueueItemStatus.WAITING:
                self.queue_controller.cancel_waiting(item.queue_id)
                self.footer_hint.set(
                    f"{item.queue_id} cancelled before dispatch; durable terminal history recorded"
                )
                self._refresh_queue_route(select_queue_id=item.queue_id)
            elif item.status.terminal:
                self.queue_controller.remove_terminal(item.queue_id)
                self.footer_hint.set(
                    f"{item.queue_id} removed from active Queue view; durable history retained"
                )
                self._refresh_queue_route()
            else:
                self.footer_hint.set("A RUNNING row is controlled by Stop Queue")
                return
        except (KeyError, RuntimeError) as exc:
            self.footer_hint.set(f"Queue action refused: {exc}")
            return
        self._refresh_queue_buttons()

    def _refresh_queue_buttons(self) -> None:
        super()._refresh_queue_buttons()
        snapshot = self.queue_controller.snapshot
        selected = self._selected_item()
        self._configure_live_queue_widget(
            "queue_clear_button",
            state="normal" if snapshot.items else "disabled",
        )
        self._configure_live_queue_widget(
            "queue_clear_completed_button",
            state="normal" if snapshot.completed_count else "disabled",
        )
        waiting = bool(selected and selected.status is QueueItemStatus.WAITING)
        terminal = bool(
            selected
            and selected.status.terminal
            and selected.status is not QueueItemStatus.RECOVERY_REQUIRED
        )
        unresolved_recovery = bool(
            selected
            and selected.status is QueueItemStatus.RECOVERY_REQUIRED
            and not any(
                row.retry_of == selected.queue_id
                for row in snapshot.items
            )
        )
        if unresolved_recovery:
            self._configure_live_queue_widget(
                "queue_cancel_button",
                text="Recovery Required",
                state="disabled",
            )
        else:
            self._configure_live_queue_widget(
                "queue_cancel_button",
                text=("Remove Selected" if terminal else "Cancel Selected"),
                state="normal" if (waiting or terminal) else "disabled",
            )


__all__ = ["ObserverLauncher2Queue2Shell"]
