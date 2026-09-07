"""EXPERIMENTS-FIX7 command service for canonical experiment telemetry identity.

Experiment runtime rows keep their per-row file output directory, but their
SQLite telemetry must remain the canonical experimental-conditions database.
The legacy Observer resolves experiment_id/condition_id before starting the
simulation, so pointing SQLite at the per-row directory creates an empty DB and
fails before the first presentation/telemetry identity is emitted.
"""
from __future__ import annotations

from pathlib import Path

from Analyzer_next.execution.observer.shell2.config1.command_service import ObserverCommandService
from Analyzer_next.execution.observer.shell2.config1.model import ConfigurationDraft


class ExperimentObserverCommandServiceFix7(ObserverCommandService):
    """Route experimental SQLite to canonical telemetry, files to row output."""

    def __init__(self, project_root: Path, **kwargs) -> None:
        self.project_root = Path(project_root).resolve()
        self.canonical_telemetry_db = (
            self.project_root / "Results" / "Universe_Search" / "observation_logs" / "telemetry.sqlite"
        ).resolve()
        kwargs.setdefault(
            "default_output_dir",
            self.project_root / "Results" / "Universe_Search" / "observation_logs",
        )
        super().__init__(**kwargs)

    def _command(self, draft: ConfigurationDraft, context):
        command = list(super()._command(draft, context))
        if context is None:
            return tuple(command)
        # The experimental contract forces SQLite on.  Bind that SQLite channel
        # explicitly to the canonical DB even when --run-output-dir points at a
        # dedicated runtime-row directory.
        if "--telemetry-db" in command:
            index = command.index("--telemetry-db")
            if index + 1 >= len(command):
                raise ValueError("malformed --telemetry-db command")
            command[index + 1] = str(self.canonical_telemetry_db)
        else:
            command.extend(["--telemetry-db", str(self.canonical_telemetry_db)])
        return tuple(command)


__all__ = ["ExperimentObserverCommandServiceFix7"]
