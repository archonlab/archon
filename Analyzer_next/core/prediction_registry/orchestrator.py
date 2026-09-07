"""Pure coordination of candidate generation and persistent-memory update."""
from __future__ import annotations

from .candidates import generate_candidates
from .contracts import PredictionRegistryInputs, PredictionRegistryRunResult
from .database import (
    compatibility_payload,
    ensure_database_shape,
    merge_predictions,
)
from .reporting import render_database_md, render_markdown


class PredictionRegistryOrchestrator:
    def run(self, inputs: PredictionRegistryInputs) -> PredictionRegistryRunResult:
        candidates = generate_candidates(
            inputs.atlas,
            inputs.knowledge_base,
            inputs.principles,
        )
        database = ensure_database_shape(inputs.database)
        database = merge_predictions(database, candidates, inputs.validations)
        return PredictionRegistryRunResult(
            database=database,
            compatibility=compatibility_payload(database),
            database_markdown=render_database_md(database),
            output_markdown=render_markdown(database),
            principle_count=len(inputs.principles),
            candidate_count=len(candidates),
            validation_count=len(inputs.validations),
        )


__all__ = ["PredictionRegistryOrchestrator"]
