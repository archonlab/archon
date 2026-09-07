"""OL2-FUNCTIONS1D: real Experiments route over canonical read-only telemetry."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from Analyzer_next.execution.observer.shell2.config1.model import ProvenanceKind
from Analyzer_next.execution.observer.shell2.functions1c.app import (
    ObserverLauncher2FunctionsSettingsShell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute

from .controller import ExperimentCatalogController


class ObserverLauncher2FunctionsExperimentsShell(ObserverLauncher2FunctionsSettingsShell):
    """Browse canonical experiments and safely hand one context to CONFIG1."""

    def __init__(
        self,
        root: tk.Tk,
        *args,
        experiment_controller: ExperimentCatalogController,
        **kwargs,
    ) -> None:
        if not isinstance(experiment_controller, ExperimentCatalogController):
            raise TypeError("FUNCTIONS1D requires ExperimentCatalogController")
        self.experiment_controller = experiment_controller
        self.experiment_query_var = tk.StringVar(master=root)
        self.experiment_status_var = tk.StringVar(master=root, value="All")
        self.experiment_role_context_var = tk.StringVar(master=root, value="baseline")
        self.experiment_summary_var = tk.StringVar(master=root, value="Select an experiment.")
        self.experiment_context_var = tk.StringVar(master=root, value="Select a condition.")
        self._experiment_search_after: str | None = None
        self.experiment_tree: ttk.Treeview | None = None
        self.experiment_condition_tree: ttk.Treeview | None = None
        self.experiment_runs_tree: ttk.Treeview | None = None
        self._prepare_experiment_button: tk.Widget | None = None
        self._experiment_query_trace: str | None = None
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — FUNCTIONS1D")
        self._experiment_query_trace = self.experiment_query_var.trace_add(
            "write", self._experiment_search_changed
        )
        self.footer_hint.set(
            "FUNCTIONS1D canonical experiment browser • read-only catalog • explicit CONFIG1 handoff"
        )

    def _build_route_content(self) -> None:
        if not self.analysis_route_active and self.snapshot.route is ShellRoute.EXPERIMENTS:
            for child in self.workspace.winfo_children():
                child.destroy()
            self._build_experiments_route()
            return
        super()._build_route_content()

    # ------------------------------------------------------------------
    # Canonical experiment browser
    # ------------------------------------------------------------------
    def _build_experiments_route(self) -> None:
        self.experiment_controller.refresh()
        root = self._frame(self.workspace, "surface.app")
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        _canvas, body = self._new_hidden_scroller(root)

        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(
            header,
            "Experiments",
            surface="surface.card",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(side="left", padx=14, pady=12)
        self._label(
            header,
            "Canonical SQLite inventory • browsing is read-only",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)
        self._button(header, "Refresh", self._refresh_experiment_catalog).pack(
            side="right", padx=12, pady=8
        )

        filters = self._frame(body, "surface.card")
        filters.pack(fill="x", pady=(0, 8))
        self._label(filters, "Search", surface="surface.card", font=("TkDefaultFont", 9, "bold")).pack(
            side="left", padx=(14, 6), pady=9
        )
        search = ttk.Entry(
            filters,
            textvariable=self.experiment_query_var,
            style="OL2.TEntry",
        )
        search.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=7)
        self._label(filters, "Status", surface="surface.card", foreground="text.secondary").pack(side="left")
        status = ttk.Combobox(
            filters,
            textvariable=self.experiment_status_var,
            values=self._experiment_status_values(),
            state="readonly",
            width=13,
        )
        status.pack(side="left", padx=(6, 14), pady=7)
        status.bind("<<ComboboxSelected>>", lambda _e: self._apply_experiment_filters())

        experiments = self._frame(body, "surface.card")
        experiments.pack(fill="x", pady=(0, 8))
        self._label(
            experiments,
            "EXPERIMENT CATALOG",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 6))
        columns = ("id", "title", "status", "runs", "updated")
        tree = ttk.Treeview(experiments, columns=columns, show="headings", selectmode="browse", height=7, style="OL2.Treeview")
        for key, title, width, anchor in (
            ("id", "Experiment", 210, "w"),
            ("title", "Title", 430, "w"),
            ("status", "Status", 110, "center"),
            ("runs", "Runs", 70, "center"),
            ("updated", "Updated", 210, "w"),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=60, anchor=anchor)
        tree.pack(fill="x", padx=10, pady=(0, 10))
        tree.bind("<<TreeviewSelect>>", self._experiment_selected)
        self.experiment_tree = tree

        details = self._frame(body, "surface.card")
        details.pack(fill="x", pady=(0, 8))
        self._label(
            details,
            "SELECTED EXPERIMENT",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 5))
        summary = self._label(
            details,
            surface="surface.card",
            foreground="text.primary",
            font=("TkDefaultFont", 10),
        )
        summary.configure(textvariable=self.experiment_summary_var, wraplength=1120, justify="left")
        summary.pack(anchor="w", padx=14, pady=(0, 10))

        conditions = self._frame(body, "surface.card")
        conditions.pack(fill="x", pady=(0, 8))
        condition_header = self._frame(conditions, "surface.card")
        condition_header.pack(fill="x", padx=14, pady=(9, 5))
        self._label(
            condition_header,
            "CONDITIONS",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="left")
        self._label(condition_header, "Role", surface="surface.card", foreground="text.secondary").pack(side="right", padx=(10, 5))
        role = ttk.Combobox(
            condition_header,
            textvariable=self.experiment_role_context_var,
            values=("baseline", "treatment", "control", "calibration"),
            state="readonly",
            width=13,
        )
        role.pack(side="right")
        role.bind("<<ComboboxSelected>>", lambda _e: self._refresh_experiment_context_summary())

        condition_columns = ("id", "name", "field", "topology", "boundary", "initial", "linked")
        ctree = ttk.Treeview(conditions, columns=condition_columns, show="headings", selectmode="browse", height=6, style="OL2.Treeview")
        for key, title, width, anchor in (
            ("id", "Condition", 190, "w"),
            ("name", "Name", 280, "w"),
            ("field", "Field", 90, "center"),
            ("topology", "Topology", 90, "center"),
            ("boundary", "Boundary", 115, "center"),
            ("initial", "Initial state", 185, "w"),
            ("linked", "Linked runs", 95, "center"),
        ):
            ctree.heading(key, text=title)
            ctree.column(key, width=width, minwidth=55, anchor=anchor)
        ctree.pack(fill="x", padx=10, pady=(0, 6))
        ctree.bind("<<TreeviewSelect>>", self._condition_selected)
        self.experiment_condition_tree = ctree

        action = self._frame(conditions, "surface.card")
        action.pack(fill="x", padx=14, pady=(0, 10))
        context_label = self._label(
            action,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        context_label.configure(textvariable=self.experiment_context_var, wraplength=850, justify="left")
        context_label.pack(side="left", fill="x", expand=True)
        prepare_button = self._button(
            action,
            "Prepare in Runs",
            self._prepare_selected_experiment_in_runs,
            kind="primary",
        )
        prepare_button.pack(side="right", padx=(8, 0))
        self._prepare_experiment_button = prepare_button

        runs = self._frame(body, "surface.card")
        runs.pack(fill="x", pady=(0, 12))
        self._label(
            runs,
            "LINKED RUNS",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 6))
        run_columns = ("run", "rule", "condition", "role", "replicate", "created")
        rtree = ttk.Treeview(runs, columns=run_columns, show="headings", selectmode="browse", height=6, style="OL2.Treeview")
        for key, title, width, anchor in (
            ("run", "Run ID", 310, "w"),
            ("rule", "Rule", 75, "center"),
            ("condition", "Condition", 180, "w"),
            ("role", "Role", 100, "center"),
            ("replicate", "Replicate", 85, "center"),
            ("created", "Created", 210, "w"),
        ):
            rtree.heading(key, text=title)
            rtree.column(key, width=width, minwidth=55, anchor=anchor)
        rtree.pack(fill="x", padx=10, pady=(0, 10))
        self.experiment_runs_tree = rtree

        self._populate_experiment_route()

    def _experiment_status_values(self) -> tuple[str, ...]:
        statuses = sorted({row.status for row in self.experiment_controller.snapshot.experiments})
        return ("All", *statuses)

    def _experiment_search_changed(self, *_args) -> None:
        if self._experiment_search_after is not None:
            try:
                self.root.after_cancel(self._experiment_search_after)
            except tk.TclError:
                pass
        self._experiment_search_after = self.root.after(120, self._apply_experiment_filters)

    def _apply_experiment_filters(self) -> None:
        self._experiment_search_after = None
        self.experiment_controller.set_filters(
            query=self.experiment_query_var.get(),
            status=self.experiment_status_var.get(),
        )
        if self.snapshot.route is ShellRoute.EXPERIMENTS and not self.analysis_route_active:
            self._populate_experiment_table()

    def _refresh_experiment_catalog(self) -> None:
        self.experiment_controller.refresh()
        if self.snapshot.route is ShellRoute.EXPERIMENTS:
            self._populate_experiment_route()
        snap = self.experiment_controller.snapshot
        self.footer_hint.set(
            snap.error or f"Experiment catalog refreshed: {len(snap.experiments)} experiments, {len(snap.conditions)} conditions"
        )

    def _populate_experiment_route(self) -> None:
        self._populate_experiment_table()
        self._populate_condition_table()
        self._populate_experiment_runs()
        self._refresh_experiment_summary()
        self._refresh_experiment_context_summary()

    def _populate_experiment_table(self) -> None:
        tree = self.experiment_tree
        if tree is None:
            return
        tree.delete(*tree.get_children())
        snap = self.experiment_controller.snapshot
        for row in snap.visible_experiments:
            tree.insert(
                "",
                "end",
                iid=row.experiment_id,
                values=(row.experiment_id, row.title, row.status, row.run_count, row.updated_at_utc or row.created_at_utc or "—"),
            )
        if snap.selected_experiment_id and tree.exists(snap.selected_experiment_id):
            tree.selection_set(snap.selected_experiment_id)
            tree.focus(snap.selected_experiment_id)
            tree.see(snap.selected_experiment_id)

    def _populate_condition_table(self) -> None:
        tree = self.experiment_condition_tree
        if tree is None:
            return
        tree.delete(*tree.get_children())
        snap = self.experiment_controller.snapshot
        for row in snap.conditions:
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
        if snap.selected_condition_id and tree.exists(snap.selected_condition_id):
            tree.selection_set(snap.selected_condition_id)
            tree.focus(snap.selected_condition_id)
            tree.see(snap.selected_condition_id)

    def _populate_experiment_runs(self) -> None:
        tree = self.experiment_runs_tree
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for index, row in enumerate(self.experiment_controller.snapshot.runs):
            tree.insert(
                "",
                "end",
                iid=f"run-{index}",
                values=(
                    row.run_id,
                    f"{row.rule_id:05d}" if row.rule_id is not None else "—",
                    row.condition_id,
                    row.role,
                    row.replicate_index,
                    row.created_at_utc or "—",
                ),
            )

    def _experiment_selected(self, _event: tk.Event | None = None) -> None:
        tree = self.experiment_tree
        if tree is None or not tree.selection():
            return
        experiment_id = str(tree.selection()[0])
        try:
            self.experiment_controller.select_experiment(experiment_id)
        except Exception as exc:
            self.footer_hint.set(f"Experiment selection failed: {exc}")
            return
        self._populate_condition_table()
        self._populate_experiment_runs()
        self._refresh_experiment_summary()
        self._refresh_experiment_context_summary()

    def _condition_selected(self, _event: tk.Event | None = None) -> None:
        tree = self.experiment_condition_tree
        if tree is None or not tree.selection():
            return
        try:
            self.experiment_controller.select_condition(str(tree.selection()[0]))
        except Exception as exc:
            self.footer_hint.set(f"Condition selection failed: {exc}")
            return
        self._refresh_experiment_context_summary()

    def _refresh_experiment_summary(self) -> None:
        snap = self.experiment_controller.snapshot
        row = snap.selected_experiment
        if snap.error:
            self.experiment_summary_var.set(f"Catalog error: {snap.error}")
            return
        if row is None:
            self.experiment_summary_var.set("No experiments are registered in canonical telemetry.")
            return
        question = row.research_question or "No research question recorded."
        self.experiment_summary_var.set(
            f"{row.experiment_id} • {row.title} • status={row.status} • linked runs={len(snap.runs)}\n{question}"
        )

    def _refresh_experiment_context_summary(self) -> None:
        snap = self.experiment_controller.snapshot
        experiment = snap.selected_experiment
        condition = snap.selected_condition
        if experiment is None or condition is None:
            self.experiment_context_var.set("Select an experiment and condition.")
            return
        world = self.config_store.config_snapshot.draft.world
        world_text = f"Rule {world.display_id}" if world is not None else "No world selected"
        role = self.experiment_role_context_var.get()
        self.experiment_context_var.set(
            f"{world_text} • {experiment.experiment_id} → {condition.condition_id} • role={role} • "
            f"{condition.field_width}×{condition.field_height} {condition.topology}/{condition.boundary_mode} • "
            "Prepare creates a fresh experimental CONFIG1 draft; execution remains fail-closed until authorized."
        )

    def _prepare_selected_experiment_in_runs(self) -> None:
        if self.control_controller.process_active:
            self.footer_hint.set("Experiment handoff refused while Observer is active • Stop the current run first")
            return
        snap = self.experiment_controller.snapshot
        experiment = snap.selected_experiment
        condition = snap.selected_condition
        if experiment is None or condition is None:
            self.footer_hint.set("Select an experiment and condition first")
            return
        cfg = self.config_store.config_snapshot
        world = cfg.draft.world
        if world is None:
            self.footer_hint.set("Select a canonical world first; experiment context never auto-selects a rule")
            self.store.select_route(ShellRoute.WORLDS)
            return
        role = self.experiment_role_context_var.get()
        try:
            replicate_index = self.experiment_controller.next_replicate_index(
                rule_id=world.rule_id,
                role=role,
            )
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
            f"Experimental context prepared for Rule {world.display_id} • {experiment.experiment_id}/{condition.condition_id} • Validate & Review required"
        )


__all__ = ["ObserverLauncher2FunctionsExperimentsShell"]
