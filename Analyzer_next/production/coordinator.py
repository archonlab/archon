"""Modular execution shell for the transitional Analyzer scientific DAG.

This module owns the production coordinator control flow. Scientific step
implementations are selected through the fail-closed route map. The
content-aware DAG, execution policy, and receipt attestation are native. The
legacy profile bypasses this module entirely and remains a rollback path.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

from archon_paths import (
    ANALYZER_DIR,
    ANALYSIS_RESULTS_DIR,
    KNOWLEDGE_ATLAS_DIR,
    PROJECT_ROOT,
    SEARCH_RESULTS_DIR,
    WORLD_ATLAS_DIR,
    ensure_layout,
)
from Analyzer_next.production.catalog import build_steps
from Analyzer_next.production.contracts import ANALYZER_MODES, STAGE_ORDER
from Analyzer_next.production.incremental_dag import AnalyzerDAG
from Analyzer_next.production.input_mirroring import mirror_inputs
from Analyzer_next.production.process_execution import ExecutionPaths, run_step
from Analyzer_next.production.receipt_renderer import (
    write_scientific_refresh_receipt,
)
from Analyzer_next.production.routing import validate_module_overrides
from Analyzer_next.production.telemetry_materializer import materialize_telemetry
from Analyzer_next.production.world_atlas_index_reconciliation import (
    reconcile_world_atlas_index,
)


COORDINATOR_ROUTE = "Analyzer_next/production/coordinator.py"
EXECUTION_PATHS = ExecutionPaths(
    project_root=PROJECT_ROOT,
    analyzer_dir=ANALYZER_DIR,
    search_results_dir=SEARCH_RESULTS_DIR,
    analysis_results_dir=ANALYSIS_RESULTS_DIR,
    knowledge_atlas_dir=KNOWLEDGE_ATLAS_DIR,
    world_atlas_dir=WORLD_ATLAS_DIR,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_folder", nargs="?")
    parser.add_argument("--mode", choices=ANALYZER_MODES, default="full")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--profiles-only",
        action="store_true",
        help="Deprecated alias for --mode intake.",
    )
    parser.add_argument("--skip-lab", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-stage", choices=STAGE_ORDER)
    parser.add_argument("--from-stage", choices=STAGE_ORDER)
    parser.add_argument("--scientific-refresh-id")
    parser.add_argument("--telemetry-db")
    parser.add_argument("--telemetry-run-id", action="append")
    parser.add_argument("--telemetry-rule-id", type=int)
    parser.add_argument("--telemetry-latest-only", action="store_true")
    parser.add_argument("--telemetry-status", action="append")
    parser.add_argument("--telemetry-no-overwrite", action="store_true")
    return parser


def parse_request(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    request = parser.parse_args(list(argv) if argv is not None else None)
    if request.profiles_only:
        if request.mode != "full":
            parser.error("--profiles-only cannot be combined with --mode")
        request.mode = "intake"
    if request.mode == "intake" and request.from_stage:
        parser.error("--from-stage is not valid with --mode intake")
    if request.mode == "scientific-refresh" and request.from_stage == "profiles":
        parser.error("--mode scientific-refresh cannot start from profiles")
    return request


def select_steps(
    steps: Sequence[Any],
    *,
    mode: str,
    from_stage: str | None,
) -> list[Any]:
    """Apply the public mode/stage policy without changing catalog order."""
    selected = list(steps)
    if mode == "intake":
        selected = [step for step in selected if step.stage == "profiles"]
    elif mode == "scientific-refresh":
        selected = [step for step in selected if step.stage != "profiles"]
    if from_stage:
        start = STAGE_ORDER.index(from_stage)
        selected = [
            step
            for step in selected
            if STAGE_ORDER.index(step.stage) >= start
        ]
    return selected


def resolve_results_dir(value: str | None) -> Path:
    if not value:
        return SEARCH_RESULTS_DIR.resolve()
    raw = Path(value).expanduser()
    candidates = (
        (raw,)
        if raw.is_absolute()
        else (Path.cwd() / raw, PROJECT_ROOT / raw)
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _print_policy(results: Path) -> None:
    mutation_root = results / "mutation_runs"
    if not mutation_root.exists():
        return
    print("Mutation experiments:", mutation_root)
    print(
        "[policy] Mutation Analyzer writes isolated perturbation evidence "
        "to Results/Analysis/Mutations."
    )
    print(
        "[policy] Mutation reports feed a separate perturbation-evidence "
        "channel in Evidence, Principles, Theory, and Consensus."
    )
    print(
        "[policy] Perturbations do not increment observational support or "
        "automatically adjust confidence."
    )


def main(
    argv: Iterable[str] | None = None,
    *,
    module_overrides: Mapping[str, Path | str] | None = None,
    profile: str = "modular",
) -> int:
    request = parse_request(argv)
    try:
        overrides = validate_module_overrides(
            Path(__file__).resolve().parents[2],
            module_overrides or {},
        )
    except RuntimeError as exc:
        print(f"[FAILED] Analyzer entrypoint routing: {exc}", file=sys.stderr)
        return 2
    ensure_layout()
    results = resolve_results_dir(request.results_folder)
    if request.telemetry_db:
        report = materialize_telemetry(
            database_path=request.telemetry_db,
            results_dir=results,
            run_ids=request.telemetry_run_id,
            rule_id=request.telemetry_rule_id,
            latest_only=request.telemetry_latest_only,
            statuses=request.telemetry_status,
            overwrite=not request.telemetry_no_overwrite,
        )
        print(
            f"[telemetry bridge] runs={report.total_runs} "
            f"rows={report.total_rows} output={report.output_dir}"
        )

    print("Project ARCHON Analyzer")
    print("=" * 72)
    print("Search results:", results)
    print("Analysis output:", ANALYSIS_RESULTS_DIR)
    print("Knowledge Atlas:", KNOWLEDGE_ATLAS_DIR)
    print("Entrypoint profile:", profile)
    print("DAG coordinator:", COORDINATOR_ROUTE)
    print("Modular routes:", len(overrides))
    _print_policy(results)

    try:
        all_steps = build_steps(results, skip_lab=request.skip_lab)
    except RuntimeError as exc:
        print(f"[FAILED] Analyzer step catalog: {exc}", file=sys.stderr)
        return 2
    semantic_paths = {
        output.resolve()
        for step in all_steps
        for output in step.outputs
    }
    dag = AnalyzerDAG(
        ANALYSIS_RESULTS_DIR,
        semantic_paths=semantic_paths,
    )
    steps = select_steps(
        all_steps,
        mode=request.mode,
        from_stage=request.from_stage,
    )
    if any(step.label == "Alias Integrity Audit" for step in steps):
        if request.dry_run:
            print("World Atlas index reconciliation: DRY-RUN")
        else:
            reconciliation = reconcile_world_atlas_index(
                atlas_root=WORLD_ATLAS_DIR,
                knowledge_root=KNOWLEDGE_ATLAS_DIR,
                analysis_root=ANALYSIS_RESULTS_DIR,
            )
            print(
                "World Atlas index reconciliation: "
                f"{reconciliation['status']} "
                f"(active={reconciliation['active_rules']}, "
                f"index={reconciliation['previous_index_rules']}->"
                f"{reconciliation['final_index_rules']}, "
                f"recovered={len(reconciliation['recovered_rule_ids'])}, "
                f"removed={len(reconciliation['removed_rule_ids'])})"
            )
            if reconciliation["status"] == "FAILED":
                print(
                    "[FAILED] World Atlas Index Reconciliation: "
                    f"{reconciliation['report_path']}",
                    file=sys.stderr,
                )
                return 2
    refresh_started_at = _now_iso()
    dag_state_before = json.loads(json.dumps(dag.state))
    failures: list[str] = []

    for step in steps:
        if step.stage in ("notebook", "discovery", "mechanism"):
            mirror_inputs(
                results,
                analysis_results_dir=ANALYSIS_RESULTS_DIR,
            )
        if (
            step.label == "Experiment Planner"
            and not (
                ANALYSIS_RESULTS_DIR / "cohort_targets.json"
            ).exists()
        ):
            print(
                "[FAILED] Experiment Planner: cohort_targets.json is "
                "missing. Cohort Builder must finish first."
            )
            failures.append(step.label)
            if not request.continue_on_error:
                break
            continue
        force = request.force or request.force_stage == step.stage
        if not run_step(
            step,
            dag,
            paths=EXECUTION_PATHS,
            dry_run=request.dry_run,
            force=force,
            module_overrides=overrides,
        ):
            failures.append(step.label)
            if not request.continue_on_error:
                break

    dag.flush()
    if request.mode == "scientific-refresh" and not request.dry_run:
        refresh_id = (
            request.scientific_refresh_id
            or (request.telemetry_run_id or [None])[0]
            or datetime.now(timezone.utc).strftime(
                "SCIENTIFIC-REFRESH-%Y%m%dT%H%M%SZ"
            )
        )
        receipt_path, receipt = write_scientific_refresh_receipt(
            refresh_id=refresh_id,
            observer_run_ids=list(request.telemetry_run_id or []),
            selected_steps=steps,
            dag_state_before=dag_state_before,
            dag_state_after=dag.state,
            failures=failures,
            started_at=refresh_started_at,
            paths=EXECUTION_PATHS,
            module_overrides=overrides,
        )
        print(
            f"[scientific refresh] status={receipt['status']} "
            f"changed_stages={receipt['changed_stages']} "
            f"receipt={receipt_path}"
        )
        if receipt["status"] != "COMPLETED" and not failures:
            failures.append("Scientific Refresh Receipt")

    print("\n" + "=" * 72)
    if failures:
        print("Analyzer finished with failures:")
        for label in failures:
            print(" -", label)
        return 1
    print("Analyzer pipeline finished successfully.")
    return 0
