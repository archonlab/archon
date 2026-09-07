"""Pure Markdown projection for prediction validation results."""
from __future__ import annotations

from typing import Any

from .rules import get_experiments


def render_markdown(
    results: list[dict[str, Any]],
    atlas: dict[str, Any],
    generated: str,
) -> str:
    lines: list[str] = []
    experiments = get_experiments(atlas)

    lines.append("# Universe Search Validation Report")
    lines.append("")
    lines.append(f"Generated: **{generated}**")
    lines.append(f"Atlas experiments: **{len(experiments)}**")
    lines.append(f"Predictions checked: **{len(results)}**")
    lines.append("")

    confirmed = sum(1 for result in results if result["status_after"] == "Confirmed")
    testing = sum(1 for result in results if result["status_after"] == "Still testing")
    open_count = sum(1 for result in results if result["status_after"] == "Open")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Confirmed: **{confirmed}**")
    lines.append(f"- Still testing: **{testing}**")
    lines.append(f"- Open: **{open_count}**")
    lines.append("")
    lines.append("## Prediction validation")
    lines.append("")
    for result in results:
        lines.append(f"### {result['id']}: {result.get('based_on')}")
        lines.append("")
        lines.append(f"- Status: **{result['status_after']}**")
        lines.append(f"- Verdict: **{result['verdict']}**")
        lines.append(f"- Support: **{result['support_count']}**")
        stats = result.get("support_statistics", {})
        seed_count = stats.get("independent_seed_count")
        seed_label = "unknown" if seed_count is None else str(seed_count)
        lines.append(
            "- Support independence: "
            f"runs={stats.get('run_count', 0)}, "
            f"canonical rules={stats.get('canonical_rule_count', 0)}, "
            f"independent seeds={seed_label}, "
            f"families={stats.get('behavioural_family_count', 0)}"
        )
        lines.append(f"- Negative cohort: **{result['negative_cohort_count']}**")
        lines.append(
            "- Canonical claim counterexamples: "
            f"**{result['claim_counterexample_count']}**"
        )
        lines.append(
            "- Failed prediction outcomes: "
            f"**{result['failed_prediction_count']}**"
        )
        lines.append("")
        lines.append("Evidence:")
        for evidence in result.get("evidence", []):
            lines.append(f"- {evidence}")
        if result.get("next_action"):
            lines.append("")
            lines.append(f"Next action: **{result['next_action']}**")
        lines.append("")

    lines.append("## What this means")
    lines.append("")
    if len(experiments) < 5:
        lines.append(
            "The atlas is still small, so most predictions should remain open or still testing. "
            "This is expected. Validation becomes powerful after multiple independent experiments."
        )
    else:
        lines.append(
            "The atlas contains enough experiments for preliminary validation, but still needs counterexamples and replications."
        )
    lines.append("")
    return "\n".join(lines)


__all__ = ["render_markdown"]
