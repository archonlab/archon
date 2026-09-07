#!/usr/bin/env python3
"""Compatibility CLI for the modular Mechanism Engine v2.2."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.mechanism.contracts import (
    MechanismPaths,
    MechanismRunResult,
)
from Analyzer_next.engines.mechanism_engine import MechanismEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate mechanism reports for all representative Observer profiles."
        )
    )
    parser.add_argument(
        "results_folder", help="Raw Universe Search results folder"
    )
    parser.add_argument(
        "--rule", default=None, help="Analyze only one rule, e.g. 00251"
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=(
            "Directory for per-rule Markdown reports. "
            "Default: Results/Analysis"
        ),
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help=(
            "Aggregate JSON output. "
            "Default: Results/Universe_Search/mechanism_report.json"
        ),
    )
    parser.add_argument(
        "--analysis-root",
        default=None,
        help="Results/Analysis folder. Auto-detected from project layout.",
    )
    parser.add_argument(
        "--world-atlas-root",
        default=None,
        help="Atlas/Worlds folder. Auto-detected from project layout.",
    )
    parser.add_argument(
        "--knowledge-root",
        default=None,
        help="Atlas/Knowledge folder. Auto-detected from project layout.",
    )
    return parser.parse_args(argv)


def resolve_paths(args: argparse.Namespace) -> MechanismPaths:
    results_root = Path(args.results_folder).expanduser().resolve()
    project_root = results_root.parent.parent
    analysis_root = (
        Path(args.analysis_root).expanduser().resolve()
        if args.analysis_root
        else project_root / "Results" / "Analysis"
    )
    world_atlas_root = (
        Path(args.world_atlas_root).expanduser().resolve()
        if args.world_atlas_root
        else project_root / "Atlas" / "Worlds"
    )
    knowledge_root = (
        Path(args.knowledge_root).expanduser().resolve()
        if args.knowledge_root
        else project_root / "Atlas" / "Knowledge"
    )
    output_directory = (
        Path(args.out_dir).expanduser()
        if args.out_dir
        else analysis_root
    )
    if not output_directory.is_absolute():
        output_directory = (Path.cwd() / output_directory).resolve()
    aggregate_json = (
        Path(args.json_out).expanduser()
        if args.json_out
        else results_root / "mechanism_report.json"
    )
    if not aggregate_json.is_absolute():
        aggregate_json = (Path.cwd() / aggregate_json).resolve()
    return MechanismPaths(
        results_root=results_root,
        analysis_root=analysis_root,
        knowledge_root=knowledge_root,
        world_atlas_root=world_atlas_root,
        output_directory=output_directory,
        aggregate_json=aggregate_json,
    )


def print_result(paths: MechanismPaths, result: MechanismRunResult) -> None:
    payload = result.aggregate
    print("=" * 72)
    print("Universe Search Mechanism Engine v2.2 Alias-Aware Batch")
    print("=" * 72)
    print(f"Results: {paths.results_root}")
    print(f"Rules queued: {payload['rules_queued']}")
    for line in result.status_lines:
        print(line)
    print("-" * 72)
    print(f"Rules analyzed:         {payload['rules_analyzed']}")
    print(
        f"Rules with mechanisms: {payload['rules_with_mechanisms']}"
    )
    print(f"Mechanism candidates:  {payload['mechanism_candidates']}")
    print(f"Deferred:              {payload.get('rules_deferred', 0)}")
    print(f"Failures:              {payload['rules_failed']}")
    print(f"Aggregate JSON:        {paths.aggregate_json}")
    print(f"Markdown directory:    {paths.output_directory}")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = resolve_paths(args)
    if not paths.results_root.exists():
        print(f"[ERROR] results folder not found: {paths.results_root}")
        return 1
    try:
        result = MechanismEngine().run(
            paths,
            selected_rule=args.rule,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    print_result(paths, result)
    return 0 if result.aggregate["rules_failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
