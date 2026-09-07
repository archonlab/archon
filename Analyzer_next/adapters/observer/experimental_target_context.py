"""Resolve one immutable ScientificTarget from runtime/Observer provenance."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from Analyzer_next.adapters.observer.historical_target_recovery import (
    recover_historical_target,
)
from Analyzer_next.core.experimental_evidence.targeting import (
    validate_scientific_target,
)


@dataclass(frozen=True, slots=True)
class ResolvedExperimentalTarget:
    target: dict[str, Any] | None
    runtime_package: dict[str, Any]
    runtime_path: str | None
    source_runtime_id: str | None
    status: str
    reasons: tuple[str, ...] = ()
    recovery: dict[str, Any] | None = None


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _runtime_ids(
    experiment_metadata: Mapping[str, Any],
    rows: Iterable[Mapping[str, Any]],
) -> list[str]:
    values: list[str] = []
    direct = str(experiment_metadata.get("source_runtime_id") or "").strip()
    if direct:
        values.append(direct)
    for row in rows:
        context = _as_dict(row.get("experimental_context"))
        attempt = _as_dict(context.get("execution_attempt"))
        value = str(
            attempt.get("source_runtime_id")
            or context.get("source_runtime_id")
            or ""
        ).strip()
        if value and value not in values:
            values.append(value)
    return values


def resolve_experimental_target(
    *,
    project_root: Path,
    experiment_id: str,
    rows: Iterable[Mapping[str, Any]],
    experiment_metadata: Mapping[str, Any],
) -> ResolvedExperimentalTarget:
    materialized_rows = list(rows)
    candidates: list[dict[str, Any]] = []
    metadata_target = experiment_metadata.get("scientific_target")
    if isinstance(metadata_target, Mapping):
        candidates.append(dict(metadata_target))
    for row in materialized_rows:
        context = _as_dict(row.get("experimental_context"))
        target = context.get("scientific_target")
        if isinstance(target, Mapping):
            candidates.append(dict(target))

    runtime_ids = _runtime_ids(experiment_metadata, materialized_rows)
    runtime_package: dict[str, Any] = {}
    runtime_path: Path | None = None
    if len(runtime_ids) > 1:
        return ResolvedExperimentalTarget(
            target=None,
            runtime_package={},
            runtime_path=None,
            source_runtime_id=None,
            status="CONFLICT",
            reasons=("MULTIPLE_SOURCE_RUNTIME_IDS",),
        )
    runtime_id = runtime_ids[0] if runtime_ids else None
    if runtime_id:
        runtime_path = (
            Path(project_root).resolve()
            / "Results"
            / "Analysis"
            / "Experiments"
            / "RuntimePackages"
            / runtime_id
            / "runtime_package.json"
        )
        runtime_package = _load(runtime_path)
        runtime = _as_dict(runtime_package.get("runtime"))
        target = runtime.get("scientific_target")
        if isinstance(target, Mapping):
            candidates.append(dict(target))

    if not candidates:
        historical = recover_historical_target(
            project_root=project_root,
            experiment_id=experiment_id,
            experiment_metadata=experiment_metadata,
            runtime_package=runtime_package,
        )
        if historical.status == "RECOVERED":
            return ResolvedExperimentalTarget(
                target=historical.target,
                runtime_package=runtime_package,
                runtime_path=str(runtime_path) if runtime_path else None,
                source_runtime_id=runtime_id,
                status="RECOVERED",
                recovery=historical.recovery,
            )
        if historical.status == "REFUSED":
            return ResolvedExperimentalTarget(
                target=None,
                runtime_package=runtime_package,
                runtime_path=str(runtime_path) if runtime_path else None,
                source_runtime_id=runtime_id,
                status="HISTORICAL_RECOVERY_REFUSED",
                reasons=historical.reasons,
            )
        return ResolvedExperimentalTarget(
            target=None,
            runtime_package=runtime_package,
            runtime_path=str(runtime_path) if runtime_path else None,
            source_runtime_id=runtime_id,
            status="NOT_TARGETED",
        )

    valid_candidates: list[dict[str, Any]] = []
    failures: list[str] = []
    for candidate in candidates:
        valid, reasons = validate_scientific_target(candidate)
        if valid:
            valid_candidates.append(candidate)
        else:
            failures.extend(reasons)
    if failures:
        return ResolvedExperimentalTarget(
            target=None,
            runtime_package=runtime_package,
            runtime_path=str(runtime_path) if runtime_path else None,
            source_runtime_id=runtime_id,
            status="INVALID",
            reasons=tuple(sorted(set(failures))),
        )
    hashes = {str(candidate.get("target_hash")) for candidate in valid_candidates}
    if len(hashes) != 1:
        return ResolvedExperimentalTarget(
            target=None,
            runtime_package=runtime_package,
            runtime_path=str(runtime_path) if runtime_path else None,
            source_runtime_id=runtime_id,
            status="CONFLICT",
            reasons=("SCIENTIFIC_TARGET_PROVENANCE_CONFLICT",),
        )
    return ResolvedExperimentalTarget(
        target=valid_candidates[0],
        runtime_package=runtime_package,
        runtime_path=str(runtime_path) if runtime_path else None,
        source_runtime_id=runtime_id,
        status="RESOLVED",
    )


__all__ = [
    "ResolvedExperimentalTarget",
    "resolve_experimental_target",
]
