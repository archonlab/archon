"""OL2-EXPERIMENTS-FIX5: thread-safe Stage 6.5 authorization result handoff."""
from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
import threading
import tkinter as tk
from typing import Any

from Analyzer_next.execution.observer.shell2.experiments_fix4.app import (
    ObserverLauncher2ExperimentsFix4Shell,
)
from Analyzer_next.execution.observer.shell2.store import ShellRoute
from Analyzer_next.execution.observer.shell2.functions1g.model import (
    RuntimeAuthorizationResult,
    RuntimeQueuePreparation,
    SearchDispatchResult,
    SearchLauncherOpenResult,
)


@dataclass(frozen=True, slots=True)
class _RuntimeWorkerMessage:
    token: int
    kind: str
    authorization: RuntimeAuthorizationResult | None = None
    preparation: RuntimeQueuePreparation | None = None
    search_dispatch: SearchDispatchResult | None = None
    search_launcher: SearchLauncherOpenResult | None = None
    error_type: str | None = None
    error_text: str | None = None


class ObserverLauncher2ExperimentsFix5Shell(ObserverLauncher2ExperimentsFix4Shell):
    """Keep all Tk work on the main thread during experiment authorization."""

    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        self._runtime_worker_messages: Queue[_RuntimeWorkerMessage] = Queue()
        self._runtime_worker_token = 0
        self._runtime_worker_poll_id: str | None = None
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — EXPERIMENTS-FIX5")
        self.footer_hint.set(
            "EXPERIMENTS-FIX5 • thread-safe Stage 6.5 authorization → Queue handoff • no silent worker failure"
        )

    def _authorize_and_queue_selected_runtime(self) -> None:
        controller = getattr(self, "runtime_handoff_controller", None)
        if controller is None:
            self.footer_hint.set("Experiment runtime handoff is unavailable in this composition")
            return
        snap = controller.snapshot
        row = snap.selected
        if row is None or snap.busy:
            return
        # BRIDGE4.1: EXPERIMENTS-FIX5 is later in the final OL2 MRO than
        # FUNCTIONS1G.  Therefore the button created by FUNCTIONS1G resolves
        # this override at runtime.  Route Search rows explicitly instead of
        # applying Observer-only can_authorize/can_queue guards.
        if getattr(row, "is_search", False):
            self._authorize_or_start_selected_search_fix5(row)
            return
        if self.control_controller.process_active:
            self.footer_hint.set("Runtime handoff refused while Observer is active • stop the current run first")
            return
        if not (row.can_authorize or row.can_queue):
            self.footer_hint.set(f"Runtime {row.runtime_id} is not eligible for authorization/Queue handoff")
            return
        execution_horizon = None
        autosave_every = None
        execution_values = getattr(self, "_runtime_execution_values_for_handoff", None)
        if callable(execution_values):
            try:
                execution_horizon, autosave_every = execution_values(row)
            except ValueError as exc:
                self.footer_hint.set(str(exc))
                self.dialogs.error("Invalid execution settings", str(exc))
                return
        action = "Add the already-authorized runtime" if row.can_queue else "Authorize this runtime and add it"
        execution_text = ""
        confirmation_text = getattr(self, "_runtime_execution_confirmation_text", None)
        if callable(confirmation_text):
            execution_text = str(
                confirmation_text(row, execution_horizon, autosave_every) or ""
            )
        if not self.dialogs.confirm(
            "Authorize experiment runtime for Queue",
            f"{action} to ARCHON Queue?\n\nRuntime: {row.runtime_id}\nRuns: {row.run_count}\n"
            f"{execution_text}\n"
            "Stage 6.5 authorization will be hash/receipt verified. Queue rows will be created, but Queue will NOT "
            "start automatically and Observer will NOT be launched.",
        ):
            return
        try:
            controller.begin("authorization", f"Preparing {row.runtime_id}…")
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return

        self._runtime_worker_token += 1
        token = self._runtime_worker_token
        self.footer_hint.set(
            f"{row.runtime_id}: Stage 6.5 authorization in progress • Queue not started"
        )
        self._refresh_runtime_handoff_summary()
        self._schedule_runtime_worker_poll(token)
        threading.Thread(
            target=self._runtime_handoff_worker_fix5,
            args=(token, row.runtime_id, row.can_authorize, execution_horizon, autosave_every),
            daemon=True,
            name=f"ol2-exp-auth-{row.runtime_id}",
        ).start()

    def _authorize_or_start_selected_search_fix5(self, row) -> None:
        """Thread-safe BRIDGE4 Search authorization/start path for final OL2 MRO."""
        if self.control_controller.process_active:
            self.footer_hint.set(
                "Search launch refused while Observer is active • stop the current Observer run first"
            )
            return

        if row.can_authorize_search:
            title = "Authorize Universe Search launch"
            text = (
                f"Authorize this cohort Search runtime?\n\nRuntime: {row.runtime_id}\n"
                f"Target: {row.target_regime or '—'}\nSearch job: {row.search_job_id or '—'}\n"
                f"Budget: {row.population or '?'} × {row.generations or '?'} = "
                f"{row.candidate_slots or '?'} candidate slots\n\n"
                "This creates a VERIFIED Search authorization receipt only. No process will start and "
                "Observer Queue will not be used."
            )
            stage = "search-authorization"
            progress = f"Authorizing {row.runtime_id}…"
            worker_kind = "search-authorization"
        elif row.can_start_search or row.search_execution_started:
            title = "Open Universe Search Launcher"
            text = (
                f"Open Search Launcher v2 in ARCHON-managed mode?\n\nRuntime: {row.runtime_id}\n"
                f"Target: {row.target_regime or '—'}\nSearch job: {row.search_job_id or '—'}\n"
                f"Budget: {row.population or '?'} × {row.generations or '?'} = "
                f"{row.candidate_slots or '?'} candidate slots\n\n"
                "Observer Launcher will not start Universe Search itself. The managed Search Launcher owns "
                "start/monitor/pause/resume and keeps the authorized scientific contract read-only."
            )
            stage = "search-launcher-open"
            progress = f"Opening Search Launcher for {row.runtime_id}…"
            worker_kind = "search-open"
        else:
            self.footer_hint.set(
                f"Runtime {row.runtime_id} is not eligible for Search authorization/managed launcher"
            )
            return

        if not self.dialogs.confirm(title, text):
            return
        try:
            self.runtime_handoff_controller.begin(stage, progress)
        except Exception as exc:
            self.footer_hint.set(str(exc))
            return

        self._runtime_worker_token += 1
        token = self._runtime_worker_token
        self.footer_hint.set(
            f"{row.runtime_id}: "
            + (
                "Search authorization in progress • no process started"
                if worker_kind == "search-authorization"
                else "Opening managed Search Launcher • Search is not started by OL2"
            )
        )
        self._refresh_runtime_handoff_summary()
        self._schedule_runtime_worker_poll(token)
        threading.Thread(
            target=self._runtime_search_worker_fix41,
            args=(token, row.runtime_id, worker_kind),
            daemon=True,
            name=f"ol2-{worker_kind}-{row.runtime_id}",
        ).start()

    def _runtime_search_worker_fix41(
        self,
        token: int,
        runtime_id: str,
        worker_kind: str,
    ) -> None:
        """Worker performs Search file/process I/O only; Tk is updated by the poller."""
        try:
            if worker_kind == "search-authorization":
                result = self.runtime_handoff_controller.port.authorize_runtime(
                    runtime_id,
                    requested_by=self._runtime_requested_by(),
                )
                message = _RuntimeWorkerMessage(
                    token=token,
                    kind="search-authorization",
                    authorization=result,
                )
            elif worker_kind == "search-open":
                opened = self.runtime_handoff_controller.port.open_authorized_search_launcher(
                    runtime_id,
                    requested_by=self._runtime_requested_by(),
                )
                message = _RuntimeWorkerMessage(
                    token=token,
                    kind="search-open",
                    search_launcher=opened,
                )
            elif worker_kind == "search-start":
                # Compatibility path retained for BRIDGE4.1 regression tests and
                # non-UI callers. BRIDGE4.2 production UI no longer chooses it.
                dispatch = self.runtime_handoff_controller.port.start_authorized_search(
                    runtime_id,
                    requested_by=self._runtime_requested_by(),
                )
                message = _RuntimeWorkerMessage(
                    token=token,
                    kind="search-start",
                    search_dispatch=dispatch,
                )
            else:
                raise ValueError(f"unknown Search worker kind: {worker_kind}")
        except BaseException as exc:
            message = _RuntimeWorkerMessage(
                token=token,
                kind="error",
                error_type=type(exc).__name__,
                error_text=str(exc),
            )
        self._runtime_worker_messages.put(message)

    def _runtime_handoff_worker_fix5(
        self,
        token: int,
        runtime_id: str,
        needs_authorization: bool,
        execution_horizon: int | None = None,
        autosave_every: int | None = None,
    ) -> None:
        """Worker owns file/process I/O only; it never calls Tk methods."""
        try:
            auth_result: RuntimeAuthorizationResult | None = None
            if needs_authorization:
                auth_result = self.runtime_handoff_controller.port.authorize_runtime(
                    runtime_id,
                    requested_by=self._runtime_requested_by(),
                )
            if execution_horizon is None and autosave_every is None:
                preparation = self.runtime_handoff_controller.port.prepare_authorized_runtime(runtime_id)
            else:
                preparation = self.runtime_handoff_controller.port.prepare_authorized_runtime(
                    runtime_id,
                    execution_horizon=execution_horizon,
                    autosave_every=autosave_every,
                )
        except BaseException as exc:  # surface every worker-side failure to the main thread
            self._runtime_worker_messages.put(
                _RuntimeWorkerMessage(
                    token=token,
                    kind="error",
                    error_type=type(exc).__name__,
                    error_text=str(exc),
                )
            )
            return
        self._runtime_worker_messages.put(
            _RuntimeWorkerMessage(
                token=token,
                kind="success",
                authorization=auth_result,
                preparation=preparation,
            )
        )

    @staticmethod
    def _runtime_requested_by() -> str:
        import os

        return os.environ.get("USER") or os.environ.get("USERNAME") or "human"

    def _schedule_runtime_worker_poll(self, token: int) -> None:
        if self._runtime_worker_poll_id is not None:
            try:
                self.root.after_cancel(self._runtime_worker_poll_id)
            except tk.TclError:
                pass
        try:
            self._runtime_worker_poll_id = self.root.after(
                60,
                lambda t=token: self._poll_runtime_worker_results(t),
            )
        except tk.TclError:
            self._runtime_worker_poll_id = None

    def _poll_runtime_worker_results(self, token: int) -> None:
        """Main-thread bridge from worker results into controller/Tk state."""
        self._runtime_worker_poll_id = None
        handled = False
        while True:
            try:
                message = self._runtime_worker_messages.get_nowait()
            except Empty:
                break
            if message.token != token:
                continue
            handled = True
            if message.kind == "success":
                assert message.preparation is not None
                self._runtime_handoff_ready(message.authorization, message.preparation)
            elif message.kind == "search-authorization":
                assert message.authorization is not None
                self._search_authorization_ready(message.authorization)
            elif message.kind == "search-open":
                assert message.search_launcher is not None
                self._search_launcher_open_ready(message.search_launcher)
            elif message.kind == "search-start":
                assert message.search_dispatch is not None
                self._search_start_ready(message.search_dispatch)
            else:
                error = f"{message.error_type or 'RuntimeError'}: {message.error_text or 'unknown authorization failure'}"
                self.runtime_handoff_controller.fail(error)
                self.footer_hint.set(f"Runtime authorization/Queue handoff stopped safely: {error}")
                if self.snapshot.route is ShellRoute.EXPERIMENTS and self.experiment_workflow_stage == "execution":
                    self._refresh_runtime_handoff()
                self.dialogs.error(
                    "Experiment authorization stopped",
                    f"Stage 6.5 could not complete the runtime handoff.\n\n{error}\n\n"
                    "No Queue rows were started and Observer was not launched.",
                )
            break

        if handled:
            return
        snap = self.runtime_handoff_controller.snapshot
        if snap.busy and token == self._runtime_worker_token:
            self._schedule_runtime_worker_poll(token)

    def close(self) -> None:
        poll_id = self._runtime_worker_poll_id
        self._runtime_worker_poll_id = None
        if poll_id is not None:
            try:
                self.root.after_cancel(poll_id)
            except tk.TclError:
                pass
        super().close()


__all__ = ["ObserverLauncher2ExperimentsFix5Shell"]
