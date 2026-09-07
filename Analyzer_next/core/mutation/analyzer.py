"""One-mutation scientific analysis service."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .baseline import choose_baseline, choose_mutant_samples, discover_baseline_samples, load_csv_rows
from .constants import CONTROL_RESOLUTION_FILENAME, REPORT_SCHEMA
from .contracts import LifecycleReconciler
from .controls import build_required_control
from .discovery import (_declared_passport_paths, _locked_legacy_baseline, _mutation_report_path, _required_control_resolution)
from .lifecycle import lifecycle_contract_for_samples
from .comparison import aligned_differences, comparison_confidence, effect_interpretation
from .feature_builder import summarize_samples, truncate_rows_to_tick
from .metrics import compare_summaries, structural_extinction_comparison
from .experimental import public_resolution, resolve_experimental_mutation
from .reporting import write_mutation_report
from .utils import normalize_rule_id, now_iso, read_json, safe_int

def analyze_mutation(
    manifest_path: Path,
    results_root: Path,
    mutation_root: Path,
    output_root: Path,
    *,
    lifecycle_reconciler: LifecycleReconciler,
) -> dict[str, Any]:
    run_dir = manifest_path.parent
    manifest = read_json(manifest_path, {})
    mutation_id = str(
        manifest.get("mutation_id") or run_dir.name
    )
    parent_rule_id = normalize_rule_id(
        manifest.get("canonical_parent_rule_id")
    )

    warnings: list[str] = []
    if not parent_rule_id:
        raise ValueError(
            f"Missing canonical_parent_rule_id in {manifest_path}"
        )

    paths = manifest.get("paths", {}) if isinstance(
        manifest.get("paths"), dict
    ) else {}

    original_path = run_dir / "original_rule.json"
    mutated_path = run_dir / "mutated_rule.json"
    diff_path = run_dir / "mutation_diff.json"

    for key, fallback in (
        ("original_rule", original_path),
        ("mutated_rule", mutated_path),
        ("mutation_diff", diff_path),
    ):
        declared = paths.get(key)
        if declared and Path(str(declared)).exists():
            if key == "original_rule":
                original_path = Path(str(declared))
            elif key == "mutated_rule":
                mutated_path = Path(str(declared))
            else:
                diff_path = Path(str(declared))

    original_rule = read_json(original_path, {})
    mutated_rule = read_json(mutated_path, {})
    changes = read_json(diff_path, manifest.get("changes", []))
    if not isinstance(changes, list):
        changes = manifest.get("changes", []) or []

    original_seed = original_rule.get("seed")
    experimental_resolution = resolve_experimental_mutation(
        manifest=manifest,
        results_root=results_root,
        run_dir=run_dir,
    )
    experimental_mutation = experimental_resolution is not None
    if (
        experimental_resolution is not None
        and experimental_resolution.get("status") == "RESOLVED"
        and experimental_resolution.get("treatment_samples")
    ):
        mutant_samples = Path(
            str(experimental_resolution["treatment_samples"])
        )
    else:
        mutant_samples = choose_mutant_samples(run_dir)

    if mutant_samples is None:
        warnings.append("Mutation samples CSV is missing.")
        mutant_rows: list[dict[str, str]] = []
    else:
        mutant_rows = load_csv_rows(mutant_samples)

    resolution, resolution_samples, resolution_passport = (
        _required_control_resolution(
            run_dir,
            mutation_id=mutation_id,
            parent_rule_id=parent_rule_id,
        )
    )
    explicit_baseline = (
        manifest.get("baseline_samples")
        or manifest.get("baseline_path")
        or paths.get("baseline_samples")
    )
    if experimental_mutation:
        if (
            experimental_resolution is not None
            and experimental_resolution.get("status") == "RESOLVED"
            and mutant_samples is not None
        ):
            baseline_path_value = str(
                experimental_resolution.get("baseline_samples") or ""
            )
            baseline_tick = safe_int(
                experimental_resolution.get("baseline_final_tick")
            )
            mutant_tick = safe_int(
                experimental_resolution.get("treatment_final_tick")
            )
            coverage = (
                min(1.0, baseline_tick / max(1, mutant_tick))
                if baseline_tick is not None and mutant_tick is not None
                else 0.0
            )
            baseline_match = {
                "path": baseline_path_value or None,
                "match_type": "matched_experiment_control",
                "same_seed": experimental_resolution.get("same_seed") is True,
                "coverage_ratio": round(coverage, 4),
                "reason": (
                    "Authoritative matched unperturbed control from the same "
                    "experiment, rule, replicate, seed, and horizon."
                ),
                "seed_verification": "verified_from_experiment_registry",
                "treatment_run_id": experimental_resolution.get("treatment_run_id"),
                "baseline_run_id": experimental_resolution.get("baseline_run_id"),
            }
        else:
            reason = (
                experimental_resolution.get("reason")
                if isinstance(experimental_resolution, dict)
                else "experimental_resolution_missing"
            )
            baseline_match = {
                "path": None,
                "match_type": "missing",
                "same_seed": None,
                "coverage_ratio": 0.0,
                "reason": (
                    "Authoritative matched experimental control unresolved; "
                    f"canonical fallback refused ({reason})."
                ),
            }
    else:
        locked_legacy_baseline = (
            _locked_legacy_baseline(
                _mutation_report_path(manifest_path, output_root),
                results_root,
                mutation_root,
                parent_rule_id,
            )
            if not explicit_baseline and resolution_samples is None
            else None
        )
        baseline_candidates = (
            [locked_legacy_baseline]
            if locked_legacy_baseline is not None
            else discover_baseline_samples(
                results_root,
                mutation_root,
                parent_rule_id,
            )
        )
        effective_explicit_baseline = (
            str(resolution_samples)
            if resolution_samples is not None
            else str(explicit_baseline) if explicit_baseline else None
        )
        baseline_match = choose_baseline(
            baseline_candidates,
            mutant_samples if mutant_samples else run_dir / "missing.csv",
            original_seed,
            effective_explicit_baseline,
        ) if mutant_samples else {
            "path": None,
            "match_type": "missing",
            "same_seed": None,
            "coverage_ratio": 0.0,
            "reason": "Mutation samples missing.",
        }
        if resolution_samples is not None and baseline_match.get("path"):
            baseline_match["match_type"] = "required_control"
            baseline_match["reason"] = (
                "Completed required control explicitly linked to this mutation."
            )
            baseline_match["control_resolution"] = str(
                (run_dir / CONTROL_RESOLUTION_FILENAME).resolve()
            )

    baseline_path = baseline_match.get("path")
    baseline_rows_full = (
        load_csv_rows(Path(baseline_path))
        if baseline_path
        else []
    )

    mutant_final_tick_full = (
        safe_int(mutant_rows[-1].get("tick"))
        if mutant_rows else None
    )
    baseline_final_tick_full = (
        safe_int(baseline_rows_full[-1].get("tick"))
        if baseline_rows_full else None
    )
    available_final_ticks = [
        tick
        for tick in (baseline_final_tick_full, mutant_final_tick_full)
        if tick is not None
    ]
    comparison_final_tick = (
        min(available_final_ticks)
        if available_final_ticks else None
    )
    baseline_rows = truncate_rows_to_tick(
        baseline_rows_full,
        comparison_final_tick,
    )
    mutant_rows_comparison = truncate_rows_to_tick(
        mutant_rows,
        comparison_final_tick,
    )

    baseline_summary_full = summarize_samples(baseline_rows_full)
    mutant_summary_full = summarize_samples(mutant_rows)
    baseline_summary = summarize_samples(baseline_rows)
    mutant_summary = summarize_samples(mutant_rows_comparison)
    metric_delta = compare_summaries(
        baseline_summary,
        mutant_summary,
    )
    aligned = aligned_differences(
        baseline_rows,
        mutant_rows_comparison,
    )
    original_seed_matches_mutant = (
        original_rule.get("seed") is not None
        and mutated_rule.get("seed") is not None
        and str(original_rule.get("seed")) == str(mutated_rule.get("seed"))
    )
    if experimental_mutation:
        # Experiment seed identity belongs to the execution registry, not the
        # canonical rule snapshot.  Do not overwrite that stronger evidence.
        baseline_match.setdefault(
            "seed_verification",
            "not_verified",
        )
    elif original_seed_matches_mutant:
        baseline_match["same_seed"] = True
        baseline_match["seed_verification"] = (
            "verified_from_original_and_mutated_rule_snapshots"
        )
    else:
        baseline_match["seed_verification"] = "not_verified"

    confidence = comparison_confidence(
        baseline_match,
        baseline_rows,
        mutant_rows_comparison,
    )
    structural_extinction = structural_extinction_comparison(
        baseline_rows,
        mutant_rows_comparison,
    )
    interpretation = effect_interpretation(
        baseline_summary,
        mutant_summary,
        metric_delta,
        aligned,
        confidence,
        structural_extinction,
    )
    shared_passport_roots = [
        results_root / "observation_logs",
        run_dir,
    ]
    if mutant_samples:
        shared_passport_roots.append(Path(mutant_samples).parent)
    if baseline_path:
        shared_passport_roots.append(Path(baseline_path).parent)

    baseline_lifecycle = lifecycle_contract_for_samples(
        Path(baseline_path) if baseline_path else None,
        lifecycle_reconciler,
        search_roots=shared_passport_roots,
        explicit_paths=(
            [resolution_passport]
            if resolution_passport is not None
            else _declared_passport_paths(
                manifest,
                paths,
                run_dir,
                role="baseline",
            )
        ),
    )
    mutant_lifecycle = lifecycle_contract_for_samples(
        mutant_samples,
        lifecycle_reconciler,
        search_roots=shared_passport_roots,
        explicit_paths=_declared_passport_paths(
            manifest,
            paths,
            run_dir,
            role="mutant",
        ),
        expected_source_path=mutated_path,
    )
    lifecycle_reconciliation = lifecycle_reconciler.reconcile_perturbation(
        baseline_lifecycle,
        mutant_lifecycle,
        structural_extinction,
        interpretation,
    )
    if (
        experimental_mutation
        and experimental_resolution is not None
        and experimental_resolution.get("status") == "RESOLVED"
    ):
        baseline_provenance = {
            "status": "resolved",
            "method": "matched_experiment_registry",
            "rule_id": parent_rule_id,
            "expected_seed": experimental_resolution.get("experiment_seed"),
            "samples_path": str(Path(str(baseline_path)).resolve()) if baseline_path else None,
            "passport_path": None,
            "run_id": experimental_resolution.get("baseline_run_id"),
            "samples_final_tick": baseline_final_tick_full,
            "verification": "verified",
            "experiment_id": experimental_resolution.get("experiment_id"),
            "condition_id": experimental_resolution.get("condition_id"),
            "replicate_index": experimental_resolution.get("replicate_index"),
        }
    else:
        baseline_provenance = (
            {
                "status": "resolved",
                "method": "required_control_resolution",
                "rule_id": parent_rule_id,
                "expected_seed": original_seed,
                "samples_path": str(resolution_samples.resolve()),
                "passport_path": (
                    str(resolution_passport.resolve())
                    if resolution_passport is not None else None
                ),
                "run_id": resolution.get("run_id"),
                "samples_final_tick": baseline_final_tick_full,
                "verification": "verified",
            }
            if resolution_samples is not None
            else (
                manifest.get("baseline_provenance")
                if isinstance(manifest.get("baseline_provenance"), dict)
                else {}
            )
        )
    if (
        baseline_provenance.get("status") == "resolved"
        and not experimental_mutation
    ):
        declared_run_id = str(baseline_provenance.get("run_id") or "")
        resolved_run_id = str(
            baseline_lifecycle.get("source_resolution", {}).get(
                "passport_run_id"
            ) or ""
        )
        declared_samples = baseline_provenance.get("samples_path")
        resolved_samples = str(Path(baseline_path).resolve()) if baseline_path else ""
        provenance_ok = (
            declared_run_id
            and declared_run_id == resolved_run_id
            and declared_samples
            and str(Path(str(declared_samples)).resolve()) == resolved_samples
        )
        baseline_provenance = {
            **baseline_provenance,
            "verification": (
                "verified" if provenance_ok else "mismatch"
            ),
            "resolved_run_id": resolved_run_id or None,
            "resolved_samples_path": resolved_samples or None,
        }
        if not provenance_ok:
            warnings.append(
                "Declared baseline provenance did not match the resolved "
                "baseline artifacts."
            )

    if original_rule.get("rule_id") != mutated_rule.get("rule_id"):
        warnings.append(
            "Mutated rule_id differs from original rule_id."
        )
    if len(changes) != manifest.get("change_count", len(changes)):
        warnings.append(
            "mutation_diff length differs from manifest change_count."
        )
    if baseline_match.get("same_seed") is not True:
        warnings.append(
            "Experiment seed could not be confirmed as identical."
        )
    if confidence.get("score", 0.0) < 0.70:
        warnings.append(
            "Comparison is not high-confidence; causal interpretation must "
            "remain provisional."
        )

    if experimental_mutation:
        required_control = None
        if (
            experimental_resolution is None
            or experimental_resolution.get("status") != "RESOLVED"
        ):
            warnings.append(
                "Production experimental mutation could not resolve its "
                "authoritative matched control; canonical fallback is refused."
            )
        else:
            scope = experimental_resolution.get("scientific_scope", {})
            if (
                isinstance(scope, dict)
                and scope.get("direct_claim_eligible") is not True
            ):
                warnings.append(
                    "Experimental perturbation is supporting-program context, "
                    "not direct principle-claim evidence."
                )
    else:
        required_control = build_required_control(
            manifest,
            original_rule,
            baseline_rows_full,
            mutant_rows,
            parent_rule_id,
            baseline_match,
        )

    report = {
        "schema": REPORT_SCHEMA,
        "generated": now_iso(),
        "mutation_id": mutation_id,
        "experiment_type": "mutation",
        "canonical_evidence": False,
        "independent_replication": False,
        "canonical_promotion": bool(
            manifest.get("canonical_promotion", False)
        ),
        "parent_rule_id": parent_rule_id,
        "canonical_parent_hash": manifest.get(
            "canonical_parent_hash"
        ),
        "mutated_hash": manifest.get("mutated_hash"),
        "mutation_mode": manifest.get("mutation_mode"),
        "mutation_parameter": manifest.get("mutation_parameter"),
        "mutation_preset": manifest.get("mutation_preset"),
        "mutation_intensity": manifest.get("mutation_intensity"),
        "mutation_seed": manifest.get("mutation_seed"),
        "status": manifest.get("status"),
        "changes": changes,
        "paths": {
            "run_dir": str(run_dir.resolve()),
            "manifest": str(manifest_path.resolve()),
            "original_rule": str(original_path.resolve()),
            "mutated_rule": str(mutated_path.resolve()),
            "mutation_diff": str(diff_path.resolve()),
            "mutant_samples": (
                str(mutant_samples.resolve())
                if mutant_samples else None
            ),
        },
        "original_rule_summary": {
            "rule_id": normalize_rule_id(original_rule.get("rule_id")),
            "seed": original_seed,
        },
        "mutated_rule_summary": {
            "rule_id": normalize_rule_id(mutated_rule.get("rule_id")),
            "seed": mutated_rule.get("seed"),
        },
        "baseline_match": {
            **baseline_match,
            "path": (
                str(Path(baseline_path).resolve())
                if baseline_path else None
            ),
        },
        "baseline_provenance": baseline_provenance,
        "comparison_horizon": {
            "mode": "shared_tick_horizon",
            "start_tick": 0,
            "end_tick": comparison_final_tick,
            "baseline_rows_used": len(baseline_rows),
            "baseline_rows_full": len(baseline_rows_full),
            "mutant_rows_used": len(mutant_rows_comparison),
            "mutant_rows_full": len(mutant_rows),
        },
        "baseline_metrics": baseline_summary,
        "baseline_full_run_context": baseline_summary_full,
        "mutant_metrics": mutant_summary,
        "mutant_full_run_context": mutant_summary_full,
        "metric_delta": metric_delta,
        "aligned_trajectory_delta": aligned,
        "structural_extinction_comparison": structural_extinction,
        "comparison_confidence": confidence,
        "effect_interpretation": interpretation,
        "perturbation_lifecycle_reconciliation": lifecycle_reconciliation,
        "required_control": required_control,
        "warnings": warnings,
    }
    if experimental_mutation:
        report["experimental_match"] = public_resolution(
            experimental_resolution
        )
        report["scientific_scope"] = (
            dict(experimental_resolution.get("scientific_scope", {}))
            if isinstance(experimental_resolution, dict)
            else {
                "status": "UNVERIFIED",
                "direct_claim_eligible": False,
                "direct_claim_id": None,
            }
        )

    return write_mutation_report(
        output_root,
        parent_rule_id,
        mutation_id,
        report,
        required_control,
    )
