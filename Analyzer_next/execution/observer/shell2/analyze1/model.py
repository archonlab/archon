"""Pure state and immutable launch contract for OL2-ANALYZE1."""
from __future__ import annotations

from Tools.archon_runtime_python import runtime_python_command

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
from pathlib import Path


class AnalysisState(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class AnalysisEventType(str, Enum):
    START_REQUEST = "START_REQUEST"
    START_ACK = "START_ACK"
    START_FAILED = "START_FAILED"
    STOP_REQUEST = "STOP_REQUEST"
    STOP_FAILED = "STOP_FAILED"
    PROCESS_EXIT = "PROCESS_EXIT"


@dataclass(frozen=True, slots=True)
class AnalysisEvent:
    kind: AnalysisEventType
    exit_code: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    state: AnalysisState
    attempt: int = 0
    exit_code: int | None = None
    error: str | None = None

    @property
    def active(self) -> bool:
        return self.state in {
            AnalysisState.STARTING,
            AnalysisState.RUNNING,
            AnalysisState.STOPPING,
        }


@dataclass(frozen=True, slots=True)
class AnalysisLaunchPlan:
    project_root: Path
    launcher: Path
    analyzer_entrypoint: Path
    command: tuple[str, ...]
    launcher_sha256: str

    @classmethod
    def create(cls, project_root: Path) -> "AnalysisLaunchPlan":
        root = Path(project_root).resolve()
        launcher = root / "ANALYZER.sh"
        entrypoint = root / "Analyzer_next" / "cli" / "analyze_results.py"
        if launcher.is_symlink() or not launcher.is_file():
            raise ValueError(f"canonical Analyzer launcher is unavailable: {launcher}")
        if entrypoint.is_symlink() or not entrypoint.is_file():
            raise ValueError(f"modular Analyzer entrypoint is unavailable: {entrypoint}")
        if launcher.resolve().parent != root:
            raise ValueError("Analyzer launcher escapes the project root")
        digest = hashlib.sha256(launcher.read_bytes()).hexdigest()
        return cls(
            project_root=root,
            launcher=launcher,
            analyzer_entrypoint=entrypoint,
            command=(*runtime_python_command(root), str(entrypoint)),
            launcher_sha256=digest,
        )


def initial_analysis_record() -> AnalysisRecord:
    return AnalysisRecord(state=AnalysisState.IDLE)


def reduce_analysis(record: AnalysisRecord, event: AnalysisEvent) -> AnalysisRecord:
    """Apply one fail-closed transition; unexpected events are rejected."""

    state = record.state
    if event.kind is AnalysisEventType.START_REQUEST:
        if state not in {
            AnalysisState.IDLE,
            AnalysisState.SUCCEEDED,
            AnalysisState.FAILED,
            AnalysisState.STOPPED,
        }:
            raise ValueError(f"cannot start Analyzer from {state.value}")
        return AnalysisRecord(
            state=AnalysisState.STARTING,
            attempt=record.attempt + 1,
        )
    if event.kind is AnalysisEventType.START_ACK:
        if state is not AnalysisState.STARTING:
            raise ValueError(f"cannot acknowledge Analyzer start from {state.value}")
        return replace(record, state=AnalysisState.RUNNING)
    if event.kind is AnalysisEventType.START_FAILED:
        if state is not AnalysisState.STARTING:
            raise ValueError(f"cannot fail Analyzer start from {state.value}")
        if not event.error:
            raise ValueError("Analyzer start failure requires an error")
        return replace(record, state=AnalysisState.FAILED, error=event.error)
    if event.kind is AnalysisEventType.STOP_REQUEST:
        if state not in {AnalysisState.STARTING, AnalysisState.RUNNING}:
            raise ValueError(f"cannot stop Analyzer from {state.value}")
        return replace(record, state=AnalysisState.STOPPING)
    if event.kind is AnalysisEventType.STOP_FAILED:
        if state is not AnalysisState.STOPPING:
            raise ValueError(f"cannot reject Analyzer stop from {state.value}")
        if not event.error:
            raise ValueError("Analyzer stop failure requires an error")
        return replace(record, state=AnalysisState.RUNNING, error=event.error)
    if event.kind is AnalysisEventType.PROCESS_EXIT:
        if state not in {AnalysisState.RUNNING, AnalysisState.STOPPING}:
            raise ValueError(f"unexpected Analyzer exit from {state.value}")
        if event.exit_code is None:
            raise ValueError("Analyzer exit requires an exit code")
        if state is AnalysisState.STOPPING:
            final = AnalysisState.STOPPED
        else:
            final = AnalysisState.SUCCEEDED if event.exit_code == 0 else AnalysisState.FAILED
        return replace(
            record,
            state=final,
            exit_code=event.exit_code,
            error=event.error,
        )
    raise ValueError(f"unsupported Analyzer event: {event.kind.value}")
