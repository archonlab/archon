"""OL2-EXPERIMENTS-FIX8: visible, history-preserving experiment Queue refresh.

FIX7 intentionally regenerates experiment PreparedConfiguration commands with an
explicit canonical ``--telemetry-db`` while retaining the same materialized row
``output_dir``.  Queue rows created before FIX7 therefore collide by output
identity with the corrected rows.  FUNCTIONS1G used to fail this duplicate guard
silently after the authorization worker completed, producing the visible
``Working… -> button enabled`` no-op.

FIX8 keeps immutable/durable terminal history, removes only stale terminal rows
from the active Queue view when their reviewed command has changed, and then
queues the freshly prepared authorized rows.  A WAITING/RUNNING collision, or an
identical terminal row, remains fail-closed and is surfaced to the user.
"""
from __future__ import annotations

import tkinter as tk

from Analyzer_next.execution.observer.shell2.experiments_fix7.app import (
    ObserverLauncher2ExperimentsFix7Shell,
)
from Analyzer_next.execution.observer.shell2.functions1g.model import (
    RuntimeAuthorizationResult,
    RuntimeQueuePreparation,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute


class ObserverLauncher2ExperimentsFix8Shell(ObserverLauncher2ExperimentsFix7Shell):
    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — EXPERIMENTS-FIX8")
        self.footer_hint.set(
            "EXPERIMENTS-FIX8 • corrected runtime rows replace stale terminal active-view rows • durable history retained"
        )

    def _runtime_handoff_ready(
        self,
        auth_result: RuntimeAuthorizationResult | None,
        preparation: RuntimeQueuePreparation,
    ) -> None:
        if auth_result is not None:
            self.runtime_handoff_controller.complete_authorization(auth_result)

        current_items = tuple(self.queue_controller.snapshot.items)
        prepared_by_output = {
            prepared.run_spec.output_dir: prepared
            for prepared in preparation.prepared
        }
        collisions = [
            item for item in current_items
            if item.prepared.run_spec.output_dir in prepared_by_output
        ]

        active_collisions = [item for item in collisions if not item.status.terminal]
        if active_collisions:
            queue_ids = ", ".join(item.queue_id for item in active_collisions)
            message = (
                "This experiment already has active Queue rows "
                f"({queue_ids}). Open Queue and cancel/finish them before regenerating runtime rows."
            )
            self.runtime_handoff_controller.fail(message)
            self.footer_hint.set(message)
            self._refresh_runtime_handoff()
            self.dialogs.error(
                "Experiment Queue handoff blocked",
                message + "\n\nNo Queue rows were changed and Observer was not started.",
            )
            return

        identical_terminal = []
        stale_terminal = []
        for item in collisions:
            fresh = prepared_by_output[item.prepared.run_spec.output_dir]
            if item.prepared.review_hash == fresh.review_hash:
                identical_terminal.append(item)
            else:
                stale_terminal.append(item)

        if identical_terminal:
            queue_ids = ", ".join(item.queue_id for item in identical_terminal)
            message = (
                "The same reviewed experiment rows already exist as terminal Queue history "
                f"in the active view ({queue_ids}). Use Queue retry/recovery controls instead of duplicating them."
            )
            self.runtime_handoff_controller.fail(message)
            self.footer_hint.set(message)
            self._refresh_runtime_handoff()
            self.dialogs.error(
                "Experiment already queued",
                message + "\n\nNo duplicate Queue rows were created.",
            )
            return

        # A terminal row with the same output identity but a different review
        # hash is an obsolete active-view projection (notably pre-FIX7 commands
        # missing canonical --telemetry-db).  QUEUE2 records terminal history
        # durably before remove_terminal(), so removing it here does not erase
        # execution evidence/history.
        if stale_terminal:
            remover = getattr(self.queue_controller, "remove_terminal", None)
            if not callable(remover):
                message = (
                    "Stale terminal experiment Queue rows need active-view cleanup, "
                    "but this Queue controller does not support history-preserving removal."
                )
                self.runtime_handoff_controller.fail(message)
                self.footer_hint.set(message)
                self._refresh_runtime_handoff()
                self.dialogs.error("Experiment Queue cleanup unavailable", message)
                return
            try:
                for item in stale_terminal:
                    remover(item.queue_id)
            except Exception as exc:
                message = f"Could not archive stale terminal Queue rows: {type(exc).__name__}: {exc}"
                self.runtime_handoff_controller.fail(message)
                self.footer_hint.set(message)
                self._refresh_runtime_handoff()
                self.dialogs.error("Experiment Queue cleanup failed", message)
                return

        try:
            for prepared in preparation.prepared:
                self.queue_controller.enqueue(prepared)
        except Exception as exc:
            self.runtime_handoff_controller.fail(exc)
            message = f"Queue handoff failed closed: {type(exc).__name__}: {exc}"
            self.footer_hint.set(message)
            self._refresh_runtime_handoff()
            self.dialogs.error("Experiment Queue handoff failed", message)
            return

        self.runtime_handoff_controller.complete_queue(preparation)
        archived = len(stale_terminal)
        suffix = f" • archived {archived} stale terminal row(s) from active view" if archived else ""
        self.footer_hint.set(
            f"{preparation.runtime_id}: {len(preparation.prepared)} authorized run(s) added to Queue • Queue not started{suffix}"
        )
        self.store.select_route(ShellRoute.QUEUE)


__all__ = ["ObserverLauncher2ExperimentsFix8Shell"]
