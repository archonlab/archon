"""Per-mutation and aggregate Markdown reporting."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .controls import render_control_markdown
from .utils import now_iso, read_json, write_json_atomic

def render_mutation_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ARCHON Mutation Report",
        "",
        f"Generated: **{report['generated']}**",
        f"Mutation: **{report['mutation_id']}**",
        f"Canonical parent: **{report['parent_rule_id']}**",
        f"Experiment type: **mutation**",
        "",
        "## Mutation",
        "",
        f"- Mode: **{report.get('mutation_mode')}**",
        f"- Parameter: **{report.get('mutation_parameter')}**",
        f"- Intensity: **{report.get('mutation_intensity')}**",
        f"- Changed fields: **{len(report.get('changes', []))}**",
        "",
    ]

    for change in report.get("changes", []):
        lines.append(
            f"- `{change.get('path')}`: "
            f"`{change.get('before')}` → `{change.get('after')}`"
        )

    match = report.get("baseline_match", {})
    confidence = report.get("comparison_confidence", {})
    lines += [
        "",
        "## Baseline",
        "",
        f"- Match type: **{match.get('match_type')}**",
        f"- Same seed: **{match.get('same_seed')}**",
        f"- Coverage: **{match.get('coverage_ratio')}**",
        f"- Confidence: **{confidence.get('grade')} "
        f"({confidence.get('score')})**",
        f"- Baseline samples: `{match.get('path')}`",
        f"- Comparison horizon: **0..{report.get('comparison_horizon', {}).get('end_tick')} ticks**",
        f"- Baseline rows used: **{report.get('comparison_horizon', {}).get('baseline_rows_used')}** "
        f"of {report.get('comparison_horizon', {}).get('baseline_rows_full')}",
        "",
        "## Effect",
        "",
        f"- Primary interpretation: "
        f"**{report.get('effect_interpretation', {}).get('primary')}**",
        f"- Labels: **{', '.join(report.get('effect_interpretation', {}).get('labels', []))}**",
    ]

    for evidence in report.get("effect_interpretation", {}).get("evidence", []):
        lines.append(f"- {evidence}")

    extinction = report.get("structural_extinction_comparison", {})
    if (
        extinction.get("baseline_structural_extinction_tick") is not None
        or extinction.get("mutant_structural_extinction_tick") is not None
    ):
        lines += [
            "",
            "## Structural extinction comparison",
            "",
            f"- Baseline structural extinction tick: "
            f"**{extinction.get('baseline_structural_extinction_tick')}**",
            f"- Mutant structural extinction tick: "
            f"**{extinction.get('mutant_structural_extinction_tick')}**",
            f"- Tick delta: **{extinction.get('tick_delta')}**",
            f"- Method: **{extinction.get('method')}**",
            f"- Grace samples: **{extinction.get('grace_samples')}**",
            f"- Classification: **{extinction.get('classification')}**",
            "- Life claim: **False**",
            "- Note: this is a technical zero-structure criterion, not a "
            "Life Detector verdict.",
        ]

    lifecycle = report.get("perturbation_lifecycle_reconciliation", {})
    if lifecycle:
        baseline_lifecycle = lifecycle.get("baseline", {})
        mutant_lifecycle = lifecycle.get("mutant", {})
        effect_relation = lifecycle.get("effect_relation", {})
        baseline_resolution = baseline_lifecycle.get(
            "source_resolution", {}
        )
        mutant_resolution = mutant_lifecycle.get(
            "source_resolution", {}
        )
        lines += [
            "",
            "## Typed lifecycle reconciliation (shadow)",
            "",
            f"- Verification: **{lifecycle.get('verification_status')}**",
            f"- Baseline relation: **{baseline_lifecycle.get('relation')}**",
            f"- Mutant relation: **{mutant_lifecycle.get('relation')}**",
            f"- Typed effect relation: **{effect_relation.get('status')}**",
            f"- Baseline typed events: **{', '.join(baseline_lifecycle.get('event_types', [])) or '-'}**",
            f"- Mutant typed events: **{', '.join(mutant_lifecycle.get('event_types', [])) or '-'}**",
            f"- Baseline lifecycle source: "
            f"**{baseline_resolution.get('method') or baseline_resolution.get('reason', 'unavailable')}**",
            f"- Mutant lifecycle source: "
            f"**{mutant_resolution.get('method') or mutant_resolution.get('reason', 'unavailable')}**",
            f"- Baseline passport: `{baseline_lifecycle.get('passport_path') or '-'}`",
            f"- Mutant passport: `{mutant_lifecycle.get('passport_path') or '-'}`",
            f"- Baseline temporal integrity: "
            f"**{baseline_lifecycle.get('temporal_integrity', {}).get('status', 'unavailable')}**"
            f" ({', '.join(baseline_lifecycle.get('temporal_integrity', {}).get('issue_codes', [])) or '-'})",
            f"- Mutant temporal integrity: "
            f"**{mutant_lifecycle.get('temporal_integrity', {}).get('status', 'unavailable')}**"
            f" ({', '.join(mutant_lifecycle.get('temporal_integrity', {}).get('issue_codes', [])) or '-'})",
            f"- Interpretation: {effect_relation.get('explanation')}",
            "- This reconciliation is descriptive and does not replace the "
            "Mutation Analyzer effect.",
        ]

    lines += [
        "",
        "## Core tail-median deltas",
        "",
        "| Metric | Baseline | Mutant | Absolute Δ | Relative Δ |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    core = [
        "total_living_mass",
        "objects",
        "stability_index",
        "evo_extinction_risk",
        "knowledge_score",
        "feedback_score",
        "emergence_score",
        "validation_quality",
        "morphology_change_rate",
        "total_drift",
    ]
    delta = report.get("metric_delta", {}).get("tail_median", {})
    for metric in core:
        item = delta.get(metric)
        if not item:
            continue
        rel = item.get("relative_delta")
        rel_text = f"{rel:.2%}" if isinstance(rel, (int, float)) else "n/a"
        lines.append(
            f"| {metric} | {item.get('baseline')} | {item.get('mutant')} | "
            f"{item.get('absolute_delta')} | {rel_text} |"
        )

    control = report.get("required_control")
    if control:
        lines += [
            "",
            "## Required control",
            "",
            f"- Reason: **{control.get('reason')}**",
            f"- Canonical rule: **{control.get('canonical_rule_id')}**",
            f"- Seed: **{control.get('canonical_rule_seed')}**",
            f"- Target ticks: **{control.get('target_ticks')}**",
            f"- Sample interval: **{control.get('sample_interval')}**",
            "- Mutation enabled: **False**",
        ]

    warnings = report.get("warnings", [])
    if warnings:
        lines += ["", "## Warnings", ""]
        lines.extend(f"- {warning}" for warning in warnings)

    lines += [
        "",
        "## Scientific status",
        "",
        "- Primary conclusions use only the shared observation horizon.",
        "- The full canonical run is retained as context, not as the comparison tail.",
        "- Structural extinction is a technical zero-structure state, not a life verdict.",
        "- This experiment is perturbation evidence.",
        "- It is not an independent replication of the canonical rule.",
        "- It does not create or modify a canonical Atlas rule.",
        "",
    ]
    return "\n".join(lines)


def write_mutation_report(
    output_root: Path,
    parent_rule_id: str,
    mutation_id: str,
    report: dict[str, Any],
    required_control: dict[str, Any] | None,
) -> dict[str, Any]:
    """Publish one mutation report and remove stale control artifacts."""

    report_dir = output_root / f"rule_{parent_rule_id}" / mutation_id
    json_path = report_dir / "mutation_report.json"
    md_path = report_dir / "mutation_report.md"
    control_json_path = report_dir / "required_control.json"
    control_md_path = report_dir / "required_control.md"
    report["output"] = {
        "json": str(json_path.resolve()),
        "markdown": str(md_path.resolve()),
        "required_control_json": (
            str(control_json_path.resolve()) if required_control else None
        ),
        "required_control_markdown": (
            str(control_md_path.resolve()) if required_control else None
        ),
    }

    if required_control:
        write_json_atomic(control_json_path, required_control)
        control_md_path.parent.mkdir(parents=True, exist_ok=True)
        control_md_path.write_text(
            render_control_markdown(required_control),
            encoding="utf-8",
        )
    else:
        for stale in (control_json_path, control_md_path):
            if stale.exists():
                stale.unlink()

    write_json_atomic(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_mutation_markdown(report), encoding="utf-8")
    return report


def render_aggregate_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# ARCHON Mutation Analysis",
        "",
        f"Generated: **{payload['generated']}**",
        f"Mutation runs: **{payload['summary']['runs']}**",
        f"Analyzed: **{payload['summary']['analyzed']}**",
        f"Failed: **{payload['summary']['failed']}**",
        f"Incremental execution: **{payload['summary'].get('incremental', {})}**",
        f"Lifecycle reconciliation: **{payload['summary'].get('lifecycle_reconciliation_counts', {})}**",
        "",
        "| Mutation | Parent | Parameter | Baseline | Confidence | Effect | Lifecycle | Control |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for report in payload.get("reports", []):
        lines.append(
            f"| {report.get('mutation_id')} | "
            f"{report.get('parent_rule_id')} | "
            f"{report.get('mutation_parameter')} | "
            f"{report.get('baseline_match', {}).get('match_type')} | "
            f"{report.get('comparison_confidence', {}).get('grade')} "
            f"({report.get('comparison_confidence', {}).get('score')}) | "
            f"{report.get('effect_interpretation', {}).get('primary')} | "
            f"{report.get('perturbation_lifecycle_reconciliation', {}).get('verification_status', 'unavailable')} | "
            f"{'REQUIRED' if report.get('required_control') else 'not needed'} |"
        )
    if payload.get("failures"):
        lines += ["", "## Failures", ""]
        for failure in payload["failures"]:
            lines.append(
                f"- `{failure.get('manifest')}`: {failure.get('error')}"
            )
    lines.append("")
    return "\n".join(lines)


def write_aggregate_reports(
    output_root: Path,
    aggregate: dict[str, Any],
    required_controls: list[dict[str, Any]],
) -> tuple[Path, Path, Path, bool]:
    """Publish aggregate and required-control registry atomically."""

    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "mutation_analysis.json"
    md_path = output_root / "mutation_analysis.md"
    previous_aggregate = read_json(json_path, {})
    aggregate_changed = (
        _scientific_payload(previous_aggregate)
        != _scientific_payload(aggregate)
        or not md_path.is_file()
    )
    if aggregate_changed:
        write_json_atomic(json_path, aggregate)
        md_path.write_text(render_aggregate_markdown(aggregate), encoding="utf-8")

    controls_json_path = output_root / "required_controls.json"
    controls_md_path = output_root / "required_controls.md"
    controls_payload = {
        "schema": "archon_required_control_registry_v1",
        "generated": now_iso(),
        "count": len(required_controls),
        "controls": required_controls,
    }
    controls_lines = [
        "# ARCHON Required Controls",
        "",
        f"Generated: **{controls_payload['generated']}**",
        f"Controls required: **{len(required_controls)}**",
        "",
    ]
    for control in required_controls:
        controls_lines += [
            f"## Rule {control.get('canonical_rule_id')}",
            "",
            f"- Source mutation: `{control.get('source_mutation_id')}`",
            f"- Reason: **{control.get('reason')}**",
            f"- Target ticks: **{control.get('target_ticks')}**",
            f"- Sample interval: **{control.get('sample_interval')}**",
            "",
        ]
    if (
        aggregate_changed
        or not controls_json_path.is_file()
        or not controls_md_path.is_file()
    ):
        write_json_atomic(controls_json_path, controls_payload)
        controls_md_path.write_text("\n".join(controls_lines), encoding="utf-8")

    return json_path, md_path, controls_json_path, aggregate_changed


def _scientific_payload(value: Any) -> Any:
    """Remove execution-only fields before comparing aggregate content."""

    if isinstance(value, dict):
        return {
            key: _scientific_payload(item)
            for key, item in value.items()
            if key not in {"generated", "incremental"}
        }
    if isinstance(value, list):
        return [_scientific_payload(item) for item in value]
    return value
