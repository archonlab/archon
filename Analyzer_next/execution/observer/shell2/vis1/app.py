"""OL2-VIS1: session-local visualization toggle and themed overflow surface."""
from __future__ import annotations

import tkinter as tk

from Analyzer_next.execution.observer.shell2.experiments_fix9.app import (
    ObserverLauncher2ExperimentsFix9Shell,
)
from Analyzer_next.execution.observer.shell2.observe1.model import LegacyPresentationFrame
from Analyzer_next.execution.observer.shell2.theme import palette_for

from .overflow import ObservationOverflowPopover, OverflowAction


class ObserverLauncher2VisShell(ObserverLauncher2ExperimentsFix9Shell):
    """Final RC viewer polish without changing simulation/runtime semantics.

    ``VIS OFF`` disables only field rendering in Tk.  Presentation frames keep
    flowing so Instruments, Chronicle, Queue state, telemetry and autosave stay
    live.  Re-enabling rendering draws the latest frame immediately; skipped
    frames are intentionally not replayed.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._visualization_enabled = True
        self._visualization_placeholder_drawn = False
        self.visualization_button: tk.Button | None = None
        self._overflow_popover: ObservationOverflowPopover | None = None
        super().__init__(*args, **kwargs)
        self._overflow_popover = ObservationOverflowPopover(self.root)
        self.root.title("ARCHON Observer Launcher 2.0 — VIS1")
        self.footer_hint.set(
            "VIS1 • session-local field rendering toggle • themed Observation overflow"
        )

    # ------------------------------------------------------------------
    # Observation toolbar
    # ------------------------------------------------------------------
    def _build_observation(self) -> None:
        super()._build_observation()
        grid_button = getattr(self, "grid_button", None)
        if grid_button is None:
            return
        try:
            parent = grid_button.master
            button = self._button(parent, "VIS ON", self._toggle_visualization)
            button.pack(side="left", padx=(0, 8), before=grid_button)
        except tk.TclError:
            return
        self.visualization_button = button
        self._sync_visualization_button()

    def _sync_visualization_button(self) -> None:
        button = self.visualization_button
        if button is None:
            return
        try:
            if not button.winfo_exists():
                return
            button.configure(text="VIS ON" if self._visualization_enabled else "VIS OFF")
        except tk.TclError:
            return

    def _toggle_visualization(self) -> None:
        self._visualization_enabled = not self._visualization_enabled
        self._visualization_placeholder_drawn = False
        self._sync_visualization_button()
        reset = getattr(self, "_reset_perf_field_renderer", None)
        if callable(reset):
            reset()
        frame = self.presentation_controller.presentation_frame
        if self._visualization_enabled:
            if frame is not None:
                self._render_field_frame(frame)
            else:
                self._draw_field()
            self.footer_hint.set(
                "Visualization ON • latest live field frame restored • simulation remained continuous"
            )
        else:
            self._draw_visualization_off()
            self.footer_hint.set(
                "Visualization OFF • simulation, Queue, telemetry, Instruments, Chronicle and autosave continue"
            )

    # ------------------------------------------------------------------
    # Rendering gate. Observe1 still refreshes Instruments/Chronicle after this
    # method returns, so field rendering can be disabled independently.
    # ------------------------------------------------------------------
    def _render_field_frame(self, frame: LegacyPresentationFrame) -> None:
        if not self._visualization_enabled:
            self._draw_visualization_off()
            return
        self._visualization_placeholder_drawn = False
        super()._render_field_frame(frame)

    def _draw_visualization_off(self) -> None:
        if self._visualization_placeholder_drawn:
            return
        canvas = getattr(self, "field_canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except tk.TclError:
            return
        reset = getattr(self, "_reset_perf_field_renderer", None)
        if callable(reset):
            reset()
        palette = palette_for(self.snapshot.resolved_theme)
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.create_text(
            width / 2,
            height / 2 - 16,
            text="VISUALIZATION OFF",
            fill=palette["text.secondary"],
            justify="center",
            font=("TkDefaultFont", 12, "bold"),
            tags=("vis1-placeholder",),
        )
        canvas.create_text(
            width / 2,
            height / 2 + 14,
            text="Simulation is still running • telemetry, Instruments and autosave remain active",
            fill=palette["text.muted"],
            justify="center",
            font=("TkDefaultFont", 9),
            tags=("vis1-placeholder",),
        )
        self._visualization_placeholder_drawn = True

    # ------------------------------------------------------------------
    # Themed overflow replaces native tk.Menu while preserving INTERACT1
    # commands and ownership.
    # ------------------------------------------------------------------
    def _show_run_menu(self) -> None:
        if self._overflow_popover is None:
            self._overflow_popover = ObservationOverflowPopover(self.root)
        palette = palette_for(self.snapshot.resolved_theme)
        fullscreen_label = "Exit fullscreen" if getattr(self, "_fullscreen", False) else "Enter fullscreen"
        self._overflow_popover.show(
            self.more_button,
            (
                OverflowAction("Copy run ID", self._copy_run_id),
                OverflowAction("Save checkpoint", self._save_checkpoint),
                None,
                OverflowAction("Reset zoom", self._reset_zoom),
                OverflowAction(fullscreen_label, self._toggle_fullscreen),
            ),
            palette,
        )

    def _apply_theme(self) -> None:
        popover = getattr(self, "_overflow_popover", None)
        if popover is not None:
            popover.close()
        super()._apply_theme()
        if not self._visualization_enabled:
            self._visualization_placeholder_drawn = False
            self._draw_visualization_off()
        self._sync_visualization_button()

    def close(self) -> None:
        popover = getattr(self, "_overflow_popover", None)
        if popover is not None:
            popover.close()
        super().close()


__all__ = ["ObserverLauncher2VisShell"]
