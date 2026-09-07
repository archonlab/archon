"""Interactive Observer process adapter for OL2-INTERACT1.

OS ownership remains delegated to :class:`SubprocessRunner`; this adapter only
selects the interactive headless bridge and exposes a bounded JSONL control
channel over the child stdin pipe.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Sequence

from .presentation_process_runner import LEGACY_OBSERVER_BASENAME
from .process_runner import SubprocessRunner

INTERACTIVE_BRIDGE_MODULE = "Analyzer_next.adapters.observer.legacy_interactive_bridge"
CONTROL_PROTOCOL = "archon.ol2.legacy-control.v1"
_ALLOWED_COMMANDS = frozenset({"pause", "resume", "speed", "save"})


class InteractivePresentationProcessRunner:
    """Preserve CONTROL1 process ownership while enabling explicit controls."""

    def __init__(self, delegate: SubprocessRunner | None = None) -> None:
        self.delegate = delegate or SubprocessRunner()

    @staticmethod
    def presentation_command(command: Sequence[str]) -> list[str]:
        values = [str(item) for item in command]
        if len(values) < 2 or Path(values[1]).name != LEGACY_OBSERVER_BASENAME:
            return values
        legacy_args = list(values[2:])
        if "--max-ticks" in legacy_args and "--exit-at-max-ticks" not in legacy_args:
            try:
                index = legacy_args.index("--max-ticks")
                horizon = int(legacy_args[index + 1])
            except (ValueError, IndexError):
                horizon = 0
            if horizon > 0:
                legacy_args.append("--exit-at-max-ticks")
        return [values[0], "-m", INTERACTIVE_BRIDGE_MODULE, "--", *legacy_args]

    def start(self, command: Sequence[str], **kwargs: Any):
        rewritten = self.presentation_command(command)
        if len(rewritten) >= 3 and rewritten[1:3] == ["-m", INTERACTIVE_BRIDGE_MODULE]:
            kwargs = dict(kwargs)
            kwargs["stdin"] = subprocess.PIPE
        return self.delegate.start(rewritten, **kwargs)

    def run(self, command: Sequence[str], **kwargs: Any):
        return self.delegate.run(self.presentation_command(command), **kwargs)

    def stream_and_wait(self, process, output) -> int:
        return self.delegate.stream_and_wait(process, output)

    def terminate(self, process) -> None:
        self.delegate.terminate(process)

    def send_control(
        self,
        process,
        *,
        sequence: int,
        command: str,
        value: int | None = None,
    ) -> None:
        command = str(command).strip().lower()
        if command not in _ALLOWED_COMMANDS:
            raise ValueError(f"unsupported interactive Observer command: {command}")
        if process.stdin is None:
            raise RuntimeError("interactive Observer stdin channel is unavailable")
        payload: dict[str, object] = {
            "protocol": CONTROL_PROTOCOL,
            "sequence": int(sequence),
            "command": command,
        }
        if value is not None:
            payload["value"] = int(value)
        process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        process.stdin.flush()


__all__ = [
    "CONTROL_PROTOCOL",
    "INTERACTIVE_BRIDGE_MODULE",
    "InteractivePresentationProcessRunner",
]
