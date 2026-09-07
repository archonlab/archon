#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project ARCHON Search Launcher v2.0.

BRIDGE4.2 establishes the Search Launcher as the operator surface for long
Universe Search executions. Observer Launcher retains scientific authorization;
managed Search Launcher owns start/monitor/pause/resume without changing the
pinned research contract or using Observer Queue.

Standalone/manual Search remains supported for ordinary exploratory work.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
import os
import queue
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

LAUNCHER_VERSION = "v2.0"
BRIDGE_ID = "BRIDGE4.2"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from Tools.archon_runtime_python import runtime_python_command
from Tools.archon_platform import pid_alive, open_folder

SEARCH_SCRIPT = PROJECT_ROOT / "Universe_Search" / "universe_search_v34_closed_research_cycle.py"
DEFAULT_EXPERIMENT_PLAN = PROJECT_ROOT / "Results" / "Analysis" / "experiment_plan.json"
DEFAULT_CHECKPOINT = PROJECT_ROOT / "Results" / "Universe_Search" / "checkpoint_observer_niches.json"
SEARCH_LAUNCHER_SETTINGS = PROJECT_ROOT / "Config" / "Studio" / "search_launcher_settings.json"
STUDIO_SETTINGS = PROJECT_ROOT / "Config" / "Studio" / "settings.json"
SEARCH_LAUNCHER_SETTINGS_SCHEMA = "archon_search_launcher_settings_v1"


SEARCH_MODES = [
    "ordinary",
    "diversity",
    "cohort_target",
    "counterexample",
    "local_around_rule",
]

MODE_HELP = {
    "ordinary": "Standard Search using the current legacy-compatible logic.",
    "diversity": "Diversity Search increases exploration and novelty pressure.",
    "cohort_target": "Targeted Search driven by an authorized Analyzer research job.",
    "counterexample": "Control-heavy Search for worlds that challenge a current claim.",
    "local_around_rule": "Local Search around selected Atlas rules without modifying parents.",
}

FALLBACK_SCORE_MODES = [
    "balanced", "novelty", "motion", "islands", "boundaries", "scale_genesis",
    "living_boundaries", "edge_transport", "emergence", "nested_complexity",
    "memory", "information_flow", "stable_movers", "hierarchy", "emergent_ecology",
    "observer_log", "entity_mode", "local_life", "flow", "region_dynamics",
    "hierarchical_novelty", "macro_scaffold", "memory_trace", "adaptive_observer",
    "cosmic_curator", "stress_test", "observer_evolution", "coevolution",
    "observer_stability", "observer_genetics", "observer_niches",
]

PALETTES = {
    "dark": {
        "window": "#07111d",
        "surface": "#0b1624",
        "surface2": "#0e1c2c",
        "surface3": "#122337",
        "border": "#26364a",
        "text": "#f3f6fa",
        "muted": "#9ba9bb",
        "accent": "#14c9b7",
        "accent_hover": "#1bd9c6",
        "success": "#20d29c",
        "warning": "#f3bd56",
        "danger": "#ff6c78",
        "entry": "#0a1421",
    },
    "light": {
        "window": "#f4f6f8",
        "surface": "#ffffff",
        "surface2": "#f8fafb",
        "surface3": "#eef3f5",
        "border": "#d8e0e5",
        "text": "#15202b",
        "muted": "#667482",
        "accent": "#13b8aa",
        "accent_hover": "#0fa89b",
        "success": "#13a77d",
        "warning": "#b97b15",
        "danger": "#ce4052",
        "entry": "#ffffff",
    },
}

_GEN_RE = re.compile(r"Generation\s+(\d+)/(\d+)\s+mode=([^\s]+)")
_WORKERS_RE = re.compile(r"parallel eval:\s+workers=(\d+),\s+jobs=(\d+)")
_EVAL_RE = re.compile(r"eval\s+(\d+)/(\d+)\s+done\s+\(failed=(\d+),\s+elapsed=(\d+)s\)")
_HEART_RE = re.compile(r"eval heartbeat:\s+(\d+)/(\d+)\s+done,.*?elapsed=(\d+)s")
_TARGET_RE = re.compile(
    r"\[TargetScoring\]\s+gen=(\d+)\s+exact=(\d+)\s+best_rule=([^\s]+)\s+"
    r"distance=([^\s]+)\s+coverage=([^\s]+)"
)
_BEST_RE = re.compile(
    r"BEST\s+gen=(\d+):\s+rule=([^\s]+)\s+score=([^\s]+)\s+\|\s+"
    r"best ever=([^\s]+)\s+([^\s]+)"
)
_GEN_TIME_RE = re.compile(r"generation time:\s+([0-9.]+)\s+min")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default



def _normalize_theme_preference(value: Any) -> str:
    text = str(value or "follow_studio").strip().lower()
    aliases = {"auto": "follow_studio", "studio": "follow_studio", "system": "follow_studio"}
    text = aliases.get(text, text)
    return text if text in {"follow_studio", "dark", "light"} else "follow_studio"


def load_search_launcher_settings() -> dict[str, Any]:
    payload = read_json(SEARCH_LAUNCHER_SETTINGS, {})
    source = payload.get("settings", payload) if isinstance(payload, dict) else {}
    if not isinstance(source, dict):
        source = {}
    return {
        "theme": _normalize_theme_preference(source.get("theme")),
        "confirm_close": bool(source.get("confirm_close", True)),
    }


def save_search_launcher_settings(settings: dict[str, Any]) -> None:
    normalized = {
        "theme": _normalize_theme_preference(settings.get("theme")),
        "confirm_close": bool(settings.get("confirm_close", True)),
    }
    SEARCH_LAUNCHER_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SEARCH_LAUNCHER_SETTINGS.write_text(
        json.dumps({"schema": SEARCH_LAUNCHER_SETTINGS_SCHEMA, "settings": normalized}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def studio_theme() -> str:
    payload = read_json(STUDIO_SETTINGS, {})
    source = payload.get("settings", payload) if isinstance(payload, dict) else {}
    appearance = str(source.get("appearance") or "midnight").strip().lower() if isinstance(source, dict) else "midnight"
    return "light" if appearance == "light" else "dark"


def resolve_launcher_theme(preference: str) -> str:
    pref = _normalize_theme_preference(preference)
    return studio_theme() if pref == "follow_studio" else pref


def ask_yes_no_english(parent: tk.Misc, title: str, message: str, *, warning: bool = False) -> bool:
    """Locale-independent confirmation dialog with explicit English Yes/No labels."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)
    result = {"value": False}

    frame = ttk.Frame(dialog, padding=(18, 16))
    frame.pack(fill="both", expand=True)
    if warning:
        ttk.Label(frame, text="⚠", font=("TkDefaultFont", 18, "bold")).grid(row=0, column=0, sticky="n", padx=(0, 12))
    ttk.Label(frame, text=message, justify="left", wraplength=500).grid(row=0, column=1, sticky="w")
    buttons = ttk.Frame(frame)
    buttons.grid(row=1, column=0, columnspan=2, sticky="e", pady=(18, 0))

    def finish(value: bool) -> None:
        result["value"] = value
        dialog.destroy()

    ttk.Button(buttons, text="No", command=lambda: finish(False)).pack(side="right")
    ttk.Button(buttons, text="Yes", command=lambda: finish(True)).pack(side="right", padx=(0, 8))
    dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    dialog.bind("<Escape>", lambda _event: finish(False))
    dialog.bind("<Return>", lambda _event: finish(True))
    dialog.update_idletasks()
    try:
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - dialog.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - dialog.winfo_reqheight()) // 2)
        dialog.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass
    dialog.grab_set()
    dialog.focus_set()
    parent.wait_window(dialog)
    return bool(result["value"])

def normalize_rule_id(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        return f"{int(value):05d}"
    except Exception:
        return value


def checkpoint_resume_config(payload: Any) -> dict[str, Any]:
    """Extract the exact experiment selection stored in a checkpoint."""
    if not isinstance(payload, dict):
        raise ValueError("checkpoint is not a JSON object")
    score_mode = str(payload.get("score_mode") or "").strip()
    if not score_mode:
        raise ValueError("checkpoint has no score_mode")
    identity = payload.get("search_config_identity")
    if not isinstance(identity, dict):
        return {
            "score_mode": score_mode,
            "search_mode": "ordinary",
            "job_id": "",
            "target_regime": "",
            "seed_rules": [],
            "legacy": True,
        }
    search_mode = str(identity.get("search_mode") or "").strip().lower()
    if search_mode not in SEARCH_MODES:
        raise ValueError(f"checkpoint has unknown Search mode {search_mode or 'missing'}")
    return {
        "score_mode": score_mode,
        "search_mode": search_mode,
        "job_id": str(identity.get("job_id") or "").strip(),
        "target_regime": str(identity.get("target_regime") or "").strip(),
        "seed_rules": [
            normalize_rule_id(value)
            for value in (identity.get("seed_rules") or [])
            if normalize_rule_id(value)
        ],
        "legacy": False,
    }


def detect_score_modes() -> list[str]:
    try:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from Universe_Search import universe_search_core as core  # type: ignore
        modes = list(getattr(core, "SCORE_MODES", []) or [])
        return modes or FALLBACK_SCORE_MODES
    except Exception:
        return FALLBACK_SCORE_MODES


def pid_is_alive(pid: int | None) -> bool:
    if not pid or int(pid) <= 0:
        return False
    return pid_alive(int(pid))


def _finite_float(value: str) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class SearchProgressSnapshot:
    generation: int = 0
    generations: int = 0
    evaluated: int = 0
    population: int = 0
    failed: int = 0
    workers: int = 0
    current_generation_elapsed_seconds: int = 0
    completed_generation_seconds: float = 0.0
    exact_matches: int = 0
    target_rule: str | None = None
    target_distance: float | None = None
    target_coverage: float | None = None
    overall_rule: str | None = None
    overall_score: float | None = None
    best_ever_rule: str | None = None
    best_ever_score: float | None = None
    complete: bool = False

    @property
    def total_slots(self) -> int:
        return max(0, self.generations * self.population)

    @property
    def completed_slots(self) -> int:
        if not self.generation or not self.population:
            return 0
        before = max(0, self.generation - 1) * self.population
        return min(self.total_slots or before + self.evaluated, before + self.evaluated)

    @property
    def overall_fraction(self) -> float:
        return (self.completed_slots / self.total_slots) if self.total_slots else 0.0

    @property
    def generation_fraction(self) -> float:
        return (self.evaluated / self.population) if self.population else 0.0

    @property
    def elapsed_seconds(self) -> float:
        return self.completed_generation_seconds + float(self.current_generation_elapsed_seconds)

    @property
    def eta_seconds(self) -> float | None:
        done = self.completed_slots
        total = self.total_slots
        elapsed = self.elapsed_seconds
        if done < 5 or total <= done or elapsed <= 0:
            return None
        return max(0.0, (elapsed / done) * (total - done))


class SearchProgressTracker:
    """Pure stdout parser used by both live managed monitoring and tests."""

    def __init__(self, *, generations: int = 0, population: int = 0) -> None:
        self.snapshot = SearchProgressSnapshot(generations=generations, population=population)

    def reset(self, *, generations: int = 0, population: int = 0) -> None:
        self.snapshot = SearchProgressSnapshot(generations=generations, population=population)

    def feed_line(self, line: str) -> SearchProgressSnapshot:
        snap = self.snapshot
        if match := _GEN_RE.search(line):
            gen, total, _mode = match.groups()
            snap = replace(
                snap,
                generation=int(gen),
                generations=int(total),
                evaluated=0,
                failed=0,
                current_generation_elapsed_seconds=0,
            )
        if match := _WORKERS_RE.search(line):
            workers, jobs = match.groups()
            snap = replace(snap, workers=int(workers), population=int(jobs) or snap.population)
        if match := _EVAL_RE.search(line):
            done, total, failed, elapsed = match.groups()
            snap = replace(
                snap,
                evaluated=int(done),
                population=int(total),
                failed=int(failed),
                current_generation_elapsed_seconds=int(elapsed),
            )
        elif match := _HEART_RE.search(line):
            done, total, elapsed = match.groups()
            snap = replace(
                snap,
                evaluated=int(done),
                population=int(total),
                current_generation_elapsed_seconds=int(elapsed),
            )
        if match := _TARGET_RE.search(line):
            _gen, exact, rule, distance, coverage = match.groups()
            snap = replace(
                snap,
                exact_matches=int(exact),
                target_rule=normalize_rule_id(rule),
                target_distance=_finite_float(distance),
                target_coverage=_finite_float(coverage),
            )
        if match := _BEST_RE.search(line):
            _gen, rule, score, best_rule, best_score = match.groups()
            snap = replace(
                snap,
                overall_rule=normalize_rule_id(rule),
                overall_score=_finite_float(score),
                best_ever_rule=normalize_rule_id(best_rule),
                best_ever_score=_finite_float(best_score),
            )
        if match := _GEN_TIME_RE.search(line):
            minutes = float(match.group(1))
            # Generation time is emitted only after the generation is complete.
            snap = replace(
                snap,
                completed_generation_seconds=snap.completed_generation_seconds + minutes * 60.0,
                current_generation_elapsed_seconds=0,
            )
        if "Search complete." in line:
            # Terminal Search state: workers are no longer active even though the
            # last emitted parallel-eval line still contains the worker pool size.
            snap = replace(snap, complete=True, workers=0)
        self.snapshot = snap
        return snap

    def feed_text(self, text: str) -> SearchProgressSnapshot:
        for line in text.splitlines():
            self.feed_line(line)
        return self.snapshot


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "Estimating…"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def progress_display_labels(
    snapshot: SearchProgressSnapshot, *, execution_completed: bool = False
) -> tuple[str, str]:
    """Return terminal-aware worker/ETA labels for the operator surface.

    A historical replay retains the last `parallel eval: workers=N` line in the
    log. Once Search is complete those workers are not active, and ETA is not
    being estimated anymore. `execution_completed` covers reconciled runtimes
    whose log may be partial or externally rotated.
    """
    terminal = bool(snapshot.complete or execution_completed)
    if terminal:
        return "0 / Idle", "Completed"
    workers = f"{snapshot.workers} Active" if snapshot.workers else "0 / Idle"
    return workers, format_duration(snapshot.eta_seconds)


class SearchLauncher(tk.Tk):
    def __init__(self, *, managed_runtime: str | None = None, theme: str = "auto") -> None:
        super().__init__()
        self.managed_runtime = str(managed_runtime or "").strip() or None
        self.managed = self.managed_runtime is not None
        self.managed_context: dict[str, Any] = {}
        self.managed_handoff: Any | None = None
        self.managed_log_path: Path | None = None
        self.managed_log_offset = 0
        self.managed_pid: int | None = None
        self.managed_pause_requested = False
        self.managed_reconciled = False
        self.process: subprocess.Popen[str] | None = None
        self.active_command = "evolve"
        self.close_when_process_finishes = False
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.jobs_by_id: dict[str, dict[str, Any]] = {}
        self.launcher_settings = load_search_launcher_settings()
        requested_theme = _normalize_theme_preference(theme) if theme != "auto" else self.launcher_settings["theme"]
        self.theme_preference = requested_theme
        self.theme_name = resolve_launcher_theme(requested_theme)
        self.confirm_close = bool(self.launcher_settings.get("confirm_close", True))
        self.progress_tracker = SearchProgressTracker()

        self.score_mode_var = tk.StringVar(value="observer_niches")
        self.search_mode_var = tk.StringVar(value="ordinary")
        self.plan_path_var = tk.StringVar(value=str(DEFAULT_EXPERIMENT_PLAN))
        self.job_id_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.seed_rules_var = tk.StringVar()
        self.command_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.managed_status_var = tk.StringVar(value="Standalone Search")
        self.managed_detail_var = tk.StringVar(value="Manual configuration")
        self.summary_var = tk.StringVar(value="")
        self.progress_title_var = tk.StringVar(value="Search idle")
        self.progress_percent_var = tk.StringVar(value="0.0%")
        self.generation_var = tk.StringVar(value="0 / 0")
        self.evaluated_var = tk.StringVar(value="0 / 0")
        self.failed_var = tk.StringVar(value="0")
        self.workers_var = tk.StringVar(value="0")
        self.elapsed_var = tk.StringVar(value="0s")
        self.eta_var = tk.StringVar(value="Estimating…")
        self.champions_var = tk.StringVar(value="Overall: —    Target: —    Exact: 0")
        self.scientific_var = tk.StringVar(value="Scientific outcome: pending")
        self.previous_search_mode = self.search_mode_var.get()

        self.title(f"Project ARCHON Search Launcher {LAUNCHER_VERSION}")
        self.geometry("1180x820")
        self.minsize(1020, 720)

        self._build_ui()
        self._bind_events()
        self._apply_theme(self.theme_name)

        if self.managed:
            try:
                self._initialize_managed_mode()
            except Exception as exc:
                self.status_var.set(f"Managed mode refused: {exc}")
                messagebox.showerror("Managed Search Refused", str(exc), parent=self)
                self.after(10, self.destroy)
                return
        else:
            self.load_experiment_plan(silent=True)
            self.update_mode_ui()
            self.update_command_preview()

        self.protocol("WM_DELETE_WINDOW", self.on_window_close)
        self.after(100, self.poll_output_queue)
        self.after(500, self.poll_managed_execution)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.root_frame = ttk.Frame(self, style="Archon.Root.TFrame", padding=(18, 14))
        self.root_frame.pack(fill="both", expand=True)

        header = ttk.Frame(self.root_frame, style="Archon.Root.TFrame")
        header.pack(fill="x", pady=(0, 10))
        title_box = ttk.Frame(header, style="Archon.Root.TFrame")
        title_box.pack(side="left")
        ttk.Label(title_box, text="Project ARCHON", style="Archon.Brand.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text="Search Launcher v2.0",
            style="Archon.Subtitle.TLabel",
        ).pack(anchor="w")
        self.theme_button = ttk.Button(header, text="Light / Dark", command=self.toggle_theme, style="Archon.Secondary.TButton")
        self.theme_button.pack(side="right", padx=(8, 0))
        ttk.Button(header, text="Settings", command=self._show_settings_dialog, style="Archon.Secondary.TButton").pack(side="right")

        self.notebook = ttk.Notebook(self.root_frame, style="Archon.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.launch_tab = ttk.Frame(self.notebook, style="Archon.Root.TFrame", padding=(0, 12))
        self.job_tab = ttk.Frame(self.notebook, style="Archon.Root.TFrame", padding=(0, 12))
        self.command_tab = ttk.Frame(self.notebook, style="Archon.Root.TFrame", padding=(0, 12))
        self.output_tab = ttk.Frame(self.notebook, style="Archon.Root.TFrame", padding=(0, 12))
        self.notebook.add(self.launch_tab, text=" Launch Settings ")
        self.notebook.add(self.job_tab, text=" Selected Research Job ")
        self.notebook.add(self.command_tab, text=" Launch Command ")
        self.notebook.add(self.output_tab, text=" Process Output ")

        top = ttk.Frame(self.launch_tab, style="Archon.Root.TFrame")
        top.pack(fill="x")
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=2)

        config_card = self._card(top, "Search Configuration")
        config_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        config = ttk.Frame(config_card, style="Archon.Card.TFrame", padding=(14, 4, 14, 12))
        config.pack(fill="both", expand=True)
        config.columnconfigure(1, weight=1)
        self.score_combo = self._field_combo(config, 0, "Score mode", self.score_mode_var, detect_score_modes())
        self.mode_combo = self._field_combo(config, 1, "Search mode", self.search_mode_var, SEARCH_MODES)
        self.plan_entry = self._field_entry(config, 2, "Experiment plan", self.plan_path_var)
        plan_buttons = ttk.Frame(config, style="Archon.Card.TFrame")
        plan_buttons.grid(row=2, column=2, sticky="e", padx=(7, 0), pady=5)
        self.plan_browse_button = ttk.Button(plan_buttons, text="Browse", command=self.choose_plan, style="Archon.Secondary.TButton")
        self.plan_browse_button.pack(side="left")
        self.plan_reload_button = ttk.Button(plan_buttons, text="Reload", command=self.load_experiment_plan, style="Archon.Secondary.TButton")
        self.plan_reload_button.pack(side="left", padx=(5, 0))
        self.job_combo = self._field_combo(config, 3, "Search job", self.job_id_var, [])
        self.target_entry = self._field_entry(config, 4, "Target regime", self.target_var)
        self.seed_entry = self._field_entry(config, 5, "Seed rules", self.seed_rules_var)
        self.mode_help = ttk.Label(config, text="", style="Archon.Muted.TLabel", wraplength=580, justify="left")
        self.mode_help.grid(row=6, column=1, columnspan=2, sticky="w", pady=(5, 0))

        right = ttk.Frame(top, style="Archon.Root.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        managed_card = self._card(right, "ARCHON-managed")
        managed_card.pack(fill="x")
        managed_body = ttk.Frame(managed_card, style="Archon.Card.TFrame", padding=(14, 4, 14, 13))
        managed_body.pack(fill="x")
        ttk.Label(managed_body, textvariable=self.managed_status_var, style="Archon.Success.TLabel").pack(anchor="w")
        ttk.Label(managed_body, textvariable=self.managed_detail_var, style="Archon.Muted.TLabel", wraplength=420, justify="left").pack(anchor="w", pady=(5, 0))

        summary_card = self._card(right, "Search Configuration Summary")
        summary_card.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(summary_card, textvariable=self.summary_var, style="Archon.Body.TLabel", wraplength=430, justify="left").pack(anchor="w", padx=14, pady=(4, 14))

        progress_card = self._card(self.launch_tab, "Search Progress")
        progress_card.pack(fill="x", pady=(14, 0))
        progress_body = ttk.Frame(progress_card, style="Archon.Card.TFrame", padding=(14, 3, 14, 14))
        progress_body.pack(fill="x")
        progress_head = ttk.Frame(progress_body, style="Archon.Card.TFrame")
        progress_head.pack(fill="x")
        ttk.Label(progress_head, textvariable=self.progress_title_var, style="Archon.Body.TLabel").pack(side="left")
        ttk.Label(progress_head, textvariable=self.progress_percent_var, style="Archon.Success.TLabel").pack(side="right")
        self.progress_bar = ttk.Progressbar(progress_body, mode="determinate", maximum=100.0, style="Archon.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", pady=(8, 12))
        stats = ttk.Frame(progress_body, style="Archon.Card.TFrame")
        stats.pack(fill="x")
        for idx, (label, var) in enumerate((
            ("Generation", self.generation_var),
            ("Evaluated", self.evaluated_var),
            ("Failed", self.failed_var),
            ("Workers", self.workers_var),
            ("Elapsed", self.elapsed_var),
            ("ETA", self.eta_var),
        )):
            box = ttk.Frame(stats, style="Archon.Card.TFrame")
            box.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 8, 0))
            stats.columnconfigure(idx, weight=1)
            ttk.Label(box, text=label.upper(), style="Archon.Micro.TLabel").pack(anchor="w")
            ttk.Label(box, textvariable=var, style="Archon.Stat.TLabel").pack(anchor="w", pady=(3, 0))
        ttk.Label(progress_body, textvariable=self.champions_var, style="Archon.Muted.TLabel").pack(anchor="w", pady=(11, 0))
        ttk.Label(progress_body, textvariable=self.scientific_var, style="Archon.Muted.TLabel").pack(anchor="w", pady=(4, 0))

        command_card = self._card(self.launch_tab, "Launch Command")
        command_card.pack(fill="x", pady=(14, 0))
        self.command_entry = ttk.Entry(command_card, textvariable=self.command_var, state="readonly", style="Archon.TEntry")
        self.command_entry.pack(fill="x", padx=14, pady=(3, 14))

        actions = ttk.Frame(self.root_frame, style="Archon.Root.TFrame")
        actions.pack(fill="x", pady=(12, 0))
        self.launch_button = ttk.Button(actions, text="Start New Search", command=self.launch_search, style="Archon.Primary.TButton")
        self.launch_button.pack(side="left")
        self.resume_button = ttk.Button(actions, text="Resume from Checkpoint", command=self.resume_search, style="Archon.Secondary.TButton")
        self.resume_button.pack(side="left", padx=(8, 0))
        self.stop_button = ttk.Button(actions, text="Pause After Generation", command=self.stop_search, state="disabled", style="Archon.Secondary.TButton")
        self.stop_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Copy Command", command=self.copy_command, style="Archon.Secondary.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open Run Folder", command=self.open_run_folder, style="Archon.Secondary.TButton").pack(side="left", padx=(8, 0))
        ttk.Label(actions, textvariable=self.status_var, style="Archon.Muted.TLabel").pack(side="right")

        # Research Job tab
        job_card = self._card(self.job_tab, "Selected Research Job")
        job_card.pack(fill="both", expand=True)
        self.job_info = tk.Text(job_card, height=18, wrap="word", relief="flat", borderwidth=0, padx=14, pady=12, state="disabled")
        self.job_info.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        # Command tab
        command_detail_card = self._card(self.command_tab, "Pinned / Previewed Launch Command")
        command_detail_card.pack(fill="x")
        self.command_text = tk.Text(command_detail_card, height=10, wrap="word", relief="flat", borderwidth=0, padx=14, pady=12, state="disabled")
        self.command_text.pack(fill="x", padx=1, pady=(0, 1))
        ttk.Label(
            self.command_tab,
            text="Managed mode keeps this scientific command read-only. Resume may only replace the evolve verb with resume.",
            style="Archon.Muted.TLabel",
            wraplength=980,
        ).pack(anchor="w", pady=(10, 0))

        # Output tab
        output_card = self._card(self.output_tab, "Process Output")
        output_card.pack(fill="both", expand=True)
        output_body = ttk.Frame(output_card, style="Archon.Card.TFrame")
        output_body.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.output = tk.Text(output_body, wrap="none", relief="flat", borderwidth=0, padx=12, pady=10, state="disabled")
        self.output.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(output_body, orient="vertical", command=self.output.yview)
        scrollbar.pack(side="right", fill="y")
        self.output.configure(yscrollcommand=scrollbar.set)

    def _card(self, parent: tk.Widget, title: str) -> ttk.Frame:
        outer = ttk.Frame(parent, style="Archon.Card.TFrame")
        ttk.Label(outer, text=title, style="Archon.CardTitle.TLabel").pack(anchor="w", padx=14, pady=(11, 6))
        return outer

    def _field_combo(self, parent: tk.Widget, row: int, label: str, var: tk.StringVar, values: list[str]) -> ttk.Combobox:
        ttk.Label(parent, text=label.upper(), style="Archon.Micro.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        combo = ttk.Combobox(parent, textvariable=var, values=values, state="readonly", style="Archon.TCombobox")
        combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)
        return combo

    def _field_entry(self, parent: tk.Widget, row: int, label: str, var: tk.StringVar) -> ttk.Entry:
        ttk.Label(parent, text=label.upper(), style="Archon.Micro.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        entry = ttk.Entry(parent, textvariable=var, style="Archon.TEntry")
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)
        return entry

    def _apply_theme(self, theme: str) -> None:
        self.theme_name = theme
        c = PALETTES[theme]
        self.configure(background=c["window"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Archon.Root.TFrame", background=c["window"])
        style.configure("Archon.Card.TFrame", background=c["surface"], relief="solid", borderwidth=1)
        style.configure("Archon.Brand.TLabel", background=c["window"], foreground=c["text"], font=("TkDefaultFont", 15, "bold"))
        style.configure("Archon.Subtitle.TLabel", background=c["window"], foreground=c["muted"], font=("TkDefaultFont", 10))
        style.configure("Archon.CardTitle.TLabel", background=c["surface"], foreground=c["text"], font=("TkDefaultFont", 10, "bold"))
        style.configure("Archon.Body.TLabel", background=c["surface"], foreground=c["text"], font=("TkDefaultFont", 10))
        style.configure("Archon.Muted.TLabel", background=c["surface"], foreground=c["muted"], font=("TkDefaultFont", 9))
        style.configure("Archon.Micro.TLabel", background=c["surface"], foreground=c["muted"], font=("TkDefaultFont", 8, "bold"))
        style.configure("Archon.Stat.TLabel", background=c["surface"], foreground=c["text"], font=("TkDefaultFont", 11, "bold"))
        style.configure("Archon.Success.TLabel", background=c["surface"], foreground=c["success"], font=("TkDefaultFont", 10, "bold"))
        style.configure("Archon.TEntry", fieldbackground=c["entry"], foreground=c["text"], insertcolor=c["text"], bordercolor=c["border"], padding=7)
        style.configure("Archon.TCombobox", fieldbackground=c["entry"], foreground=c["text"], bordercolor=c["border"], padding=6)
        style.map("Archon.TCombobox", fieldbackground=[("readonly", c["entry"])], foreground=[("readonly", c["text"])])
        style.configure("Archon.Primary.TButton", background=c["accent"], foreground="#001513", padding=(12, 8), borderwidth=0)
        style.map("Archon.Primary.TButton", background=[("active", c["accent_hover"]), ("disabled", c["border"])])
        style.configure("Archon.Secondary.TButton", background=c["surface2"], foreground=c["text"], padding=(10, 8), bordercolor=c["border"])
        style.map("Archon.Secondary.TButton", background=[("active", c["surface3"])])
        style.configure("Archon.TCheckbutton", background=c["surface"], foreground=c["text"])
        style.configure("Archon.Horizontal.TProgressbar", troughcolor=c["surface3"], background=c["accent"], bordercolor=c["surface3"], lightcolor=c["accent"], darkcolor=c["accent"])
        style.configure("Archon.TNotebook", background=c["window"], borderwidth=0)
        style.configure("Archon.TNotebook.Tab", background=c["window"], foreground=c["muted"], padding=(14, 8), borderwidth=0)
        style.map("Archon.TNotebook.Tab", background=[("selected", c["surface"])], foreground=[("selected", c["text"])])
        if hasattr(self, "theme_button"):
            self.theme_button.configure(text=f"Theme: {self.theme_name.title()}")
        for widget in (getattr(self, "job_info", None), getattr(self, "command_text", None), getattr(self, "output", None)):
            if widget is not None:
                widget.configure(background=c["surface"], foreground=c["text"], insertbackground=c["text"], selectbackground=c["accent"], selectforeground="#001513")

    def toggle_theme(self) -> None:
        next_theme = "light" if self.theme_name == "dark" else "dark"
        self.theme_preference = next_theme
        self._apply_theme(next_theme)
        self.launcher_settings.update({"theme": next_theme, "confirm_close": self.confirm_close})
        save_search_launcher_settings(self.launcher_settings)

    def _show_settings_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Search Launcher Settings")
        dialog.transient(self)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=(18, 16))
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Appearance", style="Archon.CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text="Theme", style="Archon.Body.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 0), padx=(0, 18))
        labels = {"Follow Studio": "follow_studio", "Dark": "dark", "Light": "light"}
        reverse = {value: key for key, value in labels.items()}
        theme_var = tk.StringVar(value=reverse.get(self.theme_preference, "Follow Studio"))
        combo = ttk.Combobox(body, textvariable=theme_var, values=list(labels), state="readonly", width=20, style="Archon.TCombobox")
        combo.grid(row=1, column=1, sticky="ew", pady=(12, 0))

        confirm_var = tk.BooleanVar(value=self.confirm_close)
        ttk.Checkbutton(body, text="Confirm before closing Search Launcher", variable=confirm_var, style="Archon.TCheckbutton").grid(row=2, column=0, columnspan=2, sticky="w", pady=(14, 0))
        ttk.Label(
            body,
            text="Scientific Search parameters are controlled by the active research profile and are not changed here.",
            style="Archon.Muted.TLabel",
            wraplength=470,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(14, 0))

        buttons = ttk.Frame(body, style="Archon.Root.TFrame")
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(18, 0))

        def save_and_close() -> None:
            preference = labels.get(theme_var.get(), "follow_studio")
            self.theme_preference = preference
            self.confirm_close = bool(confirm_var.get())
            self.launcher_settings = {"theme": preference, "confirm_close": self.confirm_close}
            save_search_launcher_settings(self.launcher_settings)
            self._apply_theme(resolve_launcher_theme(preference))
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=dialog.destroy, style="Archon.Secondary.TButton").pack(side="right")
        ttk.Button(buttons, text="Save", command=save_and_close, style="Archon.Primary.TButton").pack(side="right", padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set()
        combo.focus_set()

    # ---------------------------------------------------------- mode/config
    def _bind_events(self) -> None:
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_mode_changed())
        self.score_combo.bind("<<ComboboxSelected>>", lambda _e: self.update_command_preview())
        self.job_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_job_selected())
        for var in (self.plan_path_var, self.target_var, self.seed_rules_var):
            var.trace_add("write", lambda *_args: self.update_command_preview())

    def choose_plan(self) -> None:
        if self.managed:
            return
        selected = filedialog.askopenfilename(
            title="Select experiment_plan.json",
            initialdir=str(DEFAULT_EXPERIMENT_PLAN.parent),
            filetypes=[("JSON files", "*.json"), ("All files", "*")],
        )
        if selected:
            self.plan_path_var.set(selected)
            self.load_experiment_plan()

    def load_experiment_plan(self, silent: bool = False) -> None:
        if self.managed:
            return
        path = Path(self.plan_path_var.get()).expanduser()
        payload = read_json(path, {})
        jobs = payload.get("search_jobs", []) if isinstance(payload, dict) else []
        jobs = [job for job in jobs if isinstance(job, dict)]
        self.jobs_by_id = {str(job.get("id")): job for job in jobs if job.get("id")}
        values = list(self.jobs_by_id)
        self.job_combo.configure(values=values)
        if values:
            if self.job_id_var.get() not in self.jobs_by_id:
                self.job_id_var.set(values[0])
            self.on_job_selected()
            self.status_var.set(f"Loaded Search jobs: {len(values)}")
        else:
            self.job_id_var.set("")
            self.target_var.set("")
            self.update_job_info()
            self.status_var.set("No Search jobs found")
            if not silent:
                messagebox.showwarning("Experiment plan", f"No search_jobs found in:\n{path}", parent=self)

    def on_job_selected(self) -> None:
        if self.managed:
            return
        job = self.jobs_by_id.get(self.job_id_var.get())
        mode = self.search_mode_var.get()
        if job and mode in {"cohort_target", "counterexample"}:
            self.target_var.set(str(job.get("target_regime") or ""))
            self.seed_rules_var.set(", ".join(normalize_rule_id(x) for x in (job.get("seed_rules") or [])))
        self.update_job_info()
        self.update_command_preview()

    def on_mode_changed(self) -> None:
        if self.managed:
            return
        mode = self.search_mode_var.get()
        previous = self.previous_search_mode
        if mode in {"ordinary", "diversity", "local_around_rule"}:
            self.target_var.set("")
            if mode != "local_around_rule":
                self.seed_rules_var.set("")
        elif mode in {"cohort_target", "counterexample"} and previous not in {"cohort_target", "counterexample"}:
            self.on_job_selected()
        self.previous_search_mode = mode
        self.update_mode_ui()
        self.update_command_preview()

    def update_mode_ui(self) -> None:
        mode = self.search_mode_var.get()
        self.mode_help.configure(text=MODE_HELP.get(mode, ""))
        if self.managed:
            for widget in (self.score_combo, self.mode_combo, self.job_combo):
                widget.configure(state="disabled")
            for widget in (self.plan_entry, self.target_entry, self.seed_entry):
                widget.configure(state="readonly")
            self.plan_browse_button.configure(state="disabled")
            self.plan_reload_button.configure(state="disabled")
        else:
            needs_plan = mode in {"cohort_target", "counterexample"}
            needs_seeds = mode in {"diversity", "cohort_target", "counterexample", "local_around_rule"}
            self.plan_entry.configure(state="normal" if needs_plan else "disabled")
            self.plan_browse_button.configure(state="normal" if needs_plan else "disabled")
            self.plan_reload_button.configure(state="normal" if needs_plan else "disabled")
            self.job_combo.configure(state="readonly" if needs_plan else "disabled")
            self.target_entry.configure(state="normal" if needs_plan else "disabled")
            self.seed_entry.configure(state="normal" if needs_seeds else "disabled")
        self.update_job_info()

    def update_job_info(self) -> None:
        lines: list[str] = []
        if self.managed and self.managed_context:
            c = self.managed_context
            lines.extend([
                f"Runtime: {c.get('runtime_id', '-')}",
                f"Authorization: {c.get('authorization_id', '-')} ({c.get('verification_status', '-')})",
                f"Design: {c.get('design_mode', '-')}",
                f"Search job: {c.get('search_job_id', '-')}",
                f"Target regime: {c.get('target_regime', '-')}",
                f"Search mode: {c.get('search_mode', '-')}",
                "",
                "Reference / seed rules:",
                "  " + ", ".join(normalize_rule_id(x) for x in (c.get("reference_rules") or [])),
                "",
                "Budget:",
            ])
            budget = c.get("budget") or {}
            lines.extend([
                f"  population: {budget.get('population', '-')}",
                f"  generations: {budget.get('generations', '-')}",
                f"  candidate evaluation slots: {budget.get('candidate_evaluation_slots', '-')}",
                "",
                "Mutation branch:",
                f"  {(c.get('mutation_branch') or {}).get('execution_mode') or (c.get('mutation_branch') or {}).get('mode') or 'separate'}",
                "",
                "Managed mode policy:",
                "  Scientific parameters are read-only.",
                "  Observer Queue is forbidden for this runtime.",
                "  Start / pause / resume are owned by Search Launcher v2.",
            ])
        else:
            mode = self.search_mode_var.get()
            job = self.jobs_by_id.get(self.job_id_var.get())
            if mode in {"cohort_target", "counterexample"} and job:
                lines.extend([
                    f"Job: {job.get('id', '-')}",
                    f"Claim: {job.get('claim_id', '-')}",
                    f"Target regime: {job.get('target_regime', '-')}",
                    f"Priority: {job.get('priority', '-')}",
                    "",
                    "Constraints:",
                ])
                for key, value in (job.get("constraints") or {}).items():
                    lines.append(f"  {key}: {value}")
                lines.extend(["", "Seed rules: " + ", ".join(normalize_rule_id(x) for x in (job.get("seed_rules") or []))])
            else:
                lines.append(MODE_HELP.get(mode, ""))
        text = "\n".join(lines)
        self.job_info.configure(state="normal")
        self.job_info.delete("1.0", "end")
        self.job_info.insert("1.0", text)
        self.job_info.configure(state="disabled")

    def parsed_seed_rules(self) -> list[str]:
        raw = self.seed_rules_var.get().replace(",", " ")
        out: list[str] = []
        for token in raw.split():
            rid = normalize_rule_id(token)
            if rid and rid not in out:
                out.append(rid)
        return out

    def build_command(self, run_command: str = "evolve") -> list[str]:
        if self.managed and self.managed_context:
            command = [str(x) for x in (self.managed_context.get("command") or [])]
            if run_command == "resume" and len(command) >= 4 and command[3] == "evolve":
                command[3] = "resume"
            return command
        command = [*runtime_python_command(PROJECT_ROOT), "-u", str(SEARCH_SCRIPT), run_command, self.score_mode_var.get(), "--search-mode", self.search_mode_var.get()]
        mode = self.search_mode_var.get()
        if mode in {"cohort_target", "counterexample"}:
            plan = self.plan_path_var.get().strip()
            if plan:
                command.extend(["--experiment-plan", plan])
            job_id = self.job_id_var.get().strip()
            target = self.target_var.get().strip()
            if job_id:
                command.extend(["--search-job", job_id])
            elif target:
                command.extend(["--target-regime", target])
        if mode in {"diversity", "cohort_target", "counterexample", "local_around_rule"}:
            for rid in self.parsed_seed_rules():
                command.extend(["--seed-rule", rid])
        return command

    def update_command_preview(self) -> None:
        command = self.build_command("evolve")
        text = " ".join(shlex.quote(part) for part in command)
        self.command_var.set(text)
        self.command_text.configure(state="normal")
        self.command_text.delete("1.0", "end")
        self.command_text.insert("1.0", text)
        self.command_text.configure(state="disabled")

    # --------------------------------------------------------- managed mode
    def _initialize_managed_mode(self) -> None:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from Analyzer_next.adapters.observer.cohort_search_execution_handoff import CohortSearchExecutionHandoff
        self.managed_handoff = CohortSearchExecutionHandoff(PROJECT_ROOT)
        self._refresh_managed_context(replay_log=True)

    def _refresh_managed_context(self, *, replay_log: bool = False) -> None:
        assert self.managed_handoff is not None and self.managed_runtime is not None
        self.managed_context = self.managed_handoff.managed_launcher_context(self.managed_runtime)
        c = self.managed_context
        self.score_mode_var.set(str(c.get("score_mode") or "observer_niches"))
        self.search_mode_var.set(str(c.get("search_mode") or "cohort_target"))
        self.plan_path_var.set(str(c.get("experiment_plan_path") or ""))
        self.job_id_var.set(str(c.get("search_job_id") or ""))
        self.target_var.set(str(c.get("target_regime") or ""))
        seeds = c.get("seed_rules") or c.get("reference_rules") or []
        self.seed_rules_var.set(", ".join(normalize_rule_id(x) for x in seeds))
        self.managed_pid = int(c["pid"]) if c.get("pid") is not None else None
        budget = c.get("budget") or {}
        generations = int(budget.get("generations") or 0)
        population = int(budget.get("population") or 0)
        if replay_log:
            self.progress_tracker.reset(generations=generations, population=population)
        elif not self.progress_tracker.snapshot.generations:
            self.progress_tracker.reset(generations=generations, population=population)
        drift = [str(item) for item in (c.get("live_contract_drift") or []) if str(item)]
        self.managed_status_var.set("Authorization VERIFIED")
        if drift and c.get("historical_monitoring_safe"):
            self.managed_detail_var.set(
                f"{c.get('runtime_id')}  •  {c.get('authorization_id')}\n"
                "Historical execution is safe to monitor. Current Search files changed after dispatch; "
                "fresh start/resume remains fail-closed."
            )
        elif drift:
            self.managed_detail_var.set(
                f"{c.get('runtime_id')}  •  {c.get('authorization_id')}\n"
                f"Pinned contract drift detected: {', '.join(drift)}. Start/resume will be refused until rematerialized."
            )
        else:
            self.managed_detail_var.set(
                f"{c.get('runtime_id')}  •  {c.get('authorization_id')}\n"
                "Parameters are locked by ARCHON. Observer Queue is not used."
            )
        mutation = c.get("mutation_branch") or {}
        mutation_text = mutation.get("execution_mode") or mutation.get("mode") or "SEPARATE"
        self.summary_var.set(
            f"Budget     {population} × {generations} = {budget.get('candidate_evaluation_slots', population * generations or '—')} slots\n"
            f"Reference  {len(c.get('reference_rules') or [])} rule(s)\n"
            f"Target     {c.get('target_regime') or '—'}\n"
            f"Mutation   {mutation_text}"
        )
        self.update_mode_ui()
        self.update_command_preview()
        self._update_managed_buttons()
        self.update_job_info()
        if replay_log:
            self._attach_managed_log(replay=True)
        self._render_progress()

    def _update_managed_buttons(self) -> None:
        if not self.managed:
            return
        status = str(self.managed_context.get("runtime_status") or "")
        alive = pid_is_alive(self.managed_pid)
        completed = bool(self.managed_context.get("execution_completed") or status == "SEARCH_EXECUTION_COMPLETED")
        if completed:
            self.launch_button.configure(text="Search Completed", state="disabled")
            self.resume_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            scientific = self.managed_context.get("scientific_status") or "COMPLETED"
            self.status_var.set(f"Completed • {scientific}")
        elif status == "SEARCH_LAUNCH_AUTHORIZED":
            self.launch_button.configure(text="Start Authorized Search", state="normal")
            self.resume_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self.status_var.set("Authorized • ready to start")
        elif status == "SEARCH_EXECUTION_STARTED" and alive:
            self.launch_button.configure(text="Search Running", state="disabled")
            self.resume_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.status_var.set(f"Running • PID {self.managed_pid}")
        elif status == "SEARCH_EXECUTION_STARTED":
            self.launch_button.configure(text="Search Paused / Stopped", state="disabled")
            self.resume_button.configure(state="normal" if DEFAULT_CHECKPOINT.exists() else "disabled")
            self.stop_button.configure(state="disabled")
            self.status_var.set("Paused or stopped • checkpoint can be inspected")

    def _attach_managed_log(self, *, replay: bool) -> None:
        value = self.managed_context.get("log_path")
        self.managed_log_path = Path(str(value)).expanduser() if value else None
        self.managed_log_offset = 0
        if not self.managed_log_path or not self.managed_log_path.exists():
            return
        if replay:
            raw = self.managed_log_path.read_bytes()
            self.managed_log_offset = len(raw)
            text = raw.decode("utf-8", errors="replace")
            self.progress_tracker.feed_text(text)
            self.append_output(text, clear=True)

    def _read_managed_log_delta(self) -> None:
        path = self.managed_log_path
        if path is None or not path.exists():
            return
        try:
            with path.open("rb") as handle:
                handle.seek(self.managed_log_offset)
                raw = handle.read()
                self.managed_log_offset = handle.tell()
        except OSError:
            return
        if not raw:
            return
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines():
            self.progress_tracker.feed_line(line)
        self.append_output(text)
        self._render_progress()

    def poll_managed_execution(self) -> None:
        if self.managed and self.winfo_exists():
            self._read_managed_log_delta()
            if self.managed_context:
                alive = pid_is_alive(self.managed_pid)
                snap = self.progress_tracker.snapshot
                if not alive and str(self.managed_context.get("runtime_status") or "") == "SEARCH_EXECUTION_STARTED":
                    if snap.complete or (self.managed_context.get("outcome_path") and Path(str(self.managed_context["outcome_path"])).exists()):
                        self._reconcile_managed_completion()
                    else:
                        self._update_managed_buttons()
                elif alive:
                    self._update_managed_buttons()
        try:
            self.after(500, self.poll_managed_execution)
        except tk.TclError:
            pass

    def _reconcile_managed_completion(self) -> None:
        if self.managed_reconciled or not self.managed_runtime:
            return
        try:
            from Analyzer_next.adapters.observer.cohort_search_postsearch import CohortSearchPostSearchReconciler
            result = CohortSearchPostSearchReconciler(PROJECT_ROOT).reconcile(self.managed_runtime)
            self.managed_reconciled = True
            self.status_var.set(f"Completed • {result.get('scientific_status')}")
            self._refresh_managed_context(replay_log=False)
        except Exception as exc:
            self.status_var.set(f"Search complete • POSTSEARCH reconcile pending: {exc}")

    def _render_progress(self) -> None:
        snap = self.progress_tracker.snapshot
        overall = max(0.0, min(1.0, snap.overall_fraction))
        self.progress_bar["value"] = overall * 100.0
        self.progress_percent_var.set(f"{overall * 100.0:.1f}%")
        if snap.complete:
            self.progress_title_var.set("Search complete")
        elif snap.generation:
            self.progress_title_var.set(f"Generation {snap.generation} of {snap.generations}")
        else:
            self.progress_title_var.set("Waiting for Search progress")
        self.generation_var.set(f"{snap.generation} / {snap.generations}")
        self.evaluated_var.set(f"{snap.evaluated} / {snap.population}")
        self.failed_var.set(str(snap.failed))
        execution_completed = bool(
            self.managed_context
            and (
                self.managed_context.get("execution_completed")
                or str(self.managed_context.get("runtime_status") or "") == "SEARCH_EXECUTION_COMPLETED"
            )
        )
        workers_label, eta_label = progress_display_labels(
            snap, execution_completed=execution_completed
        )
        self.workers_var.set(workers_label)
        self.elapsed_var.set(format_duration(snap.elapsed_seconds))
        self.eta_var.set(eta_label)
        overall_rule = snap.best_ever_rule or snap.overall_rule or "—"
        target_rule = snap.target_rule or "—"
        self.champions_var.set(
            f"Overall Champion: {overall_rule}    Target Champion: {target_rule}    Exact Target Matches: {snap.exact_matches}"
        )
        scientific = self.managed_context.get("scientific_status") if self.managed_context else None
        if scientific:
            reason = self.managed_context.get("scientific_reason") or ""
            self.scientific_var.set(f"Scientific outcome: {scientific}" + (f" • {reason}" if reason else ""))
        elif snap.target_rule:
            cov = "—" if snap.target_coverage is None else f"{snap.target_coverage:.2f}"
            dist = "—" if snap.target_distance is None else f"{snap.target_distance:.2f}"
            self.scientific_var.set(f"Target status: coverage={cov} • distance={dist} • final outcome pending")
        else:
            self.scientific_var.set("Scientific outcome: pending")

    # ----------------------------------------------------------- execution
    def validate_launch(self) -> bool:
        if not SEARCH_SCRIPT.exists():
            messagebox.showerror("Search Script Missing", f"File not found:\n{SEARCH_SCRIPT}", parent=self)
            return False
        if self.managed:
            return str(self.managed_context.get("runtime_status") or "") == "SEARCH_LAUNCH_AUTHORIZED"
        mode = self.search_mode_var.get()
        if mode in {"cohort_target", "counterexample"}:
            plan = Path(self.plan_path_var.get()).expanduser()
            if not plan.exists():
                messagebox.showerror("Experiment Plan Missing", f"File not found:\n{plan}", parent=self)
                return False
            if not self.job_id_var.get().strip() and not self.target_var.get().strip():
                messagebox.showerror("Search Job Missing", "Select a Search job or target regime.", parent=self)
                return False
            selected_job = self.job_id_var.get().strip()
            if selected_job and selected_job not in self.jobs_by_id:
                messagebox.showerror("Search Job Missing", "Selected Search job is no longer present in the loaded plan.", parent=self)
                return False
        if mode == "local_around_rule" and not self.parsed_seed_rules():
            messagebox.showerror("Seed Rules Missing", "local_around_rule requires at least one seed rule.", parent=self)
            return False
        return True

    def launch_search(self) -> None:
        if self.managed:
            self.start_managed_search()
        else:
            self.start_search_process("evolve")

    def start_managed_search(self) -> None:
        if not self.validate_launch() or not self.managed_handoff or not self.managed_runtime:
            return
        if not ask_yes_no_english(
            self,
            "Start Authorized Search",
            f"Start the pinned ARCHON Search?\n\nRuntime: {self.managed_runtime}\n"
            f"Job: {self.managed_context.get('search_job_id')}\nTarget: {self.managed_context.get('target_regime')}\n\n"
            "Observer Queue will not be used. Scientific parameters cannot be edited in managed mode.",
        ):
            return
        try:
            result = self.managed_handoff.start_authorized_search(
                self.managed_runtime,
                requested_by=os.environ.get("USER") or os.environ.get("USERNAME") or "human",
            )
        except Exception as exc:
            messagebox.showerror("Search Start Refused", str(exc), parent=self)
            return
        self.managed_log_path = Path(str(result.log_path)).expanduser() if result.log_path else None
        self.managed_log_offset = 0
        self.managed_pid = result.pid
        self.managed_pause_requested = False
        self.managed_reconciled = False
        budget = self.managed_context.get("budget") or {}
        self.progress_tracker.reset(generations=int(budget.get("generations") or 0), population=int(budget.get("population") or 0))
        self.append_output(f"\n[Launcher] {result.message}\n", clear=True)
        self._refresh_managed_context(replay_log=False)
        self._attach_managed_log(replay=False)
        self.notebook.select(self.launch_tab)

    def resume_search(self) -> None:
        if self.managed:
            self.resume_managed_search()
            return
        checkpoint = DEFAULT_CHECKPOINT
        if not checkpoint.exists():
            messagebox.showerror("Checkpoint Missing", f"Checkpoint not found:\n{checkpoint}", parent=self)
            return
        payload = read_json(checkpoint, {})
        try:
            resume_config = checkpoint_resume_config(payload)
        except ValueError as exc:
            messagebox.showerror("Invalid Checkpoint", f"Cannot restore Search configuration:\n{exc}", parent=self)
            return
        score_mode = resume_config["score_mode"]
        search_mode = resume_config["search_mode"]
        job_id = resume_config["job_id"]
        if score_mode not in detect_score_modes():
            messagebox.showerror("Checkpoint Score Mode Missing", f"Checkpoint requires score mode {score_mode}.", parent=self)
            return
        if search_mode in {"cohort_target", "counterexample"}:
            self.load_experiment_plan(silent=True)
            if not job_id or job_id not in self.jobs_by_id:
                messagebox.showerror("Checkpoint Search Job Missing", f"Checkpoint requires Search job {job_id or 'unknown'}.", parent=self)
                return
        self.score_mode_var.set(score_mode)
        self.search_mode_var.set(search_mode)
        self.job_id_var.set(job_id)
        self.target_var.set(resume_config["target_regime"])
        self.seed_rules_var.set(", ".join(resume_config["seed_rules"]))
        self.previous_search_mode = search_mode
        self.update_mode_ui()
        self.update_job_info()
        self.update_command_preview()
        self.status_var.set("Checkpoint restored")
        self.append_output(f"\n[Launcher] Restored checkpoint configuration: score={score_mode} mode={search_mode} job={job_id or '-'}\n")
        self.start_search_process("resume")

    def resume_managed_search(self) -> None:
        if not self.managed_handoff or not self.managed_runtime:
            return
        if pid_is_alive(self.managed_pid):
            messagebox.showinfo("Search Running", "Search is still running and cannot be resumed.", parent=self)
            return
        if not DEFAULT_CHECKPOINT.exists():
            messagebox.showerror("Checkpoint Missing", f"Checkpoint not found:\n{DEFAULT_CHECKPOINT}", parent=self)
            return
        if not ask_yes_no_english(
            self,
            "Resume Authorized Search",
            "Resume this managed Search from its verified checkpoint?\n\nOnly the evolve → resume verb is allowed to change; the authorized scientific contract remains pinned.",
        ):
            return
        try:
            result = self.managed_handoff.resume_authorized_search(
                self.managed_runtime,
                requested_by=os.environ.get("USER") or os.environ.get("USERNAME") or "human",
            )
        except Exception as exc:
            messagebox.showerror("Managed Resume Refused", str(exc), parent=self)
            return
        self.managed_pid = result.pid
        self.managed_log_path = Path(str(result.log_path)).expanduser() if result.log_path else None
        self.managed_log_offset = 0
        self.managed_pause_requested = False
        self.append_output(f"\n[Launcher] {result.message}\n", clear=True)
        self._refresh_managed_context(replay_log=False)
        self._attach_managed_log(replay=False)

    def start_search_process(self, run_command: str) -> None:
        if self.process is not None:
            messagebox.showinfo("Search Already Running", "A Search process is already running.", parent=self)
            return
        if not self.validate_launch():
            return
        self.active_command = run_command
        command = self.build_command(run_command)
        self.append_output("\n" + "=" * 80 + "\nLaunching:\n" + " ".join(shlex.quote(x) for x in command) + "\n" + "=" * 80 + "\n")
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(x for x in (str(PROJECT_ROOT), env.get("PYTHONPATH", "")) if x)
        try:
            self.process = subprocess.Popen(command, cwd=str(PROJECT_ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as exc:
            self.process = None
            messagebox.showerror("Launch Failed", repr(exc), parent=self)
            return
        self.launch_button.configure(state="disabled")
        self.resume_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set(f"Search started, PID {self.process.pid}")
        self.progress_tracker.reset()
        threading.Thread(target=self._read_process_output, daemon=True).start()

    def _read_process_output(self) -> None:
        process = self.process
        if process is None:
            return
        try:
            assert process.stdout is not None
            for line in process.stdout:
                self.output_queue.put(line)
            return_code = process.wait()
            self.output_queue.put(f"\n[Search exited with code {return_code}]\n")
        except Exception as exc:
            self.output_queue.put(f"\n[Launcher output error: {exc!r}]\n")
        finally:
            self.output_queue.put("__PROCESS_FINISHED__")

    def poll_output_queue(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if item == "__PROCESS_FINISHED__":
                    self.process = None
                    if not self.managed:
                        self.launch_button.configure(state="normal")
                        self.resume_button.configure(state="normal")
                        self.stop_button.configure(state="disabled")
                    self.status_var.set("Search finished or paused")
                    if self.close_when_process_finishes:
                        self.destroy()
                        return
                else:
                    for line in item.splitlines():
                        self.progress_tracker.feed_line(line)
                    self.append_output(item)
                    self._render_progress()
        except queue.Empty:
            pass
        try:
            self.after(100, self.poll_output_queue)
        except tk.TclError:
            pass

    def append_output(self, text: str, *, clear: bool = False) -> None:
        self.output.configure(state="normal")
        if clear:
            self.output.delete("1.0", "end")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def stop_search(self) -> None:
        if os.name == "nt":
            messagebox.showwarning("Pause unsupported", "Safe checkpoint pause is not supported on Windows yet. Studio Stop forcibly terminates the process and cannot promise a saved checkpoint.", parent=self)
            return
        if self.managed:
            if not pid_is_alive(self.managed_pid):
                return
            if not ask_yes_no_english(
                self,
                "Pause Search",
                "Pause the managed Search safely? Active evaluations in the incomplete generation are discarded and a checkpoint is saved.",
            ):
                return
            try:
                os.kill(int(self.managed_pid), signal.SIGTERM)
                self.managed_pause_requested = True
                self.stop_button.configure(state="disabled")
                self.status_var.set("Pause requested • saving safe checkpoint")
                self.append_output("\n[Launcher] Pause requested. Waiting for safe checkpoint...\n")
            except Exception as exc:
                messagebox.showerror("Pause Failed", repr(exc), parent=self)
            return
        if self.process is None:
            return
        if not ask_yes_no_english(
            self,
            "Pause Search",
            "Search will stop active evaluations, discard only the incomplete generation, and save a checkpoint. Resume will restart that generation.\n\nPause Search?",
        ):
            return
        try:
            self.process.terminate()
            self.stop_button.configure(state="disabled")
            self.status_var.set("Pause requested: stopping evaluations safely")
        except Exception as exc:
            messagebox.showerror("Pause Failed", repr(exc), parent=self)

    def on_window_close(self) -> None:
        """Protect standalone Search; managed Search survives launcher closure."""
        if self.managed and pid_is_alive(self.managed_pid):
            confirmed = ask_yes_no_english(
                self,
                "Close Search Launcher?",
                "Universe Search is still running. Closing this window will NOT stop it. You can reopen Search Launcher from Observer Launcher and reconnect to the same runtime.\n\nClose launcher?",
            )
            if confirmed:
                self.destroy()
            return
        if self.process is not None:
            if self.close_when_process_finishes:
                return
            confirmed = ask_yes_no_english(
                self,
                "Close Search Launcher?",
                ("Windows will forcibly terminate Search. A saved checkpoint and descendant cleanup are not guaranteed. Close Search?" if os.name == "nt" else "Search is currently running.\n\nClosing will stop active evaluations, discard only the incomplete generation, save a safe checkpoint, and then close the window. Resume will restart that generation.\n\nDo you really want to close Search?"),
                warning=True,
            )
            if not confirmed:
                return
            self.close_when_process_finishes = True
            try:
                self.process.terminate()
                self.launch_button.configure(state="disabled")
                self.resume_button.configure(state="disabled")
                self.stop_button.configure(state="disabled")
                self.status_var.set("Windows forced stop requested" if os.name == "nt" else "Stopping evaluations and saving a safe checkpoint")
                self.append_output("\n[Launcher] Windows forced stop; checkpoint not guaranteed.\n" if os.name == "nt" else "\n[Launcher] Close requested. Stopping active evaluations and saving the checkpoint...\n")
            except Exception as exc:
                self.close_when_process_finishes = False
                messagebox.showerror("Could Not Pause Search", repr(exc), parent=self)
            return
        if not self.confirm_close or ask_yes_no_english(self, "Close Search Launcher?", "Do you really want to close Search Launcher?"):
            self.destroy()

    def copy_command(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.command_var.get())
        self.status_var.set("Command copied")

    def open_run_folder(self) -> None:
        folder = PROJECT_ROOT / "Results" / "Universe_Search" / "search_runs"
        if self.managed and self.managed_context.get("log_path"):
            folder = Path(str(self.managed_context["log_path"])).expanduser().parent
        folder.mkdir(parents=True, exist_ok=True)
        try:
            open_folder(folder)
        except Exception as exc:
            messagebox.showerror("Open Folder Failed", repr(exc), parent=self)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project ARCHON Search Launcher v2.0")
    parser.add_argument("--managed-runtime", default="", help="Open a VERIFIED BRIDGE4 Search runtime in managed mode")
    parser.add_argument("--theme", choices=("auto", "dark", "light"), default="auto")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    app = SearchLauncher(managed_runtime=args.managed_runtime or None, theme=args.theme)
    app.mainloop()


if __name__ == "__main__":
    main()
