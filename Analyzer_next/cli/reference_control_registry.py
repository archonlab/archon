#!/usr/bin/env python3
"""Compatibility CLI for Reference Control Registry v1.1."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.reference_control_registry.file_repository import FileRegistryRepository
from Analyzer_next.engines.reference_control_registry import ReferenceControlRegistryEngine


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build ARCHON reference-control registry from normalized Observer profiles.")
    ap.add_argument("results_folder")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md-out", default=None)
    ns = ap.parse_args(argv)
    results = Path(ns.results_folder).resolve()
    profiles = results / "observer_profiles_v30.json"
    if not profiles.exists():
        raise SystemExit(f"Observer profiles not found: {profiles}")
    out = Path(ns.out).resolve()
    md = Path(ns.md_out).resolve() if ns.md_out else out.with_suffix(".md")
    artifact = ReferenceControlRegistryEngine(FileRegistryRepository(profiles, out, md)).run()
    summary = artifact.payload["summary"]
    print("Project ARCHON Reference Control Registry v1.1")
    print("=" * 64)
    print(f"Independent rules:  {summary['independent_rules']}")
    print(f"Observed classes:   {summary['observed_classes']}/{summary['class_count']}")
    print(f"Qualified classes:  {summary['qualified_classes']}/{summary['class_count']}")
    print(f"JSON:               {out}")
    print(f"Markdown:           {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
