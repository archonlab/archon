"""Operating-system process adapter for Observer execution."""
from __future__ import annotations

import os
import queue
import signal
import subprocess
from typing import Any, Sequence


class SubprocessRunner:
    """The only Observer-launcher component allowed to control OS processes."""

    def start(
        self,
        command: Sequence[str],
        **kwargs: Any,
    ) -> subprocess.Popen[str]:
        return subprocess.Popen(command, **kwargs)

    def run(
        self,
        command: Sequence[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, **kwargs)

    def stream_and_wait(
        self,
        process: subprocess.Popen[str],
        output: queue.Queue[Any],
    ) -> int:
        if process.stdout is not None:
            for line in process.stdout:
                output.put(line)
        return process.wait()

    def terminate(self, process: subprocess.Popen[str]) -> None:
        os.killpg(process.pid, signal.SIGTERM)

    def force_kill(self, process: subprocess.Popen[str]) -> None:
        """Force-stop only the process group explicitly owned by CONTROL1."""
        os.killpg(process.pid, signal.SIGKILL)
