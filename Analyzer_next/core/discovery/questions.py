"""Research-question parsing with the preserved v2 legacy grammar."""
from __future__ import annotations

import re
from typing import Any

from .ids import normalize_rule_id


def parse_research_questions(
    text: str | None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    if not text:
        return {}

    by_rule: dict[str, dict[str, list[dict[str, Any]]]] = {}

    def bucket(rule: str) -> dict[str, list[dict[str, Any]]]:
        return by_rule.setdefault(
            rule,
            {"high_priority": [], "hypotheses": [], "next_actions": []},
        )

    for line in text.splitlines():
        if not line.startswith("| ★") or "| Rule |" in line:
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 5:
            continue
        rule = normalize_rule_id(parts[1])
        if not rule:
            continue
        bucket(rule)["high_priority"].append({
            "priority": parts[0],
            "rule": rule,
            "question": parts[2],
            "why": parts[3],
            "test": parts[4],
        })

    for match in re.finditer(
        r"###\s+(H-[^\n]+)\n\n(.+?)(?=\n###|\n##|\Z)",
        text,
        re.S,
    ):
        hypothesis_id = match.group(1).strip()
        hypothesis_text = " ".join(match.group(2).strip().split())
        rule = normalize_rule_id(hypothesis_id) or normalize_rule_id(
            hypothesis_text
        )
        if rule:
            bucket(rule)["hypotheses"].append({
                "id": hypothesis_id,
                "text": hypothesis_text,
            })

    global_actions: list[dict[str, Any]] = []
    in_next = False
    for line in text.splitlines():
        if line.strip().startswith("## Next actions"):
            in_next = True
            continue
        if in_next and line.startswith("## "):
            break
        if in_next:
            match = re.match(r"\d+\.\s+(.+)", line.strip())
            if match:
                global_actions.append({"text": match.group(1).strip()})

    if global_actions:
        by_rule["_global"] = {
            "high_priority": [],
            "hypotheses": [],
            "next_actions": global_actions,
        }
    return by_rule
