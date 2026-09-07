"""Native Reference Control Registry engine."""
from __future__ import annotations

from Analyzer_next.core.reference_control_registry.orchestrator import run_registry


class ReferenceControlRegistryEngine:
    def __init__(self, repository) -> None:
        self.repository = repository

    def run(self):
        return run_registry(self.repository)
