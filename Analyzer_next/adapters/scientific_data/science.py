from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import load_json


def load_principles(analysis_root: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(analysis_root / "general_principles.json", {})
    items = payload.get("principles", [])
    return {
        str(item.get("id")): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }


def load_predictions(analysis_root: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(analysis_root / "predictions.json", {})
    items = payload.get("predictions", [])
    return {
        str(item.get("id")): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }


def load_validations(analysis_root: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(analysis_root / "validation_report.json", {})
    if not payload:
        payload = load_json(analysis_root / "validation_results.json", {})

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("results")
            or payload.get("predictions")
            or payload.get("validation")
            or []
        )
    else:
        items = []

    return {
        str(item.get("id")): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }
