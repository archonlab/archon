"""OL2-CATALOG1 persistent validated world-catalog cache."""
from __future__ import annotations

from pathlib import Path

from .cache import CACHE_SCHEMA, CatalogCacheStatus, ValidatedWorldCatalogCache
from .catalog import Catalog1WorldCatalog
from .store import Catalog1ControlShellStore


def build_catalog1(project_root: Path) -> ValidatedWorldCatalogCache:
    root = Path(project_root).expanduser().resolve()
    atlas = root / "Atlas/Worlds"
    search = root / "Results/Universe_Search"
    observations = search / "observation_logs"
    mutations = search / "mutation_runs"
    backend = Catalog1WorldCatalog(
        world_atlas_dir=atlas,
        observation_logs_dir=observations,
        mutation_root=mutations,
    )
    return ValidatedWorldCatalogCache(
        backend,
        project_root=root,
        world_atlas_dir=atlas,
        observation_logs_dir=observations,
        mutation_root=mutations,
        cache_path=root / "Config/ObserverLauncher/cache/world_catalog_v1.json",
    )


__all__ = [
    "CACHE_SCHEMA",
    "Catalog1ControlShellStore",
    "Catalog1WorldCatalog",
    "CatalogCacheStatus",
    "ValidatedWorldCatalogCache",
    "build_catalog1",
]
