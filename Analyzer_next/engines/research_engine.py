"""Stable facade for the modular Research Director."""
from __future__ import annotations

from pathlib import Path

from Analyzer_next.research.director.service import run_director


class ResearchDirectorEngine:
    """Execute one complete Director evaluation and governance pass."""

    def run(
        self,
        results_dir: Path,
        analysis_root: Path,
        knowledge_root: Path,
    ) -> int:
        return run_director(
            results_dir.resolve(),
            analysis_root.resolve(),
            knowledge_root.resolve(),
        )


__all__ = ["ResearchDirectorEngine"]

