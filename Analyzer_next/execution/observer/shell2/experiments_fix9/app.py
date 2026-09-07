"""BRIDGE5.2: configurable Observer execution horizon for authorized runtimes.

The scientific runtime remains immutable.  An operator may shorten the concrete
Observer execution horizon before Queue handoff.  The selected horizon is
applied uniformly to every runtime row, recorded inside the reviewed RunSpec,
and re-verified against the original Stage 6.5 authorization when Queue starts.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from Analyzer_next.execution.observer.shell2.experiments_fix8.app import (
    ObserverLauncher2ExperimentsFix8Shell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute


class ObserverLauncher2ExperimentsFix9Shell(ObserverLauncher2ExperimentsFix8Shell):
    """Expose a bounded operator horizon override without rewriting science."""

    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        self.runtime_execution_horizon_var = tk.StringVar(master=root, value="")
        self.runtime_execution_autosave_var = tk.StringVar(master=root, value="")
        self.runtime_execution_note_var = tk.StringVar(master=root, value="")
        self._runtime_execution_settings_frame: tk.Widget | None = None
        self._runtime_execution_horizon_entry: tk.Widget | None = None
        self._runtime_execution_autosave_entry: tk.Widget | None = None
        self._runtime_execution_loaded_id: str | None = None
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — BRIDGE5.2")
        self.footer_hint.set(
            "BRIDGE5.2 • configurable pre-launch Observer horizon • scientific runtime remains immutable"
        )

    def _build_execution_stage(self, body: tk.Widget) -> None:
        super()._build_execution_stage(body)
        card = getattr(self, "_runtime_handoff_card", None)
        button = getattr(self, "_runtime_handoff_button", None)
        if card is None or button is None:
            return
        try:
            action = button.master
            settings = self._frame(card, "surface.card")
            settings.pack(fill="x", padx=14, pady=(0, 8), before=action)

            self._label(
                settings,
                "EXECUTION SETTINGS",
                surface="surface.card",
                foreground="text.secondary",
                font=("TkDefaultFont", 9, "bold"),
            ).pack(side="left", padx=(0, 12))

            self._label(
                settings,
                "Tick horizon",
                surface="surface.card",
                foreground="text.secondary",
            ).pack(side="left", padx=(0, 5))
            horizon = ttk.Entry(
                settings,
                textvariable=self.runtime_execution_horizon_var,
                style="OL2.TEntry",
                width=11,
            )
            horizon.pack(side="left", padx=(0, 12))

            self._label(
                settings,
                "Autosave every",
                surface="surface.card",
                foreground="text.secondary",
            ).pack(side="left", padx=(0, 5))
            autosave = ttk.Entry(
                settings,
                textvariable=self.runtime_execution_autosave_var,
                style="OL2.TEntry",
                width=11,
            )
            autosave.pack(side="left", padx=(0, 12))

            note = self._label(
                settings,
                surface="surface.card",
                foreground="text.secondary",
                font=("TkDefaultFont", 9),
            )
            note.configure(textvariable=self.runtime_execution_note_var)
            note.pack(side="left", fill="x", expand=True)

            self._runtime_execution_settings_frame = settings
            self._runtime_execution_horizon_entry = horizon
            self._runtime_execution_autosave_entry = autosave
        except tk.TclError:
            return
        self._sync_runtime_execution_settings(force=True)

    def _sync_runtime_execution_settings(self, *, force: bool = False) -> None:
        controller = getattr(self, "runtime_handoff_controller", None)
        if controller is None:
            return
        row = controller.snapshot.selected
        frame = self._runtime_execution_settings_frame
        horizon_entry = self._runtime_execution_horizon_entry
        autosave_entry = self._runtime_execution_autosave_entry
        prepare_button = getattr(self, "_prepare_experiment_button", None)

        if row is None or row.is_search:
            self.runtime_execution_note_var.set(
                "Observer execution settings are unavailable for this runtime."
            )
            for widget in (horizon_entry, autosave_entry):
                if widget is not None:
                    try:
                        widget.configure(state="disabled")
                    except tk.TclError:
                        pass
            if prepare_button is not None:
                try:
                    prepare_button.configure(text="Prepare in Runs")
                except tk.TclError:
                    pass
            return

        configurable = row.planned_horizon is not None and row.planned_horizon > 0
        if force or self._runtime_execution_loaded_id != row.runtime_id:
            self._runtime_execution_loaded_id = row.runtime_id
            self.runtime_execution_horizon_var.set(
                str(row.planned_horizon or "")
            )
            self.runtime_execution_autosave_var.set(
                str(row.checkpoint_interval if row.checkpoint_interval is not None else 0)
            )

        for widget in (horizon_entry, autosave_entry):
            if widget is not None:
                try:
                    widget.configure(state=("normal" if configurable else "disabled"))
                except tk.TclError:
                    pass

        if configurable:
            self.runtime_execution_note_var.set(
                f"Planned {row.planned_horizon:,} ticks • a shorter value is an execution override, not a protocol rewrite"
            )
        else:
            self.runtime_execution_note_var.set(
                "This runtime has non-uniform/fixed row horizons and cannot use one global override."
            )

        if prepare_button is not None:
            try:
                prepare_button.configure(
                    text=(
                        "Configure Execution"
                        if row.experiment_type == "perturbation_recovery_test"
                        else "Prepare in Runs"
                    )
                )
            except tk.TclError:
                pass

    def _refresh_runtime_handoff_summary(self) -> None:
        super()._refresh_runtime_handoff_summary()
        self._sync_runtime_execution_settings()

    def _prepare_selected_experiment_in_runs(self) -> None:
        controller = getattr(self, "runtime_handoff_controller", None)
        if controller is not None:
            experiment = self.experiment_controller.snapshot.selected_experiment
            if experiment is not None:
                try:
                    controller.refresh(experiment.experiment_id)
                except Exception:
                    pass
                row = controller.snapshot.selected
                if (
                    row is not None
                    and row.experiment_type == "perturbation_recovery_test"
                    and row.status in {"READY_FOR_LAUNCH_REVIEW", "LAUNCH_AUTHORIZED"}
                ):
                    self._sync_runtime_execution_settings()
                    entry = self._runtime_execution_horizon_entry
                    if entry is not None:
                        try:
                            entry.focus_set()
                            entry.selection_range(0, "end")
                        except tk.TclError:
                            pass
                    self.footer_hint.set(
                        f"{row.runtime_id}: configure Tick horizon here, then use the authorized runtime handoff below. "
                        "Perturbation rows require BRIDGE5 specialized execution and are not projected through generic Runs review."
                    )
                    return
        super()._prepare_selected_experiment_in_runs()

    def _runtime_execution_values_for_handoff(self, row) -> tuple[int | None, int | None]:
        if row.planned_horizon is None:
            return None, None
        try:
            horizon = int(self.runtime_execution_horizon_var.get().strip())
            autosave = int(self.runtime_execution_autosave_var.get().strip())
        except ValueError as exc:
            raise ValueError("Tick horizon and Autosave every must be integers") from exc
        if horizon < 1:
            raise ValueError("Tick horizon must be positive")
        if horizon > row.planned_horizon:
            raise ValueError(
                f"Tick horizon may shorten the planned {row.planned_horizon:,} ticks, but may not extend it"
            )
        if autosave < 0:
            raise ValueError("Autosave every cannot be negative")
        if autosave > horizon:
            autosave = horizon
            self.runtime_execution_autosave_var.set(str(autosave))
        return horizon, autosave

    def _runtime_execution_confirmation_text(
        self,
        row,
        execution_horizon: int | None,
        autosave_every: int | None,
    ) -> str:
        if row.planned_horizon is None:
            return ""
        effective = execution_horizon if execution_horizon is not None else row.planned_horizon
        return (
            f"Planned horizon: {row.planned_horizon:,}\n"
            f"Execution horizon: {effective:,}\n"
            f"Autosave every: {autosave_every if autosave_every is not None else 'planned'}\n\n"
            "A shorter execution horizon is applied uniformly to every matched row and recorded in RunSpec provenance. "
            "The scientific runtime/package is not rewritten. "
        )


__all__ = ["ObserverLauncher2ExperimentsFix9Shell"]
