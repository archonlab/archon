"""OL2-DIALOGS1: launcher-themed modals for the current candidate workflows."""
from __future__ import annotations

import threading
import tkinter as tk

from Analyzer_next.execution.observer.shell2.save_policy1.app import ObserverLauncher2SavePolicyShell
from Analyzer_next.execution.observer.shell2.save_policy1.service import with_autosave_ticks
from Analyzer_next.execution.observer.shell2.store import ShellRoute

from .modal import ThemedDialogPresenter


class ObserverLauncher2DialogsShell(ObserverLauncher2SavePolicyShell):
    """Replace OS message boxes in live OL2 workflows without changing their decisions."""

    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        super().__init__(root, *args, **kwargs)
        self.dialogs = ThemedDialogPresenter(root, lambda: self.snapshot.resolved_theme)
        self.root.title("ARCHON Observer Launcher 2.0 — DIALOGS1")
        self.footer_hint.set(
            "DIALOGS1 • launcher-themed light/dark modals • English Yes / No • Enter confirm • Esc cancel"
        )

    # ------------------------------------------------------------------
    # Mutations: preserve PERF1/SAVE-POLICY1 hot paths and only replace UI.
    # ------------------------------------------------------------------
    def _create_mutation_batch(self) -> None:
        try:
            self._sync_mutation_draft_from_ui()
            preview_snap = self.mutation_controller.snapshot
            if preview_snap.preview is None:
                preview_snap = self.mutation_controller.preview()
        except (ValueError, OSError) as exc:
            self.dialogs.error("Mutation cannot be prepared", str(exc))
            return
        preview = preview_snap.preview
        assert preview is not None
        if preview.baseline_status != "resolved":
            self.dialogs.error(
                "Canonical baseline required",
                "This rule has no resolved canonical baseline/passport. Observe and save the canonical rule first.",
            )
            return
        draft = self.mutation_controller.snapshot.draft
        if not self.dialogs.confirm(
            "Create mutation batch",
            f"Create {draft.count} isolated mutation run(s) for Rule {draft.source_rule_id:05d}?\n\n"
            f"Strategy: {draft.strategy.value}\nStrength: {draft.intensity:.2f}\n"
            f"Preview changes: {preview.change_count}\n\nCanonical Atlas files will remain read-only.",
        ):
            return
        try:
            self.mutation_controller.create_batch()
        except (ValueError, OSError, FileExistsError) as exc:
            self.dialogs.error("Mutation batch failed", str(exc))
            return
        self.footer_hint.set(f"Created {draft.count} isolated mutation run(s)")
        self._build_route_content()

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
            self.dialogs.error("Mutation launch refused", str(exc))
            return
        record = self.mutation_controller.snapshot.selected_record
        assert record is not None
        periodic = "Off" if autosave_ticks == 0 else f"Every {autosave_ticks:,} ticks"
        if not self.dialogs.confirm(
            "Run mutation",
            f"Launch {record.mutation_id}?\n\nParent: Rule {record.parent_rule_id:05d}\n"
            f"Changes: {record.change_count}\nAutosave: {periodic}\n"
            "Final save: Save & Stop (manual-horizon mutation)\n\n"
            "This is an isolated mutation run. Canonical Atlas files are not modified.",
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
    # Experiments: presentation-only replacement for existing human gates.
    # Scientific/governance pipeline semantics remain inherited unchanged.
    # ------------------------------------------------------------------
    def _record_preferred_resolution(self) -> None:
        row = self.proposal_controller.snapshot.selected
        if row is None or row.ui_status != "NEEDS REVIEW":
            return
        guidance = row.preferred_resolution or "Use the Research Director preferred resolution."
        if not self.dialogs.confirm(
            "Record preferred resolution",
            f"{row.title}\n\nDirector guidance:\n{guidance}\n\n"
            "Record this as NEEDS_REVISION?\n\nNo experiment will be launched.",
        ):
            return
        self._start_review_decision(
            row.proposal_id,
            "NEEDS_REVISION",
            f"Observer Launcher 2.0 recorded Director preferred resolution: {guidance}",
        )

    def _defer_selected_proposal(self) -> None:
        row = self.proposal_controller.snapshot.selected
        if row is None or row.ui_status != "BLOCKED":
            return
        if not self.dialogs.confirm(
            "Defer blocked proposal",
            f"{row.title}\n\nThis proposal is BLOCKED. Record it as DEFERRED?\n\nNo experiment will be launched.",
        ):
            return
        self._start_review_decision(
            row.proposal_id,
            "DEFERRED",
            "Deferred in Observer Launcher 2.0 until Research Director prerequisites are resolved.",
        )

    def _approve_prepared_and_materialize(self) -> None:
        prepared = self.proposal_controller.snapshot.prepared
        row = self.proposal_controller.snapshot.selected
        if prepared is None or row is None or prepared.proposal_id != row.proposal_id:
            self.footer_hint.set("Prepare the selected VALID proposal first")
            return
        if not row.can_prepare:
            self.footer_hint.set(f"Proposal {row.proposal_id} is no longer VALID")
            return
        if self.experiment_pipeline_controller.snapshot.busy:
            return
        if not self.dialogs.confirm(
            "Approve & materialize experiment",
            f"Approve this VALID Research Director proposal?\n\n{prepared.title}\n\n"
            f"Why:\n{prepared.rationale}\n\nDone when:\n{prepared.done_when}\n\n"
            "ARCHON will commit the audited human decision, apply the verified governance patch, "
            "build/commit the experiment plan, register canonical experiment identities, and materialize runtime packages.\n\n"
            "Launch authorization and Observer execution remain separate.",
        ):
            return
        try:
            self.experiment_pipeline_controller.begin(
                prepared.proposal_id,
                "Starting audited Research Director → experiment materialization…",
            )
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self.pipeline_status_var.set("Starting audited materialization…")
        self._build_route_content()
        threading.Thread(
            target=self._materialize_worker,
            args=(prepared.proposal_id, prepared.title),
            daemon=True,
        ).start()

    # FUNCTIONS1G is optional in the cutover contract, but present in the
    # current baseline.  Keeping this override here means its confirmation is
    # themed when installed and is simply unreachable when it is absent.
    def _authorize_and_queue_selected_runtime(self) -> None:
        controller = getattr(self, "runtime_handoff_controller", None)
        if controller is None:
            return
        snap = controller.snapshot
        row = snap.selected
        if row is None or snap.busy:
            return
        if self.control_controller.process_active:
            self.footer_hint.set("Runtime handoff refused while Observer is active • stop the current run first")
            return
        if not (row.can_authorize or row.can_queue):
            self.footer_hint.set(f"Runtime {row.runtime_id} is not eligible for authorization/Queue handoff")
            return
        action = "Add the already-authorized runtime" if row.can_queue else "Authorize this runtime and add it"
        if not self.dialogs.confirm(
            "Authorize experiment runtime for Queue",
            f"{action} to ARCHON Queue?\n\nRuntime: {row.runtime_id}\nRuns: {row.run_count}\n\n"
            "Stage 6.5 authorization will be hash/receipt verified. Queue rows will be created, but Queue will NOT "
            "start automatically and Observer will NOT be launched.",
        ):
            return
        try:
            controller.begin("authorization", f"Preparing {row.runtime_id}…")
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self._refresh_runtime_handoff_summary()
        threading.Thread(
            target=self._runtime_handoff_worker,
            args=(row.runtime_id, row.can_authorize),
            daemon=True,
        ).start()


__all__ = ["ObserverLauncher2DialogsShell"]
