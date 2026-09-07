#!/usr/bin/env python3
"""Compatibility CLI for Mechanism Evolution Graph v1.0."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.mechanism_evolution.contracts import (
    MechanismEvolutionPaths,
    MechanismEvolutionRunResult,
)
from Analyzer_next.engines.mechanism_evolution_graph import (
    MechanismEvolutionGraph,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build mechanism/template evolution graph."
    )
    parser.add_argument(
        "results_folder", help="Universe Search results folder."
    )
    return parser.parse_args(argv)


def print_result(
    paths: MechanismEvolutionPaths,
    result: MechanismEvolutionRunResult,
) -> None:
    results_dir = paths.results_root
    evo = result.evolution_graph
    print("Mechanism Evolution Graph v1.0")
    print("=" * 64)
    print(f"Results: {results_dir}")
    print(f"Rules: {evo['rule_count']}")
    print(
        "Template nodes/edges: "
        f"{evo['template_layer']['node_count']} / "
        f"{evo['template_layer']['edge_count']}"
    )
    print(
        "Atomic nodes/edges: "
        f"{evo['atomic_layer']['node_count']} / "
        f"{evo['atomic_layer']['edge_count']}"
    )
    for name in (
        "mechanism_evolution_graph.json",
        "mechanism_evolution_graph.md",
        "mechanism_evolution_report.json",
        "mechanism_evolution_report.md",
        "rule_evolution_paths.json",
        "rule_evolution_paths.md",
    ):
        print(f"Wrote: {results_dir / name}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_dir = Path(args.results_folder).expanduser().resolve()
    if not results_dir.exists():
        print(f"[ERROR] Results folder does not exist: {results_dir}")
        return 1
    paths = MechanismEvolutionPaths(results_root=results_dir)
    result = MechanismEvolutionGraph().run(paths)
    print_result(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
