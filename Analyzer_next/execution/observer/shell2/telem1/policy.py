"""Context policy for OL2 right-side scientific telemetry chrome."""
from __future__ import annotations

from enum import Enum

from Analyzer_next.execution.observer.shell2.store import ShellRoute


class MetricRailMode(str, Enum):
    HIDDEN = "hidden"
    FIXED = "fixed"
    DRAWER = "drawer"


def metric_rail_mode(
    route: ShellRoute,
    *,
    analysis_active: bool,
    compact: bool,
) -> MetricRailMode:
    """Metrics belong to live Observation, never to the global shell."""
    if analysis_active or route is not ShellRoute.OBSERVATION:
        return MetricRailMode.HIDDEN
    return MetricRailMode.DRAWER if compact else MetricRailMode.FIXED


__all__ = ["MetricRailMode", "metric_rail_mode"]
