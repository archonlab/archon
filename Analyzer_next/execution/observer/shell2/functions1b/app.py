"""OL2-FUNCTIONS1B: explicit Save & Stop / Stop without saving dialog."""
from __future__ import annotations

import tkinter as tk

from Analyzer_next.execution.observer.shell2.functions1a.app import (
    ObserverLauncher2FunctionsWorldsShell,
)

from .controller import ObserverStopWorkflowController


class ObserverLauncher2FunctionsStopShell(ObserverLauncher2FunctionsWorldsShell):
    """Add an explicit stop decision without changing scientific/runtime ownership."""

    STOP_SAVE_POLL_MS = 60

    def __init__(self, *args, **kwargs) -> None:
        control = kwargs.get("control_controller")
        if control is None and len(args) >= 5:
            control = args[4]
        if not isinstance(control, ObserverStopWorkflowController):
            raise TypeError("FUNCTIONS1B requires ObserverStopWorkflowController")
        self.stop_workflow_controller = control
        self._save_stop_after: str | None = None
        self._stop_dialog: tk.Toplevel | None = None
        super().__init__(*args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — FUNCTIONS1B")
        self.footer_hint.set(
            "FUNCTIONS1B explicit stop workflow • Save & Stop waits for checkpoint ACK"
        )

    # ------------------------------------------------------------------
    # Stop workflow
    # ------------------------------------------------------------------
    def _stop_observer(self) -> None:
        if not self.stop_workflow_controller.process_active:
            # Preserve CONTROL1's existing fail-closed status message for an
            # idle process; there is no destructive action to confirm.
            return super()._stop_observer()
        status = self.stop_workflow_controller.save_stop_status
        if status.pending:
            self.footer_hint.set("Save & Stop already waiting for checkpoint acknowledgement")
            self._refresh_stop_workflow_buttons()
            return
        choice = self._ask_stop_choice()
        if choice == "cancel":
            self.footer_hint.set("Stop cancelled • Observer continues running")
            return
        if choice == "stop_without_saving":
            self._perform_stop_without_prompt()
            return
        if choice != "save_and_stop":
            return
        try:
            sequence = self.stop_workflow_controller.request_save_and_stop()
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Save & Stop refused: {exc}")
            self._refresh_stop_workflow_buttons()
            return
        self.footer_hint.set(
            f"Saving checkpoint before stop • awaiting ACK seq={sequence}"
        )
        self._refresh_stop_workflow_buttons()
        self._schedule_save_stop_poll()

    def _perform_stop_without_prompt(self) -> None:
        try:
            snapshot = self.stop_workflow_controller.stop_without_saving()
        except (RuntimeError, ValueError) as exc:
            self.footer_hint.set(f"Observer stop refused: {exc}")
            self._refresh_control_status()
            return
        self.control_store.sync_control(
            snapshot,
            elapsed_seconds=self.stop_workflow_controller.elapsed_seconds,
        )
        self.footer_hint.set("Stop without saving requested for Observer process group")
        self._refresh_control_status()

    def _schedule_save_stop_poll(self) -> None:
        if self._save_stop_after is not None:
            return
        try:
            self._save_stop_after = self.root.after(
                self.STOP_SAVE_POLL_MS, self._poll_save_stop_workflow
            )
        except tk.TclError:
            self._save_stop_after = None

    def _poll_save_stop_workflow(self) -> None:
        self._save_stop_after = None
        status = self.stop_workflow_controller.save_stop_status
        if status.error:
            self.footer_hint.set(
                "Save & Stop aborted: checkpoint was not confirmed • Observer remains running • "
                + status.error
            )
            self._refresh_stop_workflow_buttons()
            return
        if status.pending and status.checkpoint_acknowledged:
            try:
                snapshot = self.stop_workflow_controller.complete_save_and_stop_if_ready()
            except (RuntimeError, ValueError) as exc:
                self.footer_hint.set(f"Save succeeded but stop failed: {exc}")
                self._refresh_control_status()
                return
            if snapshot is not None:
                self.control_store.sync_control(
                    snapshot,
                    elapsed_seconds=self.stop_workflow_controller.elapsed_seconds,
                )
                self.footer_hint.set("Checkpoint saved • stopping Observer")
                self._refresh_control_status()
                return
        if status.pending:
            self._refresh_stop_workflow_buttons()
            self._schedule_save_stop_poll()

    def _refresh_control_buttons(self) -> None:
        super()._refresh_control_buttons()
        self._refresh_stop_workflow_buttons()

    def _refresh_stop_workflow_buttons(self) -> None:
        pending = self.stop_workflow_controller.save_stop_status.pending
        for name in ("stop_button", "control_stop_config_button"):
            widget = getattr(self, name, None)
            if widget is None:
                continue
            try:
                if not widget.winfo_exists():
                    continue
                if pending:
                    widget.configure(text="Saving…", state="disabled")
                else:
                    widget.configure(text="Stop")
            except tk.TclError:
                continue

    # ------------------------------------------------------------------
    # Themed modal.  No visible scrollbar/foreign native dialog styling.
    # ------------------------------------------------------------------
    def _ask_stop_choice(self) -> str:
        if self._stop_dialog is not None:
            try:
                if self._stop_dialog.winfo_exists():
                    self._stop_dialog.lift()
                    return "cancel"
            except tk.TclError:
                self._stop_dialog = None

        result = {"value": "cancel"}
        dialog = tk.Toplevel(self.root)
        self._stop_dialog = dialog
        dialog.title("Stop Observer")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish("cancel"))

        body = self._frame(dialog, "surface.card")
        body.pack(fill="both", expand=True)
        self._label(
            body,
            "Stop current Observer run?",
            surface="surface.card",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 6))
        explanation = self._label(
            body,
            "Save & Stop writes a manual checkpoint and waits for the legacy runtime to confirm it before termination.",
            surface="surface.card",
            foreground="text.secondary",
            font=("TkDefaultFont", 9),
        )
        explanation.configure(wraplength=520, justify="left")
        explanation.pack(anchor="w", padx=18, pady=(0, 14))

        actions = self._frame(body, "surface.card")
        actions.pack(fill="x", padx=14, pady=(0, 14))

        def finish(value: str) -> None:
            result["value"] = value
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            try:
                dialog.destroy()
            except tk.TclError:
                pass

        self._button(actions, "Cancel", lambda: finish("cancel")).pack(side="right", padx=4)
        self._button(
            actions,
            "Stop without saving",
            lambda: finish("stop_without_saving"),
            kind="danger",
        ).pack(side="right", padx=4)
        self._button(
            actions,
            "Save & Stop",
            lambda: finish("save_and_stop"),
            kind="primary",
        ).pack(side="right", padx=4)

        # New semantic widgets were created after the last global theme pass.
        self._apply_theme()
        dialog.update_idletasks()
        try:
            x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_reqwidth()) // 2)
            y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_reqheight()) // 3)
            dialog.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        try:
            dialog.grab_set()
            dialog.focus_force()
            self.root.wait_window(dialog)
        finally:
            self._stop_dialog = None
        return result["value"]

    def close(self) -> None:
        if self._save_stop_after is not None:
            try:
                self.root.after_cancel(self._save_stop_after)
            except tk.TclError:
                pass
            self._save_stop_after = None
        super().close()


__all__ = ["ObserverLauncher2FunctionsStopShell"]
