#!/usr/bin/env python3
"""Compatibility CLI for the modular Knowledge Base Engine v3.2."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.knowledge_base.contracts import KnowledgeBasePaths
from Analyzer_next.engines.knowledge_base_engine import KnowledgeBaseEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build normalized ARCHON Knowledge Base v3."
    )
    parser.add_argument("results_folder")
    parser.add_argument("--atlas", default=None)
    parser.add_argument("--analysis-root", default=None)
    parser.add_argument("--knowledge-root", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--pretty-json", action="store_true")
    return parser.parse_args(argv)


def resolve_paths(args: argparse.Namespace) -> KnowledgeBasePaths:
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
    atlas_path = (
        Path(args.atlas).expanduser().resolve()
        if args.atlas
        else knowledge_root / "research_atlas.json"
    )
    output_json = (
        Path(args.out).expanduser().resolve()
        if args.out
        else knowledge_root / "knowledge_base.json"
    )
    return KnowledgeBasePaths(
        results_root=results_root,
        analysis_root=analysis_root,
        knowledge_root=knowledge_root,
        atlas_path=atlas_path,
        output_json=output_json,
        output_markdown=output_json.with_suffix(".md"),
        integrity_json=output_json.with_name("knowledge_base_integrity.json"),
        pretty_json=bool(args.pretty_json),
    )


def print_summary(paths: KnowledgeBasePaths, result) -> None:
    kb = result.knowledge_base
    integrity = result.integrity
    print("")
    print("=" * 72)
    print("Universe Search Knowledge Base Engine v3.2")
    print("=" * 72)
    print(f"Rules:              {kb['summary']['rules']}")
    print(f"Principles:         {kb['summary']['principles']}")
    print(f"Predictions:        {kb['summary']['predictions']}")
    print(f"Validations:        {kb['summary']['validations']}")
    print(f"Discoveries:        {kb['summary']['discoveries']}")
    print(f"Mechanisms:         {kb['summary']['mechanisms']}")
    print(f"Integrity:          {'OK' if integrity['ok'] else 'FAILED'}")
    print(f"Broken references:  {integrity['broken_reference_count']}")
    print(f"Duplicate links:    {integrity['duplicate_relation_count']}")
    print(f"Output JSON:        {paths.output_json}")
    print(f"Output MD:          {paths.output_markdown}")
    print(f"Integrity report:   {paths.integrity_json}")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    paths = resolve_paths(parse_args(argv))
    result = KnowledgeBaseEngine().run(paths)
    print_summary(paths, result)
    return 0 if result.integrity["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
