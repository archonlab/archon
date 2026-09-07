"""Tk CONFIG1 extension for the isolated Observer Launcher 2 preview shell."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import Any

from Analyzer_next.execution.observer.settings import SPEED_VALUES
from Analyzer_next.execution.observer.shell2.app import ObserverLauncher2Shell
from Analyzer_next.execution.observer.shell2.store import ShellRoute, ShellSnapshot
from Analyzer_next.execution.observer.shell2.theme import ThemeMode, detect_system_scheme, palette_for

from .model import ConfigStep, OUTPUT_OPTIONS, ProvenanceKind, WorldRecord, forced_controls_for
from .store import ConfigShellStore


class ObserverLauncher2ConfigShell(ObserverLauncher2Shell):
    """Add real Worlds and immutable Run review without production execution."""

    def __init__(
        self,
        root: tk.Tk,
        store: ConfigShellStore,
        *,
        animate: bool = False,
    ) -> None:
        self.config_store = store
        self._world_rows: dict[str, WorldRecord] = {}
        self._selected_table_world: WorldRecord | None = None
        self.form_vars: dict[str, tk.Variable] = {}
        self.output_vars: dict[str, tk.BooleanVar] = {}
        self.experiment_widgets: list[ttk.Widget] = []
        super().__init__(root, store, animate=animate)
        root.title("ARCHON Observer Launcher 2.0 — CONFIG1 Preview")

    def _build_route_content(self) -> None:
        for child in self.workspace.winfo_children():
            child.destroy()
        if self.snapshot.route is ShellRoute.WORLDS:
            self._build_worlds_route()
        elif self.snapshot.route is ShellRoute.RUNS:
            self._build_configuration_route()
        else:
            super()._build_route_content()

    def _build_worlds_route(self) -> None:
        root = self._frame(self.workspace, "surface.app")
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_rowconfigure(2, weight=1)
        root.grid_columnconfigure(0, weight=1)

        header = self._frame(root, "surface.card")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._label(
            header,
            "Select a canonical world",
            surface="surface.card",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(side="left", padx=14, pady=12)
        self.world_count_label = self._label(
            header,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        self.world_count_label.pack(side="right", padx=14)

        filters = self._frame(root, "surface.card")
        filters.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        cfg = self.config_store.config_snapshot
        self.world_query_var = tk.StringVar(value=cfg.filters.query)
        self.world_class_var = tk.StringVar(value=cfg.filters.world_class)
        self.world_status_var = tk.StringVar(value=cfg.filters.status)
        self.world_sort_var = tk.StringVar(value=cfg.filters.sort)
        self._label(filters, "Search", surface="surface.card", foreground="text.secondary").pack(side="left", padx=(12, 5), pady=10)
        search = ttk.Entry(filters, textvariable=self.world_query_var, width=18, style="OL2.TEntry")
        search.pack(side="left", pady=8)
        search.bind("<Return>", lambda _event: self._apply_world_filters())
        self._label(filters, "Class", surface="surface.card", foreground="text.secondary").pack(side="left", padx=(12, 5))
        classes = ("All", *cfg.world_classes)
        class_combo = ttk.Combobox(
            filters,
            textvariable=self.world_class_var,
            values=classes,
            state="readonly",
            width=20,
            style="OL2.TCombobox",
        )
        class_combo.pack(side="left")
        class_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_world_filters())
        status_combo = ttk.Combobox(
            filters,
            textvariable=self.world_status_var,
            values=("All", "Verified", "Needs source", "Observed", "Not observed"),
            state="readonly",
            width=13,
            style="OL2.TCombobox",
        )
        status_combo.pack(side="left", padx=8)
        status_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_world_filters())
        sort_combo = ttk.Combobox(
            filters,
            textvariable=self.world_sort_var,
            values=("Rule ID", "Score high", "Score low", "Last run"),
            state="readonly",
            width=11,
            style="OL2.TCombobox",
        )
        sort_combo.pack(side="left")
        sort_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_world_filters())
        refresh = self._button(filters, "Refresh Atlas", self.config_store.reload_worlds)
        refresh.pack(side="right", padx=10, pady=6)

        body = self._frame(root, "surface.app")
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)

        table_panel = self._frame(body, "surface.card")
        table_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        table_panel.grid_rowconfigure(0, weight=1)
        table_panel.grid_columnconfigure(0, weight=1)
        columns = ("rule", "class", "score", "integrity", "observed", "last")
        self.world_tree = ttk.Treeview(
            table_panel,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="OL2.Treeview",
        )
        headings = {
            "rule": "Rule",
            "class": "Class",
            "score": "Score",
            "integrity": "Integrity",
            "observed": "Observed",
            "last": "Last run",
        }
        widths = {"rule": 72, "class": 185, "score": 74, "integrity": 118, "observed": 72, "last": 120}
        for key in columns:
            self.world_tree.heading(key, text=headings[key])
            self.world_tree.column(key, width=widths[key], anchor="w" if key == "class" else "center")
        scrollbar = ttk.Scrollbar(table_panel, orient="vertical", command=self.world_tree.yview)
        self.world_tree.configure(yscrollcommand=scrollbar.set)
        self.world_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.world_tree.bind("<<TreeviewSelect>>", self._world_table_selected)
        self.world_tree.bind("<Double-1>", lambda _event: self._select_world_and_configure())

        details = self._frame(body, "surface.card")
        details.grid(row=0, column=1, sticky="nsew")
        self._label(
            details,
            "WORLD IDENTITY",
            surface="surface.card",
            foreground="text.muted",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))
        self.world_detail_title = self._label(
            details,
            "No world selected",
            surface="surface.card",
            font=("TkDefaultFont", 16, "bold"),
        )
        self.world_detail_title.pack(anchor="w", padx=16)
        self.world_detail_body = self._label(
            details,
            "Select a row to inspect canonical source identity.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 10),
        )
        self.world_detail_body.configure(justify="left", wraplength=300)
        self.world_detail_body.pack(anchor="w", padx=16, pady=12)
        self.world_integrity_label = self._label(
            details,
            "○  Not inspected",
            surface="surface.card",
            foreground="status.offline",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.world_integrity_label.pack(anchor="w", padx=16, pady=(0, 12))
        self.configure_world_button = self._button(
            details,
            "Select & Configure",
            self._select_world_and_configure,
            kind="primary",
        )
        self.configure_world_button.configure(state="disabled")
        self.configure_world_button.pack(fill="x", side="bottom", padx=16, pady=16)
        self._populate_world_table()

    def _apply_world_filters(self) -> None:
        self.config_store.set_world_filters(
            query=self.world_query_var.get(),
            world_class=self.world_class_var.get(),
            status=self.world_status_var.get(),
            sort=self.world_sort_var.get(),
        )

    def _populate_world_table(self) -> None:
        if not hasattr(self, "world_tree") or not self.world_tree.winfo_exists():
            return
        cfg = self.config_store.config_snapshot
        selected = self.world_tree.selection()
        selected_id = selected[0] if selected else None
        self.world_tree.delete(*self.world_tree.get_children())
        self._world_rows = {}
        for world in cfg.visible_worlds:
            iid = world.display_id
            self._world_rows[iid] = world
            self.world_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    iid,
                    world.world_class,
                    f"{world.score:.3f}" if world.score is not None else "—",
                    world.integrity.value,
                    "Yes" if world.observed else "No",
                    world.last_run,
                ),
                tags=("verified" if world.source_verified else "blocked",),
            )
        if selected_id in self._world_rows:
            self.world_tree.selection_set(selected_id)
        verified = sum(world.source_verified for world in cfg.worlds)
        suffix = f" • catalog error: {self.config_store.catalog_error}" if self.config_store.catalog_error else ""
        self.world_count_label.configure(
            text=f"{len(cfg.visible_worlds):,}/{len(cfg.worlds):,} visible • {verified:,} verified{suffix}"
        )
        self._theme_world_tree_tags()

    def _world_table_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.world_tree.selection()
        if not selection:
            return
        world = self._world_rows.get(selection[0])
        if world is None:
            return
        self._selected_table_world = world
        self.world_detail_title.configure(text=f"Rule {world.display_id}")
        self.world_detail_body.configure(
            text=(
                f"Class: {world.world_class}\n"
                f"Score: {world.score if world.score is not None else '—'}\n"
                f"Genome: {world.genome_hash or '—'}\n"
                f"Observed: {'yes' if world.observed else 'no'}\n"
                f"Mutation runs: {world.mutation_runs}\n\n"
                f"Source: {world.source_path or 'not resolved'}"
            )
        )
        palette = palette_for(self.snapshot.resolved_theme)
        token = "status.running" if world.source_verified else "status.failed"
        marker = "●" if world.source_verified else "!"
        self.world_integrity_label.configure(
            text=f"{marker}  {world.integrity.value}",
            foreground=palette[token],
        )
        self.configure_world_button.configure(
            state="normal" if world.source_verified else "disabled"
        )

    def _select_world_and_configure(self) -> None:
        world = self._selected_table_world
        if world is None or not world.source_verified:
            self.footer_hint.set("A verified canonical rule source is required")
            return
        self.config_store.select_world(world.rule_id)

    def _build_configuration_route(self) -> None:
        cfg = self.config_store.config_snapshot
        if cfg.draft.world is None:
            panel = self._frame(self.workspace, "surface.card")
            panel.grid(row=0, column=0, sticky="nsew")
            self._label(
                panel,
                "Select a verified world before configuration.",
                surface="surface.card",
                font=("TkDefaultFont", 16, "bold"),
            ).pack(pady=(80, 20))
            self._button(panel, "Open Worlds", self.config_store.back_to_worlds, kind="primary").pack()
            return

        root = self._frame(self.workspace, "surface.app")
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)

        self.step_bar = self._frame(root, "surface.card")
        self.step_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.step_labels: dict[ConfigStep, tk.Label] = {}
        for number, (step, label) in enumerate(
            ((ConfigStep.SELECT_WORLD, "World"), (ConfigStep.CONFIGURE, "Configure"), (ConfigStep.REVIEW, "Review")),
            start=1,
        ):
            widget = self._label(
                self.step_bar,
                f"{number}  {label}",
                surface="surface.card",
                foreground="text.secondary",
                font=("TkDefaultFont", 10, "bold"),
            )
            widget.pack(side="left", padx=18, pady=11)
            self.step_labels[step] = widget
        self._label(
            self.step_bar,
            f"Rule {cfg.draft.world.display_id} • {cfg.draft.world.world_class}",
            surface="surface.card",
            foreground="text.secondary",
        ).pack(side="right", padx=16)

        self.config_notebook = ttk.Notebook(root, style="OL2.TNotebook")
        self.config_notebook.grid(row=1, column=0, sticky="nsew")
        self.configure_tab = self._frame(self.config_notebook, "surface.app")
        self.provenance_tab = self._frame(self.config_notebook, "surface.app")
        self.review_tab = self._frame(self.config_notebook, "surface.app")
        self.config_notebook.add(self.configure_tab, text="Configuration")
        self.config_notebook.add(self.provenance_tab, text="Provenance & locks")
        self.config_notebook.add(self.review_tab, text="Review")
        self._initialize_form_vars(cfg.draft)
        self._build_configuration_form()
        self._build_provenance_form()
        self._build_review_panel()

        actions = self._frame(root, "surface.card")
        actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self._button(actions, "Back to Worlds", self.config_store.back_to_worlds).pack(side="left", padx=10, pady=7)
        self._button(actions, "Validate & Review", self._validate_and_review, kind="primary").pack(side="right", padx=10, pady=7)
        launch = self._button(actions, "Launch disabled in CONFIG1", lambda: None)
        launch.configure(state="disabled")
        launch.pack(side="right", padx=3, pady=7)
        self._apply_forced_control_ui()
        self._refresh_review_panel()

    def _initialize_form_vars(self, draft) -> None:
        values: dict[str, Any] = {
            "provenance": draft.provenance.value,
            "max_ticks": str(draft.max_ticks),
            "autosave_every": str(draft.autosave_every),
            "sample_every": str(draft.sample_every),
            "pressure_every": str(draft.pressure_every),
            "speed": str(draft.speed),
            "frame_delay_ms": str(draft.frame_delay_ms),
            "cell_size": str(draft.cell_size),
            "auto_stop": draft.auto_stop,
            "output_dir": draft.output_dir,
            "field_width": str(draft.field_width),
            "field_height": str(draft.field_height),
            "topology": draft.topology,
            "boundary_mode": draft.boundary_mode,
            "seed": "" if draft.seed is None else str(draft.seed),
            "experiment_id": draft.experiment_id or "",
            "condition_id": draft.condition_id or "",
            "experiment_role": draft.experiment_role,
            "replicate_index": str(draft.replicate_index),
            "initial_state_mode": draft.initial_state_mode,
        }
        self.form_vars = {
            key: (tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=value))
            for key, value in values.items()
        }
        self.output_vars = {
            option: tk.BooleanVar(value=option in draft.outputs)
            for option in OUTPUT_OPTIONS
        }

    def _section(self, parent: tk.Misc, title: str, column: int) -> tk.Frame:
        frame = self._frame(parent, "surface.card")
        frame.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 5 if column == 0 else 0), pady=4)
        frame.grid_columnconfigure(1, weight=1)
        self._label(
            frame,
            title.upper(),
            surface="surface.card",
            foreground="text.muted",
            font=("TkDefaultFont", 9, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        return frame

    def _field(self, parent: tk.Frame, row: int, label: str, key: str, values: tuple[str, ...] | None = None) -> ttk.Widget:
        self._label(parent, label, surface="surface.card", foreground="text.secondary").grid(row=row, column=0, sticky="w", padx=12, pady=5)
        if values is None:
            widget: ttk.Widget = ttk.Entry(parent, textvariable=self.form_vars[key], style="OL2.TEntry")
        else:
            widget = ttk.Combobox(
                parent,
                textvariable=self.form_vars[key],
                values=values,
                state="readonly",
                style="OL2.TCombobox",
            )
        widget.grid(row=row, column=1, sticky="ew", padx=(8, 12), pady=5)
        return widget

    def _build_configuration_form(self) -> None:
        self.configure_tab.grid_columnconfigure(0, weight=1)
        self.configure_tab.grid_columnconfigure(1, weight=1)
        simulation = self._section(self.configure_tab, "Simulation", 0)
        self._field(simulation, 1, "Maximum ticks", "max_ticks")
        self._field(simulation, 2, "Autosave every", "autosave_every")
        self._field(simulation, 3, "Sample every", "sample_every")
        self._field(simulation, 4, "Pressure every", "pressure_every")
        self._field(simulation, 5, "Speed", "speed", tuple(str(item) for item in SPEED_VALUES))
        self._field(simulation, 6, "Frame delay (ms)", "frame_delay_ms")
        self._field(simulation, 7, "Cell size", "cell_size")
        self.auto_stop_check = ttk.Checkbutton(
            simulation,
            text="Auto-stop after collapse",
            variable=self.form_vars["auto_stop"],
            style="OL2.TCheckbutton",
        )
        self.auto_stop_check.grid(row=8, column=0, columnspan=2, sticky="w", padx=12, pady=8)

        environment = self._section(self.configure_tab, "Environment & outputs", 1)
        self._field(environment, 1, "Output directory", "output_dir")
        self._field(environment, 2, "Field width", "field_width")
        self._field(environment, 3, "Field height", "field_height")
        self._field(environment, 4, "Topology", "topology", ("torus", "bounded"))
        self._field(
            environment,
            5,
            "Boundary",
            "boundary_mode",
            ("wrap", "fixed_dead", "fixed_alive", "reflective"),
        )
        self._field(environment, 6, "Seed (optional)", "seed")
        output_box = self._frame(environment, "surface.elevated")
        output_box.grid(row=7, column=0, columnspan=2, sticky="ew", padx=12, pady=8)
        self.output_checks: dict[str, ttk.Checkbutton] = {}
        labels = {
            "samples": "Samples CSV",
            "events": "Events CSV",
            "pressure": "Pressure timeline",
            "chronicle": "Chronicle CSV",
            "passport": "Passport",
            "log": "Observation log",
            "sqlite": "SQLite telemetry",
            "evidence": "Evidence Framework",
        }
        for index, option in enumerate(OUTPUT_OPTIONS):
            check = ttk.Checkbutton(
                output_box,
                text=labels[option],
                variable=self.output_vars[option],
                style="OL2.TCheckbutton",
            )
            check.grid(row=index // 2, column=index % 2, sticky="w", padx=10, pady=4)
            self.output_checks[option] = check

    def _build_provenance_form(self) -> None:
        self.provenance_tab.grid_columnconfigure(0, weight=1)
        self.provenance_tab.grid_columnconfigure(1, weight=1)
        source = self._section(self.provenance_tab, "Provenance", 0)
        provenance = self._field(
            source,
            1,
            "Run provenance",
            "provenance",
            tuple(item.value for item in ProvenanceKind),
        )
        provenance.bind("<<ComboboxSelected>>", lambda _event: self._apply_forced_control_ui())
        self._field(source, 2, "Experiment ID", "experiment_id")
        self._field(source, 3, "Condition ID", "condition_id")
        role = self._field(
            source,
            4,
            "Experiment role",
            "experiment_role",
            ("baseline", "treatment", "control", "calibration"),
        )
        self._field(source, 5, "Replicate index", "replicate_index")
        initial = self._field(
            source,
            6,
            "Initial state",
            "initial_state_mode",
            ("canonical_seed", "random_seed", "saved_state", "deterministic_regenerated"),
        )
        self.experiment_widgets = [
            child
            for child in source.winfo_children()
            if isinstance(child, (ttk.Entry, ttk.Combobox))
        ][1:]
        locks = self._section(self.provenance_tab, "Scientific locks", 1)
        self.forced_controls_label = self._label(
            locks,
            surface="surface.card",
            foreground="status.info",
            font=("TkDefaultFont", 10),
        )
        self.forced_controls_label.configure(justify="left", wraplength=350)
        self.forced_controls_label.grid(row=1, column=0, columnspan=2, sticky="nw", padx=12, pady=8)
        self._label(
            locks,
            "Locks are derived from the provenance contract. They are applied to the effective draft and cannot be bypassed by checkbox state.",
            surface="surface.card",
            foreground="text.muted",
            font=("TkDefaultFont", 9),
        ).grid(row=2, column=0, columnspan=2, sticky="nw", padx=12, pady=12)

    def _build_review_panel(self) -> None:
        self.review_tab.grid_columnconfigure(0, weight=1)
        self.review_tab.grid_rowconfigure(2, weight=1)
        status = self._frame(self.review_tab, "surface.card")
        status.grid(row=0, column=0, sticky="ew", pady=(4, 8))
        self.review_status_label = self._label(
            status,
            "Not validated",
            surface="surface.card",
            foreground="status.waiting",
            font=("TkDefaultFont", 13, "bold"),
        )
        self.review_status_label.pack(anchor="w", padx=14, pady=(12, 4))
        self.review_issues_label = self._label(
            status,
            "Use Validate & Review to create an immutable RunSpec.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        self.review_issues_label.configure(justify="left", wraplength=820)
        self.review_issues_label.pack(anchor="w", padx=14, pady=(0, 12))

        hashes = self._frame(self.review_tab, "surface.card")
        hashes.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.run_spec_hash_label = self._label(hashes, "RunSpec SHA-256: —", surface="surface.card", foreground="text.secondary", font=("TkFixedFont", 9))
        self.run_spec_hash_label.pack(anchor="w", padx=14, pady=(10, 3))
        self.review_hash_label = self._label(hashes, "Review SHA-256: —", surface="surface.card", foreground="text.secondary", font=("TkFixedFont", 9))
        self.review_hash_label.pack(anchor="w", padx=14, pady=(3, 10))

        command_panel = self._frame(self.review_tab, "surface.card")
        command_panel.grid(row=2, column=0, sticky="nsew")
        command_panel.grid_rowconfigure(1, weight=1)
        command_panel.grid_columnconfigure(0, weight=1)
        self._label(command_panel, "NORMALIZED COMMAND", surface="surface.card", foreground="text.muted", font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        self.command_text = tk.Text(
            command_panel,
            height=7,
            wrap="word",
            borderwidth=0,
            highlightthickness=1,
            font=("TkFixedFont", 9),
            state="disabled",
            padx=10,
            pady=10,
        )
        self._register(
            self.command_text,
            background="surface.elevated",
            foreground="text.primary",
            highlightbackground="border.default",
            highlightcolor="focus.ring",
            insertbackground="text.primary",
            selectbackground="action.primary",
            selectforeground="text.inverse",
        )
        self.command_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

    def _apply_forced_control_ui(self) -> None:
        if not self.form_vars or "provenance" not in self.form_vars:
            return
        try:
            provenance = ProvenanceKind(str(self.form_vars["provenance"].get()))
        except ValueError:
            return
        controls = forced_controls_for(provenance)
        if hasattr(self, "forced_controls_label"):
            if controls:
                self.forced_controls_label.configure(
                    text="\n\n".join(
                        f"[LOCK] {item.field} = {item.forced_value}\n{item.owner}: {item.reason}"
                        for item in controls
                    )
                )
            else:
                self.forced_controls_label.configure(text="No forced controls for canonical provenance.")
        if hasattr(self, "output_checks"):
            for check in self.output_checks.values():
                check.configure(state="normal")
            self.auto_stop_check.configure(state="normal")
            if provenance is ProvenanceKind.EXPERIMENTAL:
                self.output_vars["sqlite"].set(True)
                self.output_checks["sqlite"].configure(state="disabled")
            elif provenance is ProvenanceKind.REQUIRED_CONTROL:
                self.form_vars["auto_stop"].set(False)
                self.auto_stop_check.configure(state="disabled")
                for option in ("samples", "passport"):
                    self.output_vars[option].set(True)
                    self.output_checks[option].configure(state="disabled")
        experiment_enabled = provenance is ProvenanceKind.EXPERIMENTAL
        for widget in self.experiment_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="readonly" if experiment_enabled else "disabled")
            else:
                widget.configure(state="normal" if experiment_enabled else "disabled")

    def _capture_form(self) -> dict[str, Any]:
        seed_text = str(self.form_vars["seed"].get()).strip()
        return {
            "provenance": ProvenanceKind(str(self.form_vars["provenance"].get())),
            "max_ticks": int(self.form_vars["max_ticks"].get()),
            "autosave_every": int(self.form_vars["autosave_every"].get()),
            "sample_every": int(self.form_vars["sample_every"].get()),
            "pressure_every": int(self.form_vars["pressure_every"].get()),
            "speed": int(self.form_vars["speed"].get()),
            "frame_delay_ms": int(self.form_vars["frame_delay_ms"].get()),
            "cell_size": int(self.form_vars["cell_size"].get()),
            "auto_stop": bool(self.form_vars["auto_stop"].get()),
            "outputs": {key for key, variable in self.output_vars.items() if variable.get()},
            "output_dir": str(self.form_vars["output_dir"].get()),
            "field_width": int(self.form_vars["field_width"].get()),
            "field_height": int(self.form_vars["field_height"].get()),
            "topology": str(self.form_vars["topology"].get()),
            "boundary_mode": str(self.form_vars["boundary_mode"].get()),
            "seed": int(seed_text) if seed_text else None,
            "experiment_id": str(self.form_vars["experiment_id"].get()).strip() or None,
            "condition_id": str(self.form_vars["condition_id"].get()).strip() or None,
            "experiment_role": str(self.form_vars["experiment_role"].get()),
            "replicate_index": int(self.form_vars["replicate_index"].get()),
            "initial_state_mode": str(self.form_vars["initial_state_mode"].get()),
        }

    def _validate_and_review(self) -> None:
        try:
            changes = self._capture_form()
            self.config_store.update_configuration(**changes)
            self.config_store.review_configuration()
        except (TypeError, ValueError) as exc:
            self.footer_hint.set(f"Configuration input error: {exc}")
            self.review_status_label.configure(text="Input error")
            self.review_issues_label.configure(text=str(exc))
            self.config_notebook.select(self.review_tab)
            return
        self.config_notebook.select(self.review_tab)
        self._refresh_review_panel()

    def _refresh_review_panel(self) -> None:
        if not hasattr(self, "review_status_label") or not self.review_status_label.winfo_exists():
            return
        review = self.config_store.config_snapshot.review
        palette = palette_for(self.snapshot.resolved_theme)
        if review is None:
            self.review_status_label.configure(text="Not validated", foreground=palette["status.waiting"])
            return
        if not review.valid or review.prepared is None:
            self.review_status_label.configure(text="Validation blocked", foreground=palette["status.failed"])
            self.review_issues_label.configure(
                text="\n".join(f"• {item.message} [{item.code}]" for item in review.issues)
            )
            self.run_spec_hash_label.configure(text="RunSpec SHA-256: —")
            self.review_hash_label.configure(text="Review SHA-256: —")
            command = "No command was produced because validation failed."
        else:
            prepared = review.prepared
            self.review_status_label.configure(text="✓ Ready for immutable handoff", foreground=palette["status.running"])
            self.review_issues_label.configure(
                text=(
                    f"RunSpec is frozen. Forced controls applied: {len(prepared.forced_controls)}. "
                    "CONFIG1 does not enqueue or start the process."
                )
            )
            self.run_spec_hash_label.configure(text=f"RunSpec SHA-256: {prepared.run_spec.content_hash}")
            self.review_hash_label.configure(text=f"Review SHA-256:  {prepared.review_hash}")
            command = prepared.command_text
            if hasattr(self, "step_labels"):
                self._refresh_step_theme(ConfigStep.REVIEW)
        self.command_text.configure(state="normal")
        self.command_text.delete("1.0", "end")
        self.command_text.insert("1.0", command)
        self.command_text.configure(state="disabled")

    def _refresh_step_theme(self, active: ConfigStep | None = None) -> None:
        if not hasattr(self, "step_labels"):
            return
        active = active or self.config_store.config_snapshot.step
        order = [ConfigStep.SELECT_WORLD, ConfigStep.CONFIGURE, ConfigStep.REVIEW]
        active_index = order.index(active)
        palette = palette_for(self.snapshot.resolved_theme)
        for index, step in enumerate(order):
            token = "chart.1" if index <= active_index else "text.muted"
            self.step_labels[step].configure(foreground=palette[token])

    def _theme_world_tree_tags(self) -> None:
        if not hasattr(self, "world_tree") or not self.world_tree.winfo_exists():
            return
        palette = palette_for(self.snapshot.resolved_theme)
        self.world_tree.tag_configure("verified", foreground=palette["text.primary"])
        self.world_tree.tag_configure("blocked", foreground=palette["status.failed"])

    def _apply_theme(self) -> None:
        super()._apply_theme()
        palette = palette_for(self.snapshot.resolved_theme)
        self.style.configure(
            "OL2.Treeview",
            background=palette["surface.card"],
            fieldbackground=palette["surface.card"],
            foreground=palette["text.primary"],
            bordercolor=palette["border.default"],
            rowheight=34,
        )
        self.style.configure(
            "OL2.Treeview.Heading",
            background=palette["surface.elevated"],
            foreground=palette["text.secondary"],
            bordercolor=palette["border.default"],
            font=("TkDefaultFont", 9, "bold"),
        )
        self.style.map(
            "OL2.Treeview",
            background=[("selected", palette["surface.selected"])],
            foreground=[("selected", palette["text.primary"])],
        )
        self.style.configure(
            "OL2.TEntry",
            fieldbackground=palette["surface.control"],
            foreground=palette["text.primary"],
            bordercolor=palette["border.default"],
            insertcolor=palette["text.primary"],
            padding=6,
        )
        self.style.configure(
            "OL2.TCheckbutton",
            background=palette["surface.card"],
            foreground=palette["text.secondary"],
            focuscolor=palette["focus.ring"],
            padding=4,
        )
        self.style.map(
            "OL2.TCheckbutton",
            background=[("active", palette["surface.card"])],
            foreground=[("disabled", palette["text.muted"])],
        )
        self.style.configure("OL2.TNotebook", background=palette["surface.app"], bordercolor=palette["border.default"])
        self.style.configure(
            "OL2.TNotebook.Tab",
            background=palette["surface.control"],
            foreground=palette["text.secondary"],
            padding=(18, 9),
        )
        self.style.map(
            "OL2.TNotebook.Tab",
            background=[("selected", palette["surface.selected"])],
            foreground=[("selected", palette["text.primary"])],
        )
        self._theme_world_tree_tags()
        self._refresh_step_theme()

    def _refresh_config_content(self) -> None:
        if self.snapshot.route is ShellRoute.WORLDS:
            self._populate_world_table()
        elif self.snapshot.route is ShellRoute.RUNS:
            self._apply_forced_control_ui()
            self._refresh_review_panel()
            self._refresh_step_theme()

    def _on_store_change(self, snapshot: ShellSnapshot) -> None:
        super()._on_store_change(snapshot)
        self._refresh_config_content()


def run_config_shell(
    *,
    theme: ThemeMode = ThemeMode.SYSTEM,
    auto_close_ms: int | None = None,
) -> int:
    root = tk.Tk()
    store = ConfigShellStore(
        theme_preference=theme,
        system_scheme=detect_system_scheme(),
    )
    store.select_route(ShellRoute.WORLDS)
    ObserverLauncher2ConfigShell(root, store, animate=False)
    if auto_close_ms is not None:
        root.after(max(1, auto_close_ms), root.destroy)
    root.mainloop()
    return 0
