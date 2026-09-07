#!/usr/bin/env python3
"""Compatibility CLI for Composition Template Builder v1.0."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.composition_templates.contracts import (
    CompositionTemplatePaths,
    CompositionTemplateRunResult,
)
from Analyzer_next.engines.composition_template_builder import (
    CompositionTemplateBuilder,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build composition templates from composition instances."
    )
    parser.add_argument(
        "results_folder", help="Universe Search results folder."
    )
    return parser.parse_args(argv)


def print_result(
    paths: CompositionTemplatePaths,
    result: CompositionTemplateRunResult,
) -> None:
    results_dir = paths.results_root
    print("Composition Template Builder v1.0")
    print("=" * 64)
    print(f"Results: {results_dir}")
    print(f"Templates: {result.template_registry['template_count']}")
    print(f"Instances: {result.instance_registry['instance_count']}")
    print(f"Rules mapped: {result.template_rule_map['rule_count']}")
    for name in (
        "composition_templates.json",
        "composition_templates.md",
        "composition_instances.json",
        "composition_instances.md",
        "template_rule_map.json",
        "template_rule_map.md",
        "template_report.json",
        "template_report.md",
    ):
        print(f"Wrote: {results_dir / name}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_dir = Path(args.results_folder).expanduser().resolve()
    if not results_dir.exists():
        print(f"[ERROR] Results folder does not exist: {results_dir}")
        return 1
    paths = CompositionTemplatePaths(results_root=results_dir)
    result = CompositionTemplateBuilder().run(paths)
    print_result(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
