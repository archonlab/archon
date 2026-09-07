"""Shadow publication of canonical lifecycle events into ARCHON telemetry.

The publisher is intentionally separate from legacy Observer event handling.
It serializes events already present in ``ObserverState`` and never infers a
transition, changes control flow, or appends to the legacy in-memory event log.
"""

from __future__ import annotations

import json
from typing import Any

from Scientific_Ontology.event_types import OntologyEvent
from Scientific_Ontology.observer_state import ObserverState


EVENT_TYPE_PREFIX = "ontology.lifecycle."


def lifecycle_event_key(event: OntologyEvent) -> tuple[int, str, str]:
    """Return the stable identity used to suppress repeated snapshot emission."""

    return (event.tick, event.event_type.value, event.scope.value)


def lifecycle_event_payload(event: OntologyEvent) -> dict[str, Any]:
    """Convert one canonical event to the existing three-column event contract."""

    detail = {
        "confidence": event.confidence,
        "ontology_event_type": event.event_type.value,
        "ontology_schema": "1.0.0",
        "provenance": "observer_state",
        "scope": event.scope.value,
        "source": dict(event.details),
    }
    return {
        "tick": event.tick,
        "type": f"{EVENT_TYPE_PREFIX}{event.event_type.value}",
        "detail": json.dumps(
            detail,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


class LifecycleTelemetryShadowPublisher:
    """Publish each typed lifecycle event once per configured Observer run."""

    def __init__(self) -> None:
        self._published: set[tuple[int, str, str]] = set()

    @property
    def published_count(self) -> int:
        return len(self._published)

    def reset(self) -> None:
        self._published.clear()

    def publish(self, state: ObserverState | None, telemetry: Any) -> int:
        """Write unseen events and return the number newly published.

        A missing or closed telemetry router is a normal pre-configuration
        state. The events remain available in ``ObserverState`` and can be
        published after telemetry is configured.
        """

        if state is None or telemetry is None or getattr(telemetry, "closed", False):
            return 0

        published_now = 0
        for event in state.events:
            key = lifecycle_event_key(event)
            if key in self._published:
                continue
            telemetry.emit("event", lifecycle_event_payload(event))
            self._published.add(key)
            published_now += 1
        return published_now


__all__ = [
    "EVENT_TYPE_PREFIX",
    "LifecycleTelemetryShadowPublisher",
    "lifecycle_event_key",
    "lifecycle_event_payload",
]
