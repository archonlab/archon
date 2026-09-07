"""OL2-EXPERIMENTS-FIX3: runtime policy repair + approved plan revision."""
from __future__ import annotations

import threading
import tkinter as tk

from Analyzer_next.execution.observer.shell2.experiments_fix2.app import (
    ObserverLauncher2ExperimentsFix2Shell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute


class ObserverLauncher2ExperimentsFix3Shell(ObserverLauncher2ExperimentsFix2Shell):
    """Close runtime pseudoreplication and stale approved-plan gaps."""

    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — EXPERIMENTS-FIX3")
        self.footer_hint.set(
            "EXPERIMENTS-FIX3 • legacy seed-policy repair • approved plan revision • exact READY runtime review"
        )

    # ------------------------------------------------------------------
    # Step 2: an already-approved proposal must rebuild downstream planning,
    # not commit a second human approval/governance transaction.
    # ------------------------------------------------------------------
    def _build_prepared_stage(self, body: tk.Widget) -> None:
        super()._build_prepared_stage(body)
        prepared = self.proposal_controller.snapshot.prepared
        if prepared is None or prepared.decision.upper() != "APPROVED":
            return
        button = getattr(self, "_pipeline_action_button", None)
        if button is not None:
            try:
                if button.winfo_exists():
                    button.configure(text="Rebuild Plan & Materialize")
            except tk.TclError:
                pass
        self.pipeline_status_var.set(
            "This proposal is already APPROVED. Rebuild creates/reuses a downstream planner revision; governance approval is not recommitted."
        )

    def _approve_prepared_and_materialize(self) -> None:
        prepared = self.proposal_controller.snapshot.prepared
        row = self.proposal_controller.snapshot.selected
        if (
            prepared is None
            or row is None
            or prepared.proposal_id != row.proposal_id
            or row.decision.upper() != "APPROVED"
        ):
            super()._approve_prepared_and_materialize()
            return
        if self.experiment_pipeline_controller.snapshot.busy:
            return
        if not self.dialogs.confirm(
            "Rebuild approved experiment plan",
            f"Rebuild the downstream planner/runtime revision for this already APPROVED proposal?\n\n"
            f"{prepared.title}\n\n"
            "The existing verified governance approval stays unchanged. ARCHON will rerun kind-stable planner intake, "
            "commit a new plan only if its intake identity changed, reconcile canonical targets/protocols, repair the known legacy "
            "multi-replicate seed policy when applicable, and rematerialize runtimes.\n\n"
            "Nothing will be authorized, queued, or launched automatically.",
        ):
            return
        try:
            self.experiment_pipeline_controller.begin(
                prepared.proposal_id,
                "Rebuilding approved planner/runtime revision…",
            )
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self.pipeline_status_var.set("Rebuilding approved planner/runtime revision…")
        self._build_route_content()
        threading.Thread(
            target=self._rebuild_approved_worker,
            args=(prepared.proposal_id,),
            daemon=True,
        ).start()

    def _rebuild_approved_worker(self, proposal_id: str) -> None:
        try:
            result = self.experiment_pipeline_controller.port.rebuild_approved(
                proposal_id,
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

    # ------------------------------------------------------------------
    # FIX1 reconciliation now also performs the explicit compatibility repair
    # of a legacy CANONICAL_SEED + multiple-replicate runtime policy.
    # ------------------------------------------------------------------
    def _reconcile_existing_experiments(self) -> None:
        if self.experiment_pipeline_controller.snapshot.busy:
            return
        if self.control_controller.process_active:
            self.footer_hint.set("Experiment reconciliation refused while Observer is active")
            return
        if not self.dialogs.confirm(
            "Repair policy & reconcile experiments",
            "Reconcile all committed experiment plans with canonical SQLite and runtime registries?\n\n"
            "If the persisted runtime policy still contains the known legacy contradiction CANONICAL_SEED + multiple deterministic "
            "replicates, it will be migrated explicitly to RANDOM_SEED before target/runtime regeneration.\n\n"
            "Committed plan manifests are not edited. No proposal is approved, no launch authorization is issued, Queue is not started, "
            "and Observer is not run.",
        ):
            return
        try:
            self.experiment_pipeline_controller.begin(
                "EXISTING-EXPERIMENTS",
                "Repairing compatible runtime policy and reconciling committed plans…",
            )
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self.experiment_reconcile_status_var.set(
            "Repairing compatible runtime policy and reconciling committed plans…"
        )
        self._build_route_content()
        threading.Thread(target=self._reconcile_existing_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # When a runtime is READY, Prepare in Runs should review an exact runtime
    # matrix row instead of inventing a generic 20k-tick experimental draft.
    # The first row is deterministic preview only; multi-run execution remains
    # owned by Authorized Runtime Handoff → Queue.
    # ------------------------------------------------------------------
    def _prepare_selected_experiment_in_runs(self) -> None:
        runtime_controller = getattr(self, "runtime_handoff_controller", None)
        if runtime_controller is None:
            super()._prepare_selected_experiment_in_runs()
            return
        experiment = self.experiment_controller.snapshot.selected_experiment
        if experiment is None:
            self.footer_hint.set("Select an experiment first")
            return
        try:
            runtime_controller.refresh(experiment.experiment_id)
        except Exception:
            super()._prepare_selected_experiment_in_runs()
            return
        row = runtime_controller.snapshot.selected
        if row is None or row.status not in {"READY_FOR_LAUNCH_REVIEW", "LAUNCH_AUTHORIZED"}:
            super()._prepare_selected_experiment_in_runs()
            if row is not None:
                self.footer_hint.set(
                    f"Experiment runtime {row.runtime_id} is {row.status}; reconcile/rebuild it before exact Runs review"
                )
            return
        try:
            prepared_rows = runtime_controller.port.prepare_runtime_for_review(row.runtime_id)
        except Exception as exc:
            self.footer_hint.set(f"Exact runtime review failed closed: {exc}")
            return
        if not prepared_rows:
            self.footer_hint.set(f"Runtime {row.runtime_id} has no reviewable run rows")
            return
        prepared = prepared_rows[0]
        draft = prepared.effective_draft
        if draft.world is None:
            self.footer_hint.set("Exact runtime review failed closed: runtime row has no canonical world")
            return
        try:
            self.config_store.workflow.select_world(draft.world.rule_id)
            self.config_store.update_configuration(
                provenance=draft.provenance,
                max_ticks=draft.max_ticks,
                autosave_every=draft.autosave_every,
                sample_every=draft.sample_every,
                pressure_every=draft.pressure_every,
                speed=draft.speed,
                frame_delay_ms=draft.frame_delay_ms,
                cell_size=draft.cell_size,
                auto_stop=draft.auto_stop,
                outputs=draft.outputs,
                output_dir=draft.output_dir,
                field_width=draft.field_width,
                field_height=draft.field_height,
                topology=draft.topology,
                boundary_mode=draft.boundary_mode,
                seed=draft.seed,
                experiment_id=draft.experiment_id,
                condition_id=draft.condition_id,
                experiment_role=draft.experiment_role,
                replicate_index=draft.replicate_index,
                initial_state_mode=draft.initial_state_mode,
            )
            self.config_store.review_configuration()
        except Exception as exc:
            self.footer_hint.set(f"Exact runtime review failed closed: {exc}")
            return
        self.analysis_route_active = False
        self.store.select_route(ShellRoute.RUNS)
        self.footer_hint.set(
            f"Exact runtime row prepared for review • {row.runtime_id} • row 1/{len(prepared_rows)} • "
            "execution still requires VERIFIED Stage 6.5 authorization; multi-run experiment execution belongs in Queue"
        )


__all__ = ["ObserverLauncher2ExperimentsFix3Shell"]
