"""OL2-CAMPAIGNS1: canonical Scope → Campaign → Queue batch composer."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from collections import Counter

from Analyzer_next.execution.observer.shell2.perf1.app import ObserverLauncher2PerfShell
from Analyzer_next.execution.observer.shell2.store import ShellRoute

from .controller import CampaignController
from .model import CampaignStage


class ObserverLauncher2CampaignsShell(ObserverLauncher2PerfShell):
    """Compose ordinary canonical observation batches and hand them to QUEUE1."""

    def __init__(
        self,
        root: tk.Tk,
        *args,
        campaign_controller: CampaignController,
        **kwargs,
    ) -> None:
        if not isinstance(campaign_controller, CampaignController):
            raise TypeError("CAMPAIGNS1 requires CampaignController")
        self.campaign_controller = campaign_controller
        self.campaign_scope_tree: ttk.Treeview | None = None
        self.campaign_plan_tree: ttk.Treeview | None = None
        self.campaign_query_var = tk.StringVar(master=root)
        self.campaign_scope_summary = tk.StringVar(master=root, value="No worlds selected.")
        self.campaign_max_ticks_var = tk.StringVar(master=root, value="20000")
        self.campaign_sample_every_var = tk.StringVar(master=root, value="10")
        self.campaign_pressure_every_var = tk.StringVar(master=root, value="100")
        self.campaign_repetitions_var = tk.StringVar(master=root, value="1")
        self.campaign_seed_start_var = tk.StringVar(master=root, value="")
        self.campaign_plan_summary = tk.StringVar(master=root, value="Campaign has not been reviewed.")
        self._campaign_search_after: str | None = None
        self._campaign_query_trace: str | None = None
        super().__init__(root, *args, **kwargs)
        self._campaign_query_trace = self.campaign_query_var.trace_add("write", self._campaign_query_changed)
        self.root.title("ARCHON Observer Launcher 2.0 — CAMPAIGNS1")
        self.footer_hint.set(
            "CAMPAIGNS1 Scope → Campaign → Queue • canonical observation batches only • no auto-start"
        )

    def _build_route_content(self) -> None:
        try:
            if not self.analysis_route_active and self.snapshot.route is ShellRoute.CAMPAIGNS:
                for child in self.workspace.winfo_children():
                    child.destroy()
                self._build_campaigns_route()
                return
            super()._build_route_content()
        finally:
            schedule = getattr(self, "_schedule_theme_reconciliation", None)
            if callable(schedule):
                schedule()

    def _build_campaigns_route(self) -> None:
        root = self._frame(self.workspace, "surface.app")
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        _canvas, body = self._new_hidden_scroller(root)
        self._build_campaign_steps(body)
        stage = self.campaign_controller.snapshot.stage
        if stage is CampaignStage.SCOPE:
            self._build_campaign_scope(body)
        elif stage is CampaignStage.CAMPAIGN:
            self._build_campaign_editor(body)
        else:
            self._build_campaign_queue_preview(body)

    def _build_campaign_steps(self, parent: tk.Widget) -> None:
        bar = self._frame(parent, "surface.card")
        bar.pack(fill="x", pady=(0, 8))
        for stage, label in (
            (CampaignStage.SCOPE, "1 Scope"),
            (CampaignStage.CAMPAIGN, "2 Campaign"),
            (CampaignStage.QUEUE, "3 Queue"),
        ):
            self._button(
                bar,
                label,
                lambda value=stage: self._set_campaign_stage(value),
                kind="primary" if self.campaign_controller.snapshot.stage is stage else "neutral",
            ).pack(side="left", padx=(8 if stage is CampaignStage.SCOPE else 2, 2), pady=7)
        selected = len(self.campaign_controller.snapshot.draft.selected_rule_ids)
        plan = self.campaign_controller.snapshot.plan
        context = f"{selected} world(s) selected"
        if plan is not None:
            context += f" • {plan.run_count} reviewed run(s)"
        self._label(
            bar,
            context,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="right", padx=14)

    def _set_campaign_stage(self, stage: CampaignStage) -> None:
        self.campaign_controller.set_stage(stage)
        if self.snapshot.route is ShellRoute.CAMPAIGNS and not self.analysis_route_active:
            self._build_route_content()

    # ------------------------------------------------------------------
    # 1 Scope
    # ------------------------------------------------------------------
    def _build_campaign_scope(self, body: tk.Widget) -> None:
        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(header, "Campaign Scope", surface="surface.card", font=("TkDefaultFont", 16, "bold")).pack(
            side="left", padx=14, pady=12
        )
        self._label(
            header,
            "Select several verified canonical worlds. Campaigns never modify Atlas sources.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)

        filters = self._frame(body, "surface.card")
        filters.pack(fill="x", pady=(0, 8))
        self._label(filters, "Search", surface="surface.card", font=("TkDefaultFont", 9, "bold")).pack(
            side="left", padx=(14, 6), pady=9
        )
        ttk.Entry(filters, textvariable=self.campaign_query_var, style="OL2.TEntry").pack(
            side="left", fill="x", expand=True, padx=(0, 10), pady=7
        )
        self._button(filters, "Select Visible", self._campaign_select_visible).pack(side="right", padx=(3, 12), pady=7)
        self._button(filters, "Select Not Observed", self._campaign_select_not_observed).pack(
            side="right", padx=3, pady=7
        )
        self._button(filters, "Clear", self._campaign_clear_scope).pack(side="right", padx=3, pady=7)

        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 8))
        columns = ("rule", "class", "observed", "mutations", "last")
        tree = ttk.Treeview(card, columns=columns, show="headings", selectmode="extended", height=13, style="OL2.Treeview")
        for key, title, width, anchor in (
            ("rule", "Rule", 90, "center"),
            ("class", "Class", 340, "w"),
            ("observed", "Observed", 100, "center"),
            ("mutations", "Mutations", 100, "center"),
            ("last", "Last run", 180, "w"),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor=anchor)
        tree.pack(fill="x", padx=12, pady=(10, 8))
        tree.bind("<<TreeviewSelect>>", self._campaign_scope_selected)
        self.campaign_scope_tree = tree
        self._fill_campaign_scope()

        footer = self._frame(body, "surface.card")
        footer.pack(fill="x", pady=(0, 8))
        label = self._label(footer, surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 10))
        label.configure(textvariable=self.campaign_scope_summary, wraplength=850, justify="left")
        label.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        self._button(footer, "Configure Campaign →", self._campaign_continue, kind="primary").pack(
            side="right", padx=14, pady=10
        )
        self._update_campaign_scope_summary()

    def _fill_campaign_scope(self) -> None:
        tree = self.campaign_scope_tree
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for world in self.campaign_controller.snapshot.visible_worlds:
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
        selected = set(self.campaign_controller.snapshot.draft.selected_rule_ids)
        visible_selected = tuple(str(rule_id) for rule_id in selected if tree.exists(str(rule_id)))
        if visible_selected:
            tree.selection_set(visible_selected)

    def _campaign_query_changed(self, *_args) -> None:
        try:
            if self._campaign_search_after is not None:
                self.root.after_cancel(self._campaign_search_after)
        except (tk.TclError, ValueError):
            pass
        try:
            self._campaign_search_after = self.root.after(80, self._apply_campaign_filter)
        except tk.TclError:
            self._campaign_search_after = None

    def _apply_campaign_filter(self) -> None:
        self._campaign_search_after = None
        self.campaign_controller.set_query(self.campaign_query_var.get())
        self._fill_campaign_scope()
        self._update_campaign_scope_summary()

    def _campaign_scope_selected(self, _event=None) -> None:
        tree = self.campaign_scope_tree
        if tree is None:
            return
        visible_ids = {int(item) for item in tree.get_children()}
        selected_visible = {int(item) for item in tree.selection()}
        selected = set(self.campaign_controller.snapshot.draft.selected_rule_ids)
        selected.difference_update(visible_ids)
        selected.update(selected_visible)
        try:
            self.campaign_controller.set_scope(selected)
        except ValueError as exc:
            self.footer_hint.set(str(exc))
            self._fill_campaign_scope()
        self._update_campaign_scope_summary()

    def _campaign_select_visible(self) -> None:
        try:
            self.campaign_controller.select_visible()
        except ValueError as exc:
            self.footer_hint.set(str(exc))
            return
        self._fill_campaign_scope()
        self._update_campaign_scope_summary()

    def _campaign_select_not_observed(self) -> None:
        try:
            self.campaign_controller.select_not_observed_visible()
        except ValueError as exc:
            self.footer_hint.set(str(exc))
            return
        self._fill_campaign_scope()
        self._update_campaign_scope_summary()

    def _campaign_clear_scope(self) -> None:
        self.campaign_controller.clear_scope()
        self._fill_campaign_scope()
        self._update_campaign_scope_summary()

    def _update_campaign_scope_summary(self) -> None:
        selected = self.campaign_controller.snapshot.selected_worlds
        if not selected:
            self.campaign_scope_summary.set("No worlds selected. Use Ctrl/Shift selection or Select Visible.")
            return
        preview = ", ".join(f"{world.display_id}" for world in selected[:8])
        if len(selected) > 8:
            preview += f", … +{len(selected) - 8}"
        self.campaign_scope_summary.set(f"Selected {len(selected)} canonical world(s): {preview}")

    def _campaign_continue(self) -> None:
        if not self.campaign_controller.snapshot.draft.selected_rule_ids:
            self.footer_hint.set("Select at least one canonical world for the campaign")
            return
        self.campaign_controller.set_stage(CampaignStage.CAMPAIGN)
        self._build_route_content()

    # ------------------------------------------------------------------
    # 2 Campaign
    # ------------------------------------------------------------------
    def _build_campaign_editor(self, body: tk.Widget) -> None:
        if not self.campaign_controller.snapshot.draft.selected_rule_ids:
            self._build_campaign_empty(body, "No campaign scope", "Choose one or more canonical worlds first.", CampaignStage.SCOPE)
            return

        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(header, "Configure Campaign", surface="surface.card", font=("TkDefaultFont", 16, "bold")).pack(
            side="left", padx=14, pady=12
        )
        self._label(
            header,
            f"{len(self.campaign_controller.snapshot.draft.selected_rule_ids)} canonical world(s) • ordinary queue mode",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)

        settings = self._frame(body, "surface.card")
        settings.pack(fill="x", pady=(0, 8))
        grid = self._frame(settings, "surface.card")
        grid.pack(fill="x", padx=14, pady=12)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(3, weight=1)

        fields = (
            (0, 0, "Max ticks", self.campaign_max_ticks_var),
            (0, 2, "Repetitions / world", self.campaign_repetitions_var),
            (1, 0, "Sample every", self.campaign_sample_every_var),
            (1, 2, "Pressure every", self.campaign_pressure_every_var),
            (2, 0, "Seed start", self.campaign_seed_start_var),
        )
        for row, col, title, variable in fields:
            self._label(grid, title, surface="surface.card", font=("TkDefaultFont", 9, "bold")).grid(
                row=row, column=col, sticky="w", pady=6
            )
            ttk.Entry(grid, textvariable=variable, style="OL2.TEntry").grid(
                row=row, column=col + 1, sticky="ew", padx=(8, 18 if col == 0 else 0), pady=6
            )
        self._label(
            grid,
            "Leave Seed start empty for runtime-random seeds. If set, runs receive sequential deterministic seeds.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))

        summary = self._frame(body, "surface.card")
        summary.pack(fill="x", pady=(0, 8))
        worlds = self.campaign_controller.snapshot.selected_worlds
        self._label(
            summary,
            f"Scope: {', '.join(world.display_id for world in worlds[:12])}"
            + (f" … +{len(worlds)-12}" if len(worlds) > 12 else ""),
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 10),
        ).pack(side="left", padx=14, pady=12)
        self._button(summary, "Review Campaign →", self._review_campaign, kind="primary").pack(
            side="right", padx=14, pady=10
        )

    def _sync_campaign_draft(self) -> None:
        seed_text = self.campaign_seed_start_var.get().strip()
        seed_start = None if not seed_text else int(seed_text)
        self.campaign_controller.update_draft(
            max_ticks=int(self.campaign_max_ticks_var.get().strip()),
            sample_every=int(self.campaign_sample_every_var.get().strip()),
            pressure_every=int(self.campaign_pressure_every_var.get().strip()),
            repetitions=int(self.campaign_repetitions_var.get().strip()),
            seed_start=seed_start,
        )

    def _review_campaign(self) -> None:
        try:
            self._sync_campaign_draft()
            snap = self.campaign_controller.prepare()
        except (ValueError, TypeError) as exc:
            self.footer_hint.set(f"Campaign review refused: {exc}")
            return
        assert snap.plan is not None
        self.footer_hint.set(
            f"Campaign reviewed • {snap.plan.run_count} immutable canonical queue row(s) • not queued yet"
        )
        self._build_route_content()

    # ------------------------------------------------------------------
    # 3 Queue preview
    # ------------------------------------------------------------------
    def _build_campaign_queue_preview(self, body: tk.Widget) -> None:
        plan = self.campaign_controller.snapshot.plan
        if plan is None:
            self._build_campaign_empty(
                body,
                "Campaign not reviewed",
                "Configure the scope and review the campaign before queue handoff.",
                CampaignStage.CAMPAIGN,
            )
            return

        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(header, "Queue Preview", surface="surface.card", font=("TkDefaultFont", 16, "bold")).pack(
            side="left", padx=14, pady=12
        )
        self._label(
            header,
            f"{plan.run_count} immutable run(s) • plan {plan.plan_hash[:12]} • Queue will not auto-start",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)

        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 8))
        columns = ("pos", "rule", "rep", "seed", "horizon", "review")
        tree = ttk.Treeview(card, columns=columns, show="headings", selectmode="browse", height=13, style="OL2.Treeview")
        for key, title, width, anchor in (
            ("pos", "#", 55, "center"),
            ("rule", "Rule", 90, "center"),
            ("rep", "Repeat", 80, "center"),
            ("seed", "Seed", 110, "center"),
            ("horizon", "Horizon", 110, "center"),
            ("review", "Review hash", 260, "w"),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor=anchor)
        tree.pack(fill="x", padx=12, pady=(10, 8))
        for row in plan.rows:
            tree.insert(
                "",
                "end",
                iid=str(row.ordinal),
                values=(
                    row.ordinal,
                    f"{row.rule_id:05d}",
                    row.repetition,
                    "random" if row.seed is None else row.seed,
                    f"{row.prepared.run_spec.max_ticks:,}",
                    row.prepared.review_hash[:18],
                ),
            )
        self.campaign_plan_tree = tree

        footer = self._frame(body, "surface.card")
        footer.pack(fill="x", pady=(0, 8))
        existing = Counter(item.prepared.review_hash for item in self.queue_controller.snapshot.items)
        required = Counter(row.prepared.review_hash for row in plan.rows)
        new_count = sum(max(0, count - existing[review_hash]) for review_hash, count in required.items())
        duplicate_count = plan.run_count - new_count
        self.campaign_plan_summary.set(
            f"Ready to add {new_count} run(s) to QUEUE1"
            + (f" • {duplicate_count} already present and will be skipped" if duplicate_count else "")
        )
        label = self._label(footer, surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 10))
        label.configure(textvariable=self.campaign_plan_summary, wraplength=820, justify="left")
        label.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        self._button(footer, "Add Campaign to Queue", self._add_campaign_to_queue, kind="primary").pack(
            side="right", padx=14, pady=10
        )

        note = self._frame(body, "surface.card")
        note.pack(fill="x", pady=(0, 8))
        self._label(
            note,
            "CAMPAIGNS1 creates ordinary canonical_queue rows only. Experimental and production campaign authorization stays fail-closed in their dedicated pipelines.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w", padx=14, pady=12)

    def _add_campaign_to_queue(self) -> None:
        plan = self.campaign_controller.snapshot.plan
        if plan is None:
            self.footer_hint.set("Review the campaign before queue handoff")
            return
        existing = Counter(item.prepared.review_hash for item in self.queue_controller.snapshot.items)
        seen = Counter()
        added = 0
        skipped = 0
        for row in plan.rows:
            review_hash = row.prepared.review_hash
            seen[review_hash] += 1
            if existing[review_hash] >= seen[review_hash]:
                skipped += 1
                continue
            self.queue_controller.enqueue(row.prepared)
            added += 1
        self.footer_hint.set(
            f"Campaign handoff complete • {added} added • {skipped} duplicate(s) skipped • Queue not started"
        )
        self.control_store.select_route(ShellRoute.QUEUE)

    def _build_campaign_empty(
        self,
        body: tk.Widget,
        title: str,
        message: str,
        target: CampaignStage,
    ) -> None:
        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 8))
        self._label(card, title, surface="surface.card", font=("TkDefaultFont", 16, "bold")).pack(
            anchor="w", padx=14, pady=(14, 6)
        )
        self._label(
            card,
            message,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 10),
        ).pack(anchor="w", padx=14, pady=(0, 10))
        self._button(card, "Go Back", lambda: self._set_campaign_stage(target), kind="primary").pack(
            anchor="w", padx=14, pady=(0, 14)
        )

    def close(self) -> None:
        try:
            if self._campaign_query_trace is not None:
                self.campaign_query_var.trace_remove("write", self._campaign_query_trace)
        except (tk.TclError, ValueError):
            pass
        super().close()


__all__ = ["ObserverLauncher2CampaignsShell"]
