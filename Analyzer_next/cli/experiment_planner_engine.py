#!/usr/bin/env python3
"""Compatibility CLI for modular Experiment Planner Engine v4.4."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.experiment_planner.file_repository import resolve_paths
from Analyzer_next.core.experiment_planner.planning import ENGINE_VERSION, stars
from Analyzer_next.engines.experiment_planner_engine import ExperimentPlannerEngine


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate dynamic experiments from current ARCHON validation state."
    )
    parser.add_argument("knowledge_base", help="Path to knowledge_base.json")
    parser.add_argument("--out", default="experiment_plan.md")
    parser.add_argument("--validation", default=None)
    parser.add_argument("--predictions", default=None)
    parser.add_argument("--cohort-targets", default=None)
    parser.add_argument("--consensus", default=None)
    parser.add_argument("--evidence", default=None)
    parser.add_argument("--metric-audit", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = resolve_paths(
        args.knowledge_base,
        args.out,
        validation=args.validation,
        predictions=args.predictions,
        cohort_targets=args.cohort_targets,
        consensus=args.consensus,
        evidence=args.evidence,
        metric_audit=args.metric_audit,
    )
    if not paths.knowledge_base.exists():
        print(f"[ERROR] Knowledge Base not found: {paths.knowledge_base}")
        return 1
    saved = ExperimentPlannerEngine().run(paths)
    artifact = saved.artifact
    payload = artifact.payload

    print("")
    print("=" * 72)
    print(ENGINE_VERSION)
    print("=" * 72)
    print(f"Knowledge Base:       {paths.knowledge_base}")
    print(f"Validation report:    {paths.validation_report}")
    print(f"Prediction database:  {paths.prediction_database}")
    print(f"Cohort targets:       {paths.cohort_targets}")
    print(f"Consensus report:     {paths.consensus_report}")
    print(f"Evidence report:      {paths.evidence_report}")
    print(f"Validation results:   {artifact.validation_count}")
    print(f"Plan items:           {payload['plan_item_count']}")
    print(f"Search jobs:          {payload['search_job_count']}")
    print(f"Mutation jobs:        {payload['mutation_job_count']}")
    print(f"Perturbation programs:{payload['perturbation_program_count']:>8}")
    print(f"Output MD:            {paths.output_markdown}")
    print(f"Output JSON:          {paths.output_json}")
    print(
        "Output update:        "
        + (
            "scientific plan changed"
            if artifact.changed
            else "no content change"
        )
    )
    print("-" * 72)
    for task in payload["plan"]:
        print(
            f"{task['id']}: priority={stars(task['priority'])} "
            f"{task['title']}"
        )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
