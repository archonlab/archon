"""Immutable requests, results, and infrastructure ports for mutations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


class LifecycleReconciler(Protocol):
    def reconcile_contract(
        self,
        lifecycle_summary: Mapping[str, Any] | None,
        observer_state: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        ...

    def reconcile_perturbation(
        self,
        baseline_lifecycle: Mapping[str, Any],
        mutant_lifecycle: Mapping[str, Any],
        structural_extinction: Mapping[str, Any],
        interpretation: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class MutationRequest:
    results_folder: str | Path = "Results/Universe_Search"
    mutation_root: str | Path | None = None
    out_dir: str | Path | None = None
    rule: str | None = None
    mutation_id: str | None = None
    allow_missing_root: bool = False
    force_recompute: bool = False


@dataclass(frozen=True)
class MutationRunResult:
    exit_code: int
    aggregate: dict[str, Any] | None
    reports: tuple[dict[str, Any], ...]
    failures: tuple[dict[str, str], ...]
    incremental: dict[str, int]
    output_root: Path

