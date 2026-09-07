"""Markdown projections of consensus memory and current judgement."""
from __future__ import annotations

from typing import Any

from .numeric import sf, si, ss

def render_database_md(db: dict[str, Any]) -> str:
    principles = db.get("principles", {})
    rows = []
    for cid, p in principles.items():
        if not isinstance(p, dict):
            continue
        s = p.get("summary", {}) if isinstance(p.get("summary"), dict) else {}
        rows.append((cid, ss(p.get("title"), cid), ss(s.get("status"), "unknown"), si(s.get("support")), si(s.get("counterexamples")), si(s.get("neutral")), sf(s.get("confidence_score")), ss(s.get("confidence_label"), "NONE")))
    rows.sort(key=lambda x: (x[6], x[3], -x[4]), reverse=True)
    lines = [
        "# Consensus Database v32",
        "",
        "Persistent scientific memory layer. It stores one latest observation per principle/rule.",
        "Consensus scoring is written separately to `consensus_report.*`.",
        "",
        "## Metadata",
        "",
        f"- Created: `{db.get('created', '')}`",
        f"- Updated: `{db.get('updated', '')}`",
        f"- Analyzer root: `{db.get('analyzer_root', '')}`",
        f"- Results folder: `{db.get('results_folder', '')}`",
        f"- Principles tracked: **{len(rows)}**",
        f"- Runs recorded: **{len(db.get('run_history', []))}**",
        "",
        "## Principle Memory Summary",
        "",
        "| ID | Principle | DB status | Support | Counter | Neutral | Confidence | Score |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | ---: |",
    ]
    for cid, title, status, support, counter, neutral, score, label in rows:
        lines.append(f"| {cid} | {title} | {status} | {support} | {counter} | {neutral} | {label} | {score:.3f} |")
    lines.extend(["", "## Notes", "", "- This file is memory. `consensus_report.md` is the current scientific judgement layer.", "- Counterexamples are preserved, not hidden. They sharpen the theory.", ""])
    return "\n".join(lines)

def render_report_md(report: dict[str, Any]) -> str:
    principles = report.get("principles", [])
    maturity = report.get("scientific_maturity", {})
    lines = [
        "# Universe Search Consensus Report v33.1",
        "",
        "This report converts accumulated evidence into a coverage-adjusted scientific status per principle.",
        "Stage 3.2 adds a separate channel-aware interpretation without modifying legacy score or status.",
        "Stage 3.3 adds advisory action signals for downstream Director integration.",
        "Stage 3.3.1 prioritizes and deduplicates them into primary, secondary, and blocked actions.",
        "A single supporting rule remains an **OBSERVATION**, not a law. The engine becomes stronger as more rules are analyzed.",
        "",
        "## Scientific Maturity",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    for status in ["FOUNDATIONAL", "CONSENSUS", "STRONG", "SUPPORTED", "PROMISING", "OBSERVATION", "DISPUTED", "NO_SIGNAL"]:
        lines.append(f"| {status} | {si(maturity.get(status))} |")

    lines.extend([
        "",
        "## Top Scientific Principles",
        "",
        "| Rank | ID | Principle | Legacy status | Channel-aware status | Primary action | Priority | Active | Blocked |",
        "| ---: | --- | --- | --- | --- | --- | --- | ---: | ---: |",
    ])
    for i, p in enumerate(principles[:20], start=1):
        lines.append(
            f"| {i} | {p.get('id')} | {p.get('title')} | **{p.get('status')}** | "
            f"**{p.get('channel_aware_status')}** | "
            f"{p.get('primary_action_signal') or 'none'} | "
            f"{p.get('highest_action_priority')} | "
            f"{si(p.get('action_signal_count'))} | "
            f"{si(p.get('blocked_action_signal_count'))} |"
        )

    lines.extend(["", "## Principle Cards", ""])
    for p in principles:
        support_rules = ", ".join(p.get("support_rules", [])[:40]) or "-"
        counter_rules = ", ".join(p.get("counterexample_rules", [])[:40]) or "-"
        lines.extend([
            f"### {p.get('id')}: {p.get('title')}",
            "",
            f"- Legacy status: **{p.get('status')}**",
            f"- Channel-aware status: **{p.get('channel_aware_status')}**",
            f"- Confidence posture: **{p.get('confidence_posture')}**",
            f"- Interpretation: {p.get('interpretation_summary', '')}",
            f"- Highest action priority: **{p.get('highest_action_priority', 'NONE')}**",
            f"- Primary action: **{p.get('primary_action_signal') or 'none'}**",
            f"- Secondary actions: {', '.join(signal.get('signal_type', '') for signal in (p.get('prioritized_actions') or {}).get('secondary_signals', [])) or 'none'}",
            f"- Blocked actions: {', '.join(signal.get('signal_type', '') + ' ← ' + ', '.join(signal.get('blocked_by', [])) for signal in (p.get('prioritized_actions') or {}).get('blocked_signals', [])) or 'none'}",
            "- Action policy: advisory only; dependencies and deduplication do not execute or reprioritize Director actions.",
            f"- Adjusted consensus: **{sf(p.get('consensus_percent')):.1f}%**",
            f"- Raw observational consensus: **{sf(p.get('raw_consensus_percent')):.1f}%**",
            f"- Validation factor: `{sf(p.get('validation_factor')):.3f}`",
            f"- Opposing-regime coverage: **{p.get('counterexample_coverage_status')}**",
            f"- Perturbation status: **{p.get('perturbation_status')}**",
            f"- Perturbation coverage: **{si(p.get('perturbation_run_count'))} informative run(s)** across **{si(p.get('perturbation_parent_count'))} parent rule(s)**",
            "- Perturbation policy: reported separately; no automatic consensus-score adjustment.",
            f"- Experimental picture: **{p.get('experimental_picture', 'UNTESTED')}**",
            f"- Perturbation picture: **{p.get('perturbation_picture', 'INSUFFICIENT')}**",
            f"- Cross-channel tension: **{'YES' if (p.get('consensus_context_flags') or {}).get('cross_channel_tension') else 'NO'}**",
            f"- Evidence gaps: {', '.join(p.get('evidence_gaps', [])) or 'none'}",
            f"- Evidence synthesis: {(p.get('consensus_context') or {}).get('scientific_summary', '')}",
            "- Stage 3.1 policy: evidence profiles inform interpretation only; score and status remain legacy-derived.",
            f"- Repeated-observation coverage: `{sf(p.get('repeated_observation_coverage')):.3f}`",
            f"- Independent-seed coverage: `{sf(p.get('independent_seed_coverage')):.3f}`",
            f"- Metric independence: `{sf(p.get('metric_independence')):.3f}`",
            (
                "- Metric-independence method: `"
                + ss(
                    (
                        p.get("metric_independence_detail", {})
                        if isinstance(
                            p.get("metric_independence_detail"),
                            dict,
                        )
                        else {}
                    ).get("method"),
                    "unknown",
                )
                + "`"
            ),
            f"- Support / Counterexamples: **{si(p.get('support'))} / {si(p.get('counterexamples'))}**",
            f"- Mean confidence: `{sf(p.get('mean_confidence')):.3f}`",
            f"- Mean EMG / VAL: `{sf(p.get('mean_emg')):.3f}` / `{sf(p.get('mean_val')):.3f}`",
            f"- Knowledge / Feedback / Civilization: `{sf(p.get('mean_knowledge')):.3f}` / `{sf(p.get('mean_feedback')):.3f}` / `{sf(p.get('mean_civilization')):.3f}`",
            f"- Rule diversity: `{sf(p.get('rule_diversity')):.3f}`",
            f"- Repeatability proxy: `{sf(p.get('repeatability')):.3f}`",
            f"- Evidence quality: `{sf(p.get('evidence_quality')):.3f}`",
            f"- Predictive value proxy: `{sf(p.get('predictive_value')):.3f}`",
            f"- Support rules: {support_rules}",
            f"- Counterexample rules: {counter_rules}",
            "",
        ])

    lines.extend([
        "## Status Ladder",
        "",
        "`OBSERVATION → PROMISING → SUPPORTED → STRONG → CONSENSUS → FOUNDATIONAL`",
        "",
        "A principle can also become `DISPUTED` if counterexamples outgrow support.",
        "",
    ])
    return "\n".join(lines)

