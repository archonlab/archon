#!/usr/bin/env python3
"""Compatibility CLI for the modular ARCHON Meta Science Engine."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.common.paths import analysis_results_dir, knowledge_atlas_dir
from Analyzer_next.core.meta_science.contracts import MetaSciencePaths, MetaScienceRunResult
from Analyzer_next.core.meta_science.numeric import sf, si
from Analyzer_next.engines.meta_science_engine import MetaScienceEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Observe knowledge evolution in the Universe Search Analyzer pipeline."
    )
    parser.add_argument("results_folder", help="Shared Universe Search results folder")
    parser.add_argument("--root", default=None, help="Analysis report folder. Default: Results/Analysis")
    parser.add_argument("--report-json", default=None, help="Output JSON. Default: ROOT/meta_science_report.json")
    parser.add_argument("--report-md", default=None, help="Output Markdown. Default: ROOT/meta_science_report.md")
    parser.add_argument("--history", default=None, help="History JSON. Default: Atlas/Knowledge/meta_science_history.json")
    parser.add_argument("--knowledge-root", default=None, help="Persistent knowledge folder")
    return parser.parse_args(argv)


def resolve_paths(args: argparse.Namespace) -> MetaSciencePaths:
    results = Path(args.results_folder).resolve()
    root = Path(args.root).resolve() if args.root else analysis_results_dir().resolve()
    knowledge_root = (
        Path(args.knowledge_root).resolve()
        if args.knowledge_root
        else knowledge_atlas_dir().resolve()
    )
    return MetaSciencePaths(
        results=results,
        root=root,
        knowledge_root=knowledge_root,
        report_json=(
            Path(args.report_json).resolve()
            if args.report_json
            else root / "meta_science_report.json"
        ),
        report_markdown=(
            Path(args.report_md).resolve()
            if args.report_md
            else root / "meta_science_report.md"
        ),
        history=(
            Path(args.history).resolve()
            if args.history
            else knowledge_root / "meta_science_history.json"
        ),
    )


def print_summary(paths: MetaSciencePaths, result: MetaScienceRunResult) -> None:
    snapshot = result.report
    metrics = snapshot.get("research_metrics", {})
    age = snapshot.get("knowledge_age", {})
    inputs = snapshot.get("inputs_seen", {})
    print("Universe Search Meta Science Engine v34.2")
    print("=" * 64)
    print(f"Root:              {paths.root}")
    print(f"Results:           {paths.results}")
    print(f"Output JSON:        {paths.report_json}")
    print(f"Output MD:          {paths.report_markdown}")
    print(f"History:            {paths.history}")
    print("-" * 64)
    print(f"Profiles:           {si(inputs.get('observer_profiles'))}")
    print(f"Principles:         {si(metrics.get('principles_total'))}")
    print(f"Knowledge maturity: {sf(metrics.get('knowledge_maturity_score')):.3f}")
    print(f"Stability:          {sf(metrics.get('scientific_stability_score')):.3f}")
    print(f"Velocity:           {sf(metrics.get('research_velocity_score')):.3f}")
    print(f"Efficiency:         {sf(metrics.get('knowledge_efficiency_score')):.3f}")
    scientific_health = snapshot.get("scientific_health", {})
    bottlenecks = snapshot.get("bottlenecks", {})
    primary_bottleneck = bottlenecks.get("primary") or {}
    secondary_bottleneck = bottlenecks.get("secondary") or {}
    print(
        f"Scientific health:  {sf(scientific_health.get('index')):.3f} "
        f"({scientific_health.get('grade', 'Unknown')})"
    )
    print(
        f"Primary bottleneck: {primary_bottleneck.get('title', 'None')} "
        f"(severity={sf(primary_bottleneck.get('severity')):.3f}, "
        f"gain=+{sf(primary_bottleneck.get('max_index_gain')):.3f})"
    )
    print(
        f"Secondary:          {secondary_bottleneck.get('title', 'None')} "
        f"(severity={sf(secondary_bottleneck.get('severity')):.3f})"
    )
    health = snapshot.get("laboratory_health", {})
    coverage = snapshot.get("coverage", {})
    pipeline = snapshot.get("prediction_pipeline", {})
    debt = snapshot.get("research_debt", {})
    print(f"Lab rules:          {si(health.get('rules'))}")
    print(f"Mechanism coverage: {sf(coverage.get('mechanism_percent')):.1f}%")
    print(f"Predictions:        {si(pipeline.get('generated'))} total, {si(pipeline.get('confirmed'))} confirmed, {si(pipeline.get('testing'))} testing")
    print(f"Research debt:      {si(debt.get('rules_without_mechanisms'))} rules without mechanisms")
    print(f"Integrity:          {'OK' if health.get('integrity_ok') else 'FAILED'}")
    print(
        f"Stages: OBS={si(age.get('observations'))} PROM={si(age.get('promising'))} "
        f"SUP={si(age.get('supported'))} STR={si(age.get('strong'))} "
        f"CONS={si(age.get('consensus'))} FOUND={si(age.get('foundational'))} "
        f"DIS={si(age.get('disputed'))}"
    )
    print("=" * 64)


def main(argv: list[str] | None = None) -> int:
    paths = resolve_paths(parse_args(argv))
    consensus_path = paths.root / "consensus_report.json"
    if not consensus_path.exists():
        raise SystemExit(
            f"Consensus report not found: {consensus_path}\nRun Consensus Engine first."
        )
    result = MetaScienceEngine().run(paths)
    print_summary(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
