"""Typed events for the pure Observer Launcher 2.0 reducers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .model import RunSpec


class LauncherEventType(str, Enum):
    BOOT_OK = "BOOT_OK"
    BOOT_FAILED = "BOOT_FAILED"
    CLOSE_REQUESTED = "CLOSE_REQUESTED"
    CLOSE_CONFIRMED = "CLOSE_CONFIRMED"
    INFRASTRUCTURE_FAILED = "INFRASTRUCTURE_FAILED"
    RECOVERED = "RECOVERED"


class RunEventType(str, Enum):
    VALIDATE = "VALIDATE"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    EDIT = "EDIT"
    QUEUE = "QUEUE"
    START = "START"
    CANCEL = "CANCEL"
    PROCESS_STARTED = "PROCESS_STARTED"
    START_FAILED = "START_FAILED"
    STOP = "STOP"
    PAUSE = "PAUSE"
    PAUSE_ACK = "PAUSE_ACK"
    CONTROL_FAILED = "CONTROL_FAILED"
    RESUME = "RESUME"
    RESUME_ACK = "RESUME_ACK"
    PROCESS_EXITED_ZERO = "PROCESS_EXITED_ZERO"
    PROCESS_EXITED_NONZERO = "PROCESS_EXITED_NONZERO"
    PROCESS_EXITED_AFTER_STOP = "PROCESS_EXITED_AFTER_STOP"
    PROCESS_COMPLETED_BEFORE_STOP = "PROCESS_COMPLETED_BEFORE_STOP"
    STOP_FAILED = "STOP_FAILED"
    CLONE = "CLONE"


class TelemetryEventType(str, Enum):
    CONNECT = "CONNECT"
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    SOURCE_FAILED = "SOURCE_FAILED"
    FRESHNESS_EXPIRED = "FRESHNESS_EXPIRED"
    SOURCE_CLOSED = "SOURCE_CLOSED"
    READ_FAILED = "READ_FAILED"
    FRESH_UPDATE = "FRESH_UPDATE"
    RECONNECT = "RECONNECT"


@dataclass(frozen=True, slots=True)
class LauncherEvent:
    kind: LauncherEventType
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RunEvent:
    kind: RunEventType
    process_identity: str | None = None
    exit_code: int | None = None
    error: str | None = None
    new_run_id: str | None = None
    new_spec: RunSpec | None = None


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    kind: TelemetryEventType
    run_id: str | None = None
    tick: int | None = None
    error: str | None = None
