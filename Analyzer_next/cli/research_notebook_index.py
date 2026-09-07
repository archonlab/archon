#!/usr/bin/env python3
"""Compatibility CLI for modular Research Notebook Index v1."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.research_notebook_index.file_repository import (
    ResearchNotebookIndexInputError,
)
from Analyzer_next.core.research_notebook_index.contracts import (
    ResearchNotebookIndexPaths,
)
from Analyzer_next.core.research_notebook_index.scoring import research_score
from Analyzer_next.engines.research_notebook_index_engine import (
    ResearchNotebookIndexEngine,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build ResearchNotebook/index.md"
    )
    parser.add_argument("results_folder", help="Universe Search results folder")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_folder = Path(args.results_folder)
    try:
        saved = ResearchNotebookIndexEngine().run(
            ResearchNotebookIndexPaths(results_folder=results_folder)
        )
    except ResearchNotebookIndexInputError as exc:
        print(f"[ERROR] {exc}")
        return 1

    items = saved.artifact.items
    print("")
    print("=" * 64)
    print("Universe Search Research Notebook Index")
    print("=" * 64)
    print(f"Notebook dir:   {saved.notebook_dir}")
    print(f"Experiments:    {len(items)}")
    print(f"Output:         {saved.output_path}")
    print("-" * 64)
    for item in sorted(items, key=research_score, reverse=True):
        print(
            f"Rule {item.rule}: score={research_score(item)} "
            f"class={item.classification}"
        )
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
