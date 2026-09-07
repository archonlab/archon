"""Composition root for the modular Mechanism Engine."""
from __future__ import annotations

from Analyzer_next.adapters.mechanism.file_repository import (
    FileMechanismRepository,
)
from Analyzer_next.core.mechanism.contracts import (
    MechanismPaths,
    MechanismRepository,
    MechanismRunResult,
)
from Analyzer_next.core.mechanism.orchestrator import MechanismOrchestrator


class MechanismEngine:
    def __init__(
        self,
        repository: MechanismRepository | None = None,
        orchestrator: MechanismOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileMechanismRepository()
        self._orchestrator = orchestrator or MechanismOrchestrator()

    def run(
        self,
        paths: MechanismPaths,
        *,
        selected_rule: str | None = None,
    ) -> MechanismRunResult:
        inputs = self._repository.load(
            paths,
            selected_rule=selected_rule,
        )
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result
