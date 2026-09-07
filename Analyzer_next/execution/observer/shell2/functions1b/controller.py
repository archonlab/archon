"""Toolkit-independent Save & Stop orchestration for OL2-FUNCTIONS1B."""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from Analyzer_next.execution.observer.shell2.interact1.controller import (
    CONTROL_PREFIX,
    ObserverInteractiveController,
    decode_control_ack,
)


@dataclass(frozen=True, slots=True)
class SaveStopStatus:
    pending: bool = False
    checkpoint_sequence: int | None = None
    checkpoint_acknowledged: bool = False
    error: str | None = None


class ObserverStopWorkflowController(ObserverInteractiveController):
    """Gate process termination behind an acknowledged manual checkpoint.

    CONTROL1 still owns process start/stop and the process adapter still owns OS
    primitives.  This layer only coordinates the user's explicit Save & Stop
    intent over INTERACT1's existing control channel.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._save_stop_lock = RLock()
        self._save_stop_status = SaveStopStatus()

    @property
    def save_stop_status(self) -> SaveStopStatus:
        with self._save_stop_lock:
            return self._save_stop_status

    def start(self, prepared, *, retry_of: str | None = None):
        with self._save_stop_lock:
            self._save_stop_status = SaveStopStatus()
        return super().start(prepared, retry_of=retry_of)

    def request_save_and_stop(self) -> int:
        if not self.process_active:
            raise RuntimeError("Observer process identity is missing")
        with self._save_stop_lock:
            if self._save_stop_status.pending:
                raise RuntimeError("Save & Stop is already waiting for checkpoint acknowledgement")
            self._save_stop_status = SaveStopStatus(pending=True)
            # Keep this lock until the expected sequence is published.  The
            # child can ACK very quickly; _capture_output must not observe a
            # transient pending state with no sequence and discard that ACK.
            try:
                sequence = self.save_checkpoint()
            except Exception as exc:
                self._save_stop_status = SaveStopStatus(error=f"{type(exc).__name__}: {exc}")
                raise
            self._save_stop_status = SaveStopStatus(
                pending=True,
                checkpoint_sequence=sequence,
            )
        self._output.put(
            f"[Save & Stop] checkpoint requested seq={sequence}; process remains running until ACK\n"
        )
        return sequence

    def clear_save_stop_error(self) -> None:
        with self._save_stop_lock:
            status = self._save_stop_status
            if status.pending:
                return
            self._save_stop_status = SaveStopStatus()

    def complete_save_and_stop_if_ready(self):
        """Stop only after the matching save ACK has been observed.

        This method is intentionally called by the GUI/event-loop thread.  ACK
        parsing happens on the process output thread, while CONTROL1 termination
        stays on the normal controller call path.
        """
        with self._save_stop_lock:
            status = self._save_stop_status
            if not status.pending or not status.checkpoint_acknowledged:
                return None
            self._save_stop_status = SaveStopStatus()
        try:
            snapshot = self.stop()
        except Exception as exc:
            with self._save_stop_lock:
                self._save_stop_status = SaveStopStatus(error=f"{type(exc).__name__}: {exc}")
            raise
        self._output.put("[Save & Stop] checkpoint acknowledged; stop requested\n")
        return snapshot

    def stop_without_saving(self):
        with self._save_stop_lock:
            if self._save_stop_status.pending:
                raise RuntimeError("Cannot bypass a Save & Stop checkpoint already in flight")
            self._save_stop_status = SaveStopStatus()
        return self.stop()

    def _capture_output(self, text: str) -> None:
        ack = None
        if text.lstrip().startswith(CONTROL_PREFIX):
            try:
                ack = decode_control_ack(text)
            except Exception:
                ack = None
        super()._capture_output(text)
        if ack is None or ack.command != "save":
            return
        with self._save_stop_lock:
            status = self._save_stop_status
            if not status.pending or status.checkpoint_sequence != ack.sequence:
                return
            if ack.status == "ok":
                self._save_stop_status = SaveStopStatus(
                    pending=True,
                    checkpoint_sequence=ack.sequence,
                    checkpoint_acknowledged=True,
                )
            else:
                self._save_stop_status = SaveStopStatus(
                    pending=False,
                    checkpoint_sequence=ack.sequence,
                    checkpoint_acknowledged=False,
                    error=ack.error or "legacy checkpoint failed",
                )


__all__ = ["ObserverStopWorkflowController", "SaveStopStatus"]
