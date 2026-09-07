"""Reconcile Observer passport lifecycle data for Analyzer consumers.

The passport summary is the canonical persisted projection.  Analyzer may
independently rebuild the same projection from ``observer_state`` to verify
transport integrity, but a mismatch must be reported rather than silently
replacing the persisted summary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from .lifecycle_summary import summarize_lifecycle_state
from .lifecycle_temporal_integrity import (
    assess_lifecycle_temporal_integrity,
)


RECONCILIATION_SCHEMA_VERSION = "1.1.0"

_SUMMARY_FIELDS = (
    "schema_version",
    "mode",
    "history_status",
    "history_complete_for_supported_types",
    "observed_through_tick",
    "phase",
    "event_count",
    "event_types",
    "first_ticks",
    "latest_event_type",
    "latest_event_tick",
)


def reconcile_lifecycle_contract(
    passport_summary: Mapping[str, Any] | None,
    observer_state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return canonical summary, event history, and verification metadata."""

    persisted_available = isinstance(passport_summary, Mapping)
    state_available = isinstance(observer_state, Mapping)
    projected = summarize_lifecycle_state(observer_state if state_available else None)
    raw_events_available = (
        state_available
        and isinstance(observer_state.get("events"), Sequence)
        and not isinstance(
            observer_state.get("events"), (str, bytes, bytearray)
        )
    )

    if persisted_available:
        canonical = _copy_summary(passport_summary)
        source = "passport.lifecycle_summary"
    elif state_available:
        canonical = projected
        source = "observer_state_projection"
    else:
        canonical = projected
        source = "unavailable"

    events = normalize_lifecycle_events(
        observer_state.get("events") if state_available else None
    )
    temporal_integrity = assess_lifecycle_temporal_integrity(
        canonical,
        events,
        raw_events_available=raw_events_available,
    )

    mismatches: list[str] = []
    if persisted_available and state_available:
        for field in _SUMMARY_FIELDS:
            persisted_value = _comparable(field, canonical.get(field))
            projected_value = _comparable(field, projected.get(field))
            if persisted_value != projected_value:
                mismatches.append(field)
        verification_status = "mismatch" if mismatches else "verified"
    elif persisted_available:
        verification_status = "observer_state_unavailable"
    elif state_available:
        verification_status = "passport_summary_unavailable"
    else:
        verification_status = "unavailable"
    if (
        temporal_integrity["status"] == "invalid"
        and verification_status != "mismatch"
    ):
        verification_status = "temporal_invalid"

    return {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "canonical_source": source,
        "verification_status": verification_status,
        "mismatch_fields": mismatches,
        "summary": canonical,
        "observer_state_projection": projected,
        "events": events,
        "temporal_integrity": temporal_integrity,
    }


def normalize_lifecycle_events(value: Any) -> list[dict[str, Any]]:
    """Copy valid typed events without losing historical confidence/details."""

    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        return []

    events: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        tick = _non_negative_int(raw.get("tick"))
        event_type = str(raw.get("event_type") or "").strip()
        scope = str(raw.get("scope") or "").strip()
        if tick is None or not event_type:
            continue
        key = (tick, event_type, scope)
        if key in seen:
            continue
        seen.add(key)

        confidence = _bounded_float(raw.get("confidence"))
        details = raw.get("details")
        event = {
            "tick": tick,
            "event_type": event_type,
            "scope": scope,
            "confidence": confidence,
            "details": deepcopy(dict(details)) if isinstance(details, Mapping) else {},
        }
        events.append(event)

    return sorted(
        events,
        key=lambda item: (item["tick"], item["event_type"], item["scope"]),
    )


def _copy_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: deepcopy(value.get(field))
        for field in _SUMMARY_FIELDS
    }


def _comparable(field: str, value: Any) -> Any:
    if field == "event_types":
        if not isinstance(value, Sequence) or isinstance(
            value, (str, bytes, bytearray)
        ):
            return ()
        return tuple(sorted(str(item) for item in value))
    if field == "first_ticks":
        if not isinstance(value, Mapping):
            return ()
        return tuple(
            sorted(
                (str(key), _non_negative_int(item))
                for key, item in value.items()
            )
        )
    return value


def _non_negative_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _bounded_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if 0.0 <= result <= 1.0 else None


__all__ = [
    "RECONCILIATION_SCHEMA_VERSION",
    "normalize_lifecycle_events",
    "reconcile_lifecycle_contract",
]
