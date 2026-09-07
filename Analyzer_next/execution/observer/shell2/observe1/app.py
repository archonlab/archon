"""OL2-OBSERVE1 UI: real legacy frames/instruments inside Launcher Observation."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from Analyzer_next.execution.observer.shell2.queue1.app import ObserverLauncher2QueueShell
from Analyzer_next.execution.observer.shell2.store import ShellRoute
from Analyzer_next.execution.observer.shell2.theme import palette_for

from .controller import ObserverPresentationController
from .model import LegacyPresentationFrame




def _viewer_rule_text(rule_id: int) -> str:
    """Return the canonical centered rule identity used by the LIVE LEGACY STREAM."""
    return f"Rule {int(rule_id):05d}"


def _viewer_context_text(
    frame: LegacyPresentationFrame,
    *,
    max_ticks: int,
    speed: float,
    experimental_context: dict[str, Any] | None = None,
) -> str:
    """Build truthful read-only live context without owning runtime state."""
    horizon = f"{int(max_ticks):,}" if int(max_ticks) > 0 else "∞"
    parts = [
        f"Tick {int(frame.tick):,} / {horizon}",
        f"x{float(speed):g}",
        f"{int(frame.width)}×{int(frame.height)}",
    ]
    context = experimental_context or {}
    role = str(context.get("role") or "").strip()
    if role:
        parts.append(role.upper())
    replicate_index = context.get("replicate_index")
    if replicate_index is not None:
        parts.append(f"rep {replicate_index}")
    return "  •  ".join(parts)

_SECTION_DEFAULTS = {
    "UNIVERSE": True,
    "LIFE": True,
    "ONTOLOGY / LIFECYCLE": True,
    "PRESSURE": False,
    "MORPHOLOGY": False,
    "KNOWLEDGE / EVIDENCE": False,
    "PERFORMANCE": False,
}


class ObserverLauncher2ObserveShell(ObserverLauncher2QueueShell):
    """Render the legacy Observer presentation stream without a second window."""

    def __init__(
        self,
        root: tk.Tk,
        store,
        analysis_controller,
        telemetry_controller,
        control_controller: ObserverPresentationController,
        queue_controller,
        *,
        animate: bool = False,
    ) -> None:
        self.presentation_controller = control_controller
        self._last_presentation_sequence = -1
        self._last_field_shape: tuple[int, int] | None = None
        self._field_rects: list[int] = []
        self._field_values: bytes | None = None
        self._instrument_views: list[dict[str, Any]] = []
        self._instrument_mode: dict[int, str] = {}
        self.legacy_chronicle_label: tk.Label | None = None
        self.legacy_status_label: tk.Label | None = None
        super().__init__(
            root,
            store,
            analysis_controller,
            telemetry_controller,
            control_controller,
            queue_controller,
            animate=animate,
        )
        root.title("ARCHON Observer Launcher 2.0 — OBSERVE1")
        if hasattr(self, "metrics_toggle"):
            self.metrics_toggle.configure(text="Instruments")
        self.footer_hint.set(
            "OBSERVE1 renders the canonical legacy Observer inside Observation"
        )
        root.after(50, self._poll_presentation)

    def _build_navigation(self) -> None:
        super()._build_navigation()
        for widget in self._walk(self.navigation):
            if not isinstance(widget, tk.Label):
                continue
            try:
                text = str(widget.cget("text") or "")
            except tk.TclError:
                continue
            if "CONTROL1 process adapter" in text:
                widget.configure(
                    text="OBSERVE1 integrated viewer\nLegacy runtime • live presentation"
                )

    # ------------------------------------------------------------------
    # Right rail: legacy instruments by default, canonical TELEM1 cards
    # remain available behind the Metrics tab.
    # ------------------------------------------------------------------
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

        super()._build_metrics_rail(metrics_host, drawer=drawer)

    def _select_rail_mode(self, parent: tk.Frame, mode: str) -> None:
        for view in self._instrument_views:
            if view.get("parent") is not parent:
                continue
            self._instrument_mode[id(parent)] = mode
            if mode == "metrics":
                view["instrument_host"].pack_forget()
                view["metrics_host"].pack(fill="both", expand=True)
            else:
                view["metrics_host"].pack_forget()
                view["instrument_host"].pack(fill="both", expand=True)
            self._theme_instrument_tabs(view, mode)
            return

    def _theme_instrument_tabs(self, view: dict[str, Any], mode: str | None = None) -> None:
        mode = mode or self._instrument_mode.get(id(view.get("parent")), "instruments")
        palette = palette_for(self.snapshot.resolved_theme)
        for name, key in (("instruments", "instrument_button"), ("metrics", "metrics_button")):
            button = view.get(key)
            if button is None:
                continue
            selected = name == mode
            button.configure(
                background=(palette["surface.selected"] if selected else palette["surface.control"]),
                foreground=(palette["chart.1"] if selected else palette["text.primary"]),
            )

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
        canvas = tk.Canvas(host, borderwidth=0, highlightthickness=0)
        self._register(canvas, background="surface.navigation")
        scrollbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

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

        sections: dict[str, dict[str, Any]] = {}
        return {
            "canvas": canvas,
            "content": content,
            "sections": sections,
        }

    def _ensure_instrument_sections(self, view: dict[str, Any], frame: LegacyPresentationFrame) -> None:
        content = view["content"]
        sections = view["sections"]
        for section in frame.sections:
            if section.title in sections:
                continue
            outer = self._frame(content, "surface.card")
            outer.pack(fill="x", pady=3)
            body = self._frame(outer, "surface.card")
            expanded = bool(_SECTION_DEFAULTS.get(section.title, False))
            header = self._button(
                outer,
                ("▼ " if expanded else "▶ ") + section.title,
                lambda title=section.title, v=view: self._toggle_instrument_section(v, title),
            )
            header.configure(anchor="w", font=("TkFixedFont", 9, "bold"), padx=8, pady=4)
            header.pack(fill="x")
            labels: dict[str, tk.Label] = {}
            for key, _value in section.rows:
                label = self._label(
                    body,
                    "",
                    surface="surface.card",
                    foreground="text.secondary",
                    font=("TkFixedFont", 8),
                )
                label.pack(fill="x", padx=8, pady=1)
                labels[key] = label
            if expanded:
                body.pack(fill="x", pady=(2, 6))
            sections[section.title] = {
                "outer": outer,
                "header": header,
                "body": body,
                "expanded": expanded,
                "labels": labels,
            }

    def _toggle_instrument_section(self, view: dict[str, Any], title: str) -> None:
        section = view["sections"].get(title)
        if not section:
            return
        section["expanded"] = not section["expanded"]
        if section["expanded"]:
            section["body"].pack(fill="x", pady=(2, 6))
            section["header"].configure(text=f"▼ {title}")
        else:
            section["body"].pack_forget()
            section["header"].configure(text=f"▶ {title}")

    def _render_instruments(self, frame: LegacyPresentationFrame) -> None:
        for view in self._instrument_views:
            self._ensure_instrument_sections(view, frame)
            for section_data in frame.sections:
                widget_section = view["sections"].get(section_data.title)
                if not widget_section:
                    continue
                labels = widget_section["labels"]
                for key, value in section_data.rows:
                    label = labels.get(key)
                    if label is not None:
                        label.configure(text=value)

    # ------------------------------------------------------------------
    # Observation route.
    # ------------------------------------------------------------------
    def _build_observation(self) -> None:
        super()._build_observation()
        self._last_field_shape = None
        self._field_rects = []
        self._field_values = None

        if hasattr(self, "state_strip_frame"):
            self.state_strip_frame.grid_configure(row=3)
        chronicle = self._frame(self.observation, "surface.card")
        chronicle.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self._label(
            chronicle,
            "LEGACY CHRONICLE",
            surface="surface.card",
            foreground="text.muted",
            font=("TkFixedFont", 8, "bold"),
        ).pack(anchor="w", padx=10, pady=(7, 2))
        self.legacy_chronicle_label = self._label(
            chronicle,
            "Waiting for Observer presentation stream…",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkFixedFont", 8),
        )
        self.legacy_chronicle_label.pack(fill="x", padx=10, pady=(0, 2))
        self.legacy_status_label = self._label(
            chronicle,
            "",
            surface="surface.card",
            foreground="text.muted",
            font=("TkFixedFont", 7),
        )
        self.legacy_status_label.pack(fill="x", padx=10, pady=(0, 7))
        self._draw_field()

    def _draw_field(self) -> None:
        if not hasattr(self, "field_canvas"):
            return
        canvas = self.field_canvas
        try:
            if not canvas.winfo_exists():
                return
        except tk.TclError:
            return
        frame = self.presentation_controller.presentation_frame
        if frame is None:
            palette = palette_for(self.snapshot.resolved_theme)
            canvas.delete("all")
            self._field_rects = []
            self._field_values = None
            self._last_field_shape = None
            width = max(1, canvas.winfo_width())
            height = max(1, canvas.winfo_height())
            canvas.create_text(
                width / 2,
                height / 2,
                text=(
                    "WAITING FOR LEGACY OBSERVER STREAM\n"
                    "Launch a validated run or start the queue"
                ),
                fill=palette["text.muted"],
                justify="center",
                font=("TkDefaultFont", 10, "bold"),
            )
            return
        self._render_field_frame(frame)

    @staticmethod
    def _legacy_rgb(value: int) -> str:
        a = max(0.0, min(1.0, int(value) / 255.0))
        blue = int((1.0 - a) * 230)
        yellow = int(a * 255)
        green = int(120 + 90 * (1.0 - abs(a - 0.5) * 2))
        return f"#{yellow:02x}{green:02x}{blue:02x}"

    def _render_field_frame(self, frame: LegacyPresentationFrame) -> None:
        canvas = self.field_canvas
        width_px = max(1, canvas.winfo_width())
        height_px = max(1, canvas.winfo_height())
        cell = max(1, min(width_px // frame.width, height_px // frame.height))
        field_width = frame.width * cell
        field_height = frame.height * cell
        offset_x = max(0, (width_px - field_width) // 2)
        offset_y = max(0, (height_px - field_height) // 2)
        shape = (frame.width, frame.height)

        if self._last_field_shape != shape or len(self._field_rects) != len(frame.field):
            canvas.delete("all")
            self._field_rects = []
            for row in range(frame.height):
                for column in range(frame.width):
                    x0 = offset_x + column * cell
                    y0 = offset_y + row * cell
                    self._field_rects.append(
                        canvas.create_rectangle(
                            x0,
                            y0,
                            x0 + cell,
                            y0 + cell,
                            outline="",
                            fill="#000000",
                        )
                    )
            self._last_field_shape = shape
            self._field_values = None
        else:
            for index, item in enumerate(self._field_rects):
                row, column = divmod(index, frame.width)
                x0 = offset_x + column * cell
                y0 = offset_y + row * cell
                canvas.coords(item, x0, y0, x0 + cell, y0 + cell)

        previous = self._field_values
        for index, value in enumerate(frame.field):
            if previous is not None and index < len(previous) and previous[index] == value:
                continue
            canvas.itemconfigure(self._field_rects[index], fill=self._legacy_rgb(value))
        self._field_values = frame.field

        palette = palette_for(self.snapshot.resolved_theme)
        canvas.delete("observe1-overlay")
        max_ticks = int(self.snapshot.run.spec.max_ticks)
        speed = float(getattr(getattr(self, "interactive_controller", None), "speed", 1.0))
        context = self.snapshot.run.spec.experimental_context
        rule_text = _viewer_rule_text(frame.rule_id)
        context_text = _viewer_context_text(
            frame,
            max_ticks=max_ticks,
            speed=speed,
            experimental_context=context,
        )
        header_width = min(max(320, width_px // 3), max(320, width_px - 32))
        left = max(16, (width_px - header_width) // 2)
        right = min(width_px - 16, left + header_width)
        canvas.create_rectangle(
            left,
            12,
            right,
            66,
            fill=palette["surface.overlay"],
            outline=palette["border.default"],
            tags=("observe1-overlay",),
        )
        canvas.create_text(
            width_px / 2,
            29,
            text=rule_text,
            fill=palette["text.primary"],
            anchor="center",
            font=("TkDefaultFont", 13, "bold"),
            tags=("observe1-overlay",),
        )
        canvas.create_text(
            width_px / 2,
            49,
            text=context_text,
            fill=palette["text.secondary"],
            anchor="center",
            font=("TkDefaultFont", 8, "bold"),
            tags=("observe1-overlay",),
        )

    def _poll_presentation(self) -> None:
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        frame = self.presentation_controller.presentation_frame
        if frame is not None and frame.sequence != self._last_presentation_sequence:
            self._last_presentation_sequence = frame.sequence
            if self.snapshot.route is ShellRoute.OBSERVATION:
                self._render_field_frame(frame)
                self._render_instruments(frame)
                if self.legacy_chronicle_label is not None:
                    self.legacy_chronicle_label.configure(text=frame.chronicle or "—")
                if self.legacy_status_label is not None:
                    self.legacy_status_label.configure(
                        text=(frame.status_bar or "").replace("\n", "   •   ")
                    )
        self.root.after(50, self._poll_presentation)

    # ------------------------------------------------------------------
    # Fix the confusing CONFIG1 placeholder and stale Tk references without
    # changing frozen CONFIG1/CONTROL1/QUEUE1 source files.
    # ------------------------------------------------------------------
    def _build_configuration_route(self) -> None:
        super()._build_configuration_route()
        self._ensure_real_launch_control()

    def _ensure_real_launch_control(self) -> None:
        stale = []
        for widget in self._walk(self.workspace):
            try:
                text = str(widget.cget("text") or "")
            except Exception:
                continue
            if text == "Launch disabled in CONFIG1":
                stale.append(widget)
        for widget in stale:
            parent = widget.master
            try:
                widget.pack_forget()
            except Exception:
                pass
            try:
                widget.destroy()
            except Exception:
                pass
            self.control_launch_button = self._button(
                parent,
                "Launch Observer",
                self._launch_observer,
                kind="primary",
            )
            self.control_launch_button.pack(side="right", padx=3, pady=7)
            if not hasattr(self, "control_stop_config_button"):
                self.control_stop_config_button = self._button(
                    parent,
                    "Stop Observer",
                    self._stop_observer,
                    kind="danger",
                )
                self.control_stop_config_button.pack(side="right", padx=3, pady=7)
        self._refresh_control_buttons()

    def _drop_dead_widget_refs(self, names: tuple[str, ...]) -> None:
        for name in names:
            widget = getattr(self, name, None)
            if widget is None:
                continue
            try:
                alive = bool(widget.winfo_exists())
            except (tk.TclError, AttributeError):
                alive = False
            if not alive:
                try:
                    delattr(self, name)
                except AttributeError:
                    pass

    def _refresh_control_buttons(self) -> None:
        self._drop_dead_widget_refs((
            "control_launch_button",
            "control_stop_config_button",
            "pause_button",
            "stop_button",
            "new_run_button",
        ))
        super()._refresh_control_buttons()

    def _refresh_queue_buttons(self) -> None:
        self._drop_dead_widget_refs((
            "queue_add_button",
            "queue_add_current_button",
            "queue_start_button",
            "queue_stop_button",
            "queue_clear_button",
            "queue_up_button",
            "queue_down_button",
            "queue_cancel_button",
            "queue_retry_button",
        ))
        super()._refresh_queue_buttons()

    def _refresh_step_theme(self, active=None) -> None:
        labels = getattr(self, "step_labels", None)
        if labels:
            for widget in labels.values():
                try:
                    if not widget.winfo_exists():
                        return
                except tk.TclError:
                    return
        super()._refresh_step_theme(active)

    def _apply_theme(self) -> None:
        super()._apply_theme()
        for view in self._instrument_views:
            self._theme_instrument_tabs(view)

    def _refresh_content(self) -> None:
        super()._refresh_content()
        frame = self.presentation_controller.presentation_frame
        if self.snapshot.route is ShellRoute.OBSERVATION:
            if frame is not None:
                self._render_instruments(frame)
                self.footer_right.configure(
                    text=(
                        f"Observer OBSERVE1  •  frame {frame.sequence}  •  "
                        f"legacy tick {frame.tick:,}  •  canonical SQLite read-only"
                    )
                )
            elif self.presentation_controller.presentation_error:
                self.footer_right.configure(
                    text=f"Observer OBSERVE1 presentation ERROR  •  {self.presentation_controller.presentation_error}"
                )


__all__ = ["ObserverLauncher2ObserveShell"]
