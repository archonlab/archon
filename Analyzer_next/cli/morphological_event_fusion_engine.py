#!/usr/bin/env python3
"""Compatibility CLI for modular morphological event fusion."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.fusion.contracts import FusionPaths, FusionRunResult
from Analyzer_next.engines.fusion_engine import FusionEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fuse raw morphology events into macro-events."
    )
    parser.add_argument("results_folder", help="Universe Search results folder.")
    return parser.parse_args(argv)


def print_summary(paths: FusionPaths, result: FusionRunResult) -> None:
    print("Morphological Event Fusion Engine v1.0")
    print("=" * 64)
    print(f"Results: {paths.results_dir}")
    print(f"Rules analyzed: {result.report['rules_analyzed']}")
    for name in result.artifacts:
        print(f"Wrote: {paths.results_dir / name}")


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
    paths = FusionPaths(results_dir=results_dir)
    result = FusionEngine().run(paths)
    print_summary(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

