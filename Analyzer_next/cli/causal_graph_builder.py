#!/usr/bin/env python3
"""Compatibility CLI for Causal Graph Builder v1.0 Stage 3."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.causal_graph.contracts import CausalGraphPaths
from Analyzer_next.engines.causal_graph_builder import CausalGraphBuilder


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build causal mechanism families from fused morphology events."
    )
    parser.add_argument(
        "results_folder", help="Universe Search results folder."
    )
    return parser.parse_args(argv)


def print_result(paths: CausalGraphPaths, report: dict[str, object]) -> None:
    results_dir = paths.results_root
    global_motifs = report["global_motifs"]
    hypotheses = report["mechanism_hypotheses"]
    assert isinstance(global_motifs, dict)
    assert isinstance(hypotheses, list)
    print("Causal Graph Builder v1.0 Stage 3")
    print("=" * 64)
    print(f"Results: {results_dir}")
    print(f"Rules analyzed: {report['rules_analyzed']}")
    print(f"Event motifs: {global_motifs['event_motif_count']}")
    print(f"Family motifs: {global_motifs['family_motif_count']}")
    print(f"Mechanism hypotheses: {len(hypotheses)}")
    for name in (
        "causal_graph.json",
        "causal_graph.md",
        "causal_report.json",
        "causal_report.md",
        "causal_motifs.json",
        "causal_motifs.md",
        "causal_mechanisms.json",
        "causal_mechanisms.md",
    ):
        print(f"Wrote: {results_dir / name}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_dir = Path(args.results_folder).expanduser().resolve()
    if not results_dir.exists():
        print(f"[ERROR] Results folder does not exist: {results_dir}")
        return 1
    paths = CausalGraphPaths(results_root=results_dir)
    result = CausalGraphBuilder().run(paths)
    print_result(paths, result.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
