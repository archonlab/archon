"""OL2-MUTATIONS1: simple Source → Mutation → Execution workflow."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

try:  # FUNCTIONS1G is optional while Experiments remains a separate track.
    from Analyzer_next.execution.observer.shell2.functions1g.app import (
        ObserverLauncher2FunctionsExperimentQueueShell as _BaseShell,
    )
    HAS_FUNCTIONS1G = True
except ImportError:
    from Analyzer_next.execution.observer.shell2.functions1f.app import (
        ObserverLauncher2FunctionsExperimentPipelineShell as _BaseShell,
    )
    HAS_FUNCTIONS1G = False

from Analyzer_next.execution.observer.shell2.store import ShellRoute

from .controller import MutationWorkspaceController
from .model import MutationStage, MutationStrategy


_STRATEGY_LABELS = {
    "Single parameter": MutationStrategy.SINGLE_PARAMETER,
    "Preset": MutationStrategy.PRESET,
    "Local random": MutationStrategy.LOCAL_RANDOM,
}
_STRENGTHS = {
    "Low": 0.35,
    "Balanced": 0.70,
    "Strong": 1.20,
}


class ObserverLauncher2MutationsShell(_BaseShell):
    """Expose legacy mutation science through a compact OL2 workflow."""

    def __init__(
        self,
        root: tk.Tk,
        *args,
        mutation_controller: MutationWorkspaceController,
        mutation_telemetry_router=None,
        **kwargs,
    ) -> None:
        if not isinstance(mutation_controller, MutationWorkspaceController):
            raise TypeError("MUTATIONS1 requires MutationWorkspaceController")
        self.mutation_controller = mutation_controller
        self.mutation_telemetry_router = mutation_telemetry_router
        self.mutation_tree: ttk.Treeview | None = None
        self.mutation_source_tree: ttk.Treeview | None = None
        self.mutation_source_summary = tk.StringVar(master=root, value="Select a canonical source rule.")
        self.mutation_preview_summary = tk.StringVar(master=root, value="Preview has not been generated.")
        self.mutation_record_summary = tk.StringVar(master=root, value="No prepared mutation selected.")
        self.mutation_query_var = tk.StringVar(master=root)
        self.mutation_strategy_var = tk.StringVar(master=root, value="Single parameter")
        self.mutation_parameter_var = tk.StringVar(master=root)
        self.mutation_preset_var = tk.StringVar(master=root, value="balanced")
        self.mutation_strength_var = tk.StringVar(master=root, value="Balanced")
        self.mutation_count_var = tk.IntVar(master=root, value=1)
        self.mutation_seed_var = tk.IntVar(master=root, value=0)
        self._mutation_search_after: str | None = None
        self._mutation_query_trace: str | None = None
        self._mutation_parameter_combo: ttk.Combobox | None = None
        self._mutation_preset_combo: ttk.Combobox | None = None
        super().__init__(root, *args, **kwargs)
        self._mutation_query_trace = self.mutation_query_var.trace_add("write", self._mutation_query_changed)
        self.root.title("ARCHON Observer Launcher 2.0 — MUTATIONS1")
        self.footer_hint.set(
            "MUTATIONS1 Source → Mutation → Execution • canonical Atlas rules stay read-only"
        )

    def _poll_control(self) -> None:
        super()._poll_control()
        router = self.mutation_telemetry_router
        if router is None or getattr(router, "armed_database", None) is None:
            return
        snapshot = self.control_controller.snapshot
        if snapshot.run is not None and not snapshot.active:
            router.finalize_armed_database(snapshot.telemetry_run_id)

    def _build_route_content(self) -> None:
        try:
            if not self.analysis_route_active and self.snapshot.route is ShellRoute.MUTATIONS:
                for child in self.workspace.winfo_children():
                    child.destroy()
                self._build_mutations_route()
                return
            super()._build_route_content()
        finally:
            schedule = getattr(self, "_schedule_theme_reconciliation", None)
            if callable(schedule):
                schedule()

    # ------------------------------------------------------------------
    # Route/stage shell
    # ------------------------------------------------------------------
    def _build_mutations_route(self) -> None:
        snap = self.mutation_controller.snapshot
        # Route mounting must stay I/O-free.  Candidate wiring primes worlds
        # from the already-loaded CONFIG1 snapshot; an empty source catalog is
        # rendered as empty instead of triggering a second synchronous Atlas
        # scan in Tk's event loop.
        if snap.stage is MutationStage.EXECUTION:
            self.mutation_controller.refresh_records()

        root = self._frame(self.workspace, "surface.app")
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        _canvas, body = self._new_hidden_scroller(root)
        self._build_mutation_steps(body)
        stage = self.mutation_controller.snapshot.stage
        if stage is MutationStage.SOURCE:
            self._build_mutation_source(body)
        elif stage is MutationStage.MUTATION:
            self._build_mutation_editor(body)
        else:
            self._build_mutation_execution(body)

    def _build_mutation_steps(self, parent: tk.Widget) -> None:
        bar = self._frame(parent, "surface.card")
        bar.pack(fill="x", pady=(0, 8))
        for stage, label in (
            (MutationStage.SOURCE, "1 Source"),
            (MutationStage.MUTATION, "2 Mutation"),
            (MutationStage.EXECUTION, "3 Execution"),
        ):
            self._button(
                bar,
                label,
                lambda value=stage: self._set_mutation_stage(value),
                kind="primary" if self.mutation_controller.snapshot.stage is stage else "neutral",
            ).pack(side="left", padx=(8 if stage is MutationStage.SOURCE else 2, 2), pady=7)
        source = self.mutation_controller.snapshot.selected_source
        context = f"Rule {source.display_id} • {source.world_class}" if source else "No source selected"
        self._label(
            bar,
            context,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="right", padx=14)

    def _set_mutation_stage(self, stage: MutationStage) -> None:
        try:
            self.mutation_controller.set_stage(stage)
        except ValueError as exc:
            self.footer_hint.set(str(exc))
            return
        if self.snapshot.route is ShellRoute.MUTATIONS and not self.analysis_route_active:
            self._build_route_content()

    # ------------------------------------------------------------------
    # 1 Source
    # ------------------------------------------------------------------
    def _build_mutation_source(self, body: tk.Widget) -> None:
        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(header, "Mutation Source", surface="surface.card", font=("TkDefaultFont", 16, "bold")).pack(
            side="left", padx=14, pady=12
        )
        self._label(
            header,
            "Choose one verified canonical rule. The source file is never modified.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)
        self._button(header, "Refresh", self._refresh_mutation_sources).pack(side="right", padx=12, pady=8)

        filters = self._frame(body, "surface.card")
        filters.pack(fill="x", pady=(0, 8))
        self._label(filters, "Search", surface="surface.card", font=("TkDefaultFont", 9, "bold")).pack(
            side="left", padx=(14, 6), pady=9
        )
        ttk.Entry(filters, textvariable=self.mutation_query_var, style="OL2.TEntry").pack(
            side="left", fill="x", expand=True, padx=(0, 14), pady=7
        )

        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 8))
        columns = ("rule", "class", "observed", "mutations", "last")
        tree = ttk.Treeview(card, columns=columns, show="headings", selectmode="browse", height=12, style="OL2.Treeview")
        for key, title, width, anchor in (
            ("rule", "Rule", 90, "center"),
            ("class", "Class", 320, "w"),
            ("observed", "Observed", 100, "center"),
            ("mutations", "Mutations", 100, "center"),
            ("last", "Last run", 180, "w"),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor=anchor)
        tree.pack(fill="x", padx=12, pady=(10, 8))
        tree.bind("<<TreeviewSelect>>", self._mutation_source_selected)
        self.mutation_source_tree = tree
        self._fill_mutation_sources()

        detail = self._frame(body, "surface.card")
        detail.pack(fill="x", pady=(0, 8))
        label = self._label(detail, surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 10))
        label.configure(textvariable=self.mutation_source_summary, wraplength=900, justify="left")
        label.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        self._button(detail, "Use Source →", self._use_selected_mutation_source, kind="primary").pack(
            side="right", padx=14, pady=10
        )
        self._update_mutation_source_summary()

    def _fill_mutation_sources(self) -> None:
        tree = self.mutation_source_tree
        if tree is None:
            return
        try:
            if not tree.winfo_exists():
                return
        except tk.TclError:
            return
        tree.delete(*tree.get_children())
        for world in self.mutation_controller.snapshot.visible_worlds:
            tree.insert(
                "",
                "end",
                iid=str(world.rule_id),
                values=(
                    world.display_id,
                    world.world_class,
                    "Yes" if world.observed else "No",
                    world.mutation_runs,
                    world.last_run,
                ),
            )
        selected = self.mutation_controller.snapshot.selected_source_id
        if selected is not None and tree.exists(str(selected)):
            tree.selection_set(str(selected))
            tree.see(str(selected))

    def _mutation_query_changed(self, *_args) -> None:
        try:
            if self._mutation_search_after is not None:
                self.root.after_cancel(self._mutation_search_after)
        except (tk.TclError, ValueError):
            pass
        try:
            self._mutation_search_after = self.root.after(80, self._apply_mutation_source_filter)
        except tk.TclError:
            self._mutation_search_after = None

    def _apply_mutation_source_filter(self) -> None:
        self._mutation_search_after = None
        self.mutation_controller.set_query(self.mutation_query_var.get())
        self._fill_mutation_sources()

    def _mutation_source_selected(self, _event=None) -> None:
        tree = self.mutation_source_tree
        if tree is None:
            return
        selection = tree.selection()
        if not selection:
            return
        try:
            rule_id = int(selection[0])
        except ValueError:
            return
        world = next((w for w in self.mutation_controller.snapshot.worlds if w.rule_id == rule_id), None)
        if world is None:
            return
        self.mutation_source_summary.set(
            f"Rule {world.display_id} • {world.world_class} • "
            f"{'observed baseline available in catalog' if world.observed else 'catalog marks this rule as not observed'} • "
            f"existing mutation runs: {world.mutation_runs}"
        )

    def _use_selected_mutation_source(self) -> None:
        tree = self.mutation_source_tree
        selection = tree.selection() if tree is not None else ()
        if not selection:
            self.footer_hint.set("Select a canonical source rule first")
            return
        try:
            self.mutation_controller.select_source(int(selection[0]))
        except ValueError as exc:
            self.footer_hint.set(str(exc))
            return
        self.footer_hint.set(f"Mutation source set to Rule {int(selection[0]):05d}")
        self._build_route_content()

    def _refresh_mutation_sources(self) -> None:
        self.mutation_controller.refresh_sources()
        self._fill_mutation_sources()
        self.footer_hint.set("Canonical mutation source catalog refreshed")

    def _update_mutation_source_summary(self) -> None:
        source = self.mutation_controller.snapshot.selected_source
        if source is None:
            self.mutation_source_summary.set("Select a verified canonical source rule. Search accepts 251, 0251 or 00251.")
        else:
            self.mutation_source_summary.set(
                f"Current source: Rule {source.display_id} • {source.world_class} • canonical source verified"
            )

    # ------------------------------------------------------------------
    # 2 Mutation
    # ------------------------------------------------------------------
    def _build_mutation_editor(self, body: tk.Widget) -> None:
        source = self.mutation_controller.snapshot.selected_source
        if source is None:
            self._build_mutation_empty(body, "No source selected", "Choose a canonical rule before configuring a mutation.")
            return

        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(header, "Configure Mutation", surface="surface.card", font=("TkDefaultFont", 16, "bold")).pack(
            side="left", padx=14, pady=12
        )
        self._label(
            header,
            f"Rule {source.display_id} • isolated derived rule • canonical promotion OFF",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)

        settings = self._frame(body, "surface.card")
        settings.pack(fill="x", pady=(0, 8))
        grid = self._frame(settings, "surface.card")
        grid.pack(fill="x", padx=14, pady=12)
        for col in (1, 3):
            grid.grid_columnconfigure(col, weight=1)

        self._setting_label(grid, 0, 0, "Strategy")
        strategy = ttk.Combobox(
            grid,
            textvariable=self.mutation_strategy_var,
            values=tuple(_STRATEGY_LABELS),
            state="readonly",
            style="OL2.TCombobox",
        )
        strategy.grid(row=0, column=1, sticky="ew", padx=(8, 18), pady=5)
        strategy.bind("<<ComboboxSelected>>", lambda _e: self._mutation_strategy_changed())

        self._setting_label(grid, 0, 2, "Strength")
        ttk.Combobox(
            grid,
            textvariable=self.mutation_strength_var,
            values=tuple(_STRENGTHS),
            state="readonly",
            style="OL2.TCombobox",
        ).grid(row=0, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._setting_label(grid, 1, 0, "Parameter")
        choices = self.mutation_controller.parameter_choices()
        if not self.mutation_parameter_var.get() and choices:
            self.mutation_parameter_var.set(choices[0])
        parameter = ttk.Combobox(
            grid,
            textvariable=self.mutation_parameter_var,
            values=choices,
            state="readonly",
            style="OL2.TCombobox",
        )
        parameter.grid(row=1, column=1, sticky="ew", padx=(8, 18), pady=5)
        self._mutation_parameter_combo = parameter

        self._setting_label(grid, 1, 2, "Preset")
        preset = ttk.Combobox(
            grid,
            textvariable=self.mutation_preset_var,
            values=("conservative", "balanced", "aggressive", "structural", "functional"),
            state="disabled",
            style="OL2.TCombobox",
        )
        preset.grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=5)
        self._mutation_preset_combo = preset

        self._setting_label(grid, 2, 0, "Mutation runs")
        ttk.Spinbox(grid, textvariable=self.mutation_count_var, from_=1, to=20, width=10).grid(
            row=2, column=1, sticky="w", padx=(8, 18), pady=5
        )
        self._setting_label(grid, 2, 2, "Seed")
        seed = ttk.Entry(grid, textvariable=self.mutation_seed_var, style="OL2.TEntry")
        seed.grid(row=2, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._label(
            settings,
            "Seed 0 = automatic. A mutation batch is created only after a resolved canonical baseline is found. "
            "Every derived rule lives under Results/Universe_Search/mutation_runs and can never overwrite Atlas.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w", padx=14, pady=(0, 12))
        self._mutation_strategy_changed()

        preview = self._frame(body, "surface.card")
        preview.pack(fill="x", pady=(0, 8))
        top = self._frame(preview, "surface.card")
        top.pack(fill="x", padx=14, pady=(10, 6))
        self._label(top, "PREVIEW", surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 9, "bold")).pack(side="left")
        self._button(top, "Preview", self._preview_mutation).pack(side="right")
        summary = self._label(preview, surface="surface.card", foreground="text.primary", font=("TkDefaultFont", 10))
        summary.configure(textvariable=self.mutation_preview_summary, wraplength=980, justify="left")
        summary.pack(anchor="w", fill="x", padx=14, pady=(0, 10))
        self._render_mutation_preview_changes(preview)

        actions = self._frame(body, "surface.card")
        actions.pack(fill="x", pady=(0, 8))
        self._button(actions, "← Source", lambda: self._set_mutation_stage(MutationStage.SOURCE)).pack(side="left", padx=12, pady=10)
        self._button(actions, "Create Mutation Batch", self._create_mutation_batch, kind="primary").pack(side="right", padx=12, pady=10)

    def _setting_label(self, parent: tk.Widget, row: int, column: int, text: str) -> None:
        self._label(parent, text, surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 9, "bold")).grid(
            row=row, column=column, sticky="w", pady=5
        )

    def _mutation_strategy_changed(self) -> None:
        label = self.mutation_strategy_var.get()
        strategy = _STRATEGY_LABELS.get(label, MutationStrategy.SINGLE_PARAMETER)
        if self._mutation_parameter_combo is not None:
            self._mutation_parameter_combo.configure(state="readonly" if strategy is MutationStrategy.SINGLE_PARAMETER else "disabled")
        if self._mutation_preset_combo is not None:
            self._mutation_preset_combo.configure(state="readonly" if strategy is MutationStrategy.PRESET else "disabled")

    def _sync_mutation_draft_from_ui(self) -> None:
        strategy = _STRATEGY_LABELS.get(self.mutation_strategy_var.get(), MutationStrategy.SINGLE_PARAMETER)
        strength = _STRENGTHS.get(self.mutation_strength_var.get(), 0.70)
        self.mutation_controller.update_draft(
            strategy=strategy,
            parameter=(self.mutation_parameter_var.get() or None),
            preset=self.mutation_preset_var.get(),
            intensity=strength,
            count=int(self.mutation_count_var.get()),
            seed=int(self.mutation_seed_var.get()),
        )

    def _preview_mutation(self) -> None:
        try:
            self._sync_mutation_draft_from_ui()
            snap = self.mutation_controller.preview()
        except (ValueError, OSError) as exc:
            self.mutation_preview_summary.set(f"Preview unavailable: {exc}")
            self.footer_hint.set(str(exc))
            return
        preview = snap.preview
        assert preview is not None
        baseline = "resolved" if preview.baseline_status == "resolved" else "missing"
        self.mutation_preview_summary.set(
            f"{preview.change_count} field change(s) • mutated hash {preview.mutated_hash} • "
            f"preview seed {preview.seed} • baseline {baseline}: {preview.baseline_detail}"
        )
        self._build_route_content()

    def _render_mutation_preview_changes(self, parent: tk.Widget) -> None:
        preview = self.mutation_controller.snapshot.preview
        if preview is None:
            return
        changes = list(preview.changes[:8])
        if not changes:
            self._label(parent, "No fields changed.", surface="surface.card", foreground="text.secondary").pack(anchor="w", padx=14, pady=(0, 10))
            return
        for change in changes:
            text = f"{change.get('path')}: {change.get('before')} → {change.get('after')}"
            label = self._label(parent, text, surface="surface.card", foreground="text.secondary", font=("TkFixedFont", 8))
            label.configure(wraplength=980, justify="left")
            label.pack(anchor="w", padx=14, pady=1)
        if preview.change_count > len(changes):
            self._label(
                parent,
                f"… and {preview.change_count - len(changes)} more change(s)",
                surface="surface.card",
                foreground="text.muted",
                font=("TkDefaultFont", 8),
            ).pack(anchor="w", padx=14, pady=(2, 10))

    def _create_mutation_batch(self) -> None:
        try:
            self._sync_mutation_draft_from_ui()
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
            snap = self.mutation_controller.create_batch()
        except (ValueError, OSError, FileExistsError) as exc:
            messagebox.showerror("Mutation batch failed", str(exc), parent=self.root)
            return
        self.footer_hint.set(f"Created {draft.count} isolated mutation run(s)")
        self._build_route_content()

    def _build_mutation_empty(self, body: tk.Widget, title: str, detail: str) -> None:
        card = self._frame(body, "surface.card")
        card.pack(fill="x")
        self._label(card, title, surface="surface.card", font=("TkDefaultFont", 16, "bold")).pack(anchor="w", padx=14, pady=(14, 6))
        self._label(card, detail, surface="surface.card", foreground="text.secondary").pack(anchor="w", padx=14, pady=(0, 12))
        self._button(card, "Go to Source", lambda: self._set_mutation_stage(MutationStage.SOURCE), kind="primary").pack(anchor="w", padx=14, pady=(0, 14))

    # ------------------------------------------------------------------
    # 3 Execution
    # ------------------------------------------------------------------
    def _build_mutation_execution(self, body: tk.Widget) -> None:
        self.mutation_controller.refresh_records()
        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(header, "Prepared Mutations", surface="surface.card", font=("TkDefaultFont", 16, "bold")).pack(
            side="left", padx=14, pady=12
        )
        self._label(
            header,
            "Run one selected mutant explicitly. Mutation observations use manual stop/shared-horizon policy.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)
        self._button(header, "Refresh", self._refresh_mutation_records).pack(side="right", padx=12, pady=8)

        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 8))
        columns = ("mutation", "parent", "mode", "changes", "status", "created")
        tree = ttk.Treeview(card, columns=columns, show="headings", selectmode="browse", height=11, style="OL2.Treeview")
        for key, title, width, anchor in (
            ("mutation", "Mutation", 285, "w"),
            ("parent", "Parent", 85, "center"),
            ("mode", "Mode", 130, "center"),
            ("changes", "Changes", 80, "center"),
            ("status", "Status", 105, "center"),
            ("created", "Created", 165, "w"),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor=anchor)
        tree.pack(fill="x", padx=12, pady=(10, 8))
        tree.bind("<<TreeviewSelect>>", self._mutation_record_selected)
        self.mutation_tree = tree
        self._fill_mutation_records()

        detail = self._frame(body, "surface.card")
        detail.pack(fill="x", pady=(0, 8))
        label = self._label(detail, surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 10))
        label.configure(textvariable=self.mutation_record_summary, wraplength=850, justify="left")
        label.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        self._button(detail, "Open Folder", self._open_selected_mutation_folder).pack(side="right", padx=(4, 12), pady=10)
        self._button(detail, "Run Selected", self._run_selected_mutation, kind="primary").pack(side="right", padx=4, pady=10)
        self._update_mutation_record_summary()

        note = self._frame(body, "surface.card")
        note.pack(fill="x", pady=(0, 8))
        self._label(
            note,
            "Mutation Analyzer remains a separate analysis step. ANALYZED appears here when Results/Analysis/Mutations contains a mutation_report.json.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w", padx=14, pady=12)

    def _fill_mutation_records(self) -> None:
        tree = self.mutation_tree
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for record in self.mutation_controller.snapshot.records:
            tree.insert(
                "",
                "end",
                iid=record.mutation_id,
                values=(
                    record.mutation_id,
                    f"{record.parent_rule_id:05d}",
                    record.mode,
                    record.change_count,
                    record.status,
                    record.created_at,
                ),
            )
        selected = self.mutation_controller.snapshot.selected_mutation_id
        if selected and tree.exists(selected):
            tree.selection_set(selected)
            tree.see(selected)
        if not self.mutation_controller.snapshot.records:
            self.mutation_record_summary.set(
                "No mutation manifests yet. Choose a Source, configure a Mutation, then Create Mutation Batch."
            )

    def _mutation_record_selected(self, _event=None) -> None:
        tree = self.mutation_tree
        if tree is None:
            return
        selection = tree.selection()
        if not selection:
            return
        try:
            self.mutation_controller.select_record(selection[0])
        except ValueError:
            return
        self._update_mutation_record_summary()

    def _update_mutation_record_summary(self) -> None:
        record = self.mutation_controller.snapshot.selected_record
        if record is None:
            return
        target = record.parameter or record.preset or record.mode
        analyzed = f" • report {record.analysis_report}" if record.analysis_report else ""
        self.mutation_record_summary.set(
            f"{record.mutation_id} • parent Rule {record.parent_rule_id:05d} • {target} • "
            f"intensity {record.intensity:.2f} • seed {record.seed} • {record.change_count} change(s) • {record.status}{analyzed}"
        )

    def _refresh_mutation_records(self) -> None:
        self.mutation_controller.refresh_records()
        self._fill_mutation_records()
        self._update_mutation_record_summary()
        self.footer_hint.set("Mutation manifests refreshed")

    def _run_selected_mutation(self) -> None:
        if self.control_controller.process_active:
            self.footer_hint.set("Stop the active Observer before launching a mutation")
            return
        try:
            prepared = self.mutation_controller.prepare_selected_launch()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Mutation launch refused", str(exc), parent=self.root)
            return
        record = self.mutation_controller.snapshot.selected_record
        assert record is not None
        if not messagebox.askyesno(
            "Run mutation",
            f"Launch {record.mutation_id}?\n\nParent: Rule {record.parent_rule_id:05d}\n"
            f"Changes: {record.change_count}\n\nThis is an isolated mutation run. Canonical Atlas files are not modified.",
            parent=self.root,
        ):
            return
        telemetry_router = self.mutation_telemetry_router
        if telemetry_router is not None:
            telemetry_router.arm_database(record.run_dir / "telemetry.sqlite")
        try:
            snapshot = self.control_controller.start(prepared)
        except (RuntimeError, ValueError) as exc:
            if telemetry_router is not None:
                telemetry_router.clear_armed_database()
            self.footer_hint.set(f"Mutation start refused: {exc}")
            return
        if not snapshot.active and telemetry_router is not None:
            telemetry_router.clear_armed_database()
        self.control_store.sync_control(snapshot, elapsed_seconds=self.control_controller.elapsed_seconds)
        self.analysis_route_active = False
        self.control_store.select_route(ShellRoute.OBSERVATION)
        self.footer_hint.set(f"Mutation {record.mutation_id} launched • manual stop/shared-horizon policy")

    def _open_selected_mutation_folder(self) -> None:
        record = self.mutation_controller.snapshot.selected_record
        if record is None:
            self.footer_hint.set("Select a mutation first")
            return
        try:
            self.settings_controller.open_path(record.run_dir)
        except Exception as exc:
            self.footer_hint.set(f"Could not open mutation folder: {exc}")

    def close(self) -> None:
        try:
            if self._mutation_query_trace is not None:
                self.mutation_query_var.trace_remove("write", self._mutation_query_trace)
        except (tk.TclError, ValueError):
            pass
        super().close()


__all__ = ["HAS_FUNCTIONS1G", "ObserverLauncher2MutationsShell"]
