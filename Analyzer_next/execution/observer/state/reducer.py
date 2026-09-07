"""Pure fail-closed reducers for Observer Launcher 2.0."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Generic, TypeVar

from .events import (
    LauncherEvent,
    LauncherEventType,
    RunEvent,
    RunEventType,
    TelemetryEvent,
    TelemetryEventType,
)
from .model import (
    LauncherRecord,
    LauncherState,
    LauncherTransitionContext,
    RunRecord,
    RunState,
    RunTransitionContext,
    TERMINAL_RUN_STATES,
    TelemetryRecord,
    TelemetryState,
    TransitionRejected,
)


StateT = TypeVar("StateT")


@dataclass(frozen=True, slots=True)
class TransitionRule(Generic[StateT]):
    target: StateT
    guard: str | None = None


LAUNCHER_TRANSITIONS = {
    (LauncherState.BOOTSTRAPPING, LauncherEventType.BOOT_OK): TransitionRule(
        LauncherState.READY
    ),
    (
        LauncherState.BOOTSTRAPPING,
        LauncherEventType.BOOT_FAILED,
    ): TransitionRule(LauncherState.FAULTED),
    (LauncherState.READY, LauncherEventType.CLOSE_REQUESTED): TransitionRule(
        LauncherState.SHUTTING_DOWN,
        "active_run_resolved",
    ),
    (
        LauncherState.SHUTTING_DOWN,
        LauncherEventType.CLOSE_CONFIRMED,
    ): TransitionRule(LauncherState.CLOSED),
    (
        LauncherState.READY,
        LauncherEventType.INFRASTRUCTURE_FAILED,
    ): TransitionRule(LauncherState.FAULTED),
    (LauncherState.FAULTED, LauncherEventType.RECOVERED): TransitionRule(
        LauncherState.READY
    ),
}


RUN_TRANSITIONS = {
    (RunState.DRAFT, RunEventType.VALIDATE): TransitionRule(
        RunState.VALIDATING,
        "world_and_configuration_present",
    ),
    (RunState.VALIDATING, RunEventType.VALIDATION_PASSED): TransitionRule(
        RunState.READY,
        "scientific_and_authorization_checks_pass",
    ),
    (RunState.VALIDATING, RunEventType.VALIDATION_FAILED): TransitionRule(
        RunState.INVALID
    ),
    (RunState.INVALID, RunEventType.EDIT): TransitionRule(RunState.DRAFT),
    (RunState.READY, RunEventType.EDIT): TransitionRule(RunState.DRAFT),
    (RunState.READY, RunEventType.QUEUE): TransitionRule(
        RunState.QUEUED,
        "runspec_committed",
    ),
    (RunState.QUEUED, RunEventType.START): TransitionRule(
        RunState.STARTING,
        "launcher_ready_queue_head_no_active_process",
    ),
    (RunState.QUEUED, RunEventType.CANCEL): TransitionRule(
        RunState.CANCELLED
    ),
    (RunState.STARTING, RunEventType.PROCESS_STARTED): TransitionRule(
        RunState.RUNNING,
        "process_identity_matches",
    ),
    (RunState.STARTING, RunEventType.START_FAILED): TransitionRule(
        RunState.FAILED
    ),
    (RunState.STARTING, RunEventType.STOP): TransitionRule(
        RunState.STOPPING
    ),
    (RunState.RUNNING, RunEventType.PAUSE): TransitionRule(
        RunState.PAUSING,
        "supports_pause",
    ),
    (RunState.PAUSING, RunEventType.PAUSE_ACK): TransitionRule(
        RunState.PAUSED
    ),
    (RunState.PAUSING, RunEventType.CONTROL_FAILED): TransitionRule(
        RunState.FAILED
    ),
    (RunState.PAUSED, RunEventType.RESUME): TransitionRule(
        RunState.RESUMING,
        "supports_resume",
    ),
    (RunState.RESUMING, RunEventType.RESUME_ACK): TransitionRule(
        RunState.RUNNING
    ),
    (RunState.RESUMING, RunEventType.CONTROL_FAILED): TransitionRule(
        RunState.FAILED
    ),
    (RunState.RUNNING, RunEventType.PROCESS_EXITED_ZERO): TransitionRule(
        RunState.COMPLETED
    ),
    (
        RunState.RUNNING,
        RunEventType.PROCESS_EXITED_NONZERO,
    ): TransitionRule(RunState.FAILED),
    (RunState.RUNNING, RunEventType.STOP): TransitionRule(
        RunState.STOPPING
    ),
    (RunState.PAUSING, RunEventType.STOP): TransitionRule(
        RunState.STOPPING
    ),
    (RunState.PAUSED, RunEventType.STOP): TransitionRule(
        RunState.STOPPING
    ),
    (RunState.RESUMING, RunEventType.STOP): TransitionRule(
        RunState.STOPPING
    ),
    (
        RunState.STOPPING,
        RunEventType.PROCESS_EXITED_AFTER_STOP,
    ): TransitionRule(RunState.CANCELLED),
    (
        RunState.STOPPING,
        RunEventType.PROCESS_COMPLETED_BEFORE_STOP,
    ): TransitionRule(RunState.COMPLETED),
    (RunState.STOPPING, RunEventType.STOP_FAILED): TransitionRule(
        RunState.FAILED
    ),
}


TELEMETRY_TRANSITIONS = {
    (TelemetryState.OFFLINE, TelemetryEventType.CONNECT): TransitionRule(
        TelemetryState.CONNECTING
    ),
    (
        TelemetryState.CONNECTING,
        TelemetryEventType.SOURCE_VERIFIED,
    ): TransitionRule(TelemetryState.LIVE, "run_identity_matches"),
    (
        TelemetryState.CONNECTING,
        TelemetryEventType.SOURCE_FAILED,
    ): TransitionRule(TelemetryState.ERROR),
    (
        TelemetryState.LIVE,
        TelemetryEventType.FRESHNESS_EXPIRED,
    ): TransitionRule(TelemetryState.STALE),
    (TelemetryState.LIVE, TelemetryEventType.SOURCE_CLOSED): TransitionRule(
        TelemetryState.CLOSED
    ),
    (TelemetryState.LIVE, TelemetryEventType.READ_FAILED): TransitionRule(
        TelemetryState.ERROR
    ),
    (TelemetryState.STALE, TelemetryEventType.FRESH_UPDATE): TransitionRule(
        TelemetryState.LIVE,
        "run_identity_matches",
    ),
    (TelemetryState.STALE, TelemetryEventType.READ_FAILED): TransitionRule(
        TelemetryState.ERROR
    ),
    (TelemetryState.STALE, TelemetryEventType.SOURCE_CLOSED): TransitionRule(
        TelemetryState.CLOSED
    ),
    (TelemetryState.ERROR, TelemetryEventType.RECONNECT): TransitionRule(
        TelemetryState.CONNECTING
    ),
}


def _reject(machine: str, state: str, event: str, reason: str) -> None:
    raise TransitionRejected(
        machine=machine,
        state=state,
        event=event,
        reason=reason,
    )


def reduce_launcher(
    record: LauncherRecord,
    event: LauncherEvent,
    context: LauncherTransitionContext | None = None,
) -> LauncherRecord:
    context = context or LauncherTransitionContext()
    rule = LAUNCHER_TRANSITIONS.get((record.state, event.kind))
    if rule is None:
        _reject("launcher", record.state.value, event.kind.value, "illegal transition")
    if rule.guard == "active_run_resolved" and not context.active_run_resolved:
        _reject("launcher", record.state.value, event.kind.value, rule.guard)
    error = event.error if rule.target is LauncherState.FAULTED else None
    return replace(
        record,
        state=rule.target,
        error=error,
        revision=record.revision + 1,
    )


def _require_run_payload(record: RunRecord, event: RunEvent) -> None:
    if event.kind is RunEventType.PROCESS_STARTED:
        if not event.process_identity:
            _reject(
                "run",
                record.state.value,
                event.kind.value,
                "process_identity is required",
            )
    if event.kind is RunEventType.PROCESS_EXITED_ZERO:
        if event.exit_code not in {None, 0}:
            _reject(
                "run",
                record.state.value,
                event.kind.value,
                "zero exit event cannot carry non-zero exit_code",
            )
    if event.kind is RunEventType.PROCESS_EXITED_NONZERO:
        if event.exit_code in {None, 0}:
            _reject(
                "run",
                record.state.value,
                event.kind.value,
                "non-zero exit_code is required",
            )


def clone_terminal_run(record: RunRecord, event: RunEvent) -> RunRecord:
    if record.state not in TERMINAL_RUN_STATES:
        _reject(
            "run",
            record.state.value,
            event.kind.value,
            "only a terminal run may be cloned",
        )
    new_run_id = str(event.new_run_id or "").strip()
    if not new_run_id or new_run_id == record.run_id:
        _reject(
            "run",
            record.state.value,
            event.kind.value,
            "clone requires a distinct new_run_id",
        )
    return RunRecord(
        run_id=new_run_id,
        spec=event.new_spec or record.spec,
        state=RunState.DRAFT,
        parent_run_id=record.run_id,
    )


def reduce_run(
    record: RunRecord,
    event: RunEvent,
    context: RunTransitionContext | None = None,
) -> RunRecord:
    context = context or RunTransitionContext()
    if event.kind is RunEventType.CLONE:
        return clone_terminal_run(record, event)

    rule = RUN_TRANSITIONS.get((record.state, event.kind))
    if rule is None:
        _reject("run", record.state.value, event.kind.value, "illegal transition")
    if rule.guard and not context.guard(rule.guard):
        _reject("run", record.state.value, event.kind.value, rule.guard)
    if event.kind is RunEventType.STOP:
        if not context.capabilities.supports_stop:
            _reject(
                "run",
                record.state.value,
                event.kind.value,
                "supports_stop",
            )
        if not context.stop_authorized:
            _reject(
                "run",
                record.state.value,
                event.kind.value,
                "stop_authorized",
            )
    _require_run_payload(record, event)

    spec = event.new_spec or record.spec
    process_identity = record.process_identity
    exit_code = record.exit_code
    stop_requested = record.stop_requested
    error = record.error

    if event.kind is RunEventType.EDIT:
        process_identity = None
        exit_code = None
        stop_requested = False
        error = None
    elif event.kind is RunEventType.PROCESS_STARTED:
        process_identity = event.process_identity
        error = None
    elif event.kind is RunEventType.STOP:
        stop_requested = True
    elif event.kind in {
        RunEventType.VALIDATION_FAILED,
        RunEventType.START_FAILED,
        RunEventType.CONTROL_FAILED,
        RunEventType.STOP_FAILED,
    }:
        error = event.error or event.kind.value
    elif event.kind in {
        RunEventType.PROCESS_EXITED_ZERO,
        RunEventType.PROCESS_COMPLETED_BEFORE_STOP,
    }:
        exit_code = 0
        error = None
    elif event.kind is RunEventType.PROCESS_EXITED_NONZERO:
        exit_code = event.exit_code
        error = event.error or f"Observer exited with code {event.exit_code}"
    elif event.kind is RunEventType.PROCESS_EXITED_AFTER_STOP:
        exit_code = event.exit_code
        error = None

    return replace(
        record,
        spec=spec,
        state=rule.target,
        process_identity=process_identity,
        exit_code=exit_code,
        stop_requested=stop_requested,
        error=error,
        revision=record.revision + 1,
    )


def _telemetry_identity_matches(
    record: TelemetryRecord,
    event: TelemetryEvent,
) -> bool:
    return bool(record.run_id and event.run_id == record.run_id)


def _validated_tick(record: TelemetryRecord, event: TelemetryEvent) -> int | None:
    if event.tick is None:
        return record.last_tick
    if event.tick < 0:
        _reject(
            "telemetry",
            record.state.value,
            event.kind.value,
            "tick cannot be negative",
        )
    if record.last_tick is not None and event.tick < record.last_tick:
        _reject(
            "telemetry",
            record.state.value,
            event.kind.value,
            "tick regression",
        )
    return event.tick


def reduce_telemetry(
    record: TelemetryRecord,
    event: TelemetryEvent,
) -> TelemetryRecord:
    rule = TELEMETRY_TRANSITIONS.get((record.state, event.kind))
    if rule is None:
        _reject(
            "telemetry",
            record.state.value,
            event.kind.value,
            "illegal transition",
        )
    if event.kind is TelemetryEventType.CONNECT:
        run_id = str(event.run_id or "").strip()
        if not run_id:
            _reject(
                "telemetry",
                record.state.value,
                event.kind.value,
                "run_id is required",
            )
    else:
        run_id = record.run_id
    if rule.guard == "run_identity_matches" and not _telemetry_identity_matches(
        record, event
    ):
        _reject(
            "telemetry",
            record.state.value,
            event.kind.value,
            rule.guard,
        )

    last_tick = _validated_tick(record, event)
    error = event.error if rule.target is TelemetryState.ERROR else None
    if event.kind is TelemetryEventType.CONNECT:
        last_tick = None
    return replace(
        record,
        state=rule.target,
        run_id=run_id,
        last_tick=last_tick,
        error=error,
        revision=record.revision + 1,
    )


def accept_telemetry_sample(
    record: TelemetryRecord,
    *,
    run_id: str,
    tick: int,
) -> TelemetryRecord:
    """Accept a fresh sample without inventing a LIVE-to-LIVE transition."""
    if record.state is not TelemetryState.LIVE:
        _reject(
            "telemetry",
            record.state.value,
            "SAMPLE",
            "samples require LIVE telemetry",
        )
    event = TelemetryEvent(
        TelemetryEventType.SOURCE_VERIFIED,
        run_id=run_id,
        tick=tick,
    )
    if not _telemetry_identity_matches(record, event):
        _reject(
            "telemetry",
            record.state.value,
            "SAMPLE",
            "run_identity_matches",
        )
    last_tick = _validated_tick(record, event)
    return replace(
        record,
        last_tick=last_tick,
        error=None,
        revision=record.revision + 1,
    )
