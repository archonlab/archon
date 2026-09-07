"""Compose deterministic composition-template projections in memory."""
from __future__ import annotations

from Analyzer_next.core.composition_templates.contracts import (
    CompositionTemplateInputs,
    CompositionTemplatePaths,
    CompositionTemplateRunResult,
)
from Analyzer_next.core.composition_templates.templates import (
    build_report,
    build_templates,
)


class CompositionTemplateOrchestrator:
    def run(
        self,
        paths: CompositionTemplatePaths,
        inputs: CompositionTemplateInputs,
    ) -> CompositionTemplateRunResult:
        template_registry, instance_registry, template_rule_map = build_templates(
            inputs.mechanism_registry,
            inputs.composition_registry,
            inputs.rule_map,
            paths.results_root,
        )
        report = build_report(
            template_registry,
            instance_registry,
            template_rule_map,
            paths.results_root,
        )
        return CompositionTemplateRunResult(
            template_registry=template_registry,
            instance_registry=instance_registry,
            template_rule_map=template_rule_map,
            report=report,
        )
