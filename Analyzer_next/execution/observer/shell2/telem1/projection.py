"""Project canonical live samples into the six frozen OL2 metric cards."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.telemetry.live import LiveTelemetryFrame, LiveTelemetrySample
from Analyzer_next.execution.observer.shell2.metrics import (
    MetricDefinition,
    MetricSample,
    format_delta,
    format_metric,
    load_default_metric_definitions,
)
from Analyzer_next.execution.observer.shell2.view_model import MetricCardViewModel


class TelemetryProjectionError(ValueError):
    pass


_UNIT_BY_METRIC = {
    "objects": "objects",
    "total_living_mass": "cells",
    "largest": "cells",
    "ecosystem_health": "score",
    "stability_index": "score",
    "life_score": "score",
}

_STATE_SOURCES = (
    ("Life", "life_state"),
    ("Structure", "structural_state"),
    ("Phase", "ecosystem_phase"),
    ("Morphology", "morphology_class"),
    ("Validation", "validation_grade"),
)


def _source_key(source: str) -> str:
    prefix = "samples."
    if not source.startswith(prefix):
        raise TelemetryProjectionError(f"unsupported live source: {source}")
    return source[len(prefix):]


def _numeric(sample: LiveTelemetrySample, key: str) -> float | None:
    value = sample.value(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_sample(
    frame: LiveTelemetryFrame,
    definition: MetricDefinition,
) -> MetricSample:
    key = _source_key(definition.source)
    history = tuple(
        value
        for sample in frame.samples
        if (value := _numeric(sample, key)) is not None
    )
    if not history:
        raise TelemetryProjectionError(
            f"required metric missing from live samples: {definition.source}"
        )
    current = _numeric(frame.samples[-1], key)
    if current is None:
        raise TelemetryProjectionError(
            f"latest sample missing required metric: {definition.source}"
        )
    previous = history[-2] if len(history) >= 2 else current
    secondary = None
    if definition.secondary_source:
        secondary_key = _source_key(definition.secondary_source)
        secondary = _numeric(frame.samples[-1], secondary_key)
    return MetricSample(
        definition=definition,
        value=current,
        previous_value=previous,
        history=history,
        unit=_UNIT_BY_METRIC[definition.metric_id],
        secondary_value=secondary,
    )


def metric_cards_from_frame(
    frame: LiveTelemetryFrame,
) -> tuple[MetricCardViewModel, ...]:
    cards = []
    for index, definition in enumerate(load_default_metric_definitions()):
        sample = _metric_sample(frame, definition)
        secondary = (
            f"confidence {sample.secondary_value:.3f}"
            if sample.secondary_value is not None
            else None
        )
        cards.append(
            MetricCardViewModel(
                metric_id=definition.metric_id,
                label=definition.label,
                value_text=format_metric(sample),
                delta_text=format_delta(sample),
                source_text=f"{definition.source} · {definition.kind}",
                secondary_text=secondary,
                history=sample.history,
                chart_token=f"chart.{index % 5 + 1}",
            )
        )
    return tuple(cards)


def state_strip_from_frame(
    frame: LiveTelemetryFrame,
) -> tuple[tuple[str, str], ...]:
    latest = frame.latest
    if latest is None:
        return tuple((label, "—") for label, _key in _STATE_SOURCES)
    rows = []
    for label, key in _STATE_SOURCES:
        value: Any = latest.value(key)
        rows.append((label, "—" if value in (None, "") else str(value)))
    return tuple(rows)


__all__ = [
    "TelemetryProjectionError",
    "metric_cards_from_frame",
    "state_strip_from_frame",
]
