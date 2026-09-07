#!/usr/bin/env python3
"""Compatibility CLI for the modular ARCHON Morphology Analyzer."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.morphology.contracts import MorphologyPaths, MorphologyRunResult
from Analyzer_next.engines.morphology_engine import MorphologyEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze and compare Universe Search Observer morphology samples."
    )
    parser.add_argument("results_folder", help="Universe Search results folder.")
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of similar/different worlds to list.",
    )
    return parser.parse_args(argv)


def print_summary(paths: MorphologyPaths, result: MorphologyRunResult) -> None:
    report = result.report
    comparison = result.comparison
    print("Morphology Analyzer v2.3")
    print("=" * 64)
    print(f"Results: {paths.results_dir}")
    print(f"CSV files found: {report['csv_files_found']}")
    print(f"Rules with morphology: {report['rules_with_morphology']}")
    print(f"Rules compared: {comparison['rule_count']}")
    for name in result.artifacts:
        print(f"Wrote: {paths.results_dir / name}")
    if report.get("errors"):
        print(f"Warnings/errors: {len(report['errors'])}")


def main(argv: list[str] | None = None) -> int:
    try:
        os.nice(int(os.environ.get("ARCHON_ANALYZER_NICE", "8")))
    except (AttributeError, OSError, ValueError):
        pass
    args = parse_args(argv)
    results_dir = Path(args.results_folder).expanduser().resolve()
    if not results_dir.exists():
        print(f"[ERROR] Results folder does not exist: {results_dir}")
        return 1
    paths = MorphologyPaths(results_dir=results_dir)
    result = MorphologyEngine().run(paths, top_n=max(1, args.top_n))
    print_summary(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
