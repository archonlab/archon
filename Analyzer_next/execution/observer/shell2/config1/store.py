"""Bridge the pure CONFIG1 workflow into the existing SHELL1 preview store."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from Analyzer_next.execution.observer.settings import SEARCH_RESULTS_DIR
from Analyzer_next.execution.observer.shell2.store import FakeShellStore, ShellRoute, ShellSnapshot
from Analyzer_next.execution.observer.shell2.theme import ColorScheme, ThemeMode

from .catalog_adapter import NativeWorldCatalog
from .command_service import ObserverCommandService
from .model import ProvenanceKind, WorldRecord
from .workflow import ConfigSnapshot, ConfigurationWorkflow


class ConfigShellStore(FakeShellStore):
    """SHELL1 fake lifecycle plus a separate non-production CONFIG1 workflow."""

    def __init__(
        self,
        *,
        theme_preference: ThemeMode = ThemeMode.SYSTEM,
        system_scheme: ColorScheme | None = None,
        catalog: NativeWorldCatalog | None = None,
        worlds: Iterable[WorldRecord] | None = None,
        default_output_dir: Path | None = None,
    ) -> None:
        super().__init__(
            theme_preference=theme_preference,
            system_scheme=system_scheme,
        )
        output_dir = (
            Path(default_output_dir)
            if default_output_dir is not None
            else SEARCH_RESULTS_DIR / "observation_logs"
        )
        service = ObserverCommandService(default_output_dir=output_dir)
        self.workflow = ConfigurationWorkflow(
            service,
            default_output_dir=output_dir,
        )
        self.catalog = catalog or NativeWorldCatalog()
        self.catalog_error: str | None = None
        try:
            loaded = tuple(worlds) if worlds is not None else self.catalog.load_worlds()
        except Exception as exc:
            loaded = ()
            self.catalog_error = f"{type(exc).__name__}: {exc}"
        self.workflow.load_worlds(loaded)

    @property
    def config_snapshot(self) -> ConfigSnapshot:
        return self.workflow.snapshot

    def _notify_config(self) -> ShellSnapshot:
        return self._publish(self.snapshot)

    def reload_worlds(self) -> ShellSnapshot:
        try:
            worlds = self.catalog.load_worlds()
        except Exception as exc:
            self.catalog_error = f"{type(exc).__name__}: {exc}"
            worlds = ()
        else:
            self.catalog_error = None
        self.workflow.load_worlds(worlds)
        return self._notify_config()

    def set_world_filters(self, **changes: str) -> ShellSnapshot:
        self.workflow.set_filters(**changes)
        return self._notify_config()

    def select_world(self, rule_id: int) -> ShellSnapshot:
        self.workflow.select_world(rule_id)
        return self.select_route(ShellRoute.RUNS)

    def update_configuration(self, **changes: Any) -> ShellSnapshot:
        self.workflow.update_draft(**changes)
        return self._notify_config()

    def set_provenance(self, provenance: ProvenanceKind | str) -> ShellSnapshot:
        self.workflow.set_provenance(provenance)
        return self._notify_config()

    def review_configuration(self) -> ShellSnapshot:
        self.workflow.review()
        return self._notify_config()

    def back_to_worlds(self) -> ShellSnapshot:
        self.workflow.back_to_worlds()
        return self.select_route(ShellRoute.WORLDS)
