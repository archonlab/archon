"""Ports and queue contracts for Observer execution."""
from __future__ import annotations

from pathlib import Path
import queue
import subprocess
from typing import Any, Protocol, Sequence, TypedDict


class QueuedObserverRun(TypedDict, total=False):
    rule_id: int
    mode: str
    status: str
    mutation_id: str | None
    run_dir: Path
    run_output_dir: Path
    rule_file: Path | None
    manifest_file: Path | None
    experimental_context: dict[str, Any] | None
    exit_code: int
    launch_error: str


class ProcessRunner(Protocol):
    def start(
        self,
        command: Sequence[str],
        **kwargs: Any,
    ) -> subprocess.Popen[str]: ...

    def run(
        self,
        command: Sequence[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]: ...

    def stream_and_wait(
        self,
        process: subprocess.Popen[str],
        output: queue.Queue[Any],
    ) -> int: ...

    def terminate(self, process: subprocess.Popen[str]) -> None: ...

    def force_kill(self, process: subprocess.Popen[str]) -> None: ...
