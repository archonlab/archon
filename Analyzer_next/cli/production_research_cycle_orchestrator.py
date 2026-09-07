#!/usr/bin/env python3
"""Stable production owner routing Stage 7.6 through Analyzer_next."""
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.compatibility.legacy_analyzer import (  # noqa: E402
    production_research_cycle_orchestrator as owner,
)
from Analyzer_next.production.runtime_routes import (  # noqa: E402
    cli_route,
)
_legacy_run_module = owner.run_module
EXECUTION_ENTRYPOINT = cli_route("production_execution_cycle_orchestrator.py")


def run_module(
    python_executable,
    script,
    analysis_root,
    log_path,
    *,
    modules_root=None,
    extra_args=None,
    allow_nonzero=False,
):
    selected = (
        EXECUTION_ENTRYPOINT
        if Path(script).name == "production_execution_cycle_orchestrator.py"
        else script
    )
    return _legacy_run_module(
        python_executable,
        selected,
        analysis_root,
        log_path,
        modules_root=modules_root,
        extra_args=extra_args,
        allow_nonzero=allow_nonzero,
    )


owner.run_module = run_module
main = owner.main


if __name__ == "__main__":
    raise SystemExit(main())
