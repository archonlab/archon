"""Markdown projection for the discovery database."""
from __future__ import annotations

from typing import Any

from .analysis import impact_stars


def render_markdown(database: dict[str, Any]) -> str:
    summary = database["summary"]
    lines = [
        "# Universe Search Discovery Report v2",
        "",
        f"Generated: **{database['generated']}**",
        "",
        "## Summary",
        "",
        f"- Rules analyzed: **{summary['rules_analyzed']}**",
        f"- Rules with discoveries: **{summary['rules_with_discoveries']}**",
        f"- Total discoveries: **{summary['discovery_count']}**",
        f"- High-impact discoveries: **{summary['high_impact_count']}**",
        "",
        "## Discovery categories",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for category, count in summary["category_counts"].items():
        lines.append(f"| {category} | {count} |")
    lines.extend([
        "",
        "## Top discoveries",
        "",
        "| Rule | Discovery | Category | Impact | Confidence |",
        "|---:|---|---|---:|---|",
    ])
    for item in database["top_discoveries"]:
        lines.append(
            f"| {item['rule_id']} | {item['title']} | {item['category']} | "
            f"{impact_stars(item['impact'])} | {item['confidence']} |"
        )
    lines.extend(["", "## Rule summaries", ""])
    for rule, payload in database["discoveries_by_rule"].items():
        discoveries = payload["discoveries"]
        if not discoveries:
            continue
        lines.append(f"### Rule {rule}")
        lines.append("")
        for item in discoveries:
            lines.append(
                f"- **{item['title']}** "
                f"({impact_stars(item['impact'])}, {item['confidence']}): "
                f"{item['finding']}"
            )
        lines.append("")
    return "\n".join(lines)
