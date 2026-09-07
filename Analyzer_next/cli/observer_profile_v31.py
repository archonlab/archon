#!/usr/bin/env python3
"""Modular compatibility entrypoint for Observer Profile v31.

Keeps the frozen legacy profile parser and provenance semantics intact while
adding passports produced inside experiment RuntimePackages to ``profile_records``.
Experimental profiles remain excluded from the rule-level observational
representative view by the existing telemetry provenance policy.
"""
from __future__ import annotations

import importlib
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.observer.experiment_passport_collection import (  # noqa: E402
    collect_passport_json as collect_experiment_passports,
)

legacy = importlib.import_module(
    "Analyzer_next.compatibility.legacy_analyzer.observer_profile_v31"
)
_legacy_collect = legacy.collect_passport_json


def collect_passport_json(results_folder: Path):
    canonical = _legacy_collect(Path(results_folder))
    return collect_experiment_passports(
        Path(results_folder),
        legacy_files=canonical,
    )


legacy.collect_passport_json = collect_passport_json
main = legacy.main


if __name__ == "__main__":
    raise SystemExit(main())
