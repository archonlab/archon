"""RELEASE3.2 first-run bootstrap contract for launcher-local configuration.

Clean packages contain no machine-local configuration.  The stable Observer
router resolves the authorized production profile first and then materializes
portable launcher defaults.  Source-derived caches remain lazy and are built
only when their runtime owner has inspected the new installation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from Analyzer_next.execution.observer.shell2.cutover1.service import PROFILE_SCHEMA
from Analyzer_next.execution.observer.shell2.functions1c.model import (
    LauncherUIPreferences,
)


SCHEMA = "archon_release3_2_config_first_run_bootstrap_v1"
MILESTONE = "RELEASE3.2-CONFIG-FIRST-RUN-BOOTSTRAP"

CONFIG_BOOTSTRAP_DIRECTORIES = (
    "Config/ObserverLauncher/",
    "Config/ObserverLauncher/cache/",
)

LOCAL_CONFIG_PATHS = (
    "Config/ObserverLauncher/launcher_profile.json",
    "Config/ObserverLauncher/ui_preferences.json",
    "Config/ObserverLauncher/cache/world_catalog_v1.json",
)

CONFIG_OWNER_FILES = (
    "Analyzer_next/cli/observer_launcher_profile.py",
    "Analyzer_next/cli/observer_launcher_2.py",
    "Analyzer_next/execution/observer/shell2/cutover1/service.py",
    "Analyzer_next/adapters/observer/ui_preferences.py",
    "Analyzer_next/execution/observer/shell2/catalog1/__init__.py",
    "Analyzer_next/execution/observer/shell2/catalog1/cache.py",
)


class ConfigBootstrapError(RuntimeError):
    """Raised when portable first-run configuration cannot be created."""


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_new_json(path: Path, payload: object) -> bool:
    """Atomically create a JSON file while preserving any existing state."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".first-run-{os.getpid()}")
    try:
        temp.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if path.exists():
            return False
        os.replace(temp, path)
        return True
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def ensure_config_layout(project_root: Path, *, active_profile: str) -> dict:
    """Create portable launcher defaults without copying builder-machine state."""
    root = Path(project_root).resolve()
    if active_profile not in {"ol2", "modular-v1"}:
        raise ConfigBootstrapError(
            f"Unsupported first-run launcher profile: {active_profile!r}"
        )

    created_directories: list[str] = []
    for relative in CONFIG_BOOTSTRAP_DIRECTORIES:
        target = root / relative
        if not target.exists():
            created_directories.append(relative)
        target.mkdir(parents=True, exist_ok=True)

    seeds = {
        "Config/ObserverLauncher/launcher_profile.json": {
            "schema": PROFILE_SCHEMA,
            "profile": active_profile,
            "updated_at": "first-run",
            "acceptance_receipt_hash": None,
        },
        "Config/ObserverLauncher/ui_preferences.json": (
            LauncherUIPreferences().as_dict()
        ),
    }
    created_files: list[str] = []
    preserved_files: list[str] = []
    try:
        for relative, payload in seeds.items():
            if _write_new_json(root / relative, payload):
                created_files.append(relative)
            else:
                preserved_files.append(relative)
    except OSError as exc:
        raise ConfigBootstrapError(
            f"Cannot create first-run launcher configuration: {exc}"
        ) from exc

    cache = root / "Config/ObserverLauncher/cache/world_catalog_v1.json"
    if cache.exists():
        preserved_files.append(
            "Config/ObserverLauncher/cache/world_catalog_v1.json"
        )
    return {
        "created_directories": created_directories,
        "created_files": created_files,
        "preserved_existing_files": sorted(set(preserved_files)),
        "cache_files_created": [],
        "policy": (
            "portable defaults only; existing local configuration is never "
            "deleted or rewritten; source-derived caches are lazy"
        ),
    }


def build_config_bootstrap_manifest(
    root: Path,
    packaging_files: Iterable[str],
) -> dict:
    """Describe and validate the clean-package Config boundary."""
    root = Path(root).resolve()
    packaged = sorted(set(str(item) for item in packaging_files))
    packaged_config = [
        relative
        for relative in packaged
        if relative == "Config" or relative.startswith("Config/")
    ]
    missing_owners = [
        relative
        for relative in CONFIG_OWNER_FILES
        if (root / relative).is_file() and relative not in packaged
    ]
    blockers: list[dict] = []
    if packaged_config:
        blockers.append({
            "code": "LOCAL_CONFIG_STATE_PACKAGED",
            "detail": (
                f"{len(packaged_config)} machine-local Config file(s) entered "
                "the packaging whitelist"
            ),
            "files": packaged_config,
        })
    if missing_owners:
        blockers.append({
            "code": "CONFIG_RUNTIME_OWNER_MISSING",
            "detail": (
                f"{len(missing_owners)} Config runtime owner(s) are missing "
                "from the runtime closure"
            ),
            "files": missing_owners,
        })

    payload = {
        "schema": SCHEMA,
        "milestone": MILESTONE,
        "status": "PASS" if not blockers else "BLOCKED",
        "bootstrap_mode": "PORTABLE_DEFAULTS_AND_LAZY_CACHE",
        "bootstrap_directories": list(CONFIG_BOOTSTRAP_DIRECTORIES),
        "packaged_config_state": packaged_config,
        "local_config_paths": list(LOCAL_CONFIG_PATHS),
        "first_run_files": {
            "launcher_profile": (
                "authorized active profile; no local acceptance hash"
            ),
            "ui_preferences": "code-owned portable presentation defaults",
            "world_catalog_cache": (
                "created lazily after validating local Atlas/Results sources"
            ),
        },
        "runtime_ownership": {
            "mode": "PACKAGED_PYTHON_CODE",
            "owners": list(CONFIG_OWNER_FILES),
            "missing": missing_owners,
        },
        "first_run_contract": {
            "builder_launcher_profile_absent": True,
            "builder_ui_preferences_absent": True,
            "builder_world_catalog_cache_absent": True,
            "machine_specific_paths_absent": True,
            "authorized_profile_materialized_on_first_observer_launch": True,
            "portable_ui_defaults_materialized_on_first_observer_launch": True,
            "world_catalog_cache_is_source_derived": True,
            "existing_install_config_is_never_deleted": True,
            "existing_install_config_is_never_rewritten": True,
        },
        "blockers": blockers,
    }
    payload["content_hash"] = _canonical_hash(payload)
    return payload


__all__ = [
    "CONFIG_BOOTSTRAP_DIRECTORIES",
    "CONFIG_OWNER_FILES",
    "ConfigBootstrapError",
    "LOCAL_CONFIG_PATHS",
    "MILESTONE",
    "SCHEMA",
    "build_config_bootstrap_manifest",
    "ensure_config_layout",
]
