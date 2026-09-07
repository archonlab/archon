"""Toolkit-independent real Observer process controller for OL2-CONTROL1."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from typing import Any, Callable

from Analyzer_next.execution.observer.contracts import ProcessRunner
from Analyzer_next.execution.observer.shell2.config1.model import PreparedConfiguration
from Analyzer_next.execution.observer.state import (
    ControlCapabilities,
    RunEvent,
    RunEventType,
    RunRecord,
    RunState,
    RunTransitionContext,
    reduce_run,
)

from .model import ControlSnapshot


Clock = Callable[[], float]
_TELEMETRY_RUN_ID = re.compile(r"^\[telemetry\]\s+run_id=([^\s]+)")
_STOP_ONLY = ControlCapabilities(
    supports_stop=True,
    supports_pause=False,
    supports_resume=False,
)


def _transition_context(*, process_identity_matches: bool = False) -> RunTransitionContext:
    return RunTransitionContext(
        world_and_configuration_present=True,
        scientific_and_authorization_checks_pass=True,
        runspec_committed=True,
        launcher_ready=True,
        queue_head=True,
        no_active_process=True,
        process_identity_matches=process_identity_matches,
        stop_authorized=True,
        capabilities=_STOP_ONLY,
    )


class _OutputSink:
    """Minimal queue-compatible sink used by the existing ProcessRunner port."""

    def __init__(self, owner: "ObserverControlController") -> None:
        self.owner = owner

    def put(self, item: Any) -> None:
        self.owner._capture_output(str(item))


class ObserverControlController:
    """Own at most one explicitly launched Observer process group."""

    def __init__(
        self,
        project_root,
        process_runner: ProcessRunner,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        self.project_root = project_root.resolve()
        self.process_runner = process_runner
        self.clock = clock
        self._snapshot = ControlSnapshot()
        self._process: Any | None = None
        self._output: queue.Queue[str] = queue.Queue()
        self._lock = threading.RLock()
        self._diagnostic_log: Path | None = None
        self._diagnostic_terminal: Path | None = None
        self._diagnostic_started_utc: str | None = None
        self._diagnostic_retry_of: str | None = None
        self._process_finished = threading.Event()
        self._process_finished.set()

    @property
    def snapshot(self) -> ControlSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def elapsed_seconds(self) -> int:
        with self._lock:
            started = self._snapshot.started_monotonic
            if started is None:
                return 0
            end = self._snapshot.finished_monotonic
            if end is None:
                end = self.clock()
            return max(0, int(end - started))

    @property
    def process_active(self) -> bool:
        with self._lock:
            return self._process is not None

    def _publish(self, **changes: Any) -> ControlSnapshot:
        self._snapshot = replace(
            self._snapshot,
            **changes,
            revision=self._snapshot.revision + 1,
        )
        return self._snapshot

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _diagnostic_paths(self, prepared: PreparedConfiguration) -> tuple[Path, Path]:
        output = Path(prepared.run_spec.output_dir).expanduser()
        if not output.is_absolute():
            output = self.project_root / output
        output.mkdir(parents=True, exist_ok=True)
        return output / "ol2_execution.log", output / "ol2_terminal.json"

    def _append_diagnostic(self, text: str) -> None:
        path = self._diagnostic_log
        if path is None:
            return
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(text)
        except OSError:
            # Diagnostics must never change execution semantics.
            pass

    def _write_terminal_diagnostic(self, *, exit_code: int | None, error: str | None) -> None:
        path = self._diagnostic_terminal
        run = self._snapshot.run
        if path is None:
            return
        payload = {
            "schema": "archon.ol2.execution-terminal.v1",
            "execution_id": run.run_id if run is not None else None,
            "state": run.state.value if run is not None else "UNKNOWN",
            "process_identity": run.process_identity if run is not None else None,
            "telemetry_run_id": self._snapshot.telemetry_run_id,
            "exit_code": exit_code,
            "error": error or (run.error if run is not None else None),
            "command": list(self._snapshot.command),
            "cwd": str(self.project_root),
            "started_utc": self._diagnostic_started_utc,
            "finished_utc": self._utc_now(),
            "retry_of_queue_id": getattr(self, "_diagnostic_retry_of", None),
        }
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass

    def _capture_output(self, text: str) -> None:
        self._output.put(text)
        self._append_diagnostic(text)
        match = _TELEMETRY_RUN_ID.match(text.strip())
        if match is None:
            return
        run_id = match.group(1).strip()
        if not run_id:
            return
        with self._lock:
            run = self._snapshot.run
            expected_rule = None if run is None else int(run.spec.rule_id)
            if expected_rule is not None:
                expected_prefix = f"rule_{expected_rule:05d}_"
                if not run_id.startswith(expected_prefix):
                    self._output.put(
                        "[CONTROL1 identity guard] ignored telemetry run_id for "
                        f"wrong rule: {run_id}; expected_prefix={expected_prefix}\n"
                    )
                    return
            current = self._snapshot.telemetry_run_id
            if current is None:
                self._publish(telemetry_run_id=run_id)
            elif current != run_id:
                self._output.put(
                    "[CONTROL1 identity guard] ignored conflicting telemetry run_id="
                    f"{run_id}; active={current}\n"
                )

    def start(
        self,
        prepared: PreparedConfiguration,
        *,
        retry_of: str | None = None,
    ) -> ControlSnapshot:
        with self._lock:
            if self._process is not None or self._snapshot.active:
                raise RuntimeError("Observer process is already active")
            if not prepared.command:
                raise ValueError("prepared command is empty")
            attempt = self._snapshot.attempt + 1
            execution_id = f"OL2-CTRL-{prepared.review_hash[:12]}-{attempt:03d}"
            run = RunRecord(
                run_id=execution_id,
                spec=prepared.run_spec,
                state=RunState.DRAFT,
            )
            context = _transition_context()
            run = reduce_run(run, RunEvent(RunEventType.VALIDATE), context)
            run = reduce_run(run, RunEvent(RunEventType.VALIDATION_PASSED), context)
            run = reduce_run(run, RunEvent(RunEventType.QUEUE), context)
            run = reduce_run(run, RunEvent(RunEventType.START), context)
            started = self.clock()
            self._publish(
                run=run,
                review_hash=prepared.review_hash,
                command=tuple(prepared.command),
                telemetry_run_id=None,
                attempt=attempt,
                started_monotonic=started,
                finished_monotonic=None,
            )
            self._process_finished.clear()
            self._diagnostic_log, self._diagnostic_terminal = self._diagnostic_paths(prepared)
            self._diagnostic_started_utc = self._utc_now()
            self._diagnostic_retry_of = retry_of
            try:
                self._diagnostic_log.write_text(
                    f"[OL2 diagnostic] started_utc={self._diagnostic_started_utc}\n"
                    f"[OL2 diagnostic] execution_id={execution_id}\n"
                    f"[OL2 diagnostic] cwd={self.project_root}\n"
                    f"[OL2 diagnostic] command={prepared.command_text}\n"
                    f"[OL2 diagnostic] retry_of_queue_id={retry_of or '-'}\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
            self._output.put(
                "\n" + "=" * 80 + "\n"
                + f"OL2-CONTROL1 attempt {attempt}\n"
                + f"Execution ID: {execution_id}\n"
                + f"Review SHA-256: {prepared.review_hash}\n"
                + "=" * 80 + "\n"
            )

            environment = os.environ.copy()
            environment["PYTHONUNBUFFERED"] = "1"
            if retry_of:
                environment["ARCHON_OL2_RETRY_OF_QUEUE_ID"] = str(retry_of)
            else:
                environment.pop("ARCHON_OL2_RETRY_OF_QUEUE_ID", None)
            try:
                process = self.process_runner.start(
                    list(prepared.command),
                    cwd=str(self.project_root),
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
                run = reduce_run(
                    run,
                    RunEvent(RunEventType.START_FAILED, error=error),
                    context,
                )
                self._publish(
                    run=run,
                    finished_monotonic=self.clock(),
                )
                self._capture_output(f"[Observer launch failed] {error}\n")
                self._write_terminal_diagnostic(exit_code=None, error=error)
                self._process_finished.set()
                return self._snapshot

            self._process = process
            process_identity = f"pid:{int(process.pid)}"
            run = reduce_run(
                run,
                RunEvent(
                    RunEventType.PROCESS_STARTED,
                    process_identity=process_identity,
                ),
                _transition_context(process_identity_matches=True),
            )
            self._publish(run=run)
            self._output.put(f"[Observer started] {process_identity}\n")
            threading.Thread(
                target=self._stream_and_finalize,
                args=(process,),
                name="ol2-observer-control-output",
                daemon=True,
            ).start()
            return self._snapshot

    def _stream_and_finalize(self, process: Any) -> None:
        error: str | None = None
        try:
            exit_code = int(
                self.process_runner.stream_and_wait(process, _OutputSink(self))
            )
        except Exception as exc:
            exit_code = 125
            error = f"{type(exc).__name__}: {exc}"
            self._capture_output(f"[Observer stream failed] {error}\n")

        with self._lock:
            if process is not self._process:
                return
            run = self._snapshot.run
            if run is not None:
                context = _transition_context(process_identity_matches=True)
                if run.state is RunState.STOPPING:
                    event = (
                        RunEvent(RunEventType.PROCESS_COMPLETED_BEFORE_STOP, exit_code=0)
                        if exit_code == 0
                        else RunEvent(
                            RunEventType.PROCESS_EXITED_AFTER_STOP,
                            exit_code=exit_code,
                        )
                    )
                    run = reduce_run(run, event, context)
                elif run.state is RunState.RUNNING:
                    event = (
                        RunEvent(RunEventType.PROCESS_EXITED_ZERO, exit_code=0)
                        if exit_code == 0
                        else RunEvent(
                            RunEventType.PROCESS_EXITED_NONZERO,
                            exit_code=exit_code,
                            error=error,
                        )
                    )
                    run = reduce_run(run, event, context)
            self._process = None
            self._publish(
                run=run,
                finished_monotonic=self.clock(),
            )
            state = run.state.value if run is not None else "UNKNOWN"
            self._capture_output(
                f"\n[Observer finished] state={state} exit_code={exit_code}\n"
            )
            self._write_terminal_diagnostic(exit_code=exit_code, error=error)
            self._process_finished.set()

    def stop(self) -> ControlSnapshot:
        with self._lock:
            process = self._process
            run = self._snapshot.run
            if process is None or run is None:
                raise RuntimeError("Observer process identity is missing")
            if run.state not in {
                RunState.STARTING,
                RunState.RUNNING,
                RunState.PAUSING,
                RunState.PAUSED,
                RunState.RESUMING,
            }:
                raise RuntimeError(f"Observer cannot stop from {run.state.value}")
            run = reduce_run(
                run,
                RunEvent(RunEventType.STOP),
                _transition_context(process_identity_matches=True),
            )
            self._publish(run=run)
            self._output.put("[Stop requested] terminating Observer process group…\n")
            try:
                self.process_runner.terminate(process)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                run = reduce_run(
                    run,
                    RunEvent(RunEventType.STOP_FAILED, error=error),
                    _transition_context(process_identity_matches=True),
                )
                self._publish(run=run)
                self._output.put(f"[Observer stop failed] {error}\n")
                raise RuntimeError(error) from exc
            return self._snapshot

    def drain_output(self, *, maximum: int = 2000) -> tuple[str, ...]:
        chunks: list[str] = []
        for _ in range(maximum):
            try:
                chunks.append(self._output.get_nowait())
            except queue.Empty:
                break
        return tuple(chunks)

    def close(
        self,
        *,
        grace_seconds: float = 2.0,
        kill_seconds: float = 1.0,
    ) -> bool:
        """Release only the process group CONTROL1 owns before launcher exit.

        Normal window close is not treated as a crash.  Request a regular stop,
        wait a bounded interval for the output/finalizer thread, then escalate to
        the adapter's process-group force kill if the owned process ignores
        SIGTERM.  Returning ``False`` means ownership could not be proven
        released; callers must not fabricate a terminal Queue/evidence state.
        """
        grace_seconds = max(0.0, float(grace_seconds))
        kill_seconds = max(0.0, float(kill_seconds))
        with self._lock:
            process = self._process
            run = self._snapshot.run
        if process is None:
            self._process_finished.set()
            return True

        if run is not None and run.state in {
            RunState.STARTING,
            RunState.RUNNING,
            RunState.PAUSING,
            RunState.PAUSED,
            RunState.RESUMING,
        }:
            try:
                self.stop()
            except Exception as exc:
                self._capture_output(
                    f"[CONTROL1 shutdown guard] graceful stop failed: {type(exc).__name__}: {exc}\n"
                )
        else:
            try:
                self.process_runner.terminate(process)
            except Exception as exc:
                self._capture_output(
                    f"[CONTROL1 shutdown guard] terminate failed: {type(exc).__name__}: {exc}\n"
                )

        if self._process_finished.wait(grace_seconds):
            return True

        with self._lock:
            current = self._process
        if current is None:
            return True
        killer = getattr(self.process_runner, "force_kill", None)
        if callable(killer):
            try:
                self._capture_output(
                    "[CONTROL1 shutdown guard] graceful stop timed out; force-killing owned process group\n"
                )
                killer(current)
            except Exception as exc:
                self._capture_output(
                    f"[CONTROL1 shutdown guard] force kill failed: {type(exc).__name__}: {exc}\n"
                )
        else:
            # Compatibility with deterministic/legacy adapters: retry the same
            # scoped termination primitive, never reach outside CONTROL1's owner.
            try:
                self.process_runner.terminate(current)
            except Exception:
                pass

        if self._process_finished.wait(kill_seconds):
            return True
        self._capture_output(
            "[CONTROL1 shutdown guard] owned Observer process did not reach a confirmed terminal state\n"
        )
        return False


__all__ = ["ObserverControlController"]
