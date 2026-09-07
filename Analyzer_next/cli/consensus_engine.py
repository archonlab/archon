#!/usr/bin/env python3
"""Compatibility CLI for the modular ARCHON Consensus Engine."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.consensus.contracts import ConsensusPaths, ConsensusRunResult
from Analyzer_next.core.consensus.numeric import sf, si
from Analyzer_next.engines.consensus_engine import ConsensusEngine
from archon_paths import ANALYSIS_RESULTS_DIR


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build/update consensus database and consensus report from evidence report."
    )
    parser.add_argument("results_folder", help="Shared Universe Search results folder")
    parser.add_argument(
        "--root",
        default=None,
        help="Analyzer root folder. Default: legacy Analyzer directory",
    )
    parser.add_argument(
        "--evidence",
        default=None,
        help="Evidence report JSON path. Default: ROOT/evidence_report.json",
    )
    parser.add_argument(
        "--counterexamples",
        default=None,
        help="Counterexample report JSON path. Default: ROOT/counterexample_report.json",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Consensus database JSON path. Default: ROOT/consensus_database.json",
    )
    parser.add_argument(
        "--md",
        default=None,
        help="Consensus database Markdown path. Default: ROOT/consensus_database.md",
    )
    parser.add_argument(
        "--report-json",
        default=None,
        help="Consensus report JSON path. Default: ROOT/consensus_report.json",
    )
    parser.add_argument(
        "--report-md",
        default=None,
        help="Consensus report Markdown path. Default: ROOT/consensus_report.md",
    )
    return parser.parse_args(argv)


def resolve_paths(args: argparse.Namespace) -> ConsensusPaths:
    results = Path(args.results_folder).resolve()
    root = Path(args.root).resolve() if args.root else ANALYSIS_RESULTS_DIR
    return ConsensusPaths(
        results=results,
        root=root,
        evidence=(Path(args.evidence).resolve() if args.evidence else root / "evidence_report.json"),
        counterexamples=(
            Path(args.counterexamples).resolve()
            if args.counterexamples
            else root / "counterexample_report.json"
        ),
        database_json=(Path(args.db).resolve() if args.db else root / "consensus_database.json"),
        database_markdown=(Path(args.md).resolve() if args.md else root / "consensus_database.md"),
        report_json=(
            Path(args.report_json).resolve()
            if args.report_json
            else root / "consensus_report.json"
        ),
        report_markdown=(
            Path(args.report_md).resolve()
            if args.report_md
            else root / "consensus_report.md"
        ),
    )


def print_summary(paths: ConsensusPaths, result: ConsensusRunResult) -> None:
    report = result.report
    print("")
    print("=" * 72)
    print("Universe Search Consensus Engine v33.1 — Stage 3.3.1 Signal Prioritization and Deduplication")
    print("=" * 72)
    print(f"Evidence:        {paths.evidence}")
    print(f"Counterexamples: {paths.counterexamples}")
    print(f"Database JSON:   {paths.database_json}")
    print(f"Database MD:     {paths.database_markdown}")
    print(f"Consensus JSON:  {paths.report_json}")
    print(f"Consensus MD:    {paths.report_markdown}")
    print(f"Principles:      {report.get('principle_count', 0)}")
    contexts = [
        principle
        for principle in report.get("principles", [])
        if (principle.get("consensus_context") or {}).get("profile_available")
    ]
    tensions = [
        principle
        for principle in report.get("principles", [])
        if (principle.get("consensus_context_flags") or {}).get("cross_channel_tension")
    ]
    print(f"Ev profiles:     {len(contexts)} ingested")
    print(f"Tension flags:   {len(tensions)}")
    interpretations = report.get("channel_aware_status_counts", {})
    print(f"Interpretations: {sum(interpretations.values())}")
    action_summary = report.get("action_signal_summary", {})
    print(
        "Action signals:  "
        f"{si(action_summary.get('total_active_signals'))} active / "
        f"{si(action_summary.get('total_blocked_signals'))} blocked / "
        f"{si(action_summary.get('total_raw_signals'))} raw across "
        f"{si(action_summary.get('principles_with_signals'))} principles"
    )
    print("-" * 72)
    for principle in report.get("principles", [])[:12]:
        print(
            f"{principle.get('id')}: {principle.get('title')} | {principle.get('status')} | "
            f"adjusted={sf(principle.get('consensus_percent')):.1f}% | "
            f"raw={sf(principle.get('raw_consensus_percent')):.1f}% | "
            f"channel={principle.get('channel_aware_status')} | "
            f"primary={principle.get('primary_action_signal') or 'none'} | "
            f"action={principle.get('highest_action_priority')} | "
            f"active={si(principle.get('action_signal_count'))} | "
            f"blocked={si(principle.get('blocked_action_signal_count'))}"
        )
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    paths = resolve_paths(parse_args(argv))
    result = ConsensusEngine().run(paths)
    print_summary(paths, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
