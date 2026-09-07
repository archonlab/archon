"""OL2-LAYOUT1 UI stabilization over OBSERVE1.

This layer owns presentation geometry only.  It does not own scientific state,
process execution, queue orchestration, telemetry storage, or legacy Observer
logic.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any

from Analyzer_next.execution.observer.shell2.observe1.app import (
    ObserverLauncher2ObserveShell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute
from Analyzer_next.execution.observer.shell2.telem1.app import (
    ObserverLauncher2TelemetryShell,
)
from Analyzer_next.execution.observer.shell2.telem1.policy import MetricRailMode


class ObserverLauncher2LayoutShell(ObserverLauncher2ObserveShell):
    """Freeze live layout geometry while keeping the right rail user-resizable."""

    DEFAULT_RAIL_WIDTH = 380
    MIN_RAIL_WIDTH = 300
    MAX_RAIL_WIDTH = 620
    SASH_WIDTH = 7

    def __init__(self, *args, **kwargs) -> None:
        self._rail_width = self.DEFAULT_RAIL_WIDTH
        self._rail_drag_origin_x: int | None = None
        self._rail_drag_origin_width = self.DEFAULT_RAIL_WIDTH
        self._wheel_scroll_views: list[dict[str, Any]] = []
        self.rail_sash: tk.Frame | None = None
        super().__init__(*args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — LAYOUT1")
        self.footer_hint.set(
            "LAYOUT1 stable viewer geometry • drag the right divider • wheel-scroll rail"
        )
        self.root.bind_all("<MouseWheel>", self._on_rail_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_rail_mousewheel, add="+")
        self.root.bind_all("<Button-5>", self._on_rail_mousewheel, add="+")
        self.root.after_idle(self._apply_stable_geometry)

    # ------------------------------------------------------------------
    # Stable body geometry.  The rail has an explicit width owned only by
    # the draggable divider, never by child requested sizes.
    # ------------------------------------------------------------------
    def _build_body(self) -> None:
        self.body = self._frame(self.root, "surface.app")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, minsize=220)
        self.body.grid_columnconfigure(1, weight=1, minsize=620)
        self.body.grid_columnconfigure(2, minsize=self.SASH_WIDTH)
        self.body.grid_columnconfigure(3, minsize=self._rail_width)

        self.navigation = self._frame(self.body, "surface.navigation")
        self.navigation.grid(row=0, column=0, sticky="nsew")
        self.navigation.grid_rowconfigure(9, weight=1)
        self._build_navigation()

        self.workspace = self._frame(self.body, "surface.app")
        self.workspace.grid(row=0, column=1, sticky="nsew", padx=(12, 8), pady=12)
        self.workspace.grid_rowconfigure(0, weight=1)
        self.workspace.grid_columnconfigure(0, weight=1)

        self.rail_sash = self._frame(self.body, "border.default")
        self.rail_sash.configure(width=self.SASH_WIDTH, cursor="sb_h_double_arrow")
        self.rail_sash.grid_propagate(False)
        self.rail_sash.grid(row=0, column=2, sticky="ns", pady=12)
        self.rail_sash.bind("<ButtonPress-1>", self._begin_rail_drag)
        self.rail_sash.bind("<B1-Motion>", self._drag_rail)

        self.metrics_rail = self._frame(self.body, "surface.navigation")
        self.metrics_rail.configure(width=self._rail_width)
        self.metrics_rail.grid_propagate(False)
        self.metrics_rail.pack_propagate(False)
        self.metrics_rail.grid(row=0, column=3, sticky="nsew")
        self._build_metrics_rail(self.metrics_rail, drawer=False)

        self.metrics_drawer = self._frame(self.body, "surface.navigation")
        self.metrics_drawer.configure(width=self._rail_width)
        self.metrics_drawer.grid_propagate(False)
        self.metrics_drawer.pack_propagate(False)
        self._build_metrics_rail(self.metrics_drawer, drawer=True)
        self.metrics_drawer.place_forget()

        self._build_route_content()

    def _begin_rail_drag(self, event: tk.Event) -> None:
        if self._metric_rail_mode() is not MetricRailMode.FIXED:
            return
        self._rail_drag_origin_x = int(event.x_root)
        self._rail_drag_origin_width = int(self._rail_width)

    def _drag_rail(self, event: tk.Event) -> None:
        if self._rail_drag_origin_x is None:
            return
        delta = int(event.x_root) - self._rail_drag_origin_x
        requested = self._rail_drag_origin_width - delta
        available = max(self.MIN_RAIL_WIDTH, int(self.root.winfo_width()) - 760)
        upper = min(self.MAX_RAIL_WIDTH, available)
        width = max(self.MIN_RAIL_WIDTH, min(requested, upper))
        if width == self._rail_width:
            return
        self._rail_width = width
        self._apply_rail_width()

    def _apply_rail_width(self) -> None:
        if hasattr(self, "metrics_rail"):
            self.metrics_rail.configure(width=self._rail_width)
        if hasattr(self, "metrics_drawer"):
            self.metrics_drawer.configure(width=self._rail_width)
        if hasattr(self, "body") and self._metric_rail_mode() is MetricRailMode.FIXED:
            self.body.grid_columnconfigure(3, minsize=self._rail_width)
        wrap = max(180, self._rail_width - 58)
        for view in self._instrument_views:
            for section in view.get("sections", {}).values():
                for label in section.get("labels", {}).values():
                    try:
                        label.configure(wraplength=wrap, justify="left", anchor="w")
                    except tk.TclError:
                        pass
        for card_set in self._metric_sets:
            for card in card_set:
                for key in ("delta", "secondary", "source"):
                    try:
                        card[key].configure(wraplength=wrap, justify="left", anchor="w")
                    except tk.TclError:
                        pass

    # TELEM1 assumes the legacy fixed rail is column 2.  LAYOUT1 owns the
    # divider and moves the fixed rail to column 3 while preserving the same
    # contextual visibility policy.
    def _sync_metric_rail(self) -> None:
        if not hasattr(self, "metrics_rail"):
            return
        mode = self._metric_rail_mode()
        if mode is MetricRailMode.HIDDEN:
            self.metrics_rail.grid_remove()
            if self.rail_sash is not None:
                self.rail_sash.grid_remove()
            self.body.grid_columnconfigure(2, minsize=0)
            self.body.grid_columnconfigure(3, minsize=0)
            self.metrics_toggle.pack_forget()
            self.metrics_drawer.place_forget()
            self._drawer_open = False
            return
        if mode is MetricRailMode.DRAWER:
            self.metrics_rail.grid_remove()
            if self.rail_sash is not None:
                self.rail_sash.grid_remove()
            self.body.grid_columnconfigure(2, minsize=0)
            self.body.grid_columnconfigure(3, minsize=0)
            self.metrics_toggle.pack(side="right", padx=6, pady=8)
            return
        self.metrics_toggle.pack_forget()
        self.metrics_drawer.place_forget()
        self._drawer_open = False
        self.body.grid_columnconfigure(2, minsize=self.SASH_WIDTH)
        self.body.grid_columnconfigure(3, minsize=self._rail_width)
        if self.rail_sash is not None:
            self.rail_sash.grid(row=0, column=2, sticky="ns", pady=12)
        self.metrics_rail.grid(row=0, column=3, sticky="nsew")

    def _toggle_metrics_drawer(self) -> None:
        if self._metric_rail_mode() is not MetricRailMode.DRAWER:
            self._drawer_open = False
            self.metrics_drawer.place_forget()
            return
        self._drawer_open = not self._drawer_open
        if self._drawer_open:
            self.metrics_drawer.place(
                relx=1.0,
                rely=0,
                relheight=1.0,
                width=self._rail_width,
                anchor="ne",
            )
            self.metrics_drawer.lift()
        else:
            self.metrics_drawer.place_forget()

    # ------------------------------------------------------------------
    # Hidden-scroll rails.  No visible scrollbar is required; wheel input is
    # routed to whichever Instruments/Metrics canvas is under the pointer.
    # ------------------------------------------------------------------
    def _new_hidden_scroller(self, parent: tk.Frame) -> tuple[tk.Canvas, tk.Frame]:
        canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0, takefocus=False)
        self._register(canvas, background="surface.navigation")
        canvas.pack(fill="both", expand=True)
        content = self._frame(canvas, "surface.navigation")
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda _event, c=canvas: c.configure(scrollregion=c.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event, c=canvas, w=window: c.itemconfigure(w, width=max(1, event.width)),
        )
        self._wheel_scroll_views.append({"canvas": canvas, "content": content})
        return canvas, content

    def _build_instrument_view(self, parent: tk.Frame, *, drawer: bool) -> dict[str, Any]:
        header = self._frame(parent, "surface.navigation")
        header.pack(fill="x", padx=10, pady=(6, 3))
        self._label(
            header,
            "LEGACY INSTRUMENTS",
            surface="surface.navigation",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="left")
        if drawer:
            self._button(header, "×", self._toggle_metrics_drawer, width=2).pack(side="right")

        host = self._frame(parent, "surface.navigation")
        host.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        canvas, content = self._new_hidden_scroller(host)
        return {
            "canvas": canvas,
            "content": content,
            "sections": {},
        }

    def _build_metrics_rail(self, parent: tk.Frame, *, drawer: bool) -> None:
        shell = self._frame(parent, "surface.navigation")
        shell.pack(fill="both", expand=True)

        tabs = self._frame(shell, "surface.navigation")
        tabs.pack(fill="x", padx=9, pady=(10, 4))
        instrument_button = self._button(
            tabs,
            "Instruments",
            lambda p=parent: self._select_rail_mode(p, "instruments"),
        )
        instrument_button.pack(side="left", fill="x", expand=True, padx=(0, 2))
        metrics_button = self._button(
            tabs,
            "Metrics",
            lambda p=parent: self._select_rail_mode(p, "metrics"),
        )
        metrics_button.pack(side="left", fill="x", expand=True, padx=(2, 0))

        instrument_host = self._frame(shell, "surface.navigation")
        metrics_host = self._frame(shell, "surface.navigation")
        instrument_host.pack(fill="both", expand=True)

        view = self._build_instrument_view(instrument_host, drawer=drawer)
        view.update(
            {
                "parent": parent,
                "instrument_host": instrument_host,
                "metrics_host": metrics_host,
                "instrument_button": instrument_button,
                "metrics_button": metrics_button,
            }
        )
        self._instrument_views.append(view)
        self._instrument_mode[id(parent)] = "instruments"

        _metrics_canvas, metrics_content = self._new_hidden_scroller(metrics_host)
        # Call the pre-OBSERVE1 metric-card implementation directly so cards
        # live inside the hidden scroller instead of growing the rail itself.
        ObserverLauncher2TelemetryShell._build_metrics_rail(
            self,
            metrics_content,
            drawer=drawer,
        )
        self._apply_rail_width()

    def _is_descendant(self, widget: tk.Misc | None, ancestor: tk.Misc) -> bool:
        current = widget
        while current is not None:
            if current is ancestor:
                return True
            current = getattr(current, "master", None)
        return False

    def _on_rail_mousewheel(self, event: tk.Event):
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
        except tk.TclError:
            return None
        target: tk.Canvas | None = None
        for view in self._wheel_scroll_views:
            canvas = view["canvas"]
            content = view["content"]
            try:
                alive = bool(canvas.winfo_exists())
            except tk.TclError:
                alive = False
            if not alive:
                continue
            if widget is canvas or self._is_descendant(widget, content):
                target = canvas
                break
        if target is None:
            return None

        number = getattr(event, "num", None)
        if number == 4:
            units = -3
        elif number == 5:
            units = 3
        else:
            delta = int(getattr(event, "delta", 0) or 0)
            if delta == 0:
                return "break"
            units = -max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120)
        target.yview_scroll(units, "units")
        return "break"

    # ------------------------------------------------------------------
    # Live text is clipped/wrapped inside fixed-height chrome; it may change
    # content but may not negotiate new viewer geometry every frame.
    # ------------------------------------------------------------------
    def _build_observation(self) -> None:
        super()._build_observation()
        self._apply_stable_geometry()

    def _apply_stable_geometry(self) -> None:
        if not hasattr(self, "observation"):
            return
        try:
            if not self.observation.winfo_exists():
                return
        except tk.TclError:
            return

        self.observation.grid_rowconfigure(1, weight=1, minsize=360)

        if hasattr(self, "run_status_label"):
            controls = getattr(
                self,
                "observation_controls",
                self.run_status_label.master,
            )
            controls.configure(height=52)
            controls.grid_propagate(False)

        if hasattr(self, "field_canvas"):
            viewport = self.field_canvas.master
            viewport.configure(width=900, height=560)
            viewport.grid_propagate(False)
            self.field_canvas.configure(width=900, height=500)

        if self.legacy_chronicle_label is not None:
            chronicle = self.legacy_chronicle_label.master
            chronicle.configure(height=70)
            chronicle.pack_propagate(False)
            self.legacy_chronicle_label.configure(anchor="w", justify="left")
        if self.legacy_status_label is not None:
            self.legacy_status_label.configure(anchor="w", justify="left")

        if hasattr(self, "state_strip_frame"):
            self.state_strip_frame.configure(height=38)
            self.state_strip_frame.pack_propagate(False)

        self._apply_rail_width()

    # ------------------------------------------------------------------
    # CONFIG action ownership: one and only one Launch Observer button.
    # Observe1 previously repaired a stale placeholder after CONTROL1 had
    # already done so, which could create a duplicate depending on rebuild
    # order.  LAYOUT1 canonicalizes this footer without touching prior files.
    # ------------------------------------------------------------------
    def _ensure_real_launch_control(self) -> None:
        placeholders: list[tk.Button] = []
        launches: list[tk.Button] = []
        stops: list[tk.Button] = []
        for widget in self._walk(self.workspace):
            if not isinstance(widget, tk.Button):
                continue
            try:
                text = str(widget.cget("text") or "")
            except tk.TclError:
                continue
            if text == "Launch disabled in CONFIG1":
                placeholders.append(widget)
            elif text == "Launch Observer":
                launches.append(widget)
            elif text == "Stop Observer":
                stops.append(widget)

        # CONTROL1 normally replaced the placeholder already.  If not, repair
        # exactly once here.
        for widget in placeholders:
            parent = widget.master
            widget.destroy()
            launch = self._button(parent, "Launch Observer", self._launch_observer, kind="primary")
            launch.pack(side="right", padx=3, pady=7)
            launches.append(launch)

        # Keep the earliest packed launch.  Later duplicates are repair-layer
        # artifacts and have no independent state ownership.
        if launches:
            keep = launches[0]
            for widget in launches[1:]:
                try:
                    widget.destroy()
                except tk.TclError:
                    pass
            self.control_launch_button = keep

        if stops:
            keep_stop = stops[0]
            for widget in stops[1:]:
                try:
                    widget.destroy()
                except tk.TclError:
                    pass
            self.control_stop_config_button = keep_stop

        self._refresh_control_buttons()

    def _on_resize(self, event: tk.Event) -> None:
        super()._on_resize(event)
        if event.widget is self.root:
            self._sync_metric_rail()
            self._apply_rail_width()

    def close(self) -> None:
        try:
            self.root.unbind_all("<MouseWheel>")
            self.root.unbind_all("<Button-4>")
            self.root.unbind_all("<Button-5>")
        except tk.TclError:
            pass
        super().close()


__all__ = ["ObserverLauncher2LayoutShell"]
