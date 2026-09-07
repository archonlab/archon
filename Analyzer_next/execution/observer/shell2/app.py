"""Tk application shell for OL2-SHELL1; wired exclusively to FakeShellStore."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from Analyzer_next.execution.observer.state import RunState

from .store import FakeShellStore, ShellRoute, ShellSnapshot
from .theme import ThemeMode, detect_system_scheme, palette_for
from .view_model import ROUTES, MetricCardViewModel, ShellViewModel, build_view_model


class ObserverLauncher2Shell:
    """Presentation-only OL2 shell. It has no process or telemetry adapter."""

    def __init__(
        self,
        root: tk.Tk,
        store: FakeShellStore,
        *,
        animate: bool = True,
    ) -> None:
        self.root = root
        self.store = store
        self.animate = animate
        self.snapshot = store.snapshot
        self.view_model = build_view_model(self.snapshot)
        self._semantic_widgets: list[tuple[tk.Misc, dict[str, str]]] = []
        self._nav_buttons: dict[ShellRoute, tk.Button] = {}
        self._metric_sets: list[list[dict[str, Any]]] = []
        self._metrics_compact = False
        self._drawer_open = False
        self._nav_compact = False

        root.title("ARCHON Observer Launcher 2.0 — SHELL1 Preview")
        root.geometry("1536x864")
        root.minsize(980, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)

        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self.theme_var = tk.StringVar(value=self.snapshot.theme_preference.value)
        self.footer_hint = tk.StringVar(value="OL2-SHELL1 mock store is active")

        self._build_top_bar()
        self._build_body()
        self._build_footer()
        self._bind_shortcuts()
        self._unsubscribe = store.subscribe(self._on_store_change)
        root.bind("<Configure>", self._on_resize, add="+")
        if self.animate:
            root.after(1000, self._advance_demo)

    def _register(self, widget: tk.Misc, **semantic_options: str) -> tk.Misc:
        self._semantic_widgets.append((widget, semantic_options))
        return widget

    def _frame(self, parent: tk.Misc, surface: str) -> tk.Frame:
        widget = tk.Frame(parent, borderwidth=0)
        return self._register(widget, background=surface)  # type: ignore[return-value]

    def _label(
        self,
        parent: tk.Misc,
        text: str = "",
        *,
        surface: str = "surface.app",
        foreground: str = "text.primary",
        font: tuple[str, int, str] | tuple[str, int] = ("TkDefaultFont", 10),
        anchor: str = "w",
        textvariable: tk.StringVar | None = None,
    ) -> tk.Label:
        widget = tk.Label(
            parent,
            text=text,
            textvariable=textvariable,
            borderwidth=0,
            font=font,
            anchor=anchor,
        )
        return self._register(
            widget,
            background=surface,
            foreground=foreground,
        )  # type: ignore[return-value]

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], Any],
        *,
        kind: str = "neutral",
        width: int | None = None,
    ) -> tk.Button:
        mapping = {
            "neutral": (
                "surface.control",
                "text.primary",
                "surface.elevated",
                "text.primary",
            ),
            "primary": (
                "action.primary",
                "text.inverse",
                "action.primary_hover",
                "text.inverse",
            ),
            "danger": (
                "action.danger",
                "text.inverse",
                "action.danger_hover",
                "text.inverse",
            ),
        }
        background, foreground, active_background, active_foreground = mapping[kind]
        widget = tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            borderwidth=0,
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=8,
            takefocus=True,
            highlightthickness=2,
            font=("TkDefaultFont", 10, "bold"),
        )
        return self._register(
            widget,
            background=background,
            foreground=foreground,
            activebackground=active_background,
            activeforeground=active_foreground,
            disabledforeground="text.muted",
            highlightbackground=background,
            highlightcolor="focus.ring",
        )  # type: ignore[return-value]

    def _build_top_bar(self) -> None:
        self.top_bar = self._frame(self.root, "surface.navigation")
        self.top_bar.grid(row=0, column=0, sticky="ew")
        self.top_bar.configure(height=56)
        self.top_bar.pack_propagate(False)

        brand = self._label(
            self.top_bar,
            "⬡  ARCHON Observer",
            surface="surface.navigation",
            font=("TkDefaultFont", 13, "bold"),
        )
        brand.pack(side="left", padx=(16, 20), fill="y")

        divider = self._frame(self.top_bar, "border.default")
        divider.pack(side="left", fill="y", padx=(0, 18))
        divider.configure(width=1)

        self.route_title = self._label(
            self.top_bar,
            "OBSERVATION",
            surface="surface.navigation",
            foreground="chart.1",
            font=("TkDefaultFont", 11, "bold"),
        )
        self.route_title.pack(side="left", fill="y")

        self.route_context_label = self._label(
            self.top_bar,
            surface="surface.navigation",
            foreground="text.secondary",
            font=("TkDefaultFont", 11, "bold"),
        )
        self.route_context_label.pack(side="left", padx=(14, 0), fill="y")

        self.user_label = self._label(
            self.top_bar,
            "observer\nViewer",
            surface="surface.navigation",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        self.user_label.pack(side="right", padx=(10, 18), fill="y")

        self.settings_button = self._button(
            self.top_bar,
            "⚙",
            lambda: self.store.select_route(ShellRoute.SETTINGS),
            width=2,
        )
        self.settings_button.pack(side="right", padx=4, pady=8)
        self.help_button = self._button(
            self.top_bar,
            "?",
            lambda: self.footer_hint.set(
                "Space Pause/Resume  •  Shift+S Stop  •  Ctrl+L Observation  •  Ctrl+Q Queue"
            ),
            width=2,
        )
        self.help_button.pack(side="right", padx=4, pady=8)

        self.theme_combo = ttk.Combobox(
            self.top_bar,
            textvariable=self.theme_var,
            values=tuple(item.value for item in ThemeMode),
            state="readonly",
            width=8,
            takefocus=True,
            style="OL2.TCombobox",
        )
        self.theme_combo.pack(side="right", padx=(8, 10), pady=11)
        self.theme_combo.bind("<<ComboboxSelected>>", self._theme_selected)
        theme_text = self._label(
            self.top_bar,
            "Theme",
            surface="surface.navigation",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        theme_text.pack(side="right", pady=11)

        self.metrics_toggle = self._button(
            self.top_bar,
            "Metrics",
            self._toggle_metrics_drawer,
        )

    def _build_body(self) -> None:
        self.body = self._frame(self.root, "surface.app")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=1)
        self.body.grid_columnconfigure(0, minsize=220)

        self.navigation = self._frame(self.body, "surface.navigation")
        self.navigation.grid(row=0, column=0, sticky="nsew")
        self.navigation.grid_rowconfigure(9, weight=1)
        self._build_navigation()

        self.workspace = self._frame(self.body, "surface.app")
        self.workspace.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        self.workspace.grid_rowconfigure(0, weight=1)
        self.workspace.grid_columnconfigure(0, weight=1)

        self.metrics_rail = self._frame(self.body, "surface.navigation")
        self.metrics_rail.grid(row=0, column=2, sticky="nsew")
        self.metrics_rail.configure(width=320)
        self.metrics_rail.grid_propagate(False)
        self._build_metrics_rail(self.metrics_rail, drawer=False)

        self.metrics_drawer = self._frame(self.body, "surface.navigation")
        self.metrics_drawer.configure(width=320)
        self._build_metrics_rail(self.metrics_drawer, drawer=True)
        self.metrics_drawer.place_forget()

        self._build_route_content()

    def _build_navigation(self) -> None:
        heading = self._label(
            self.navigation,
            "WORKSPACE",
            surface="surface.navigation",
            foreground="text.muted",
            font=("TkDefaultFont", 8, "bold"),
        )
        heading.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 8))
        self.navigation.grid_columnconfigure(0, weight=1)
        for row, descriptor in enumerate(ROUTES, start=1):
            button = self._button(
                self.navigation,
                f"{descriptor.glyph}   {descriptor.label}",
                lambda route=descriptor.route: self.store.select_route(route),
            )
            button.configure(anchor="w", font=("TkDefaultFont", 10, "bold"))
            button.grid(row=row, column=0, sticky="ew", padx=8, pady=3)
            button.bind(
                "<Enter>",
                lambda _event, label=descriptor.label: self.footer_hint.set(
                    f"Open {label}"
                ),
            )
            button.bind(
                "<Leave>",
                lambda _event: self.footer_hint.set("OL2-SHELL1 mock store is active"),
            )
            self._nav_buttons[descriptor.route] = button

        status = self._frame(self.navigation, "surface.card")
        status.grid(row=10, column=0, sticky="sew", padx=10, pady=12)
        self._label(
            status,
            "SYSTEM STATUS",
            surface="surface.card",
            foreground="text.muted",
            font=("TkDefaultFont", 8, "bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))
        self._label(
            status,
            "●  Online",
            surface="surface.card",
            foreground="status.running",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", padx=12)
        self._label(
            status,
            "SHELL1 fake store\nNo process adapter",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 8),
        ).pack(anchor="w", padx=12, pady=(8, 12))

    def _build_route_content(self) -> None:
        for child in self.workspace.winfo_children():
            child.destroy()
        if self.snapshot.route is ShellRoute.OBSERVATION:
            self._build_observation()
            return
        panel = self._frame(self.workspace, "surface.card")
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        descriptor = next(item for item in ROUTES if item.route is self.snapshot.route)
        content = self._frame(panel, "surface.card")
        content.grid(row=0, column=0)
        self._label(
            content,
            descriptor.label,
            surface="surface.card",
            font=("TkDefaultFont", 22, "bold"),
            anchor="center",
        ).pack(pady=(0, 8))
        self._label(
            content,
            "Route container is operational.\nFeature binding belongs to a later OL2 milestone.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 11),
            anchor="center",
        ).pack()
        back = self._button(
            content,
            "Return to Observation",
            lambda: self.store.select_route(ShellRoute.OBSERVATION),
            kind="primary",
        )
        back.pack(pady=22)

    def _build_observation(self) -> None:
        self.observation = self._frame(self.workspace, "surface.app")
        self.observation.grid(row=0, column=0, sticky="nsew")
        self.observation.grid_rowconfigure(1, weight=1)
        self.observation.grid_columnconfigure(0, weight=1)

        controls = self._frame(self.observation, "surface.card")
        self.observation_controls = controls
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls.grid_columnconfigure(1, weight=1)
        status_group = self._frame(controls, "surface.card")
        status_group.grid(row=0, column=0, sticky="w")
        self.run_status_label = self._label(
            status_group,
            surface="surface.card",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.run_status_label.pack(side="left", padx=(10, 6), pady=10)
        self.elapsed_label = self._label(
            status_group,
            surface="surface.card",
            foreground="text.secondary",
        )
        self.elapsed_label.pack(side="left", padx=6)
        self.tick_label = self._label(
            status_group,
            surface="surface.card",
            foreground="text.secondary",
        )
        self.tick_label.pack(side="left", padx=6)

        action_group = self._frame(controls, "surface.card")
        action_group.grid(row=0, column=2, sticky="e")

        self.more_button = self._button(
            action_group,
            "⋯",
            lambda: self.footer_hint.set(
                f"Run ID copied in production: {self.snapshot.run.run_id}"
            ),
            width=2,
        )
        self.more_button.pack(side="right", padx=(4, 10), pady=6)
        self.new_run_button = self._button(
            action_group,
            "New Run",
            self.store.new_run,
        )
        self.new_run_button.pack(side="right", padx=4, pady=6)
        self.stop_button = self._button(
            action_group,
            "Stop",
            self._request_stop,
            kind="danger",
        )
        self.stop_button.pack(side="right", padx=4, pady=6)
        self.pause_button = self._button(
            action_group,
            "Pause",
            self.store.pause_or_resume,
        )
        self.pause_button.pack(side="right", padx=4, pady=6)

        viewport = self._frame(self.observation, "surface.card")
        viewport.grid(row=1, column=0, sticky="nsew")
        viewport.grid_rowconfigure(0, weight=1)
        viewport.grid_columnconfigure(0, weight=1)
        self.field_canvas = tk.Canvas(
            viewport,
            borderwidth=0,
            highlightthickness=1,
            takefocus=True,
        )
        self._register(
            self.field_canvas,
            background="surface.canvas",
            highlightbackground="border.default",
            highlightcolor="focus.ring",
        )
        self.field_canvas.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))
        self.field_canvas.bind("<Configure>", lambda _event: self._draw_field())

        viewport_controls = self._frame(viewport, "surface.elevated")
        viewport_controls.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        self._label(
            viewport_controls,
            "ZOOM    −    100%    +    ⛶",
            surface="surface.elevated",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="left", padx=14, pady=9)
        self._label(
            viewport_controls,
            "SPEED    1.0×",
            surface="surface.elevated",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="left", padx=28)
        self._label(
            viewport_controls,
            "GRID    ON    64 px",
            surface="surface.elevated",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="right", padx=14)

        self.state_strip_frame = self._frame(self.observation, "surface.card")
        self.state_strip_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.state_badges: list[tk.Label] = []
        for key, value in self.snapshot.state_strip:
            badge = self._label(
                self.state_strip_frame,
                f"{key}: {value}",
                surface="surface.card",
                foreground="text.secondary",
                font=("TkDefaultFont", 8, "bold"),
            )
            badge.pack(side="left", padx=10, pady=8)
            self.state_badges.append(badge)

    def _build_metrics_rail(self, parent: tk.Frame, *, drawer: bool) -> None:
        header = self._frame(parent, "surface.navigation")
        header.pack(fill="x", padx=10, pady=(12, 6))
        self._label(
            header,
            "METRICS",
            surface="surface.navigation",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="left")
        if drawer:
            close = self._button(header, "×", self._toggle_metrics_drawer, width=2)
            close.pack(side="right")
        cards: list[dict[str, Any]] = []
        for _index in range(6):
            frame = self._frame(parent, "surface.card")
            frame.pack(fill="x", padx=9, pady=4)
            label = self._label(
                frame,
                surface="surface.card",
                foreground="text.secondary",
                font=("TkDefaultFont", 8, "bold"),
            )
            label.grid(row=0, column=0, sticky="w", padx=10, pady=(8, 0))
            value = self._label(
                frame,
                surface="surface.card",
                font=("TkDefaultFont", 18, "bold"),
            )
            value.grid(row=1, column=0, sticky="w", padx=10)
            spark = tk.Canvas(frame, width=116, height=38, borderwidth=0, highlightthickness=0)
            self._register(spark, background="surface.card")
            spark.grid(row=0, column=1, rowspan=2, sticky="e", padx=8)
            delta = self._label(
                frame,
                surface="surface.card",
                foreground="text.muted",
                font=("TkDefaultFont", 8),
            )
            delta.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 2))
            secondary = self._label(
                frame,
                surface="surface.card",
                foreground="status.info",
                font=("TkDefaultFont", 8),
            )
            secondary.grid(row=2, column=1, sticky="e", padx=8)
            source = self._label(
                frame,
                surface="surface.card",
                foreground="text.muted",
                font=("TkDefaultFont", 7),
            )
            source.grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 7))
            frame.grid_columnconfigure(0, weight=1)
            cards.append(
                {
                    "label": label,
                    "value": value,
                    "delta": delta,
                    "secondary": secondary,
                    "source": source,
                    "spark": spark,
                }
            )
        self._metric_sets.append(cards)
        configure = self._button(
            parent,
            "Configure Observables",
            lambda: self.store.select_route(ShellRoute.SETTINGS),
        )
        configure.pack(fill="x", padx=9, pady=(7, 10))

    def _build_footer(self) -> None:
        self.footer = self._frame(self.root, "surface.navigation")
        self.footer.grid(row=2, column=0, sticky="ew")
        self.footer.configure(height=32)
        self.footer.pack_propagate(False)
        self.footer_left = self._label(
            self.footer,
            surface="surface.navigation",
            foreground="text.secondary",
            font=("TkDefaultFont", 8),
        )
        self.footer_left.pack(side="left", padx=16, fill="y")
        self.footer_right = self._label(
            self.footer,
            surface="surface.navigation",
            foreground="text.secondary",
            font=("TkDefaultFont", 8),
        )
        self.footer_right.pack(side="right", padx=16, fill="y")
        self.footer_hint_label = self._label(
            self.footer,
            surface="surface.navigation",
            foreground="status.info",
            font=("TkDefaultFont", 8),
            textvariable=self.footer_hint,
        )
        self.footer_hint_label.pack(side="right", padx=16, fill="y")

    def _bind_shortcuts(self) -> None:
        self.root.bind("<space>", self._shortcut_pause)
        self.root.bind("<Shift-KeyPress-s>", self._shortcut_stop)
        self.root.bind(
            "<Control-l>",
            lambda _event: self.store.select_route(ShellRoute.OBSERVATION),
        )
        self.root.bind(
            "<Control-q>",
            lambda _event: self.store.select_route(ShellRoute.QUEUE),
        )

    def _shortcut_pause(self, _event: tk.Event) -> str:
        self.store.pause_or_resume()
        return "break"

    def _shortcut_stop(self, _event: tk.Event) -> str:
        self._request_stop()
        return "break"

    def _theme_selected(self, _event: tk.Event | None = None) -> None:
        self.store.set_theme(
            self.theme_var.get(),
            system_scheme=detect_system_scheme(),
        )

    def _request_stop(self) -> None:
        snapshot = self.store.request_stop()
        if snapshot.run.state is RunState.STOPPING:
            self.footer_hint.set("Mock stop requested; awaiting fake acknowledgement")
            self.root.after(750, self._acknowledge_stop)

    def _acknowledge_stop(self) -> None:
        self.store.acknowledge_stop()
        self.footer_hint.set("Mock stop acknowledged; evidence remains untouched")

    def _on_store_change(self, snapshot: ShellSnapshot) -> None:
        route_changed = snapshot.route is not self.snapshot.route
        self.snapshot = snapshot
        self.view_model = build_view_model(snapshot)
        self.theme_var.set(snapshot.theme_preference.value)
        if route_changed:
            self._build_route_content()
        self._apply_theme()
        self._refresh_content()

    def _apply_theme(self) -> None:
        palette = palette_for(self.snapshot.resolved_theme)
        self.root.configure(background=palette["surface.app"])
        self.style.configure(
            "OL2.TCombobox",
            fieldbackground=palette["surface.control"],
            background=palette["surface.control"],
            foreground=palette["text.primary"],
            arrowcolor=palette["text.primary"],
            bordercolor=palette["border.default"],
            lightcolor=palette["border.default"],
            darkcolor=palette["border.default"],
            focuscolor=palette["focus.ring"],
            padding=6,
        )
        self.style.map(
            "OL2.TCombobox",
            fieldbackground=[("readonly", palette["surface.control"])],
            foreground=[("readonly", palette["text.primary"])],
            selectbackground=[("readonly", palette["action.primary"])],
            selectforeground=[("readonly", palette["text.inverse"])],
        )
        for widget, options in tuple(self._semantic_widgets):
            try:
                exists = bool(widget.winfo_exists())
            except tk.TclError:
                exists = False
            if not exists:
                continue
            widget.configure(**{name: palette[token] for name, token in options.items()})
        self._refresh_navigation_theme()
        self._draw_field()
        self._draw_all_sparklines()

    def _refresh_navigation_theme(self) -> None:
        palette = palette_for(self.snapshot.resolved_theme)
        for route, button in self._nav_buttons.items():
            selected = route is self.snapshot.route
            background = palette["surface.selected"] if selected else palette["surface.control"]
            foreground = palette["chart.1"] if selected else palette["text.primary"]
            button.configure(
                background=background,
                foreground=foreground,
                highlightbackground=background,
            )

    def _refresh_content(self) -> None:
        view = self.view_model
        self.route_title.configure(text=view.route_label.upper())
        self.route_context_label.configure(
            text=(
                f"Rule {self.snapshot.run.spec.rule_id:05d}"
                if view.route is ShellRoute.OBSERVATION
                else ""
            )
        )
        self.footer_left.configure(text=view.footer_left)
        self.footer_right.configure(text=view.footer_right)
        if view.route is ShellRoute.OBSERVATION and hasattr(self, "run_status_label"):
            palette = palette_for(self.snapshot.resolved_theme)
            self.run_status_label.configure(
                text=f"●  {view.controls.status_text}",
                foreground=palette[view.controls.status_token],
            )
            self.elapsed_label.configure(text=f"◷  {view.elapsed_text}")
            self.tick_label.configure(text=view.tick_text)
            self.pause_button.configure(
                text=view.controls.pause_label,
                state="normal" if view.controls.pause_enabled else "disabled",
            )
            self.stop_button.configure(
                state="normal" if view.controls.stop_enabled else "disabled"
            )
            self.new_run_button.configure(
                state="normal" if view.controls.new_run_enabled else "disabled"
            )
            for label, (key, value) in zip(self.state_badges, view.state_strip):
                label.configure(text=f"{key}: {value}")
            self._draw_field()
        for card_set in self._metric_sets:
            for widgets, card in zip(card_set, view.metric_cards):
                widgets["label"].configure(text=card.label.upper())
                widgets["value"].configure(text=card.value_text)
                widgets["delta"].configure(text=card.delta_text)
                widgets["secondary"].configure(text=card.secondary_text or "")
                widgets["source"].configure(text=card.source_text)
        self._draw_all_sparklines()

    def _draw_field(self) -> None:
        if not hasattr(self, "field_canvas"):
            return
        canvas = self.field_canvas
        try:
            if not canvas.winfo_exists():
                return
        except tk.TclError:
            return
        palette = palette_for(self.snapshot.resolved_theme)
        canvas.delete("all")
        width = max(canvas.winfo_width(), 760)
        height = max(canvas.winfo_height(), 420)
        cell = 13
        columns = min(72, max(1, width // cell))
        rows = min(42, max(1, height // cell))
        offset_x = max(0, (width - columns * cell) // 2)
        offset_y = max(0, (height - rows * cell) // 2)
        for column in range(columns + 1):
            x = offset_x + column * cell
            canvas.create_line(x, offset_y, x, offset_y + rows * cell, fill=palette["grid.line"])
        for row in range(rows + 1):
            y = offset_y + row * cell
            canvas.create_line(offset_x, y, offset_x + columns * cell, y, fill=palette["grid.line"])
        tick = int(self.snapshot.telemetry.last_tick or 0)
        center_y = rows / 2
        for row in range(rows):
            vertical_weight = abs(row - center_y) / max(1.0, center_y)
            for column in range(columns):
                value = (
                    (row * 73)
                    ^ (column * 151)
                    ^ (row * column * 17)
                    ^ tick
                ) % 113
                threshold = 16 if vertical_weight < 0.55 else 7
                if value >= threshold:
                    continue
                token = "cell.secondary" if value % 5 == 0 else "cell.primary"
                if value % 7 == 0:
                    token = "cell.quiet"
                x0 = offset_x + column * cell + 2
                y0 = offset_y + row * cell + 2
                canvas.create_rectangle(
                    x0,
                    y0,
                    x0 + cell - 4,
                    y0 + cell - 4,
                    fill=palette[token],
                    outline="",
                )
        canvas.create_rectangle(
            14,
            14,
            292,
            42,
            fill=palette["surface.overlay"],
            outline=palette["border.default"],
        )
        canvas.create_text(
            27,
            28,
            text="MOCK FRAME  •  FrameStreamPort not connected",
            fill=palette["text.secondary"],
            anchor="w",
            font=("TkDefaultFont", 8, "bold"),
        )

    def _draw_all_sparklines(self) -> None:
        for card_set in self._metric_sets:
            for widgets, card in zip(card_set, self.view_model.metric_cards):
                self._draw_sparkline(widgets["spark"], card)

    def _draw_sparkline(self, canvas: tk.Canvas, card: MetricCardViewModel) -> None:
        try:
            if not canvas.winfo_exists():
                return
        except tk.TclError:
            return
        palette = palette_for(self.snapshot.resolved_theme)
        canvas.delete("all")
        history = card.history
        if len(history) < 2:
            return
        width = max(100, canvas.winfo_width())
        height = max(30, canvas.winfo_height())
        minimum, maximum = min(history), max(history)
        span = max(maximum - minimum, 1e-9)
        points = []
        for index, value in enumerate(history):
            x = 4 + index * (width - 8) / (len(history) - 1)
            y = height - 4 - (value - minimum) * (height - 8) / span
            points.extend((x, y))
        canvas.create_line(
            *points,
            fill=palette[card.chart_token],
            width=2,
            smooth=True,
        )

    def _on_resize(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        width = int(event.width)
        compact_metrics = width < 1360
        compact_navigation = width < 1220
        if compact_metrics != self._metrics_compact:
            self._metrics_compact = compact_metrics
            if compact_metrics:
                self.metrics_rail.grid_remove()
                self.metrics_toggle.pack(side="right", padx=6, pady=8)
            else:
                self.metrics_toggle.pack_forget()
                self.metrics_drawer.place_forget()
                self._drawer_open = False
                self.metrics_rail.grid(row=0, column=2, sticky="nsew")
        if compact_navigation != self._nav_compact:
            self._nav_compact = compact_navigation
            self.body.grid_columnconfigure(0, minsize=68 if compact_navigation else 220)
            for descriptor in ROUTES:
                text = descriptor.glyph if compact_navigation else f"{descriptor.glyph}   {descriptor.label}"
                self._nav_buttons[descriptor.route].configure(text=text, anchor="center" if compact_navigation else "w")

    def _toggle_metrics_drawer(self) -> None:
        if not self._metrics_compact:
            return
        self._drawer_open = not self._drawer_open
        if self._drawer_open:
            self.metrics_drawer.place(
                relx=1.0,
                rely=0,
                relheight=1.0,
                width=320,
                anchor="ne",
            )
            self.metrics_drawer.lift()
        else:
            self.metrics_drawer.place_forget()

    def _advance_demo(self) -> None:
        if not self.root.winfo_exists():
            return
        self.store.advance_tick()
        self.root.after(1000, self._advance_demo)

    def close(self) -> None:
        self._unsubscribe()
        self.root.destroy()


def run_shell(
    *,
    theme: ThemeMode = ThemeMode.SYSTEM,
    auto_close_ms: int | None = None,
    animate: bool = True,
) -> int:
    root = tk.Tk()
    store = FakeShellStore(
        theme_preference=theme,
        system_scheme=detect_system_scheme(),
    )
    ObserverLauncher2Shell(root, store, animate=animate)
    if auto_close_ms is not None:
        root.after(max(1, auto_close_ms), root.destroy)
    root.mainloop()
    return 0
