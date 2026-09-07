"""OL2-MUTATIONS2: Mutation Analyzer evidence inside the Execution step."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from Analyzer_next.execution.observer.shell2.dialogs1.app import ObserverLauncher2DialogsShell
from Analyzer_next.execution.observer.shell2.mutations1.model import MutationRecord

from .controller import MutationAnalysisController


def _fmt_number(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return f"{value:,}"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 1000:
        return f"{number:,.2f}"
    if abs(number) >= 10:
        return f"{number:.3f}"
    return f"{number:.5f}".rstrip("0").rstrip(".")


class ObserverLauncher2Mutations2Shell(ObserverLauncher2DialogsShell):
    """Project existing Mutation Analyzer evidence without duplicating science."""

    def __init__(
        self,
        root: tk.Tk,
        *args,
        mutation_analysis_controller: MutationAnalysisController,
        **kwargs,
    ) -> None:
        self.mutation_analysis_controller = mutation_analysis_controller
        super().__init__(root, *args, **kwargs)
        self.mutation_analysis_status_var = tk.StringVar(
            value="Select an observed mutation to inspect scientific effect."
        )
        self.mutation_effect_var = tk.StringVar(value="—")
        self.mutation_confidence_var = tk.StringVar(value="—")
        self.mutation_baseline_var = tk.StringVar(value="—")
        self.mutation_control_var = tk.StringVar(value="—")
        self.mutation_interpretation_var = tk.StringVar(value="No analysis report selected.")
        self.mutation_control_detail_var = tk.StringVar(value="")
        self.mutation_metric_tree: ttk.Treeview | None = None
        self.mutation_analyze_button: tk.Widget | None = None
        self.mutation_open_report_button: tk.Widget | None = None
        self.root.title("ARCHON Observer Launcher 2.0 — MUTATIONS2")
        self.footer_hint.set(
            "MUTATIONS2 • explicit Mutation Analyzer • effect/confidence/baseline/control evidence • no automatic analysis"
        )

    # ------------------------------------------------------------------
    # 3 Execution: run state + scientific interpretation in one screen.
    # ------------------------------------------------------------------
    def _build_mutation_execution(self, body: tk.Widget) -> None:
        self.mutation_controller.refresh_records()
        self._sync_mutation_analysis_selection()

        header = self._frame(body, "surface.card")
        header.pack(fill="x", pady=(0, 8))
        self._label(
            header,
            "Mutation Evidence",
            surface="surface.card",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(side="left", padx=14, pady=12)
        self._label(
            header,
            "Run isolated mutants, then compare saved evidence with the canonical baseline through Mutation Analyzer.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", padx=10)
        self._button(header, "Refresh", self._refresh_mutation_records).pack(
            side="right", padx=12, pady=8
        )

        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 8))
        columns = ("mutation", "parent", "mode", "changes", "run", "analysis", "created")
        tree = ttk.Treeview(
            card,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=8,
            style="OL2.Treeview",
        )
        for key, title, width, anchor in (
            ("mutation", "Mutation", 270, "w"),
            ("parent", "Parent", 80, "center"),
            ("mode", "Mode", 120, "center"),
            ("changes", "Changes", 75, "center"),
            ("run", "Run", 95, "center"),
            ("analysis", "Analysis", 95, "center"),
            ("created", "Created", 155, "w"),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor=anchor)
        tree.pack(fill="x", padx=12, pady=(10, 8))
        tree.bind("<<TreeviewSelect>>", self._mutation_record_selected)
        self.mutation_tree = tree
        self._fill_mutation_records()

        detail = self._frame(body, "surface.card")
        detail.pack(fill="x", pady=(0, 8))
        label = self._label(
            detail,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 10),
        )
        label.configure(textvariable=self.mutation_record_summary, wraplength=760, justify="left")
        label.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        self._button(detail, "Open Folder", self._open_selected_mutation_folder).pack(
            side="right", padx=(4, 12), pady=10
        )
        self._button(detail, "Run Selected", self._run_selected_mutation, kind="primary").pack(
            side="right", padx=4, pady=10
        )
        self._update_mutation_record_summary()

        analysis = self._frame(body, "surface.card")
        analysis.pack(fill="x", pady=(0, 8))
        top = self._frame(analysis, "surface.card")
        top.pack(fill="x", padx=14, pady=(10, 6))
        self._label(
            top,
            "SCIENTIFIC COMPARISON",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="left")
        self.mutation_open_report_button = self._button(
            top, "Open Report", self._open_selected_mutation_report
        )
        self.mutation_open_report_button.pack(side="right", padx=(4, 0))
        self.mutation_analyze_button = self._button(
            top, "Analyze Selected", self._analyze_selected_mutation, kind="primary"
        )
        self.mutation_analyze_button.pack(side="right", padx=4)

        status = self._label(
            analysis,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        status.configure(textvariable=self.mutation_analysis_status_var, wraplength=970, justify="left")
        status.pack(anchor="w", padx=14, pady=(0, 8))

        cards = self._frame(analysis, "surface.card")
        cards.pack(fill="x", padx=10, pady=(0, 8))
        for column in range(4):
            cards.grid_columnconfigure(column, weight=1, uniform="mutation-analysis")
        self._analysis_card(cards, 0, "Effect", self.mutation_effect_var)
        self._analysis_card(cards, 1, "Confidence", self.mutation_confidence_var)
        self._analysis_card(cards, 2, "Baseline", self.mutation_baseline_var)
        self._analysis_card(cards, 3, "Required control", self.mutation_control_var)

        interpretation = self._label(
            analysis,
            surface="surface.card",
            foreground="text.primary",
            font=("TkDefaultFont", 9),
        )
        interpretation.configure(
            textvariable=self.mutation_interpretation_var,
            wraplength=970,
            justify="left",
        )
        interpretation.pack(anchor="w", fill="x", padx=14, pady=(2, 8))

        metric_box = self._frame(analysis, "surface.card")
        metric_box.pack(fill="x", padx=14, pady=(0, 8))
        metric_columns = ("metric", "baseline", "mutant", "delta", "relative")
        metrics = ttk.Treeview(
            metric_box,
            columns=metric_columns,
            show="headings",
            height=5,
            style="OL2.Treeview",
        )
        for key, title, width, anchor in (
            ("metric", "Metric", 270, "w"),
            ("baseline", "Baseline", 130, "e"),
            ("mutant", "Mutant", 130, "e"),
            ("delta", "Δ", 130, "e"),
            ("relative", "Relative Δ", 130, "e"),
        ):
            metrics.heading(key, text=title)
            metrics.column(key, width=width, anchor=anchor)
        metrics.pack(fill="x")
        self.mutation_metric_tree = metrics

        control = self._label(
            analysis,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        control.configure(textvariable=self.mutation_control_detail_var, wraplength=970, justify="left")
        control.pack(anchor="w", fill="x", padx=14, pady=(0, 12))
        self._refresh_mutation_analysis_widgets()

        save = self._frame(body, "surface.card")
        save.pack(fill="x", pady=(0, 8))
        self._label(
            save,
            "SAVE POLICY",
            surface="surface.card",
            foreground="text.muted",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(side="left", padx=(14, 8), pady=12)
        self._label(
            save, "Autosave ticks", surface="surface.card", foreground="text.secondary"
        ).pack(side="left", padx=(4, 6))
        ttk.Entry(
            save, textvariable=self.mutation_autosave_var, style="OL2.TEntry", width=12
        ).pack(side="left", padx=(0, 12), pady=8)
        self._label(
            save,
            "Periodic checkpoints use this cadence; mutation horizon is manual, so final checkpoint = Save & Stop.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        ).pack(side="left", fill="x", expand=True, padx=(0, 14), pady=12)

    def _analysis_card(self, parent: tk.Widget, column: int, title: str, variable: tk.StringVar) -> None:
        card = self._frame(parent, "surface.elevated")
        card.grid(row=0, column=column, sticky="nsew", padx=4, pady=2)
        self._label(
            card,
            title.upper(),
            surface="surface.elevated",
            foreground="text.secondary",
            font=("TkDefaultFont", 8, "bold"),
        ).pack(anchor="w", padx=10, pady=(8, 2))
        value = self._label(
            card,
            surface="surface.elevated",
            foreground="text.primary",
            font=("TkDefaultFont", 10, "bold"),
        )
        value.configure(textvariable=variable, wraplength=220, justify="left")
        value.pack(anchor="w", padx=10, pady=(0, 8))

    def _fill_mutation_records(self) -> None:
        tree = self.mutation_tree
        if tree is None:
            return
        tree.delete(*tree.get_children())
        reader = self.mutation_analysis_controller.reader
        for record in self.mutation_controller.snapshot.records:
            analysis_state = "REPORT" if reader.has_report(record) else "—"
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
                    analysis_state,
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
        self._sync_mutation_analysis_selection(force=True)
        self._update_mutation_record_summary()
        self._refresh_mutation_analysis_widgets()

    def _sync_mutation_analysis_selection(self, *, force: bool = False) -> None:
        record = self.mutation_controller.snapshot.selected_record
        current = self.mutation_analysis_controller.snapshot
        record_id = record.mutation_id if record else None
        if current.busy and current.selected_mutation_id == record_id:
            return
        if force or current.selected_mutation_id != record_id:
            try:
                self.mutation_analysis_controller.select(record)
            except ValueError as exc:
                self.mutation_analysis_controller.reject(record_id, str(exc))
        elif record is not None and current.analysis is None:
            try:
                if self.mutation_analysis_controller.reader.has_report(record):
                    self.mutation_analysis_controller.refresh(record)
            except ValueError:
                pass

    def _refresh_mutation_analysis_widgets(self) -> None:
        snapshot = self.mutation_analysis_controller.snapshot
        record = self.mutation_controller.snapshot.selected_record
        view = snapshot.analysis
        self.mutation_analysis_status_var.set(snapshot.status)
        if view is None:
            self.mutation_effect_var.set("—")
            self.mutation_confidence_var.set("—")
            self.mutation_baseline_var.set("—")
            self.mutation_control_var.set("—")
            self.mutation_interpretation_var.set(
                "No Mutation Analyzer report yet. Run and save the mutation, then choose Analyze Selected."
            )
            self.mutation_control_detail_var.set("")
        else:
            self.mutation_effect_var.set(view.effect_primary)
            self.mutation_confidence_var.set(view.confidence_label)
            horizon = "—" if view.comparison_end_tick is None else f"tick {view.comparison_end_tick:,}"
            self.mutation_baseline_var.set(
                f"{view.baseline_match_type} • {view.baseline_coverage:.0%} • {horizon}"
            )
            self.mutation_control_var.set(view.control_label)
            labels = ", ".join(view.effect_labels) or "no secondary labels"
            evidence = " ".join(view.evidence[:3]) or "No interpretation evidence text was published."
            warnings = (
                f" Warnings: {'; '.join(view.warnings[:2])}"
                if view.warnings else ""
            )
            self.mutation_interpretation_var.set(
                f"Labels: {labels}. {evidence}{warnings}"
            )
            if view.required_control:
                bits = [f"Required control: {view.required_control_reason or 'reason not specified'}"]
                if view.required_control_target_ticks is not None:
                    bits.append(f"target {view.required_control_target_ticks:,} ticks")
                if view.required_control_sample_interval is not None:
                    bits.append(f"sample every {view.required_control_sample_interval:,}")
                self.mutation_control_detail_var.set(" • ".join(bits))
            else:
                self.mutation_control_detail_var.set(
                    f"Lifecycle reconciliation: {view.lifecycle_status} • same seed: {view.baseline_same_seed}"
                )

        tree = self.mutation_metric_tree
        if tree is not None:
            tree.delete(*tree.get_children())
            if view is not None:
                for index, row in enumerate(view.metric_deltas):
                    relative = "—" if row.relative_delta is None else f"{row.relative_delta:+.1%}"
                    tree.insert(
                        "",
                        "end",
                        iid=f"metric-{index}",
                        values=(
                            row.metric,
                            _fmt_number(row.baseline),
                            _fmt_number(row.mutant),
                            _fmt_number(row.absolute_delta),
                            relative,
                        ),
                    )

        can_analyze = self.mutation_analysis_controller.can_analyze(record)
        if self.mutation_analyze_button is not None:
            self.mutation_analyze_button.configure(
                state=("normal" if can_analyze else "disabled")
            )
        if self.mutation_open_report_button is not None:
            self.mutation_open_report_button.configure(
                state=("normal" if view is not None else "disabled")
            )

    def _refresh_mutation_records(self) -> None:
        port = getattr(self.mutation_controller, "port", None)
        invalidate = getattr(port, "invalidate_records", None)
        if callable(invalidate):
            invalidate()
        self.mutation_controller.refresh_records()
        self._sync_mutation_analysis_selection(force=True)
        self._fill_mutation_records()
        self._update_mutation_record_summary()
        self._refresh_mutation_analysis_widgets()
        self.footer_hint.set("Mutation manifests and analysis reports refreshed")

    def _analyze_selected_mutation(self) -> None:
        record = self.mutation_controller.snapshot.selected_record
        if record is None:
            self.footer_hint.set("Select a mutation first")
            return
        if self.control_controller.process_active:
            self.footer_hint.set("Stop the active Observer before analyzing mutation evidence")
            return
        try:
            self.mutation_analysis_controller.begin(record)
        except ValueError as exc:
            self.footer_hint.set(str(exc))
            return
        self._refresh_mutation_analysis_widgets()
        self.footer_hint.set(f"Mutation Analyzer running for {record.mutation_id}…")
        threading.Thread(
            target=self._mutation_analysis_worker,
            args=(record,),
            daemon=True,
        ).start()

    def _mutation_analysis_worker(self, record: MutationRecord) -> None:
        try:
            outcome = self.mutation_analysis_controller.run(record)
        except Exception as exc:
            from .model import MutationAnalysisRunOutcome
            outcome = MutationAnalysisRunOutcome(exit_code=2, stderr=str(exc))
        try:
            self.root.after(0, self._finish_mutation_analysis, record, outcome)
        except tk.TclError:
            return

    def _finish_mutation_analysis(self, record: MutationRecord, outcome) -> None:
        # Keep the completion hot path local to the selected mutation.  The
        # Analysis column is independent from the run-status column, so a new
        # per-mutation report never requires a global mutation-tree rescan.
        try:
            snapshot = self.mutation_analysis_controller.finish(record, outcome)
        except Exception as exc:
            self.dialogs.error("Mutation analysis failed", str(exc))
            return
        self._fill_mutation_records()
        self._update_mutation_record_summary()
        self._refresh_mutation_analysis_widgets()
        if snapshot.analysis is not None:
            self.footer_hint.set(
                f"Mutation analysis complete • {snapshot.analysis.effect_primary} • {snapshot.analysis.confidence_label}"
            )
        else:
            self.footer_hint.set(snapshot.status)
            if not outcome.ok:
                self.dialogs.error("Mutation analysis failed", snapshot.status)

    def _open_selected_mutation_report(self) -> None:
        view = self.mutation_analysis_controller.snapshot.analysis
        if view is None:
            self.footer_hint.set("Analyze the selected mutation first")
            return
        target = view.report_markdown or view.report_json
        try:
            self.settings_controller.open_path(target)
        except Exception as exc:
            self.footer_hint.set(f"Could not open mutation report: {exc}")


__all__ = ["ObserverLauncher2Mutations2Shell"]
