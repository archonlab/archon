"""Markdown projections for persistent predictions."""
from __future__ import annotations

from typing import Any

from .database import status_counts
from .values import normalize_status, now_iso, stars


def render_markdown(db: dict[str, Any]) -> str:
    predictions = sorted(
        db["predictions"].values(),
        key=lambda item: (
            item.get("status") == "Open",
            int(item.get("priority", 0)),
            float(item.get("confidence_score", 0.0)),
        ),
        reverse=True,
    )
    counts = status_counts(db["predictions"])

    lines = [
        "# Universe Search Prediction Report v2",
        "",
        f"Generated: **{now_iso()}**",
        f"Stored predictions: **{len(predictions)}**",
        "",
        "## Status",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status in ("Open", "Testing", "Confirmed", "Rejected", "Inconclusive"):
        lines.append(f"| {status} | {counts.get(status, 0)} |")

    lines.extend(["", "## Predictions", ""])
    for item in predictions:
        lines.extend([
            f"### {item.get('id')}: {item.get('based_on')}",
            "",
            f"- Status: **{normalize_status(item.get('status'))}**",
            f"- Priority: **{stars(item.get('priority', 1))}**",
            f"- Confidence: **{item.get('confidence')}** "
            f"(`{float(item.get('confidence_score', 0.0)):.3f}`)",
            f"- Created: `{item.get('created', '')}`",
            f"- Last validated: `{item.get('last_validated', '-')}`",
            "",
            "**Prediction**",
            "",
            str(item.get("prediction", "")),
            "",
            "**Expected observation**",
            "",
            str(item.get("expected_observation", "")),
            "",
            "**Test**",
            "",
            str(item.get("test", "")),
            "",
            "**Success criteria**",
            "",
            str(item.get("success_criteria", "")),
            "",
        ])

        validation = item.get("validation")
        if isinstance(validation, dict):
            lines.extend([
                "**Latest validation**",
                "",
                f"- Verdict: {validation.get('verdict')}",
                f"- Support: {validation.get('support', 0)}",
                f"- Counterexamples: {validation.get('counterexamples', 0)}",
                "",
            ])

    return "\n".join(lines)


def render_database_md(db: dict[str, Any]) -> str:
    counts = status_counts(db["predictions"])
    lines = [
        "# ARCHON Prediction Database v2",
        "",
        f"- Created: `{db.get('created')}`",
        f"- Updated: `{db.get('updated')}`",
        f"- Predictions: **{len(db.get('predictions', {}))}**",
        f"- Runs recorded: **{len(db.get('run_history', []))}**",
        "",
        "## Status counts",
        "",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"- {status}: **{count}**")

    lines.extend([
        "",
        "## Registry",
        "",
        "| ID | Status | Priority | Confidence | Based on |",
        "|---|---|---:|---:|---|",
    ])
    for prediction_id, item in sorted(db["predictions"].items()):
        lines.append(
            f"| {prediction_id} | {normalize_status(item.get('status'))} | "
            f"{item.get('priority', 0)} | "
            f"{float(item.get('confidence_score', 0.0)):.3f} | "
            f"{item.get('based_on', '')} |"
        )
    return "\n".join(lines) + "\n"


__all__ = ["render_database_md", "render_markdown"]
