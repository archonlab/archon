"""Pure assembly of morphology report, comparison, and rendered artifacts."""
from __future__ import annotations

from Analyzer_next.core.morphology.comparison import build_comparison
from Analyzer_next.core.morphology.contracts import (
    MorphologyInputs,
    MorphologyPaths,
    MorphologyRunResult,
)
from Analyzer_next.core.morphology.reporting import render_artifacts
from Analyzer_next.core.morphology.summarization import build_report


class MorphologyOrchestrator:
    def run(
        self,
        paths: MorphologyPaths,
        inputs: MorphologyInputs,
        *,
        top_n: int = 5,
    ) -> MorphologyRunResult:
        report = build_report(
            paths.results_dir,
            inputs.summaries,
            inputs.csv_files_found,
        )
        comparison = build_comparison(report, top_n=max(1, top_n))
        return MorphologyRunResult(
            report=report,
            comparison=comparison,
            artifacts=render_artifacts(report, comparison),
            incremental=dict(inputs.incremental),
            elapsed_seconds=inputs.elapsed_seconds,
        )
