from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from Analyzer_next.core.scientific_data.ids import normalize_rule_id
from .io import read_text


SCORE_LABELS = (
    "Field memory",
    "Stochastic stability",
    "Oscillatory feedback",
    "Multi-scale feedback",
    "Genome complexity",
)


def find_mechanism_reports(*roots: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.glob("mechanism_report_rule_*.md"):
            rule = normalize_rule_id(path.name)
            if rule:
                out[rule] = path
    return out


def parse_mechanism_report(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {"scores": {}, "mechanisms": []}

    text = read_text(path)
    scores: dict[str, float] = {}

    for label in SCORE_LABELS:
        match = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*([0-9.]+)\s*\|", text)
        if match:
            scores[label.lower().replace(" ", "_")] = float(match.group(1))

    mechanisms = []
    for match in re.finditer(r"###\s+(M-\d+):\s+(.+?)\n\n(.+?)(?=\n###|\n##|\Z)", text, re.S):
        block = match.group(3)
        confidence = re.search(r"Confidence:\s*\*\*(.+?)\*\*", block)
        claim = re.search(r"Claim:\s*(.+)", block)
        mechanisms.append({
            "id": match.group(1),
            "title": match.group(2).strip(),
            "confidence": confidence.group(1).strip() if confidence else None,
            "claim": claim.group(1).strip() if claim else None,
        })

    return {"scores": scores, "mechanisms": mechanisms}
