#!/usr/bin/env python3
"""Stable Stage 7.6 shell routing Stage 7.5 through Analyzer_next."""
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from Analyzer_next.compatibility.legacy_analyzer import (  # noqa: E402
    production_execution_cycle_orchestrator as orchestrator,
)
from Analyzer_next.production.runtime_routes import cli_route  # noqa: E402
_legacy_run_module = orchestrator.run_module
INTAKE_ENTRYPOINT = cli_route("production_observer_result_intake.py")


def run_module(
    python_executable,
    module_path,
    analysis_root,
    log_path,
):
    selected = (
        INTAKE_ENTRYPOINT
        if Path(module_path).name == "production_observer_result_intake.py"
        else module_path
    )
    return _legacy_run_module(
        python_executable,
        selected,
        analysis_root,
        log_path,
    )


orchestrator.run_module = run_module
main = orchestrator.main


if __name__ == "__main__":
    raise SystemExit(main())
