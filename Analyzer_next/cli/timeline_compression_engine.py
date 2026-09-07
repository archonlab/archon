#!/usr/bin/env python3
"""Compatibility CLI for Timeline Compression Engine v1.0."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.timeline_compression.contracts import (
    TimelineCompressionPaths,
    TimelineCompressionRunResult,
)
from Analyzer_next.engines.timeline_compression_engine import (
    TimelineCompressionEngine,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compress overlapping mechanism timeline windows."
    )
    parser.add_argument(
        "results_folder",
        help="Universe Search results folder.",
    )
    return parser.parse_args(argv)


def print_result(
    paths: TimelineCompressionPaths,
    result: TimelineCompressionRunResult,
) -> None:
    results_dir = paths.results_root
    summary = result.compression["global_summary"]
    print("Timeline Compression Engine v1.0")
    print("=" * 64)
    print(f"Results: {results_dir}")
    print(f"Raw timeline events: {summary['raw_timeline_event_count']}")
    print(
        "Canonical events: "
        f"{summary['compressed_timeline_event_count']}"
    )
    print(f"Compressed away: {summary['compressed_away_count']}")
    print(
        "Compression ratio: "
        f"{summary['global_compression_ratio']:.3f}"
    )
    print(f"Segments: {summary['segment_count']}")
    for name in (
        "compressed_timeline.json",
        "compressed_timeline.md",
        "compressed_transitions.json",
        "compressed_transitions.md",
        "timeline_segments.json",
        "timeline_segments.md",
        "timeline_compression_report.json",
        "timeline_compression_report.md",
    ):
        print(f"Wrote: {results_dir / name}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_dir = Path(args.results_folder).expanduser().resolve()
    if not results_dir.exists():
        print(f"[ERROR] Results folder does not exist: {results_dir}")
        return 1
    paths = TimelineCompressionPaths(results_root=results_dir)
    result = TimelineCompressionEngine().run(paths)
    print_result(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
