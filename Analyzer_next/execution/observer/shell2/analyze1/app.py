"""Tk Analyze Results extension for the CONFIG1 preview shell."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from Analyzer_next.execution.observer.shell2.config1.app import ObserverLauncher2ConfigShell
from Analyzer_next.execution.observer.shell2.store import ShellRoute, ShellSnapshot
from Analyzer_next.execution.observer.shell2.theme import palette_for
from Analyzer_next.execution.observer.shell2.view_model import ROUTES

from .controller import AnalysisController
from .model import AnalysisState


class ObserverLauncher2AnalyzeShell(ObserverLauncher2ConfigShell):
    """Add one real, fixed Analyzer handoff while Observer remains fake-only."""

    def __init__(
        self,
        root: tk.Tk,
        store,
        controller: AnalysisController,
        *,
        animate: bool = False,
    ) -> None:
        self.analysis_controller = controller
        self.analysis_route_active = False
        super().__init__(root, store, animate=animate)
        root.title("ARCHON Observer Launcher 2.0 — ANALYZE1")
        self.footer_hint.set("Analyzer handoff is ready; Observer backend remains fake-only")
        root.after(100, self._poll_analysis)

    def _build_navigation(self) -> None:
        super()._build_navigation()
        for descriptor in ROUTES:
            self._nav_buttons[descriptor.route].configure(
                command=lambda route=descriptor.route: self._select_base_route(route)
            )
        self.settings_button.configure(
            command=lambda: self._select_base_route(ShellRoute.SETTINGS)
        )

        settings = self._nav_buttons[ShellRoute.SETTINGS]
        settings.grid_configure(row=9)
        self.analysis_nav_button = self._button(
            self.navigation,
            "A   Analyze Results",
            self._open_analysis_results,
        )
        self.analysis_nav_button.configure(
            anchor="w",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.analysis_nav_button.grid(row=8, column=0, sticky="ew", padx=8, pady=3)
        self.analysis_nav_button.bind(
            "<Enter>",
            lambda _event: self.footer_hint.set("Open live Analyzer console"),
        )
        self.analysis_nav_button.bind(
            "<Leave>",
            lambda _event: self.footer_hint.set(
                "Analyzer handoff is ready; Observer backend remains fake-only"
            ),
        )

        for widget in self.navigation.grid_slaves(row=10):
            widget.grid_configure(row=11)
        self.navigation.grid_rowconfigure(9, weight=0)
        self.navigation.grid_rowconfigure(10, weight=1)

    def _select_base_route(self, route: ShellRoute) -> None:
        self.analysis_route_active = False
        self.store.select_route(route)

    def _open_analysis_results(self) -> None:
        self.analysis_route_active = True
        self._build_route_content()
        self._apply_theme()
        self._refresh_content()
        self.footer_hint.set("ANALYZER.sh is fixed and verified; arguments cannot be injected")

    def _build_route_content(self) -> None:
        if not self.analysis_route_active:
            super()._build_route_content()
            return
        for child in self.workspace.winfo_children():
            child.destroy()
        self._build_analysis_route()

    def _build_analysis_route(self) -> None:
        root = self._frame(self.workspace, "surface.app")
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_rowconfigure(2, weight=1)
        root.grid_columnconfigure(0, weight=1)

        header = self._frame(root, "surface.card")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._label(
            header,
            "Analyze Results",
            surface="surface.card",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(side="left", padx=14, pady=(12, 2), anchor="w")
        self._label(
            header,
            "Run the canonical modular Analyzer and watch its complete output in real time.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10, pady=(14, 2), anchor="w")

        status = self._frame(root, "surface.card")
        status.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.analysis_status_label = self._label(
            status,
            surface="surface.card",
            font=("TkDefaultFont", 11, "bold"),
        )
        self.analysis_status_label.pack(side="left", padx=(14, 10), pady=10)
        self.analysis_attempt_label = self._label(
            status,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        self.analysis_attempt_label.pack(side="left", padx=8)
        self._label(
            status,
            f"ANALYZER.sh  ·  {self.analysis_controller.plan.launcher_sha256[:12]}…",
            surface="surface.card",
            foreground="text.muted",
            font=("TkFixedFont", 8),
        ).pack(side="left", padx=12)

        self.analysis_start_button = self._button(
            status,
            "Start Analysis",
            self._start_analysis,
            kind="primary",
        )
        self.analysis_start_button.pack(side="right", padx=(4, 12), pady=6)
        self.analysis_stop_button = self._button(
            status,
            "Stop Analysis",
            self._stop_analysis,
            kind="danger",
        )
        self.analysis_stop_button.pack(side="right", padx=4, pady=6)
        self.analysis_clear_button = self._button(
            status,
            "Clear Console",
            self._clear_analysis_console,
        )
        self.analysis_clear_button.pack(side="right", padx=4, pady=6)

        panel = self._frame(root, "surface.card")
        panel.grid(row=2, column=0, sticky="nsew")
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        self._label(
            panel,
            "ANALYZER CONSOLE",
            surface="surface.card",
            foreground="text.muted",
            font=("TkDefaultFont", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        console_frame = self._frame(panel, "surface.elevated")
        console_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        console_frame.grid_rowconfigure(0, weight=1)
        console_frame.grid_columnconfigure(0, weight=1)
        self.analysis_console = tk.Text(
            console_frame,
            wrap="none",
            borderwidth=0,
            highlightthickness=1,
            padx=12,
            pady=10,
            font=("TkFixedFont", 9),
            state="disabled",
        )
        self._register(
            self.analysis_console,
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
            command=self.analysis_console.yview,
        )
        horizontal = ttk.Scrollbar(
            console_frame,
            orient="horizontal",
            command=self.analysis_console.xview,
        )
        self.analysis_console.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        self.analysis_console.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")

        note = self._frame(panel, "surface.card")
        note.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        self._label(
            note,
            "The Analyzer may update scientific results. The command is a fixed argv handoff; no shell text is accepted from the UI.",
            surface="surface.card",
            foreground="status.info",
            font=("TkDefaultFont", 8),
        ).pack(side="left")
        self._refresh_analysis_status()

    def _start_analysis(self) -> None:
        try:
            self.analysis_controller.start()
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Analyzer start refused: {exc}")
        self._drain_analysis_output()
        self._refresh_analysis_status()

    def _stop_analysis(self) -> None:
        try:
            self.analysis_controller.stop()
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Analyzer stop refused: {exc}")
        self._drain_analysis_output()
        self._refresh_analysis_status()

    def _clear_analysis_console(self) -> None:
        if not hasattr(self, "analysis_console") or not self.analysis_console.winfo_exists():
            return
        self.analysis_console.configure(state="normal")
        self.analysis_console.delete("1.0", "end")
        self.analysis_console.configure(state="disabled")

    def _drain_analysis_output(self) -> None:
        chunks = self.analysis_controller.drain_output()
        if not chunks or not self.analysis_route_active:
            return
        if not hasattr(self, "analysis_console") or not self.analysis_console.winfo_exists():
            return
        self.analysis_console.configure(state="normal")
        self.analysis_console.insert("end", "".join(chunks))
        line_count = int(self.analysis_console.index("end-1c").split(".")[0])
        if line_count > 20_000:
            self.analysis_console.delete("1.0", f"{line_count - 18_000}.0")
        self.analysis_console.see("end")
        self.analysis_console.configure(state="disabled")

    def _poll_analysis(self) -> None:
        try:
            exists = bool(self.root.winfo_exists())
        except tk.TclError:
            return
        if not exists:
            return
        self._drain_analysis_output()
        self._refresh_analysis_status()
        self.root.after(100, self._poll_analysis)

    def _refresh_analysis_status(self) -> None:
        if not self.analysis_route_active or not hasattr(self, "analysis_status_label"):
            return
        try:
            if not self.analysis_status_label.winfo_exists():
                return
        except tk.TclError:
            return
        record = self.analysis_controller.record
        tokens = {
            AnalysisState.IDLE: "status.info",
            AnalysisState.STARTING: "status.waiting",
            AnalysisState.RUNNING: "status.running",
            AnalysisState.STOPPING: "status.waiting",
            AnalysisState.SUCCEEDED: "status.completed",
            AnalysisState.FAILED: "status.failed",
            AnalysisState.STOPPED: "status.offline",
        }
        palette = palette_for(self.snapshot.resolved_theme)
        self.analysis_status_label.configure(
            text=f"●  {record.state.value.title()}",
            foreground=palette[tokens[record.state]],
        )
        exit_text = "" if record.exit_code is None else f"  ·  exit {record.exit_code}"
        self.analysis_attempt_label.configure(
            text=f"Attempt {record.attempt}{exit_text}"
        )
        self.analysis_start_button.configure(
            state="disabled" if record.active else "normal"
        )
        self.analysis_stop_button.configure(
            state=(
                "normal"
                if record.state in {AnalysisState.STARTING, AnalysisState.RUNNING}
                else "disabled"
            )
        )

    def _on_store_change(self, snapshot: ShellSnapshot) -> None:
        if self.analysis_route_active and snapshot.route is not self.snapshot.route:
            self.analysis_route_active = False
        super()._on_store_change(snapshot)

    def _refresh_content(self) -> None:
        super()._refresh_content()
        if self.analysis_route_active:
            self.route_title.configure(text="Analyze Results")
            self.footer_left.configure(text="Canonical modular Analyzer  •  live stdout/stderr")
            self.footer_right.configure(text="Real Analyzer handoff  •  fake Observer backend")
            self._refresh_analysis_status()

    def _refresh_navigation_theme(self) -> None:
        super()._refresh_navigation_theme()
        if not hasattr(self, "analysis_nav_button"):
            return
        palette = palette_for(self.snapshot.resolved_theme)
        if self.analysis_route_active:
            for button in self._nav_buttons.values():
                button.configure(
                    background=palette["surface.control"],
                    foreground=palette["text.primary"],
                    highlightbackground=palette["surface.control"],
                )
        background = (
            palette["surface.selected"]
            if self.analysis_route_active
            else palette["surface.control"]
        )
        foreground = (
            palette["chart.1"]
            if self.analysis_route_active
            else palette["text.primary"]
        )
        self.analysis_nav_button.configure(
            background=background,
            foreground=foreground,
            highlightbackground=background,
        )

    def _on_resize(self, event: tk.Event) -> None:
        super()._on_resize(event)
        if hasattr(self, "analysis_nav_button"):
            self.analysis_nav_button.configure(
                text="A" if self._nav_compact else "A   Analyze Results",
                anchor="center" if self._nav_compact else "w",
            )

    def _bind_shortcuts(self) -> None:
        super()._bind_shortcuts()
        self.root.bind(
            "<Control-l>",
            lambda _event: self._select_base_route(ShellRoute.OBSERVATION),
        )
        self.root.bind(
            "<Control-q>",
            lambda _event: self._select_base_route(ShellRoute.QUEUE),
        )

    def close(self) -> None:
        self.analysis_controller.close()
        super().close()
