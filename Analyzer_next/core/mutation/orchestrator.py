"""Incremental orchestration for modular mutation analysis."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Callable

from Analyzer_next.core.experimental_evidence.contract import (
    build_mutation_evidence_contract,
)

from .analyzer import analyze_mutation
from .cache import IncrementalMutationCache
from .constants import PER_MUTATION_ANALYSIS_VERSION, SCHEMA
from .contracts import LifecycleReconciler, MutationRequest, MutationRunResult
from .controls import normalize_required_control_reason
from .discovery import (
    _load_reusable_report,
    _mutation_cache_key,
    _mutation_report_path,
    collect_mutation_dependencies,
)
from .reporting import write_aggregate_reports
from .utils import normalize_rule_id, now_iso, read_json


class MutationOrchestrator:
    """Coordinates discovery, reuse, analysis, and aggregate publication."""

    def __init__(
        self,
        lifecycle_reconciler: LifecycleReconciler,
        *,
        cache_factory: Callable[..., Any] = IncrementalMutationCache,
        analyze_one: Callable[..., dict[str, Any]] = analyze_mutation,
        collect_dependencies: Callable[..., list[Path]] = collect_mutation_dependencies,
        load_report: Callable[..., dict[str, Any] | None] = _load_reusable_report,
        emit: Callable[[str], None] = print,
    ) -> None:
        self._lifecycle_reconciler = lifecycle_reconciler
        self._cache_factory = cache_factory
        self._analyze = analyze_one
        self._collect_dependencies = collect_dependencies
        self._load_report = load_report
        self._emit = emit

    def _analyze_one(
        self,
        manifest_path: Path,
        results_root: Path,
        mutation_root: Path,
        output_root: Path,
    ) -> dict[str, Any]:
        return self._analyze(
            manifest_path,
            results_root,
            mutation_root,
            output_root,
            lifecycle_reconciler=self._lifecycle_reconciler,
        )

    def run(self, request: MutationRequest) -> MutationRunResult:

        results_root = Path(request.results_folder).expanduser().resolve()
        mutation_root = (
            Path(request.mutation_root).expanduser().resolve()
            if request.mutation_root
            else results_root / "mutation_runs"
        )
        project_root = results_root.parent.parent
        output_root = (
            Path(request.out_dir).expanduser().resolve()
            if request.out_dir
            else project_root / "Results" / "Analysis" / "Mutations"
        )

        if not mutation_root.exists():
            if not request.allow_missing_root:
                self._emit(f"[ERROR] Mutation root not found: {mutation_root}")
                return MutationRunResult(
                exit_code=1,
                aggregate=None,
                reports=(),
                failures=(),
                incremental={},
                output_root=output_root,
            )
            self._emit(
                "[NO INPUT] Mutation root not found; "
                f"building an empty mutation aggregate: {mutation_root}"
            )

        wanted_rule = normalize_rule_id(request.rule) if request.rule else None
        manifests = sorted(mutation_root.rglob("mutation_manifest.json"))

        selected: list[Path] = []
        for path in manifests:
            manifest = read_json(path, {})
            rule_id = normalize_rule_id(
                manifest.get("canonical_parent_rule_id")
            )
            mutation_id = str(
                manifest.get("mutation_id") or path.parent.name
            )
            if wanted_rule and rule_id != wanted_rule:
                continue
            if request.mutation_id and mutation_id != request.mutation_id:
                continue
            selected.append(path)

        self._emit("=" * 72)
        self._emit("Project ARCHON Mutation Analyzer v1.5.4")
        self._emit("=" * 72)
        self._emit(f"Results root:  {results_root}")
        self._emit(f"Mutation root: {mutation_root}")
        self._emit(f"Output:        {output_root}")
        self._emit(f"Runs queued:   {len(selected)}")

        reports: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        incremental = {
            "new": 0,
            "changed": 0,
            "reused": 0,
            "removed": 0,
            "bootstrapped": 0,
            "computed": 0,
            "reused_failures": 0,
        }
        cache = self._cache_factory(
            output_root,
            analysis_version=PER_MUTATION_ANALYSIS_VERSION,
        )
        active_keys = {
            _mutation_cache_key(path)
            for path in selected
        }
        if not wanted_rule and not request.mutation_id:
            incremental["removed"] = cache.remove_absent(active_keys)

        for index, manifest_path in enumerate(selected, start=1):
            cache_key = _mutation_cache_key(manifest_path)
            report_path = _mutation_report_path(
                manifest_path,
                output_root,
            )
            input_files: dict[str, str] = {}
            input_digest = ""
            try:
                dependencies = self._collect_dependencies(
                    manifest_path,
                    results_root,
                    mutation_root,
                    output_root,
                )
                input_files, input_digest = cache.snapshot(dependencies)
                previous = cache.previous(cache_key)

                if (
                    not request.force_recompute
                    and cache.is_current(
                        cache_key,
                        input_digest=input_digest,
                        report_path=report_path,
                    )
                ):
                    report = self._load_report(
                        report_path,
                        manifest_path,
                        dependencies,
                        require_newer_than_inputs=False,
                    )
                    if report is not None:
                        reports.append(report)
                        incremental["reused"] += 1
                        self._emit(
                            f"[reuse {index:02d}/{len(selected):02d}] "
                            f"{report['mutation_id']}: "
                            f"{report['effect_interpretation']['primary']} | "
                            "inputs=current"
                        )
                        continue

                if not request.force_recompute:
                    report = self._load_report(
                        report_path,
                        manifest_path,
                        dependencies,
                        require_newer_than_inputs=True,
                    )
                    if report is not None:
                        cache.record_success(
                            cache_key,
                            input_files=input_files,
                            input_digest=input_digest,
                            report_path=report_path,
                            bootstrapped=True,
                        )
                        reports.append(report)
                        incremental["reused"] += 1
                        incremental["bootstrapped"] += 1
                        self._emit(
                            f"[bootstrap {index:02d}/{len(selected):02d}] "
                            f"{report['mutation_id']}: "
                            "reindexed current report"
                        )
                        continue

                if (
                    not request.force_recompute
                    and previous
                    and previous.get("status") == "failed"
                    and previous.get("analysis_version")
                        == PER_MUTATION_ANALYSIS_VERSION
                    and previous.get("input_digest") == input_digest
                ):
                    failure = previous.get("failure")
                    if not isinstance(failure, dict):
                        failure = {
                            "manifest": str(manifest_path),
                            "error": "Cached mutation analysis failure.",
                        }
                    failures.append({
                        "manifest": str(
                            failure.get("manifest") or manifest_path
                        ),
                        "error": str(
                            failure.get("error")
                            or "Cached mutation analysis failure."
                        ),
                    })
                    incremental["reused"] += 1
                    incremental["reused_failures"] += 1
                    self._emit(
                        f"[reuse {index:02d}/{len(selected):02d}] "
                        f"{manifest_path.parent.name}: cached failure"
                    )
                    continue

                if previous is None:
                    incremental["new"] += 1
                else:
                    incremental["changed"] += 1
                incremental["computed"] += 1
                report = self._analyze_one(
                    manifest_path,
                    results_root,
                    mutation_root,
                    output_root,
                )
                final_dependencies = self._collect_dependencies(
                    manifest_path,
                    results_root,
                    mutation_root,
                    output_root,
                )
                input_files, input_digest = cache.snapshot(
                    final_dependencies
                )
                cache.record_success(
                    cache_key,
                    input_files=input_files,
                    input_digest=input_digest,
                    report_path=report_path,
                )
                reports.append(report)
                self._emit(
                    f"[compute {index:02d}/{len(selected):02d}] "
                    f"{report['mutation_id']}: "
                    f"{report['effect_interpretation']['primary']} | "
                    f"baseline={report['baseline_match']['match_type']} | "
                    f"confidence={report['comparison_confidence']['grade']}"
                )
            except Exception as exc:
                failures.append({
                    "manifest": str(manifest_path),
                    "error": str(exc),
                })
                if input_digest:
                    cache.record_failure(
                        cache_key,
                        input_files=input_files,
                        input_digest=input_digest,
                        failure=failures[-1],
                    )
                self._emit(
                    f"[compute {index:02d}/{len(selected):02d}] "
                    f"{manifest_path.parent.name}: FAILED: {exc}"
                )
        cache.flush()
        self._emit(
            "[incremental] "
            f"new={incremental['new']} "
            f"changed={incremental['changed']} "
            f"reused={incremental['reused']} "
            f"removed={incremental['removed']} "
            f"bootstrapped={incremental['bootstrapped']} "
            f"computed={incremental['computed']}"
        )

        required_controls = [
            normalize_required_control_reason(report["required_control"])
            for report in reports
            if report.get("required_control")
        ]

        effect_counts = Counter(
            report.get("effect_interpretation", {}).get(
                "primary", "unknown"
            )
            for report in reports
        )
        confidence_counts = Counter(
            report.get("comparison_confidence", {}).get(
                "grade", "MISSING"
            )
            for report in reports
        )
        lifecycle_reconciliation_counts = Counter(
            report.get("perturbation_lifecycle_reconciliation", {}).get(
                "verification_status", "unavailable"
            )
            for report in reports
        )

        aggregate = {
            "schema": SCHEMA,
            "generated": now_iso(),
            "results_root": str(results_root),
            "mutation_root": str(mutation_root),
            "output_root": str(output_root),
            "scientific_policy": {
                "compare_with_canonical_original": True,
                "canonical_evidence": False,
                "independent_replication": False,
                "automatic_promotion": False,
            },
            "summary": {
                "runs": len(selected),
                "analyzed": len(reports),
                "failed": len(failures),
                "effect_counts": dict(effect_counts),
                "confidence_counts": dict(confidence_counts),
                "lifecycle_reconciliation_counts": dict(
                    lifecycle_reconciliation_counts
                ),
                "required_controls": len(required_controls),
                "incremental": incremental,
            },
            "required_controls": required_controls,
            "reports": reports,
            "failures": failures,
        }
        aggregate["experimental_evidence_contract"] = (
            build_mutation_evidence_contract(aggregate)
        )
        self._emit(
            "[BRIDGE5.4] experimental evidence contract: "
            f"records={aggregate['experimental_evidence_contract']['record_count']} "
            "consumer_raw_reports=false"
        )

        json_path, md_path, controls_json_path, aggregate_changed = (
            write_aggregate_reports(
                output_root,
                aggregate,
                required_controls,
            )
        )
        if not aggregate_changed:
            self._emit(
                "[incremental] aggregate scientific content unchanged; "
                "existing outputs preserved"
            )

        self._emit("-" * 72)
        self._emit(
            f"Analyzed: {len(reports)} "
            f"({incremental['computed']} computed, "
            f"{incremental['reused']} reused)"
        )
        self._emit(f"Failed:   {len(failures)}")
        self._emit(f"JSON:     {json_path}")
        self._emit(f"Markdown: {md_path}")
        self._emit(f"Controls: {controls_json_path}")
        self._emit(f"Required: {len(required_controls)}")
        self._emit("=" * 72)

        return MutationRunResult(
            exit_code=0 if not failures else 2,
            aggregate=aggregate,
            reports=tuple(reports),
            failures=tuple(failures),
            incremental=dict(incremental),
            output_root=output_root,
        )
