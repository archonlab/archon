"""OL2-SAVE-POLICY1: one explicit checkpoint policy across live workflows."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from Analyzer_next.execution.observer.shell2.campaigns1.model import CampaignStage
from Analyzer_next.execution.observer.shell2.queue2.app import ObserverLauncher2Queue2Shell
from Analyzer_next.execution.observer.shell2.store import ShellRoute

from .campaign_controller import SavePolicyCampaignController
from .model import SavePolicy
from .service import with_autosave_ticks


class ObserverLauncher2SavePolicyShell(ObserverLauncher2Queue2Shell):
    """Expose autosave before review, keep Queue immutable, explain final saves."""

    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        campaign_controller = kwargs.get("campaign_controller")
        if not isinstance(campaign_controller, SavePolicyCampaignController):
            raise TypeError("SAVE-POLICY1 requires SavePolicyCampaignController")
        self.campaign_autosave_var = tk.StringVar(master=root, value=str(campaign_controller.autosave_every))
        self.mutation_autosave_var = tk.StringVar(master=root, value="5000")
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — SAVE-POLICY1")
        self.footer_hint.set(
            "SAVE-POLICY1 • periodic checkpoints are explicit • finite runs always save once at max ticks"
        )

    # ------------------------------------------------------------------
    # Runs / CONFIG1
    # ------------------------------------------------------------------
    def _field(self, parent, row, label, key, values=None):
        if key == "autosave_every":
            label = "Autosave ticks"
        return super()._field(parent, row, label, key, values)

    def _build_configuration_form(self) -> None:
        super()._build_configuration_form()
        card = self._frame(self.configure_tab, "surface.card")
        card.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        self._label(
            card,
            "SAVE POLICY",
            surface="surface.card",
            foreground="text.muted",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=12, pady=(10, 3))
        self._label(
            card,
            "Autosave ticks controls periodic checkpoints. 0 disables periodic autosave. "
            "For a finite integrated run, reaching Maximum ticks still writes one final checkpoint before exit.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w", padx=12, pady=(0, 10))

    def _refresh_review_panel(self) -> None:
        super()._refresh_review_panel()
        if not hasattr(self, "review_issues_label"):
            return
        review = self.config_store.config_snapshot.review
        if review is None or not review.valid or review.prepared is None:
            return
        prepared = review.prepared
        policy = SavePolicy(
            max_ticks=prepared.run_spec.max_ticks,
            autosave_ticks=prepared.effective_draft.autosave_every,
            output_dir=prepared.effective_draft.output_dir,
            finite_exit=True,
        )
        base = str(self.review_issues_label.cget("text"))
        self.review_issues_label.configure(text=f"{base}\n\n{policy.multiline}")

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------
    def _build_campaign_editor(self, body: tk.Widget) -> None:
        if not self.campaign_controller.snapshot.draft.selected_rule_ids:
            self._build_campaign_empty(
                body,
                "No campaign scope",
                "Choose one or more canonical worlds first.",
                CampaignStage.SCOPE,
            )
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
            (0, 2, "Autosave ticks", self.campaign_autosave_var),
            (1, 0, "Repetitions / world", self.campaign_repetitions_var),
            (1, 2, "Sample every", self.campaign_sample_every_var),
            (2, 0, "Pressure every", self.campaign_pressure_every_var),
            (2, 2, "Seed start", self.campaign_seed_start_var),
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
            "Autosave 0 = periodic checkpoints off. Every finite campaign row still saves once at Max ticks. "
            "Leave Seed start empty for runtime-random seeds.",
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
        super()._sync_campaign_draft()
        self.campaign_controller.set_autosave_every(int(self.campaign_autosave_var.get().strip()))

    def _build_campaign_queue_preview(self, body: tk.Widget) -> None:
        super()._build_campaign_queue_preview(body)
        tree = getattr(self, "campaign_plan_tree", None)
        plan = self.campaign_controller.snapshot.plan
        if tree is None or plan is None:
            return
        try:
            tree.heading("horizon", text="Horizon / autosave")
            tree.column("horizon", width=170)
        except Exception:
            return
        for row in plan.rows:
            autosave = row.prepared.effective_draft.autosave_every
            periodic = "off" if autosave == 0 else f"{autosave:,}"
            tree.set(str(row.ordinal), "horizon", f"{row.prepared.run_spec.max_ticks:,} / {periodic} + final")

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def _build_mutation_execution(self, body: tk.Widget) -> None:
        super()._build_mutation_execution(body)
        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 8))
        self._label(card, "SAVE POLICY", surface="surface.card", foreground="text.muted", font=("TkDefaultFont", 9, "bold")).pack(
            side="left", padx=(14, 8), pady=12
        )
        self._label(card, "Autosave ticks", surface="surface.card", foreground="text.secondary").pack(side="left", padx=(4, 6))
        ttk.Entry(card, textvariable=self.mutation_autosave_var, style="OL2.TEntry", width=12).pack(side="left", padx=(0, 12), pady=8)
        self._label(
            card,
            "Mutation runs currently have a manual horizon: periodic checkpoints use this cadence; final checkpoint = Save & Stop.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", fill="x", expand=True, padx=(0, 14), pady=12)

    def _run_selected_mutation(self) -> None:
        if self.control_controller.process_active:
            self.footer_hint.set("Stop the active Observer before launching a mutation")
            return
        try:
            autosave_ticks = int(self.mutation_autosave_var.get().strip())
            if autosave_ticks < 0:
                raise ValueError("Autosave ticks cannot be negative")
            prepared = self.mutation_controller.prepare_selected_launch()
            prepared = with_autosave_ticks(prepared, autosave_ticks)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Mutation launch refused", str(exc), parent=self.root)
            return
        record = self.mutation_controller.snapshot.selected_record
        assert record is not None
        periodic = "Off" if autosave_ticks == 0 else f"Every {autosave_ticks:,} ticks"
        if not messagebox.askyesno(
            "Run mutation",
            f"Launch {record.mutation_id}?\n\nParent: Rule {record.parent_rule_id:05d}\n"
            f"Changes: {record.change_count}\nAutosave: {periodic}\n"
            "Final save: Save & Stop (manual-horizon mutation)\n\n"
            "This is an isolated mutation run. Canonical Atlas files are not modified.",
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
        self.footer_hint.set(
            f"Mutation {record.mutation_id} launched • autosave {autosave_ticks:,} ticks • final via Save & Stop"
        )

    # ------------------------------------------------------------------
    # Queue: immutable visibility only
    # ------------------------------------------------------------------
    def _build_queue_route(self) -> None:
        super()._build_queue_route()
        tree = getattr(self, "queue_tree", None)
        if tree is None:
            return
        panel = tree.master
        note = self._label(
            panel,
            "Save policy is frozen before Queue handoff. Queue shows Horizon / autosave only; finite rows always write a final checkpoint at max ticks.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 8),
        )
        note.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))


__all__ = ["ObserverLauncher2SavePolicyShell"]
