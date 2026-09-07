"""OL2-FUNCTIONS1F: audited Research Director proposal materialization UI."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from Analyzer_next.execution.observer.shell2.functions1e.app import (
    ObserverLauncher2FunctionsExperimentWorkflowShell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute

from .controller import ExperimentPipelineController
from .model import ExperimentPipelineResult


class ObserverLauncher2FunctionsExperimentPipelineShell(
    ObserverLauncher2FunctionsExperimentWorkflowShell
):
    """Connect the simple Experiments workflow to ARCHON's audited pipeline."""

    def __init__(
        self,
        root: tk.Tk,
        *args,
        experiment_pipeline_controller: ExperimentPipelineController,
        **kwargs,
    ) -> None:
        if not isinstance(experiment_pipeline_controller, ExperimentPipelineController):
            raise TypeError("FUNCTIONS1F requires ExperimentPipelineController")
        self.experiment_pipeline_controller = experiment_pipeline_controller
        self.pipeline_status_var = tk.StringVar(master=root, value="Ready for explicit human review")
        self._pipeline_action_button: tk.Widget | None = None
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — FUNCTIONS1F")
        self.footer_hint.set(
            "FUNCTIONS1F audited proposal approval/materialization • launch authorization remains separate"
        )

    # ------------------------------------------------------------------
    # Proposal actions: keep the UI simple, but expose real audited decisions.
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
        selected = self.proposal_controller.snapshot.selected
        if selected is None:
            return
        busy = self.experiment_pipeline_controller.snapshot.busy
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
            button = self._button(
                actions,
                "Record Preferred Resolution",
                self._record_preferred_resolution,
                kind="primary",
            )
            button.pack(side="right")
            if busy:
                button.configure(state="disabled")
        elif selected.ui_status == "BLOCKED":
            button = self._button(
                actions,
                "Defer",
                self._defer_selected_proposal,
            )
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

    # ------------------------------------------------------------------
    # Step 2: append a single audited action to the human-readable review.
    # ------------------------------------------------------------------
    def _build_prepared_stage(self, body: tk.Widget) -> None:
        super()._build_prepared_stage(body)
        prepared = self.proposal_controller.snapshot.prepared
        if prepared is None:
            return

        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 12))
        self._label(
            card,
            "AUDITED MATERIALIZATION",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 4))
        status = self._label(card, surface="surface.card", foreground="text.primary", font=("TkDefaultFont", 10))
        status.configure(textvariable=self.pipeline_status_var, wraplength=980, justify="left")
        status.pack(side="left", fill="x", expand=True, padx=14, pady=(0, 10))

        snap = self.experiment_pipeline_controller.snapshot
        label = "Materializing…" if snap.busy else "Approve & Materialize"
        button = self._button(
            card,
            label,
            self._approve_prepared_and_materialize,
            kind="primary",
        )
        button.pack(side="right", padx=14, pady=(0, 10))
        if snap.busy:
            button.configure(state="disabled")
        self._pipeline_action_button = button

        self._label(
            card,
            "Commits the human approval, applies the verified Director patch, builds planner drafts, commits plans, "
            "registers canonical experiment identities and materializes runtime packages. It does NOT authorize launch or start Observer.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w", fill="x", padx=14, pady=(0, 10))

    # ------------------------------------------------------------------
    # Explicit human decisions
    # ------------------------------------------------------------------
    def _record_preferred_resolution(self) -> None:
        row = self.proposal_controller.snapshot.selected
        if row is None or row.ui_status != "NEEDS REVIEW":
            return
        guidance = row.preferred_resolution or "Use the Research Director preferred resolution."
        if not messagebox.askyesno(
            "Record preferred resolution",
            f"{row.title}\n\nDirector guidance:\n{guidance}\n\n"
            "Record this as NEEDS_REVISION?\n\nNo experiment will be launched.",
            parent=self.root,
        ):
            return
        self._start_review_decision(
            row.proposal_id,
            "NEEDS_REVISION",
            f"Observer Launcher 2.0 recorded Director preferred resolution: {guidance}",
        )

    def _defer_selected_proposal(self) -> None:
        row = self.proposal_controller.snapshot.selected
        if row is None or row.ui_status != "BLOCKED":
            return
        if not messagebox.askyesno(
            "Defer blocked proposal",
            f"{row.title}\n\nThis proposal is BLOCKED. Record it as DEFERRED?\n\nNo experiment will be launched.",
            parent=self.root,
        ):
            return
        self._start_review_decision(
            row.proposal_id,
            "DEFERRED",
            "Deferred in Observer Launcher 2.0 until Research Director prerequisites are resolved.",
        )

    def _approve_prepared_and_materialize(self) -> None:
        prepared = self.proposal_controller.snapshot.prepared
        row = self.proposal_controller.snapshot.selected
        if prepared is None or row is None or prepared.proposal_id != row.proposal_id:
            self.footer_hint.set("Prepare the selected VALID proposal first")
            return
        if not row.can_prepare:
            self.footer_hint.set(f"Proposal {row.proposal_id} is no longer VALID")
            return
        if self.experiment_pipeline_controller.snapshot.busy:
            return
        if not messagebox.askyesno(
            "Approve & materialize experiment",
            f"Approve this VALID Research Director proposal?\n\n{prepared.title}\n\n"
            f"Why:\n{prepared.rationale}\n\nDone when:\n{prepared.done_when}\n\n"
            "ARCHON will commit the audited human decision, apply the verified governance patch, "
            "build/commit the experiment plan, register canonical experiment identities, and materialize runtime packages.\n\n"
            "Launch authorization and Observer execution remain separate.",
            parent=self.root,
        ):
            return
        try:
            self.experiment_pipeline_controller.begin(
                prepared.proposal_id,
                "Starting audited Research Director → experiment materialization…",
            )
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self.pipeline_status_var.set("Starting audited materialization…")
        self._build_route_content()

        thread = threading.Thread(
            target=self._materialize_worker,
            args=(prepared.proposal_id, prepared.title),
            daemon=True,
        )
        thread.start()

    def _start_review_decision(self, proposal_id: str, decision: str, reason: str) -> None:
        try:
            self.experiment_pipeline_controller.begin(proposal_id, f"Recording {decision}…")
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self.pipeline_status_var.set(f"Recording {decision}…")
        self._render_proposal_actions()
        threading.Thread(
            target=self._review_worker,
            args=(proposal_id, decision, reason),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Workers never touch Tk directly.
    # ------------------------------------------------------------------
    def _progress_from_worker(self, stage: str, message: str) -> None:
        try:
            self.root.after(0, self._apply_pipeline_progress, stage, message)
        except tk.TclError:
            return

    def _apply_pipeline_progress(self, stage: str, message: str) -> None:
        self.experiment_pipeline_controller.progress(stage, message)
        self.pipeline_status_var.set(message)
        self.footer_hint.set(message)

    def _materialize_worker(self, proposal_id: str, title: str) -> None:
        try:
            result = self.experiment_pipeline_controller.port.approve_and_materialize(
                proposal_id,
                decision_reason=(
                    f"Approved in Observer Launcher 2.0 for audited experiment materialization: {title}"
                ),
                progress=self._progress_from_worker,
            )
        except Exception as exc:
            try:
                self.root.after(0, self._pipeline_failed, exc)
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._pipeline_completed, result)
        except tk.TclError:
            pass

    def _review_worker(self, proposal_id: str, decision: str, reason: str) -> None:
        try:
            result = self.experiment_pipeline_controller.port.record_review_decision(
                proposal_id,
                decision=decision,
                reason=reason,
                progress=self._progress_from_worker,
            )
        except Exception as exc:
            try:
                self.root.after(0, self._pipeline_failed, exc)
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._review_completed, result)
        except tk.TclError:
            pass

    def _pipeline_completed(self, result: ExperimentPipelineResult) -> None:
        self.experiment_pipeline_controller.complete(result)
        self.pipeline_status_var.set(result.message)
        self.footer_hint.set(result.message)
        self.proposal_controller.refresh()
        self.experiment_controller.refresh()
        # The target resolver has now registered canonical experiment identities,
        # so the most useful destination is the existing Execution inventory.
        self.experiment_workflow_stage = "execution"
        if self.snapshot.route is ShellRoute.EXPERIMENTS and not self.analysis_route_active:
            self._build_route_content()

    def _review_completed(self, result: ExperimentPipelineResult) -> None:
        self.experiment_pipeline_controller.complete(result)
        self.pipeline_status_var.set(result.message)
        self.footer_hint.set(result.message)
        self.proposal_controller.clear_prepared()
        self.proposal_controller.refresh()
        if self.snapshot.route is ShellRoute.EXPERIMENTS and not self.analysis_route_active:
            self._build_route_content()

    def _pipeline_failed(self, exc: BaseException) -> None:
        self.experiment_pipeline_controller.fail(exc)
        text = str(exc)
        self.pipeline_status_var.set(f"Materialization stopped safely: {text}")
        self.footer_hint.set(f"Experiment pipeline stopped safely: {text}")
        if self.snapshot.route is ShellRoute.EXPERIMENTS and not self.analysis_route_active:
            self._build_route_content()


__all__ = ["ObserverLauncher2FunctionsExperimentPipelineShell"]
