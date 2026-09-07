#!/usr/bin/env python3
"""Compatibility CLI for modular Prediction Validation Engine v2.3."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.prediction_validation.contracts import PredictionValidationPaths
from Analyzer_next.engines.prediction_validation_engine import PredictionValidationEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate predictions against current Universe Search Atlas."
    )
    parser.add_argument("atlas", help="Path to research_atlas.json")
    parser.add_argument(
        "--predictions",
        default=None,
        help="Optional predictions.json path",
    )
    parser.add_argument(
        "--out",
        default="validation_report.md",
        help="Output markdown file",
    )
    return parser.parse_args(argv)


def resolve_paths(args: argparse.Namespace) -> PredictionValidationPaths:
    atlas = Path(args.atlas)
    predictions = (
        Path(args.predictions)
        if args.predictions
        else atlas.parent / "predictions.json"
    )
    output_markdown = Path(args.out)
    if not output_markdown.is_absolute():
        output_markdown = atlas.parent / output_markdown
    return PredictionValidationPaths(
        atlas=atlas,
        predictions=predictions,
        output_markdown=output_markdown,
        output_json=output_markdown.with_suffix(".json"),
    )


def print_summary(paths: PredictionValidationPaths, result) -> None:
    print("")
    print("=" * 64)
    print("Universe Search Validation Engine v2.3")
    print("=" * 64)
    print(f"Atlas:        {paths.atlas}")
    print(f"Predictions:  {len(result.results)}")
    print(f"Output MD:    {paths.output_markdown}")
    print(f"Output JSON:  {paths.output_json}")
    print("-" * 64)
    for validation in result.results:
        print(
            f"{validation['id']}: {validation['status_after']} | "
            f"{validation['verdict']}"
        )
    print("=" * 64)


def main(argv: list[str] | None = None) -> int:
    paths = resolve_paths(parse_args(argv))
    if not paths.atlas.exists():
        print(f"[ERROR] Atlas not found: {paths.atlas}")
        return 1
    if not paths.predictions.exists():
        print("[ERROR] No predictions found. Run prediction_engine first.")
        return 1
    result = PredictionValidationEngine().run(paths)
    if not result.results:
        print("[ERROR] No predictions found. Run prediction_engine first.")
        return 1
    print_summary(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
