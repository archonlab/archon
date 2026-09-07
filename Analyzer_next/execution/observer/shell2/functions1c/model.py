"""Pure launcher-local settings model for OL2-FUNCTIONS1C."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from Analyzer_next.execution.observer.shell2.metrics import load_default_metric_definitions
from Analyzer_next.execution.observer.shell2.theme import ThemeMode

PREFERENCES_SCHEMA = "archon.ol2-ui-preferences.v1"
RAIL_TABS = frozenset({"instruments", "metrics"})
MIN_RAIL_WIDTH = 300
MAX_RAIL_WIDTH = 620


def default_metric_ids() -> tuple[str, ...]:
    return tuple(item.metric_id for item in load_default_metric_definitions())


@dataclass(frozen=True, slots=True)
class LauncherUIPreferences:
    """Settings that affect only the launcher presentation layer."""

    theme: ThemeMode = ThemeMode.SYSTEM
    rail_tab: str = "instruments"
    rail_width: int = 380
    visible_metric_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        defaults = default_metric_ids()
        visible = self.visible_metric_ids or defaults
        if self.rail_tab not in RAIL_TABS:
            raise ValueError(f"unsupported rail tab: {self.rail_tab}")
        if not MIN_RAIL_WIDTH <= int(self.rail_width) <= MAX_RAIL_WIDTH:
            raise ValueError(f"rail_width must be {MIN_RAIL_WIDTH}..{MAX_RAIL_WIDTH}")
        unknown = set(visible) - set(defaults)
        if unknown:
            raise ValueError(f"unknown metric ids: {sorted(unknown)}")
        if not visible:
            raise ValueError("at least one metric card must remain visible")
        # Canonicalize to registry order regardless of JSON/user order.
        ordered = tuple(item for item in defaults if item in set(visible))
        object.__setattr__(self, "visible_metric_ids", ordered)

    def with_theme(self, value: ThemeMode | str) -> "LauncherUIPreferences":
        return replace(self, theme=ThemeMode(value))

    def with_rail_tab(self, value: str) -> "LauncherUIPreferences":
        return replace(self, rail_tab=str(value))

    def with_rail_width(self, value: int) -> "LauncherUIPreferences":
        return replace(self, rail_width=int(value))

    def with_visible_metrics(self, metric_ids: Iterable[str]) -> "LauncherUIPreferences":
        ids = tuple(str(item) for item in metric_ids)
        if not ids:
            raise ValueError("at least one metric card must remain visible")
        return replace(self, visible_metric_ids=ids)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": PREFERENCES_SCHEMA,
            "theme": self.theme.value,
            "rail_tab": self.rail_tab,
            "rail_width": int(self.rail_width),
            "visible_metric_ids": list(self.visible_metric_ids),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "LauncherUIPreferences":
        if payload.get("schema") != PREFERENCES_SCHEMA:
            raise ValueError("unsupported OL2 UI preferences schema")
        raw_metrics = payload.get("visible_metric_ids")
        if not isinstance(raw_metrics, list):
            raise ValueError("visible_metric_ids must be a list")
        return cls(
            theme=ThemeMode(str(payload.get("theme", ThemeMode.SYSTEM.value))),
            rail_tab=str(payload.get("rail_tab", "instruments")),
            rail_width=int(payload.get("rail_width", 380)),
            visible_metric_ids=tuple(str(item) for item in raw_metrics),
        )


__all__ = [
    "LauncherUIPreferences",
    "MAX_RAIL_WIDTH",
    "MIN_RAIL_WIDTH",
    "PREFERENCES_SCHEMA",
    "RAIL_TABS",
    "default_metric_ids",
]
