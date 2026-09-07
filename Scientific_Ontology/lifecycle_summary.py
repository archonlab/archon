"""Stable shadow summary for canonical ARCHON lifecycle events.

The summary is deliberately descriptive.  It reports typed events already
present in ``ObserverState`` and never derives a scientific life verdict from
legacy birth/collapse fields.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SUMMARY_SCHEMA_VERSION = "1.0.0"

_PHASE_BY_EVENT = {
    "structure_appearance": "structure_observed",
    "population_emergence": "population_observed",
    "ecosystem_emergence": "ecosystem_observed",
    "organization_onset": "organization_observed",
    "life_evidence_onset": "life_evidence_observed",
    "population_collapse": "population_collapsed",
    "ecological_collapse": "ecology_collapsed",
    "organizational_collapse": "organization_collapsed",
    "structural_extinction": "structurally_extinct",
}
_EVENT_ORDER = {
    "structure_appearance": 10,
    "population_emergence": 20,
    "ecosystem_emergence": 30,
    "organization_onset": 40,
    "life_evidence_onset": 50,
    "population_collapse": 60,
    "ecological_collapse": 70,
    "organizational_collapse": 80,
    "structural_extinction": 90,
}


def summarize_lifecycle_state(
    observer_state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a JSON-safe summary from one serialized ``ObserverState``.

    Missing legacy state is represented as unavailable.  An empty event list
    in a state carrying the lifecycle contract is a real observation: no
    supported typed transition has been recorded yet.
    """

    if not isinstance(observer_state, Mapping):
        return _unavailable_summary()

    metadata = observer_state.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    contract = str(metadata.get("lifecycle_contract") or "")
    raw_events = observer_state.get("events")
    events = _normalized_events(raw_events)
    contract_available = bool(contract) and isinstance(raw_events, Sequence)

    first_ticks: dict[str, int] = {}
    for event in events:
        event_type = event["event_type"]
        tick = event["tick"]
        previous = first_ticks.get(event_type)
        if previous is None or tick < previous:
            first_ticks[event_type] = tick

    latest = events[-1] if events else None
    phase = (
        _PHASE_BY_EVENT.get(latest["event_type"], "typed_event_observed")
        if latest is not None
        else "no_typed_transition_observed"
    )
    history_status = (
        "supported_transitions_from_run_start"
        if contract_available
        else "observer_state_events_only"
        if events
        else "unavailable"
    )

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "mode": "shadow",
        "history_status": history_status,
        "history_complete_for_supported_types": contract_available,
        "observed_through_tick": _non_negative_int(observer_state.get("tick")),
        "phase": phase,
        "event_count": len(events),
        "event_types": sorted(first_ticks),
        "first_ticks": dict(sorted(first_ticks.items())),
        "latest_event_type": latest["event_type"] if latest else None,
        "latest_event_tick": latest["tick"] if latest else None,
    }


def _normalized_events(value: Any) -> list[dict[str, Any]]:
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
        events.append(
            {"tick": tick, "event_type": event_type, "scope": scope}
        )
    return sorted(
        events,
        key=lambda item: (
            item["tick"],
            _EVENT_ORDER.get(item["event_type"], 55),
            item["event_type"],
            item["scope"],
        ),
    )


def _non_negative_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _unavailable_summary() -> dict[str, Any]:
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "mode": "shadow",
        "history_status": "unavailable",
        "history_complete_for_supported_types": False,
        "observed_through_tick": None,
        "phase": "unavailable",
        "event_count": 0,
        "event_types": [],
        "first_ticks": {},
        "latest_event_type": None,
        "latest_event_tick": None,
    }


__all__ = ["SUMMARY_SCHEMA_VERSION", "summarize_lifecycle_state"]
