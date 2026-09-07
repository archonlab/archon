#!/usr/bin/env python3
"""Compatibility CLI for the modular Discovery Engine v2."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.discovery.analysis import impact_stars
from Analyzer_next.core.discovery.contracts import DiscoveryPaths, DiscoveryRunResult
from Analyzer_next.engines.discovery_engine import DiscoveryEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a multi-rule discovery database through ARCHON Data Layer."
    )
    parser.add_argument("results_folder", help="Universe Search results folder")
    parser.add_argument(
        "--analysis-root",
        default=None,
        help="Results/Analysis folder. Auto-detected from project layout.",
    )
    parser.add_argument(
        "--knowledge-root",
        default=None,
        help="Atlas/Knowledge folder. Auto-detected from project layout.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Output discovery database JSON. Default: results/discovery_database.json",
    )
    parser.add_argument(
        "--md-out",
        default=None,
        help="Output Markdown report. Default: results/discovery_report.md",
    )
    return parser.parse_args(argv)


def resolve_paths(args: argparse.Namespace) -> DiscoveryPaths:
    results_root = Path(args.results_folder).expanduser().resolve()
    project_root = results_root.parent.parent
    analysis_root = (
        Path(args.analysis_root).expanduser().resolve()
        if args.analysis_root
        else project_root / "Results" / "Analysis"
    )
    knowledge_root = (
        Path(args.knowledge_root).expanduser().resolve()
        if args.knowledge_root
        else project_root / "Atlas" / "Knowledge"
    )
    return DiscoveryPaths(
        results_root=results_root,
        analysis_root=analysis_root,
        knowledge_root=knowledge_root,
        atlas_path=knowledge_root / "research_atlas.json",
        database_json=(
            Path(args.json_out).expanduser().resolve()
            if args.json_out
            else results_root / "discovery_database.json"
        ),
        report_markdown=(
            Path(args.md_out).expanduser().resolve()
            if args.md_out
            else results_root / "discovery_report.md"
        ),
    )


def print_summary(paths: DiscoveryPaths, result: DiscoveryRunResult) -> None:
    database = result.database
    summary = database["summary"]
    print("")
    print("=" * 68)
    print("Universe Search Discovery Engine v2")
    print("=" * 68)
    print(f"Rules analyzed:          {summary['rules_analyzed']}")
    print(f"Rules with discoveries: {summary['rules_with_discoveries']}")
    print(f"Discoveries:             {summary['discovery_count']}")
    print(f"High-impact:             {summary['high_impact_count']}")
    print(f"JSON:                    {paths.database_json}")
    print(f"Markdown:                {paths.report_markdown}")
    print("-" * 68)
    for item in database["top_discoveries"][:12]:
        print(
            f"{item['rule_id']} | {item['title']} | "
            f"{impact_stars(item['impact'])} | {item['confidence']}"
        )
    print("=" * 68)


def main(argv: list[str] | None = None) -> int:
    paths = resolve_paths(parse_args(argv))
    result = DiscoveryEngine().run(paths)
    print_summary(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
