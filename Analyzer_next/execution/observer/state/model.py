"""Immutable Observer Launcher 2.0 state and run specification models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Iterable, Mapping


class LauncherState(str, Enum):
    BOOTSTRAPPING = "BOOTSTRAPPING"
    READY = "READY"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    CLOSED = "CLOSED"
    FAULTED = "FAULTED"


class RunState(str, Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    INVALID = "INVALID"
    READY = "READY"
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TelemetryState(str, Enum):
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    LIVE = "LIVE"
    STALE = "STALE"
    ERROR = "ERROR"
    CLOSED = "CLOSED"


TERMINAL_RUN_STATES = frozenset({
    RunState.COMPLETED,
    RunState.FAILED,
    RunState.CANCELLED,
})

ACTIVE_RUN_STATES = frozenset({
    RunState.STARTING,
    RunState.RUNNING,
    RunState.PAUSING,
    RunState.PAUSED,
    RunState.RESUMING,
    RunState.STOPPING,
})


def _canonical_json(value: Mapping[str, Any] | None) -> str:
    return json.dumps(
        dict(value or {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class ControlCapabilities:
    """Capabilities acknowledged by the active Observer control adapter."""

    supports_stop: bool = True
    supports_pause: bool = False
    supports_resume: bool = False

    def __post_init__(self) -> None:
        if self.supports_resume and not self.supports_pause:
            raise ValueError("resume capability requires pause capability")


@dataclass(frozen=True, slots=True)
class RunSpec:
    """Reviewed, immutable and deterministically hashable Observer run input."""

    rule_id: int
    mode: str
    max_ticks: int
    sample_every: int
    pressure_every: int
    output_dir: str
    outputs: tuple[str, ...] = ()
    field_width: int = 96
    field_height: int = 64
    topology: str = "torus"
    boundary_mode: str = "wrap"
    seed: int | None = None
    experimental_context_json: str = "{}"

    def __post_init__(self) -> None:
        if isinstance(self.rule_id, bool) or self.rule_id < 0:
            raise ValueError("rule_id must be a non-negative integer")
        if not self.mode.strip():
            raise ValueError("mode is required")
        if self.max_ticks < 0:
            raise ValueError("max_ticks cannot be negative")
        if self.sample_every < 1 or self.pressure_every < 1:
            raise ValueError("telemetry intervals must be positive")
        if self.field_width < 1 or self.field_height < 1:
            raise ValueError("field dimensions must be positive")
        if self.topology not in {"torus", "bounded"}:
            raise ValueError(f"unsupported topology: {self.topology}")
        if self.boundary_mode not in {
            "wrap",
            "fixed_dead",
            "fixed_alive",
            "reflective",
        }:
            raise ValueError(f"unsupported boundary mode: {self.boundary_mode}")
        if self.seed is not None and self.seed < 0:
            raise ValueError("seed cannot be negative")
        if not self.output_dir.strip():
            raise ValueError("output_dir is required")
        if tuple(sorted(set(self.outputs))) != self.outputs:
            raise ValueError("outputs must be a sorted unique tuple")
        try:
            context = json.loads(self.experimental_context_json)
        except json.JSONDecodeError as exc:
            raise ValueError("experimental_context_json is invalid") from exc
        if not isinstance(context, dict):
            raise ValueError("experimental_context_json must encode an object")
        if _canonical_json(context) != self.experimental_context_json:
            raise ValueError("experimental_context_json must be canonical")

    @classmethod
    def create(
        cls,
        *,
        rule_id: int,
        mode: str,
        max_ticks: int,
        sample_every: int,
        pressure_every: int,
        output_dir: str,
        outputs: Iterable[str] = (),
        field_width: int = 96,
        field_height: int = 64,
        topology: str = "torus",
        boundary_mode: str = "wrap",
        seed: int | None = None,
        experimental_context: Mapping[str, Any] | None = None,
    ) -> "RunSpec":
        return cls(
            rule_id=int(rule_id),
            mode=str(mode),
            max_ticks=int(max_ticks),
            sample_every=int(sample_every),
            pressure_every=int(pressure_every),
            output_dir=str(output_dir),
            outputs=tuple(sorted({str(item) for item in outputs})),
            field_width=int(field_width),
            field_height=int(field_height),
            topology=str(topology),
            boundary_mode=str(boundary_mode),
            seed=int(seed) if seed is not None else None,
            experimental_context_json=_canonical_json(experimental_context),
        )

    @property
    def experimental_context(self) -> dict[str, Any]:
        """Return a detached copy so callers cannot mutate this specification."""
        return json.loads(self.experimental_context_json)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "boundary_mode": self.boundary_mode,
            "experimental_context": self.experimental_context,
            "field_height": self.field_height,
            "field_width": self.field_width,
            "max_ticks": self.max_ticks,
            "mode": self.mode,
            "output_dir": self.output_dir,
            "outputs": list(self.outputs),
            "pressure_every": self.pressure_every,
            "rule_id": self.rule_id,
            "sample_every": self.sample_every,
            "seed": self.seed,
            "topology": self.topology,
        }

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class LauncherRecord:
    state: LauncherState = LauncherState.BOOTSTRAPPING
    error: str | None = None
    revision: int = 0

    def __post_init__(self) -> None:
        if self.revision < 0:
            raise ValueError("revision cannot be negative")


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    spec: RunSpec
    state: RunState = RunState.DRAFT
    parent_run_id: str | None = None
    process_identity: str | None = None
    exit_code: int | None = None
    stop_requested: bool = False
    error: str | None = None
    revision: int = 0

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if self.parent_run_id == self.run_id:
            raise ValueError("a run cannot be its own parent")
        if self.revision < 0:
            raise ValueError("revision cannot be negative")
        if self.state in {
            RunState.RUNNING,
            RunState.PAUSING,
            RunState.PAUSED,
            RunState.RESUMING,
        } and not self.process_identity:
            raise ValueError(f"{self.state.value} requires process identity")


@dataclass(frozen=True, slots=True)
class TelemetryRecord:
    state: TelemetryState = TelemetryState.OFFLINE
    run_id: str | None = None
    last_tick: int | None = None
    error: str | None = None
    revision: int = 0

    def __post_init__(self) -> None:
        if self.state is not TelemetryState.OFFLINE and not self.run_id:
            raise ValueError(f"{self.state.value} requires run_id")
        if self.last_tick is not None and self.last_tick < 0:
            raise ValueError("last_tick cannot be negative")
        if self.revision < 0:
            raise ValueError("revision cannot be negative")


@dataclass(frozen=True, slots=True)
class LauncherTransitionContext:
    active_run_resolved: bool = False


@dataclass(frozen=True, slots=True)
class RunTransitionContext:
    world_and_configuration_present: bool = False
    scientific_and_authorization_checks_pass: bool = False
    runspec_committed: bool = False
    launcher_ready: bool = False
    queue_head: bool = False
    no_active_process: bool = False
    process_identity_matches: bool = False
    stop_authorized: bool = False
    capabilities: ControlCapabilities = field(
        default_factory=ControlCapabilities
    )

    @classmethod
    def permissive(
        cls,
        *,
        capabilities: ControlCapabilities | None = None,
    ) -> "RunTransitionContext":
        return cls(
            world_and_configuration_present=True,
            scientific_and_authorization_checks_pass=True,
            runspec_committed=True,
            launcher_ready=True,
            queue_head=True,
            no_active_process=True,
            process_identity_matches=True,
            stop_authorized=True,
            capabilities=(
                capabilities
                or ControlCapabilities(
                    supports_stop=True,
                    supports_pause=True,
                    supports_resume=True,
                )
            ),
        )

    def guard(self, name: str) -> bool:
        values = {
            "world_and_configuration_present": (
                self.world_and_configuration_present
            ),
            "scientific_and_authorization_checks_pass": (
                self.scientific_and_authorization_checks_pass
            ),
            "runspec_committed": self.runspec_committed,
            "launcher_ready_queue_head_no_active_process": (
                self.launcher_ready
                and self.queue_head
                and self.no_active_process
            ),
            "process_identity_matches": self.process_identity_matches,
            "supports_pause": self.capabilities.supports_pause,
            "supports_resume": self.capabilities.supports_resume,
        }
        try:
            return bool(values[name])
        except KeyError as exc:
            raise ValueError(f"unknown run transition guard: {name}") from exc


class TransitionRejected(ValueError):
    """A structured fail-closed state-machine rejection."""

    def __init__(
        self,
        *,
        machine: str,
        state: str,
        event: str,
        reason: str,
    ) -> None:
        self.machine = machine
        self.state = state
        self.event = event
        self.reason = reason
        super().__init__(
            f"{machine} rejected {event} from {state}: {reason}"
        )
