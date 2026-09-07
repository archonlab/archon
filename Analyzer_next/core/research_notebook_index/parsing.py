"""Pure Markdown parsing for Research Notebook Index v1."""
from __future__ import annotations

import re

from .contracts import ResearchNotebookIndexItem


def grab(pattern: str, text: str, default=None):
    match = re.search(pattern, text, re.I | re.M)
    if not match:
        return default
    return match.group(1).strip()


def count_section_items(text: str, section: str) -> int:
    match = re.search(
        rf"##\s+{re.escape(section)}\s*\n(.+?)(?=\n##\s+|\Z)",
        text,
        re.I | re.S,
    )
    if not match:
        return 0
    return len(
        [
            line
            for line in match.group(1).splitlines()
            if line.strip().startswith("- ") and "No linked" not in line
        ]
    )


def parse_metric(text: str, metric: str):
    match = re.search(
        rf"\|\s*{re.escape(metric)}\s*\|\s*([^|]+)\|",
        text,
        re.I,
    )
    if not match:
        return None
    raw = match.group(1).strip()
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except Exception:
        return raw


def parse_notebook(filename: str, text: str) -> ResearchNotebookIndexItem:
    classification = None
    match = re.search(r"Classification:\s*([^\n.]+)", text)
    if match:
        classification = match.group(1).strip()
    return ResearchNotebookIndexItem(
        filename=filename,
        rule=grab(r"-\s*Rule:\s*\*\*([^*]+)\*\*", text) or "unknown",
        date=grab(r"-\s*Date:\s*\*\*([^*]+)\*\*", text) or "unknown",
        status=grab(r"-\s*Status:\s*\*\*([^*]+)\*\*", text) or "unknown",
        confidence=grab(r"Level:\s*\*\*([^*]+)\*\*", text) or "unknown",
        classification=classification or "unknown",
        lifetime=parse_metric(text, "lifetime"),
        dynamic=parse_metric(text, "dynamic_score"),
        breathing=parse_metric(text, "breathing_score"),
        collapse=parse_metric(text, "collapse"),
        questions=count_section_items(text, "Open Questions"),
        discoveries=count_section_items(text, "Discoveries"),
        mechanisms=count_section_items(text, "Mechanisms"),
        principles=count_section_items(text, "General Principles"),
        predictions=count_section_items(text, "Predictions"),
    )


__all__ = [
    "count_section_items",
    "grab",
    "parse_metric",
    "parse_notebook",
]
