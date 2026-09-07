from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from Analyzer_next.core.scientific_data.ids import normalize_rule_id
from .io import read_text


def find_notebooks(results_root: Path) -> dict[str, Path]:
    notebook_dir = results_root / "ResearchNotebook"
    if not notebook_dir.exists():
        return {}

    out: dict[str, Path] = {}
    for path in notebook_dir.glob("experiment_*.md"):
        rule = normalize_rule_id(path.name)
        if rule:
            out[rule] = path
    return out


def parse_notebook(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}

    text = read_text(path)
    return {
        "path": str(path),
        "questions": re.findall(r"## Open Questions\s+(.+?)(?=\n##|\Z)", text, re.S),
        "has_manual_notes": "Add manual notes here" not in text,
    }
