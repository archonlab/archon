"""OL2-FUNCTIONS1E: proposal-first Experiments workflow with Runs-style steps."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from Analyzer_next.execution.observer.shell2.functions1d.app import (
    ObserverLauncher2FunctionsExperimentsShell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute

from .controller import ProposalWorkflowController


class ObserverLauncher2FunctionsExperimentWorkflowShell(ObserverLauncher2FunctionsExperimentsShell):
    """Present Research Director proposals as a simple three-step workflow."""

    STAGES = ("proposals", "experiment", "execution")
    DETAIL_TABS = ("overview", "conditions", "review")

    def __init__(
        self,
        root: tk.Tk,
        *args,
        proposal_controller: ProposalWorkflowController,
        director_report_path: Path,
        **kwargs,
    ) -> None:
        if not isinstance(proposal_controller, ProposalWorkflowController):
            raise TypeError("FUNCTIONS1E requires ProposalWorkflowController")
        self.proposal_controller = proposal_controller
        self.director_report_path = Path(director_report_path).expanduser().resolve()
        self.experiment_workflow_stage = "proposals"
        self.experiment_detail_tab = "overview"
        self.proposal_query_var = tk.StringVar(master=root)
        self.proposal_status_var = tk.StringVar(master=root, value="All")
        self.proposal_summary_var = tk.StringVar(master=root, value="Select a Research Director proposal.")
        self.prepared_summary_var = tk.StringVar(master=root, value="No experiment proposal is prepared.")
        self._proposal_search_after: str | None = None
        self._proposal_query_trace: str | None = None
        self.proposal_tree: ttk.Treeview | None = None
        self.proposal_actions_frame: tk.Widget | None = None
        self._action_tooltip: tk.Toplevel | None = None
        self._action_tooltip_row: str | None = None
        # Route mounts can happen outside Store notifications (stage/tab switches).
        # Keep one deferred reconciliation token so every freshly-created subtree
        # receives the current semantic palette after Tk has finished mounting it.
        self._theme_reconcile_after: str | None = None
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — FUNCTIONS1E")
        self._proposal_query_trace = self.proposal_query_var.trace_add("write", self._proposal_search_changed)
        self.footer_hint.set(
            "FUNCTIONS1E proposal-first Experiments • Research Director → Experiment → Execution"
        )

    def _build_route_content(self) -> None:
        try:
            if not self.analysis_route_active and self.snapshot.route is ShellRoute.EXPERIMENTS:
                for child in self.workspace.winfo_children():
                    child.destroy()
                self._build_experiments_route()
                return
            super()._build_route_content()
        finally:
            # Some inherited/newer workflows rebuild the current route directly
            # (without a store publication), so the ordinary _on_store_change
            # theme pass is not guaranteed to run. Reconcile once Tk is idle.
            self._schedule_theme_reconciliation()

    def _schedule_theme_reconciliation(self) -> None:
        try:
            if self._theme_reconcile_after is not None:
                self.root.after_cancel(self._theme_reconcile_after)
        except (tk.TclError, ValueError):
            pass
        try:
            self._theme_reconcile_after = self.root.after_idle(self._reconcile_theme_after_mount)
        except tk.TclError:
            self._theme_reconcile_after = None

    def _reconcile_theme_after_mount(self) -> None:
        self._theme_reconcile_after = None
        try:
            if not self.root.winfo_exists():
                return
            # ttk themes are process-global to this interpreter. Reassert the
            # known rendering base before applying semantic OL2 styles in case a
            # desktop/native widget or route mount drifted it.
            if self.style.theme_use() != "clam":
                self.style.theme_use("clam")
            self._apply_theme()
            self._refresh_content()
        except tk.TclError:
            # A route may have been destroyed between after_idle scheduling and
            # execution. The next mount schedules a fresh reconciliation.
            return

    # ------------------------------------------------------------------
    # Three-step Experiments workflow
    # ------------------------------------------------------------------
    def _build_experiments_route(self) -> None:
        if self.experiment_workflow_stage == "proposals":
            self.proposal_controller.refresh()
        elif self.experiment_workflow_stage == "execution":
            self.experiment_controller.refresh()

        root = self._frame(self.workspace, "surface.app")
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        _canvas, body = self._new_hidden_scroller(root)
        self._build_experiment_steps(body)

        if self.experiment_workflow_stage == "proposals":
            self._build_proposals_stage(body)
        elif self.experiment_workflow_stage == "experiment":
            self._build_prepared_stage(body)
        else:
            self._build_execution_stage(body)

    def _build_experiment_steps(self, parent: tk.Widget) -> None:
        bar = self._frame(parent, "surface.card")
        bar.pack(fill="x", pady=(0, 8))
        entries = (
            ("proposals", "1 Proposals"),
            ("experiment", "2 Experiment"),
            ("execution", "3 Execution"),
        )
        for stage, label in entries:
            active = stage == self.experiment_workflow_stage
            button = self._button(
                bar,
                label,
                lambda value=stage: self._set_experiment_stage(value),
                kind="primary" if active else "neutral",
            )
            button.pack(side="left", padx=(8 if stage == "proposals" else 2, 2), pady=7)
        prepared = self.proposal_controller.snapshot.prepared
        context = "No proposal prepared"
        if prepared is not None:
            context = f"{prepared.proposal_id} • {prepared.title}"
        self._label(
            bar,
            context,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="right", padx=14)

    def _set_experiment_stage(self, stage: str) -> None:
        if stage not in self.STAGES:
            return
        # Stage navigation is presentation state, not an authorization gate.
        # Let users inspect the Experiment step even when no proposal has been
        # prepared yet; the step renders an explicit empty state instead of
        # silently bouncing them back to Proposals.
        self.experiment_workflow_stage = stage
        if stage == "experiment" and self.proposal_controller.snapshot.prepared is None:
            self.footer_hint.set("No proposal prepared • choose one in Proposals when ready")
        if self.snapshot.route is ShellRoute.EXPERIMENTS and not self.analysis_route_active:
            self._build_route_content()

    # ------------------------------------------------------------------
    # 1 Proposals
    # ------------------------------------------------------------------
    def _build_proposals_stage(self, body: tk.Widget) -> None:
        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(
            header,
            "Research Director Suggestions",
            surface="surface.card",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(side="left", padx=14, pady=12)
        self._label(
            header,
            "Scientific proposals • review is explicit • no automatic execution",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)
        self._button(header, "Refresh", self._refresh_proposals).pack(side="right", padx=(4, 12), pady=8)
        self._button(header, "Open Director Report", self._open_director_report).pack(side="right", padx=4, pady=8)

        filters = self._frame(body, "surface.card")
        filters.pack(fill="x", pady=(0, 8))
        self._label(filters, "Search", surface="surface.card", font=("TkDefaultFont", 9, "bold")).pack(
            side="left", padx=(14, 6), pady=9
        )
        ttk.Entry(filters, textvariable=self.proposal_query_var, style="OL2.TEntry").pack(
            side="left", fill="x", expand=True, padx=(0, 10), pady=7
        )
        self._label(filters, "Status", surface="surface.card", foreground="text.secondary").pack(side="left")
        status = ttk.Combobox(
            filters,
            textvariable=self.proposal_status_var,
            values=self._proposal_status_values(),
            state="readonly",
            width=14,
        )
        status.pack(side="left", padx=(6, 14), pady=7)
        status.bind("<<ComboboxSelected>>", lambda _e: self._apply_proposal_filters())

        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 8))
        self._label(
            card,
            "PROPOSALS",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 6))
        columns = ("status", "priority", "action", "title", "runtime")
        tree = ttk.Treeview(card, columns=columns, show="headings", selectmode="browse", height=9, style="OL2.Treeview")
        for key, title, width, anchor in (
            ("status", "Status", 120, "center"),
            ("priority", "Priority", 85, "center"),
            ("action", "Action", 160, "w"),
            ("title", "Proposal", 560, "w"),
            ("runtime", "Runtime", 110, "center"),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=65, anchor=anchor)
        tree.pack(fill="x", padx=10, pady=(0, 10))
        tree.bind("<<TreeviewSelect>>", self._proposal_selected)
        tree.bind("<Motion>", self._proposal_action_hover)
        tree.bind("<Leave>", lambda _event: self._hide_action_tooltip())
        tree.bind("<Button-3>", self._copy_action_id_from_tree)
        tree.bind("<Control-c>", self._copy_selected_action_id)
        self.proposal_tree = tree

        details = self._frame(body, "surface.card")
        details.pack(fill="x", pady=(0, 12))
        self._label(
            details,
            "SELECTED PROPOSAL",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 5))
        summary = self._label(details, surface="surface.card", foreground="text.primary", font=("TkDefaultFont", 10))
        summary.configure(textvariable=self.proposal_summary_var, wraplength=1120, justify="left")
        summary.pack(anchor="w", fill="x", padx=14, pady=(0, 8))
        actions = self._frame(details, "surface.card")
        actions.pack(fill="x", padx=14, pady=(0, 10))
        self.proposal_actions_frame = actions

        self._populate_proposals()
        self._refresh_proposal_summary()
        self._render_proposal_actions()

    def _proposal_status_values(self) -> tuple[str, ...]:
        statuses = []
        for row in self.proposal_controller.snapshot.proposals:
            if row.ui_status not in statuses:
                statuses.append(row.ui_status)
        return ("All", *statuses)

    def _proposal_search_changed(self, *_args) -> None:
        if self._proposal_search_after is not None:
            try:
                self.root.after_cancel(self._proposal_search_after)
            except tk.TclError:
                pass
        self._proposal_search_after = self.root.after(120, self._apply_proposal_filters)

    def _apply_proposal_filters(self) -> None:
        self._proposal_search_after = None
        self.proposal_controller.set_filters(
            query=self.proposal_query_var.get(),
            status=self.proposal_status_var.get(),
        )
        if self.snapshot.route is ShellRoute.EXPERIMENTS and self.experiment_workflow_stage == "proposals":
            self._populate_proposals()

    def _populate_proposals(self) -> None:
        tree = self.proposal_tree
        if tree is None:
            return
        tree.delete(*tree.get_children())
        snap = self.proposal_controller.snapshot
        for row in snap.visible_proposals:
            tree.insert(
                "",
                "end",
                iid=row.proposal_id,
                values=(row.ui_status, row.priority, row.action_id or "—", row.display_title, row.runtime),
            )
        if snap.selected_proposal_id and tree.exists(snap.selected_proposal_id):
            tree.selection_set(snap.selected_proposal_id)
            tree.focus(snap.selected_proposal_id)
            tree.see(snap.selected_proposal_id)

    def _proposal_selected(self, _event: tk.Event | None = None) -> None:
        tree = self.proposal_tree
        if tree is None or not tree.selection():
            return
        proposal_id = str(tree.selection()[0])
        try:
            if self.proposal_controller.snapshot.selected_proposal_id != proposal_id:
                self.proposal_controller.select(proposal_id)
        except Exception as exc:
            self.footer_hint.set(f"Proposal selection failed: {exc}")
            return
        # Selection events must never remount the full route.  Programmatic
        # Treeview selection also emits <<TreeviewSelect>> on a live Tk loop;
        # rebuilding here creates an infinite select → rebuild → select storm.
        self._refresh_proposal_summary()
        self._render_proposal_actions()

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
        if selected is not None and selected.action_id:
            self._button(
                actions,
                "Copy Action ID",
                self._copy_selected_action_id,
            ).pack(side="left", padx=(8, 0))
        if selected is not None and selected.can_prepare:
            self._button(
                actions,
                "Prepare Experiment",
                self._prepare_director_proposal,
                kind="primary",
            ).pack(side="right")
        elif selected is not None:
            label = "Review Required" if selected.ui_status == "NEEDS REVIEW" else selected.ui_status.title()
            self._button(actions, label, self._open_director_report).pack(side="right")

    def _proposal_action_id(self, proposal_id: str | None) -> str:
        if not proposal_id:
            return ""
        for row in self.proposal_controller.snapshot.proposals:
            if row.proposal_id == proposal_id:
                return row.action_id
        return ""

    def _copy_action_id(self, action_id: str) -> bool:
        canonical = str(action_id)
        if not canonical:
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(canonical)
        self.footer_hint.set(f"Action ID copied: {canonical}")
        return True

    def _copy_selected_action_id(self, _event: tk.Event | None = None) -> str:
        selected = self.proposal_controller.snapshot.selected
        self._copy_action_id(selected.action_id if selected is not None else "")
        return "break"

    def _copy_action_id_from_tree(self, event: tk.Event) -> str:
        tree = self.proposal_tree
        if tree is None:
            return "break"
        row_id = str(tree.identify_row(event.y) or "")
        if row_id:
            tree.selection_set(row_id)
            tree.focus(row_id)
            self._copy_action_id(self._proposal_action_id(row_id))
        return "break"

    def _proposal_action_hover(self, event: tk.Event) -> None:
        tree = self.proposal_tree
        if tree is None:
            return
        row_id = str(tree.identify_row(event.y) or "")
        column = str(tree.identify_column(event.x) or "")
        action_id = self._proposal_action_id(row_id) if column == "#3" else ""
        if not action_id:
            self._hide_action_tooltip()
            return
        if self._action_tooltip is not None and self._action_tooltip_row == row_id:
            return
        self._hide_action_tooltip()
        tip = tk.Toplevel(self.root)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{event.x_root + 14}+{event.y_root + 12}")
        label = tk.Label(
            tip,
            text=action_id,
            background="#fff7d6",
            foreground="#15202b",
            relief="solid",
            borderwidth=1,
            padx=7,
            pady=4,
            font=("TkFixedFont", 9),
        )
        label.pack()
        self._action_tooltip = tip
        self._action_tooltip_row = row_id

    def _hide_action_tooltip(self) -> None:
        tip = self._action_tooltip
        self._action_tooltip = None
        self._action_tooltip_row = None
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass

    def _refresh_proposal_summary(self) -> None:
        snap = self.proposal_controller.snapshot
        row = snap.selected
        if snap.error:
            self.proposal_summary_var.set(f"Research Director report error: {snap.error}")
            return
        if row is None:
            self.proposal_summary_var.set(
                "No Research Director proposals are available. Run Analyze Results / Research Director first."
            )
            return
        guidance = row.display_guidance
        self.proposal_summary_var.set(
            f"{row.display_title}\n"
            f"Why: {row.rationale}\n"
            f"Goal: {row.suggested_target}\n"
            f"Done when: {row.done_when}\n"
            f"Status: {row.ui_status} • validation={row.validation_status} • decision={row.decision} • "
            f"priority={row.priority} • runtime={row.runtime}\n"
            f"Director guidance: {guidance}"
        )

    def _refresh_proposals(self) -> None:
        self.proposal_controller.refresh()
        if self.snapshot.route is ShellRoute.EXPERIMENTS:
            self._build_route_content()
        snap = self.proposal_controller.snapshot
        self.footer_hint.set(snap.error or f"Research Director proposals refreshed: {len(snap.proposals)}")

    def _open_director_report(self) -> None:
        try:
            self.settings_controller.open_path(self.director_report_path)
        except Exception as exc:
            self.footer_hint.set(f"Open Director report failed: {exc}")

    def _prepare_director_proposal(self) -> None:
        try:
            snap = self.proposal_controller.prepare_selected()
        except Exception as exc:
            self.footer_hint.set(f"Prepare Experiment refused: {exc}")
            return
        prepared = snap.prepared
        assert prepared is not None
        self.experiment_workflow_stage = "experiment"
        self.experiment_detail_tab = "overview"
        self.footer_hint.set(
            f"Prepared {prepared.proposal_id} locally • no governance commit or execution was performed"
        )
        self._build_route_content()

    # ------------------------------------------------------------------
    # 2 Experiment
    # ------------------------------------------------------------------
    def _build_prepared_stage(self, body: tk.Widget) -> None:
        prepared = self.proposal_controller.snapshot.prepared
        if prepared is None:
            header = self._frame(body, "surface.card")
            header.pack(fill="x", pady=(0, 8))
            self._label(
                header,
                "Experiment",
                surface="surface.card",
                font=("TkDefaultFont", 16, "bold"),
            ).pack(side="left", padx=14, pady=12)
            self._label(
                header,
                "No proposal prepared",
                surface="surface.card",
                foreground="text.secondary",
                font=("TkDefaultFont", 9),
            ).pack(side="left", padx=10)

            empty = self._frame(body, "surface.card")
            empty.pack(fill="both", expand=True, pady=(0, 8))
            self._build_text_block(
                empty,
                "NO PROPOSAL PREPARED",
                "Choose a Research Director proposal in step 1 and prepare it when you want to review an experiment draft. "
                "Opening this step does not change governance or execution state.",
            )
            actions = self._frame(body, "surface.card")
            actions.pack(fill="x", pady=(0, 12))
            self._button(
                actions,
                "Go to Proposals",
                lambda: self._set_experiment_stage("proposals"),
                kind="primary",
            ).pack(side="left", padx=12, pady=8)
            self._button(
                actions,
                "View Execution",
                lambda: self._set_experiment_stage("execution"),
            ).pack(side="right", padx=12, pady=8)
            return

        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(
            header,
            "Prepared Experiment",
            surface="surface.card",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(side="left", padx=14, pady=12)
        self._label(
            header,
            f"{prepared.proposal_id} • local review draft",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)
        self._button(header, "Open Director Report", self._open_director_report).pack(side="right", padx=12, pady=8)

        tabs = self._frame(body, "surface.card")
        tabs.pack(fill="x", pady=(0, 8))
        for tab, label in (("overview", "Overview"), ("conditions", "Conditions"), ("review", "Review")):
            self._button(
                tabs,
                label,
                lambda value=tab: self._set_experiment_detail_tab(value),
                kind="primary" if tab == self.experiment_detail_tab else "neutral",
            ).pack(side="left", padx=(8 if tab == "overview" else 2, 2), pady=7)

        card = self._frame(body, "surface.card")
        card.pack(fill="both", expand=True, pady=(0, 8))
        if self.experiment_detail_tab == "overview":
            self._build_prepared_overview(card, prepared)
        elif self.experiment_detail_tab == "conditions":
            self._build_prepared_conditions(card, prepared)
        else:
            self._build_prepared_review(card, prepared)

        actions = self._frame(body, "surface.card")
        actions.pack(fill="x", pady=(0, 12))
        self._button(actions, "Back to Proposals", lambda: self._set_experiment_stage("proposals")).pack(side="left", padx=12, pady=8)
        self._button(actions, "View Execution", lambda: self._set_experiment_stage("execution"), kind="primary").pack(side="right", padx=12, pady=8)
        self._label(
            actions,
            "Prepared locally only • audited approval/materialization remains a later explicit step",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="right", padx=8)

    def _set_experiment_detail_tab(self, tab: str) -> None:
        if tab not in self.DETAIL_TABS:
            return
        self.experiment_detail_tab = tab
        if self.snapshot.route is ShellRoute.EXPERIMENTS and self.experiment_workflow_stage == "experiment":
            self._build_route_content()

    def _build_text_block(self, parent: tk.Widget, title: str, text: str) -> None:
        self._label(
            parent,
            title,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 4))
        label = self._label(parent, text, surface="surface.card", foreground="text.primary", font=("TkDefaultFont", 10))
        label.configure(wraplength=1080, justify="left")
        label.pack(anchor="w", fill="x", padx=16, pady=(0, 4))

    def _build_prepared_overview(self, card: tk.Widget, prepared) -> None:
        self._build_text_block(card, "EXPERIMENT", prepared.title)
        self._build_text_block(card, "WHY", prepared.rationale)
        self._build_text_block(card, "GOAL", prepared.suggested_target)
        self._build_text_block(card, "EXPECTED GAIN", prepared.expected_gain)
        self._build_text_block(card, "SCOPE", f"Priority {prepared.priority} • runtime {prepared.runtime}")

    def _build_prepared_conditions(self, card: tk.Widget, prepared) -> None:
        principles = ", ".join(prepared.affected_principles) or "Not explicitly declared"
        signals = ", ".join(prepared.affected_signals) or "Not explicitly declared"
        self._build_text_block(card, "TARGET", prepared.suggested_target)
        self._build_text_block(card, "AFFECTED PRINCIPLES", principles)
        self._build_text_block(card, "AFFECTED SIGNALS", signals)
        self._build_text_block(card, "SUCCESS CRITERION", prepared.done_when)
        self._build_text_block(
            card,
            "RUNTIME CONDITIONS",
            "Field geometry, treatment/control arms, seeds and replicates are resolved by the existing planner/materializer after governance approval. They are intentionally not invented by the Launcher.",
        )

    def _build_prepared_review(self, card: tk.Widget, prepared) -> None:
        row = self.proposal_controller.snapshot.selected
        self._build_text_block(card, "VALIDATION", prepared.validation_status)
        self._build_text_block(card, "HUMAN DECISION", prepared.decision)
        self._build_text_block(card, "DONE WHEN", prepared.done_when)
        if row is not None:
            self._build_text_block(card, "ISSUES", str(row.issue_count))
            self._build_text_block(card, "DIRECTOR GUIDANCE", row.preferred_resolution or "No additional guidance.")
        self._build_text_block(
            card,
            "SAFETY",
            "This screen is a review projection only. It has not written human-review decisions, applied patches, materialized an experiment runtime or authorized execution.",
        )

    # ------------------------------------------------------------------
    # 3 Execution: reuse FUNCTIONS1D canonical inventory semantics
    # ------------------------------------------------------------------
    def _build_execution_stage(self, body: tk.Widget) -> None:
        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(header, "Registered Experiments", surface="surface.card", font=("TkDefaultFont", 16, "bold")).pack(
            side="left", padx=14, pady=12
        )
        self._label(
            header,
            "Canonical SQLite • read-only execution inventory",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)
        self._button(header, "Refresh", self._refresh_execution_catalog).pack(side="right", padx=12, pady=8)

        filters = self._frame(body, "surface.card")
        filters.pack(fill="x", pady=(0, 8))
        self._label(filters, "Search", surface="surface.card", font=("TkDefaultFont", 9, "bold")).pack(side="left", padx=(14, 6), pady=9)
        ttk.Entry(filters, textvariable=self.experiment_query_var, style="OL2.TEntry").pack(side="left", fill="x", expand=True, padx=(0, 10), pady=7)
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
        self._label(experiments, "EXECUTION", surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 9, "bold")).pack(
            anchor="w", padx=14, pady=(10, 6)
        )
        columns = ("id", "title", "status", "runs", "updated")
        tree = ttk.Treeview(experiments, columns=columns, show="headings", selectmode="browse", height=8, style="OL2.Treeview")
        for key, title, width, anchor in (
            ("id", "Experiment", 210, "w"),
            ("title", "Title", 500, "w"),
            ("status", "Status", 120, "center"),
            ("runs", "Runs", 80, "center"),
            ("updated", "Updated", 210, "w"),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=60, anchor=anchor)
        tree.pack(fill="x", padx=10, pady=(0, 10))
        tree.bind("<<TreeviewSelect>>", self._experiment_selected)
        self.experiment_tree = tree

        details = self._frame(body, "surface.card")
        details.pack(fill="x", pady=(0, 8))
        self._label(details, "SELECTED EXPERIMENT", surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 9, "bold")).pack(
            anchor="w", padx=14, pady=(10, 5)
        )
        summary = self._label(details, surface="surface.card", foreground="text.primary", font=("TkDefaultFont", 10))
        summary.configure(textvariable=self.experiment_summary_var, wraplength=1120, justify="left")
        summary.pack(anchor="w", padx=14, pady=(0, 10))

        conditions = self._frame(body, "surface.card")
        conditions.pack(fill="x", pady=(0, 8))
        self._experiment_conditions_card = conditions
        self._label(conditions, "CONDITIONS", surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 9, "bold")).pack(
            anchor="w", padx=14, pady=(10, 6)
        )
        condition_columns = ("id", "name", "field", "topology", "boundary", "initial", "linked")
        ctree = ttk.Treeview(conditions, columns=condition_columns, show="headings", selectmode="browse", height=5, style="OL2.Treeview")
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
        context = self._label(action, surface="surface.card", foreground="text.secondary", font=("TkDefaultFont", 9))
        context.configure(textvariable=self.experiment_context_var, wraplength=850, justify="left")
        context.pack(side="left", fill="x", expand=True)
        prepare_button = self._button(action, "Prepare in Runs", self._prepare_selected_experiment_in_runs, kind="primary")
        prepare_button.pack(side="right", padx=(8, 0))
        self._prepare_in_runs_button = prepare_button

        self._populate_experiment_table()
        self._populate_condition_table()
        self._refresh_experiment_summary()
        self._refresh_experiment_context_summary()
        if not self.experiment_controller.snapshot.experiments:
            self.experiment_summary_var.set(
                "No registered experiments yet. Research Director proposals appear in step 1; audited approval/materialization will create execution records here."
            )

    def _refresh_execution_catalog(self) -> None:
        self.experiment_controller.refresh()
        if self.snapshot.route is ShellRoute.EXPERIMENTS and self.experiment_workflow_stage == "execution":
            self._build_route_content()
        snap = self.experiment_controller.snapshot
        self.footer_hint.set(snap.error or f"Execution inventory refreshed: {len(snap.experiments)} experiments")


__all__ = ["ObserverLauncher2FunctionsExperimentWorkflowShell"]
