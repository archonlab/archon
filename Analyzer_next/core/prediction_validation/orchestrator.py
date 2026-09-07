"""Pure coordination of prediction validation."""
from __future__ import annotations

from Analyzer_next.core.scientific_claims import get_claim_spec

from .contracts import PredictionValidationInputs, PredictionValidationRunResult
from .reporting import render_markdown
from .rules import get_experiments, validate_prediction


class PredictionValidationOrchestrator:
    def run(self, inputs: PredictionValidationInputs) -> PredictionValidationRunResult:
        experiments = get_experiments(inputs.atlas)
        results = [
            validate_prediction(prediction, experiments, inputs.aliases)
            for prediction in inputs.predictions
        ]
        payload = {
            "version": "Universe Search Validation Engine v2.3",
            "generated": inputs.generated,
            "scientific_claims_registry": {
                "module": "scientific_claims.py",
                "claim_versions": {
                    claim_id: get_claim_spec(claim_id).version
                    for claim_id in ("GP-101", "GP-102", "GP-103", "GP-105")
                },
            },
            "results": results,
        }
        return PredictionValidationRunResult(
            payload=payload,
            markdown=render_markdown(results, inputs.atlas, inputs.generated),
            results=results,
        )


__all__ = ["PredictionValidationOrchestrator"]
