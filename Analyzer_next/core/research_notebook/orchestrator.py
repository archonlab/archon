"""Pure coordination of research notebook generation."""
from __future__ import annotations

from .contracts import (
    ResearchNotebookArtifact,
    ResearchNotebookInputs,
    ResearchNotebookRunResult,
)
from .notebooks import build_notebook
from .parsing import parse_passport_analysis
from .reporting import render_markdown


class ResearchNotebookOrchestrator:
    def run(self, inputs: ResearchNotebookInputs) -> ResearchNotebookRunResult:
        artifacts: list[ResearchNotebookArtifact] = []
        for passport in parse_passport_analysis(inputs.passport_text):
            notebook = build_notebook(
                passport,
                generated_date=inputs.generated_date,
            )
            rule = notebook["experiment"].get("rule")
            mechanism_text = inputs.mechanism_reports.get(
                str(rule),
                inputs.fallback_mechanism_text,
            )
            artifacts.append(
                ResearchNotebookArtifact(
                    notebook=notebook,
                    markdown=render_markdown(
                        notebook,
                        results_folder_display=inputs.results_folder_display,
                        questions_text=inputs.questions_text,
                        discoveries_text=inputs.discoveries_text,
                        mechanisms_text=mechanism_text,
                        principles_text=inputs.principles_text,
                        predictions_text=inputs.predictions_text,
                    ),
                )
            )
        return ResearchNotebookRunResult(
            artifacts=tuple(artifacts),
            passport_source_name=inputs.passport_source_name,
        )


__all__ = ["ResearchNotebookOrchestrator"]
