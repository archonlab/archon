#!/usr/bin/env python3
"""Compatibility CLI for the modular ARCHON Research Director."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.common.paths import analysis_results_dir, knowledge_atlas_dir
from Analyzer_next.engines.research_engine import ResearchDirectorEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Universe Search Research Director v37.6.4 — modular migration"
        )
    )
    parser.add_argument(
        "results_folder",
        help="Shared Universe Search results folder",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Results/Analysis folder. Default: canonical Results/Analysis",
    )
    parser.add_argument(
        "--knowledge-root",
        default=None,
        help="Persistent Atlas/Knowledge folder",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_folder).resolve()
    root = Path(args.root).resolve() if args.root else analysis_results_dir()
    knowledge_root = (
        Path(args.knowledge_root).resolve()
        if args.knowledge_root
        else knowledge_atlas_dir()
    )
    return ResearchDirectorEngine().run(results_dir, root, knowledge_root)


if __name__ == "__main__":
    raise SystemExit(main())
