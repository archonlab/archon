"""OL2-FUNCTIONS1C: real launcher-local Settings and observable preferences."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from Analyzer_next.common.paths import PROJECT_ROOT
from Analyzer_next.execution.observer.shell2.functions1b.app import (
    ObserverLauncher2FunctionsStopShell,
)
from Analyzer_next.execution.observer.shell2.metrics import load_default_metric_definitions
from Analyzer_next.execution.observer.shell2.store import ShellRoute
from Analyzer_next.execution.observer.shell2.theme import ThemeMode

from .controller import LauncherSettingsController
from .model import LauncherUIPreferences


class ObserverLauncher2FunctionsSettingsShell(ObserverLauncher2FunctionsStopShell):
    """Bind Settings without changing simulation, queue or telemetry ownership."""

    def __init__(self, *args, settings_controller: LauncherSettingsController, **kwargs) -> None:
        if not isinstance(settings_controller, LauncherSettingsController):
            raise TypeError("FUNCTIONS1C requires LauncherSettingsController")
        self.settings_controller = settings_controller
        self._settings_metric_vars: dict[str, tk.BooleanVar] = {}
        self._settings_rail_width_var: tk.StringVar | None = None
        super().__init__(*args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — FUNCTIONS1C")

        preferences = self.settings_controller.preferences
        # LAYOUT1 owns geometry; FUNCTIONS1C only restores the user's saved
        # launcher-local width after all inherited widgets exist.
        self._rail_width = int(preferences.rail_width)
        self._apply_rail_width()
        for view in tuple(self._instrument_views):
            parent = view.get("parent")
            if parent is not None:
                self._select_rail_mode(parent, preferences.rail_tab, persist=False)
        self._apply_metric_visibility()
        self.footer_hint.set(
            "FUNCTIONS1C Settings active • launcher preferences only • scientific runtime unchanged"
        )

    # ------------------------------------------------------------------
    # Route ownership / Analyze Results overlay lifecycle
    # ------------------------------------------------------------------
    def _select_base_route(self, route: ShellRoute) -> None:
        # ANALYZE1 is an overlay over the current base ShellRoute rather than
        # a distinct store route. Returning to the same base route therefore
        # cannot rely on route_changed=True to rebuild the workspace. Force a
        # fresh mount in that one case so Observation receives new live widgets.
        returning_from_analysis = bool(self.analysis_route_active)
        same_route = route is self.snapshot.route
        self.analysis_route_active = False
        if returning_from_analysis and same_route:
            if route is ShellRoute.OBSERVATION:
                # The controller kept ingesting frames while the overlay was
                # visible. Re-render the newest frame even if its sequence was
                # already seen before the old canvas was destroyed. Clear
                # route-local Tk handles first because OBSERVE1 draws once
                # before INTERACT1 recreates its toolbar labels.
                self._last_presentation_sequence = -1
                self._clear_dead_interaction_refs()
            self._build_route_content()
            self._apply_theme()
            self._refresh_content()
            self.footer_hint.set(f"Returned from Analyze Results to {route.value}")
            return
        self.store.select_route(route)

    def _refresh_content(self) -> None:
        # While ANALYZE1 owns the workspace, snapshot.route still names the
        # underlying base route (often Observation). Do not let inherited live
        # renderers touch widgets that were destroyed when the analysis overlay
        # replaced the workspace. Controller/process state continues below.
        if self.analysis_route_active:
            try:
                self.route_title.configure(text="Analyze Results")
                self.footer_left.configure(text="Canonical modular Analyzer  •  live stdout/stderr")
                self.footer_right.configure(text="Real Analyzer handoff  •  Observer runtime continues independently")
            except tk.TclError:
                return
            self._refresh_analysis_status()
            return
        super()._refresh_content()

    def _poll_presentation(self) -> None:
        # Presentation ingestion happens in the controller's process-output
        # thread. Only painting is suspended while Analyze Results owns the
        # workspace; otherwise a dead Observation canvas would kill this Tk
        # after-loop permanently.
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        if self.analysis_route_active:
            self.root.after(50, self._poll_presentation)
            return
        super()._poll_presentation()

    def _poll_control(self) -> None:
        # Keep lifecycle/ACK reconciliation alive while Analyze Results is open,
        # but skip route-local widget refreshes until the base route is mounted
        # again. This prevents Pause/Resume from being stranded in transitional
        # states after an analysis detour.
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        if not self.analysis_route_active:
            super()._poll_control()
            return
        chunks = self.control_controller.drain_output()
        self._append_control_output(chunks)
        snapshot = self.control_controller.snapshot
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
        self.root.after(100, self._poll_control)

    def _poll_live_telemetry(self) -> None:
        # The telemetry port stays read-only and the next Observation poll will
        # immediately catch up. Avoid painting telemetry widgets while ANALYZE1
        # is the visible workspace.
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        if self.analysis_route_active:
            self.root.after(500, self._poll_live_telemetry)
            return
        super()._poll_live_telemetry()

    # ------------------------------------------------------------------
    # Settings route ownership
    # ------------------------------------------------------------------
    def _build_route_content(self) -> None:
        if not self.analysis_route_active and self.snapshot.route is ShellRoute.SETTINGS:
            for child in self.workspace.winfo_children():
                child.destroy()
            self._build_settings_route()
            return
        super()._build_route_content()

    def _build_settings_route(self) -> None:
        root = self._frame(self.workspace, "surface.app")
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        canvas, body = self._new_hidden_scroller(root)
        canvas.pack_configure(padx=0, pady=0)

        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(
            header,
            "Settings",
            surface="surface.card",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 2))
        description = self._label(
            header,
            "Launcher-local rendering, telemetry display and workspace preferences. These controls never mutate scientific configuration or Observer evidence.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        description.configure(wraplength=980, justify="left")
        description.pack(anchor="w", padx=14, pady=(0, 12))

        self._build_settings_appearance(body)
        self._build_settings_observables(body)
        self._build_settings_telemetry(body)
        self._build_settings_paths(body)

        reset = self._frame(body, "surface.card")
        reset.pack(fill="x", pady=(0, 12))
        self._label(
            reset,
            "Reset only changes launcher presentation preferences.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=14, pady=12)
        self._button(reset, "Reset UI Preferences", self._reset_ui_preferences).pack(
            side="right", padx=12, pady=8
        )
        self._sync_settings_controls()

    def _settings_section(self, parent: tk.Misc, title: str) -> tk.Frame:
        outer = self._frame(parent, "surface.card")
        outer.pack(fill="x", pady=(0, 8))
        self._label(
            outer,
            title.upper(),
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(11, 7))
        return outer

    def _build_settings_appearance(self, parent: tk.Misc) -> None:
        section = self._settings_section(parent, "Appearance")
        theme_row = self._frame(section, "surface.card")
        theme_row.pack(fill="x", padx=14, pady=(0, 8))
        self._label(
            theme_row,
            "Theme",
            surface="surface.card",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="left")
        self.settings_theme_combo = ttk.Combobox(
            theme_row,
            textvariable=self.theme_var,
            values=tuple(item.value for item in ThemeMode),
            state="readonly",
            width=10,
            style="OL2.TCombobox",
        )
        self.settings_theme_combo.pack(side="right")
        self.settings_theme_combo.bind("<<ComboboxSelected>>", self._settings_theme_selected)

        tab_row = self._frame(section, "surface.card")
        tab_row.pack(fill="x", padx=14, pady=(0, 8))
        self._label(
            tab_row,
            "Default Observation rail",
            surface="surface.card",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="left")
        self.settings_rail_tab_var = tk.StringVar(value=self.settings_controller.preferences.rail_tab)
        for value, text in (("metrics", "Metrics"), ("instruments", "Instruments")):
            radio = tk.Radiobutton(
                tab_row,
                text=text,
                value=value,
                variable=self.settings_rail_tab_var,
                command=self._settings_rail_tab_changed,
                borderwidth=0,
                highlightthickness=1,
                cursor="hand2",
                padx=8,
                pady=5,
            )
            self._register(
                radio,
                background="surface.card",
                foreground="text.primary",
                activebackground="surface.elevated",
                activeforeground="text.primary",
                selectcolor="surface.selected",
                highlightbackground="surface.card",
                highlightcolor="focus.ring",
            )
            radio.pack(side="right", padx=(4, 0))

        width_row = self._frame(section, "surface.card")
        width_row.pack(fill="x", padx=14, pady=(0, 12))
        self._label(
            width_row,
            "Observation rail width",
            surface="surface.card",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="left")
        self._settings_rail_width_var = tk.StringVar()
        self._label(
            width_row,
            surface="surface.card",
            foreground="text.secondary",
            textvariable=self._settings_rail_width_var,
        ).pack(side="right", padx=(8, 0))
        self._button(width_row, "Reset 380 px", self._reset_rail_width).pack(side="right", padx=4)

    def _build_settings_observables(self, parent: tk.Misc) -> None:
        section = self._settings_section(parent, "Metric observables")
        note = self._label(
            section,
            "Choose which of the six frozen canonical TELEM1 metric cards are visible. This changes presentation only; all telemetry remains read-only.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        note.configure(wraplength=980, justify="left")
        note.pack(anchor="w", padx=14, pady=(0, 8))

        grid = self._frame(section, "surface.card")
        grid.pack(fill="x", padx=14, pady=(0, 12))
        visible = set(self.settings_controller.preferences.visible_metric_ids)
        self._settings_metric_vars = {}
        for index, definition in enumerate(load_default_metric_definitions()):
            variable = tk.BooleanVar(value=definition.metric_id in visible)
            self._settings_metric_vars[definition.metric_id] = variable
            check = tk.Checkbutton(
                grid,
                text=definition.label,
                variable=variable,
                command=lambda metric_id=definition.metric_id: self._metric_visibility_changed(metric_id),
                anchor="w",
                borderwidth=0,
                highlightthickness=1,
                cursor="hand2",
                padx=8,
                pady=6,
            )
            self._register(
                check,
                background="surface.control",
                foreground="text.primary",
                activebackground="surface.elevated",
                activeforeground="text.primary",
                selectcolor="surface.selected",
                highlightbackground="surface.control",
                highlightcolor="focus.ring",
            )
            check.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 6), pady=3)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

    def _build_settings_telemetry(self, parent: tk.Misc) -> None:
        section = self._settings_section(parent, "Telemetry")
        database = getattr(getattr(self.telemetry_controller, "port", None), "database_path", None)
        rows = (
            ("Access", "read-only SQLite"),
            ("Card refresh", "500 ms"),
            ("STALE threshold", f"{self.telemetry_controller.stale_after_seconds:.1f} s"),
            ("Database", str(database) if database is not None else "unavailable"),
        )
        for label, value in rows:
            row = self._frame(section, "surface.card")
            row.pack(fill="x", padx=14, pady=2)
            self._label(
                row,
                label,
                surface="surface.card",
                foreground="text.secondary",
                font=("TkDefaultFont", 9, "bold"),
            ).pack(side="left")
            value_label = self._label(
                row,
                value,
                surface="surface.card",
                foreground="text.primary",
                font=("TkDefaultFont", 9),
            )
            value_label.configure(wraplength=760, justify="right")
            value_label.pack(side="right")
        spacer = self._frame(section, "surface.card")
        spacer.pack(fill="x", pady=(0, 8))

    def _build_settings_paths(self, parent: tk.Misc) -> None:
        section = self._settings_section(parent, "Workspace folders")
        targets = (
            ("Project Root", PROJECT_ROOT),
            ("Atlas Worlds", PROJECT_ROOT / "Atlas/Worlds"),
            ("Universe Search Results", PROJECT_ROOT / "Results/Universe_Search"),
            ("Analysis Results", PROJECT_ROOT / "Results/Analysis"),
            ("Launcher Config", PROJECT_ROOT / "Config/ObserverLauncher"),
        )
        row = self._frame(section, "surface.card")
        row.pack(fill="x", padx=14, pady=(0, 12))
        for label, path in targets:
            self._button(row, label, lambda p=path: self._open_settings_path(p)).pack(
                side="left", padx=(0, 6), pady=2
            )

    # ------------------------------------------------------------------
    # Preference application/persistence
    # ------------------------------------------------------------------
    def _theme_selected(self, event: tk.Event | None = None) -> None:
        super()._theme_selected(event)
        try:
            self.settings_controller.set_theme(self.theme_var.get())
        except (OSError, ValueError) as exc:
            self.footer_hint.set(f"Theme changed for this session; preference save failed: {exc}")

    def _settings_theme_selected(self, event: tk.Event | None = None) -> None:
        self._theme_selected(event)

    def _select_rail_mode(self, parent: tk.Frame, mode: str, *, persist: bool = True) -> None:
        super()._select_rail_mode(parent, mode)
        if persist:
            try:
                self.settings_controller.set_rail_tab(mode)
            except (OSError, ValueError) as exc:
                self.footer_hint.set(f"Rail tab changed for this session; preference save failed: {exc}")
        if hasattr(self, "settings_rail_tab_var"):
            try:
                self.settings_rail_tab_var.set(mode)
            except tk.TclError:
                pass

    def _settings_rail_tab_changed(self) -> None:
        mode = self.settings_rail_tab_var.get()
        try:
            self.settings_controller.set_rail_tab(mode)
        except (OSError, ValueError) as exc:
            self.footer_hint.set(f"Default rail tab not saved: {exc}")
            return
        for view in tuple(self._instrument_views):
            parent = view.get("parent")
            if parent is not None:
                self._select_rail_mode(parent, mode, persist=False)
        self.footer_hint.set(f"Default Observation rail set to {mode.title()}")

    def _build_metrics_rail(self, parent: tk.Frame, *, drawer: bool) -> None:
        before = len(self._metric_sets)
        super()._build_metrics_rail(parent, drawer=drawer)
        definitions = load_default_metric_definitions()
        for card_set in self._metric_sets[before:]:
            for widgets, definition in zip(card_set, definitions):
                widgets["metric_id"] = definition.metric_id
                widgets["frame"] = widgets["label"].master
        self._apply_metric_visibility()
        try:
            mode = self.settings_controller.preferences.rail_tab
        except AttributeError:
            mode = "instruments"
        self._select_rail_mode(parent, mode, persist=False)

    def _apply_metric_visibility(self) -> None:
        visible = set(self.settings_controller.preferences.visible_metric_ids)
        definitions = load_default_metric_definitions()
        for card_set in self._metric_sets:
            if not card_set:
                continue
            for widgets, definition in zip(card_set, definitions):
                widgets.setdefault("metric_id", definition.metric_id)
                widgets.setdefault("frame", widgets["label"].master)
            containers: dict[tk.Misc, list[dict]] = {}
            for widgets in card_set:
                frame = widgets.get("frame")
                if frame is not None:
                    containers.setdefault(frame.master, []).append(widgets)
            for container, rows in containers.items():
                configure = None
                try:
                    for child in container.winfo_children():
                        if isinstance(child, tk.Button) and str(child.cget("text")) == "Configure Observables":
                            configure = child
                            break
                except tk.TclError:
                    continue
                for widgets in rows:
                    frame = widgets["frame"]
                    try:
                        frame.pack_forget()
                    except tk.TclError:
                        pass
                for widgets in rows:
                    if widgets.get("metric_id") not in visible:
                        continue
                    frame = widgets["frame"]
                    try:
                        options = {"fill": "x", "padx": 9, "pady": 4}
                        if configure is not None:
                            options["before"] = configure
                        frame.pack(**options)
                    except tk.TclError:
                        pass

    def _metric_visibility_changed(self, metric_id: str) -> None:
        variable = self._settings_metric_vars[metric_id]
        requested = bool(variable.get())
        try:
            preferences = self.settings_controller.set_metric_visible(metric_id, requested)
        except (OSError, ValueError) as exc:
            variable.set(not requested)
            self.footer_hint.set(f"Observable change refused: {exc}")
            return
        self._apply_metric_visibility()
        self.footer_hint.set(
            f"Visible metric cards: {len(preferences.visible_metric_ids)} / {len(load_default_metric_definitions())}"
        )

    def _reset_rail_width(self) -> None:
        self._rail_width = 380
        self._apply_rail_width()
        try:
            self.settings_controller.set_rail_width(self._rail_width)
        except OSError as exc:
            self.footer_hint.set(f"Rail width reset for this session; preference save failed: {exc}")
        self._sync_settings_controls()

    def _begin_rail_drag(self, event: tk.Event) -> None:
        super()._begin_rail_drag(event)
        if self.rail_sash is not None:
            self.rail_sash.bind("<ButtonRelease-1>", self._finish_rail_drag)

    def _finish_rail_drag(self, _event: tk.Event | None = None) -> None:
        self._rail_drag_origin_x = None
        try:
            self.settings_controller.set_rail_width(int(self._rail_width))
        except (OSError, ValueError) as exc:
            self.footer_hint.set(f"Rail width changed for this session; preference save failed: {exc}")
        self._sync_settings_controls()

    def _sync_settings_controls(self) -> None:
        preferences = self.settings_controller.preferences
        if self._settings_rail_width_var is not None:
            self._settings_rail_width_var.set(f"{int(self._rail_width)} px • saved {preferences.rail_width} px")
        if hasattr(self, "settings_rail_tab_var"):
            self.settings_rail_tab_var.set(preferences.rail_tab)
        for metric_id, variable in self._settings_metric_vars.items():
            variable.set(metric_id in set(preferences.visible_metric_ids))

    def _reset_ui_preferences(self) -> None:
        try:
            preferences = self.settings_controller.reset_defaults()
        except OSError as exc:
            self.footer_hint.set(f"UI preference reset failed: {exc}")
            return
        self.theme_var.set(preferences.theme.value)
        self.store.set_theme(preferences.theme)
        self._rail_width = int(preferences.rail_width)
        self._apply_rail_width()
        for view in tuple(self._instrument_views):
            parent = view.get("parent")
            if parent is not None:
                self._select_rail_mode(parent, preferences.rail_tab, persist=False)
        self._apply_metric_visibility()
        self._sync_settings_controls()
        self.footer_hint.set("Launcher UI preferences reset to defaults")

    def _open_settings_path(self, path: Path) -> None:
        try:
            self.settings_controller.open_path(path)
        except Exception as exc:
            self.footer_hint.set(f"Could not open {path}: {exc}")
            return
        self.footer_hint.set(f"Opened {path}")


__all__ = ["ObserverLauncher2FunctionsSettingsShell"]
