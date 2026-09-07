"""POSTSEARCH1 scientific completion reconciliation for Universe Search.

This adapter closes the lifecycle opened by BRIDGE4.  It consumes the
machine-readable Search target outcome emitted by Universe Search v34.5+ and
updates only Analyzer_next-owned execution registries.  Legacy BRIDGE4 runs
that predate the outcome receipt can be reconstructed conservatively from the
finished log + checkpoint, but are never upgraded to TARGET_NOT_FOUND when the
old target scorer failed to evaluate a required boolean constraint.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from Analyzer_next.adapters.observer.cohort_search_execution_handoff import (
    SEARCH_COMPLETED_STATUS,
    SEARCH_STARTED_STATUS,
    _atomic_json,
    _canonical_hash,
    _refresh_auth_registry_hash,
    _refresh_runtime_registry_hash,
)

POSTSEARCH_BRIDGE_ID = "POSTSEARCH1"
OUTCOME_SCHEMA = "archon_search_target_outcome_v1"
OUTCOME_REGISTRY_SCHEMA = "archon_search_execution_outcome_registry_v1"
_ALLOWED_SCIENTIFIC_STATUSES = {
    "TARGET_FOUND",
    "TARGET_NOT_FOUND",
    "TARGET_INCONCLUSIVE",
}
_TARGET_LINE = re.compile(
    r"\[TargetScoring\]\s+gen=(\d+)\s+exact=(\d+)\s+"
    r"best_rule=([^\s]+)\s+distance=([^\s]+)\s+coverage=([^\s]+)"
)


class PostSearchReconciliationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {} if default is None else default
    except (OSError, json.JSONDecodeError) as exc:
        raise PostSearchReconciliationError(f"cannot read {path}: {exc}") from exc


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _resolve(project_root: Path, value: Any) -> Path:
    path = Path(str(value or "")).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class CohortSearchPostSearchReconciler:
    def __init__(self, project_root: Path, *, experiments_root: Path | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self.experiments_root = Path(
            experiments_root
            or self.project_root / "Results" / "Analysis" / "Experiments"
        ).resolve()

    @property
    def runtime_registry_path(self) -> Path:
        return self.experiments_root / "experiment_runtime_registry.json"

    @property
    def authorization_registry_path(self) -> Path:
        return self.experiments_root / "search_launch_authorization_registry.json"

    @property
    def outcome_registry_path(self) -> Path:
        return self.experiments_root / "search_execution_outcome_registry.json"

    def _runtime(self, runtime_id: str) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
        registry = _load(self.runtime_registry_path, {})
        rows = [
            row for row in _as_list(registry.get("packages"))
            if isinstance(row, dict) and str(row.get("runtime_id") or "") == runtime_id
        ]
        if len(rows) != 1:
            raise PostSearchReconciliationError(
                f"runtime {runtime_id!r} is not uniquely registered"
            )
        entry = rows[0]
        package_path = _resolve(self.project_root, entry.get("package_path"))
        package = _load(package_path, {})
        if not isinstance(package, dict) or not package:
            raise PostSearchReconciliationError(f"runtime package missing: {package_path}")
        return registry, entry, package_path, package

    def _dispatch(self, package: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        state = _as_dict(package.get("search_execution_state"))
        dispatch_id = str(state.get("dispatch_id") or "")
        if not dispatch_id:
            raise PostSearchReconciliationError("Search dispatch id is missing")
        path = self.experiments_root / "SearchExecutionDispatches" / f"{dispatch_id}.json"
        payload = _load(path, {})
        if not isinstance(payload, dict) or payload.get("dispatch_id") != dispatch_id:
            raise PostSearchReconciliationError(f"Search dispatch receipt missing/invalid: {path}")
        return path, payload

    def _legacy_outcome(
        self,
        runtime_id: str,
        package: dict[str, Any],
        dispatch: dict[str, Any],
        outcome_path: Path,
    ) -> dict[str, Any]:
        """Conservatively reconstruct one pre-POSTSEARCH1 completed run."""
        runtime = _as_dict(package.get("runtime"))
        search = _as_dict(runtime.get("search_execution"))
        log_path = _resolve(self.project_root, dispatch.get("log_path"))
        checkpoint_path = self.project_root / "Results" / "Universe_Search" / "checkpoint_observer_niches.json"
        if not log_path.exists():
            raise PostSearchReconciliationError(f"legacy Search log missing: {log_path}")
        text = log_path.read_text(encoding="utf-8", errors="replace")
        if "Search complete." not in text:
            raise PostSearchReconciliationError("legacy Search log does not prove completion")
        checkpoint = _load(checkpoint_path, {})
        completed_generation = int(checkpoint.get("completed_generation") or 0)
        budget = _as_dict(search.get("budget"))
        expected_generations = int(budget.get("generations") or 0)
        population = int(budget.get("population") or 0)
        if expected_generations and completed_generation < expected_generations:
            raise PostSearchReconciliationError(
                f"checkpoint only completed {completed_generation}/{expected_generations} generations"
            )

        identity = _as_dict(checkpoint.get("search_config_identity"))
        if search.get("search_job_id") and identity.get("job_id") not in {None, search.get("search_job_id")}:
            raise PostSearchReconciliationError("checkpoint Search job identity mismatch")

        target_lines = []
        for match in _TARGET_LINE.finditer(text):
            generation, exact, best_rule, distance, coverage = match.groups()
            target_lines.append({
                "generation": int(generation),
                "exact_matches": int(exact),
                "best_rule": best_rule,
                "target_distance": _safe_float(distance),
                "target_coverage": _safe_float(coverage),
            })

        best_metrics = _as_dict(_as_dict(checkpoint.get("best_ever")).get("metrics"))
        details = [
            dict(row) for row in _as_list(best_metrics.get("target_constraint_details"))
            if isinstance(row, dict)
        ]
        bool_parse_failure = any(
            row.get("operator") == "?"
            and isinstance(_as_dict(identity.get("constraints")).get(str(row.get("alias"))), bool)
            for row in details
        )
        missing_metrics = [str(x) for x in _as_list(best_metrics.get("target_missing_metrics"))]
        exact_total = sum(int(row.get("exact_matches") or 0) for row in target_lines)
        evaluated_slots = (expected_generations * population) if expected_generations and population else 0

        # Old v1.0 Search scorer could not parse JSON boolean constraints and
        # therefore never evaluated e.g. ``collapsed: true``.  Even a complete
        # 8/8 run is scientifically inconclusive and must not be rewritten as
        # TARGET_NOT_FOUND.
        if bool_parse_failure:
            status = "TARGET_INCONCLUSIVE"
            reason = "LEGACY_BOOLEAN_TARGET_CONSTRAINT_NOT_EVALUATED"
        elif missing_metrics:
            status = "TARGET_INCONCLUSIVE"
            reason = "LEGACY_TARGET_METRIC_COVERAGE_INCOMPLETE"
        elif exact_total > 0:
            status = "TARGET_FOUND"
            reason = "LEGACY_LOG_REPORTS_EXACT_TARGET_MATCH"
        else:
            # Without POSTSEARCH1 generation summaries we cannot prove that all
            # evaluated slots had complete target coverage.
            status = "TARGET_INCONCLUSIVE"
            reason = "LEGACY_RUN_LACKS_FULL_COVERAGE_PROOF"

        outcome = {
            "schema": OUTCOME_SCHEMA,
            "target_scoring_version": best_metrics.get("target_scoring_version") or "legacy",
            "scientific_status": status,
            "reason": reason,
            "search_mode": search.get("search_mode") or identity.get("search_mode"),
            "search_job_id": search.get("search_job_id") or identity.get("job_id"),
            "claim_id": identity.get("claim_id"),
            "target_regime": search.get("target_regime") or identity.get("target_regime"),
            "runtime_id": runtime_id,
            "dispatch_id": dispatch.get("dispatch_id"),
            "search_run_id": checkpoint.get("search_run_id"),
            "constraints": _as_dict(identity.get("constraints")),
            "generations_completed": completed_generation,
            "evaluated_candidate_slots": evaluated_slots,
            "exact_matches": exact_total,
            "full_coverage_candidate_slots": None,
            "partial_coverage_candidate_slots": None,
            "missing_metric_counts": {name: evaluated_slots or 1 for name in missing_metrics},
            "fallback_metric_counts": {},
            "best_target_candidate": {
                "rule_id": _as_dict(_as_dict(checkpoint.get("best_ever")).get("rule")).get("rule_id"),
                "score": _as_dict(checkpoint.get("best_ever")).get("score"),
                "target_match": best_metrics.get("target_match"),
                "target_distance": best_metrics.get("target_distance"),
                "target_coverage": best_metrics.get("target_coverage"),
                "missing_metrics": missing_metrics,
            },
            "legacy_reconstruction": True,
            "legacy_target_lines": target_lines,
            "requires_observer_validation": False,
            "scientific_policy": {
                "missing_metrics_never_count_as_failure": True,
                "target_not_found_requires_full_metric_coverage": True,
                "legacy_boolean_constraint_bug_is_inconclusive": True,
            },
            "generated_at": _now(),
            "bridge": POSTSEARCH_BRIDGE_ID,
        }
        _atomic_json(outcome_path, outcome)
        return outcome

    def _load_or_reconstruct_outcome(
        self,
        runtime_id: str,
        package: dict[str, Any],
        dispatch: dict[str, Any],
    ) -> tuple[Path, dict[str, Any]]:
        state = _as_dict(package.get("search_execution_state"))
        candidate = state.get("outcome_path") or dispatch.get("outcome_path")
        if candidate:
            outcome_path = _resolve(self.project_root, candidate)
        else:
            outcome_path = (
                self.experiments_root
                / "SearchExecutionOutcomes"
                / f"{dispatch.get('dispatch_id')}.json"
            )
        if outcome_path.exists():
            outcome = _load(outcome_path, {})
        else:
            outcome = self._legacy_outcome(runtime_id, package, dispatch, outcome_path)
        if not isinstance(outcome, dict) or outcome.get("schema") != OUTCOME_SCHEMA:
            raise PostSearchReconciliationError("Search outcome receipt schema is invalid")
        if outcome.get("scientific_status") not in _ALLOWED_SCIENTIFIC_STATUSES:
            raise PostSearchReconciliationError("Search outcome scientific_status is invalid")
        for key, expected in (
            ("runtime_id", runtime_id),
            ("dispatch_id", dispatch.get("dispatch_id")),
        ):
            actual = outcome.get(key)
            if actual not in {None, "", expected}:
                raise PostSearchReconciliationError(f"Search outcome {key} mismatch")
        return outcome_path, outcome

    def _update_outcome_registry(self, outcome_path: Path, outcome: dict[str, Any]) -> None:
        registry = _load(self.outcome_registry_path, {})
        if not isinstance(registry, dict):
            registry = {}
        rows = [dict(row) for row in _as_list(registry.get("outcomes")) if isinstance(row, dict)]
        dispatch_id = str(outcome.get("dispatch_id") or "")
        row = {
            "dispatch_id": dispatch_id,
            "runtime_id": outcome.get("runtime_id"),
            "search_job_id": outcome.get("search_job_id"),
            "target_regime": outcome.get("target_regime"),
            "scientific_status": outcome.get("scientific_status"),
            "reason": outcome.get("reason"),
            "outcome_path": str(outcome_path),
            "generated_at": outcome.get("generated_at") or _now(),
            "content_hash": _canonical_hash(outcome),
        }
        rows = [existing for existing in rows if existing.get("dispatch_id") != dispatch_id]
        rows.append(row)
        rows.sort(key=lambda item: str(item.get("generated_at") or ""))
        summary = {
            "count": len(rows),
            "target_found": sum(x.get("scientific_status") == "TARGET_FOUND" for x in rows),
            "target_not_found": sum(x.get("scientific_status") == "TARGET_NOT_FOUND" for x in rows),
            "target_inconclusive": sum(x.get("scientific_status") == "TARGET_INCONCLUSIVE" for x in rows),
        }
        payload = {
            "schema": OUTCOME_REGISTRY_SCHEMA,
            "generated_at": _now(),
            "summary": summary,
            "outcomes": rows,
        }
        payload["content_hash"] = _canonical_hash({"summary": summary, "outcomes": rows})
        _atomic_json(self.outcome_registry_path, payload)

    def reconcile(self, runtime_id: str) -> dict[str, Any]:
        runtime_id = str(runtime_id).strip()
        if not runtime_id:
            raise PostSearchReconciliationError("runtime_id is required")
        registry, entry, package_path, package = self._runtime(runtime_id)
        if entry.get("status") not in {SEARCH_STARTED_STATUS, SEARCH_COMPLETED_STATUS}:
            raise PostSearchReconciliationError(
                f"runtime status is not Search started/completed: {entry.get('status')}"
            )
        dispatch_path, dispatch = self._dispatch(package)
        outcome_path, outcome = self._load_or_reconstruct_outcome(runtime_id, package, dispatch)
        completed_at = outcome.get("generated_at") or _now()

        dispatch["status"] = "COMPLETED"
        dispatch["completed_at"] = completed_at
        dispatch["outcome_path"] = str(outcome_path)
        dispatch["scientific_status"] = outcome.get("scientific_status")
        dispatch["scientific_reason"] = outcome.get("reason")
        dispatch["outcome_hash"] = _canonical_hash(outcome)
        _atomic_json(dispatch_path, dispatch)

        state = _as_dict(package.get("search_execution_state"))
        state.update({
            "execution_started": True,
            "execution_completed": True,
            "completed_at": completed_at,
            "outcome_path": str(outcome_path),
            "scientific_status": outcome.get("scientific_status"),
            "scientific_reason": outcome.get("reason"),
            "outcome_hash": _canonical_hash(outcome),
            "postsearch_bridge": POSTSEARCH_BRIDGE_ID,
        })
        package["search_execution_state"] = state
        package["status"] = SEARCH_COMPLETED_STATUS
        package["updated_at"] = completed_at
        _atomic_json(package_path, package)

        for row in _as_list(registry.get("packages")):
            if isinstance(row, dict) and str(row.get("runtime_id") or "") == runtime_id:
                row["status"] = SEARCH_COMPLETED_STATUS
                row["updated_at"] = completed_at
                row["search_scientific_status"] = outcome.get("scientific_status")
                row["search_scientific_reason"] = outcome.get("reason")
                row["search_outcome_path"] = str(outcome_path)
        _refresh_runtime_registry_hash(registry)
        _atomic_json(self.runtime_registry_path, registry)

        auth_registry = _load(self.authorization_registry_path, {})
        if isinstance(auth_registry, dict):
            for row in _as_list(auth_registry.get("authorizations")):
                if isinstance(row, dict) and str(row.get("runtime_id") or "") == runtime_id:
                    if row.get("dispatch_id") == dispatch.get("dispatch_id"):
                        row["execution_completed"] = True
                        row["execution_completed_at"] = completed_at
                        row["scientific_status"] = outcome.get("scientific_status")
                        row["outcome_path"] = str(outcome_path)
                        row["lifecycle_status"] = "COMPLETED"
            _refresh_auth_registry_hash(auth_registry)
            _atomic_json(self.authorization_registry_path, auth_registry)

        self._update_outcome_registry(outcome_path, outcome)
        return {
            "runtime_id": runtime_id,
            "dispatch_id": dispatch.get("dispatch_id"),
            "runtime_status": SEARCH_COMPLETED_STATUS,
            "scientific_status": outcome.get("scientific_status"),
            "reason": outcome.get("reason"),
            "outcome_path": str(outcome_path),
            "legacy_reconstruction": bool(outcome.get("legacy_reconstruction")),
            "generations_completed": outcome.get("generations_completed"),
            "evaluated_candidate_slots": outcome.get("evaluated_candidate_slots"),
            "exact_matches": outcome.get("exact_matches"),
            "missing_metric_counts": outcome.get("missing_metric_counts") or {},
        }
