#!/usr/bin/env python3
"""Compatibility CLI for the modular ARCHON Mutation Analyzer."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.mutation.contracts import MutationRequest
from Analyzer_next.engines.mutation_engine import MutationEngine


def parse_args(argv: list[str] | None = None) -> MutationRequest:
    parser = argparse.ArgumentParser(
        description="Compare Observer mutation runs with their canonical originals."
    )
    parser.add_argument(
        "results_folder",
        nargs="?",
        default="Results/Universe_Search",
        help="Universe Search results root.",
    )
    parser.add_argument("--mutation-root", default=None, help="Override mutation_runs directory.")
    parser.add_argument("--out-dir", default=None, help="Override Results/Analysis/Mutations output.")
    parser.add_argument("--rule", default=None, help="Analyze mutations for one canonical rule.")
    parser.add_argument("--mutation-id", default=None, help="Analyze one mutation ID.")
    parser.add_argument(
        "--allow-missing-root",
        action="store_true",
        help=(
            "Treat an absent mutation_runs directory as an empty mutation "
            "channel. Intended for full Analyzer refreshes where a canonical "
            "Observer run may contain no mutation experiments."
        ),
    )
    parser.add_argument(
        "--force-recompute",
        action="store_true",
        help="Recompute selected mutation reports even when their inputs are current.",
    )
    args = parser.parse_args(argv)
    return MutationRequest(
        results_folder=args.results_folder,
        mutation_root=args.mutation_root,
        out_dir=args.out_dir,
        rule=args.rule,
        mutation_id=args.mutation_id,
        allow_missing_root=bool(args.allow_missing_root),
        force_recompute=bool(args.force_recompute),
    )


def main(argv: list[str] | None = None) -> int:
    return MutationEngine().run(parse_args(argv)).exit_code


if __name__ == "__main__":
    raise SystemExit(main())

