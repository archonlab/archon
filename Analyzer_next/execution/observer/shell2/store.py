"""In-memory SHELL1 store backed only by OL2 pure state reducers and fake data."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable

from Analyzer_next.execution.observer.state import (
    LauncherRecord,
    LauncherState,
    RunEvent,
    RunEventType,
    RunRecord,
    RunSpec,
    RunState,
    RunTransitionContext,
    TelemetryEvent,
    TelemetryEventType,
    TelemetryRecord,
    TelemetryState,
    accept_telemetry_sample,
    reduce_run,
    reduce_telemetry,
)

from .metrics import MetricDefinition, MetricSample, load_default_metric_definitions
from .theme import ColorScheme, ThemeMode, resolve_scheme


class ShellRoute(str, Enum):
    WORLDS = "worlds"
    RUNS = "runs"
    EXPERIMENTS = "experiments"
    MUTATIONS = "mutations"
    OBSERVATION = "observation"
    CAMPAIGNS = "campaigns"
    QUEUE = "queue"
    SETTINGS = "settings"


@dataclass(frozen=True, slots=True)
class ShellSnapshot:
    route: ShellRoute
    theme_preference: ThemeMode
    resolved_theme: ColorScheme
    launcher: LauncherRecord
    run: RunRecord
    telemetry: TelemetryRecord
    metrics: tuple[MetricSample, ...]
    state_strip: tuple[tuple[str, str], ...]
    elapsed_seconds: int
    revision: int = 0


Subscriber = Callable[[ShellSnapshot], None]


def _demo_spec() -> RunSpec:
    return RunSpec.create(
        rule_id=42,
        mode="canonical",
        max_ticks=20_000,
        sample_every=10,
        pressure_every=100,
        output_dir="Results/Universe_Search/observation_logs/OL2-DEMO-0042",
        outputs=("chronicle", "events", "pressure", "samples", "sqlite"),
        field_width=96,
        field_height=64,
        topology="torus",
        boundary_mode="wrap",
        seed=42,
        experimental_context={"shell": "OL2-SHELL1", "source": "fake-store"},
    )


def _metric_seed(definition: MetricDefinition) -> tuple[float, float, tuple[float, ...], str, float | None]:
    fixtures = {
        "objects": (1247.0, 1265.0, (1198, 1221, 1204, 1238, 1217, 1251, 1232, 1247), "objects", None),
        "total_living_mass": (12732.0, 12669.0, (12180, 12310, 12260, 12480, 12530, 12495, 12669, 12732), "cells", None),
        "largest": (2134.0, 2071.0, (1870, 1944, 1918, 2020, 1984, 2051, 2071, 2134), "cells", None),
        "ecosystem_health": (0.781, 0.774, (0.72, 0.74, 0.73, 0.76, 0.75, 0.77, 0.774, 0.781), "score", None),
        "stability_index": (0.842, 0.839, (0.78, 0.81, 0.79, 0.82, 0.80, 0.83, 0.839, 0.842), "score", None),
        "life_score": (0.806, 0.798, (0.71, 0.74, 0.73, 0.77, 0.76, 0.79, 0.798, 0.806), "score", 0.913),
    }
    try:
        return fixtures[definition.metric_id]
    except KeyError as exc:
        raise ValueError(f"no SHELL1 fixture for {definition.metric_id}") from exc


def _demo_metrics() -> tuple[MetricSample, ...]:
    samples = []
    for definition in load_default_metric_definitions():
        value, previous, history, unit, secondary = _metric_seed(definition)
        samples.append(
            MetricSample(
                definition=definition,
                value=value,
                previous_value=previous,
                history=tuple(float(item) for item in history),
                unit=unit,
                secondary_value=secondary,
            )
        )
    return tuple(samples)


def initial_snapshot(
    *,
    theme_preference: ThemeMode = ThemeMode.SYSTEM,
    system_scheme: ColorScheme | None = None,
) -> ShellSnapshot:
    run_id = "OL2-DEMO-0042"
    return ShellSnapshot(
        route=ShellRoute.OBSERVATION,
        theme_preference=theme_preference,
        resolved_theme=resolve_scheme(
            theme_preference,
            system_scheme=system_scheme,
        ),
        launcher=LauncherRecord(state=LauncherState.READY),
        run=RunRecord(
            run_id=run_id,
            spec=_demo_spec(),
            state=RunState.RUNNING,
            process_identity="fake:observer",
        ),
        telemetry=TelemetryRecord(
            state=TelemetryState.LIVE,
            run_id=run_id,
            last_tick=7_643,
        ),
        metrics=_demo_metrics(),
        state_strip=(
            ("Life", "PERSISTENT"),
            ("Structure", "MULTI-COLONY"),
            ("Phase", "STABLE GROWTH"),
            ("Morphology", "BRANCHED"),
            ("Validation", "A"),
        ),
        elapsed_seconds=12 * 60 + 47,
    )


class FakeShellStore:
    """Observable, deterministic store with no process or telemetry adapter."""

    def __init__(
        self,
        *,
        theme_preference: ThemeMode = ThemeMode.SYSTEM,
        system_scheme: ColorScheme | None = None,
    ) -> None:
        self._snapshot = initial_snapshot(
            theme_preference=theme_preference,
            system_scheme=system_scheme,
        )
        self._subscribers: list[Subscriber] = []
        self._clone_number = 0

    @property
    def snapshot(self) -> ShellSnapshot:
        return self._snapshot

    def subscribe(self, subscriber: Subscriber) -> Callable[[], None]:
        self._subscribers.append(subscriber)
        subscriber(self._snapshot)

        def unsubscribe() -> None:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

        return unsubscribe

    def _publish(self, snapshot: ShellSnapshot) -> ShellSnapshot:
        self._snapshot = replace(snapshot, revision=self._snapshot.revision + 1)
        for subscriber in tuple(self._subscribers):
            subscriber(self._snapshot)
        return self._snapshot

    def select_route(self, route: ShellRoute | str) -> ShellSnapshot:
        return self._publish(replace(self._snapshot, route=ShellRoute(route)))

    def set_theme(
        self,
        preference: ThemeMode | str,
        *,
        system_scheme: ColorScheme | str | None = None,
    ) -> ShellSnapshot:
        mode = ThemeMode(preference)
        resolved = resolve_scheme(
            mode,
            system_scheme=system_scheme,
            last_resolved=self._snapshot.resolved_theme,
        )
        return self._publish(
            replace(
                self._snapshot,
                theme_preference=mode,
                resolved_theme=resolved,
            )
        )

    def pause_or_resume(self) -> ShellSnapshot:
        context = RunTransitionContext.permissive()
        record = self._snapshot.run
        if record.state is RunState.RUNNING:
            record = reduce_run(record, RunEvent(RunEventType.PAUSE), context)
            record = reduce_run(record, RunEvent(RunEventType.PAUSE_ACK), context)
        elif record.state is RunState.PAUSED:
            record = reduce_run(record, RunEvent(RunEventType.RESUME), context)
            record = reduce_run(record, RunEvent(RunEventType.RESUME_ACK), context)
        else:
            return self._snapshot
        return self._publish(replace(self._snapshot, run=record))

    def request_stop(self) -> ShellSnapshot:
        if self._snapshot.run.state not in {
            RunState.STARTING,
            RunState.RUNNING,
            RunState.PAUSING,
            RunState.PAUSED,
            RunState.RESUMING,
        }:
            return self._snapshot
        record = reduce_run(
            self._snapshot.run,
            RunEvent(RunEventType.STOP),
            RunTransitionContext.permissive(),
        )
        return self._publish(replace(self._snapshot, run=record))

    def acknowledge_stop(self) -> ShellSnapshot:
        if self._snapshot.run.state is not RunState.STOPPING:
            return self._snapshot
        record = reduce_run(
            self._snapshot.run,
            RunEvent(RunEventType.PROCESS_EXITED_AFTER_STOP, exit_code=-15),
            RunTransitionContext.permissive(),
        )
        telemetry = self._snapshot.telemetry
        if telemetry.state in {TelemetryState.LIVE, TelemetryState.STALE}:
            telemetry = reduce_telemetry(
                telemetry,
                TelemetryEvent(TelemetryEventType.SOURCE_CLOSED),
            )
        return self._publish(
            replace(self._snapshot, run=record, telemetry=telemetry)
        )

    def new_run(self) -> ShellSnapshot:
        if self._snapshot.run.state not in {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.CANCELLED,
        }:
            return self._snapshot
        self._clone_number += 1
        new_id = f"{self._snapshot.run.run_id}-CLONE-{self._clone_number:02d}"
        run = reduce_run(
            self._snapshot.run,
            RunEvent(RunEventType.CLONE, new_run_id=new_id),
            RunTransitionContext.permissive(),
        )
        return self._publish(
            replace(
                self._snapshot,
                route=ShellRoute.WORLDS,
                run=run,
                telemetry=TelemetryRecord(),
                elapsed_seconds=0,
            )
        )

    def reset_demo(self) -> ShellSnapshot:
        fresh = initial_snapshot(
            theme_preference=self._snapshot.theme_preference,
            system_scheme=self._snapshot.resolved_theme,
        )
        return self._publish(replace(fresh, route=self._snapshot.route))

    def advance_tick(self, amount: int = 10) -> ShellSnapshot:
        if amount < 1:
            raise ValueError("tick increment must be positive")
        if (
            self._snapshot.run.state is not RunState.RUNNING
            or self._snapshot.telemetry.state is not TelemetryState.LIVE
        ):
            return self._snapshot
        telemetry = accept_telemetry_sample(
            self._snapshot.telemetry,
            run_id=self._snapshot.run.run_id,
            tick=int(self._snapshot.telemetry.last_tick or 0) + amount,
        )
        step = self._snapshot.revision + 1
        integer_pattern = (-3.0, 5.0, 2.0, -1.0, 4.0)
        score_pattern = (-0.002, 0.004, 0.001, -0.001, 0.003)
        metrics = []
        for index, sample in enumerate(self._snapshot.metrics):
            pattern = (
                integer_pattern
                if sample.definition.value_format == "integer"
                else score_pattern
            )
            change = pattern[(step + index) % len(pattern)]
            value = sample.value + change
            if sample.definition.value_format == "score_0_1":
                value = min(1.0, max(0.0, value))
            secondary = sample.secondary_value
            if secondary is not None:
                secondary = min(1.0, max(0.0, secondary + score_pattern[step % 5]))
            history = (*sample.history[-11:], value)
            metrics.append(
                replace(
                    sample,
                    previous_value=sample.value,
                    value=value,
                    history=history,
                    secondary_value=secondary,
                )
            )
        return self._publish(
            replace(
                self._snapshot,
                telemetry=telemetry,
                metrics=tuple(metrics),
                elapsed_seconds=self._snapshot.elapsed_seconds + 1,
            )
        )
