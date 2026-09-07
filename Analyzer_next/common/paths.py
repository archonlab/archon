"""Canonical ARCHON paths without depending on the legacy Analyzer package."""
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def analysis_results_dir() -> Path:
    path = PROJECT_ROOT / "Results" / "Analysis"
    path.mkdir(parents=True, exist_ok=True)
    return path


def knowledge_atlas_dir() -> Path:
    path = PROJECT_ROOT / "Atlas" / "Knowledge"
    path.mkdir(parents=True, exist_ok=True)
    return path

