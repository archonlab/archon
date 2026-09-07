"""Toolkit-independent projection from the SHELL1 store to visible UI data."""
from __future__ import annotations

from dataclasses import dataclass

from Analyzer_next.execution.observer.state import RunState, TelemetryState

from .metrics import format_delta, format_metric
from .store import ShellRoute, ShellSnapshot


@dataclass(frozen=True, slots=True)
class RouteDescriptor:
    route: ShellRoute
    label: str
    glyph: str


ROUTES = (
    RouteDescriptor(ShellRoute.WORLDS, "Worlds", "W"),
    RouteDescriptor(ShellRoute.RUNS, "Runs", "R"),
    RouteDescriptor(ShellRoute.EXPERIMENTS, "Experiments", "E"),
    RouteDescriptor(ShellRoute.MUTATIONS, "Mutations", "M"),
    RouteDescriptor(ShellRoute.OBSERVATION, "Observation", "O"),
    RouteDescriptor(ShellRoute.CAMPAIGNS, "Campaigns", "C"),
    RouteDescriptor(ShellRoute.QUEUE, "Queue", "Q"),
    RouteDescriptor(ShellRoute.SETTINGS, "Settings", "S"),
)


@dataclass(frozen=True, slots=True)
class ControlViewModel:
    status_text: str
    status_token: str
    pause_label: str
    pause_enabled: bool
    stop_enabled: bool
    new_run_enabled: bool


@dataclass(frozen=True, slots=True)
class MetricCardViewModel:
    metric_id: str
    label: str
    value_text: str
    delta_text: str
    source_text: str
    secondary_text: str | None
    history: tuple[float, ...]
    chart_token: str


@dataclass(frozen=True, slots=True)
class ShellViewModel:
    route: ShellRoute
    route_label: str
    controls: ControlViewModel
    elapsed_text: str
    tick_text: str
    telemetry_text: str
    telemetry_token: str
    metric_cards: tuple[MetricCardViewModel, ...]
    state_strip: tuple[tuple[str, str], ...]
    footer_left: str
    footer_right: str
    run_id: str


def _run_status(state: RunState) -> tuple[str, str]:
    mapping = {
        RunState.RUNNING: ("Running", "status.running"),
        RunState.PAUSED: ("Paused", "status.waiting"),
        RunState.STOPPING: ("Stopping", "status.stale"),
        RunState.COMPLETED: ("Completed", "status.completed"),
        RunState.FAILED: ("Failed", "status.failed"),
        RunState.CANCELLED: ("Cancelled", "status.offline"),
        RunState.STARTING: ("Starting", "status.waiting"),
        RunState.PAUSING: ("Pausing", "status.waiting"),
        RunState.RESUMING: ("Resuming", "status.waiting"),
        RunState.QUEUED: ("Queued", "status.waiting"),
        RunState.READY: ("Ready", "status.info"),
        RunState.DRAFT: ("Draft", "status.offline"),
        RunState.VALIDATING: ("Validating", "status.waiting"),
        RunState.INVALID: ("Invalid", "status.failed"),
    }
    return mapping[state]


def _telemetry_status(state: TelemetryState) -> tuple[str, str]:
    mapping = {
        TelemetryState.OFFLINE: ("Telemetry offline", "status.offline"),
        TelemetryState.CONNECTING: ("Telemetry connecting", "status.waiting"),
        TelemetryState.LIVE: ("Telemetry live", "status.running"),
        TelemetryState.STALE: ("Telemetry stale", "status.stale"),
        TelemetryState.ERROR: ("Telemetry error", "status.failed"),
        TelemetryState.CLOSED: ("Telemetry closed", "status.offline"),
    }
    return mapping[state]


def _elapsed(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def build_view_model(snapshot: ShellSnapshot) -> ShellViewModel:
    route_label = next(item.label for item in ROUTES if item.route is snapshot.route)
    status_text, status_token = _run_status(snapshot.run.state)
    telemetry_text, telemetry_token = _telemetry_status(snapshot.telemetry.state)
    pause_label = "Resume" if snapshot.run.state is RunState.PAUSED else "Pause"
    controls = ControlViewModel(
        status_text=status_text,
        status_token=status_token,
        pause_label=pause_label,
        pause_enabled=snapshot.run.state in {RunState.RUNNING, RunState.PAUSED},
        stop_enabled=snapshot.run.state in {
            RunState.STARTING,
            RunState.RUNNING,
            RunState.PAUSING,
            RunState.PAUSED,
            RunState.RESUMING,
        },
        new_run_enabled=snapshot.run.state in {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.CANCELLED,
        },
    )
    cards = []
    for index, sample in enumerate(snapshot.metrics):
        secondary = None
        if sample.secondary_value is not None:
            secondary = f"confidence {sample.secondary_value:.3f}"
        cards.append(
            MetricCardViewModel(
                metric_id=sample.definition.metric_id,
                label=sample.definition.label,
                value_text=format_metric(sample),
                delta_text=format_delta(sample),
                source_text=f"{sample.definition.source} · {sample.definition.kind}",
                secondary_text=secondary,
                history=sample.history,
                chart_token=f"chart.{index % 5 + 1}",
            )
        )
    idle_identity = (
        snapshot.run.run_id == "OL2-CONTROL-IDLE"
        and snapshot.run.spec.max_ticks == 0
        and snapshot.telemetry.run_id is None
    )
    tick = snapshot.telemetry.last_tick
    if idle_identity:
        tick_text = "Tick — / —"
        footer_left = "Cellular Automaton  •  Rule —  •  Grid —"
    else:
        tick_text = (
            f"Tick {tick:,} / {snapshot.run.spec.max_ticks:,}"
            if tick is not None
            else f"Tick — / {snapshot.run.spec.max_ticks:,}"
        )
        footer_left = (
            f"Cellular Automaton  •  Rule {snapshot.run.spec.rule_id}  •  "
            f"{snapshot.run.spec.field_width}×{snapshot.run.spec.field_height} Grid"
        )
    return ShellViewModel(
        route=snapshot.route,
        route_label=route_label,
        controls=controls,
        elapsed_text=_elapsed(snapshot.elapsed_seconds),
        tick_text=tick_text,
        telemetry_text=telemetry_text,
        telemetry_token=telemetry_token,
        metric_cards=tuple(cards),
        state_strip=snapshot.state_strip,
        footer_left=footer_left,
        footer_right="Fake store  •  no process  •  no production cutover",
        run_id=snapshot.run.run_id,
    )
