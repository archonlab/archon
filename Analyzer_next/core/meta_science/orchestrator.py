"""Pure orchestration of snapshot, history, growth, and reporting."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from Analyzer_next.core.meta_science.contracts import (
    MetaScienceInputs,
    MetaSciencePaths,
    MetaScienceRunResult,
)
from Analyzer_next.core.meta_science.history import compute_growth, update_history
from Analyzer_next.core.meta_science.reporting import render_markdown
from Analyzer_next.core.meta_science.snapshot import build_snapshot


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class MetaScienceOrchestrator:
    def __init__(self, clock: Callable[[], str] = now_iso) -> None:
        self._clock = clock

    def run(
        self,
        paths: MetaSciencePaths,
        inputs: MetaScienceInputs,
    ) -> MetaScienceRunResult:
        timestamp = self._clock()
        report = build_snapshot(paths, inputs, timestamp)
        history = update_history(inputs.history, report, timestamp)
        report["knowledge_growth"] = compute_growth(report, history)
        return MetaScienceRunResult(
            report=report,
            history=history,
            report_markdown=render_markdown(report),
        )
