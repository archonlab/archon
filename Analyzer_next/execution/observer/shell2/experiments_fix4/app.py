"""OL2-EXPERIMENTS-FIX4: implicit legacy seed fallback reconciliation."""
from __future__ import annotations

import threading
import tkinter as tk

from Analyzer_next.execution.observer.shell2.experiments_fix3.app import ObserverLauncher2ExperimentsFix3Shell


class ObserverLauncher2ExperimentsFix4Shell(ObserverLauncher2ExperimentsFix3Shell):
    """Keep FIX3 UX while making missing old seed mode explicit before runtime rebuild."""

    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — EXPERIMENTS-FIX4")
        self.footer_hint.set(
            "EXPERIMENTS-FIX4 • explicit legacy seed fallback repair • runtime reconciliation"
        )

    def _reconcile_existing_experiments(self) -> None:
        if self.experiment_pipeline_controller.snapshot.busy:
            return
        if self.control_controller.process_active:
            self.footer_hint.set("Experiment reconciliation refused while Observer is active")
            return
        if not self.dialogs.confirm(
            "Repair runtime policy & reconcile experiments",
            "Reconcile all committed experiment plans with canonical SQLite and runtime registries?\n\n"
            "Legacy runtime policies that either explicitly use CANONICAL_SEED or omit initial_state_mode while requesting multiple "
            "deterministic replicates will be migrated explicitly to RANDOM_SEED before runtime regeneration.\n\n"
            "Committed plan manifests are not edited. No proposal is approved, no launch authorization is issued, Queue is not started, "
            "and Observer is not run.",
        ):
            return
        try:
            self.experiment_pipeline_controller.begin(
                "EXISTING-EXPERIMENTS",
                "Repairing runtime policy and reconciling committed plans…",
            )
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return
        self.experiment_reconcile_status_var.set(
            "Repairing runtime policy and reconciling committed plans…"
        )
        self._build_route_content()
        threading.Thread(target=self._reconcile_existing_worker, daemon=True).start()


__all__ = ["ObserverLauncher2ExperimentsFix4Shell"]
