"""Toolkit-independent launcher settings controller for OL2-FUNCTIONS1C."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from Analyzer_next.execution.observer.shell2.theme import ThemeMode

from .model import LauncherUIPreferences


class UIPreferencesRepository(Protocol):
    def load(self) -> LauncherUIPreferences: ...
    def save(self, preferences: LauncherUIPreferences) -> None: ...


class PathOpenPort(Protocol):
    def open(self, path: Path) -> None: ...


class LauncherSettingsController:
    """Own only launcher-local preferences and safe desktop path handoffs."""

    def __init__(
        self,
        repository: UIPreferencesRepository,
        path_opener: PathOpenPort | None = None,
    ) -> None:
        self.repository = repository
        self.path_opener = path_opener
        self._preferences = repository.load()

    @property
    def preferences(self) -> LauncherUIPreferences:
        return self._preferences

    def _commit(self, preferences: LauncherUIPreferences) -> LauncherUIPreferences:
        self.repository.save(preferences)
        self._preferences = preferences
        return preferences

    def set_theme(self, value: ThemeMode | str) -> LauncherUIPreferences:
        return self._commit(self._preferences.with_theme(value))

    def set_rail_tab(self, value: str) -> LauncherUIPreferences:
        return self._commit(self._preferences.with_rail_tab(value))

    def set_rail_width(self, value: int) -> LauncherUIPreferences:
        return self._commit(self._preferences.with_rail_width(value))

    def set_metric_visible(self, metric_id: str, visible: bool) -> LauncherUIPreferences:
        current = list(self._preferences.visible_metric_ids)
        if visible and metric_id not in current:
            current.append(metric_id)
        elif not visible and metric_id in current:
            current.remove(metric_id)
        return self._commit(self._preferences.with_visible_metrics(current))

    def reset_defaults(self) -> LauncherUIPreferences:
        return self._commit(LauncherUIPreferences())

    def open_path(self, path: Path) -> None:
        if self.path_opener is None:
            raise RuntimeError("desktop path opener is unavailable")
        self.path_opener.open(path)


__all__ = [
    "LauncherSettingsController",
    "PathOpenPort",
    "UIPreferencesRepository",
]
