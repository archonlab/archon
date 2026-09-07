"""CONTROL1 projection store layered over frozen CONFIG1/SHELL1 stores."""
from __future__ import annotations

from dataclasses import replace

from Analyzer_next.execution.observer.shell2.config1.store import ConfigShellStore
from Analyzer_next.execution.observer.shell2.store import ShellRoute
from Analyzer_next.execution.observer.state import (
    RunRecord,
    RunSpec,
    RunState,
    TelemetryRecord,
    TelemetryState,
)

from .model import ControlSnapshot


def _idle_spec(output_dir: str) -> RunSpec:
    return RunSpec.create(
        rule_id=0,
        mode="canonical",
        max_ticks=0,
        sample_every=1,
        pressure_every=1,
        output_dir=output_dir,
        outputs=(),
    )


class ControlShellStore(ConfigShellStore):
    """Publish real CONTROL1 lifecycle without mutating earlier store classes."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        idle = RunRecord(
            run_id="OL2-CONTROL-IDLE",
            spec=_idle_spec(self.workflow.snapshot.draft.output_dir),
            state=RunState.DRAFT,
        )
        self._snapshot = replace(
            self._snapshot,
            route=ShellRoute.WORLDS,
            run=idle,
            telemetry=TelemetryRecord(),
            state_strip=(("Execution", "IDLE"), ("Telemetry", "OFFLINE")),
            elapsed_seconds=0,
        )

    def sync_control(self, control: ControlSnapshot, *, elapsed_seconds: int = 0) -> None:
        if control.run is None:
            return
        elapsed = max(0, int(elapsed_seconds))
        telemetry = self._snapshot.telemetry
        if control.telemetry_run_id:
            if telemetry.run_id != control.telemetry_run_id:
                telemetry = TelemetryRecord(
                    state=TelemetryState.CONNECTING,
                    run_id=control.telemetry_run_id,
                )
        else:
            telemetry = TelemetryRecord()
        state_strip = (
            ("Execution", control.run.state.value),
            ("Process", control.run.process_identity or "—"),
            ("Telemetry", control.telemetry_run_id or "awaiting identity"),
        )
        self._publish(
            replace(
                self._snapshot,
                run=control.run,
                telemetry=telemetry,
                state_strip=state_strip,
                elapsed_seconds=elapsed,
            )
        )

    def sync_telemetry(self, *, state: TelemetryState, run_id: str, tick: int | None, error: str | None = None) -> None:
        telemetry = TelemetryRecord(
            state=state,
            run_id=run_id,
            last_tick=tick,
            error=error,
        )
        self._publish(replace(self._snapshot, telemetry=telemetry))

    def pause_or_resume(self):
        return self._snapshot

    def request_stop(self):
        return self._snapshot

    def acknowledge_stop(self):
        return self._snapshot

    def new_run(self):
        if self._snapshot.run.state not in {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.CANCELLED,
        }:
            return self._snapshot
        idle = RunRecord(
            run_id="OL2-CONTROL-IDLE",
            spec=_idle_spec(self.workflow.snapshot.draft.output_dir),
            state=RunState.DRAFT,
        )
        return self._publish(
            replace(
                self._snapshot,
                route=ShellRoute.WORLDS,
                run=idle,
                telemetry=TelemetryRecord(),
                state_strip=(("Execution", "IDLE"), ("Telemetry", "OFFLINE")),
                elapsed_seconds=0,
            )
        )


__all__ = ["ControlShellStore"]
