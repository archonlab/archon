#!/usr/bin/env python3
"""Local runtime bridge for ARCHON Studio.

STUDIO8 keeps the command boundary intentionally narrow while adding web-native
operator surfaces for Search and Observer. Native launchers remain available as
fallbacks. Embedded Search starts the canonical Universe Search engine directly;
Embedded Observer starts the canonical Observer in headless mode and consumes a
read-only presentation stream emitted by that same process. No simulation,
measurement, evidence, or Analyzer logic is reimplemented in the browser.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
import platform
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlparse

from archon_runtime_python import runtime_python_command

_PROJECT_IMPORT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_IMPORT_ROOT))
from World_Portability import WorldPortabilityError, WorldPortabilityService  # noqa: E402
from World_Portability.service import MAX_PACKAGE_BYTES  # noqa: E402
from Universe_Search.search_runtime_contract import (  # noqa: E402
    canonical_search_command,
    validate_search_runtime,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
ENGINE_NAMES = ("search", "observer", "analyzer")
SEARCH_MODES = ("ordinary", "diversity", "cohort_target", "counterexample", "local_around_rule")
OBSERVER_SPEED_VALUES = (1, 2, 10, 20, 50, 100, 200, 500, 1000)
ADAPTER_REGISTRY_SCHEMA = "archon_studio_adapter_registry_v1"
ADAPTER_MANIFEST_SCHEMA = "archon_adapter_manifest_v1"
ADAPTER_MANIFEST_NAMES = ("archon_adapter.json", ".archon/adapter.json")
STUDIO_SETTINGS_SCHEMA = "archon_studio_settings_v1"
STUDIO_SETTINGS_VERSION = "STUDIO11"
STUDIO_BUILD_VERSION = "STUDIO20.5"
STUDIO_DEFAULT_SETTINGS = {
    "researcher_name": "",
    "project_name": "Local ARCHON Project",
    "default_engine_mode": "embedded",
    "appearance": "midnight",
    "density": "comfortable",
    "motion": "full",
    "onboarding_completed": False,
}

_GEN_RE = re.compile(r"Generation\s+(\d+)/(\d+)\s+mode=([^\s]+)")
_WORKERS_RE = re.compile(r"parallel eval:\s+workers=(\d+),\s+jobs=(\d+)")
_EVAL_RE = re.compile(r"eval\s+(\d+)/(\d+)\s+done\s+\(failed=(\d+),\s+elapsed=(\d+)s\)")
_HEART_RE = re.compile(r"eval heartbeat:\s+(\d+)/(\d+)\s+done,.*?elapsed=(\d+)s")
_TARGET_RE = re.compile(r"\[TargetScoring\]\s+gen=(\d+)\s+exact=(\d+)\s+best_rule=([^\s]+)\s+distance=([^\s]+)\s+coverage=([^\s]+)")
_BEST_RE = re.compile(r"BEST\s+gen=(\d+):\s+rule=([^\s]+)\s+score=([^\s]+)\s+\|\s+best ever=([^\s]+)\s+([^\s]+)")
_GEN_TIME_RE = re.compile(r"generation time:\s+([0-9.]+)\s+min")
_STUDIO_OBSERVER_PREFIX = "ARCHON_STUDIO_OBSERVER_JSON="
_HEADLESS_OBSERVER_PREFIX = "ARCHON_HEADLESS_OBSERVER_JSON="
_SEARCH_RUNTIME_PREFIX = "ARCHON_SEARCH_RUNTIME_JSON="


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_stat(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return 0, 0


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _normalize_rule_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return f"{int(text):05d}"
    except ValueError:
        return text


def _literal_assignments(path: Path, names: set[str]) -> dict[str, Any]:
    """Read simple constant assignments without importing the scientific module."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception:
        return {}
    found: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name not in names:
            continue
        try:
            found[name] = ast.literal_eval(node.value)
        except Exception:
            continue
    return found


@dataclass(slots=True)
class EngineSpec:
    key: str
    label: str
    command: list[str]
    start_label: str
    description: str


@dataclass(slots=True)
class EngineRuntime:
    spec: EngineSpec
    process: subprocess.Popen[str] | None = None
    status: str = "IDLE"
    pid: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    stop_requested: bool = False
    launch_mode: str = "native"
    config: dict[str, Any] = field(default_factory=dict)
    live: dict[str, Any] = field(default_factory=dict)
    event_seq: int = 0
    started_ns: int = 0
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=160))
    lock: threading.RLock = field(default_factory=threading.RLock)

    def append_event(self, message: str, level: str = "info") -> None:
        text = str(message).rstrip("\n")
        if not text:
            return
        with self.lock:
            self.event_seq += 1
            self.events.append({"seq": self.event_seq, "timestamp": utc_now(), "level": level, "message": text[:4000]})


class StudioRuntimeBridge:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.python_command = runtime_python_command(self.root)
        self.snapshot_builder = self.root / "Tools" / "archon_studio_snapshot.py"
        self.snapshot_path = self.root / "archon-studio" / "public" / "studio" / "snapshot.json"
        self.snapshot_meta_path = self.snapshot_path.with_name("snapshot.sync.json")
        self.search_script = self.root / "Universe_Search" / "universe_search_v34_closed_research_cycle.py"
        self.search_core = self.root / "Universe_Search" / "universe_search_core.py"
        self.observer_script = self.root / "Observer" / "universe_search_observer_v441_validation_calibration.py"
        self.observer_studio_adapter = self.root / "Tools" / "archon_studio_observer_adapter.py"
        self.observer_launcher_adapter = self.root / "Tools" / "archon_studio_observer_launcher_adapter.py"
        self.search_results = self.root / "Results" / "Universe_Search"
        self.telemetry_database = self.search_results / "observation_logs" / "telemetry.sqlite"
        self.default_experiment_plan = self.root / "Results" / "Analysis" / "experiment_plan.json"
        self.adapter_registry_path = self.root / "Config" / "Studio" / "adapters.json"
        self.settings_path = self.root / "Config" / "Studio" / "settings.json"
        self.release_readiness_path = self.root / "Results" / "Studio" / "release_readiness.json"
        self.adapter_lock = threading.RLock()
        self.settings_lock = threading.RLock()
        self.world_portability = WorldPortabilityService(self.root)

        core_constants = _literal_assignments(self.search_core, {"SCORE_MODES", "POPULATION", "GENERATIONS"})
        score_modes = core_constants.get("SCORE_MODES")
        self.search_score_modes = [str(value) for value in score_modes] if isinstance(score_modes, (list, tuple)) else ["observer_niches"]
        self.search_population = int(core_constants.get("POPULATION") or 0)
        self.search_generations = int(core_constants.get("GENERATIONS") or 0)

        self.specs = {
            "search": EngineSpec(
                key="search",
                label="Search",
                command=[*self.python_command, str(self.root / "Universe_Search" / "search_launcher.py")],
                start_label="Open Search Launcher",
                description="Universe Search can run embedded in Studio or through the canonical native Search Launcher.",
            ),
            "observer": EngineSpec(
                key="observer",
                label="Observer",
                command=[*self.python_command, str(self.root / "Analyzer_next" / "cli" / "observer_launcher_profile.py")],
                start_label="Open Observer",
                description="Observer can run a canonical single-rule observation embedded in Studio or open the full native laboratory for queues and advanced experiment controls.",
            ),
            "analyzer": EngineSpec(
                key="analyzer",
                label="Analyzer",
                command=[*self.python_command, str(self.root / "Analyzer_next" / "cli" / "analyze_results.py")],
                start_label="Run Analyzer",
                description="Run the production Analyzer cutover entrypoint and stream its console output into Studio.",
            ),
        }
        self.engines = {key: EngineRuntime(spec) for key, spec in self.specs.items()}
        self.snapshot_lock = threading.RLock()
        self.snapshot_building = False
        self.snapshot_last_error: str | None = None
        self.snapshot_last_build_started: str | None = None
        self.snapshot_last_build_finished: str | None = None
        self.snapshot_last_source_signature = self.source_signature()
        self.snapshot_dirty_at: float | None = None
        self.snapshot_build_seq = 0
        self.snapshot_last_reason: str | None = None
        self.snapshot_last_success_revision = self.snapshot_revision()
        self.shutdown_event = threading.Event()
        self.watcher_thread = threading.Thread(target=self._watch_sources, name="studio-source-watch", daemon=True)

    def source_files(self) -> list[Path]:
        knowledge = self.root / "Atlas" / "Knowledge"
        worlds = self.root / "Atlas" / "Worlds"
        return [
            knowledge / "knowledge_base.json",
            knowledge / "research_atlas.json",
            knowledge / "prediction_database.json",
            knowledge / "research_director_history.json",
            knowledge / "consensus_database.json",
            knowledge / "meta_science_history.json",
            worlds / "atlas_index.json",
            worlds / "atlas_index.jsonl",
        ]

    def source_signature(self) -> str:
        parts = []
        for path in self.source_files():
            mtime_ns, size = _safe_stat(path)
            parts.append(f"{path.name}:{mtime_ns}:{size}")
        return "|".join(parts)

    def snapshot_revision(self) -> str:
        mtime_ns, size = _safe_stat(self.snapshot_path)
        return f"{mtime_ns}:{size}"

    def options_payload(self) -> dict[str, Any]:
        return {
            "search": {
                "ui_modes": ["embedded", "native"],
                "score_modes": self.search_score_modes,
                "search_modes": list(SEARCH_MODES),
                "defaults": {
                    "score_mode": "observer_niches" if "observer_niches" in self.search_score_modes else self.search_score_modes[0],
                    "search_mode": "ordinary",
                    "experiment_plan": self.default_experiment_plan.relative_to(self.root).as_posix(),
                    "population": self.search_population,
                    "generations": self.search_generations,
                },
            },
            "observer": {
                "ui_modes": ["embedded", "native"],
                "speed_values": list(OBSERVER_SPEED_VALUES),
                "defaults": {
                    "max_ticks": 100000,
                    "speed": 2,
                    "sample_every": 1,
                    "autosave_every": 50000,
                    "field_width": 96,
                    "field_height": 64,
                },
            },
        }

    def _normalize_settings(self, payload: Any) -> dict[str, Any]:
        source = payload if isinstance(payload, dict) else {}
        settings = dict(STUDIO_DEFAULT_SETTINGS)
        researcher_name = str(source.get("researcher_name") or "").strip()[:80]
        project_name = str(source.get("project_name") or STUDIO_DEFAULT_SETTINGS["project_name"]).strip()[:120]
        if not project_name:
            project_name = str(STUDIO_DEFAULT_SETTINGS["project_name"])
        engine_mode = str(source.get("default_engine_mode") or "embedded")
        appearance = str(source.get("appearance") or "midnight")
        density = str(source.get("density") or "comfortable")
        motion = str(source.get("motion") or "full")
        settings.update({
            "researcher_name": researcher_name,
            "project_name": project_name,
            "default_engine_mode": engine_mode if engine_mode in {"embedded", "native", "ask"} else "embedded",
            "appearance": appearance if appearance in {"midnight", "graphite", "light"} else "midnight",
            "density": density if density in {"comfortable", "compact"} else "comfortable",
            "motion": motion if motion in {"full", "reduced"} else "full",
            "onboarding_completed": bool(source.get("onboarding_completed", False)),
        })
        return settings

    def _load_settings(self) -> tuple[dict[str, Any], str | None]:
        with self.settings_lock:
            try:
                payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return dict(STUDIO_DEFAULT_SETTINGS), None
            except Exception as exc:
                return dict(STUDIO_DEFAULT_SETTINGS), f"Cannot read Studio settings: {exc}"
            if not isinstance(payload, dict):
                return dict(STUDIO_DEFAULT_SETTINGS), "Studio settings root must be a JSON object"
            if payload.get("schema") not in {None, STUDIO_SETTINGS_SCHEMA}:
                return dict(STUDIO_DEFAULT_SETTINGS), f"Unsupported Studio settings schema: {payload.get('schema')}"
            return self._normalize_settings(payload.get("settings", payload)), None

    def _save_settings(self, settings: dict[str, Any]) -> None:
        payload = {
            "schema": STUDIO_SETTINGS_SCHEMA,
            "version": STUDIO_SETTINGS_VERSION,
            "updated_at": utc_now(),
            "settings": self._normalize_settings(settings),
        }
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.settings_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.settings_path)

    def _path_diagnostic(self, path: Path) -> dict[str, Any]:
        exists = path.exists()
        directory = path if path.is_dir() else path.parent
        return {
            "path": str(path),
            "exists": exists,
            "is_directory": path.is_dir() if exists else False,
            "writable": os.access(directory if directory.exists() else self.root, os.W_OK),
        }

    def _license_diagnostic(self) -> dict[str, Any]:
        for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
            path = self.root / name
            if path.is_file():
                try:
                    head = path.read_text(encoding="utf-8", errors="replace")[:600].lower()
                except OSError:
                    head = ""
                label = "Bundled license file"
                if "affero" in head or "agpl" in head:
                    label = "GNU Affero General Public License"
                elif "gnu general public license" in head:
                    label = "GNU General Public License"
                return {"present": True, "path": str(path), "label": label}
        return {"present": False, "path": None, "label": "License file not present in this release tree"}

    def _release_readiness_diagnostic(self) -> dict[str, Any]:
        path = self.release_readiness_path
        if not path.is_file():
            return {
                "present": False,
                "path": path.relative_to(self.root).as_posix(),
                "studio_version": STUDIO_BUILD_VERSION,
                "functional_status": "NOT_RUN",
                "packaging_status": "NOT_RUN",
                "final_release_status": "NOT_RUN",
                "generated_at": None,
                "summary": {"pass": 0, "warn": 0, "skip": 0, "fail": 0},
                "release_blockers": [],
            }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "present": True,
                "path": path.relative_to(self.root).as_posix(),
                "studio_version": STUDIO_BUILD_VERSION,
                "functional_status": "INVALID",
                "packaging_status": "INVALID",
                "final_release_status": "INVALID",
                "generated_at": None,
                "summary": {"pass": 0, "warn": 0, "skip": 0, "fail": 1},
                "release_blockers": [],
                "error": str(exc),
            }
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        blockers = payload.get("release_blockers") if isinstance(payload.get("release_blockers"), list) else []
        return {
            "present": True,
            "path": path.relative_to(self.root).as_posix(),
            "studio_version": str(payload.get("studio_version") or ""),
            "functional_status": str(payload.get("functional_status") or "UNKNOWN"),
            "packaging_status": str(payload.get("packaging_status") or "UNKNOWN"),
            "final_release_status": str(payload.get("final_release_status") or "UNKNOWN"),
            "generated_at": payload.get("generated_at"),
            "summary": {
                "pass": int(summary.get("pass") or 0),
                "warn": int(summary.get("warn") or 0),
                "skip": int(summary.get("skip") or 0),
                "fail": int(summary.get("fail") or 0),
            },
            "release_blockers": blockers[:8],
        }

    def diagnostics_payload(self) -> dict[str, Any]:
        results = self.root / "Results"
        atlas = self.root / "Atlas"
        config = self.root / "Config"
        usage = shutil.disk_usage(self.root)
        return {
            "schema": "archon_studio_diagnostics_v1",
            "generated_at": utc_now(),
            "studio_version": STUDIO_BUILD_VERSION,
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
            },
            "python": {"version": platform.python_version(), "executable": sys.executable, "child_runtime_command": list(self.python_command)},
            "tools": {"node": shutil.which("node"), "npm": shutil.which("npm"), "xdg_open": shutil.which("xdg-open")},
            "paths": {
                "project": self._path_diagnostic(self.root),
                "results": self._path_diagnostic(results),
                "atlas": self._path_diagnostic(atlas),
                "config": self._path_diagnostic(config),
                "snapshot": self._path_diagnostic(self.snapshot_path),
            },
            "launchers": {
                "search": (self.root / "UNIVERSE SEARCH.sh").is_file(),
                "observer": (self.root / "OBSERVER.sh").is_file(),
                "analyzer": (self.root / "ANALYZER.sh").is_file(),
            },
            "research": {
                "atlas_index_present": (self.root / "Atlas" / "Worlds" / "atlas_index.json").is_file(),
                "knowledge_base_present": (self.root / "Atlas" / "Knowledge" / "knowledge_base.json").is_file(),
            },
            "disk": {"total_bytes": usage.total, "free_bytes": usage.free},
            "license": self._license_diagnostic(),
            "release_readiness": self._release_readiness_diagnostic(),
        }

    def settings_payload(self, *, include_diagnostics: bool = True) -> dict[str, Any]:
        settings, error = self._load_settings()
        payload: dict[str, Any] = {
            "schema": STUDIO_SETTINGS_SCHEMA,
            "version": STUDIO_SETTINGS_VERSION,
            "generated_at": utc_now(),
            "path": self.settings_path.relative_to(self.root).as_posix(),
            "error": error,
            "settings": settings,
            "choices": {
                "default_engine_mode": ["embedded", "native", "ask"],
                "appearance": ["midnight", "graphite", "light"],
                "density": ["comfortable", "compact"],
                "motion": ["full", "reduced"],
            },
        }
        if include_diagnostics:
            payload["diagnostics"] = self.diagnostics_payload()
        return payload

    def update_settings(self, config: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        current, error = self._load_settings()
        if error:
            # A corrupt local preference file should not brick Studio. A valid
            # explicit save replaces it with a normalized settings document.
            current = dict(STUDIO_DEFAULT_SETTINGS)
        patch = config.get("settings", config)
        if not isinstance(patch, dict):
            return 400, {"error": "invalid_settings", "detail": "settings must be a JSON object"}
        merged = dict(current)
        merged.update(patch)
        normalized = self._normalize_settings(merged)
        with self.settings_lock:
            self._save_settings(normalized)
        return 200, {"ok": True, "settings": self.settings_payload()}

    def open_folder(self, key: str) -> tuple[int, dict[str, Any]]:
        allowed = {
            "project": self.root,
            "results": self.root / "Results",
            "atlas": self.root / "Atlas",
            "config": self.root / "Config",
        }
        path = allowed.get(str(key))
        if path is None:
            return 400, {"error": "folder_not_allowed"}
        path.mkdir(parents=True, exist_ok=True)
        command: list[str] | None = None
        if sys.platform.startswith("linux") and shutil.which("xdg-open"):
            command = ["xdg-open", str(path)]
        elif sys.platform == "darwin" and shutil.which("open"):
            command = ["open", str(path)]
        elif os.name == "nt":
            try:
                os.startfile(str(path))  # type: ignore[attr-defined]
                return 200, {"ok": True, "key": key}
            except OSError as exc:
                return 500, {"error": "open_folder_failed", "detail": str(exc)}
        if command is None:
            return 501, {"error": "open_folder_unavailable", "detail": "No supported desktop folder opener is available"}
        try:
            subprocess.Popen(command, cwd=str(self.root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            return 500, {"error": "open_folder_failed", "detail": str(exc)}
        return 200, {"ok": True, "key": key}

    def _snapshot_is_stale_on_disk(self) -> bool:
        """Detect canonical changes that happened while the Studio bridge was offline."""
        _, snapshot_size = _safe_stat(self.snapshot_path)
        if snapshot_size <= 0:
            return True
        try:
            snapshot = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return True
        source_state = snapshot.get("source_state") if isinstance(snapshot, dict) else None
        # STUDIO12.1 publishes immutable, generation-scoped preview assets.  A
        # pre-12.1 snapshot can contain flat preview URLs that were vulnerable
        # to a rebuild race, so force a one-time migration on bridge startup.
        if isinstance(source_state, dict) and not bool(source_state.get("research_empty")):
            if not str(source_state.get("preview_generation") or "").startswith("g"):
                return True
        try:
            meta = json.loads(self.snapshot_meta_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return True
        return str(meta.get("source_signature") or "") != self.source_signature()

    def start(self) -> None:
        self.watcher_thread.start()
        if self._snapshot_is_stale_on_disk():
            self.request_snapshot_refresh(reason="bridge-startup-stale", immediate=True)

    def shutdown(self) -> None:
        self.shutdown_event.set()
        for runtime in self.engines.values():
            self._terminate_runtime(runtime, user_requested=True, force_after=1.5)

    def _engine_payload(self, runtime: EngineRuntime) -> dict[str, Any]:
        with runtime.lock:
            process = runtime.process
            alive = process is not None and process.poll() is None
            status = runtime.status
            if process is not None and not alive and status in {"RUNNING", "PAUSED"}:
                attested_search = (
                    runtime.spec.key == "search"
                    and runtime.launch_mode == "embedded"
                    and runtime.live.get("process_attested")
                    and runtime.live.get("completion_attested")
                )
                status = "COMPLETE" if process.returncode == 0 and (runtime.spec.key != "search" or runtime.launch_mode != "embedded" or attested_search) else "FAILED"
            return {
                "key": runtime.spec.key,
                "label": runtime.spec.label,
                "status": status,
                "pid": runtime.pid if alive else None,
                "started_at": runtime.started_at,
                "finished_at": runtime.finished_at,
                "exit_code": runtime.exit_code,
                "pause_supported": os.name == "posix",
                "start_label": runtime.spec.start_label,
                "description": runtime.spec.description,
                "ui_mode": runtime.launch_mode,
                "config": dict(runtime.config),
                "live": dict(runtime.live),
                "events": list(runtime.events),
            }

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "archon_studio_runtime_v1",
            "bridge": {
                "status": "READY",
                "generated_at": utc_now(),
                "root": ".",
                "root_identity": hashlib.sha256(os.fsencode(str(self.root))).hexdigest(),
                "host": DEFAULT_HOST,
                "pid": os.getpid(),
                "version": STUDIO_BUILD_VERSION,
                "capabilities": ["embedded_search", "canonical_search_runtime_v1", "pid_bound_search_telemetry_v1", "embedded_observer", "embedded_observer_preview", "observer_fast_live", "observer_preview_stop_choices", "observer_native_context_handoff", "native_fallback", "snapshot_refresh", "adapter_manager_v1", "studio_settings_v1", "studio_diagnostics_v1", "open_folder_v1", "runtime_sync_v1", "preview_asset_sync_v1", "release_readiness_v1", "production_frontend_v1", "desktop_launcher_v1", "world_portability_v1", "world_collection_export_v1", "world_collection_import_v1"],
            },
            "snapshot": {
                "revision": self.snapshot_revision(),
                "source_revision": self.snapshot_last_source_signature,
                "stale": self.snapshot_dirty_at is not None,
                "build_status": "RUNNING" if self.snapshot_building else "IDLE",
                "last_build_started": self.snapshot_last_build_started,
                "last_build_finished": self.snapshot_last_build_finished,
                "last_error": self.snapshot_last_error,
                "build_seq": self.snapshot_build_seq,
                "last_reason": self.snapshot_last_reason,
                "last_success_revision": self.snapshot_last_success_revision,
            },
            "options": self.options_payload(),
            "settings": self.settings_payload(include_diagnostics=False)["settings"],
            "engines": {key: self._engine_payload(runtime) for key, runtime in self.engines.items()},
        }

    def _adapter_manifest_template(self) -> dict[str, Any]:
        return {
            "schema": ADAPTER_MANIFEST_SCHEMA,
            "id": "my-scientific-engine",
            "name": "My Scientific Engine",
            "version": "0.1.0",
            "description": "Short human-readable description of the external engine.",
            "engine_type": "simulation",
            "capabilities": ["results"],
            "entrypoints": {
                "launch": ["python3", "main.py"]
            },
            "data_roots": ["Results"],
        }

    def _load_adapter_registry(self) -> dict[str, Any]:
        with self.adapter_lock:
            try:
                payload = json.loads(self.adapter_registry_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return {"schema": ADAPTER_REGISTRY_SCHEMA, "updated_at": None, "adapters": []}
            except Exception as exc:
                return {
                    "schema": ADAPTER_REGISTRY_SCHEMA,
                    "updated_at": None,
                    "adapters": [],
                    "registry_error": f"Cannot read adapter registry: {exc}",
                }
            if not isinstance(payload, dict) or payload.get("schema") != ADAPTER_REGISTRY_SCHEMA:
                return {
                    "schema": ADAPTER_REGISTRY_SCHEMA,
                    "updated_at": None,
                    "adapters": [],
                    "registry_error": "Adapter registry schema is invalid.",
                }
            rows = payload.get("adapters")
            if not isinstance(rows, list):
                rows = []
            payload["adapters"] = [row for row in rows if isinstance(row, dict)]
            return payload

    def _save_adapter_registry(self, rows: list[dict[str, Any]]) -> None:
        payload = {"schema": ADAPTER_REGISTRY_SCHEMA, "updated_at": utc_now(), "adapters": rows}
        self.adapter_registry_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.adapter_registry_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.adapter_registry_path)

    def _external_adapter_path(self, value: Any, *, must_exist: bool = True) -> Path:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("adapter folder path cannot be empty")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (self.root / candidate)
        try:
            resolved = candidate.resolve(strict=must_exist)
        except FileNotFoundError as exc:
            raise ValueError(f"adapter folder not found: {raw}") from exc
        if must_exist and not resolved.is_dir():
            raise ValueError("adapter path must point to a directory")
        return resolved

    def _adapter_id(self, path: Path) -> str:
        digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12].upper()
        return f"EXT-{digest}"

    def _adapter_manifest_path(self, folder: Path) -> Path | None:
        for relative in ADAPTER_MANIFEST_NAMES:
            candidate = folder / relative
            if candidate.is_file():
                return candidate
        return None

    def _adapter_markers(self, folder: Path) -> list[dict[str, str]]:
        candidates = (
            ("pyproject.toml", "Python"), ("requirements.txt", "Python"), ("setup.py", "Python"),
            ("package.json", "Node.js"), ("Cargo.toml", "Rust"), ("Project.toml", "Julia"),
            ("environment.yml", "Conda"), ("environment.yaml", "Conda"), ("Dockerfile", "Container"),
            ("compose.yml", "Container"), ("docker-compose.yml", "Container"),
        )
        found: list[dict[str, str]] = []
        for relative, runtime in candidates:
            if (folder / relative).is_file():
                found.append({"file": relative, "runtime": runtime})
        for directory in ("Results", "results", "Data", "data", "outputs", "output"):
            if (folder / directory).is_dir():
                found.append({"file": directory + "/", "runtime": "Data"})
        return found[:16]

    def _sanitize_adapter_manifest(self, payload: Any, manifest_path: Path, folder: Path) -> tuple[str, str | None, dict[str, Any]]:
        if not isinstance(payload, dict):
            return "INVALID", "Manifest JSON must be an object.", {}
        if payload.get("schema") != ADAPTER_MANIFEST_SCHEMA:
            return "INVALID", f"Expected schema {ADAPTER_MANIFEST_SCHEMA}.", {}
        manifest_id = str(payload.get("id") or "").strip()
        manifest_name = str(payload.get("name") or "").strip()
        if not manifest_id or not manifest_name:
            return "INVALID", "Manifest id and name are required.", {}
        capabilities_raw = payload.get("capabilities", [])
        if not isinstance(capabilities_raw, list) or any(not isinstance(value, str) for value in capabilities_raw):
            return "INVALID", "capabilities must be an array of strings.", {}
        entrypoints_raw = payload.get("entrypoints", {})
        if not isinstance(entrypoints_raw, dict):
            return "INVALID", "entrypoints must be an object.", {}
        if any(not isinstance(command, list) or any(not isinstance(value, str) for value in command) for command in entrypoints_raw.values()):
            return "INVALID", "each entrypoint must be an array of strings.", {}
        data_roots_raw = payload.get("data_roots", [])
        if not isinstance(data_roots_raw, list) or any(not isinstance(value, str) for value in data_roots_raw):
            return "INVALID", "data_roots must be an array of relative paths.", {}
        data_roots: list[dict[str, Any]] = []
        for value in data_roots_raw[:32]:
            rel = str(value).strip()
            if not rel:
                continue
            candidate = (folder / rel).resolve()
            try:
                candidate.relative_to(folder)
            except ValueError:
                return "INVALID", f"data_root escapes adapter folder: {rel}", {}
            data_roots.append({"path": rel, "exists": candidate.exists()})
        entrypoints = []
        for key, command in entrypoints_raw.items():
            if not isinstance(key, str) or not key.strip():
                continue
            entrypoints.append({"name": key.strip(), "declared": True})
        sanitized = {
            "schema": ADAPTER_MANIFEST_SCHEMA,
            "id": manifest_id,
            "name": manifest_name,
            "version": str(payload.get("version") or "").strip(),
            "description": str(payload.get("description") or "").strip(),
            "engine_type": str(payload.get("engine_type") or "external").strip() or "external",
            "capabilities": sorted({value.strip() for value in capabilities_raw if value.strip()}),
            "entrypoints": entrypoints,
            "data_roots": data_roots,
            "path": manifest_path.relative_to(folder).as_posix(),
        }
        try:
            sanitized["fingerprint"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:16]
        except OSError:
            sanitized["fingerprint"] = None
        return "VALID", None, sanitized

    def _inspect_adapter(self, record: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(record.get("path") or "").strip()
        enabled = bool(record.get("enabled", True))
        base = {
            "id": str(record.get("id") or ""),
            "name": str(record.get("name") or "").strip(),
            "path": raw_path,
            "enabled": enabled,
            "added_at": record.get("added_at"),
            "last_scanned_at": record.get("last_scanned_at"),
        }
        try:
            folder = self._external_adapter_path(raw_path, must_exist=True)
        except ValueError as exc:
            base.update({
                "status": "OFFLINE" if enabled else "DISABLED",
                "status_reason": str(exc),
                "manifest_status": "UNAVAILABLE",
                "manifest": None,
                "markers": [],
            })
            return base
        base["path"] = str(folder)
        base["markers"] = self._adapter_markers(folder)
        manifest_path = self._adapter_manifest_path(folder)
        if manifest_path is None:
            base.update({
                "status": "NEEDS_CONTRACT" if enabled else "DISABLED",
                "status_reason": "Folder is connected, but no ARCHON adapter manifest was found.",
                "manifest_status": "MISSING",
                "manifest": None,
            })
            if not base["name"]:
                base["name"] = folder.name
            return base
        try:
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_status, error, manifest = self._sanitize_adapter_manifest(raw_manifest, manifest_path, folder)
        except Exception as exc:
            manifest_status, error, manifest = "INVALID", f"Cannot parse manifest: {exc}", {}
        if not base["name"]:
            base["name"] = str(manifest.get("name") or folder.name)
        if not enabled:
            status = "DISABLED"
            reason = "Adapter is registered but disabled in Studio."
        elif manifest_status == "VALID":
            status = "READY"
            reason = "Adapter contract is valid. Execution remains disabled until an explicit execution bridge is configured."
        else:
            status = "INVALID_CONTRACT"
            reason = error or "Adapter manifest is invalid."
        base.update({
            "status": status,
            "status_reason": reason,
            "manifest_status": manifest_status,
            "manifest": manifest or None,
        })
        return base

    def adapters_payload(self) -> dict[str, Any]:
        registry = self._load_adapter_registry()
        rows = [self._inspect_adapter(record) for record in registry.get("adapters", [])]
        counts = {"total": len(rows), "ready": 0, "needs_contract": 0, "offline": 0, "disabled": 0, "invalid": 0}
        for row in rows:
            status = row.get("status")
            if status == "READY": counts["ready"] += 1
            elif status == "NEEDS_CONTRACT": counts["needs_contract"] += 1
            elif status == "OFFLINE": counts["offline"] += 1
            elif status == "DISABLED": counts["disabled"] += 1
            elif status == "INVALID_CONTRACT": counts["invalid"] += 1
        return {
            "schema": "archon_studio_adapters_v1",
            "generated_at": utc_now(),
            "registry_path": self.adapter_registry_path.relative_to(self.root).as_posix(),
            "registry_error": registry.get("registry_error"),
            "execution_policy": "metadata_only",
            "manifest_filename": ADAPTER_MANIFEST_NAMES[0],
            "manifest_schema": ADAPTER_MANIFEST_SCHEMA,
            "manifest_template": self._adapter_manifest_template(),
            "counts": counts,
            "adapters": rows,
        }

    def add_adapter(self, config: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            folder = self._external_adapter_path(config.get("path"), must_exist=True)
        except ValueError as exc:
            return 400, {"error": "invalid_adapter_path", "detail": str(exc)}
        name = str(config.get("name") or "").strip()[:120]
        with self.adapter_lock:
            registry = self._load_adapter_registry()
            if registry.get("registry_error"):
                return 409, {"error": "adapter_registry_invalid", "detail": registry["registry_error"]}
            rows = list(registry.get("adapters", []))
            for row in rows:
                try:
                    existing = self._external_adapter_path(row.get("path"), must_exist=False)
                except ValueError:
                    continue
                if existing == folder:
                    if name:
                        row["name"] = name
                    row["enabled"] = True
                    row["last_scanned_at"] = utc_now()
                    self._save_adapter_registry(rows)
                    return 200, {"ok": True, "added": False, "adapter": self._inspect_adapter(row), "registry": self.adapters_payload()}
            now = utc_now()
            row = {"id": self._adapter_id(folder), "path": str(folder), "name": name, "enabled": True, "added_at": now, "last_scanned_at": now}
            rows.append(row)
            self._save_adapter_registry(rows)
        return 201, {"ok": True, "added": True, "adapter": self._inspect_adapter(row), "registry": self.adapters_payload()}

    def adapter_action(self, adapter_id: str, action: str, config: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        config = dict(config or {})
        with self.adapter_lock:
            registry = self._load_adapter_registry()
            if registry.get("registry_error"):
                return 409, {"error": "adapter_registry_invalid", "detail": registry["registry_error"]}
            rows = list(registry.get("adapters", []))
            target = next((row for row in rows if str(row.get("id")) == adapter_id), None)
            if target is None:
                return 404, {"error": "adapter_not_found"}
            if action == "remove":
                rows = [row for row in rows if str(row.get("id")) != adapter_id]
                self._save_adapter_registry(rows)
                return 200, {"ok": True, "removed": adapter_id, "registry": self.adapters_payload()}
            if action == "toggle":
                if "enabled" not in config or not isinstance(config.get("enabled"), bool):
                    return 400, {"error": "invalid_request", "detail": "enabled must be a boolean"}
                target["enabled"] = bool(config["enabled"])
            elif action == "rescan":
                pass
            else:
                return 404, {"error": "unknown_adapter_action"}
            target["last_scanned_at"] = utc_now()
            self._save_adapter_registry(rows)
        return 200, {"ok": True, "adapter": self._inspect_adapter(target), "registry": self.adapters_payload()}

    def _project_path(self, value: Any, *, must_exist: bool = False) -> Path:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("project path cannot be empty")
        expanded = Path(raw).expanduser()
        path = expanded.resolve() if expanded.is_absolute() else (self.root / expanded).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path must stay inside the ARCHON project") from exc
        if must_exist and not path.exists():
            raise ValueError(f"path not found: {path.relative_to(self.root).as_posix()}")
        return path

    def _build_search_command(self, config: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        run_command = str(config.get("run_command") or "evolve").strip().lower()
        if run_command not in {"evolve", "resume"}:
            raise ValueError("Search run_command must be evolve or resume")
        score_mode = str(config.get("score_mode") or "observer_niches").strip()
        if score_mode not in self.search_score_modes:
            raise ValueError("unknown Search score mode")
        search_mode = str(config.get("search_mode") or "ordinary").strip().lower()
        if search_mode not in SEARCH_MODES:
            raise ValueError("unknown Search orchestration mode")
        seeds_raw = config.get("seed_rules") or []
        if isinstance(seeds_raw, str):
            seeds_raw = re.split(r"[\s,]+", seeds_raw.strip()) if seeds_raw.strip() else []
        if not isinstance(seeds_raw, list):
            raise ValueError("seed_rules must be a list or comma-separated string")
        seeds: list[str] = []
        for value in seeds_raw[:64]:
            rid = _normalize_rule_id(value)
            if rid and rid.isdigit() and rid not in seeds:
                seeds.append(rid)
        if search_mode == "local_around_rule" and not seeds:
            raise ValueError("local_around_rule requires at least one seed rule")

        experiment_plan = str(config.get("experiment_plan") or self.default_experiment_plan.relative_to(self.root).as_posix()).strip()
        job_id = str(config.get("search_job") or "").strip()
        target = str(config.get("target_regime") or "").strip()
        plan: Path | None = None
        if search_mode in {"cohort_target", "counterexample"}:
            plan = self._project_path(experiment_plan, must_exist=True)
            if not job_id and not target:
                raise ValueError("cohort_target/counterexample requires a Search job or target regime")
        command = canonical_search_command(
            self.root,
            self.python_command,
            run_command,
            score_mode,
            search_mode,
            experiment_plan=plan,
            search_job=job_id,
            target_regime=target,
            seed_rules=(seeds if search_mode in {"diversity", "cohort_target", "counterexample", "local_around_rule"} else ()),
        )
        clean = {
            "ui_mode": "embedded",
            "run_command": run_command,
            "score_mode": score_mode,
            "search_mode": search_mode,
            "experiment_plan": experiment_plan,
            "search_job": job_id,
            "target_regime": target,
            "seed_rules": seeds,
        }
        return command, clean

    def _normalize_observer_config(self, config: dict[str, Any], *, ui_mode: str = "embedded") -> dict[str, Any]:
        selector = str(config.get("rule_id") or "").strip()
        if not selector:
            raise ValueError("Observer requires a rule ID")
        if selector.lower() != "best":
            selector = _normalize_rule_id(selector)
            if not selector.isdigit():
                raise ValueError("Observer rule ID must be numeric or 'best'")
        max_ticks = int(config.get("max_ticks") or 100000)
        if not 1 <= max_ticks <= 10_000_000:
            raise ValueError("max_ticks must be between 1 and 10,000,000")
        speed = int(config.get("speed") or 100)
        if speed not in OBSERVER_SPEED_VALUES:
            raise ValueError("unsupported Observer steps-per-frame value")
        sample_every = int(config.get("sample_every") or 1)
        if not 1 <= sample_every <= 10000:
            raise ValueError("sample_every must be between 1 and 10,000")
        autosave_every = int(config.get("autosave_every") or min(50000, max_ticks))
        if autosave_every < 0 or autosave_every > max_ticks:
            raise ValueError("autosave_every must be between 0 and max_ticks")
        field_width = int(config.get("field_width") or 96)
        field_height = int(config.get("field_height") or 64)
        if not 16 <= field_width <= 512 or not 16 <= field_height <= 512:
            raise ValueError("Observer field dimensions must be between 16 and 512")
        return {
            "ui_mode": ui_mode,
            "rule_id": selector,
            "max_ticks": max_ticks,
            "speed": speed,
            "sample_every": sample_every,
            "autosave_every": autosave_every,
            "field_width": field_width,
            "field_height": field_height,
        }

    def _new_observer_preview_dir(self, rule_id: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        nonce = f"{time.time_ns() % 1_000_000_000:09d}"
        path = self.root / "Results" / "Studio" / "runtime" / "observer_previews" / f"{stamp}_rule_{rule_id}_{nonce}"
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _build_observer_command(self, config: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        clean = self._normalize_observer_config(config, ui_mode="embedded")
        selector = str(clean["rule_id"])
        preview_dir = self._new_observer_preview_dir(selector)
        telemetry_database = preview_dir / "telemetry.sqlite"

        # The canonical Results directory remains the read-only source catalog for
        # selecting the Rule.  Every output from Studio preview mode is redirected
        # into a Studio-owned sandbox until the user explicitly chooses Save & Stop.
        self.search_results.mkdir(parents=True, exist_ok=True)
        command = [
            *self.python_command, "-u", str(self.observer_studio_adapter), str(self.search_results), selector,
            "--headless", "--studio-stream", "--max-ticks", str(clean["max_ticks"]),
            "--speed", str(clean["speed"]), "--delay", "30",
            "--sample-every", str(clean["sample_every"]), "--autosave-every", str(clean["autosave_every"]),
            "--pressure-timeline-every", "100",
            "--samples-csv", "--events-csv", "--pressure-timeline-csv", "--chronicle-csv",
            "--passport", "--log", "--telemetry-sqlite", "--telemetry-db", str(telemetry_database),
            "--evidence-framework", "--field-width", str(clean["field_width"]), "--field-height", str(clean["field_height"]),
            "--run-output-dir", str(preview_dir),
        ]
        clean.update({
            "preview_mode": True,
            "preview_session_dir": preview_dir.relative_to(self.root).as_posix(),
            "preview_saved_path": None,
            "preview_stop_mode": None,
            "preview_finalized": False,
        })
        return command, clean

    def _build_observer_native_context_command(self, config: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        """Open the active OL2 Observer Launcher with Studio preview context prefilled."""
        clean = self._normalize_observer_config(config, ui_mode="native")
        command = [
            *self.python_command, "-u", str(self.observer_launcher_adapter),
            "--rule-id", str(clean["rule_id"]),
            "--max-ticks", str(clean["max_ticks"]),
            "--speed", str(clean["speed"]),
            "--sample-every", str(clean["sample_every"]),
            "--autosave-every", str(clean["autosave_every"]),
            "--field-width", str(clean["field_width"]),
            "--field-height", str(clean["field_height"]),
        ]
        clean.update({
            "native_target": "ol2_launcher_context",
            "native_context_handoff": True,
            "handoff_semantics": "ol2-config-prefill-fresh-native-review",
        })
        return command, clean

    def _observer_preview_path(self, runtime: EngineRuntime) -> Path | None:
        raw = str(runtime.config.get("preview_session_dir") or "").strip()
        if not raw:
            return None
        candidate = (self.root / raw).resolve()
        preview_root = (self.root / "Results" / "Studio" / "runtime" / "observer_previews").resolve()
        try:
            candidate.relative_to(preview_root)
        except ValueError:
            return None
        return candidate

    def _finalize_observer_preview(self, runtime: EngineRuntime, mode: str) -> None:
        if runtime.spec.key != "observer" or runtime.launch_mode != "embedded":
            return
        if runtime.config.get("preview_finalized"):
            return
        path = self._observer_preview_path(runtime)
        if path is None:
            runtime.config["preview_finalized"] = True
            return
        if mode == "save":
            destination_root = self.root / "Results" / "Studio" / "saved_previews"
            destination_root.mkdir(parents=True, exist_ok=True)
            destination = destination_root / path.name
            if destination.exists():
                shutil.rmtree(destination)
            if path.exists():
                shutil.move(str(path), str(destination))
            runtime.config["preview_saved_path"] = destination.relative_to(self.root).as_posix()
            runtime.append_event(
                f"Observer preview saved to {runtime.config['preview_saved_path']}. It remains preview material, not canonical evidence.",
                "success",
            )
        elif mode == "discard":
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
            runtime.append_event("Observer preview artifacts discarded.", "warning")
        runtime.config["preview_stop_mode"] = mode
        runtime.config["preview_finalized"] = True

    def _resolve_launch(self, key: str, config: dict[str, Any]) -> tuple[list[str], str, dict[str, Any]]:
        ui_mode = str(config.get("ui_mode") or "native").strip().lower()
        if key == "analyzer":
            ui_mode = "native"
        if ui_mode not in {"native", "embedded"}:
            raise ValueError("ui_mode must be native or embedded")
        if ui_mode == "native":
            if key == "observer" and bool(config.get("native_context_handoff")):
                command, clean = self._build_observer_native_context_command(config)
                return command, "native", clean
            return list(self.specs[key].command), "native", {"ui_mode": "native", "native_target": "launcher"}
        if key == "search":
            command, clean = self._build_search_command(config)
            return command, "embedded", clean
        if key == "observer":
            command, clean = self._build_observer_command(config)
            return command, "embedded", clean
        raise ValueError("embedded mode is not available for this engine")

    def _initial_live(self, key: str, mode: str, config: dict[str, Any]) -> dict[str, Any]:
        if key == "search" and mode == "embedded":
            return {
                "generation": 0, "generations": self.search_generations, "evaluated": 0,
                "population": self.search_population, "failed": 0, "workers": 0,
                "elapsed_seconds": 0.0, "eta_seconds": None, "overall_fraction": 0.0,
                "exact_matches": 0, "target_rule": None, "target_distance": None,
                "target_coverage": None, "overall_rule": None, "overall_score": None,
                "best_ever_rule": None, "best_ever_score": None, "complete": False,
                "completed_generation_seconds": 0.0, "current_generation_elapsed_seconds": 0,
                "runtime_backend": "canonical_universe_search_process",
                "telemetry_source": "process_stdout",
                "source_pid": None,
                "process_attested": False,
                "completion_attested": False,
                "runtime_id": None,
                "committed_generations": [],
                "artifact_verified": False,
                "artifact_path": None,
            }
        if key == "observer" and mode == "embedded":
            return {
                "tick": 0, "max_ticks": int(config.get("max_ticks") or 0), "progress_fraction": 0.0,
                "width": int(config.get("field_width") or 96), "height": int(config.get("field_height") or 64),
                "grid_b64": None, "metrics": {}, "run_id": None, "final": False, "frame_seq": 0,
            }
        return {}

    def start_engine(self, key: str, config: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        runtime = self.engines.get(key)
        if runtime is None:
            return 404, {"error": "unknown_engine"}
        config = dict(config or {})
        replace_running = bool(config.pop("replace_running", False))
        requested_mode = str(config.get("ui_mode") or "native").strip().lower()
        requested_context_handoff = bool(config.get("native_context_handoff", False))
        with runtime.lock:
            if runtime.process is not None and runtime.process.poll() is None:
                can_replace = (
                    replace_running
                    and key == "observer"
                    and runtime.launch_mode == "embedded"
                    and requested_mode == "native"
                )
                if not can_replace:
                    return 409, {"error": "engine_already_running", "engine": self._engine_payload(runtime)}
                old_process = runtime.process
                old_config = dict(runtime.config)
                runtime.stop_requested = True
                if runtime.launch_mode == "embedded":
                    runtime.config["preview_stop_mode"] = "discard"
                if requested_context_handoff:
                    # Trust the configuration of the process that is actually
                    # running, not potentially stale browser form values.
                    for name, value in old_config.items():
                        if name != "ui_mode":
                            config[name] = value
                    config["ui_mode"] = "native"
                    config["native_context_handoff"] = True
                if runtime.status == "PAUSED" and os.name == "posix":
                    try:
                        os.killpg(old_process.pid, signal.SIGCONT)
                    except OSError:
                        pass
                try:
                    if os.name == "posix":
                        os.killpg(old_process.pid, signal.SIGTERM)
                    else:
                        old_process.terminate()
                    runtime.append_event(
                        "Stopping Embedded Observer cleanly before native context handoff…"
                        if requested_context_handoff
                        else "Switching Embedded Observer to the native laboratory…",
                        "warning",
                    )
                except OSError as exc:
                    return 500, {"error": "observer_native_switch_failed", "detail": str(exc)}
                deadline = time.monotonic() + 6.0
                while old_process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                if old_process.poll() is None:
                    try:
                        if os.name == "posix":
                            os.killpg(old_process.pid, signal.SIGKILL)
                        else:
                            old_process.kill()
                        old_process.wait(timeout=1.0)
                    except Exception as exc:
                        return 500, {"error": "observer_native_switch_timeout", "detail": str(exc)}
                self._finalize_observer_preview(runtime, "discard")
                self.request_snapshot_refresh(reason="observer-native-switch", immediate=True)
            if key == "search":
                try:
                    validate_search_runtime(self.root)
                except RuntimeError as exc:
                    runtime.status = "FAILED"
                    runtime.append_event(str(exc), "error")
                    return 500, {"error": "canonical_search_runtime_incomplete", "detail": str(exc)}
            try:
                command, launch_mode, clean_config = self._resolve_launch(key, config)
            except (ValueError, OSError) as exc:
                return 400, {"error": "invalid_engine_configuration", "detail": str(exc)}
            for component in command[1:2]:
                path = Path(component)
                if path.is_absolute() and path.suffix in {".sh", ".py"} and not path.is_file():
                    return 500, {"error": "engine_entrypoint_missing", "path": path.name}
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            if key == "observer" and launch_mode == "embedded":
                env.setdefault("ART_EVO_FIELD_BACKEND", "numpy")
            env["PYTHONPATH"] = os.pathsep.join(value for value in (str(self.root), env.get("PYTHONPATH", "")) if value)
            try:
                process = subprocess.Popen(
                    command, cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                    start_new_session=True,
                )
            except Exception as exc:
                runtime.status = "FAILED"
                runtime.exit_code = None
                runtime.finished_at = utc_now()
                runtime.append_event(f"Launch failed: {exc}", "error")
                return 500, {"error": "engine_launch_failed", "detail": str(exc)}
            runtime.process = process
            runtime.status = "RUNNING"
            runtime.pid = process.pid
            runtime.started_at = utc_now()
            runtime.started_ns = time.time_ns()
            runtime.finished_at = None
            runtime.exit_code = None
            runtime.stop_requested = False
            runtime.launch_mode = launch_mode
            runtime.config = clean_config
            runtime.live = self._initial_live(key, launch_mode, clean_config)
            if key == "search" and launch_mode == "embedded":
                runtime.live["source_pid"] = process.pid
            runtime.events.clear()
            runtime.event_seq = 0
            if key == "observer" and clean_config.get("native_context_handoff"):
                runtime.append_event(
                    f"Native context handoff opened Observer Launcher 2 with Rule {str(clean_config.get('rule_id') or '').zfill(5)} "
                    f"and the embedded run settings prefilled (PID {process.pid}).",
                    "success",
                )
            else:
                runtime.append_event(f"Studio launched {runtime.spec.label} in {launch_mode} mode (PID {process.pid}).", "success")
            threading.Thread(target=self._drain_output, args=(runtime, process), name=f"studio-{key}-output", daemon=True).start()
            threading.Thread(target=self._wait_process, args=(runtime, process), name=f"studio-{key}-wait", daemon=True).start()
        return 200, {"ok": True, "engine": self._engine_payload(runtime)}

    def _update_search_attestation(self, runtime: EngineRuntime, process: subprocess.Popen[str], payload: dict[str, Any]) -> bool:
        if payload.get("schema") != "archon_search_runtime_v1" or int(payload.get("pid") or 0) != process.pid:
            runtime.append_event("Rejected invalid Universe Search runtime attestation.", "error")
            return False
        event = str(payload.get("event") or "")
        live = runtime.live
        if event == "process_started":
            live.update({
                "process_attested": True,
                "source_pid": process.pid,
                "runtime_id": str(payload.get("search_run_id") or ""),
                "generations": int(payload.get("generations") or live.get("generations") or 0),
                "population": int(payload.get("population") or live.get("population") or 0),
            })
            return True
        if not live.get("process_attested") or payload.get("search_run_id") != live.get("runtime_id"):
            runtime.append_event("Rejected out-of-order Universe Search runtime telemetry.", "error")
            return False
        if event == "generation_committed":
            generation = int(payload.get("generation") or 0)
            raw_path = str(payload.get("artifact") or "")
            artifact = (self.root / raw_path).resolve()
            results_root = (self.root / "Results" / "Universe_Search").resolve()
            valid = False
            try:
                artifact.relative_to(results_root)
                rows = json.loads(artifact.read_text(encoding="utf-8"))
                valid = artifact.is_file() and isinstance(rows, list) and len(rows) == int(payload.get("results") or 0)
            except (ValueError, OSError, json.JSONDecodeError, TypeError):
                valid = False
            if not valid:
                runtime.append_event("Universe Search reported an invalid generation artifact.", "error")
                return False
            committed = list(live.get("committed_generations") or [])
            if generation not in committed:
                committed.append(generation)
            live.update({"committed_generations": committed, "artifact_verified": True, "artifact_path": raw_path})
            return True
        if event == "search_complete":
            live.update({"completion_attested": True, "complete": True, "workers": 0})
            return True
        return False

    def _update_search_live(self, runtime: EngineRuntime, process: subprocess.Popen[str], line: str) -> None:
        live = runtime.live
        if line.startswith(_SEARCH_RUNTIME_PREFIX):
            try:
                payload = json.loads(line[len(_SEARCH_RUNTIME_PREFIX):])
            except (json.JSONDecodeError, TypeError) as exc:
                runtime.append_event(f"Universe Search runtime telemetry parse error: {exc}", "error")
                return
            self._update_search_attestation(runtime, process, payload)
            return
        # Human-readable progress is accepted only after the canonical child
        # process has identified itself with a PID-bound structured event.
        if not live.get("process_attested"):
            return
        if match := _GEN_RE.search(line):
            gen, total, _mode = match.groups()
            live.update({"generation": int(gen), "generations": int(total), "evaluated": 0, "failed": 0, "current_generation_elapsed_seconds": 0})
        if match := _WORKERS_RE.search(line):
            workers, jobs = match.groups()
            live.update({"workers": int(workers), "population": int(jobs) or int(live.get("population") or 0)})
        if match := _EVAL_RE.search(line):
            done, total, failed, elapsed = match.groups()
            live.update({"evaluated": int(done), "population": int(total), "failed": int(failed), "current_generation_elapsed_seconds": int(elapsed)})
        elif match := _HEART_RE.search(line):
            done, total, elapsed = match.groups()
            live.update({"evaluated": int(done), "population": int(total), "current_generation_elapsed_seconds": int(elapsed)})
        if match := _TARGET_RE.search(line):
            _gen, exact, rule, distance, coverage = match.groups()
            live.update({"exact_matches": int(exact), "target_rule": _normalize_rule_id(rule), "target_distance": _finite_float(distance), "target_coverage": _finite_float(coverage)})
        if match := _BEST_RE.search(line):
            _gen, rule, score, best_rule, best_score = match.groups()
            live.update({"overall_rule": _normalize_rule_id(rule), "overall_score": _finite_float(score), "best_ever_rule": _normalize_rule_id(best_rule), "best_ever_score": _finite_float(best_score)})
        if match := _GEN_TIME_RE.search(line):
            live["completed_generation_seconds"] = float(live.get("completed_generation_seconds") or 0.0) + float(match.group(1)) * 60.0
            live["current_generation_elapsed_seconds"] = 0
        generations = max(0, int(live.get("generations") or 0))
        population = max(0, int(live.get("population") or 0))
        generation = max(0, int(live.get("generation") or 0))
        evaluated = max(0, int(live.get("evaluated") or 0))
        total_slots = generations * population
        completed_slots = (max(0, generation - 1) * population + evaluated) if generation and population else 0
        if total_slots:
            completed_slots = min(total_slots, completed_slots)
        elapsed = float(live.get("completed_generation_seconds") or 0.0) + float(live.get("current_generation_elapsed_seconds") or 0.0)
        eta = None
        if completed_slots >= 5 and total_slots > completed_slots and elapsed > 0:
            eta = max(0.0, elapsed / completed_slots * (total_slots - completed_slots))
        live["elapsed_seconds"] = elapsed
        live["eta_seconds"] = eta
        live["overall_fraction"] = (completed_slots / total_slots) if total_slots else 0.0

    def _update_observer_live(self, runtime: EngineRuntime, payload: dict[str, Any], *, final: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        live = runtime.live
        if final:
            live.update({
                "tick": int(
                live.get("tick") or 0
                if payload.get("final_tick") in (None, "")
                else payload.get("final_tick")
            ),
                "run_id": payload.get("run_id") or live.get("run_id"),
                "samples": payload.get("samples"), "events_count": payload.get("events"), "final": True,
            })
        else:
            live.update(payload)
            live["frame_seq"] = int(live.get("frame_seq") or 0) + 1
            max_ticks = max(0, int(payload.get("max_ticks") or live.get("max_ticks") or 0))
            tick = max(0, int(payload.get("tick") or 0))
            live["progress_fraction"] = min(1.0, tick / max_ticks) if max_ticks else 0.0

    def observer_live_payload(self) -> dict[str, Any]:
        """Return a lightweight Observer pulse without events or the full Studio state."""
        runtime = self.engines["observer"]
        with runtime.lock:
            return {
                "schema": "archon_studio_observer_live_v1",
                "generated_at": utc_now(),
                "status": runtime.status,
                "pid": runtime.pid,
                "ui_mode": runtime.launch_mode,
                "live": dict(runtime.live),
            }

    def _drain_output(self, runtime: EngineRuntime, process: subprocess.Popen[str]) -> None:
        stream = process.stdout
        if stream is None:
            return
        try:
            for line in stream:
                stripped = line.rstrip("\n")
                with runtime.lock:
                    if runtime.spec.key == "search" and runtime.launch_mode == "embedded":
                        self._update_search_live(runtime, process, stripped)
                    if runtime.spec.key == "observer" and runtime.launch_mode == "embedded":
                        if stripped.startswith(_STUDIO_OBSERVER_PREFIX):
                            try:
                                self._update_observer_live(runtime, json.loads(stripped[len(_STUDIO_OBSERVER_PREFIX):]))
                            except Exception as exc:
                                runtime.append_event(f"Observer presentation stream parse error: {exc}", "warning")
                            continue
                        if stripped.startswith(_HEADLESS_OBSERVER_PREFIX):
                            try:
                                final_payload = json.loads(stripped[len(_HEADLESS_OBSERVER_PREFIX):])
                                self._update_observer_live(runtime, final_payload, final=True)
                                runtime.append_event(f"Observer finalized rule {final_payload.get('rule_id')} at tick {final_payload.get('final_tick')}.", "success")
                            except Exception as exc:
                                runtime.append_event(f"Observer final-state parse error: {exc}", "warning")
                            continue
                runtime.append_event(stripped)
        except Exception as exc:
            runtime.append_event(f"Output bridge error: {exc}", "warning")

    def _wait_process(self, runtime: EngineRuntime, process: subprocess.Popen[str]) -> None:
        code = process.wait()
        with runtime.lock:
            if runtime.process is not process:
                return
            if runtime.spec.key == "observer" and runtime.launch_mode == "embedded":
                stop_mode = str(runtime.config.get("preview_stop_mode") or "").strip().lower()
                if stop_mode in {"save", "discard"}:
                    self._finalize_observer_preview(runtime, stop_mode)
                elif code == 0:
                    runtime.append_event(
                        "Observer preview completed. Its sandbox remains temporary until explicitly saved or discarded.",
                        "success",
                    )
            runtime.exit_code = code
            runtime.finished_at = utc_now()
            runtime.pid = None
            runtime.process = None
            if runtime.stop_requested:
                runtime.status = "IDLE"
                runtime.append_event("Process stopped by Studio.", "warning")
            elif (
                code == 0
                and runtime.spec.key == "search"
                and runtime.launch_mode == "embedded"
                and not (runtime.live.get("process_attested") and runtime.live.get("completion_attested"))
            ):
                runtime.status = "FAILED"
                runtime.append_event(
                    "Canonical Universe Search process exited without complete PID-bound runtime telemetry. "
                    "Studio will not treat simulated or unattested activity as a successful Search.",
                    "error",
                )
            elif code == 0:
                runtime.status = "COMPLETE"
                runtime.append_event("Process exited successfully.", "success")
            else:
                runtime.status = "FAILED"
                runtime.append_event(f"Process exited with code {code}.", "error")
        self.request_snapshot_refresh(reason=f"{runtime.spec.key}-exit", immediate=True)
        if runtime.spec.key in {"search", "analyzer"}:
            self._schedule_preview_asset_settle(runtime.spec.key)

    def _preview_asset_signature(self) -> str:
        """Fingerprint Atlas preview files without importing scientific modules.

        This is intentionally used only by the short post-engine settle window,
        not by the one-second canonical source watcher, so large Atlases do not
        pay thousands of stat calls forever while Studio is idle.
        """
        index_path = self.root / "Atlas" / "Worlds" / "atlas_index.json"
        try:
            worlds = json.loads(index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return "no-atlas"
        if not isinstance(worlds, list):
            return "invalid-atlas"
        digest = hashlib.blake2b(digest_size=16)
        markers = ("Atlas/", "Results/")
        for world in worlds:
            if not isinstance(world, dict):
                continue
            for key in ("preview_gif", "preview"):
                raw = world.get(key)
                if not isinstance(raw, str) or not raw.strip():
                    continue
                text = raw.replace("\\", "/")
                relative = None
                for marker in markers:
                    pos = text.find(marker)
                    if pos >= 0:
                        relative = text[pos:]
                        break
                if not relative:
                    continue
                path = self.root / relative
                mtime_ns, size = _safe_stat(path)
                digest.update(relative.encode("utf-8", "replace"))
                digest.update(f":{mtime_ns}:{size};".encode("ascii"))
        return digest.hexdigest()

    def _schedule_preview_asset_settle(self, engine_key: str) -> None:
        """Catch previews that land just after canonical JSON is committed.

        Analyzer/Search can finish their canonical JSON path milliseconds before
        the retained GIF/PNG becomes visible on disk.  Two bounded follow-up
        checks avoid permanent image-less cards without turning Studio into a
        recursive filesystem monitor.
        """
        baseline = self._preview_asset_signature()

        def worker() -> None:
            nonlocal baseline
            for index, delay in enumerate((1.25, 3.75), start=1):
                if self.shutdown_event.wait(delay):
                    return
                current = self._preview_asset_signature()
                if current == baseline:
                    continue
                baseline = current
                # Wait for any immediate engine-exit build to finish, then make
                # the asset pass explicit so the new generation gets published.
                deadline = time.monotonic() + 8.0
                while time.monotonic() < deadline:
                    with self.snapshot_lock:
                        building = self.snapshot_building
                    if not building:
                        break
                    if self.shutdown_event.wait(0.15):
                        return
                self.request_snapshot_refresh(reason=f"{engine_key}-preview-settle-{index}", immediate=True)

        threading.Thread(target=worker, name=f"studio-{engine_key}-preview-settle", daemon=True).start()

    def pause_engine(self, key: str) -> tuple[int, dict[str, Any]]:
        runtime = self.engines.get(key)
        if runtime is None:
            return 404, {"error": "unknown_engine"}
        if os.name != "posix":
            return 409, {"error": "pause_not_supported"}
        with runtime.lock:
            process = runtime.process
            if process is None or process.poll() is not None:
                return 409, {"error": "engine_not_running"}
            if runtime.status == "PAUSED":
                return 200, {"ok": True, "engine": self._engine_payload(runtime)}
            try:
                os.killpg(process.pid, signal.SIGSTOP)
            except OSError as exc:
                return 500, {"error": "pause_failed", "detail": str(exc)}
            runtime.status = "PAUSED"
            runtime.append_event("Studio suspended the engine process group.", "warning")
        return 200, {"ok": True, "engine": self._engine_payload(runtime)}

    def resume_engine(self, key: str) -> tuple[int, dict[str, Any]]:
        runtime = self.engines.get(key)
        if runtime is None:
            return 404, {"error": "unknown_engine"}
        if os.name != "posix":
            return 409, {"error": "resume_not_supported"}
        with runtime.lock:
            process = runtime.process
            if process is None or process.poll() is not None:
                return 409, {"error": "engine_not_running"}
            try:
                os.killpg(process.pid, signal.SIGCONT)
            except OSError as exc:
                return 500, {"error": "resume_failed", "detail": str(exc)}
            runtime.status = "RUNNING"
            runtime.append_event("Studio resumed the engine process group.", "success")
        return 200, {"ok": True, "engine": self._engine_payload(runtime)}

    def stop_engine(self, key: str, config: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        runtime = self.engines.get(key)
        if runtime is None:
            return 404, {"error": "unknown_engine"}
        config = dict(config or {})
        with runtime.lock:
            if key == "observer" and runtime.launch_mode == "embedded":
                mode = str(config.get("preview_action") or "").strip().lower()
                if mode not in {"save", "discard"}:
                    return 400, {
                        "error": "observer_preview_stop_choice_required",
                        "detail": "Choose save or discard for the running Studio Observer preview.",
                    }
                runtime.config["preview_stop_mode"] = mode
                runtime.append_event(
                    "Save & Stop requested for Observer preview." if mode == "save" else "Stop without saving requested for Observer preview.",
                    "warning",
                )
        if not self._terminate_runtime(runtime, user_requested=True, force_after=5.0):
            return 409, {"error": "engine_not_running"}
        return 200, {"ok": True, "engine": self._engine_payload(runtime)}

    def _terminate_runtime(self, runtime: EngineRuntime, *, user_requested: bool, force_after: float) -> bool:
        with runtime.lock:
            process = runtime.process
            if process is None or process.poll() is not None:
                return False
            runtime.stop_requested = user_requested
            if runtime.status == "PAUSED" and os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGCONT)
                except OSError:
                    pass
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                runtime.append_event("Stop requested. Waiting for graceful shutdown…" if os.name == "posix" else "Windows forced stop requested; a graceful checkpoint and descendant cleanup are not guaranteed.", "warning")
            except OSError:
                return False
            threading.Thread(target=self._force_kill_after, args=(runtime, process, force_after), daemon=True).start()
            return True

    def _force_kill_after(self, runtime: EngineRuntime, process: subprocess.Popen[str], delay: float) -> None:
        deadline = time.monotonic() + delay
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.1)
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            runtime.append_event("Graceful stop timed out; Studio forced termination of the owned process; descendant cleanup depends on the platform.", "error")
        except OSError:
            pass

    def request_snapshot_refresh(self, *, reason: str, immediate: bool = False) -> None:
        with self.snapshot_lock:
            self.snapshot_dirty_at = time.monotonic() - (10.0 if immediate else 0.0)
        if immediate:
            self._start_snapshot_build(reason)

    def inspect_world_import(self, package: bytes) -> tuple[int, dict[str, Any]]:
        result = self.world_portability.inspect_import(package, include_preview_data=True)
        status = result.get("status")
        return (200 if status in {"VALID_NEW", "ALREADY_EXISTS"} else 422), result

    def import_world(self, package: bytes) -> tuple[int, dict[str, Any]]:
        result = self.world_portability.import_world(package)
        status = result.get("status")
        if status == "IMPORTED":
            self.request_snapshot_refresh(reason="world-import", immediate=True)
            return 201, result
        if status == "ALREADY_EXISTS":
            return 200, result
        return 422, result

    def export_world(self, rule_id: str) -> tuple[dict[str, Any], bytes]:
        from io import BytesIO
        output = BytesIO()
        result = self.world_portability.export_world(rule_id, output)
        return result, output.getvalue()

    def export_all_worlds(self, destination: Path) -> dict[str, Any]:
        return self.world_portability.export_all_worlds(destination)

    def inspect_world_collection(self, package: Path) -> tuple[int, dict[str, Any]]:
        result = self.world_portability.inspect_world_collection(package)
        return (200 if result.get("status") in {"VALID_COLLECTION", "ALREADY_EXISTS"} else 422), result

    def import_world_collection(self, package: Path) -> tuple[int, dict[str, Any]]:
        result = self.world_portability.import_world_collection(package)
        status = result.get("status")
        if status == "IMPORTED_COLLECTION":
            self.request_snapshot_refresh(reason="world-collection-import", immediate=True)
            return 201, result
        if status == "ALREADY_EXISTS":
            return 200, result
        return 422, result

    def _start_snapshot_build(self, reason: str) -> bool:
        with self.snapshot_lock:
            if self.snapshot_building:
                return False
            self.snapshot_building = True
            self.snapshot_last_error = None
            self.snapshot_last_build_started = utc_now()
        threading.Thread(target=self._run_snapshot_build, args=(reason,), name="studio-snapshot-build", daemon=True).start()
        return True

    def _run_snapshot_build(self, reason: str) -> None:
        signature_before = self.source_signature()
        temp_output = self.snapshot_path.with_name(self.snapshot_path.name + ".tmp")
        try:
            try:
                temp_output.unlink()
            except FileNotFoundError:
                pass
            completed = subprocess.run(
                [*self.python_command, str(self.snapshot_builder), "--output", str(temp_output)], cwd=self.root,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                timeout=180, check=False,
            )
            if completed.returncode != 0:
                tail = "\n".join((completed.stdout or "").splitlines()[-20:])
                raise RuntimeError(f"snapshot builder exited {completed.returncode}: {tail}")
            if not temp_output.is_file():
                raise RuntimeError("snapshot builder did not create the temporary output")
            temp_output.replace(self.snapshot_path)
            signature_after = self.source_signature()
            meta_tmp = self.snapshot_meta_path.with_suffix(".json.tmp")
            meta_tmp.write_text(json.dumps({
                "schema": "archon_studio_snapshot_sync_v1",
                "built_at": utc_now(),
                "source_signature": signature_after,
                "snapshot_revision": self.snapshot_revision(),
                "reason": reason,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            meta_tmp.replace(self.snapshot_meta_path)
            with self.snapshot_lock:
                self.snapshot_build_seq += 1
                self.snapshot_last_reason = reason
                self.snapshot_last_success_revision = self.snapshot_revision()
                self.snapshot_last_source_signature = signature_after
                self.snapshot_last_error = None
                # If canonical sources moved while the builder was reading them,
                # keep the snapshot dirty so the watcher performs one more pass.
                self.snapshot_dirty_at = time.monotonic() if signature_after != signature_before else None
        except Exception as exc:
            with self.snapshot_lock:
                self.snapshot_last_error = f"{reason}: {exc}"
                self.snapshot_dirty_at = time.monotonic()
        finally:
            try:
                temp_output.unlink()
            except FileNotFoundError:
                pass
            with self.snapshot_lock:
                self.snapshot_building = False
                self.snapshot_last_build_finished = utc_now()

    def _watch_sources(self) -> None:
        last_seen = self.snapshot_last_source_signature
        last_build_attempt = 0.0
        while not self.shutdown_event.wait(1.0):
            current = self.source_signature()
            now = time.monotonic()
            if current != last_seen:
                last_seen = current
                with self.snapshot_lock:
                    self.snapshot_last_source_signature = current
                    self.snapshot_dirty_at = now
            with self.snapshot_lock:
                dirty_at = self.snapshot_dirty_at
                building = self.snapshot_building
            if dirty_at is not None and not building and now - dirty_at >= 2.0 and now - last_build_attempt >= 8.0:
                if self._start_snapshot_build("source-change"):
                    last_build_attempt = now


class StudioRequestHandler(BaseHTTPRequestHandler):
    server_version = "ARCHONStudioRuntime/1.6"
    protocol_version = "HTTP/1.1"

    @property
    def bridge(self) -> StudioRuntimeBridge:
        return self.server.bridge  # type: ignore[attr-defined]

    @property
    def static_root(self) -> Path | None:
        return self.server.static_root  # type: ignore[attr-defined]

    @property
    def live_public_root(self) -> Path:
        return self.server.live_public_root  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin and self._trusted_request():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def _json(self, status: int, payload: Any) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _binary(self, status: int, data: bytes, *, content_type: str, filename: str | None = None) -> None:
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def _stream_file(self, path: Path, *, content_type: str, filename: str) -> None:
        try:
            size = path.stat().st_size
            stream = path.open("rb")
        except OSError as exc:
            self._json(500, {"status": "INVALID", "error": str(exc)})
            return
        with stream:
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            while chunk := stream.read(1024 * 1024):
                self.wfile.write(chunk)

    @staticmethod
    def _safe_file(root: Path, relative: str) -> Path | None:
        try:
            candidate = (root / relative.lstrip("/")).resolve()
            candidate.relative_to(root.resolve())
            return candidate
        except (OSError, ValueError):
            return None

    def _file(self, path: Path, *, cache_control: str) -> None:
        try:
            data = path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, OSError):
            self._json(404, {"error": "not_found"})
            return
        mime, _ = mimetypes.guess_type(path.name)
        if path.suffix == ".js":
            mime = "text/javascript"
        elif path.suffix == ".css":
            mime = "text/css"
        elif path.suffix == ".json":
            mime = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8" if (mime or '').startswith(('text/', 'application/json', 'text/javascript')) else (mime or 'application/octet-stream'))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _serve_live_studio_asset(self, raw_path: str) -> bool:
        if not raw_path.startswith("/studio/"):
            return False
        relative = raw_path[len("/studio/"):]
        target = self._safe_file(self.live_public_root, relative)
        if target is None or not target.is_file():
            self._json(404, {"error": "not_found"})
            return True
        immutable = relative.startswith("previews/g")
        self._file(target, cache_control="public, max-age=31536000, immutable" if immutable else "no-store")
        return True

    def _serve_frontend(self, raw_path: str) -> bool:
        root = self.static_root
        if root is None:
            return False
        path = raw_path or "/"
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = self._safe_file(root, relative)
        if target is not None and target.is_file():
            immutable = relative.startswith("assets/")
            self._file(target, cache_control="public, max-age=31536000, immutable" if immutable else "no-cache")
            return True
        # Studio is an in-memory SPA. Unknown browser routes deliberately fall
        # back to index.html, while API and /studio paths are handled earlier.
        index = root / "index.html"
        if index.is_file() and "." not in Path(relative).name:
            self._file(index, cache_control="no-cache")
            return True
        return False

    def _request_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > 65536:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request JSON must be an object")
        return payload

    def _request_binary(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("empty package body")
        if length > MAX_PACKAGE_BYTES:
            raise ValueError("package body exceeds 32 MiB")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("truncated package body")
        return raw

    def _request_binary_file(self, *, maximum: int, suffix: str) -> Path:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("empty package body")
        if length > maximum:
            raise ValueError("package body exceeds its safety limit")
        fd, raw_temp = tempfile.mkstemp(prefix="archon-upload-", suffix=suffix)
        temporary = Path(raw_temp)
        try:
            with os.fdopen(fd, "wb") as output:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("truncated package body")
                    output.write(chunk)
                    remaining -= len(chunk)
            return temporary
        except Exception:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise

    def _trusted_request(self) -> bool:
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in allowed:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{value}" for value in allowed}

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._trusted_request():
            self._json(403, {"error": "untrusted_origin_or_host"})
            return
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._trusted_request():
            self._json(403, {"error": "untrusted_origin_or_host"})
            return
        raw_path = urlparse(self.path).path
        path = raw_path.rstrip("/")
        if path in {"/api/studio/runtime", "/api/studio/health"}:
            self._json(200, self.bridge.payload())
            return
        if path == "/api/studio/options":
            self._json(200, self.bridge.options_payload())
            return
        if path == "/api/studio/engines/observer/live":
            self._json(200, self.bridge.observer_live_payload())
            return
        if path == "/api/studio/adapters":
            self._json(200, self.bridge.adapters_payload())
            return
        if path == "/api/studio/settings":
            self._json(200, self.bridge.settings_payload())
            return
        if path == "/api/studio/diagnostics":
            self._json(200, self.bridge.diagnostics_payload())
            return
        if path == "/api/studio/worlds/export-all":
            fd, raw_temp = tempfile.mkstemp(prefix="archon-worlds-", suffix=".archon-worlds")
            os.close(fd)
            temporary = Path(raw_temp)
            try:
                self.bridge.export_all_worlds(temporary)
                self._stream_file(
                    temporary,
                    content_type="application/vnd.archon.world-collection+zip",
                    filename="ARCHON-All-Worlds.archon-worlds",
                )
            except (WorldPortabilityError, OSError) as exc:
                self._json(500, {"status": "INVALID", "error": str(exc)})
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
            return
        parts = path.split("/")
        if len(parts) == 6 and parts[:4] == ["", "api", "studio", "worlds"] and parts[5] == "export":
            rule_id = parts[4]
            try:
                result, data = self.bridge.export_world(rule_id)
            except (WorldPortabilityError, OSError) as exc:
                self._json(404, {"status": "INVALID", "error": str(exc)})
                return
            self._binary(200, data, content_type="application/vnd.archon.world+zip", filename=f"ARCHON-Rule-{result['local_rule_id']}{'.archon-world'}")
            return
        if self._serve_live_studio_asset(raw_path):
            return
        if self._serve_frontend(raw_path):
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._trusted_request():
            self._json(403, {"error": "untrusted_origin_or_host"})
            return
        path = urlparse(self.path).path.rstrip("/")
        if path in {"/api/studio/worlds/import-all/inspect", "/api/studio/worlds/import-all"}:
            try:
                package_path = self._request_binary_file(
                    maximum=4 * 1024 * 1024 * 1024,
                    suffix=".archon-worlds",
                )
            except ValueError as exc:
                self._json(400, {"status": "INVALID", "error": str(exc)})
                return
            try:
                if path.endswith("/inspect"):
                    status, payload = self.bridge.inspect_world_collection(package_path)
                else:
                    status, payload = self.bridge.import_world_collection(package_path)
                self._json(status, payload)
            except (WorldPortabilityError, OSError) as exc:
                self._json(500, {"status": "INVALID", "error": str(exc)})
            finally:
                try:
                    package_path.unlink()
                except FileNotFoundError:
                    pass
            return
        if path in {"/api/studio/worlds/import/inspect", "/api/studio/worlds/import"}:
            try:
                package = self._request_binary()
            except ValueError as exc:
                self._json(400, {"status": "INVALID", "error": str(exc)})
                return
            if path.endswith("/inspect"):
                status, payload = self.bridge.inspect_world_import(package)
            else:
                status, payload = self.bridge.import_world(package)
            self._json(status, payload)
            return
        if path == "/api/studio/snapshot/refresh":
            started = self.bridge._start_snapshot_build("manual-refresh")
            self._json(202 if started else 200, {"ok": True, "started": started, "runtime": self.bridge.payload()})
            return
        if path == "/api/studio/adapters/add":
            try:
                config = self._request_json()
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": "invalid_request", "detail": str(exc)})
                return
            status, payload = self.bridge.add_adapter(config)
            self._json(status, payload)
            return
        if path == "/api/studio/settings":
            try:
                config = self._request_json()
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": "invalid_request", "detail": str(exc)})
                return
            status, payload = self.bridge.update_settings(config)
            self._json(status, payload)
            return
        if path == "/api/studio/system/open-folder":
            try:
                config = self._request_json()
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": "invalid_request", "detail": str(exc)})
                return
            status, payload = self.bridge.open_folder(str(config.get("key") or ""))
            self._json(status, payload)
            return
        parts = path.split("/")
        if len(parts) == 6 and parts[:4] == ["", "api", "studio", "adapters"]:
            adapter_id, action = parts[4], parts[5]
            try:
                config = self._request_json() if action == "toggle" else {}
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": "invalid_request", "detail": str(exc)})
                return
            status, payload = self.bridge.adapter_action(adapter_id, action, config)
            self._json(status, payload)
            return
        if len(parts) == 6 and parts[:4] == ["", "api", "studio", "engines"]:
            key, action = parts[4], parts[5]
            if action == "start":
                try:
                    config = self._request_json()
                except (ValueError, json.JSONDecodeError) as exc:
                    self._json(400, {"error": "invalid_request", "detail": str(exc)})
                    return
                status, payload = self.bridge.start_engine(key, config)
                self._json(status, payload)
                return
            if action == "stop":
                try:
                    config = self._request_json()
                except (ValueError, json.JSONDecodeError) as exc:
                    self._json(400, {"error": "invalid_request", "detail": str(exc)})
                    return
                status, payload = self.bridge.stop_engine(key, config)
                self._json(status, payload)
                return
            actions = {"pause": self.bridge.pause_engine, "resume": self.bridge.resume_engine}
            handler = actions.get(action)
            if handler is None:
                self._json(404, {"error": "unknown_action"})
                return
            status, payload = handler(key)
            self._json(status, payload)
            return
        self._json(404, {"error": "not_found"})


class StudioRuntimeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        bridge: StudioRuntimeBridge,
        *,
        static_root: Path | None = None,
    ):
        super().__init__(server_address, handler)
        self.bridge = bridge
        self.static_root = static_root.resolve() if static_root is not None else None
        self.live_public_root = (bridge.root / "archon-studio" / "public" / "studio").resolve()


def self_test(root: Path) -> int:
    root = root.resolve()
    required = [
        root / "UNIVERSE SEARCH.sh", root / "OBSERVER.sh", root / "ANALYZER.sh",
        root / "Universe_Search" / "universe_search_v34_closed_research_cycle.py",
        root / "Observer" / "universe_search_observer_v441_validation_calibration.py",
        root / "Tools" / "archon_studio_snapshot.py",
    ]
    missing = [path.relative_to(root).as_posix() for path in required if not path.is_file()]
    if missing:
        print("FAIL: STUDIO8 runtime bridge missing required files:")
        for item in missing:
            print(f"  - {item}")
        return 1
    bridge = StudioRuntimeBridge(root)
    payload = bridge.payload()
    assert payload["schema"] == "archon_studio_runtime_v1"
    assert set(payload["engines"]) == set(ENGINE_NAMES)
    assert payload["bridge"]["root"] == "."
    assert "embedded_search" in payload["bridge"]["capabilities"]
    assert "canonical_search_runtime_v1" in payload["bridge"]["capabilities"]
    assert "pid_bound_search_telemetry_v1" in payload["bridge"]["capabilities"]
    assert "embedded_observer_preview" in payload["bridge"]["capabilities"]
    assert "observer_preview_stop_choices" in payload["bridge"]["capabilities"]
    assert bridge.observer_studio_adapter.is_file()
    assert "observer_fast_live" in payload["bridge"]["capabilities"]
    assert "observer_native_context_handoff" in payload["bridge"]["capabilities"]
    assert "adapter_manager_v1" in payload["bridge"]["capabilities"]
    assert "studio_settings_v1" in payload["bridge"]["capabilities"]
    assert "studio_diagnostics_v1" in payload["bridge"]["capabilities"]
    assert "release_readiness_v1" in payload["bridge"]["capabilities"]
    assert payload["bridge"].get("version") == STUDIO_BUILD_VERSION
    assert "runtime_sync_v1" in payload["bridge"]["capabilities"]
    assert "preview_asset_sync_v1" in payload["bridge"]["capabilities"]
    assert "desktop_launcher_v1" in payload["bridge"]["capabilities"]
    assert "world_portability_v1" in payload["bridge"]["capabilities"]
    assert "world_collection_export_v1" in payload["bridge"]["capabilities"]
    assert "world_collection_import_v1" in payload["bridge"]["capabilities"]
    assert payload["settings"]["default_engine_mode"] in {"embedded", "native", "ask"}
    settings = bridge.settings_payload()
    assert settings["schema"] == STUDIO_SETTINGS_SCHEMA
    assert settings["diagnostics"]["schema"] == "archon_studio_diagnostics_v1"
    assert settings["diagnostics"]["release_readiness"]["functional_status"] in {"NOT_RUN", "PASS", "FAIL", "INVALID"}
    assert settings["diagnostics"]["paths"]["project"]["exists"] is True
    adapters = bridge.adapters_payload()
    assert adapters["schema"] == "archon_studio_adapters_v1"
    assert adapters["manifest_schema"] == ADAPTER_MANIFEST_SCHEMA
    assert bridge.observer_live_payload()["schema"] == "archon_studio_observer_live_v1"
    assert bridge.search_score_modes
    search_cmd, search_config = bridge._build_search_command({"score_mode": bridge.options_payload()["search"]["defaults"]["score_mode"], "search_mode": "ordinary"})
    prefix_len = len(bridge.python_command)
    assert search_cmd[prefix_len:prefix_len + 2] == ["-u", str(bridge.search_script)] and search_config["ui_mode"] == "embedded"
    observer_cmd, observer_config = bridge._build_observer_command({"rule_id": "251", "max_ticks": 1000, "speed": 100})
    assert "--headless" in observer_cmd and "--studio-stream" in observer_cmd and observer_config["rule_id"] == "00251"
    assert "--run-output-dir" in observer_cmd and observer_config["preview_mode"] is True
    preview_probe = root / str(observer_config["preview_session_dir"])
    assert preview_probe.is_dir()
    shutil.rmtree(preview_probe, ignore_errors=True)
    native_cmd, native_config = bridge._build_observer_native_context_command({"rule_id": "251", "max_ticks": 1000, "speed": 100})
    assert str(bridge.observer_launcher_adapter) in native_cmd and "--headless" not in native_cmd
    assert native_config["rule_id"] == "00251" and native_config["native_context_handoff"] is True
    assert native_config["native_target"] == "ol2_launcher_context" and native_config["handoff_semantics"] == "ol2-config-prefill-fresh-native-review"
    assert validate_search_runtime(root) == bridge.search_script
    print("PASS: STUDIO20.5 runtime bridge includes portable Worlds and fail-closed PID-attested canonical Universe Search")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ARCHON Studio local runtime bridge")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--static-root", type=Path, default=None, help="Serve the prebuilt ARCHON Studio frontend from this directory")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test(args.root)
    static_root = args.static_root.resolve() if args.static_root is not None else None
    if static_root is not None and not (static_root / "index.html").is_file():
        print(f"ARCHON Studio production bundle missing index.html under {static_root}", file=sys.stderr)
        return 2
    bridge = StudioRuntimeBridge(args.root)
    server = StudioRuntimeHTTPServer((args.host, args.port), StudioRequestHandler, bridge, static_root=static_root)
    bridge.start()
    print(f"ARCHON Studio runtime bridge listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        bridge.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
