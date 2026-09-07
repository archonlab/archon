"""OL2-INTERACT1: real Observation controls over stable LAYOUT1 geometry."""
from __future__ import annotations

import tkinter as tk
from typing import Any

from Analyzer_next.execution.observer.shell2.layout1.app import ObserverLauncher2LayoutShell
from Analyzer_next.execution.observer.shell2.observe1.model import LegacyPresentationFrame
from Analyzer_next.execution.observer.shell2.theme import palette_for
from Analyzer_next.execution.observer.state import RunState

from .controller import ObserverInteractiveController


class ObserverLauncher2InteractShell(ObserverLauncher2LayoutShell):
    """Turn Observation chrome into actual controls without moving science into UI."""

    ZOOM_LEVELS = (0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 3.00)

    def __init__(self, *args, **kwargs) -> None:
        control = kwargs.get("control_controller")
        if control is None and len(args) >= 5:
            control = args[4]
        if not isinstance(control, ObserverInteractiveController):
            raise TypeError("INTERACT1 requires ObserverInteractiveController")
        self.interactive_controller = control
        self._zoom = 1.0
        self._grid_visible = True
        self._fullscreen = False
        self._render_cell_px = 1
        self.zoom_label: tk.Label | None = None
        self.speed_label_widget: tk.Label | None = None
        self.grid_button: tk.Button | None = None
        self.cell_px_label: tk.Label | None = None
        self.speed_minus_button: tk.Button | None = None
        self.speed_plus_button: tk.Button | None = None
        self._run_menu: tk.Menu | None = None
        super().__init__(*args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — INTERACT1")
        self.footer_hint.set(
            "INTERACT1 real pause/resume + runtime speed • local zoom/grid/fullscreen"
        )
        self.root.bind("<Escape>", self._escape_fullscreen, add="+")
        self.root.bind("<Control-minus>", lambda _e: self._change_zoom(-1), add="+")
        self.root.bind("<Control-plus>", lambda _e: self._change_zoom(1), add="+")
        self.root.bind("<Control-equal>", lambda _e: self._change_zoom(1), add="+")

    # ------------------------------------------------------------------
    # Replace SHELL1 decorative viewport text with actual buttons once.
    # ------------------------------------------------------------------
    def _build_observation(self) -> None:
        super()._build_observation()
        viewport = self.field_canvas.master
        for child in tuple(viewport.winfo_children()):
            if child is self.field_canvas:
                continue
            try:
                child.destroy()
            except tk.TclError:
                pass

        toolbar = self._frame(viewport, "surface.elevated")
        toolbar.grid(row=1, column=0, sticky="ew", padx=8, pady=8)

        zoom_group = self._frame(toolbar, "surface.elevated")
        zoom_group.pack(side="left", padx=(10, 16), pady=6)
        self._label(
            zoom_group,
            "ZOOM",
            surface="surface.elevated",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="left", padx=(0, 6))
        self._button(zoom_group, "−", lambda: self._change_zoom(-1), width=2).pack(side="left")
        self.zoom_label = self._label(
            zoom_group,
            "100%",
            surface="surface.elevated",
            foreground="text.primary",
            font=("TkDefaultFont", 9, "bold"),
        )
        self.zoom_label.pack(side="left", padx=7)
        self._button(zoom_group, "+", lambda: self._change_zoom(1), width=2).pack(side="left")
        self._button(zoom_group, "⛶", self._toggle_fullscreen, width=2).pack(side="left", padx=(6, 0))

        speed_group = self._frame(toolbar, "surface.elevated")
        speed_group.pack(side="left", padx=12, pady=6)
        self._label(
            speed_group,
            "SPEED",
            surface="surface.elevated",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="left", padx=(0, 6))
        self.speed_minus_button = self._button(speed_group, "−", lambda: self._change_speed(-1), width=2)
        self.speed_minus_button.pack(side="left")
        self.speed_label_widget = self._label(
            speed_group,
            f"x{self.interactive_controller.speed}",
            surface="surface.elevated",
            foreground="text.primary",
            font=("TkDefaultFont", 9, "bold"),
        )
        self.speed_label_widget.pack(side="left", padx=7)
        self.speed_plus_button = self._button(speed_group, "+", lambda: self._change_speed(1), width=2)
        self.speed_plus_button.pack(side="left")

        grid_group = self._frame(toolbar, "surface.elevated")
        grid_group.pack(side="right", padx=(12, 10), pady=6)
        self.grid_button = self._button(grid_group, "GRID ON", self._toggle_grid)
        self.grid_button.pack(side="left")
        self.cell_px_label = self._label(
            grid_group,
            "1 px",
            surface="surface.elevated",
            foreground="text.secondary",
            font=("TkDefaultFont", 8, "bold"),
        )
        self.cell_px_label.pack(side="left", padx=(8, 0))

        self.pause_button.configure(command=self._pause_or_resume)
        self.more_button.configure(command=self._show_run_menu)
        self._refresh_interaction_controls()

    # ------------------------------------------------------------------
    # Runtime controls.  Controller owns state, adapter owns process I/O.
    # ------------------------------------------------------------------
    def _pause_or_resume(self) -> None:
        run = self.interactive_controller.snapshot.run
        if run is None:
            self.footer_hint.set("Pause/Resume refused: no active Observer")
            return
        try:
            if run.state is RunState.RUNNING:
                snapshot = self.interactive_controller.pause()
                message = "Pause requested; waiting for legacy runtime acknowledgement"
            elif run.state is RunState.PAUSED:
                snapshot = self.interactive_controller.resume()
                message = "Resume requested; waiting for legacy runtime acknowledgement"
            else:
                self.footer_hint.set(f"Pause/Resume unavailable from {run.state.value}")
                return
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Interactive control refused: {exc}")
            return
        self.control_store.sync_control(
            snapshot,
            elapsed_seconds=self.interactive_controller.elapsed_seconds,
        )
        self.footer_hint.set(message)
        self._refresh_control_buttons()

    def _change_speed(self, direction: int) -> None:
        levels = self.interactive_controller.SPEED_LEVELS
        current = self.interactive_controller.speed
        try:
            index = levels.index(current)
        except ValueError:
            index = min(range(len(levels)), key=lambda i: abs(levels[i] - current))
        index = max(0, min(len(levels) - 1, index + (1 if direction > 0 else -1)))
        requested = levels[index]
        if requested == current:
            return
        try:
            self.interactive_controller.set_speed(requested)
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Speed change refused: {exc}")
            return
        self.footer_hint.set(f"Speed x{requested} requested; awaiting runtime acknowledgement")

    def _save_checkpoint(self) -> None:
        try:
            self.interactive_controller.save_checkpoint()
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Checkpoint refused: {exc}")
            return
        self.footer_hint.set("Manual checkpoint requested from legacy Observer")

    # ------------------------------------------------------------------
    # Presentation-only controls.
    # ------------------------------------------------------------------
    def _change_zoom(self, direction: int) -> None:
        index = self.ZOOM_LEVELS.index(self._zoom)
        index = max(0, min(len(self.ZOOM_LEVELS) - 1, index + (1 if direction > 0 else -1)))
        value = self.ZOOM_LEVELS[index]
        if value == self._zoom:
            return
        self._zoom = value
        if self.zoom_label is not None:
            self.zoom_label.configure(text=f"{int(round(value * 100))}%")
        frame = self.presentation_controller.presentation_frame
        if frame is not None:
            self._field_values = None
            self._render_field_frame(frame)

    def _reset_zoom(self) -> None:
        self._zoom = 1.0
        if self.zoom_label is not None:
            self.zoom_label.configure(text="100%")
        frame = self.presentation_controller.presentation_frame
        if frame is not None:
            self._field_values = None
            self._render_field_frame(frame)

    def _toggle_grid(self) -> None:
        self._grid_visible = not self._grid_visible
        if self.grid_button is not None:
            self.grid_button.configure(text="GRID ON" if self._grid_visible else "GRID OFF")
        frame = self.presentation_controller.presentation_frame
        if frame is not None:
            self._render_field_frame(frame)

    def _toggle_fullscreen(self) -> None:
        self._fullscreen = not self._fullscreen
        try:
            self.root.attributes("-fullscreen", self._fullscreen)
        except tk.TclError:
            self._fullscreen = False
        self.footer_hint.set("Fullscreen ON • Esc to exit" if self._fullscreen else "Fullscreen OFF")

    def _escape_fullscreen(self, _event=None):
        if not self._fullscreen:
            return None
        self._fullscreen = False
        try:
            self.root.attributes("-fullscreen", False)
        except tk.TclError:
            pass
        self.footer_hint.set("Fullscreen OFF")
        return "break"

    # ------------------------------------------------------------------
    # Real overflow menu.
    # ------------------------------------------------------------------
    def _show_run_menu(self) -> None:
        if self._run_menu is not None:
            try:
                self._run_menu.destroy()
            except tk.TclError:
                pass
        menu = tk.Menu(self.root, tearoff=False)
        self._run_menu = menu
        menu.add_command(label="Copy run ID", command=self._copy_run_id)
        menu.add_command(label="Save checkpoint", command=self._save_checkpoint)
        menu.add_separator()
        menu.add_command(label="Reset zoom", command=self._reset_zoom)
        menu.add_command(label="Toggle fullscreen", command=self._toggle_fullscreen)
        try:
            x = self.more_button.winfo_rootx()
            y = self.more_button.winfo_rooty() + self.more_button.winfo_height()
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _copy_run_id(self) -> None:
        run = self.interactive_controller.snapshot.run
        run_id = (
            self.interactive_controller.snapshot.telemetry_run_id
            or (run.run_id if run is not None else "")
        )
        if not run_id:
            self.footer_hint.set("No run identity available")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(run_id)
        self.footer_hint.set(f"Copied run ID: {run_id}")

    # ------------------------------------------------------------------
    # Stable zoom/grid renderer. Geometry is still owned by LAYOUT1.
    # ------------------------------------------------------------------
    def _render_field_frame(self, frame: LegacyPresentationFrame) -> None:
        canvas = self.field_canvas
        width_px = max(1, canvas.winfo_width())
        height_px = max(1, canvas.winfo_height())
        base_cell = max(1, min(width_px // frame.width, height_px // frame.height))
        cell = max(1, int(round(base_cell * self._zoom)))
        self._render_cell_px = cell
        if self.cell_px_label is not None:
            self.cell_px_label.configure(text=f"{cell} px")
        field_width = frame.width * cell
        field_height = frame.height * cell
        offset_x = (width_px - field_width) // 2
        offset_y = (height_px - field_height) // 2
        shape = (frame.width, frame.height)
        palette = palette_for(self.snapshot.resolved_theme)
        outline = palette["border.default"] if self._grid_visible and cell >= 4 else ""

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
                            outline=outline,
                            width=1 if outline else 0,
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
                canvas.itemconfigure(item, outline=outline, width=1 if outline else 0)

        previous = self._field_values
        for index, value in enumerate(frame.field):
            if previous is not None and index < len(previous) and previous[index] == value:
                continue
            canvas.itemconfigure(self._field_rects[index], fill=self._legacy_rgb(value))
        self._field_values = frame.field

        canvas.delete("observe1-overlay")
        canvas.create_rectangle(
            12,
            12,
            300,
            36,
            fill=palette["surface.overlay"],
            outline=palette["border.default"],
            tags=("observe1-overlay",),
        )
        canvas.create_text(
            22,
            24,
            text=f"LIVE LEGACY STREAM  •  tick {frame.tick:,}  •  zoom {int(self._zoom * 100)}%",
            fill=palette["text.secondary"],
            anchor="w",
            font=("TkDefaultFont", 8, "bold"),
            tags=("observe1-overlay",),
        )

    def _refresh_interaction_controls(self) -> None:
        snapshot = self.interactive_controller.snapshot
        run = snapshot.run
        active = self.interactive_controller.process_active
        if hasattr(self, "pause_button"):
            state = run.state if run is not None else None
            self.pause_button.configure(
                text="Resume" if state is RunState.PAUSED else ("Pausing…" if state is RunState.PAUSING else ("Resuming…" if state is RunState.RESUMING else "Pause")),
                state="normal" if active and state in {RunState.RUNNING, RunState.PAUSED} else "disabled",
            )
        speed_state = "normal" if active and run is not None and run.state in {RunState.RUNNING, RunState.PAUSED} else "disabled"
        if self.speed_minus_button is not None:
            self.speed_minus_button.configure(state=speed_state)
        if self.speed_plus_button is not None:
            self.speed_plus_button.configure(state=speed_state)
        if self.speed_label_widget is not None:
            self.speed_label_widget.configure(text=f"x{self.interactive_controller.speed}")

    def _refresh_control_buttons(self) -> None:
        super()._refresh_control_buttons()
        self._refresh_interaction_controls()

    def _refresh_content(self) -> None:
        super()._refresh_content()
        self._refresh_interaction_controls()
        if self.snapshot.route.value == "observation":
            self.footer_right.configure(
                text=(
                    f"INTERACT1 • speed x{self.interactive_controller.speed} • "
                    f"zoom {int(self._zoom * 100)}% • grid {'on' if self._grid_visible else 'off'}"
                )
            )


__all__ = ["ObserverLauncher2InteractShell"]
