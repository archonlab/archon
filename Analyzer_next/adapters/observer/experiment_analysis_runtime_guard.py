"""Runtime-backed guardrails for experiment interpretation.

Experiment Analyzer v1.4 compares telemetry arms after profile matching, but the
legacy analysis contract does not inspect the immutable runtime package.  That
means a row labelled ``treatment`` can be interpreted as a scientific contrast
even when its launch configuration is identical to baseline and no intervention
was materialized.  This module audits the runtime package without changing the
frozen legacy analyzer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeContrastAudit:
    status: str
    runtime_id: str | None = None
    experiment_type: str | None = None
    package_path: str | None = None
    baseline_rows: int = 0
    treatment_rows: int = 0
    paired_rows: int = 0
    explicit_interventions: int = 0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _runtime_packages_root(project_root: Path) -> Path:
    return (
        Path(project_root).resolve()
        / "Results"
        / "Analysis"
        / "Experiments"
        / "RuntimePackages"
    )


def find_runtime_package(
    project_root: Path,
    experiment_id: str,
    *,
    source_runtime_id: str | None = None,
) -> tuple[Path | None, dict[str, Any]]:
    """Resolve the immutable source runtime for an analyzed experiment.

    OL2 execution attempts deliberately clone the experiment row so repeated
    executions never overwrite the source experiment.  The immutable runtime
    package therefore keeps the *source* experiment id while telemetry is
    written under an ``EXP-EXEC-*`` clone id.  ``source_runtime_id`` is the
    authoritative join key for those execution clones.  The historical
    experiment-id scan remains as a compatibility fallback for pre-clone data.
    """
    root = _runtime_packages_root(project_root)
    if not root.is_dir():
        return None, {}

    runtime_id = str(source_runtime_id or "").strip()
    if runtime_id:
        path = root / runtime_id / "runtime_package.json"
        payload = _load_json(path)
        if not payload:
            return None, {}
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        declared_runtime_id = str(
            runtime.get("runtime_id")
            or payload.get("runtime_id")
            or runtime_id
        ).strip()
        if declared_runtime_id != runtime_id:
            return None, {}
        return path, payload

    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.glob("*/runtime_package.json")):
        payload = _load_json(path)
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        candidate = str(
            runtime.get("experiment_id")
            or payload.get("experiment_id")
            or ""
        )
        if candidate == str(experiment_id):
            matches.append((path, payload))
    if len(matches) != 1:
        return None, {}
    return matches[0]


def _role(row: dict[str, Any]) -> str:
    value = str(row.get("role") or "").strip().upper()
    if value in {"BASELINE", "BASELINE_CONTROL", "CONTROL"}:
        return "baseline"
    if value in {"TREATMENT", "TEST"}:
        return "treatment"
    return value.lower()


def _pair_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return row.get("rule_id"), row.get("replicate_index")


def _launch_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    field = row.get("field_size")
    if isinstance(field, list):
        field_value: Any = tuple(field)
    elif isinstance(field, tuple):
        field_value = field
    else:
        field_value = field
    return (
        row.get("condition_id"),
        row.get("rule_id"),
        row.get("seed"),
        field_value,
        row.get("topology"),
        row.get("boundary_condition"),
        row.get("duration_ticks"),
        row.get("initial_state_mode"),
    )


def audit_runtime_contrast(
    project_root: Path,
    experiment_id: str,
    *,
    source_runtime_id: str | None = None,
) -> RuntimeContrastAudit:
    path, package = find_runtime_package(
        project_root,
        experiment_id,
        source_runtime_id=source_runtime_id,
    )
    if path is None:
        return RuntimeContrastAudit(
            status="RUNTIME_PACKAGE_UNAVAILABLE",
            reason="exact runtime package for experiment was not found",
        )

    runtime = package.get("runtime") if isinstance(package.get("runtime"), dict) else {}
    matrix = [
        row for row in runtime.get("run_matrix", [])
        if isinstance(row, dict)
    ]
    baseline = [row for row in matrix if _role(row) == "baseline"]
    treatment = [row for row in matrix if _role(row) == "treatment"]
    experiment_type = str(runtime.get("experiment_type") or "").strip() or None
    runtime_id = str(runtime.get("runtime_id") or package.get("runtime_id") or "").strip() or None
    interventions = sum(
        row.get("perturbation") not in (None, {}, [])
        for row in treatment
    )

    if not treatment:
        return RuntimeContrastAudit(
            status="NO_TREATMENT_ARM",
            runtime_id=runtime_id,
            experiment_type=experiment_type,
            package_path=str(path),
            baseline_rows=len(baseline),
            treatment_rows=0,
            explicit_interventions=0,
            reason="runtime contains no treatment arm",
        )

    baseline_by_key = {_pair_key(row): row for row in baseline}
    paired = 0
    all_pairs_identical = bool(treatment)
    for row in treatment:
        base = baseline_by_key.get(_pair_key(row))
        if base is None:
            all_pairs_identical = False
            continue
        paired += 1
        if _launch_signature(base) != _launch_signature(row):
            all_pairs_identical = False

    if interventions > 0 or not all_pairs_identical:
        return RuntimeContrastAudit(
            status="DISTINCT_TREATMENT_CONTRAST",
            runtime_id=runtime_id,
            experiment_type=experiment_type,
            package_path=str(path),
            baseline_rows=len(baseline),
            treatment_rows=len(treatment),
            paired_rows=paired,
            explicit_interventions=interventions,
            reason="treatment differs by materialized intervention or launch configuration",
        )

    status = (
        "REPLICATION_ONLY"
        if experiment_type == "metric_validation_baseline"
        else "INVALID_TREATMENT_CONTRAST"
    )
    reason = (
        "metric baseline runtime duplicates matched launch configurations; "
        "interpret as reproducibility evidence only"
        if status == "REPLICATION_ONLY"
        else "treatment rows are launch-equivalent to baseline and contain no intervention"
    )
    return RuntimeContrastAudit(
        status=status,
        runtime_id=runtime_id,
        experiment_type=experiment_type,
        package_path=str(path),
        baseline_rows=len(baseline),
        treatment_rows=len(treatment),
        paired_rows=paired,
        explicit_interventions=0,
        reason=reason,
    )


__all__ = [
    "RuntimeContrastAudit",
    "audit_runtime_contrast",
    "find_runtime_package",
]
