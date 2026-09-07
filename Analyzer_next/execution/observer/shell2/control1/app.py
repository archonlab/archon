"""OL2-CONTROL1 UI extension: explicit real Observer start/stop."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from Analyzer_next.execution.observer.shell2.store import ShellRoute
from Analyzer_next.execution.observer.shell2.telem1.app import (
    ObserverLauncher2TelemetryShell,
)
from Analyzer_next.execution.observer.state import RunState, TelemetryState

from .controller import ObserverControlController
from .store import ControlShellStore


class ObserverLauncher2ControlShell(ObserverLauncher2TelemetryShell):
    """Attach explicit process ownership while preserving frozen earlier layers."""

    def __init__(
        self,
        root: tk.Tk,
        store: ControlShellStore,
        analysis_controller,
        telemetry_controller,
        control_controller: ObserverControlController,
        *,
        animate: bool = False,
    ) -> None:
        self.control_controller = control_controller
        self.control_store = store
        self._last_control_revision = -1
        self._last_elapsed = -1
        self._announced_telemetry_run_id: str | None = None
        self.control_console: tk.Text | None = None
        self._control_log: list[str] = []
        super().__init__(
            root,
            store,
            analysis_controller,
            telemetry_controller,
            animate=animate,
        )
        root.title("ARCHON Observer Launcher 2.0 — CONTROL1")
        self.footer_hint.set(
            "Observer execution is real only after explicit Launch Observer"
        )
        root.after(100, self._poll_control)

    def _walk(self, widget: tk.Misc):
        for child in widget.winfo_children():
            yield child
            yield from self._walk(child)

    def _build_navigation(self) -> None:
        super()._build_navigation()
        for widget in self._walk(self.navigation):
            if isinstance(widget, tk.Label):
                text = str(widget.cget("text") or "")
                if "SHELL1 fake store" in text:
                    widget.configure(
                        text="CONTROL1 process adapter\nExplicit user launch only"
                    )
        for button in self._nav_buttons.values():
            button.bind(
                "<Leave>",
                lambda _event: self.footer_hint.set(
                    "CONTROL1 is ready; Observer starts only from a validated review"
                ),
            )
        if hasattr(self, "analysis_nav_button"):
            self.analysis_nav_button.bind(
                "<Leave>",
                lambda _event: self.footer_hint.set(
                    "Analyzer and Observer have separate process ownership"
                ),
            )

    def _build_configuration_route(self) -> None:
        super()._build_configuration_route()
        if not hasattr(self, "config_notebook"):
            return
        self.execution_tab = self._frame(self.config_notebook, "surface.app")
        self.config_notebook.add(self.execution_tab, text="Execution")
        self._build_execution_tab()
        self._replace_config1_launch_button()

    def _replace_config1_launch_button(self) -> None:
        for widget in self._walk(self.workspace):
            if not isinstance(widget, tk.Button):
                continue
            if str(widget.cget("text")) != "Launch disabled in CONFIG1":
                continue
            parent = widget.master
            widget.pack_forget()
            self.control_launch_button = self._button(
                parent,
                "Launch Observer",
                self._launch_observer,
                kind="primary",
            )
            self.control_launch_button.pack(side="right", padx=3, pady=7)
            self.control_stop_config_button = self._button(
                parent,
                "Stop Observer",
                self._stop_observer,
                kind="danger",
            )
            self.control_stop_config_button.pack(side="right", padx=3, pady=7)
            break
        self._refresh_control_buttons()

    def _build_execution_tab(self) -> None:
        tab = self.execution_tab
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        status = self._frame(tab, "surface.card")
        status.grid(row=0, column=0, sticky="ew", pady=(4, 8))
        self.control_status_label = self._label(
            status,
            "Observer process idle",
            surface="surface.card",
            font=("TkDefaultFont", 11, "bold"),
        )
        self.control_status_label.pack(side="left", padx=14, pady=10)
        self.control_identity_label = self._label(
            status,
            "Telemetry identity: —",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkFixedFont", 8),
        )
        self.control_identity_label.pack(side="right", padx=14, pady=10)

        panel = self._frame(tab, "surface.card")
        panel.grid(row=1, column=0, sticky="nsew")
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        self._label(
            panel,
            "OBSERVER PROCESS CONSOLE",
            surface="surface.card",
            foreground="text.muted",
            font=("TkDefaultFont", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))
        console_frame = self._frame(panel, "surface.elevated")
        console_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        console_frame.grid_rowconfigure(0, weight=1)
        console_frame.grid_columnconfigure(0, weight=1)
        self.control_console = tk.Text(
            console_frame,
            wrap="none",
            borderwidth=0,
            highlightthickness=1,
            padx=10,
            pady=10,
            font=("TkFixedFont", 9),
            state="disabled",
        )
        self._register(
            self.control_console,
            background="surface.canvas",
            foreground="text.primary",
            highlightbackground="border.default",
            highlightcolor="focus.ring",
            insertbackground="text.primary",
            selectbackground="action.primary",
            selectforeground="text.inverse",
        )
        vertical = ttk.Scrollbar(
            console_frame,
            orient="vertical",
            command=self.control_console.yview,
        )
        horizontal = ttk.Scrollbar(
            console_frame,
            orient="horizontal",
            command=self.control_console.xview,
        )
        self.control_console.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        if self._control_log:
            self.control_console.configure(state="normal")
            self.control_console.insert("1.0", "".join(self._control_log))
            self.control_console.configure(state="disabled")
        self.control_console.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self._refresh_control_status()

    def _build_observation(self) -> None:
        super()._build_observation()
        self.pause_button.configure(
            text="Pause unavailable",
            command=lambda: None,
            state="disabled",
        )
        self.stop_button.configure(command=self._stop_observer)
        self.new_run_button.configure(command=self._new_run)
        self.more_button.configure(
            command=lambda: self.footer_hint.set(
                "Process identity and canonical telemetry run identity are intentionally separate"
            )
        )

    def _launch_observer(self) -> None:
        review = self.config_store.config_snapshot.review
        if review is None or not review.valid or review.prepared is None:
            self.footer_hint.set(
                "Launch refused: Validate & Review must produce an immutable RunSpec first"
            )
            if hasattr(self, "config_notebook") and hasattr(self, "review_tab"):
                self.config_notebook.select(self.review_tab)
            return
        try:
            snapshot = self.control_controller.start(review.prepared)
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Observer start refused: {exc}")
            self._refresh_control_status()
            return
        self.control_store.sync_control(
            snapshot,
            elapsed_seconds=self.control_controller.elapsed_seconds,
        )
        self.analysis_route_active = False
        self.control_store.select_route(ShellRoute.OBSERVATION)
        self._announced_telemetry_run_id = None
        self.footer_hint.set("Observer launched; awaiting canonical telemetry run identity")
        self._refresh_control_status()

    def _stop_observer(self) -> None:
        try:
            snapshot = self.control_controller.stop()
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Observer stop refused: {exc}")
            self._refresh_control_status()
            return
        self.control_store.sync_control(
            snapshot,
            elapsed_seconds=self.control_controller.elapsed_seconds,
        )
        self.footer_hint.set("Stop requested for Observer process group")
        self._refresh_control_status()

    def _new_run(self) -> None:
        if self.control_controller.process_active:
            self.footer_hint.set("New run refused while Observer process is active")
            return
        self.control_store.new_run()
        self.footer_hint.set("Ready for a new validated Observer run")

    def _request_stop(self) -> None:
        self._stop_observer()

    def _shortcut_pause(self, _event: tk.Event) -> str:
        self.footer_hint.set("Pause/resume is not supported by CONTROL1")
        return "break"

    def _append_control_output(self, chunks: tuple[str, ...]) -> None:
        if not chunks:
            return
        self._control_log.extend(chunks)
        if len(self._control_log) > 20_000:
            self._control_log = self._control_log[-18_000:]
        if self.control_console is None:
            return
        try:
            if not self.control_console.winfo_exists():
                return
        except tk.TclError:
            return
        self.control_console.configure(state="normal")
        self.control_console.insert("end", "".join(chunks))
        line_count = int(self.control_console.index("end-1c").split(".")[0])
        if line_count > 20_000:
            self.control_console.delete("1.0", f"{line_count - 18_000}.0")
        self.control_console.see("end")
        self.control_console.configure(state="disabled")

    def _poll_control(self) -> None:
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        chunks = self.control_controller.drain_output()
        self._append_control_output(chunks)
        snapshot = self.control_controller.snapshot
        telemetry_run_id = snapshot.telemetry_run_id
        if (
            telemetry_run_id
            and telemetry_run_id != self._announced_telemetry_run_id
        ):
            self._announced_telemetry_run_id = telemetry_run_id
            self.footer_hint.set(f"Telemetry connected: {telemetry_run_id}")
        elapsed = self.control_controller.elapsed_seconds
        if (
            snapshot.run is not None
            and (
                snapshot.revision != self._last_control_revision
                or elapsed != self._last_elapsed
            )
        ):
            self._last_control_revision = snapshot.revision
            self._last_elapsed = elapsed
            self.control_store.sync_control(snapshot, elapsed_seconds=elapsed)
        # Route changes replace Tk controls. Keep process-state polling armed
        # independently of presentation refresh so a stale route widget cannot
        # leave a completed Observer displayed as RUNNING.
        self.root.after(100, self._poll_control)
        self._refresh_control_status()

    def _poll_live_telemetry(self) -> None:
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        telemetry_run_id = self.control_controller.snapshot.telemetry_run_id
        if self._metric_rail_mode().value != "hidden":
            if telemetry_run_id:
                self.live_poll = self.telemetry_controller.poll(telemetry_run_id)
                latest = (
                    self.live_poll.frame.latest
                    if self.live_poll.frame is not None
                    else None
                )
                self.control_store.sync_telemetry(
                    state=self.live_poll.state,
                    run_id=telemetry_run_id,
                    tick=latest.tick if latest is not None else None,
                    error=self.live_poll.error,
                )
                self._render_live_telemetry()
            else:
                self.live_poll = None
                self._render_live_telemetry()
                if hasattr(self, "footer_right"):
                    state = (
                        self.control_controller.snapshot.run.state.value
                        if self.control_controller.snapshot.run is not None
                        else "IDLE"
                    )
                    self.footer_right.configure(
                        text=f"Observer {state}  •  awaiting canonical telemetry identity"
                    )
        self.root.after(500, self._poll_live_telemetry)


    def _on_resize(self, event: tk.Event) -> None:
        if hasattr(self, "analysis_nav_button"):
            try:
                if not self.analysis_nav_button.winfo_exists():
                    return
            except tk.TclError:
                return
        super()._on_resize(event)

    def _refresh_control_status(self) -> None:
        snapshot = self.control_controller.snapshot
        if hasattr(self, "control_status_label"):
            try:
                exists = bool(self.control_status_label.winfo_exists())
            except tk.TclError:
                exists = False
            if exists:
                state = snapshot.run.state.value if snapshot.run else "IDLE"
                pid = snapshot.run.process_identity if snapshot.run else None
                suffix = f"  •  {pid}" if pid else ""
                self.control_status_label.configure(text=f"Observer {state}{suffix}")
                self.control_identity_label.configure(
                    text=f"Telemetry identity: {snapshot.telemetry_run_id or '—'}"
                )
        self._refresh_control_buttons()

    def _refresh_control_buttons(self) -> None:
        snapshot = self.control_controller.snapshot
        active = self.control_controller.process_active
        review = self.config_store.config_snapshot.review
        ready = bool(review and review.valid and review.prepared is not None)
        self._configure_live_control_widget(
            "control_launch_button",
            state="normal" if ready and not active else "disabled",
        )
        self._configure_live_control_widget(
            "control_stop_config_button",
            state="normal" if active and snapshot.active else "disabled",
        )
        self._configure_live_control_widget(
            "pause_button", state="disabled", text="Pause unavailable"
        )
        self._configure_live_control_widget(
            "stop_button",
            state="normal" if active and snapshot.active else "disabled",
        )
        terminal = bool(
            snapshot.run
            and snapshot.run.state
            in {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}
        )
        self._configure_live_control_widget(
            "new_run_button",
            state="normal" if terminal and not active else "disabled",
        )

    @staticmethod
    def _control_widget_is_live(widget) -> bool:
        if widget is None:
            return False
        try:
            return bool(widget.winfo_exists())
        except (AttributeError, tk.TclError):
            return False

    def _configure_live_control_widget(self, name: str, **options) -> bool:
        """Configure controls only while their current Tk route still exists."""
        widget = getattr(self, name, None)
        if not self._control_widget_is_live(widget):
            return False
        try:
            widget.configure(**options)
        except tk.TclError:
            return False
        return True

    def _refresh_content(self) -> None:
        super()._refresh_content()
        self._refresh_control_buttons()
        if self.snapshot.route is not ShellRoute.OBSERVATION:
            self.footer_right.configure(
                text="Observer CONTROL1  •  explicit real launch  •  no production cutover"
            )

    def close(self) -> None:
        self.control_controller.close()
        super().close()


__all__ = ["ObserverLauncher2ControlShell"]
