#!/usr/bin/env python3
"""Compatibility CLI for Mechanism Timeline Builder v1.1."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.core.mechanism_timeline.contracts import (
    MechanismTimelineExecution,
    MechanismTimelineOptions,
    MechanismTimelinePaths,
)
from Analyzer_next.engines.mechanism_timeline_builder import (
    MechanismTimelineBuilder,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build time-ordered mechanism timeline from fused events."
    )
    parser.add_argument(
        "results_folder", help="Universe Search results folder."
    )
    parser.add_argument(
        "--pretty-json",
        action="store_true",
        help="Write indented JSON. Slower and substantially larger.",
    )
    parser.add_argument(
        "--skip-full-md",
        action="store_true",
        help="Skip the very large mechanism_timeline.md.",
    )
    return parser.parse_args(argv)


def print_progress(
    index: int,
    total: int,
    rule_id: str,
    event_count: int,
    elapsed_seconds: float,
) -> None:
    print(
        f"[{index:02d}/{total:02d}] Rule {rule_id}: "
        f"{event_count} timeline events in {elapsed_seconds:.2f}s",
        flush=True,
    )


def print_result(
    paths: MechanismTimelinePaths,
    execution: MechanismTimelineExecution,
    options: MechanismTimelineOptions,
    total_elapsed: float,
) -> None:
    results_dir = paths.results_root
    timeline = execution.result.timeline
    print("Mechanism Timeline Builder v1.1")
    print("=" * 64)
    print(f"Results: {results_dir}")
    print(f"Rules: {timeline['rule_count']}")
    print(
        "Timeline events: "
        f"{timeline['global_summary']['timeline_event_count']}"
    )
    print(
        "Transition nodes/edges: "
        f"{timeline['global_transitions']['node_count']} / "
        f"{timeline['global_transitions']['edge_count']}"
    )
    print(f"Wrote: {results_dir / 'mechanism_timeline.json'}")
    if options.write_full_md:
        print(f"Wrote: {results_dir / 'mechanism_timeline.md'}")
    else:
        print("Skipped: mechanism_timeline.md")
    for name in (
        "mechanism_events.csv",
        "mechanism_transitions.json",
        "mechanism_transitions.md",
        "mechanism_timeline_report.json",
        "mechanism_timeline_report.md",
    ):
        print(f"Wrote: {results_dir / name}")
    print(f"Output writing: {execution.output_writing_seconds:.2f}s")
    print(f"Total runtime:  {total_elapsed:.2f}s")


def main(argv: list[str] | None = None) -> int:
    try:
        os.nice(int(os.environ.get("ARCHON_ANALYZER_NICE", "8")))
    except (AttributeError, OSError, ValueError):
        pass
    args = parse_args(argv)
    results_dir = Path(args.results_folder).expanduser().resolve()
    if not results_dir.exists():
        print(f"[ERROR] Results folder does not exist: {results_dir}")
        return 1
    total_started = time.perf_counter()
    paths = MechanismTimelinePaths(results_root=results_dir)
    options = MechanismTimelineOptions(
        pretty_json=args.pretty_json,
        write_full_md=not args.skip_full_md,
    )
    execution = MechanismTimelineBuilder().run(
        paths, options, print_progress
    )
    total_elapsed = time.perf_counter() - total_started
    print_result(paths, execution, options, total_elapsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
