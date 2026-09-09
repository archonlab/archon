#!/usr/bin/env python3
"""Shared, fail-closed launch contract for the canonical Universe Search runtime.

This module contains no scientific behavior.  Studio and Search Launcher use it
to resolve the same entrypoint and to reject incomplete release trees before a
process is started.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
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


class SearchDependencyError(RuntimeError):
    """The selected Search interpreter cannot provide its configured backend."""

    def __init__(self, python_executable: str, dependency: str, detail: str = "") -> None:
        self.python_executable = python_executable
        self.dependency = dependency
        self.detail = detail
        message = (
            "Universe Search cannot start.\n"
            f"Python runtime:\n{python_executable}\n"
            f"Missing dependency:\n{dependency}"
        )
        if detail:
            message += f"\nDetail:\n{detail}"
        super().__init__(message)


def configured_backend_dependency(env: dict[str, str] | None = None) -> str | None:
    backend = str((os.environ if env is None else env).get("ART_EVO_FIELD_BACKEND", "numpy")).strip().lower()
    if backend in {"", "numpy", "np"}:
        return "numpy"
    if backend in {"cupy", "cuda", "gpu"}:
        return "cupy"
    return None


def preflight_search_dependencies(
    python_command: Iterable[str],
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Validate dependencies with the exact interpreter that will run Search."""
    command = [str(value) for value in python_command]
    if not command:
        raise RuntimeError("Universe Search Python command is empty")
    dependency = configured_backend_dependency(env)
    probe = (
        "import importlib,json,platform,sys;"
        f"name={dependency!r};ok=True;detail='';"
        "\ntry:\n importlib.import_module(name) if name else None"
        "\nexcept Exception as exc:\n ok=False;detail=f'{type(exc).__name__}: {exc}'"
        "\nprint(json.dumps({'ok':ok,'detail':detail,'executable':sys.executable,'version':platform.python_version()}))"
        "\nraise SystemExit(0 if ok else 42)"
    )
    try:
        completed = subprocess.run(
            [*command, "-c", probe],
            env=dict(os.environ if env is None else env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SearchDependencyError(command[0], dependency or "configured backend", str(exc)) from exc
    try:
        payload = json.loads((completed.stdout or "").strip())
    except json.JSONDecodeError:
        payload = {}
    runtime = str(payload.get("executable") or command[0])
    if completed.returncode != 0 or not bool(payload.get("ok")):
        detail = str(payload.get("detail") or (completed.stderr or "").strip())
        raise SearchDependencyError(runtime, dependency or "configured backend", detail)
    return {
        "python_executable": runtime,
        "python_version": str(payload.get("version") or "unknown"),
        "dependency": dependency or "none",
    }


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


def search_command_parts(command: Iterable[str]) -> tuple[list[str], int]:
    """Return interpreter prefix and entrypoint index for a canonical command."""
    values = [str(value) for value in command]
    try:
        unbuffered_index = values.index("-u")
    except ValueError as exc:
        raise ValueError("canonical Search command is missing -u boundary") from exc
    entrypoint_index = unbuffered_index + 1
    if unbuffered_index < 1 or entrypoint_index >= len(values):
        raise ValueError("canonical Search command has an invalid interpreter boundary")
    return values[:unbuffered_index], entrypoint_index
