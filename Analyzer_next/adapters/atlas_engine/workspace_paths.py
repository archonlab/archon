"""Native path resolver used by Atlas Engine."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from archon_paths import ANALYZER_DIR, KNOWLEDGE_ATLAS_DIR, PROJECT_ROOT, SEARCH_RESULTS_DIR, ensure_layout

def knowledge_atlas_dir() -> Path:
    ensure_layout()
    return KNOWLEDGE_ATLAS_DIR

def resolve_results_dir(results_arg: Optional[str] = None) -> Path:
    if results_arg is None or not str(results_arg).strip():
        ensure_layout()
        return SEARCH_RESULTS_DIR.resolve()
    raw = Path(results_arg).expanduser()
    candidates = [raw] if raw.is_absolute() else [Path.cwd() / raw, PROJECT_ROOT / raw, SEARCH_RESULTS_DIR / raw, ANALYZER_DIR / raw]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    checked = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(f"Results folder not found: {results_arg}\nChecked:\n{checked}")
