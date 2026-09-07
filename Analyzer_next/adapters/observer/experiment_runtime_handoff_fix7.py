"""EXPERIMENTS-FIX7 authorized runtime handoff with canonical experiment SQLite."""
from __future__ import annotations

from pathlib import Path

from Analyzer_next.adapters.observer.experiment_runtime_command_fix7 import ExperimentObserverCommandServiceFix7
from Analyzer_next.adapters.observer.experiment_runtime_handoff_fix6 import AuditedExperimentRuntimeHandoffFix6


class AuditedExperimentRuntimeHandoffFix7(AuditedExperimentRuntimeHandoffFix6):
    def __init__(self, project_root: Path, *args, command_service=None, **kwargs) -> None:
        root = Path(project_root).resolve()
        if command_service is None:
            command_service = ExperimentObserverCommandServiceFix7(root)
        super().__init__(root, *args, command_service=command_service, **kwargs)


__all__ = ["AuditedExperimentRuntimeHandoffFix7"]
