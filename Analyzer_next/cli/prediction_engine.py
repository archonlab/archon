#!/usr/bin/env python3
"""Compatibility CLI for modular persistent Prediction Engine v2."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.prediction_registry.constants import ENGINE_VERSION
from Analyzer_next.core.prediction_registry.contracts import PredictionRegistryPaths
from Analyzer_next.core.prediction_registry.database import status_counts
from Analyzer_next.core.prediction_registry.values import normalize_status, stars
from Analyzer_next.engines.prediction_registry_engine import PredictionRegistryEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and maintain persistent ARCHON predictions."
    )
    parser.add_argument("atlas", help="Path to research_atlas.json")
    parser.add_argument(
        "--principles",
        default=None,
        help="Optional path to general_principles.json",
    )
    parser.add_argument(
        "--out",
        default="predictions.md",
        help="Output Markdown report",
    )
    parser.add_argument(
        "--knowledge-base",
        default=None,
        help="Optional Knowledge Base v3 path",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="Optional persistent prediction database path",
    )
    return parser.parse_args(argv)


def find_project_layout(
    atlas_path: Path,
    out_md: Path,
) -> tuple[Path, Path, Path]:
    if atlas_path.parent.name == "Knowledge" and atlas_path.parent.parent.name == "Atlas":
        project_root = atlas_path.parent.parent.parent
    else:
        candidate = out_md.parent.parent.parent
        project_root = (
            candidate
            if (candidate / "Analyzer_next").exists()
            else atlas_path.parent
        )

    analysis_root = project_root / "Results" / "Analysis"
    knowledge_root = project_root / "Atlas" / "Knowledge"
    return project_root.resolve(), analysis_root.resolve(), knowledge_root.resolve()


def resolve_paths(args: argparse.Namespace) -> PredictionRegistryPaths:
    atlas_path = Path(args.atlas).expanduser().resolve()
    out_md = Path(args.out).expanduser()
    if not out_md.is_absolute():
        out_md = atlas_path.parent / out_md
    out_md = out_md.resolve()

    _, analysis_root, knowledge_root = find_project_layout(atlas_path, out_md)
    knowledge_base = (
        Path(args.knowledge_base).expanduser().resolve()
        if args.knowledge_base
        else knowledge_root / "knowledge_base.json"
    )
    database_json = (
        Path(args.database).expanduser().resolve()
        if args.database
        else knowledge_root / "prediction_database.json"
    )
    return PredictionRegistryPaths(
        atlas=atlas_path,
        principles=(
            Path(args.principles).expanduser().resolve()
            if args.principles
            else None
        ),
        analysis_root=analysis_root,
        knowledge_base=knowledge_base,
        database_json=database_json,
        database_markdown=database_json.with_suffix(".md"),
        output_json=out_md.with_suffix(".json"),
        output_markdown=out_md,
    )


def print_summary(paths: PredictionRegistryPaths, result) -> None:
    counts = status_counts(result.database["predictions"])
    print("")
    print("=" * 72)
    print(ENGINE_VERSION)
    print("=" * 72)
    print(f"Atlas:                {paths.atlas}")
    print(f"Knowledge Base:       {paths.knowledge_base}")
    print(f"Principles:           {result.principle_count}")
    print(f"Candidates this run:  {result.candidate_count}")
    print(f"Stored predictions:   {len(result.database['predictions'])}")
    print(f"Validations loaded:   {result.validation_count}")
    print(f"Status counts:        {counts}")
    print(f"Output MD:            {paths.output_markdown}")
    print(f"Output JSON:          {paths.output_json}")
    print(f"Persistent database:  {paths.database_json}")
    print("-" * 72)
    for item in result.compatibility["predictions"]:
        print(
            f"{item.get('id')}: priority={stars(item.get('priority', 1))} "
            f"confidence={item.get('confidence')} "
            f"status={normalize_status(item.get('status'))}"
        )
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    paths = resolve_paths(parse_args(argv))
    if not paths.atlas.exists():
        print(f"[ERROR] Atlas not found: {paths.atlas}")
        return 1
    result = PredictionRegistryEngine().run(paths)
    print_summary(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
