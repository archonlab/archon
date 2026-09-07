"""Persistent Prediction Engine database lifecycle and validation updates."""
from __future__ import annotations

import math
from typing import Any

from .constants import DB_SCHEMA, ENGINE_VERSION
from .values import (
    confidence_label,
    confidence_value,
    normalize_status,
    now_iso,
)


def empty_database() -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "schema": DB_SCHEMA,
        "version": ENGINE_VERSION,
        "created": timestamp,
        "updated": timestamp,
        "predictions": {},
        "run_history": [],
    }


def ensure_database_shape(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = empty_database()
    payload.setdefault("created", now_iso())
    payload["schema"] = DB_SCHEMA
    payload["version"] = ENGINE_VERSION
    payload["updated"] = now_iso()

    predictions = payload.get("predictions", {})
    if isinstance(predictions, list):
        predictions = {
            str(item.get("id")): item
            for item in predictions
            if isinstance(item, dict) and item.get("id")
        }
    elif not isinstance(predictions, dict):
        predictions = {}

    payload["predictions"] = predictions
    payload.setdefault("run_history", [])
    return payload


def append_history(item: dict[str, Any], event: str, **details: Any) -> None:
    history = item.setdefault("history", [])
    entry = {
        "timestamp": now_iso(),
        "event": event,
        **details,
    }

    if history:
        previous = history[-1]
        comparable_previous = {k: v for k, v in previous.items() if k != "timestamp"}
        comparable_entry = {k: v for k, v in entry.items() if k != "timestamp"}
        if comparable_previous == comparable_entry:
            return

    history.append(entry)
    item["history"] = history[-200:]


def apply_validation(item: dict[str, Any], validation: dict[str, Any]) -> None:
    previous_status = normalize_status(item.get("status"))
    status_after = normalize_status(
        validation.get("status_after")
        or validation.get("status")
        or validation.get("verdict")
    )

    if status_after not in {
        "Confirmed", "Rejected", "Inconclusive", "Testing", "Open"
    }:
        status_after = previous_status

    support = int(validation.get("support") or 0)
    counterexamples = int(validation.get("counterexamples") or 0)
    confidence_score = item.get("confidence_score")
    if confidence_score in (None, ""):
        confidence_score = confidence_value(item.get("confidence"))
    current_confidence = float(confidence_score)

    if status_after == "Confirmed":
        updated_confidence = min(
            0.99,
            current_confidence + 0.12 + min(0.12, math.log1p(support) / 35.0),
        )
    elif status_after == "Rejected":
        updated_confidence = max(
            0.01,
            current_confidence - 0.25 - min(0.15, math.log1p(counterexamples) / 30.0),
        )
    elif status_after == "Inconclusive":
        updated_confidence = max(0.05, current_confidence - 0.03)
    else:
        updated_confidence = current_confidence

    item["status"] = status_after
    item["confidence_score"] = round(updated_confidence, 4)
    item["confidence"] = confidence_label(updated_confidence)
    item["last_validated"] = now_iso()
    item["validation"] = {
        "verdict": validation.get("verdict"),
        "support": support,
        "counterexamples": counterexamples,
        "evidence": validation.get("evidence", []),
        "next_action": validation.get("next_action"),
    }

    if status_after != previous_status:
        append_history(
            item,
            "status_changed",
            from_status=previous_status,
            to_status=status_after,
            verdict=validation.get("verdict"),
        )
    else:
        append_history(
            item,
            "validation_refreshed",
            status=status_after,
            verdict=validation.get("verdict"),
        )


def merge_predictions(
    db: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    validations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    stored = db["predictions"]
    timestamp = now_iso()

    for prediction_id, candidate in candidates.items():
        if prediction_id not in stored:
            item = dict(candidate)
            item["created"] = timestamp
            item["updated"] = timestamp
            item["status"] = "Open"
            item["history"] = []
            append_history(
                item,
                "created",
                status="Open",
                confidence=item.get("confidence"),
            )
            stored[prediction_id] = item
        else:
            item = stored[prediction_id]
            preserved = {
                "created": item.get("created"),
                "status": item.get("status"),
                "confidence": item.get("confidence"),
                "confidence_score": item.get("confidence_score"),
                "history": item.get("history"),
                "last_validated": item.get("last_validated"),
                "validation": item.get("validation"),
            }
            item.update(candidate)
            for key, value in preserved.items():
                if value is not None:
                    item[key] = value
            item["updated"] = timestamp

        if prediction_id in validations:
            apply_validation(stored[prediction_id], validations[prediction_id])

    for prediction_id, item in stored.items():
        item.setdefault("id", prediction_id)
        item.setdefault("created", timestamp)
        item.setdefault("updated", timestamp)
        item.setdefault("status", "Open")
        item.setdefault(
            "confidence_score",
            confidence_value(item.get("confidence")),
        )
        item.setdefault(
            "confidence",
            confidence_label(item["confidence_score"]),
        )
        item.setdefault("history", [])

        if prediction_id in validations and prediction_id not in candidates:
            apply_validation(item, validations[prediction_id])

    db["predictions"] = stored
    db["updated"] = timestamp
    db["run_history"].append({
        "timestamp": timestamp,
        "candidate_count": len(candidates),
        "stored_count": len(stored),
        "validation_count": len(validations),
        "status_counts": dict(status_counts(stored)),
    })
    db["run_history"] = db["run_history"][-300:]
    return db


def status_counts(predictions: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in predictions.values():
        status = normalize_status(item.get("status"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def compatibility_payload(db: dict[str, Any]) -> dict[str, Any]:
    """Keep Validation Engine compatibility with a top-level prediction list."""
    items = sorted(
        db["predictions"].values(),
        key=lambda item: (
            int(item.get("priority", 0)),
            float(item.get("confidence_score", 0.0)),
            str(item.get("id", "")),
        ),
        reverse=True,
    )
    return {
        "version": ENGINE_VERSION,
        "schema": "archon_predictions_compat_v2",
        "generated": now_iso(),
        "prediction_count": len(items),
        "status_counts": status_counts(db["predictions"]),
        "predictions": items,
    }


__all__ = [
    "append_history",
    "apply_validation",
    "compatibility_payload",
    "empty_database",
    "ensure_database_shape",
    "merge_predictions",
    "status_counts",
]
