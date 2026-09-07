"""Filesystem source and artifact sink implementing morphology ports."""
from __future__ import annotations

import time
from pathlib import Path

from Analyzer_next.adapters.morphology.incremental_cache import (
    find_cached_csvs,
    load_cached_rows,
    load_incremental_collection,
)
from Analyzer_next.core.morphology.constants import MORPH_COLUMNS
from Analyzer_next.core.morphology.contracts import (
    MorphologyInputs,
    MorphologyPaths,
    MorphologyRunResult,
    SummaryProducer,
)


class FileMorphologySource:
    def collect(
        self,
        paths: MorphologyPaths,
        producer: SummaryProducer,
    ) -> MorphologyInputs:
        csvs = find_cached_csvs(
            paths.results_dir,
            required=("tick",),
            required_any=MORPH_COLUMNS,
        )
        started = time.perf_counter()

        def analyze(path: Path):
            return producer(path, load_cached_rows(path))

        summaries, incremental = load_incremental_collection(
            csvs,
            namespace="morphology_analyzer",
            producer=analyze,
            analysis_version=1,
        )
        return MorphologyInputs(
            summaries=summaries,
            csv_files_found=len(csvs),
            incremental=incremental,
            elapsed_seconds=time.perf_counter() - started,
        )


class FileMorphologyArtifactRepository:
    def save(self, paths: MorphologyPaths, result: MorphologyRunResult) -> None:
        paths.results_dir.mkdir(parents=True, exist_ok=True)
        for name, content in result.artifacts.items():
            (paths.results_dir / name).write_text(content, encoding="utf-8")
