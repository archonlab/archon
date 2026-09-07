"""Composition root for the modular composition-template builder."""
from __future__ import annotations

from Analyzer_next.adapters.composition_templates.file_repository import (
    FileCompositionTemplateRepository,
)
from Analyzer_next.core.composition_templates.contracts import (
    CompositionTemplatePaths,
    CompositionTemplateRepository,
    CompositionTemplateRunResult,
)
from Analyzer_next.core.composition_templates.orchestrator import (
    CompositionTemplateOrchestrator,
)


class CompositionTemplateBuilder:
    def __init__(
        self,
        repository: CompositionTemplateRepository | None = None,
        orchestrator: CompositionTemplateOrchestrator | None = None,
    ) -> None:
        self._repository = repository or FileCompositionTemplateRepository()
        self._orchestrator = orchestrator or CompositionTemplateOrchestrator()

    def run(
        self,
        paths: CompositionTemplatePaths,
    ) -> CompositionTemplateRunResult:
        inputs = self._repository.load(paths)
        result = self._orchestrator.run(paths, inputs)
        self._repository.save(paths, result)
        return result
