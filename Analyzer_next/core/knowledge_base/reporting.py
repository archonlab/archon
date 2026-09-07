"""Markdown projection for the normalized Knowledge Base."""
from __future__ import annotations

from collections import Counter
from typing import Any


def render_markdown(kb: dict[str, Any], integrity: dict[str, Any]) -> str:
    summary = kb["summary"]
    family_counts = Counter(
        rule.get("family") or "Unknown"
        for rule in kb["rules"].values()
    )
    lines = [
        "# Universe Search Knowledge Base v3",
        "",
        f"Generated: **{kb['generated']}**",
        "",
        "## Summary",
        "",
        f"- Rules: **{summary['rules']}**",
        f"- Principles: **{summary['principles']}**",
        f"- Predictions: **{summary['predictions']}**",
        f"- Validations: **{summary['validations']}**",
        f"- Discoveries: **{summary['discoveries']}**",
        f"- Mechanisms: **{summary['mechanisms']}**",
        f"- Rules with discoveries: **{summary['rules_with_discoveries']}**",
        f"- Rules with mechanisms: **{summary['rules_with_mechanisms']}**",
        f"- Integrity: **{'OK' if integrity['ok'] else 'FAILED'}**",
        "",
        "## Relations",
        "",
        "| Relation | Count |",
        "|---|---:|",
    ]
    for name, count in summary["relation_counts"].items():
        lines.append(f"| {name} | {count} |")
    lines.extend([
        "",
        "## Behavioural families",
        "",
        "| Family | Rules |",
        "|---|---:|",
    ])
    for family, count in family_counts.most_common():
        lines.append(f"| {family} | {count} |")
    lines.extend([
        "",
        "## Rules",
        "",
        "| Rule | Family | Lifetime | Discoveries | Mechanisms | Principles |",
        "|---:|---|---:|---:|---:|---:|",
    ])
    for rule_id, rule in kb["rules"].items():
        lifetime = rule.get("passport", {}).get("lifetime")
        lines.append(
            f"| {rule_id} | {rule.get('family')} | {lifetime or 0} | "
            f"{len(rule['discovery_ids'])} | "
            f"{len(rule['mechanism_ids'])} | "
            f"{len(rule['principle_ids'])} |"
        )
    return "\n".join(lines) + "\n"
