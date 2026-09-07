"""Toolkit-independent process controller for the OL2 Analyzer console."""
from __future__ import annotations

import os
import queue
import subprocess
import threading
from typing import Any

from Analyzer_next.execution.observer.contracts import ProcessRunner

from .model import (
    AnalysisEvent,
    AnalysisEventType,
    AnalysisLaunchPlan,
    AnalysisRecord,
    AnalysisState,
    initial_analysis_record,
    reduce_analysis,
)


class AnalysisController:
    """Own one fixed Analyzer process; UI code only drains text and state."""

    def __init__(self, plan: AnalysisLaunchPlan, process_runner: ProcessRunner) -> None:
        self.plan = plan
        self.process_runner = process_runner
        self._record = initial_analysis_record()
        self._process: Any | None = None
        self._output: queue.Queue[Any] = queue.Queue()
        self._lock = threading.RLock()

    @property
    def record(self) -> AnalysisRecord:
        with self._lock:
            return self._record

    def _append(self, line: str) -> None:
        self._output.put(line)

    def start(self) -> AnalysisRecord:
        with self._lock:
            self._record = reduce_analysis(
                self._record,
                AnalysisEvent(AnalysisEventType.START_REQUEST),
            )
            self._append(
                "\n" + "=" * 80 + "\n"
                + f"OL2-ANALYZE1 attempt {self._record.attempt}\n"
                + f"Launcher: {self.plan.launcher}\n"
                + f"SHA-256: {self.plan.launcher_sha256}\n"
                + "=" * 80 + "\n"
            )
            environment = os.environ.copy()
            environment["PYTHONUNBUFFERED"] = "1"
            try:
                process = self.process_runner.start(
                    list(self.plan.command),
                    cwd=str(self.plan.project_root),
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                    shell=False,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._record = reduce_analysis(
                    self._record,
                    AnalysisEvent(AnalysisEventType.START_FAILED, error=error),
                )
                self._append(f"[Analyzer launch failed] {error}\n")
                return self._record
            self._process = process
            self._record = reduce_analysis(
                self._record,
                AnalysisEvent(AnalysisEventType.START_ACK),
            )
            self._append(f"[Analyzer started] pid={process.pid}\n")
            threading.Thread(
                target=self._stream_and_finalize,
                args=(process,),
                name="ol2-analyzer-output",
                daemon=True,
            ).start()
            return self._record

    def _stream_and_finalize(self, process: Any) -> None:
        error: str | None = None
        try:
            exit_code = int(self.process_runner.stream_and_wait(process, self._output))
        except Exception as exc:
            exit_code = 125
            error = f"{type(exc).__name__}: {exc}"
            self._append(f"[Analyzer stream failed] {error}\n")
        with self._lock:
            if process is not self._process:
                return
            self._record = reduce_analysis(
                self._record,
                AnalysisEvent(
                    AnalysisEventType.PROCESS_EXIT,
                    exit_code=exit_code,
                    error=error,
                ),
            )
            self._process = None
            self._append(
                f"\n[Analyzer finished] state={self._record.state.value} "
                f"exit_code={exit_code}\n"
            )

    def stop(self) -> AnalysisRecord:
        with self._lock:
            self._record = reduce_analysis(
                self._record,
                AnalysisEvent(AnalysisEventType.STOP_REQUEST),
            )
            process = self._process
            if process is None:
                raise RuntimeError("Analyzer process identity is missing")
            self._append("[Stop requested] terminating Analyzer process group…\n")
            try:
                self.process_runner.terminate(process)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._record = reduce_analysis(
                    self._record,
                    AnalysisEvent(AnalysisEventType.STOP_FAILED, error=error),
                )
                self._append(f"[Analyzer stop failed] {error}\n")
                raise RuntimeError(error) from exc
            return self._record

    def drain_output(self, *, maximum: int = 1000) -> tuple[str, ...]:
        lines: list[str] = []
        for _ in range(maximum):
            try:
                item = self._output.get_nowait()
            except queue.Empty:
                break
            lines.append(str(item))
        return tuple(lines)

    def close(self) -> None:
        if self.record.state in {AnalysisState.STARTING, AnalysisState.RUNNING}:
            try:
                self.stop()
            except Exception:
                pass
