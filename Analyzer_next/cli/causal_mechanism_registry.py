#!/usr/bin/env python3
"""Compatibility CLI for Causal Mechanism Registry v1.1 Atomic."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.causal_registry.contracts import (
    CausalRegistryPaths,
    CausalRegistryRunResult,
)
from Analyzer_next.engines.causal_mechanism_registry import (
    CausalMechanismRegistry,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build atomic mechanism registry and mechanism compositions."
    )
    parser.add_argument(
        "results_folder", help="Universe Search results folder."
    )
    return parser.parse_args(argv)


def print_result(
    paths: CausalRegistryPaths,
    result: CausalRegistryRunResult,
) -> None:
    results_dir = paths.results_root
    print("Causal Mechanism Registry v1.1 Atomic")
    print("=" * 64)
    print(f"Results: {results_dir}")
    print(f"Sources: {', '.join(result.source_keys)}")
    print(f"Atomic mechanisms: {result.atomic_registry['mechanism_count']}")
    print(f"Compositions: {result.composition_registry['composition_count']}")
    print(f"Rules mapped: {result.rule_map['rule_count']}")
    for name in (
        "mechanism_registry.json",
        "mechanism_registry.md",
        "composition_registry.json",
        "composition_registry.md",
        "rule_mechanism_map.json",
        "rule_mechanism_map.md",
        "causal_mechanism_report.json",
        "causal_mechanism_report.md",
    ):
        print(f"Wrote: {results_dir / name}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_dir = Path(args.results_folder).expanduser().resolve()
    if not results_dir.exists():
        print(f"[ERROR] Results folder does not exist: {results_dir}")
        return 1
    paths = CausalRegistryPaths(results_root=results_dir)
    result = CausalMechanismRegistry().run(paths)
    print_result(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
