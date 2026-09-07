"""Read-only UI projection for the Scientific Ontology lifecycle contract.

The viewer must display the same canonical state that is written to passports.
This module deliberately formats an already-built ``ObserverState`` and never
changes classification, lifecycle events, telemetry, or auto-stop behaviour.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from Scientific_Ontology.lifecycle_summary import summarize_lifecycle_state


_FIRST_EVENT_LABELS = (
    ("structure_appearance", "STR"),
    ("population_emergence", "POP"),
    ("organization_onset", "ORG"),
    ("life_evidence_onset", "LIFE"),
)
_TERMINAL_EVENT_LABELS = (
    ("population_collapse", "POP"),
    ("ecological_collapse", "ECO"),
    ("organizational_collapse", "ORG"),
    ("structural_extinction", "STR"),
)


def build_lifecycle_ui_snapshot(
    observer_state: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Return compact, stable text lines for the Observer instrument panel."""

    summary = summarize_lifecycle_state(observer_state)
    if not isinstance(observer_state, Mapping):
        return {
            "state": "phase UNAVAILABLE | state UNKNOWN",
            "coverage": "through n/a | history unavailable | shadow",
            "first": "first STR — | POP — | ORG — | LIFE —",
            "confidence": "conf current n/a | onset ORG n/a | LIFE n/a",
            "terminal": "latest none | collapse none | extinction none",
        }

    life = observer_state.get("life")
    life = life if isinstance(life, Mapping) else {}
    events = _events(observer_state.get("events"))
    first_ticks = summary.get("first_ticks")
    first_ticks = first_ticks if isinstance(first_ticks, Mapping) else {}

    current_confidence = _number(life.get("confidence"))
    organization_confidence = _first_confidence(
        events, "organization_onset"
    )
    life_confidence = _first_confidence(events, "life_evidence_onset")
    latest_type = summary.get("latest_event_type")
    latest_tick = summary.get("latest_event_tick")

    collapses = []
    extinction = []
    for event_type, label in _TERMINAL_EVENT_LABELS:
        event = _first_event(events, event_type)
        if event is None:
            continue
        rendered = f"{label}@{event['tick']}"
        if event_type == "structural_extinction":
            extinction.append(rendered)
        else:
            collapses.append(rendered)

    history = (
        "complete"
        if summary.get("history_complete_for_supported_types")
        else str(summary.get("history_status") or "unavailable")
    )
    phase = _words(summary.get("phase") or "unavailable")
    life_state = _words(life.get("state") or "unknown")
    through = _tick(summary.get("observed_through_tick"))
    latest = (
        f"{_event_label(latest_type)}@{latest_tick}"
        if latest_type and latest_tick is not None
        else "none"
    )

    return {
        "state": f"phase {phase} | state {life_state}",
        "coverage": f"through {through} | history {history} | shadow",
        "first": "first "
        + " | ".join(
            f"{label} {_tick(first_ticks.get(event_type))}"
            for event_type, label in _FIRST_EVENT_LABELS
        ),
        "confidence": (
            f"conf current {_confidence(current_confidence)}"
            f" | onset ORG {_confidence(organization_confidence)}"
            f" | LIFE {_confidence(life_confidence)}"
        ),
        "terminal": (
            f"latest {latest}"
            f" | collapse {','.join(collapses) if collapses else 'none'}"
            f" | extinction {','.join(extinction) if extinction else 'none'}"
        ),
    }


def _events(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        return []
    result = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        event_type = str(raw.get("event_type") or "").strip()
        tick = _non_negative_int(raw.get("tick"))
        if event_type and tick is not None:
            result.append(
                {
                    "event_type": event_type,
                    "tick": tick,
                    "confidence": _number(raw.get("confidence")),
                }
            )
    return sorted(result, key=lambda item: item["tick"])


def _first_event(
    events: Sequence[Mapping[str, Any]],
    event_type: str,
) -> Mapping[str, Any] | None:
    return next(
        (
            event
            for event in events
            if event.get("event_type") == event_type
        ),
        None,
    )


def _first_confidence(
    events: Sequence[Mapping[str, Any]],
    event_type: str,
) -> float | None:
    event = _first_event(events, event_type)
    return _number(event.get("confidence")) if event is not None else None


def _event_label(value: Any) -> str:
    labels = dict(_FIRST_EVENT_LABELS + _TERMINAL_EVENT_LABELS)
    return labels.get(str(value), _words(value))


def _words(value: Any) -> str:
    return str(value).replace("_", " ").strip().upper()


def _tick(value: Any) -> str:
    tick = _non_negative_int(value)
    return str(tick) if tick is not None else "—"


def _confidence(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _non_negative_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


__all__ = ["build_lifecycle_ui_snapshot"]
