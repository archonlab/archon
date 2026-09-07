"""Deterministic orchestration for timeline compression."""
from __future__ import annotations

from Analyzer_next.core.timeline_compression.analysis import (
    build_compression,
    build_report,
)
from Analyzer_next.core.timeline_compression.contracts import (
    TimelineCompressionInputs,
    TimelineCompressionPaths,
    TimelineCompressionRunResult,
)


class TimelineCompressionOrchestrator:
    def run(
        self,
        paths: TimelineCompressionPaths,
        inputs: TimelineCompressionInputs,
    ) -> TimelineCompressionRunResult:
        compression = build_compression(
            inputs.mechanism_timeline,
            str(paths.results_root),
        )
        return TimelineCompressionRunResult(
            compression=compression,
            report=build_report(compression),
        )
