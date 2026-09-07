"""Pure discovery coordination independent from filesystem adapters."""
from __future__ import annotations

from .analysis import build_database
from .contracts import DiscoveryInputs, DiscoveryRunResult
from .reporting import render_markdown


class DiscoveryOrchestrator:
    def run(
        self,
        inputs: DiscoveryInputs,
        *,
        generated: str | None = None,
    ) -> DiscoveryRunResult:
        database = build_database(inputs, generated=generated)
        return DiscoveryRunResult(
            database=database,
            report_markdown=render_markdown(database),
        )
