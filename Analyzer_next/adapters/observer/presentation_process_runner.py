"""Process adapter that preserves CONTROL1 ownership but suppresses legacy Tk UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .process_runner import SubprocessRunner


LEGACY_OBSERVER_BASENAME = "universe_search_observer_v441_validation_calibration.py"
BRIDGE_MODULE = "Analyzer_next.adapters.observer.legacy_presentation_bridge"


class PresentationProcessRunner:
    """Delegate OS ownership while replacing only the legacy GUI entry command."""

    def __init__(self, delegate: SubprocessRunner | None = None) -> None:
        self.delegate = delegate or SubprocessRunner()

    @staticmethod
    def presentation_command(command: Sequence[str]) -> list[str]:
        values = [str(item) for item in command]
        if len(values) < 2:
            return values
        if Path(values[1]).name != LEGACY_OBSERVER_BASENAME:
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
        return [
            values[0],
            "-m",
            BRIDGE_MODULE,
            "--",
            *legacy_args,
        ]

    def start(self, command: Sequence[str], **kwargs: Any):
        return self.delegate.start(self.presentation_command(command), **kwargs)

    def run(self, command: Sequence[str], **kwargs: Any):
        return self.delegate.run(self.presentation_command(command), **kwargs)

    def stream_and_wait(self, process, output) -> int:
        return self.delegate.stream_and_wait(process, output)

    def terminate(self, process) -> None:
        self.delegate.terminate(process)


__all__ = ["PresentationProcessRunner"]
