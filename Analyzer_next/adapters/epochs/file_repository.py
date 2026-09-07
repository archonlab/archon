"""Filesystem source and artifact sink implementing epoch ports."""
from __future__ import annotations

import time
from pathlib import Path

from Analyzer_next.adapters.morphology.incremental_cache import (
    find_cached_csvs,
    load_cached_rows,
    load_incremental_collection,
)
from Analyzer_next.core.epochs.contracts import (
    EpochInputs,
    EpochPaths,
    EpochProducer,
    EpochRunResult,
)


class FileEpochSource:
    def collect(self, paths: EpochPaths, producer: EpochProducer) -> EpochInputs:
        csvs = find_cached_csvs(
            paths.results_dir,
            required=("tick",),
            required_any=("morphology_class", "morphology_change_rate"),
        )
        started = time.perf_counter()

        def analyze(path: Path):
            return producer(path, load_cached_rows(path))

        errors: list[dict[str, str]] = []
        summaries = []
        incremental = {"new": 0, "changed": 0, "reused": 0, "removed": 0}
        try:
            summaries, incremental = load_incremental_collection(
                csvs,
                namespace="morphological_epoch_detector",
                producer=analyze,
                analysis_version=1,
            )
        except Exception as exc:
            errors.append({
                "source_csv": "<incremental_collection>",
                "error": repr(exc),
            })
        return EpochInputs(
            summaries=summaries,
            csv_files_found=len(csvs),
            incremental=incremental,
            errors=errors,
            elapsed_seconds=time.perf_counter() - started,
        )


class FileEpochArtifactRepository:
    def save(self, paths: EpochPaths, result: EpochRunResult) -> None:
        paths.results_dir.mkdir(parents=True, exist_ok=True)
        for name, content in result.artifacts.items():
            (paths.results_dir / name).write_text(content, encoding="utf-8")

