#!/usr/bin/env python3
"""Shared, fail-closed launch contract for the canonical Universe Search runtime.

This module contains no scientific behavior.  Studio and Search Launcher use it
to resolve the same entrypoint and to reject incomplete release trees before a
process is started.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


ENTRYPOINT = "Universe_Search/universe_search_v34_closed_research_cycle.py"

# These modules are imported by the canonical entrypoint as scientific layers.
# The engine historically treats some of them as optional for old source trees;
# a production Studio launch must not silently lose them because packaging was
# incomplete.
REQUIRED_RUNTIME_FILES = (
    "archon_paths.py",
    "World_Portability/__init__.py",
    "World_Portability/service.py",
    "Observer/__init__.py",
    "Observer/observer_civilization.py",
    "Observer/observer_ecology.py",
    "Observer/observer_ecosystem.py",
    "Observer/observer_institutions.py",
    "Observer/observer_network.py",
    "Universe_Search/__init__.py",
    "Universe_Search/discovery_engine.py",
    "Universe_Search/evolution_policy.py",
    "Universe_Search/experiment_engine.py",
    "Universe_Search/network_dynamics.py",
    "Universe_Search/paradigm_engine.py",
    "Universe_Search/research_bridge.py",
    "Universe_Search/research_cycle.py",
    "Universe_Search/research_programs.py",
    "Universe_Search/research_teams.py",
    "Universe_Search/scientific_state.py",
    "Universe_Search/scientific_state_builder.py",
    "Universe_Search/search_job_loader.py",
    "Universe_Search/search_launcher.py",
    "Universe_Search/search_runtime_contract.py",
    "Universe_Search/target_scoring.py",
    "Universe_Search/theory_engine.py",
    "Universe_Search/universe_search_core.py",
    ENTRYPOINT,
)


def validate_search_runtime(root: Path) -> Path:
    """Return the canonical entrypoint or raise for an incomplete release."""
    project = root.resolve()
    missing = [rel for rel in REQUIRED_RUNTIME_FILES if not (project / rel).is_file()]
    if missing:
        raise RuntimeError(
            "Canonical Universe Search runtime is incomplete; missing: "
            + ", ".join(missing)
            + ". Search was not started and no demo fallback is available."
        )
    return project / ENTRYPOINT


def canonical_search_command(
    root: Path,
    python_command: Iterable[str],
    run_command: str,
    score_mode: str,
    search_mode: str,
    *,
    experiment_plan: Path | None = None,
    search_job: str = "",
    target_regime: str = "",
    seed_rules: Iterable[str] = (),
) -> list[str]:
    """Build the one canonical command used by every Search operator surface."""
    entrypoint = root.resolve() / ENTRYPOINT
    command = [
        *[str(value) for value in python_command],
        "-u",
        str(entrypoint),
        str(run_command),
        str(score_mode),
        "--search-mode",
        str(search_mode),
    ]
    if experiment_plan is not None:
        command.extend(["--experiment-plan", str(experiment_plan)])
        if search_job:
            command.extend(["--search-job", str(search_job)])
        elif target_regime:
            command.extend(["--target-regime", str(target_regime)])
    for rule_id in seed_rules:
        command.extend(["--seed-rule", str(rule_id)])
    return command
