"""CATALOG1 projection store layered above frozen CONTROL1/CONFIG1 stores."""
from __future__ import annotations

from Analyzer_next.execution.observer.shell2.control1.store import ControlShellStore


class Catalog1ControlShellStore(ControlShellStore):
    """Force a real catalog rebuild only for an explicit Worlds refresh."""

    def reload_worlds(self):
        try:
            refresh = getattr(self.catalog, "refresh_worlds", None)
            worlds = refresh() if callable(refresh) else self.catalog.load_worlds()
        except Exception as exc:
            self.catalog_error = f"{type(exc).__name__}: {exc}"
            worlds = ()
        else:
            self.catalog_error = None
        self.workflow.load_worlds(worlds)
        return self._notify_config()

    @property
    def catalog_cache_status(self):
        return getattr(self.catalog, "status", None)


__all__ = ["Catalog1ControlShellStore"]
