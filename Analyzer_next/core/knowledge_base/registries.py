"""Pure registry selection helpers."""
from __future__ import annotations

from typing import Any


def preserve_generated_if_unchanged(
    previous: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(previous, dict):
        return payload
    previous_content = dict(previous)
    current_content = dict(payload)
    previous_generated = previous_content.pop("generated", None)
    current_content.pop("generated", None)
    if previous_content == current_content and previous_generated:
        payload["generated"] = previous_generated
    return payload


def merge_prediction_validation(
    predictions: dict[str, dict[str, Any]],
    validations: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for prediction_id, prediction in predictions.items():
        item = dict(prediction)
        validation = validations.get(prediction_id)
        if validation:
            item["validation_id"] = prediction_id
            item["validation_status"] = (
                validation.get("status_after")
                or validation.get("status")
                or item.get("status")
            )
            item["validation_verdict"] = validation.get("verdict")
        merged[prediction_id] = item
    return merged


def mechanism_global_id(
    rule_id: str,
    local_id: str | None,
    index: int,
) -> str:
    suffix = local_id or f"M-{index:03d}"
    return f"MECH-{rule_id}-{suffix}"
