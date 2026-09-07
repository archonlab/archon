"""OL2-FUNCTIONS1G + BRIDGE4 verified runtime execution handoff.

Observer runtimes keep the existing Stage 6.5 authorization → QUEUE1 path.
BRIDGE4 Universe Search runtimes instead expose an explicit two-step
Authorize Search Launch → Start Search path and are never projected into the
Observer queue.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from Analyzer_next.execution.observer.shell2.functions1f.app import (
    ObserverLauncher2FunctionsExperimentPipelineShell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute

from .controller import ExperimentRuntimeHandoffController
from .model import (
    RuntimeAuthorizationResult,
    RuntimeQueuePreparation,
    SearchDispatchResult,
    SearchLauncherOpenResult,
)


class ObserverLauncher2FunctionsExperimentQueueShell(
    ObserverLauncher2FunctionsExperimentPipelineShell
):
    """Authorize/route Observer workloads or explicitly dispatch Search workloads."""

    def __init__(
        self,
        root: tk.Tk,
        *args,
        runtime_handoff_controller: ExperimentRuntimeHandoffController,
        **kwargs,
    ) -> None:
        if not isinstance(runtime_handoff_controller, ExperimentRuntimeHandoffController):
            raise TypeError("FUNCTIONS1G requires ExperimentRuntimeHandoffController")
        self.runtime_handoff_controller = runtime_handoff_controller
        self.runtime_handoff_tree: ttk.Treeview | None = None
        self.runtime_handoff_summary_var = tk.StringVar(master=root, value="Select a registered experiment.")
        self.search_execution_summary_var = tk.StringVar(master=root, value="")
        self._runtime_handoff_button: tk.Widget | None = None
        self._runtime_handoff_card: tk.Widget | None = None
        self._runtime_handoff_title_label: tk.Widget | None = None
        self._runtime_handoff_context_label: tk.Widget | None = None
        self._runtime_handoff_open_queue_button: tk.Widget | None = None
        self._search_execution_card: tk.Widget | None = None
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — FUNCTIONS1G + BRIDGE4")
        self.footer_hint.set(
            "BRIDGE4 • Observer runtimes → verified Queue • Universe Search → explicit authorization + direct Search dispatch"
        )

    # ------------------------------------------------------------------
    # Execution stage: keep FUNCTIONS1D inventory and append typed handoff.
    # ------------------------------------------------------------------
    def _build_execution_stage(self, body: tk.Widget) -> None:
        super()._build_execution_stage(body)
        experiment_id = self.experiment_controller.snapshot.selected_experiment_id
        self.runtime_handoff_controller.refresh(experiment_id)

        search_card = self._frame(body, "surface.card")
        self._search_execution_card = search_card
        self._label(
            search_card,
            "UNIVERSE SEARCH EXECUTION",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 5))
        search_summary = self._label(
            search_card,
            surface="surface.card",
            foreground="text.primary",
            font=("TkDefaultFont", 10),
        )
        search_summary.configure(
            textvariable=self.search_execution_summary_var,
            wraplength=1120,
            justify="left",
        )
        search_summary.pack(anchor="w", padx=14, pady=(0, 10))
        search_card.pack_forget()

        card = self._frame(body, "surface.card")
        card.pack(fill="x", pady=(0, 12))
        self._runtime_handoff_card = card
        header = self._frame(card, "surface.card")
        header.pack(fill="x", padx=14, pady=(10, 6))
        title_label = self._label(
            header,
            "AUTHORIZED RUNTIME HANDOFF",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9, "bold"),
        )
        title_label.pack(side="left")
        self._runtime_handoff_title_label = title_label
        context_label = self._label(
            header,
            "Stage 6.5 authorization is explicit • Queue receives rows but is not started",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        context_label.pack(side="left", padx=12)
        self._runtime_handoff_context_label = context_label
        open_queue = self._button(header, "Open Queue", lambda: self.store.select_route(ShellRoute.QUEUE))
        open_queue.pack(side="right")
        self._runtime_handoff_open_queue_button = open_queue
        self._button(header, "Refresh", self._refresh_runtime_handoff).pack(side="right", padx=(0, 6))

        columns = ("runtime", "status", "runs", "authorization", "updated")
        tree = ttk.Treeview(
            card,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=5,
            style="OL2.Treeview",
        )
        for key, title, width, anchor in (
            ("runtime", "Runtime", 300, "w"),
            ("status", "Status", 220, "center"),
            ("runs", "Work", 100, "center"),
            ("authorization", "Authorization", 240, "w"),
            ("updated", "Updated", 210, "w"),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=60, anchor=anchor)
        tree.pack(fill="x", padx=10, pady=(0, 7))
        tree.bind("<<TreeviewSelect>>", self._runtime_handoff_selected)
        self.runtime_handoff_tree = tree

        action = self._frame(card, "surface.card")
        action.pack(fill="x", padx=14, pady=(0, 10))
        summary = self._label(
            action,
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        summary.configure(textvariable=self.runtime_handoff_summary_var, wraplength=850, justify="left")
        summary.pack(side="left", fill="x", expand=True)
        button = self._button(
            action,
            "Authorize & Add to Queue",
            self._authorize_and_queue_selected_runtime,
            kind="primary",
        )
        button.pack(side="right", padx=(8, 0))
        self._runtime_handoff_button = button
        self._populate_runtime_handoff_table()
        self._refresh_runtime_handoff_summary()

    def _experiment_selected(self, event: tk.Event | None = None) -> None:
        super()._experiment_selected(event)
        if self.experiment_workflow_stage != "execution":
            return
        experiment_id = self.experiment_controller.snapshot.selected_experiment_id
        self.runtime_handoff_controller.refresh(experiment_id)
        self._populate_runtime_handoff_table()
        self._refresh_runtime_handoff_summary()

    def _refresh_execution_catalog(self) -> None:
        super()._refresh_execution_catalog()
        if self.experiment_workflow_stage == "execution":
            experiment_id = self.experiment_controller.snapshot.selected_experiment_id
            self.runtime_handoff_controller.refresh(experiment_id)
            self._populate_runtime_handoff_table()
            self._refresh_runtime_handoff_summary()

    def _refresh_runtime_handoff(self) -> None:
        experiment_id = self.experiment_controller.snapshot.selected_experiment_id
        snap = self.runtime_handoff_controller.refresh(experiment_id)
        self._populate_runtime_handoff_table()
        self._refresh_runtime_handoff_summary()
        self.footer_hint.set(snap.error or snap.message)

    def _populate_runtime_handoff_table(self) -> None:
        tree = self.runtime_handoff_tree
        if tree is None:
            return
        try:
            if not tree.winfo_exists():
                return
        except tk.TclError:
            return
        tree.delete(*tree.get_children())
        snap = self.runtime_handoff_controller.snapshot
        for row in snap.runtimes:
            if row.is_search:
                if row.search_execution_started:
                    authorization = f"STARTED • PID {row.search_pid or '?'}"
                elif row.can_start_search:
                    authorization = f"VERIFIED • {row.search_authorization_id}"
                else:
                    authorization = row.search_verification_status or "Not authorized"
                work = f"{row.candidate_slots} slots" if row.candidate_slots else "Search"
            else:
                authorization = (
                    f"VERIFIED • {row.authorization_id}"
                    if row.can_queue
                    else row.verification_status or "Not authorized"
                )
                work = f"{row.run_count} run(s)"
            tree.insert(
                "",
                "end",
                iid=row.runtime_id,
                values=(row.runtime_id, row.status, work, authorization, row.updated_at or "—"),
            )
        if snap.selected_runtime_id and tree.exists(snap.selected_runtime_id):
            tree.selection_set(snap.selected_runtime_id)
            tree.focus(snap.selected_runtime_id)
            tree.see(snap.selected_runtime_id)

    def _runtime_handoff_selected(self, _event: tk.Event | None = None) -> None:
        tree = self.runtime_handoff_tree
        if tree is None or not tree.selection():
            return
        try:
            self.runtime_handoff_controller.select(str(tree.selection()[0]))
        except Exception as exc:
            self.footer_hint.set(f"Runtime selection failed: {exc}")
            return
        self._refresh_runtime_handoff_summary()

    def _sync_execution_kind_presentation(self, row) -> None:
        search = bool(row is not None and row.is_search)
        title = self._runtime_handoff_title_label
        context = self._runtime_handoff_context_label
        open_queue = self._runtime_handoff_open_queue_button
        conditions = getattr(self, "_experiment_conditions_card", None)
        search_card = self._search_execution_card
        runtime_card = self._runtime_handoff_card
        try:
            if title is not None and title.winfo_exists():
                title.configure(text="UNIVERSE SEARCH HANDOFF" if search else "AUTHORIZED RUNTIME HANDOFF")
            if context is not None and context.winfo_exists():
                context.configure(text=(
                    "Explicit Search authorization • Observer Queue handoff is forbidden"
                    if search
                    else "Stage 6.5 authorization is explicit • Queue receives rows but is not started"
                ))
            if open_queue is not None and open_queue.winfo_exists():
                if search:
                    open_queue.pack_forget()
                elif not open_queue.winfo_manager():
                    open_queue.pack(side="right")
            if search:
                if conditions is not None and conditions.winfo_exists() and conditions.winfo_manager():
                    conditions.pack_forget()
                if search_card is not None and search_card.winfo_exists() and not search_card.winfo_manager():
                    if runtime_card is not None and runtime_card.winfo_exists():
                        search_card.pack(fill="x", pady=(0, 8), before=runtime_card)
                    else:
                        search_card.pack(fill="x", pady=(0, 8))
            else:
                if search_card is not None and search_card.winfo_exists() and search_card.winfo_manager():
                    search_card.pack_forget()
                if conditions is not None and conditions.winfo_exists() and not conditions.winfo_manager():
                    if runtime_card is not None and runtime_card.winfo_exists():
                        conditions.pack(fill="x", pady=(0, 8), before=runtime_card)
                    else:
                        conditions.pack(fill="x", pady=(0, 8))
        except tk.TclError:
            return

    def _refresh_runtime_handoff_summary(self) -> None:
        snap = self.runtime_handoff_controller.snapshot
        row = snap.selected
        button = self._runtime_handoff_button
        self._sync_execution_kind_presentation(row)
        if row is not None and row.is_search:
            refs = row.reference_rule_count
            budget = (
                f"population={row.population or '?'} • generations={row.generations or '?'} • "
                f"candidate slots={row.candidate_slots or '?'}"
            )
            self.search_execution_summary_var.set(
                f"Target regime: {row.target_regime or '—'}\n"
                f"Search job: {row.search_job_id or '—'}\n"
                f"Mode: cohort_target • Reference rules: {refs}\n"
                f"Budget: {budget}\n"
                "Mutation branch remains separate and is not launched by this Search handoff."
            )
        else:
            self.search_execution_summary_var.set("")

        if snap.error:
            self.runtime_handoff_summary_var.set(snap.error)
        elif row is None:
            self.runtime_handoff_summary_var.set(
                "No materialized runtime for the selected experiment. Approve & Materialize a VALID proposal first."
            )
        elif row.is_search and row.search_execution_started:
            self.runtime_handoff_summary_var.set(
                f"{row.runtime_id} • Universe Search execution exists"
                + (f" • PID {row.search_pid}" if row.search_pid else "")
                + " • open Search Launcher v2 to monitor progress/outcome. Observer Queue was not used."
            )
        elif row.can_start_search:
            self.runtime_handoff_summary_var.set(
                f"{row.runtime_id} • Search authorization VERIFIED • ready for ARCHON-managed Search Launcher. "
                "OL2 will open the launcher but will not start Universe Search itself."
            )
        elif row.can_authorize_search:
            self.runtime_handoff_summary_var.set(
                f"{row.runtime_id} • Search runtime is review-ready • explicit authorization is required before any process starts. "
                "Authorization itself does not execute Search."
            )
        elif row.is_search:
            self.runtime_handoff_summary_var.set(
                f"{row.runtime_id} • status={row.status} • unresolved={row.unresolved_count} • "
                "not eligible for Search launch. Observer Queue handoff remains forbidden."
            )
        elif row.can_queue:
            self.runtime_handoff_summary_var.set(
                f"{row.runtime_id} • {row.run_count} run(s) • authorization VERIFIED • ready to create a fresh execution copy. "
                "The scientific source runtime stays immutable; adding the copy does not start Queue or Observer."
            )
        elif row.can_authorize:
            self.runtime_handoff_summary_var.set(
                f"{row.runtime_id} • {row.run_count} run(s) • ready for explicit Stage 6.5 launch authorization. "
                "Authorization itself does not execute the experiment."
            )
        else:
            self.runtime_handoff_summary_var.set(
                f"{row.runtime_id} • status={row.status} • unresolved={row.unresolved_count} • "
                "not eligible for Queue handoff."
            )
        if button is not None:
            try:
                if button.winfo_exists():
                    if snap.busy:
                        button.configure(text="Working…", state="disabled")
                    elif row is not None and row.search_execution_started:
                        button.configure(text="Open Search Launcher", state="normal")
                    elif row is not None and row.can_start_search:
                        button.configure(text="Open Search Launcher", state="normal")
                    elif row is not None and row.can_authorize_search:
                        button.configure(text="Authorize Search Launch", state="normal")
                    elif row is not None and row.can_queue:
                        button.configure(text="Add Execution Copy to Queue", state="normal")
                    elif row is not None and row.can_authorize:
                        button.configure(text="Authorize & Add to Queue", state="normal")
                    else:
                        button.configure(text=("Search Unavailable" if row is not None and row.is_search else "Authorize & Add to Queue"), state="disabled")
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Explicit human action. Worker owns I/O; Tk owns confirmation/UI state.
    # ------------------------------------------------------------------
    def _authorize_and_queue_selected_runtime(self) -> None:
        snap = self.runtime_handoff_controller.snapshot
        row = snap.selected
        if row is None or snap.busy:
            return
        if row.is_search:
            self._authorize_or_start_selected_search(row)
            return
        if self.control_controller.process_active:
            self.footer_hint.set("Runtime handoff refused while Observer is active • stop the current run first")
            return
        if not (row.can_authorize or row.can_queue):
            self.footer_hint.set(f"Runtime {row.runtime_id} is not eligible for authorization/Queue handoff")
            return
        action = "Create a fresh execution copy from the already-authorized runtime" if row.can_queue else "Authorize this runtime and create an execution copy"
        if not messagebox.askyesno(
            "Authorize experiment runtime for Queue",
            f"{action} to ARCHON Queue?\n\nRuntime: {row.runtime_id}\nRuns: {row.run_count}\n\n"
            "Stage 6.5 authorization will be hash/receipt verified. A new execution-attempt experiment identity and per-run attempt output directories will be created while the source scientific runtime remains immutable. Queue rows will be created, but Queue will NOT start automatically and Observer will NOT be launched.",
            parent=self.root,
        ):
            return
        try:
            self.runtime_handoff_controller.begin("authorization", f"Preparing {row.runtime_id}…")
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self._refresh_runtime_handoff_summary()
        threading.Thread(
            target=self._runtime_handoff_worker,
            args=(row.runtime_id, row.can_authorize),
            daemon=True,
        ).start()

    def _authorize_or_start_selected_search(self, row) -> None:
        if self.control_controller.process_active:
            self.footer_hint.set("Search launch refused while Observer is active • stop the current Observer run first")
            return
        if row.can_authorize_search:
            if not messagebox.askyesno(
                "Authorize Universe Search launch",
                f"Authorize this cohort Search runtime?\n\nRuntime: {row.runtime_id}\n"
                f"Target: {row.target_regime or '—'}\nSearch job: {row.search_job_id or '—'}\n"
                f"Budget: {row.population or '?'} × {row.generations or '?'} = {row.candidate_slots or '?'} candidate slots\n\n"
                "This creates a VERIFIED Search authorization receipt only. No process will start and Observer Queue will not be used.",
                parent=self.root,
            ):
                return
            try:
                self.runtime_handoff_controller.begin("search-authorization", f"Authorizing {row.runtime_id}…")
            except Exception as exc:
                self.footer_hint.set(str(exc))
                return
            self._refresh_runtime_handoff_summary()
            threading.Thread(
                target=self._search_authorization_worker,
                args=(row.runtime_id,),
                daemon=True,
            ).start()
            return
        if row.can_start_search or row.search_execution_started:
            try:
                self.runtime_handoff_controller.begin(
                    "search-launcher-open", f"Opening Search Launcher for {row.runtime_id}…"
                )
            except Exception as exc:
                self.footer_hint.set(str(exc))
                return
            self._refresh_runtime_handoff_summary()
            threading.Thread(
                target=self._search_launcher_open_worker,
                args=(row.runtime_id,),
                daemon=True,
            ).start()
            return
        self.footer_hint.set(
            f"Runtime {row.runtime_id} is not eligible for Search authorization/managed launcher"
        )

    def _runtime_handoff_worker(self, runtime_id: str, needs_authorization: bool) -> None:
        try:
            auth_result: RuntimeAuthorizationResult | None = None
            if needs_authorization:
                auth_result = self.runtime_handoff_controller.port.authorize_runtime(
                    runtime_id,
                    requested_by=os.environ.get("USER") or os.environ.get("USERNAME") or "human",
                )
            preparation = self.runtime_handoff_controller.port.prepare_authorized_runtime(runtime_id)
        except Exception as exc:
            try:
                self.root.after(0, self._runtime_handoff_failed, exc)
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._runtime_handoff_ready, auth_result, preparation)
        except tk.TclError:
            pass

    def _search_authorization_worker(self, runtime_id: str) -> None:
        try:
            result = self.runtime_handoff_controller.port.authorize_runtime(
                runtime_id,
                requested_by=os.environ.get("USER") or os.environ.get("USERNAME") or "human",
            )
        except Exception as exc:
            try:
                self.root.after(0, self._runtime_handoff_failed, exc)
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._search_authorization_ready, result)
        except tk.TclError:
            pass

    def _search_authorization_ready(self, result: RuntimeAuthorizationResult) -> None:
        self.runtime_handoff_controller.complete_authorization(result)
        self._refresh_runtime_handoff()
        self.footer_hint.set(
            f"{result.runtime_id}: Search authorization VERIFIED • open Search Launcher v2 to execute/monitor"
        )

    def _search_launcher_open_worker(self, runtime_id: str) -> None:
        try:
            result = self.runtime_handoff_controller.port.open_authorized_search_launcher(
                runtime_id,
                requested_by=os.environ.get("USER") or os.environ.get("USERNAME") or "human",
            )
        except Exception as exc:
            try:
                self.root.after(0, self._runtime_handoff_failed, exc)
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._search_launcher_open_ready, result)
        except tk.TclError:
            pass

    def _search_launcher_open_ready(self, result: SearchLauncherOpenResult) -> None:
        self.runtime_handoff_controller.complete_search_launcher(result)
        self._refresh_runtime_handoff()
        self.footer_hint.set(result.message)

    def _search_start_worker(self, runtime_id: str) -> None:
        try:
            result = self.runtime_handoff_controller.port.start_authorized_search(
                runtime_id,
                requested_by=os.environ.get("USER") or os.environ.get("USERNAME") or "human",
            )
        except Exception as exc:
            try:
                self.root.after(0, self._runtime_handoff_failed, exc)
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._search_start_ready, result)
        except tk.TclError:
            pass

    def _search_start_ready(self, result: SearchDispatchResult) -> None:
        self.runtime_handoff_controller.complete_search(result)
        self._refresh_runtime_handoff()
        self.footer_hint.set(result.message)
        self.dialogs.info(
            "Universe Search started",
            f"Runtime: {result.runtime_id}\nDispatch: {result.dispatch_id}\nPID: {result.pid or '—'}\n"
            f"Log: {result.log_path or '—'}\n\nObserver Queue was not used.",
        )

    def _runtime_handoff_ready(
        self,
        auth_result: RuntimeAuthorizationResult | None,
        preparation: RuntimeQueuePreparation,
    ) -> None:
        if auth_result is not None:
            self.runtime_handoff_controller.complete_authorization(auth_result)
        # Fail closed before the first Queue write.  A materialized runtime row
        # maps to a unique output directory; an existing queue/history row means
        # this runtime was already handed off and should use Queue retry semantics.
        existing_outputs = {
            item.prepared.run_spec.output_dir
            for item in self.queue_controller.snapshot.items
        }
        duplicate = [
            prepared.run_spec.output_dir
            for prepared in preparation.prepared
            if prepared.run_spec.output_dir in existing_outputs
        ]
        if duplicate:
            self.runtime_handoff_controller.fail(
                "Runtime already has Queue rows. Open Queue and use its retry/recovery controls instead of duplicating experiment identities."
            )
            self._refresh_runtime_handoff()
            return
        try:
            for prepared in preparation.prepared:
                self.queue_controller.enqueue(prepared)
        except Exception as exc:
            self.runtime_handoff_controller.fail(exc)
            self.footer_hint.set(f"Queue handoff failed closed: {exc}")
            self._refresh_runtime_handoff()
            return
        self.runtime_handoff_controller.complete_queue(preparation)
        attempt_suffix = (
            f" • execution copy {preparation.execution_attempt_id}"
            if preparation.execution_attempt_id
            else ""
        )
        self.footer_hint.set(
            f"{preparation.runtime_id}: {len(preparation.prepared)} authorized run(s) added to Queue • Queue not started{attempt_suffix}"
        )
        self.store.select_route(ShellRoute.QUEUE)

    def _runtime_handoff_failed(self, exc: BaseException) -> None:
        self.runtime_handoff_controller.fail(exc)
        self.footer_hint.set(f"Runtime execution handoff stopped safely: {exc}")
        if self.snapshot.route is ShellRoute.EXPERIMENTS and self.experiment_workflow_stage == "execution":
            self._refresh_runtime_handoff()


__all__ = ["ObserverLauncher2FunctionsExperimentQueueShell"]
