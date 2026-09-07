"""OL2-EXPERIMENTS-FIX2: schema-compatible catalog + canonical target handoff."""
from __future__ import annotations

import tkinter as tk

from Analyzer_next.adapters.observer.experiment_target_context import (
    ExperimentTargetContextError,
    ExperimentTargetContextReader,
)
from Analyzer_next.execution.observer.shell2.config1.model import ProvenanceKind
from Analyzer_next.execution.observer.shell2.experiments_fix1.app import ObserverLauncher2ExperimentsFix1Shell
from Analyzer_next.execution.observer.shell2.store import ShellRoute


class ObserverLauncher2ExperimentsFix2Shell(ObserverLauncher2ExperimentsFix1Shell):
    """Use registered target identities instead of requiring a preselected world."""

    def __init__(
        self,
        root: tk.Tk,
        *args,
        experiment_target_context: ExperimentTargetContextReader,
        **kwargs,
    ) -> None:
        self.experiment_target_context = experiment_target_context
        self._target_context_error: str | None = None
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — EXPERIMENTS-FIX2")
        self.footer_hint.set(
            "EXPERIMENTS-FIX2 • schema-compatible execution catalog • canonical experiment target → Runs handoff"
        )

    def _resolved_target_context(self):
        experiment = self.experiment_controller.snapshot.selected_experiment
        if experiment is None:
            self._target_context_error = None
            return None
        try:
            context = self.experiment_target_context.resolve(experiment.experiment_id)
        except ExperimentTargetContextError as exc:
            self._target_context_error = str(exc)
            return None
        self._target_context_error = None
        return context

    def _experiment_selected(self, event: tk.Event | None = None) -> None:
        super()._experiment_selected(event)
        if self.experiment_workflow_stage != "execution":
            return
        context = self._resolved_target_context()
        if context is not None and context.condition_id:
            if context.condition_id in {row.condition_id for row in self.experiment_controller.snapshot.conditions}:
                try:
                    self.experiment_controller.select_condition(context.condition_id)
                except ValueError:
                    pass
        self._populate_condition_table()
        self._refresh_experiment_context_summary()

    def _populate_condition_table(self) -> None:
        tree = self.experiment_condition_tree
        if tree is None:
            return
        try:
            if not tree.winfo_exists():
                return
        except tk.TclError:
            return
        tree.delete(*tree.get_children())
        snap = self.experiment_controller.snapshot
        context = self._resolved_target_context()
        rows = snap.conditions
        if context is not None and context.condition_id:
            rows = tuple(row for row in rows if row.condition_id == context.condition_id)
        for row in rows:
            tree.insert(
                "",
                "end",
                iid=row.condition_id,
                values=(
                    row.condition_id,
                    row.name,
                    f"{row.field_width}×{row.field_height}",
                    row.topology,
                    row.boundary_mode,
                    row.initial_state_mode,
                    row.linked_run_count,
                ),
            )
        selected = snap.selected_condition_id
        if context is not None and context.condition_id and tree.exists(context.condition_id):
            selected = context.condition_id
        if selected and tree.exists(selected):
            tree.selection_set(selected)
            tree.focus(selected)
            tree.see(selected)

    def _refresh_experiment_context_summary(self) -> None:
        snap = self.experiment_controller.snapshot
        experiment = snap.selected_experiment
        if experiment is None:
            self.experiment_context_var.set("Select an experiment.")
            return
        context = self._resolved_target_context()
        if context is None:
            detail = self._target_context_error or "Canonical target context is unavailable."
            self.experiment_context_var.set(f"{experiment.experiment_id} • target unresolved • {detail}")
            return
        condition = next(
            (row for row in snap.conditions if row.condition_id == context.condition_id),
            snap.selected_condition,
        )
        rules = ", ".join(f"Rule {rule_id:05d}" for rule_id in context.rule_ids)
        condition_text = context.condition_id or "condition unresolved"
        geometry = ""
        if condition is not None:
            geometry = f" • {condition.field_width}×{condition.field_height} {condition.topology}/{condition.boundary_mode}"
        self.experiment_context_var.set(
            f"Canonical target: {rules} • {experiment.experiment_id} → {condition_text}{geometry} • "
            "Prepare in Runs binds this registered target automatically; Validate & Review is still required before execution."
        )

    def _prepare_selected_experiment_in_runs(self) -> None:
        if self.control_controller.process_active:
            self.footer_hint.set("Experiment handoff refused while Observer is active • Stop the current run first")
            return
        snap = self.experiment_controller.snapshot
        experiment = snap.selected_experiment
        if experiment is None:
            self.footer_hint.set("Select an experiment first")
            return
        context = self._resolved_target_context()
        if context is None:
            self.footer_hint.set(f"Experiment handoff failed closed: {self._target_context_error or 'target unresolved'}")
            return
        if len(context.rule_ids) != 1:
            self.footer_hint.set(
                "Experiment has multiple canonical targets: "
                + ", ".join(f"{value:05d}" for value in context.rule_ids)
                + " • choose the intended target in Worlds before preparing"
            )
            self.store.select_route(ShellRoute.WORLDS)
            return
        rule_id = context.rule_ids[0]
        world = next((row for row in self.config_store.config_snapshot.worlds if row.rule_id == rule_id), None)
        if world is None:
            self.footer_hint.set(f"Experiment target Rule {rule_id:05d} is not present in the canonical world catalog")
            return
        condition = next(
            (row for row in snap.conditions if context.condition_id and row.condition_id == context.condition_id),
            None,
        )
        if condition is None:
            self.footer_hint.set(
                f"Experiment handoff failed closed: canonical condition {context.condition_id or 'unresolved'} is not in telemetry"
            )
            return
        role = self.experiment_role_context_var.get()
        try:
            # Select the canonical target inside CONFIG1 without route side effects,
            # then publish the fully-bound experimental draft in one visible handoff.
            self.config_store.workflow.select_world(rule_id)
            replicate_index = self.experiment_controller.next_replicate_index(rule_id=rule_id, role=role)
            self.config_store.update_configuration(
                provenance=ProvenanceKind.EXPERIMENTAL,
                experiment_id=experiment.experiment_id,
                condition_id=condition.condition_id,
                experiment_role=role,
                replicate_index=replicate_index,
                field_width=condition.field_width,
                field_height=condition.field_height,
                topology=condition.topology,
                boundary_mode=condition.boundary_mode,
                initial_state_mode=condition.initial_state_mode,
                seed=None,
            )
        except Exception as exc:
            self.footer_hint.set(f"Experiment handoff failed closed: {exc}")
            return
        self.analysis_route_active = False
        self.store.select_route(ShellRoute.RUNS)
        self.footer_hint.set(
            f"Experimental context prepared for Rule {rule_id:05d} • {experiment.experiment_id}/{condition.condition_id} • Validate & Review required"
        )


__all__ = ["ObserverLauncher2ExperimentsFix2Shell"]
