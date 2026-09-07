"""Markdown projection for the Meta Science report."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.meta_science.numeric import sf, si


def render_markdown(report: dict[str, Any]) -> str:
    age = report.get("knowledge_age", {})
    metrics = report.get("research_metrics", {})
    inputs = report.get("inputs_seen", {})
    growth = report.get("knowledge_growth", {})
    top = report.get("top_principles", [])
    signals = report.get("meta_signals", [])
    health = report.get("laboratory_health", {})
    coverage = report.get("coverage", {})
    pipeline = report.get("prediction_pipeline", {})
    queue = report.get("experiment_queue", {})
    debt = report.get("research_debt", {})
    integrity = report.get("knowledge_integrity", {})
    reference_controls = report.get("reference_controls", {})
    rc_summary = reference_controls.get("summary", {}) if isinstance(reference_controls, dict) else {}
    rc_classes = reference_controls.get("classes", {}) if isinstance(reference_controls, dict) else {}
    scientific_health = report.get("scientific_health", {})
    health_components = scientific_health.get("components", {})
    health_weights = scientific_health.get("weights", {})
    bottlenecks = report.get("bottlenecks", {})
    primary_bottleneck = bottlenecks.get("primary") or {}
    secondary_bottleneck = bottlenecks.get("secondary") or {}
    lines = [
        "# Universe Search Meta Science Report v34.2",
        "",
        "Stage 1: **Knowledge Evolution**. This report observes the research system itself, not the cellular automata directly.",
        "",
        "## Inputs Seen",
        "",
        f"- Observer profiles: **{si(inputs.get('observer_profiles'))}**",
        f"- Observer rules: **{len(inputs.get('observer_rules', []) or [])}**",
        f"- Atlas records: **{si(inputs.get('atlas_records'))}**",
        f"- Evidence claims: **{si(inputs.get('evidence_claims'))}**",
        f"- Consensus principles: **{si(inputs.get('consensus_principles'))}**",
        f"- Consensus DB runs: **{si(inputs.get('consensus_db_runs'))}**",
        "",
        "## Laboratory Health",
        "",
        f"- Rules: **{si(health.get('rules'))}**",
        f"- Passports: **{si(health.get('passports'))}**",
        f"- Atlas records: **{si(health.get('atlas_records'))}**",
        f"- Rules with mechanisms: **{si(health.get('mechanism_rules'))}**",
        f"- Discoveries: **{si(health.get('discoveries'))}**",
        f"- Predictions: **{si(health.get('predictions'))}**",
        f"- Validations: **{si(health.get('validations'))}**",
        f"- Planned experiments: **{si(health.get('experiments_planned'))}**",
        f"- Knowledge integrity: **{'OK' if health.get('integrity_ok') else 'FAILED'}**",
        "",
        "## Coverage",
        "",
        f"- Passport coverage: **{sf(coverage.get('passport_percent')):.1f}%**",
        f"- Atlas coverage: **{sf(coverage.get('atlas_percent')):.1f}%**",
        f"- Mechanism coverage: **{sf(coverage.get('mechanism_percent')):.1f}%**",
        f"- Discovery coverage: **{sf(coverage.get('discovery_percent')):.1f}%**",
        f"- Validation coverage: **{sf(coverage.get('validation_percent')):.1f}%**",
        "",
        "## Reference Control Coverage",
        "",
        f"- Observed classes: **{si(rc_summary.get('observed_classes'))} / {si(rc_summary.get('class_count'), 8)}**",
        f"- Qualified classes: **{si(rc_summary.get('qualified_classes'))} / {si(rc_summary.get('class_count'), 8)}**",
        "",
        *[
            f"- {('✓' if item.get('status') == 'qualified' else '⚠' if item.get('status') == 'observed' else '✗')} "
            f"{item.get('title', class_id)}: **{si(item.get('candidate_count'))}** candidate(s), "
            f"**{si(item.get('qualified_count'))}** qualified"
            for class_id, item in rc_classes.items() if isinstance(item, dict)
        ],
        "",
        "## Prediction Pipeline",
        "",
        f"- Generated: **{si(pipeline.get('generated'))}**",
        f"- Confirmed: **{si(pipeline.get('confirmed'))}**",
        f"- Testing: **{si(pipeline.get('testing'))}**",
        f"- Rejected: **{si(pipeline.get('rejected'))}**",
        f"- Open: **{si(pipeline.get('open'))}**",
        "",
        "## Experiment Queue",
        "",
        f"- Total planned: **{si(queue.get('total'))}**",
        f"- Critical: **{si((queue.get('priority_counts') or {}).get('critical'))}**",
        f"- High: **{si((queue.get('priority_counts') or {}).get('high'))}**",
        f"- Medium: **{si((queue.get('priority_counts') or {}).get('medium'))}**",
        f"- Low: **{si((queue.get('priority_counts') or {}).get('low'))}**",
        "",
        "## Research Debt",
        "",
        f"- Rules without passports: **{si(debt.get('rules_without_passports'))}**",
        f"- Rules without Atlas records: **{si(debt.get('rules_without_atlas_records'))}**",
        f"- Rules without mechanisms: **{si(debt.get('rules_without_mechanisms'))}**",
        f"- Rules without discoveries: **{si(debt.get('rules_without_discoveries'))}**",
        f"- Unresolved predictions: **{si(debt.get('unresolved_predictions'))}**",
        f"- Planned experiments: **{si(debt.get('planned_experiments'))}**",
        "",
        "## Knowledge Integrity",
        "",
        f"- Integrity: **{'OK' if integrity.get('ok') else 'FAILED'}**",
        f"- Broken references: **{si(integrity.get('broken_references'))}**",
        f"- Duplicate links: **{si(integrity.get('duplicate_links'))}**",
        f"- Unknown rules: **{si(integrity.get('unknown_rules'))}**",
        "",
        "## Scientific Health Index",
        "",
        f"- Index: **{sf(scientific_health.get('index')):.3f}** "
        f"(**{sf(scientific_health.get('percent')):.1f}%**, "
        f"{scientific_health.get('grade', 'Unknown')})",
        f"- Integrity: `{sf(health_components.get('integrity')):.3f}` "
        f"(weight {sf(health_weights.get('integrity')):.2f})",
        f"- Knowledge coverage: `{sf(health_components.get('knowledge_coverage')):.3f}` "
        f"(weight {sf(health_weights.get('knowledge_coverage')):.2f})",
        f"- Mechanism coverage: `{sf(health_components.get('mechanism_coverage')):.3f}` "
        f"(weight {sf(health_weights.get('mechanism_coverage')):.2f})",
        f"- Discovery coverage: `{sf(health_components.get('discovery_coverage')):.3f}` "
        f"(weight {sf(health_weights.get('discovery_coverage')):.2f})",
        f"- Validation resolution: `{sf(health_components.get('validation_resolution')):.3f}` "
        f"(weight {sf(health_weights.get('validation_resolution')):.2f})",
        f"- Research debt control: `{sf(health_components.get('research_debt_control')):.3f}` "
        f"(weight {sf(health_weights.get('research_debt_control')):.2f})",
        f"- Scientific stability: `{sf(health_components.get('scientific_stability')):.3f}` "
        f"(weight {sf(health_weights.get('scientific_stability')):.2f})",
        "",
        "This is a laboratory-process health score, not a truth score.",
        "",
        "## Bottleneck Detector",
        "",
        f"- Primary: **{primary_bottleneck.get('title', 'None')}**",
        f"- Primary score: `{sf(primary_bottleneck.get('score')):.3f}`",
        f"- Primary severity: `{sf(primary_bottleneck.get('severity')):.3f}`",
        f"- Maximum index gain if fixed: `+{sf(primary_bottleneck.get('max_index_gain')):.3f}`",
        f"- Projected health index: `{sf(primary_bottleneck.get('projected_index_if_fixed')):.3f}`",
        f"- Blocked experiments: **{si(primary_bottleneck.get('blocked_experiments'))}**",
        f"- Blocked predictions: **{', '.join(primary_bottleneck.get('blocked_predictions', [])) or '-'}**",
        f"- Why: {primary_bottleneck.get('why', '-')}",
        "",
        f"- Secondary: **{secondary_bottleneck.get('title', 'None')}**",
        f"- Secondary severity: `{sf(secondary_bottleneck.get('severity')):.3f}`",
        f"- Secondary maximum index gain: `+{sf(secondary_bottleneck.get('max_index_gain')):.3f}`",
        "",
        "## Knowledge Age",
        "",
        "| Stage | Count |",
        "| --- | ---: |",
        f"| Observations | {si(age.get('observations'))} |",
        f"| Promising | {si(age.get('promising'))} |",
        f"| Supported | {si(age.get('supported'))} |",
        f"| Strong | {si(age.get('strong'))} |",
        f"| Consensus | {si(age.get('consensus'))} |",
        f"| Foundational | {si(age.get('foundational'))} |",
        f"| Disputed | {si(age.get('disputed'))} |",
        f"| No signal | {si(age.get('no_signal'))} |",
        "",
        "## Research Metrics",
        "",
        f"- Knowledge maturity: **{sf(metrics.get('knowledge_maturity_score')):.3f}**",
        f"- Scientific stability: **{sf(metrics.get('scientific_stability_score')):.3f}**",
        f"- Research velocity: **{sf(metrics.get('research_velocity_score')):.3f}**",
        f"- Knowledge efficiency: **{sf(metrics.get('knowledge_efficiency_score')):.3f}**",
        f"- Mean consensus: `{sf(metrics.get('mean_consensus')):.3f}`",
        f"- Mean evidence quality: `{sf(metrics.get('mean_evidence_quality')):.3f}`",
        f"- Mean robustness: `{sf(metrics.get('mean_robustness')):.3f}`",
        f"- Total support / counterexamples: **{si(metrics.get('support_total'))} / {si(metrics.get('counterexamples_total'))}**",
        "",
        "## Knowledge Growth Since Previous Snapshot",
        "",
    ]
    if growth.get("has_previous"):
        lines.extend([
            f"- Observations: `{si(growth.get('new_observations')):+d}`",
            f"- Promising: `{si(growth.get('new_promising')):+d}`",
            f"- Supported or higher: `{si(growth.get('new_supported_or_higher')):+d}`",
            f"- Disputed: `{si(growth.get('new_disputed')):+d}`",
            f"- Maturity delta: `{sf(growth.get('maturity_delta')):+.3f}`",
            f"- Stability delta: `{sf(growth.get('stability_delta')):+.3f}`",
            f"- Efficiency delta: `{sf(growth.get('efficiency_delta')):+.3f}`",
            f"- Scientific health delta: `{sf(growth.get('scientific_health_delta')):+.3f}`",
        ])
    else:
        lines.append("- First meta-science snapshot. The little lab notebook has opened its first page.")

    lines.extend([
        "", "## Top Principles by Current Consensus", "",
        "| Rank | ID | Principle | Status | Consensus | Support | Counter |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: |",
    ])
    if not top:
        lines.append("| - | - | No principles yet | - | - | - | - |")
    else:
        for index, principle in enumerate(top, start=1):
            lines.append(
                f"| {index} | {principle.get('id')} | {principle.get('title')} | "
                f"{principle.get('status')} | {sf(principle.get('consensus_percent')):.1f}% | "
                f"{si(principle.get('support'))} | {si(principle.get('counterexamples'))} |"
            )

    lines.extend(["", "## Meta Signals", ""])
    if not signals:
        lines.append("- No unusual meta-science signals detected.")
    else:
        for signal in signals:
            lines.append(
                f"- **{signal.get('level', 'info').upper()}**: "
                f"{signal.get('signal')} — {signal.get('note')}"
            )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "Meta Science v34.2 is deliberately conservative. It measures the growth and stability of the knowledge base, but it does not promote principles by itself yet.",
        "Future v34.3 can add laboratory recommendations and intervention tracking.",
        "",
    ])
    return "\n".join(lines)
