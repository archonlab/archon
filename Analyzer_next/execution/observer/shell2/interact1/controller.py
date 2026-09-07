"""Toolkit-independent interactive controls layered over OBSERVE1/CONTROL1."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from Analyzer_next.execution.observer.shell2.observe1.controller import ObserverPresentationController
from Analyzer_next.execution.observer.state import (
    ControlCapabilities,
    RunEvent,
    RunEventType,
    RunState,
    RunTransitionContext,
    reduce_run,
)

CONTROL_PREFIX = "[ol2-control] "
CONTROL_PROTOCOL = "archon.ol2.legacy-control.v1"
INTERACTIVE_CAPABILITIES = ControlCapabilities(
    supports_stop=True,
    supports_pause=True,
    supports_resume=True,
)


@dataclass(frozen=True, slots=True)
class ControlAck:
    sequence: int
    command: str
    status: str
    tick: int
    running: bool
    speed: int
    error: str | None = None


def decode_control_ack(text: str) -> ControlAck:
    stripped = text.strip()
    if not stripped.startswith(CONTROL_PREFIX):
        raise ValueError("missing control acknowledgement prefix")
    payload = json.loads(stripped[len(CONTROL_PREFIX):])
    if payload.get("protocol") != CONTROL_PROTOCOL:
        raise ValueError("unsupported control acknowledgement protocol")
    sequence = int(payload.get("sequence") or 0)
    if sequence < 1:
        raise ValueError("invalid control acknowledgement sequence")
    status = str(payload.get("status") or "")
    if status not in {"ok", "error"}:
        raise ValueError("invalid control acknowledgement status")
    return ControlAck(
        sequence=sequence,
        command=str(payload.get("command") or ""),
        status=status,
        tick=int(payload.get("tick") or 0),
        running=bool(payload.get("running", False)),
        speed=int(payload.get("speed") or 0),
        error=str(payload.get("error")) if payload.get("error") else None,
    )


def _context(*, process_identity_matches: bool = True) -> RunTransitionContext:
    return RunTransitionContext(
        world_and_configuration_present=True,
        scientific_and_authorization_checks_pass=True,
        runspec_committed=True,
        launcher_ready=True,
        queue_head=True,
        no_active_process=True,
        process_identity_matches=process_identity_matches,
        stop_authorized=True,
        capabilities=INTERACTIVE_CAPABILITIES,
    )


class ObserverInteractiveController(ObserverPresentationController):
    """Add acknowledged pause/resume/speed/save without owning OS primitives."""

    SPEED_LEVELS = (1, 2, 10, 100, 1000)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._control_sequence = 0
        self._pending_controls: dict[int, str] = {}
        self._last_ack: ControlAck | None = None
        self._speed = 2

    @property
    def speed(self) -> int:
        with self._lock:
            return self._speed

    @property
    def last_control_ack(self) -> ControlAck | None:
        with self._lock:
            return self._last_ack

    def start(self, prepared, *, retry_of: str | None = None):
        command = tuple(str(item) for item in prepared.command)
        try:
            index = command.index("--speed")
            speed = int(command[index + 1])
        except (ValueError, IndexError):
            speed = 2
        with self._lock:
            self._speed = max(1, speed)
            self._pending_controls.clear()
            self._last_ack = None
        return super().start(prepared, retry_of=retry_of)

    def _send(self, command: str, *, value: int | None = None) -> int:
        with self._lock:
            process = self._process
            if process is None:
                raise RuntimeError("Observer process identity is missing")
            sender = getattr(self.process_runner, "send_control", None)
            if sender is None:
                raise RuntimeError("active process adapter has no interactive control port")
            self._control_sequence += 1
            sequence = self._control_sequence
            self._pending_controls[sequence] = command
            try:
                sender(process, sequence=sequence, command=command, value=value)
            except Exception:
                self._pending_controls.pop(sequence, None)
                raise
            return sequence

    def pause(self):
        with self._lock:
            run = self.snapshot.run
            if run is None or run.state is not RunState.RUNNING:
                raise RuntimeError("Observer can pause only from RUNNING")
            run = reduce_run(run, RunEvent(RunEventType.PAUSE), _context())
            self._publish(run=run)
        try:
            self._send("pause")
        except Exception as exc:
            with self._lock:
                run = self.snapshot.run
                if run is not None and run.state is RunState.PAUSING:
                    run = reduce_run(
                        run,
                        RunEvent(RunEventType.CONTROL_FAILED, error=f"{type(exc).__name__}: {exc}"),
                        _context(),
                    )
                    self._publish(run=run)
                    process = self._process
                else:
                    process = None
            if process is not None:
                try:
                    self.process_runner.terminate(process)
                except Exception:
                    pass
            raise
        self._output.put("[Pause requested] awaiting legacy runtime acknowledgement…\n")
        return self.snapshot

    def resume(self):
        with self._lock:
            run = self.snapshot.run
            if run is None or run.state is not RunState.PAUSED:
                raise RuntimeError("Observer can resume only from PAUSED")
            run = reduce_run(run, RunEvent(RunEventType.RESUME), _context())
            self._publish(run=run)
        try:
            self._send("resume")
        except Exception as exc:
            with self._lock:
                run = self.snapshot.run
                if run is not None and run.state is RunState.RESUMING:
                    run = reduce_run(
                        run,
                        RunEvent(RunEventType.CONTROL_FAILED, error=f"{type(exc).__name__}: {exc}"),
                        _context(),
                    )
                    self._publish(run=run)
                    process = self._process
                else:
                    process = None
            if process is not None:
                try:
                    self.process_runner.terminate(process)
                except Exception:
                    pass
            raise
        self._output.put("[Resume requested] awaiting legacy runtime acknowledgement…\n")
        return self.snapshot

    def set_speed(self, speed: int) -> int:
        speed = int(speed)
        if speed not in self.SPEED_LEVELS:
            raise ValueError(f"unsupported speed level: {speed}")
        self._send("speed", value=speed)
        return speed

    def save_checkpoint(self) -> int:
        return self._send("save")

    def _capture_output(self, text: str) -> None:
        if not text.lstrip().startswith(CONTROL_PREFIX):
            super()._capture_output(text)
            return
        try:
            ack = decode_control_ack(text)
        except Exception as exc:
            super()._capture_output(f"[INTERACT1 control protocol error] {exc}\n")
            return
        with self._lock:
            expected = self._pending_controls.pop(ack.sequence, None)
            if expected is None or expected != ack.command:
                super()._capture_output(
                    f"[INTERACT1 control guard] ignored unexpected acknowledgement seq={ack.sequence} command={ack.command}\n"
                )
                return
            self._last_ack = ack
            run = self.snapshot.run
            if ack.status == "error":
                if run is not None and ack.command in {"pause", "resume"} and run.state in {RunState.PAUSING, RunState.RESUMING}:
                    run = reduce_run(
                        run,
                        RunEvent(RunEventType.CONTROL_FAILED, error=ack.error or f"{ack.command} failed"),
                        _context(),
                    )
                    self._publish(run=run)
                    process = self._process
                else:
                    process = None
                super()._capture_output(
                    f"[INTERACT1 control failed] {ack.command}: {ack.error or 'unknown error'}\n"
                )
                if process is not None:
                    try:
                        self.process_runner.terminate(process)
                    except Exception:
                        pass
                return
            if run is not None and ack.command == "pause" and run.state is RunState.PAUSING:
                run = reduce_run(run, RunEvent(RunEventType.PAUSE_ACK), _context())
                self._publish(run=run)
            elif run is not None and ack.command == "resume" and run.state is RunState.RESUMING:
                run = reduce_run(run, RunEvent(RunEventType.RESUME_ACK), _context())
                self._publish(run=run)
            elif ack.command == "speed" and ack.speed > 0:
                self._speed = ack.speed
        self._output.put(
            f"[Interactive control] {ack.command} OK at tick {ack.tick}; speed=x{ack.speed}\n"
        )


__all__ = [
    "CONTROL_PREFIX",
    "CONTROL_PROTOCOL",
    "ControlAck",
    "ObserverInteractiveController",
    "decode_control_ack",
]
