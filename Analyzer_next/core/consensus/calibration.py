"""Claim calibration, opposing-regime factors, and status caps."""
from __future__ import annotations

from typing import Any

from .constants import METRIC_INDEPENDENCE_CALIBRATION
from .numeric import clamp01, sf, ss

def metric_independence_calibration(
    claim_id: str,
) -> tuple[float, dict[str, Any]]:
    default = {
        "score": 0.50,
        "channels": ["unknown"],
        "shared_upstream_penalty": 0.25,
        "formula_overlap_penalty": 0.20,
        "same_pipeline_penalty": 0.05,
        "rationale": (
            "No claim-specific calibration is registered; a conservative "
            "default is used."
        ),
    }
    raw = METRIC_INDEPENDENCE_CALIBRATION.get(claim_id, default)
    score = clamp01(sf(raw.get("score"), 0.50))
    detail = {
        "method": "structural_architecture_audit_v1",
        "score": round(score, 4),
        "channels": list(raw.get("channels", [])),
        "penalties": {
            "shared_upstream": round(
                sf(raw.get("shared_upstream_penalty")),
                4,
            ),
            "formula_overlap": round(
                sf(raw.get("formula_overlap_penalty")),
                4,
            ),
            "same_pipeline": round(
                sf(raw.get("same_pipeline_penalty")),
                4,
            ),
        },
        "rationale": ss(raw.get("rationale")),
        "empirical_validation": False,
        "upgrade_path": (
            "Replace structural estimate with intervention, metric-ablation, "
            "and independent multi-seed calibration."
        ),
    }
    return score, detail

def opposing_regime_factor(status: str) -> float:
    return {
        "UNTESTED_REGIME": 0.45,
        "NEAR_COUNTEREXAMPLES_ONLY": 0.65,
        "COUNTEREXAMPLES_FOUND": 0.85,
        "TESTED_REGIME": 1.00,
    }.get(status, 0.50)

def status_rank(status: str) -> int:
    order = [
        "NO_SIGNAL",
        "OBSERVATION",
        "PROMISING",
        "SUPPORTED",
        "STRONG",
        "CONSENSUS",
        "FOUNDATIONAL",
    ]
    try:
        return order.index(status)
    except ValueError:
        return 0

def cap_status(status: str, maximum: str) -> str:
    if status == "DISPUTED":
        return status
    return maximum if status_rank(status) > status_rank(maximum) else status

