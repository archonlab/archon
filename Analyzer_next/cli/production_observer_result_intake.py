#!/usr/bin/env python3
"""Stable Stage 7.5 intake with native SQLite inspection by default."""
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.telemetry.telemetry_run_inspection_routing import (  # noqa: E402
    inspect_sqlite,
)


from Analyzer_next.compatibility.legacy_analyzer import (  # noqa: E402
    production_observer_result_intake as intake,
)
intake.inspect_sqlite = inspect_sqlite
main = intake.main


if __name__ == "__main__":
    raise SystemExit(main())
