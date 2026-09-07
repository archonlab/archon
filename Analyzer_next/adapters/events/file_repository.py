"""Filesystem source and artifact sink implementing event ports."""
from __future__ import annotations

import time
from pathlib import Path

from Analyzer_next.adapters.morphology.incremental_cache import (
    find_cached_csvs,
    load_cached_rows,
    load_incremental_collection,
)
from Analyzer_next.core.events.contracts import (
    EventInputs,
    EventPaths,
    EventProducer,
    EventRunResult,
)


class FileEventSource:
    def collect(self, paths: EventPaths, producer: EventProducer) -> EventInputs:
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
                namespace="morphological_event_detector",
                producer=analyze,
                analysis_version=1,
            )
        except Exception as exc:
            errors.append({
                "source_csv": "<incremental_collection>",
                "error": repr(exc),
            })
        return EventInputs(
            summaries=summaries,
            csv_files_found=len(csvs),
            incremental=incremental,
            errors=errors,
            elapsed_seconds=time.perf_counter() - started,
        )


class FileEventArtifactRepository:
    def save(self, paths: EventPaths, result: EventRunResult) -> None:
        paths.results_dir.mkdir(parents=True, exist_ok=True)
        for name, content in result.artifacts.items():
            (paths.results_dir / name).write_text(content, encoding="utf-8")

