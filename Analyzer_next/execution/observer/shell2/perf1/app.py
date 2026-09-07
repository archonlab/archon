"""OL2-PERF1: keep expensive read/render work out of Tk's hot path."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from Analyzer_next.execution.observer.shell2.mutations1.app import (
    ObserverLauncher2MutationsShell,
    _STRATEGY_LABELS,
    _STRENGTHS,
)
from Analyzer_next.execution.observer.shell2.mutations1.model import MutationStrategy
from Analyzer_next.execution.observer.shell2.observe1.model import LegacyPresentationFrame
from Analyzer_next.execution.observer.shell2.theme import palette_for


class ObserverLauncher2PerfShell(ObserverLauncher2MutationsShell):
    """Presentation/performance layer; no scientific runtime semantics change."""

    def __init__(self, *args, **kwargs) -> None:
        self._perf_field_image: tk.PhotoImage | None = None
        self._perf_field_source: tk.PhotoImage | None = None
        self._perf_field_item: int | None = None
        self._perf_grid_items: list[int] = []
        self._perf_geometry_key: tuple[int, ...] | None = None
        self._perf_rgb_lut = tuple(self._rgb_bytes(i) for i in range(256))
        super().__init__(*args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — PERF1")

    @staticmethod
    def _rgb_bytes(value: int) -> bytes:
        a = max(0.0, min(1.0, int(value) / 255.0))
        blue = int((1.0 - a) * 230)
        yellow = int(a * 255)
        green = int(120 + 90 * (1.0 - abs(a - 0.5) * 2))
        return bytes((yellow, green, blue))

    # ------------------------------------------------------------------
    # MUTATIONS1 hot path: do not invalidate an already-valid preview just
    # because the same widget values were copied into the immutable draft.
    # ------------------------------------------------------------------
    def _sync_mutation_draft_from_ui(self) -> None:
        strategy = _STRATEGY_LABELS.get(
            self.mutation_strategy_var.get(), MutationStrategy.SINGLE_PARAMETER
        )
        strength = _STRENGTHS.get(self.mutation_strength_var.get(), 0.70)
        current = self.mutation_controller.snapshot.draft
        desired = current.with_updates(
            strategy=strategy,
            parameter=(self.mutation_parameter_var.get() or None),
            preset=self.mutation_preset_var.get(),
            intensity=strength,
            count=int(self.mutation_count_var.get()),
            seed=int(self.mutation_seed_var.get()),
        )
        if desired == current:
            return
        self.mutation_controller.update_draft(
            strategy=strategy,
            parameter=(self.mutation_parameter_var.get() or None),
            preset=self.mutation_preset_var.get(),
            intensity=strength,
            count=int(self.mutation_count_var.get()),
            seed=int(self.mutation_seed_var.get()),
        )

    def _create_mutation_batch(self) -> None:
        try:
            self._sync_mutation_draft_from_ui()
            preview_snap = self.mutation_controller.snapshot
            if preview_snap.preview is None:
                preview_snap = self.mutation_controller.preview()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Mutation cannot be prepared", str(exc), parent=self.root)
            return
        preview = preview_snap.preview
        assert preview is not None
        if preview.baseline_status != "resolved":
            messagebox.showerror(
                "Canonical baseline required",
                "This rule has no resolved canonical baseline/passport. Observe and save the canonical rule first.",
                parent=self.root,
            )
            return
        draft = self.mutation_controller.snapshot.draft
        if not messagebox.askyesno(
            "Create mutation batch",
            f"Create {draft.count} isolated mutation run(s) for Rule {draft.source_rule_id:05d}?\n\n"
            f"Strategy: {draft.strategy.value}\nStrength: {draft.intensity:.2f}\n"
            f"Preview changes: {preview.change_count}\n\nCanonical Atlas files will remain read-only.",
            parent=self.root,
        ):
            return
        try:
            self.mutation_controller.create_batch()
        except (ValueError, OSError, FileExistsError) as exc:
            messagebox.showerror("Mutation batch failed", str(exc), parent=self.root)
            return
        self.footer_hint.set(f"Created {draft.count} isolated mutation run(s)")
        self._build_route_content()

    def _refresh_mutation_records(self) -> None:
        port = getattr(self.mutation_controller, "port", None)
        invalidate = getattr(port, "invalidate_records", None)
        if callable(invalidate):
            invalidate()
        super()._refresh_mutation_records()

    # ------------------------------------------------------------------
    # One Canvas image instead of 6,144 rectangles + geometry calls/frame.
    # Grid is a small geometry overlay rebuilt only when geometry/theme changes.
    # ------------------------------------------------------------------
    def _reset_perf_field_renderer(self) -> None:
        """Forget Canvas handles after the Observation canvas was cleared.

        OBSERVE1 intentionally clears the field while CONTROL1 transitions
        between sequential queue processes.  PERF1 keeps the single-image item
        id for speed, so that id must be invalidated whenever the canvas no
        longer owns it.  Otherwise the next queue frame updates a deleted item
        while Instruments continue to advance normally.
        """
        self._perf_field_image = None
        self._perf_field_source = None
        self._perf_field_item = None
        self._perf_grid_items = []
        self._perf_geometry_key = None

    def _build_observation(self) -> None:
        super()._build_observation()
        self._reset_perf_field_renderer()

    def _draw_field(self) -> None:
        """Keep PERF1 image handles synchronized with OBSERVE1 canvas resets."""
        canvas = getattr(self, "field_canvas", None)
        frame = self.presentation_controller.presentation_frame
        if frame is None:
            # Queue handoff: ObserverPresentationController.start() clears the
            # previous frame before the next process emits sequence 1. Forget
            # both the Canvas item id and the prior stream sequence so even a
            # very short run whose final sequence equals the next run's first
            # sequence cannot suppress the new presentation frame.
            self._reset_perf_field_renderer()
            self._last_presentation_sequence = -1
        elif canvas is not None and self._perf_field_item is not None:
            try:
                if not canvas.type(self._perf_field_item):
                    self._reset_perf_field_renderer()
            except tk.TclError:
                self._reset_perf_field_renderer()
        super()._draw_field()

    def _render_field_frame(self, frame: LegacyPresentationFrame) -> None:
        canvas = self.field_canvas
        try:
            if not canvas.winfo_exists():
                return
        except tk.TclError:
            return

        # Any external canvas.delete("all") (theme refresh, route remount,
        # queue process handoff) invalidates the cached image id.  Recover
        # locally instead of requiring a full Observation remount.
        if self._perf_field_item is not None:
            try:
                if not canvas.type(self._perf_field_item):
                    self._reset_perf_field_renderer()
            except tk.TclError:
                self._reset_perf_field_renderer()

        width_px = max(1, canvas.winfo_width())
        height_px = max(1, canvas.winfo_height())
        base_cell = max(1, min(width_px // frame.width, height_px // frame.height))
        zoom = float(getattr(self, "_zoom", 1.0))
        cell = max(1, int(round(base_cell * zoom)))
        self._render_cell_px = cell
        if getattr(self, "cell_px_label", None) is not None:
            self.cell_px_label.configure(text=f"{cell} px")
        field_width = frame.width * cell
        field_height = frame.height * cell
        offset_x = (width_px - field_width) // 2
        offset_y = (height_px - field_height) // 2

        # Build one tiny PPM and let Tk scale it in native code.
        rgb = b"".join(self._perf_rgb_lut[value] for value in frame.field)
        ppm = f"P6\n{frame.width} {frame.height}\n255\n".encode("ascii") + rgb
        source = tk.PhotoImage(data=ppm, format="PPM")
        rendered = source if cell == 1 else source.zoom(cell, cell)
        self._perf_field_source = source
        self._perf_field_image = rendered

        if self._perf_field_item is None:
            canvas.delete("all")
            self._perf_field_item = canvas.create_image(
                offset_x,
                offset_y,
                image=rendered,
                anchor="nw",
                tags=("perf1-field",),
            )
        else:
            canvas.coords(self._perf_field_item, offset_x, offset_y)
            canvas.itemconfigure(self._perf_field_item, image=rendered)

        palette = palette_for(self.snapshot.resolved_theme)
        grid_visible = bool(getattr(self, "_grid_visible", False)) and cell >= 4
        geometry_key = (
            frame.width,
            frame.height,
            cell,
            offset_x,
            offset_y,
            int(grid_visible),
            hash(palette["border.default"]),
        )
        if geometry_key != self._perf_geometry_key:
            for item in self._perf_grid_items:
                canvas.delete(item)
            self._perf_grid_items = []
            if grid_visible:
                color = palette["border.default"]
                for column in range(frame.width + 1):
                    x = offset_x + column * cell
                    self._perf_grid_items.append(
                        canvas.create_line(x, offset_y, x, offset_y + field_height, fill=color, width=1, tags=("perf1-grid",))
                    )
                for row in range(frame.height + 1):
                    y = offset_y + row * cell
                    self._perf_grid_items.append(
                        canvas.create_line(offset_x, y, offset_x + field_width, y, fill=color, width=1, tags=("perf1-grid",))
                    )
            self._perf_geometry_key = geometry_key

        # Keep grid/overlay above the image without rebuilding field geometry.
        if self._perf_grid_items:
            canvas.tag_raise("perf1-grid")
        canvas.delete("observe1-overlay")
        canvas.create_rectangle(
            12, 12, 300, 36,
            fill=palette["surface.overlay"],
            outline=palette["border.default"],
            tags=("observe1-overlay",),
        )
        canvas.create_text(
            22, 24,
            text=f"LIVE LEGACY STREAM  •  tick {frame.tick:,}  •  zoom {int(zoom * 100)}%",
            fill=palette["text.secondary"],
            anchor="w",
            font=("TkDefaultFont", 8, "bold"),
            tags=("observe1-overlay",),
        )


__all__ = ["ObserverLauncher2PerfShell"]
