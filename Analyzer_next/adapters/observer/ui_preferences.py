"""JSON repository for launcher-local OL2 UI preferences."""
from __future__ import annotations

import json
import os
from pathlib import Path

from Analyzer_next.execution.observer.shell2.functions1c.model import LauncherUIPreferences


class JSONUIPreferencesRepository:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def load(self) -> LauncherUIPreferences:
        if not self.path.exists():
            return LauncherUIPreferences()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("preferences root must be an object")
            return LauncherUIPreferences.from_dict(payload)
        except Exception:
            # Corrupt launcher-local preferences may never block Observer.
            return LauncherUIPreferences()

    def save(self, preferences: LauncherUIPreferences) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}")
        temp.write_text(
            json.dumps(preferences.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, self.path)


__all__ = ["JSONUIPreferencesRepository"]
