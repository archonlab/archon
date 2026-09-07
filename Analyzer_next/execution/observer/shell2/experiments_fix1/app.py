"""OL2-EXPERIMENTS-FIX1: close the first real proposal/registry workflow gaps."""
from __future__ import annotations

import threading
import tkinter as tk

from Analyzer_next.execution.observer.shell2.mutations2.app import (
    ObserverLauncher2Mutations2Shell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute
from Analyzer_next.execution.observer.shell2.functions1f.model import ExperimentPipelineResult


class ObserverLauncher2ExperimentsFix1Shell(ObserverLauncher2Mutations2Shell):
    """Expose explicit Director revalidation and existing-plan reconciliation."""

    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        super().__init__(root, *args, **kwargs)
        self.experiment_reconcile_status_var = tk.StringVar(
            master=root,
            value=(
                "Existing committed experiment plans have not been reconciled "
                "in this Launcher session."
            ),
        )
        self.root.title("ARCHON Observer Launcher 2.0 — EXPERIMENTS-FIX1")
        self.footer_hint.set(
            "EXPERIMENTS-FIX1 • merge-safe additive proposals • full registry reconciliation • no auto launch"
        )

    # ------------------------------------------------------------------
    # Proposal step: refresh the *Director*, not only the JSON projection.
    # ------------------------------------------------------------------
    def _render_proposal_actions(self) -> None:
        actions = self.proposal_actions_frame
        if actions is None:
            return
        try:
            if not bool(actions.winfo_exists()):
                return
        except tk.TclError:
            return
        for child in actions.winfo_children():
            child.destroy()

        self._button(actions, "Open Director Report", self._open_director_report).pack(side="left")
        revalidate = self._button(actions, "Revalidate Director", self._revalidate_director)
        revalidate.pack(side="left", padx=(6, 0))

        selected = self.proposal_controller.snapshot.selected
        busy = self.experiment_pipeline_controller.snapshot.busy
        if busy:
            revalidate.configure(state="disabled")
        if selected is None:
            return
        if selected.can_prepare:
            button = self._button(
                actions,
                "Prepare Experiment",
                self._prepare_director_proposal,
                kind="primary",
            )
            button.pack(side="right")
            if busy:
                button.configure(state="disabled")
        elif selected.ui_status == "NEEDS REVIEW":
            # A genuine conflicting replace/mixed-operation proposal still needs
            # field-level resolution.  Do not record another generic
            # NEEDS_REVISION decision that cannot change validation semantics.
            button = self._button(
                actions,
                "Needs Field Resolution",
                self._show_true_conflict_boundary,
                kind="primary",
            )
            button.pack(side="right")
            if busy:
                button.configure(state="disabled")
        elif selected.ui_status == "BLOCKED":
            button = self._button(actions, "Defer", self._defer_selected_proposal)
            button.pack(side="right")
            if busy:
                button.configure(state="disabled")
        else:
            self._label(
                actions,
                selected.ui_status.title(),
                surface="surface.card",
                foreground="text.secondary",
                font=("TkDefaultFont", 9, "bold"),
            ).pack(side="right", padx=8)

    def _show_true_conflict_boundary(self) -> None:
        row = self.proposal_controller.snapshot.selected
        if row is None:
            return
        resolution = row.preferred_resolution or "Explicit field-level human resolution is required."
        self.dialogs.warning(
            "Field resolution still required",
            f"{row.title}\n\nValidation: {row.validation_status}\n"
            f"Resolution type: {row.resolution_type or 'unspecified'}\n\n"
            f"Director guidance:\n{resolution}\n\n"
            "EXPERIMENTS-FIX1 no longer records a generic NEEDS_REVISION loop here. "
            "A later field-resolution step must choose the actual competing value(s).",
        )

    def _revalidate_director(self) -> None:
        if self.experiment_pipeline_controller.snapshot.busy:
            return
        try:
            self.experiment_pipeline_controller.begin(
                "DIRECTOR-REVALIDATION",
                "Revalidating Research Director proposals…",
            )
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self.pipeline_status_var.set("Revalidating Research Director proposals…")
        self._render_proposal_actions()
        threading.Thread(target=self._director_revalidation_worker, daemon=True).start()

    def _director_revalidation_worker(self) -> None:
        try:
            result = self.experiment_pipeline_controller.port.refresh_director(
                progress=self._progress_from_worker,
            )
        except Exception as exc:
            try:
                self.root.after(0, self._pipeline_failed, exc)
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._director_revalidation_completed, result)
        except tk.TclError:
            pass

    def _director_revalidation_completed(self, result: ExperimentPipelineResult) -> None:
        self.experiment_pipeline_controller.complete(result)
        self.pipeline_status_var.set(result.message)
        self.footer_hint.set(result.message)
        self.proposal_controller.clear_prepared()
        self.proposal_controller.refresh()
        if self.snapshot.route is ShellRoute.EXPERIMENTS and not self.analysis_route_active:
            self._build_route_content()

    # ------------------------------------------------------------------
    # Execution step: repair already-committed plan/target/runtime state.
    # ------------------------------------------------------------------
    def _build_execution_stage(self, body: tk.Widget) -> None:
        super()._build_execution_stage(body)
        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 12))
        self._label(
            card,
            "REGISTRY RECONCILIATION",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 4))
        text = self._label(
            card,
            surface="surface.card",
            foreground="text.primary",
            font=("TkDefaultFont", 9),
        )
        text.configure(
            textvariable=self.experiment_reconcile_status_var,
            wraplength=930,
            justify="left",
        )
        text.pack(side="left", fill="x", expand=True, padx=14, pady=(0, 10))
        button = self._button(
            card,
            "Reconcile Existing",
            self._reconcile_existing_experiments,
            kind="primary",
        )
        button.pack(side="right", padx=14, pady=(0, 10))
        if self.experiment_pipeline_controller.snapshot.busy:
            button.configure(state="disabled")
        self._label(
            card,
            "Re-resolves all already committed experiment plans into canonical target/protocol/runtime registries and SQLite. "
            "It does not approve proposals, authorize launch, start Queue, or run Observer.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w", fill="x", padx=14, pady=(0, 10))

    def _reconcile_existing_experiments(self) -> None:
        if self.experiment_pipeline_controller.snapshot.busy:
            return
        if self.control_controller.process_active:
            self.footer_hint.set("Experiment reconciliation refused while Observer is active")
            return
        if not self.dialogs.confirm(
            "Reconcile existing experiments",
            "Reconcile all already committed experiment plans with canonical SQLite and runtime registries?\n\n"
            "This can create missing canonical experiment/condition identities for verified committed plans and rewrite derived "
            "target/protocol/runtime registries.\n\nIt will NOT approve a Research Director proposal, authorize launch, start Queue, or run Observer.",
        ):
            return
        try:
            self.experiment_pipeline_controller.begin(
                "EXISTING-EXPERIMENTS",
                "Reconciling existing committed experiment plans…",
            )
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self.experiment_reconcile_status_var.set("Reconciling existing committed plans…")
        self._build_route_content()
        threading.Thread(target=self._reconcile_existing_worker, daemon=True).start()

    def _reconcile_existing_worker(self) -> None:
        try:
            result = self.experiment_pipeline_controller.port.reconcile_existing(
                progress=self._progress_from_worker,
            )
        except Exception as exc:
            try:
                self.root.after(0, self._existing_reconcile_failed, exc)
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._existing_reconcile_completed, result)
        except tk.TclError:
            pass

    def _existing_reconcile_completed(self, result: ExperimentPipelineResult) -> None:
        self.experiment_pipeline_controller.complete(result)
        self.experiment_reconcile_status_var.set(result.message)
        self.pipeline_status_var.set(result.message)
        self.footer_hint.set(result.message)
        self.experiment_controller.refresh()
        runtime_controller = getattr(self, "runtime_handoff_controller", None)
        if runtime_controller is not None:
            try:
                runtime_controller.refresh(None)
            except Exception:
                pass
        if self.snapshot.route is ShellRoute.EXPERIMENTS and not self.analysis_route_active:
            self._build_route_content()

    def _existing_reconcile_failed(self, exc: BaseException) -> None:
        self.experiment_pipeline_controller.fail(exc)
        text = str(exc)
        self.experiment_reconcile_status_var.set(f"Reconciliation stopped safely: {text}")
        self.footer_hint.set(f"Experiment reconciliation stopped safely: {text}")
        if self.snapshot.route is ShellRoute.EXPERIMENTS and not self.analysis_route_active:
            self._build_route_content()


__all__ = ["ObserverLauncher2ExperimentsFix1Shell"]
