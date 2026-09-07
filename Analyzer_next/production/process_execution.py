"""Native per-step process execution for the production Analyzer DAG."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from Analyzer_next.production.alias_canonicalization import (
    canonicalize_declared_alias_outputs,
)


@dataclass(frozen=True)
class ExecutionPaths:
    """Explicit filesystem contract inherited by every Analyzer process."""

    project_root: Path
    analyzer_dir: Path
    search_results_dir: Path
    analysis_results_dir: Path
    knowledge_atlas_dir: Path
    world_atlas_dir: Path




# BRIDGE5.3.1: migrated CLI wrappers are intentionally thin. Fingerprinting
# only the wrapper misses changes in the modular implementation behind it.
# Keep the declarative Step catalog parity-stable and add code dependencies at
# the execution boundary for the stages whose internal semantics are extended
# by BRIDGE5.3.x.
MODULAR_IMPLEMENTATION_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "mutation_analyzer.py": (
        "Analyzer_next/core/mutation",
    ),
    "metric_independence_audit.py": (
        "Analyzer_next/core/metric_independence",
    ),
    "evidence_engine.py": (
        "Analyzer_next/cli/evidence_engine.py",
    ),
    "experiment_planner_engine.py": (
        "Analyzer_next/core/experiment_planner",
    ),
}

RELOCATED_COMPATIBILITY_MODULES: dict[str, str] = {
    "passport_analyzer.py": "Analyzer_next/compatibility/legacy_analyzer/passport_analyzer.py",
    "question_tracker.py": "Analyzer_next/compatibility/legacy_analyzer/question_tracker.py",
}


def modular_implementation_dependencies(
    module: str,
    *,
    paths: ExecutionPaths,
    module_overrides: Mapping[str, Path] | None = None,
) -> tuple[Path, ...]:
    if module not in (module_overrides or {}):
        return ()
    relative = MODULAR_IMPLEMENTATION_DEPENDENCIES.get(module, ())
    return tuple((paths.project_root / item).resolve() for item in relative)


def module_path(
    module: str,
    *,
    paths: ExecutionPaths,
    module_overrides: Mapping[str, Path] | None = None,
) -> Path:
    override = (module_overrides or {}).get(module)
    if override is not None:
        return Path(override)
    compatibility = RELOCATED_COMPATIBILITY_MODULES.get(module)
    if compatibility is not None:
        return (paths.project_root / compatibility).resolve()
    return paths.analyzer_dir / module


def module_route(
    module: str,
    module_overrides: Mapping[str, Path] | None = None,
) -> str:
    if module in (module_overrides or {}):
        return "modular"
    if module in RELOCATED_COMPATIBILITY_MODULES:
        return "relocated-compatibility"
    return "legacy"


def _newest_mtime(paths: tuple[Path, ...]) -> float:
    times: list[float] = []
    for path in paths:
        if path.is_file():
            times.append(path.stat().st_mtime)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    try:
                        times.append(child.stat().st_mtime)
                    except OSError:
                        pass
    return max(times, default=0.0)


def outputs_follow_data(step: Any) -> bool:
    """Legacy-safe bootstrap check that ignores a newly installed route."""
    if not step.outputs or not all(path.exists() for path in step.outputs):
        return False
    return min(
        path.stat().st_mtime for path in step.outputs
    ) >= _newest_mtime(tuple(step.inputs))


def _step_key(step: Any) -> str:
    key = f"{step.stage}:{step.label}:{step.module}"
    return f"{key}:{step.revision}" if step.revision else key


def _execution_environment(paths: ExecutionPaths) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (
            str(paths.project_root),
            environment.get("PYTHONPATH", ""),
        )
        if value
    )
    defaults = {
        "ARCHON_RESULTS_DIR": paths.search_results_dir,
        "ARCHON_ANALYSIS_DIR": paths.analysis_results_dir,
        "ARCHON_KNOWLEDGE_ATLAS_DIR": paths.knowledge_atlas_dir,
        "ARCHON_WORLD_ATLAS_DIR": paths.world_atlas_dir,
    }
    for name, path in defaults.items():
        environment.setdefault(name, str(path.resolve()))
    return environment


def run_step(
    step: Any,
    dag: Any,
    *,
    paths: ExecutionPaths,
    dry_run: bool = False,
    force: bool = False,
    module_overrides: Mapping[str, Path] | None = None,
) -> bool:
    """Inspect, execute, canonicalize, and record one declarative step."""
    path = module_path(
        step.module,
        paths=paths,
        module_overrides=module_overrides,
    )
    if not path.exists():
        status = "SKIP" if step.optional else "FAILED"
        print(f"[{status}] {step.label}: module not found: {path}")
        return bool(step.optional)

    key = _step_key(step)
    implementation_dependencies = modular_implementation_dependencies(
        step.module,
        paths=paths,
        module_overrides=module_overrides,
    )
    decision = dag.inspect(
        key,
        inputs=(*step.inputs, path, *implementation_dependencies),
        outputs=step.outputs,
    )
    delta = decision.delta
    print(
        f"[DAG] {step.label}: new={delta['new']} "
        f"changed={delta['changed']} reused={delta['reused']} "
        f"removed={delta['removed']}"
    )
    if (
        not force
        and not step.revision
        and not dag.has_step(key)
        and module_route(step.module, module_overrides) == "legacy"
        and outputs_follow_data(step)
    ):
        dag.record(
            key,
            decision=decision,
            outputs=step.outputs,
            status="ok",
        )
        print(f"[SKIP] {step.label}: bootstrapped current Stage 2F outputs")
        return True
    if not force and decision.current:
        print(f"[SKIP] {step.label}: content dependencies are current")
        dag.flush()
        return True

    command = [sys.executable, str(path), *step.args]
    print("\n" + "=" * 72)
    print("Running:", step.label)
    print("=" * 72)
    print("Route:", module_route(step.module, module_overrides))
    print("Command:", " ".join(command))
    if dry_run:
        return True

    completed = subprocess.run(
        command,
        cwd=str(paths.project_root),
        env=_execution_environment(paths),
    )
    succeeded = completed.returncode == 0
    status = "OK" if succeeded else "FAILED"
    suffix = "" if succeeded else f" exited with code {completed.returncode}"
    print(f"[{status}] {step.label}{suffix}")
    if succeeded:
        alias_changes = canonicalize_declared_alias_outputs(
            step,
            knowledge_atlas_dir=paths.knowledge_atlas_dir,
        )
        if alias_changes:
            print(
                f"[DAG] {step.label}: canonicalized "
                f"{alias_changes} alias reference(s) before fingerprint"
            )

    output_changed, _ = dag.record(
        key,
        decision=decision,
        outputs=step.outputs,
        status="ok" if succeeded else "failed",
    )
    if succeeded:
        mode = (
            "scientific-change"
            if output_changed
            else "aggregate-only/no-content-change"
        )
        print(f"[DAG] {step.label}: {mode}")
    return succeeded


__all__ = [
    "ExecutionPaths",
    "MODULAR_IMPLEMENTATION_DEPENDENCIES",
    "RELOCATED_COMPATIBILITY_MODULES",
    "modular_implementation_dependencies",
    "module_path",
    "module_route",
    "outputs_follow_data",
    "run_step",
]
