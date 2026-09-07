"""Canonical clean-release routes for subprocess Analyzer modules.

The dependency extractor can follow the explicit relative paths below, while
runtime callers receive validated absolute paths rooted in Analyzer_next.
No production route may fall back to the frozen top-level Analyzer tree.
"""
from __future__ import annotations

from pathlib import Path

from Analyzer_next.production.routing import MIGRATED_ROUTE_RELATIVE_PATHS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = (
    PROJECT_ROOT / "Analyzer_next" / "compatibility" / "legacy_analyzer"
)
CLI_ROOT = PROJECT_ROOT / "Analyzer_next" / "cli"

RUNTIME_ROUTE_RELATIVE_PATHS = (
    "Analyzer_next/compatibility/legacy_analyzer/approved_action_planner_intake.py",
    "Analyzer_next/compatibility/legacy_analyzer/experiment_execution_dispatch.py",
    "Analyzer_next/compatibility/legacy_analyzer/experiment_analyzer.py",
    "Analyzer_next/compatibility/legacy_analyzer/experiment_launch_authorization.py",
    "Analyzer_next/compatibility/legacy_analyzer/experiment_plan_commit.py",
    "Analyzer_next/compatibility/legacy_analyzer/experiment_planner_review.py",
    "Analyzer_next/compatibility/legacy_analyzer/experiment_runtime_materializer.py",
    "Analyzer_next/compatibility/legacy_analyzer/observer_execution_contract.py",
    "Analyzer_next/compatibility/legacy_analyzer/observer_profile_v31.py",
    "Analyzer_next/compatibility/legacy_analyzer/ontology_profile_shadow.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_analyzer_completion_reconciliation.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_browser_publication.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_execution_cycle_orchestrator.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_mutation_execution_adapter.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_observer_analyzer_bridge.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_observer_binding.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_observer_launch.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_observer_launch_authorization.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_observer_result_intake.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_research_cycle_launcher_handoff.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_research_cycle_orchestrator.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_runtime_recovery.py",
    "Analyzer_next/compatibility/legacy_analyzer/production_stage6_job_finalization.py",
    "Analyzer_next/compatibility/legacy_analyzer/real_observer_cli_adapter.py",
    "Analyzer_next/compatibility/legacy_analyzer/research_cycle_record.py",
    "Analyzer_next/compatibility/legacy_analyzer/scientific_protocol_resolver.py",
    "Analyzer_next/compatibility/legacy_analyzer/scientific_target_resolver.py",
    "Analyzer_next/compatibility/legacy_analyzer/passport_analyzer.py",
    "Analyzer_next/compatibility/legacy_analyzer/question_tracker.py",
    "Analyzer_next/compatibility/legacy_analyzer/scientific_view.py",
)

_ALLOWED = {Path(item).name: item for item in RUNTIME_ROUTE_RELATIVE_PATHS}
CLI_ROUTE_RELATIVE_PATHS = (
    *MIGRATED_ROUTE_RELATIVE_PATHS,
    "Analyzer_next/cli/analyze_results.py",
    "Analyzer_next/cli/approved_action_planner_intake_compat.py",
    "Analyzer_next/cli/experiment_plan_commit.py",
    "Analyzer_next/cli/experiment_planner_review.py",
    "Analyzer_next/cli/experiment_runtime_materializer.py",
    "Analyzer_next/cli/production_execution_cycle_orchestrator.py",
    "Analyzer_next/cli/production_observer_result_intake.py",
    "Analyzer_next/cli/production_research_cycle_launcher_handoff.py",
    "Analyzer_next/cli/production_research_cycle_orchestrator.py",
    "Analyzer_next/cli/scientific_protocol_resolver.py",
    "Analyzer_next/cli/scientific_target_resolver.py",
)
_CLI_ALLOWED = {
    Path(item).name: item for item in CLI_ROUTE_RELATIVE_PATHS
}


def compatibility_route(filename: str) -> Path:
    """Return one declared compatibility route and fail closed otherwise."""
    relative = _ALLOWED.get(str(filename))
    if relative is None:
        raise RuntimeError(f"Undeclared Analyzer compatibility route: {filename}")
    path = (PROJECT_ROOT / relative).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Analyzer compatibility route is missing: {path}")
    return path


def cli_route(filename: str) -> Path:
    """Return one existing modular CLI route without legacy fallback."""
    relative = _CLI_ALLOWED.get(str(filename))
    if relative is None:
        raise RuntimeError(f"Undeclared Analyzer CLI route: {filename}")
    path = (PROJECT_ROOT / relative).resolve()
    if path.parent != CLI_ROOT.resolve() or not path.is_file():
        raise FileNotFoundError(f"Analyzer CLI route is missing: {path}")
    return path


__all__ = [
    "CLI_ROOT",
    "CLI_ROUTE_RELATIVE_PATHS",
    "COMPATIBILITY_ROOT",
    "RUNTIME_ROUTE_RELATIVE_PATHS",
    "cli_route",
    "compatibility_route",
]
