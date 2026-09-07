#!/usr/bin/env python3
"""Publish one canonical ARCHON per-mutation report without rewriting aggregate analysis."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.ontology.lifecycle_adapter import ScientificOntologyLifecycleAdapter
from Analyzer_next.core.mutation.analyzer import analyze_mutation


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze one existing mutation and publish only its per-mutation report."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--results-root", type=Path, default=PROJECT_ROOT / "Results/Universe_Search")
    parser.add_argument("--mutation-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "Results/Analysis/Mutations")
    args = parser.parse_args(argv)

    results_root = args.results_root.expanduser().resolve()
    mutation_root = (args.mutation_root.expanduser().resolve() if args.mutation_root else (results_root / "mutation_runs").resolve())
    output_root = args.output_root.expanduser().resolve()
    manifest = args.manifest.expanduser().resolve()

    if not manifest.is_file() or manifest.name != "mutation_manifest.json":
        parser.error(f"mutation manifest not found: {manifest}")
    if not _within(manifest, mutation_root):
        parser.error("manifest must be inside Results/Universe_Search/mutation_runs")

    try:
        report = analyze_mutation(
            manifest,
            results_root,
            mutation_root,
            output_root,
            lifecycle_reconciler=ScientificOntologyLifecycleAdapter(),
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    effect = report.get("effect_interpretation", {}).get("primary", "unknown")
    confidence = report.get("comparison_confidence", {}).get("grade", "MISSING")
    output = report.get("output", {}).get("json")
    print(f"PASS: {report.get('mutation_id')} • effect={effect} • confidence={confidence}")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
