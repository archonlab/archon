"""OL2-QUEUE1 UI: durable campaign/recovery workflow over CONTROL1."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from Analyzer_next.execution.observer.shell2.control1.app import ObserverLauncher2ControlShell
from Analyzer_next.execution.observer.shell2.store import ShellRoute
from Analyzer_next.execution.observer.shell2.theme import palette_for

from .controller import ObserverQueueController
from .model import QueueItemStatus


class ObserverLauncher2QueueShell(ObserverLauncher2ControlShell):
    """Expose queue orchestration while CONTROL1 remains the sole process owner."""

    def __init__(
        self,
        root: tk.Tk,
        store,
        analysis_controller,
        telemetry_controller,
        control_controller,
        queue_controller: ObserverQueueController,
        *,
        animate: bool = False,
    ) -> None:
        self.queue_controller = queue_controller
        self._last_queue_revision = -1
        self.queue_tree: ttk.Treeview | None = None
        super().__init__(
            root,
            store,
            analysis_controller,
            telemetry_controller,
            control_controller,
            animate=animate,
        )
        root.title("ARCHON Observer Launcher 2.0 — QUEUE1")
        self.footer_hint.set(
            "QUEUE1 dispatches immutable reviewed runs sequentially through CONTROL1"
        )
        root.after(100, self._poll_queue)

    def _build_configuration_route(self) -> None:
        super()._build_configuration_route()
        if not hasattr(self, "control_launch_button"):
            return
        parent = self.control_launch_button.master
        self.queue_add_button = self._button(
            parent,
            "Add to Queue",
            self._enqueue_review,
        )
        self.queue_add_button.pack(side="right", padx=3, pady=7)
        self._refresh_queue_buttons()

    def _build_route_content(self) -> None:
        if (
            not getattr(self, "analysis_route_active", False)
            and self.snapshot.route is ShellRoute.QUEUE
        ):
            for child in self.workspace.winfo_children():
                child.destroy()
            self._build_queue_route()
            return
        super()._build_route_content()

    def _build_queue_route(self) -> None:
        root = self._frame(self.workspace, "surface.app")
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_rowconfigure(2, weight=1)
        root.grid_columnconfigure(0, weight=1)

        header = self._frame(root, "surface.card")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.queue_phase_label = self._label(
            header,
            "Queue IDLE",
            surface="surface.card",
            font=("TkDefaultFont", 16, "bold"),
        )
        self.queue_phase_label.pack(side="left", padx=14, pady=12)
        self.queue_counts_label = self._label(
            header,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        self.queue_counts_label.pack(side="left", padx=10)

        self.queue_start_button = self._button(
            header,
            "Start Queue",
            self._start_queue,
            kind="primary",
        )
        self.queue_start_button.pack(side="right", padx=(4, 12), pady=6)
        self.queue_stop_button = self._button(
            header,
            "Stop Queue",
            self._stop_queue,
            kind="danger",
        )
        self.queue_stop_button.pack(side="right", padx=4, pady=6)
        self.queue_add_current_button = self._button(
            header,
            "Add Reviewed Run",
            self._enqueue_review,
        )
        self.queue_add_current_button.pack(side="right", padx=4, pady=6)

        actions = self._frame(root, "surface.card")
        actions.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._label(
            actions,
            "Terminal rows stay visible. Waiting rows may be reordered, cancelled or cloned for retry.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=14, pady=9)

        self.queue_clear_button = self._button(
            actions,
            "Clear Queue",
            self._cancel_all_waiting,
        )
        self.queue_clear_button.pack(side="right", padx=(4, 12), pady=6)
        self.queue_retry_button = self._button(
            actions,
            "Retry Clone",
            self._retry_selected,
        )
        self.queue_retry_button.pack(side="right", padx=4, pady=6)
        self.queue_cancel_button = self._button(
            actions,
            "Cancel Selected",
            self._cancel_selected,
        )
        self.queue_cancel_button.pack(side="right", padx=4, pady=6)
        self.queue_down_button = self._button(
            actions,
            "↓",
            lambda: self._move_selected(1),
            width=2,
        )
        self.queue_down_button.pack(side="right", padx=2, pady=6)
        self.queue_up_button = self._button(
            actions,
            "↑",
            lambda: self._move_selected(-1),
            width=2,
        )
        self.queue_up_button.pack(side="right", padx=2, pady=6)

        panel = self._frame(root, "surface.card")
        panel.grid(row=2, column=0, sticky="nsew")
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        columns = (
            "position",
            "queue_id",
            "run_id",
            "world",
            "mode",
            "horizon",
            "status",
            "telemetry",
            "output",
        )
        tree = ttk.Treeview(
            panel,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="OL2.Treeview",
        )
        headings = {
            "position": "#",
            "queue_id": "Queue ID",
            "run_id": "Run ID",
            "world": "World",
            "mode": "Provenance / mode",
            "horizon": "Horizon",
            "status": "Status",
            "telemetry": "Telemetry run",
            "output": "Output folder",
        }
        widths = {
            "position": 45,
            "queue_id": 92,
            "run_id": 180,
            "world": 70,
            "mode": 130,
            "horizon": 90,
            "status": 135,
            "telemetry": 205,
            "output": 270,
        }
        for key in columns:
            tree.heading(key, text=headings[key])
            tree.column(
                key,
                width=widths[key],
                minwidth=45,
                anchor="w" if key in {"run_id", "mode", "telemetry", "output"} else "center",
            )
        vertical = ttk.Scrollbar(panel, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(panel, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 0))
        vertical.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=(8, 0))
        horizontal.grid(row=1, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))
        tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_queue_buttons())
        tree.bind("<Double-1>", lambda _event: self._show_selected_output())
        self.queue_tree = tree

        self.queue_error_label = self._label(
            panel,
            "",
            surface="surface.card",
            foreground="status.failed",
            font=("TkDefaultFont", 8),
        )
        self.queue_error_label.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))
        self._refresh_queue_route()

    def _current_prepared(self):
        review = self.config_store.config_snapshot.review
        if review is None or not review.valid or review.prepared is None:
            return None
        return review.prepared

    def _selected_queue_id(self) -> str | None:
        tree = self.queue_tree
        if tree is None:
            return None
        try:
            if not tree.winfo_exists():
                return None
        except tk.TclError:
            return None
        selection = tree.selection()
        return str(selection[0]) if selection else None

    def _selected_item(self):
        queue_id = self._selected_queue_id()
        if queue_id is None:
            return None
        return next(
            (item for item in self.queue_controller.snapshot.items if item.queue_id == queue_id),
            None,
        )

    def _enqueue_review(self) -> None:
        prepared = self._current_prepared()
        if prepared is None:
            self.footer_hint.set(
                "Queue add refused: Validate & Review must produce an immutable RunSpec first"
            )
            if hasattr(self, "config_notebook") and hasattr(self, "review_tab"):
                self.config_notebook.select(self.review_tab)
            return
        snapshot = self.queue_controller.enqueue(prepared)
        self.footer_hint.set(
            f"Queued rule {prepared.run_spec.rule_id:05d}; waiting={snapshot.waiting_count}"
        )
        self._refresh_queue_route()
        self._refresh_queue_buttons()

    def _launch_observer(self) -> None:
        prepared = self._current_prepared()
        if prepared is not None:
            decision = self.queue_controller.authorization.authorize(prepared)
            if not decision.authorized:
                self.footer_hint.set(
                    f"Direct launch blocked: {decision.code}: {decision.reason}"
                )
                if hasattr(self, "config_notebook") and hasattr(self, "review_tab"):
                    self.config_notebook.select(self.review_tab)
                return
        super()._launch_observer()

    def _start_queue(self) -> None:
        try:
            snapshot = self.queue_controller.start()
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Queue start refused: {exc}")
            self._refresh_queue_buttons()
            return
        if snapshot.blocked_queue_id:
            self.footer_hint.set(f"Queue blocked: {snapshot.last_error}")
            self.control_store.select_route(ShellRoute.QUEUE)
        else:
            self.analysis_route_active = False
            self.control_store.select_route(ShellRoute.OBSERVATION)
            self.footer_hint.set("Queue started; CONTROL1 owns exactly one Observer process")
        self._refresh_queue_buttons()

    def _stop_queue(self) -> None:
        snapshot = self.queue_controller.snapshot
        if not snapshot.dispatching and snapshot.active_queue_id is None:
            self.footer_hint.set("Queue stop refused: no active queue dispatch")
            self._refresh_queue_buttons()
            return
        try:
            self.queue_controller.stop()
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Queue stop failed: {exc}")
            self._refresh_queue_buttons()
            return
        self.footer_hint.set("Queue stop requested; waiting rows cancelled and retained")
        self._refresh_queue_route()
        self._refresh_queue_buttons()

    def _cancel_all_waiting(self) -> None:
        self.queue_controller.cancel_all_waiting()
        self.footer_hint.set("Clear Queue cancelled waiting rows; terminal rows remain visible")
        self._refresh_queue_route()
        self._refresh_queue_buttons()

    def _move_selected(self, direction: int) -> None:
        queue_id = self._selected_queue_id()
        if queue_id is None:
            self.footer_hint.set("Select a WAITING queue row first")
            return
        try:
            self.queue_controller.move_waiting(queue_id, direction)
        except (KeyError, RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Queue reorder refused: {exc}")
            return
        self._refresh_queue_route(select_queue_id=queue_id)
        self._refresh_queue_buttons()

    def _cancel_selected(self) -> None:
        queue_id = self._selected_queue_id()
        if queue_id is None:
            self.footer_hint.set("Select a WAITING queue row first")
            return
        try:
            self.queue_controller.cancel_waiting(queue_id)
        except (KeyError, RuntimeError) as exc:
            self.footer_hint.set(f"Queue cancel refused: {exc}")
            return
        self.footer_hint.set(f"{queue_id} cancelled before dispatch; row preserved")
        self._refresh_queue_route(select_queue_id=queue_id)
        self._refresh_queue_buttons()

    def _retry_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            self.footer_hint.set("Select a terminal queue row to retry")
            return
        try:
            snapshot = self.queue_controller.retry_by_clone(item.queue_id)
        except (KeyError, RuntimeError) as exc:
            self.footer_hint.set(f"Retry refused: {exc}")
            return
        clone = snapshot.items[-1]
        self.footer_hint.set(
            f"Retry clone {clone.queue_id} created from {item.queue_id}; original row unchanged"
        )
        self._refresh_queue_route(select_queue_id=clone.queue_id)
        self._refresh_queue_buttons()

    def _show_selected_output(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        if not item.status.terminal:
            self.footer_hint.set("Output path is immutable, but results are opened only from terminal rows")
            return
        self.footer_hint.set(f"Output: {item.prepared.run_spec.output_dir}")

    def _poll_queue(self) -> None:
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        snapshot = self.queue_controller.poll()
        # Arm the next orchestration poll before touching route-local widgets.
        # Starting Queue switches to Observation and destroys the Queue route;
        # presentation refresh must never suspend terminal reconciliation or
        # dispatch of the next WAITING row.
        self.root.after(100, self._poll_queue)
        if snapshot.revision != self._last_queue_revision:
            self._last_queue_revision = snapshot.revision
            self._refresh_queue_route()
            self._refresh_queue_buttons()

    def _refresh_queue_route(self, *, select_queue_id: str | None = None) -> None:
        snapshot = self.queue_controller.snapshot
        if hasattr(self, "queue_phase_label"):
            try:
                exists = bool(self.queue_phase_label.winfo_exists())
            except tk.TclError:
                exists = False
            if exists:
                self.queue_phase_label.configure(text=f"Queue {snapshot.phase.value}")
                self.queue_counts_label.configure(
                    text=(
                        f"{snapshot.running_count} running  •  {snapshot.waiting_count} waiting  •  "
                        f"{snapshot.completed_count} completed  •  {snapshot.failed_count} failed  •  "
                        f"{snapshot.cancelled_count} cancelled  •  {snapshot.recovery_count} recovery"
                    )
                )
                self.queue_error_label.configure(text=snapshot.last_error or "")
        tree = self.queue_tree
        if tree is None:
            return
        try:
            if not tree.winfo_exists():
                return
        except tk.TclError:
            return
        previous = select_queue_id or self._selected_queue_id()
        tree.delete(*tree.get_children())
        for position, item in enumerate(snapshot.items, 1):
            tree.insert(
                "",
                "end",
                iid=item.queue_id,
                values=(
                    position,
                    item.queue_id,
                    item.execution_id or "—",
                    f"{item.rule_id:05d}",
                    item.mode,
                    f"{item.prepared.run_spec.max_ticks:,}",
                    item.status.value,
                    item.telemetry_run_id or "—",
                    item.prepared.run_spec.output_dir,
                ),
                tags=(item.status.value,),
            )
        if previous and tree.exists(previous):
            tree.selection_set(previous)
            tree.focus(previous)
        self._theme_queue_tags()

    def _theme_queue_tags(self) -> None:
        tree = self.queue_tree
        if tree is None:
            return
        try:
            if not tree.winfo_exists():
                return
        except tk.TclError:
            return
        palette = palette_for(self.snapshot.resolved_theme)
        tree.tag_configure(QueueItemStatus.WAITING.value, foreground=palette["status.waiting"])
        tree.tag_configure(QueueItemStatus.RUNNING.value, foreground=palette["status.running"])
        tree.tag_configure(QueueItemStatus.COMPLETED.value, foreground=palette["status.running"])
        tree.tag_configure(QueueItemStatus.FAILED.value, foreground=palette["status.failed"])
        tree.tag_configure(QueueItemStatus.CANCELLED.value, foreground=palette["text.muted"])
        tree.tag_configure(QueueItemStatus.RECOVERY_REQUIRED.value, foreground=palette["status.failed"])

    def _refresh_queue_buttons(self) -> None:
        snapshot = self.queue_controller.snapshot
        prepared = self._current_prepared()
        selected = self._selected_item()
        control_active = self.control_controller.process_active
        can_start = snapshot.waiting_count > 0 and not snapshot.dispatching and not control_active
        can_stop = snapshot.dispatching or snapshot.active_queue_id is not None
        for name in ("queue_add_button", "queue_add_current_button"):
            self._configure_live_queue_widget(
                name,
                state="normal" if prepared is not None else "disabled",
            )
        self._configure_live_queue_widget(
            "queue_start_button",
            state="normal" if can_start else "disabled",
        )
        self._configure_live_queue_widget(
            "queue_stop_button",
            state="normal" if can_stop else "disabled",
        )
        self._configure_live_queue_widget(
            "queue_clear_button",
            state="normal" if snapshot.waiting_count else "disabled",
        )
        waiting_selected = bool(selected and selected.status is QueueItemStatus.WAITING)
        terminal_selected = bool(selected and selected.status.terminal)
        for name in ("queue_up_button", "queue_down_button", "queue_cancel_button"):
            self._configure_live_queue_widget(
                name,
                state="normal" if waiting_selected else "disabled",
            )
        self._configure_live_queue_widget(
            "queue_retry_button",
            state="normal" if terminal_selected else "disabled",
        )

    @staticmethod
    def _queue_widget_is_live(widget) -> bool:
        if widget is None:
            return False
        try:
            return bool(widget.winfo_exists())
        except (AttributeError, tk.TclError):
            return False

    def _configure_live_queue_widget(self, name: str, **options) -> bool:
        """Update route-local controls only while their Tk commands exist.

        Queue and CONTROL polling continue after the Queue route is replaced by
        Observation.  Tk destroys those buttons, but Python attributes retain
        the old widget objects until Queue is mounted again.
        """
        widget = getattr(self, name, None)
        if not self._queue_widget_is_live(widget):
            return False
        try:
            widget.configure(**options)
        except tk.TclError:
            return False
        return True

    def _refresh_control_buttons(self) -> None:
        super()._refresh_control_buttons()
        snapshot = self.queue_controller.snapshot
        prepared = self._current_prepared()
        direct_authorized = bool(
            prepared is not None
            and self.queue_controller.authorization.authorize(prepared).authorized
        )
        if not direct_authorized:
            self._configure_live_queue_widget("control_launch_button", state="disabled")
        if snapshot.dispatching:
            self._configure_live_queue_widget("control_launch_button", state="disabled")
            self._configure_live_queue_widget("stop_button", text="Stop Queue")
            self._configure_live_queue_widget("control_stop_config_button", text="Stop Queue")
        else:
            self._configure_live_queue_widget("stop_button", text="Stop")
            self._configure_live_queue_widget("control_stop_config_button", text="Stop Observer")
        self._refresh_queue_buttons()

    def _stop_observer(self) -> None:
        snapshot = self.queue_controller.snapshot
        if snapshot.dispatching or snapshot.active_queue_id is not None:
            self._stop_queue()
            return
        super()._stop_observer()

    def _new_run(self) -> None:
        snapshot = self.queue_controller.snapshot
        if snapshot.dispatching or snapshot.active_queue_id is not None:
            self.footer_hint.set("New run refused while QUEUE1 is dispatching")
            return
        super()._new_run()

    def _apply_theme(self) -> None:
        super()._apply_theme()
        self._theme_queue_tags()

    def _refresh_content(self) -> None:
        super()._refresh_content()
        self._refresh_queue_route()
        self._refresh_queue_buttons()
        if self.snapshot.route is ShellRoute.QUEUE:
            self.footer_right.configure(
                text="Observer QUEUE1  •  campaign recovery  •  no production cutover"
            )

    def close(self) -> None:
        """Close only after QUEUE1/CONTROL1 releases owned execution state."""
        try:
            clean = self.queue_controller.close()
        except Exception as exc:
            try:
                self.footer_hint.set(
                    f"Close refused: could not reconcile Observer ownership: {type(exc).__name__}: {exc}"
                )
            except Exception:
                pass
            return
        if not clean:
            try:
                self.footer_hint.set(
                    "Close refused: Observer process ownership is still unresolved; retry Stop/Close"
                )
            except Exception:
                pass
            return
        super().close()


__all__ = ["ObserverLauncher2QueueShell"]
