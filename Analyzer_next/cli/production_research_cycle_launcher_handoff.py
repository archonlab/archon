#!/usr/bin/env python3
"""Stable launcher-handoff entrypoint with native validation by default."""
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.adapters.telemetry.scientific_identity_validation_routing import (  # noqa: E402
    telemetry_identity_issues,
)


from Analyzer_next.compatibility.legacy_analyzer import (  # noqa: E402
    production_research_cycle_launcher_handoff as handoff,
)
handoff.telemetry_identity_issues = telemetry_identity_issues
build_spec = handoff.build_spec
main = handoff.main


if __name__ == "__main__":
    raise SystemExit(main())
