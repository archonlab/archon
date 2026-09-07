"""BRIDGE3 cohort/counterexample search runtime semantics.

A cohort-gap program is a Search discovery program with an explicitly separate
Observer-mutation branch.  It is not a matched Observer BASE/TREATMENT
experiment.  This module resolves the existing Experiment Planner Search job,
pins the effective Universe Search engine budget, and emits a reviewable Search
execution contract without authorizing or starting a process.
"""
from __future__ import annotations

from Tools.archon_runtime_python import runtime_python_command

import ast
import hashlib
import json
from pathlib import Path
from typing import Any


COHORT_SEARCH_TYPES = frozenset({"counterexample_search", "cohort_gap_program"})
SEARCH_READY_STATUS = "READY_FOR_SEARCH_LAUNCH_REVIEW"
BRIDGE_ID = "BRIDGE3"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_rule_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        numeric = int(text)
        if numeric <= 0:
            return None
        return str(numeric).zfill(5)
    return text


def _project_root_from_output_root(output_root: Path) -> Path:
    # .../Results/Analysis/Experiments/RuntimePackages
    resolved = Path(output_root).resolve()
    try:
        if (
            resolved.name == "RuntimePackages"
            and resolved.parent.name == "Experiments"
            and resolved.parent.parent.name == "Analysis"
            and resolved.parent.parent.parent.name == "Results"
        ):
            return resolved.parent.parent.parent.parent
    except IndexError:
        pass
    return resolved


def _extract_literal_assignments(path: Path, names: set[str]) -> dict[str, int]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return {}
    values: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value_node = node.value
        for target in targets:
            if not isinstance(target, ast.Name) or target.id not in names:
                continue
            try:
                value = ast.literal_eval(value_node)
            except (ValueError, TypeError):
                continue
            if isinstance(value, int) and value > 0:
                values[target.id] = value
    return values


def universe_search_budget(project_root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    core = Path(project_root) / "Universe_Search" / "universe_search_core.py"
    script = (
        Path(project_root)
        / "Universe_Search"
        / "universe_search_v34_closed_research_cycle.py"
    )
    unresolved: list[dict[str, str]] = []
    constants = _extract_literal_assignments(core, {"POPULATION", "GENERATIONS"})
    population = constants.get("POPULATION")
    generations = constants.get("GENERATIONS")
    if not core.is_file() or population is None or generations is None:
        unresolved.append({
            "field": "search_execution.budget",
            "reason": "SEARCH_ENGINE_BUDGET_UNRESOLVED",
        })
    if not script.is_file():
        unresolved.append({
            "field": "search_execution.command",
            "reason": "UNIVERSE_SEARCH_ENTRYPOINT_MISSING",
        })
    budget = {
        "mode": "ENGINE_DEFAULT_PINNED",
        "population": population,
        "generations": generations,
        "candidate_evaluation_slots": (
            population * generations
            if population is not None and generations is not None
            else None
        ),
        "engine_config_path": str(core),
        "engine_config_sha256": _file_sha256(core),
        "entrypoint_path": str(script),
        "entrypoint_sha256": _file_sha256(script),
    }
    return budget, unresolved


def _expected_job_ids(plan: dict[str, Any]) -> tuple[str | None, str | None]:
    provenance = _as_dict(plan.get("provenance"))
    action_id = str(provenance.get("source_action_id") or "").strip().upper()
    prefix = "EXP-COHORT-"
    if not action_id.startswith(prefix):
        return None, None
    suffix = action_id[len(prefix):]
    return f"SEARCH-{suffix}", f"MUTATE-{suffix}"


def _rule_set(values: list[Any]) -> set[str]:
    return {
        rid
        for rid in (_normalize_rule_id(value) for value in values)
        if rid is not None
    }


def _find_jobs(
    experiment_plan: dict[str, Any],
    plan: dict[str, Any],
    runtime: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    search_jobs = [
        row for row in _as_list(experiment_plan.get("search_jobs"))
        if isinstance(row, dict)
    ]
    mutation_jobs = [
        row for row in _as_list(experiment_plan.get("mutation_jobs"))
        if isinstance(row, dict)
    ]
    expected_search, expected_mutation = _expected_job_ids(plan)

    search_job = None
    if expected_search:
        search_job = next(
            (
                row for row in search_jobs
                if str(row.get("id") or "").strip().upper() == expected_search
            ),
            None,
        )

    runtime_rules = _rule_set(_as_list(runtime.get("rule_ids")))
    if search_job is None and runtime_rules:
        exact_rule_matches = [
            row for row in search_jobs
            if _rule_set(_as_list(row.get("seed_rules"))) == runtime_rules
        ]
        if len(exact_rule_matches) == 1:
            search_job = exact_rule_matches[0]

    mutation_job = None
    if expected_mutation:
        mutation_job = next(
            (
                row for row in mutation_jobs
                if str(row.get("id") or "").strip().upper() == expected_mutation
            ),
            None,
        )
    if mutation_job is None and search_job is not None:
        claim_id = str(search_job.get("claim_id") or "")
        target = str(search_job.get("target_regime") or "")
        matches = [
            row for row in mutation_jobs
            if str(row.get("claim_id") or "") == claim_id
            and str(row.get("target_regime") or "") == target
        ]
        if len(matches) == 1:
            mutation_job = matches[0]
    return search_job, mutation_job


def build_cohort_search_contract(
    *,
    plan: dict[str, Any],
    runtime: dict[str, Any],
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    project_root = _project_root_from_output_root(output_root)
    analysis_root = project_root / "Results" / "Analysis"
    experiment_plan_path = analysis_root / "experiment_plan.json"
    experiment_plan = _load_json(experiment_plan_path)
    unresolved: list[dict[str, str]] = []

    search_job, mutation_job = _find_jobs(experiment_plan, plan, runtime)
    if search_job is None:
        unresolved.append({
            "field": "search_execution.search_job",
            "reason": "SEARCH_JOB_NOT_FOUND",
        })

    budget, budget_unresolved = universe_search_budget(project_root)
    unresolved.extend(budget_unresolved)

    search_mode = str(
        _as_dict(search_job).get("search_mode") or "cohort_target"
    ).strip().lower()
    if search_job is not None and search_mode not in {"cohort_target", "counterexample"}:
        unresolved.append({
            "field": "search_execution.search_mode",
            "reason": "SEARCH_MODE_UNSUPPORTED_FOR_COHORT_PROGRAM",
        })

    seed_rules = [
        rid
        for rid in (
            _normalize_rule_id(value)
            for value in _as_list(_as_dict(search_job).get("seed_rules"))
        )
        if rid is not None
    ]
    if search_job is not None and not seed_rules:
        unresolved.append({
            "field": "search_execution.seed_rules",
            "reason": "SEARCH_JOB_HAS_NO_REFERENCE_RULES",
        })

    script = Path(str(budget.get("entrypoint_path") or ""))
    command: list[str] = []
    if search_job is not None and script.is_file():
        command = [
            *runtime_python_command(project_root),
            "-u",
            str(script),
            "evolve",
            "observer_niches",
            "--search-mode",
            search_mode,
            "--experiment-plan",
            str(experiment_plan_path),
            "--search-job",
            str(search_job.get("id")),
        ]
        for rule_id in seed_rules:
            command.extend(["--seed-rule", rule_id])

    search_execution = {
        "execution_kind": "UNIVERSE_SEARCH",
        "branch": "DISCOVERY",
        "search_mode": search_mode,
        "search_job_id": _as_dict(search_job).get("id"),
        "claim_id": _as_dict(search_job).get("claim_id"),
        "target_regime": _as_dict(search_job).get("target_regime"),
        "constraints": _as_dict(_as_dict(search_job).get("constraints")),
        "reference_rules": seed_rules,
        "output_policy": _as_dict(_as_dict(search_job).get("output_policy")),
        "experiment_plan_path": str(experiment_plan_path),
        "experiment_plan_sha256": _file_sha256(experiment_plan_path),
        "search_job_hash": (
            _canonical_hash(search_job) if search_job is not None else None
        ),
        "score_mode": "observer_niches",
        "budget": budget,
        "command": command,
        "launch_authorized": False,
        "execution_started": False,
    }

    mutation_branch = {
        "execution_kind": "OBSERVER_MUTATION",
        "branch": "INTERVENTION",
        "separate_from_search": True,
        "job_id": _as_dict(mutation_job).get("id"),
        "claim_id": _as_dict(mutation_job).get("claim_id"),
        "target_regime": _as_dict(mutation_job).get("target_regime"),
        "parent_rules": [
            rid
            for rid in (
                _normalize_rule_id(value)
                for value in _as_list(_as_dict(mutation_job).get("parent_rules"))
            )
            if rid is not None
        ],
        "mutation_mode": _as_dict(mutation_job).get("mutation_mode"),
        "isolation_policy": _as_dict(_as_dict(mutation_job).get("isolation_policy")),
        "status": (
            "SEPARATE_ISOLATED_BRANCH"
            if mutation_job is not None
            else "NOT_MATERIALIZED_IN_SEARCH_RUNTIME"
        ),
        "launch_authorized": False,
    }

    return search_execution, mutation_branch, unresolved


def validate_cohort_search_runtime(
    package: dict[str, Any],
    *,
    project_root: Path | None = None,
) -> list[str]:
    failures: list[str] = []
    runtime = _as_dict(package.get("runtime"))
    if package.get("status") != SEARCH_READY_STATUS:
        failures.append("STATUS_NOT_SEARCH_READY")
    if runtime.get("design_integrity_bridge") != BRIDGE_ID:
        failures.append("BRIDGE_ID_MISSING")
    if _as_list(runtime.get("run_matrix")):
        failures.append("OBSERVER_RUN_MATRIX_MUST_BE_EMPTY")
    search = _as_dict(runtime.get("search_execution"))
    if search.get("execution_kind") != "UNIVERSE_SEARCH":
        failures.append("SEARCH_EXECUTION_KIND_INVALID")
    if search.get("search_mode") not in {"cohort_target", "counterexample"}:
        failures.append("SEARCH_MODE_INVALID")
    if not search.get("search_job_id"):
        failures.append("SEARCH_JOB_ID_MISSING")
    if not _as_list(search.get("reference_rules")):
        failures.append("REFERENCE_RULES_MISSING")
    if not _as_list(search.get("command")):
        failures.append("SEARCH_COMMAND_MISSING")
    budget = _as_dict(search.get("budget"))
    if not budget.get("candidate_evaluation_slots"):
        failures.append("SEARCH_BUDGET_MISSING")
    if _as_list(package.get("unresolved_fields")):
        failures.append("UNRESOLVED_FIELDS_PRESENT")
    policy = _as_dict(package.get("policy"))
    if policy.get("launch_authorized") is not False:
        failures.append("LAUNCH_MUST_REMAIN_UNAUTHORIZED")
    if policy.get("observer_treatment_rows_forbidden") is not True:
        failures.append("TREATMENT_GUARD_MISSING")

    if project_root is not None and search:
        project_root = Path(project_root).resolve()
        plan_path = project_root / "Results" / "Analysis" / "experiment_plan.json"
        if _file_sha256(plan_path) != search.get("experiment_plan_sha256"):
            failures.append("EXPERIMENT_PLAN_DRIFT")
        core = project_root / "Universe_Search" / "universe_search_core.py"
        if _file_sha256(core) != budget.get("engine_config_sha256"):
            failures.append("SEARCH_ENGINE_CONFIG_DRIFT")
        entrypoint = (
            project_root
            / "Universe_Search"
            / "universe_search_v34_closed_research_cycle.py"
        )
        if _file_sha256(entrypoint) != budget.get("entrypoint_sha256"):
            failures.append("SEARCH_ENTRYPOINT_DRIFT")
    return sorted(set(failures))


__all__ = [
    "BRIDGE_ID",
    "COHORT_SEARCH_TYPES",
    "SEARCH_READY_STATUS",
    "build_cohort_search_contract",
    "universe_search_budget",
    "validate_cohort_search_runtime",
]
