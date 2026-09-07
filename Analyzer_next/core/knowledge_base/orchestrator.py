"""Pure Knowledge Base orchestration."""
from __future__ import annotations

from .builder import build_knowledge_base
from .contracts import (
    KnowledgeBaseInputs,
    KnowledgeBasePaths,
    KnowledgeBaseRunResult,
)
from .integrity import validate_integrity
from .registries import preserve_generated_if_unchanged
from .reporting import render_markdown


class KnowledgeBaseOrchestrator:
    def run(
        self,
        paths: KnowledgeBasePaths,
        inputs: KnowledgeBaseInputs,
    ) -> KnowledgeBaseRunResult:
        knowledge_base = preserve_generated_if_unchanged(
            inputs.previous_knowledge_base,
            build_knowledge_base(
                inputs.scientific_data,
                paths,
                inputs.aliases,
                inputs.predictions,
                inputs.validations,
            ),
        )
        integrity = preserve_generated_if_unchanged(
            inputs.previous_integrity,
            validate_integrity(knowledge_base),
        )
        return KnowledgeBaseRunResult(
            knowledge_base=knowledge_base,
            integrity=integrity,
            report_markdown=render_markdown(knowledge_base, integrity),
        )
