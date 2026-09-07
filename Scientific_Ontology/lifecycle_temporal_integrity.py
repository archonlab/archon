"""Validate internal time invariants of a persisted lifecycle history.

This module is deliberately descriptive.  It checks transport and chronology
invariants only; it does not infer a life state, require a scientific phase
order, or rewrite the canonical lifecycle summary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


TEMPORAL_INTEGRITY_SCHEMA_VERSION = "1.0.0"


def assess_lifecycle_temporal_integrity(
    summary: Mapping[str, Any] | None,
    events: Sequence[Mapping[str, Any]] | None,
    *,
    raw_events_available: bool,
) -> dict[str, Any]:
    """Return a JSON-safe integrity assessment for one lifecycle source."""

    if not isinstance(summary, Mapping):
        return _result("unavailable", [], raw_events_available)

    issues: list[dict[str, Any]] = []
    observed_through = _non_negative_int(summary.get("observed_through_tick"))
    latest_tick = _non_negative_int(summary.get("latest_event_tick"))
    latest_type = _text(summary.get("latest_event_type"))
    first_ticks = _normalized_first_ticks(summary.get("first_ticks"))

    if (latest_tick is None) != (latest_type is None):
        issues.append(
            _issue(
                "latest_event_pair_incomplete",
                ["latest_event_type", "latest_event_tick"],
                "latest_event_type and latest_event_tick must be present together.",
            )
        )

    declared_ticks = list(first_ticks.values())
    if latest_tick is not None:
        declared_ticks.append(latest_tick)
    declared_max = max(declared_ticks) if declared_ticks else None
    if (
        observed_through is not None
        and declared_max is not None
        and declared_max > observed_through
    ):
        issues.append(
            _issue(
                "event_after_observation_horizon",
                ["observed_through_tick", "first_ticks", "latest_event_tick"],
                (
                    f"Lifecycle declares an event at tick {declared_max}, beyond "
                    f"observed_through_tick {observed_through}."
                ),
            )
        )

    normalized_events = _normalized_events(events)
    if raw_events_available:
        event_count = _non_negative_int(summary.get("event_count"))
        if event_count != len(normalized_events):
            issues.append(
                _issue(
                    "event_count_mismatch",
                    ["event_count", "events"],
                    (
                        f"Summary event_count is {event_count}; normalized raw "
                        f"history contains {len(normalized_events)} events."
                    ),
                )
            )

        raw_first_ticks: dict[str, int] = {}
        for event in normalized_events:
            event_type = event["event_type"]
            tick = event["tick"]
            previous = raw_first_ticks.get(event_type)
            if previous is None or tick < previous:
                raw_first_ticks[event_type] = tick

        if first_ticks != raw_first_ticks:
            issues.append(
                _issue(
                    "first_ticks_mismatch",
                    ["first_ticks", "events"],
                    "Summary first_ticks does not match the raw event history.",
                )
            )

        declared_types = _string_set(summary.get("event_types"))
        raw_types = set(raw_first_ticks)
        if declared_types != raw_types:
            issues.append(
                _issue(
                    "event_types_mismatch",
                    ["event_types", "events"],
                    "Summary event_types does not match the raw event history.",
                )
            )

        if normalized_events:
            raw_latest_tick = max(event["tick"] for event in normalized_events)
            latest_types = {
                event["event_type"]
                for event in normalized_events
                if event["tick"] == raw_latest_tick
            }
            if latest_tick != raw_latest_tick:
                issues.append(
                    _issue(
                        "latest_event_tick_mismatch",
                        ["latest_event_tick", "events"],
                        (
                            f"Summary latest_event_tick is {latest_tick}; raw "
                            f"history ends at tick {raw_latest_tick}."
                        ),
                    )
                )
            if latest_type not in latest_types:
                issues.append(
                    _issue(
                        "latest_event_type_mismatch",
                        ["latest_event_type", "events"],
                        "Summary latest_event_type is not present at the latest raw tick.",
                    )
                )
        elif latest_tick is not None or latest_type is not None:
            issues.append(
                _issue(
                    "latest_event_without_history",
                    ["latest_event_type", "latest_event_tick", "events"],
                    "Summary declares a latest event but the raw history is empty.",
                )
            )

        raw_max = (
            max(event["tick"] for event in normalized_events)
            if normalized_events
            else None
        )
        if (
            observed_through is not None
            and raw_max is not None
            and raw_max > observed_through
            and not any(
                issue["code"] == "event_after_observation_horizon"
                for issue in issues
            )
        ):
            issues.append(
                _issue(
                    "event_after_observation_horizon",
                    ["observed_through_tick", "events"],
                    (
                        f"Raw lifecycle history reaches tick {raw_max}, beyond "
                        f"observed_through_tick {observed_through}."
                    ),
                )
            )

    if issues:
        status = "invalid"
    elif raw_events_available:
        status = "valid"
    else:
        status = "summary_only"
    return _result(status, issues, raw_events_available)


def _result(
    status: str,
    issues: list[dict[str, Any]],
    raw_events_available: bool,
) -> dict[str, Any]:
    return {
        "schema_version": TEMPORAL_INTEGRITY_SCHEMA_VERSION,
        "status": status,
        "issue_count": len(issues),
        "issue_codes": sorted({issue["code"] for issue in issues}),
        "issues": issues,
        "raw_events_available": bool(raw_events_available),
        "scientific_policy": {
            "changes_lifecycle_history": False,
            "changes_scientific_thresholds": False,
            "infers_phase_order": False,
        },
    }


def _issue(code: str, fields: list[str], explanation: str) -> dict[str, Any]:
    return {
        "code": code,
        "fields": fields,
        "explanation": explanation,
    }


def _normalized_events(
    value: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        tick = _non_negative_int(raw.get("tick"))
        event_type = _text(raw.get("event_type"))
        if tick is None or event_type is None:
            continue
        normalized.append({"tick": tick, "event_type": event_type})
    return normalized


def _normalized_first_ticks(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, raw_tick in value.items():
        event_type = _text(key)
        tick = _non_negative_int(raw_tick)
        if event_type is not None and tick is not None:
            result[event_type] = tick
    return result


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        return set()
    return {
        text
        for item in value
        if (text := _text(item)) is not None
    }


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _non_negative_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


__all__ = [
    "TEMPORAL_INTEGRITY_SCHEMA_VERSION",
    "assess_lifecycle_temporal_integrity",
]
