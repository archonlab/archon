#!/usr/bin/env python3
"""Canonical filesystem layout for Project ARCHON.

Every subsystem should import paths from this module instead of guessing
locations from the current working directory or from its own file path.
"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

UNIVERSE_SEARCH_DIR = PROJECT_ROOT / "Universe_Search"
OBSERVER_DIR = PROJECT_ROOT / "Observer"
ANALYZER_DIR = PROJECT_ROOT / "Analyzer_next" / "cli"

RESULTS_DIR = PROJECT_ROOT / "Results"
SEARCH_RESULTS_DIR = Path(
    os.environ.get("ARCHON_RESULTS_DIR", RESULTS_DIR / "Universe_Search")
).expanduser()
ANALYSIS_RESULTS_DIR = Path(
    os.environ.get("ARCHON_ANALYSIS_DIR", RESULTS_DIR / "Analysis")
).expanduser()

ATLAS_DIR = PROJECT_ROOT / "Atlas"
WORLD_ATLAS_DIR = Path(
    os.environ.get("ARCHON_WORLD_ATLAS_DIR", ATLAS_DIR / "Worlds")
).expanduser()
KNOWLEDGE_ATLAS_DIR = Path(
    os.environ.get("ARCHON_KNOWLEDGE_ATLAS_DIR", ATLAS_DIR / "Knowledge")
).expanduser()

DOCUMENTATION_DIR = PROJECT_ROOT / "Documentation"
LEGACY_DIR = PROJECT_ROOT / "Legacy"


def ensure_layout() -> None:
    """Create the canonical ARCHON directory structure if needed."""
    for path in (
        UNIVERSE_SEARCH_DIR,
        OBSERVER_DIR,
        ANALYZER_DIR,
        RESULTS_DIR,
        SEARCH_RESULTS_DIR,
        ANALYSIS_RESULTS_DIR,
        ATLAS_DIR,
        WORLD_ATLAS_DIR,
        KNOWLEDGE_ATLAS_DIR,
        DOCUMENTATION_DIR,
        LEGACY_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def describe() -> str:
    """Return a readable summary of the active filesystem layout."""
    return "\n".join(
        [
            f"Project root:     {PROJECT_ROOT}",
            f"Universe Search:  {UNIVERSE_SEARCH_DIR}",
            f"Observer:         {OBSERVER_DIR}",
            f"Analyzer:         {ANALYZER_DIR}",
            f"Search results:   {SEARCH_RESULTS_DIR}",
            f"Analysis output:  {ANALYSIS_RESULTS_DIR}",
            f"World Atlas:      {WORLD_ATLAS_DIR}",
            f"Knowledge Atlas:  {KNOWLEDGE_ATLAS_DIR}",
        ]
    )


__all__ = [
    "PROJECT_ROOT",
    "UNIVERSE_SEARCH_DIR",
    "OBSERVER_DIR",
    "ANALYZER_DIR",
    "RESULTS_DIR",
    "SEARCH_RESULTS_DIR",
    "ANALYSIS_RESULTS_DIR",
    "ATLAS_DIR",
    "WORLD_ATLAS_DIR",
    "KNOWLEDGE_ATLAS_DIR",
    "DOCUMENTATION_DIR",
    "LEGACY_DIR",
    "ensure_layout",
    "describe",
]
