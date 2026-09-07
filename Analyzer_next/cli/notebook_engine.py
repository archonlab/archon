#!/usr/bin/env python3
"""Compatibility CLI for modular Research Notebook Engine v4."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from pprint import pprint
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.research_notebook.contracts import ResearchNotebookPaths
from Analyzer_next.core.research_notebook.notebooks import build_notebook
from Analyzer_next.engines.research_notebook_engine import ResearchNotebookEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one research notebook per analyzed rule."
    )
    parser.add_argument(
        "results_folder",
        nargs="?",
        help="Universe Search results folder",
    )
    parser.add_argument(
        "--analysis-root",
        default=None,
        help="Analysis output folder",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.results_folder:
        pprint(build_notebook(generated_date=datetime.now().strftime("%Y-%m-%d")))
        return 0
    results_folder = Path(args.results_folder)
    analysis_root = (
        Path(args.analysis_root)
        if args.analysis_root
        else results_folder.parent / "Analysis"
    )
    saved = ResearchNotebookEngine().run(
        ResearchNotebookPaths(
            results_folder=results_folder,
            analysis_root=analysis_root,
        )
    )
    print("")
    print("=" * 64)
    print("Universe Search Research Notebook Engine v4 Batch")
    print("=" * 64)
    print(f"Source:      {saved.source_path}")
    print(f"Rules:       {len(saved.outputs)}")
    print(f"Output dir:  {results_folder / 'ResearchNotebook'}")
    print(f"Manifest:    {saved.manifest_path}")
    for artifact in saved.outputs:
        notebook = artifact.notebook
        print(
            f"Rule {notebook['experiment'].get('rule')}: "
            f"{notebook['confidence'].get('level')} -> {artifact.path.name}"
        )
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
