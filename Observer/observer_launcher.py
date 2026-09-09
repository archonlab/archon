#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project ARCHON Observer Launcher v3.2.

Tabbed English laboratory UI for canonical Observer runs and isolated mutations.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import queue
import secrets
import shlex
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
_TELEMETRY_ROOT = _BOOTSTRAP_ROOT / "Telemetry"

for _bootstrap_path in (_TELEMETRY_ROOT, _BOOTSTRAP_ROOT):
    _bootstrap_text = str(_bootstrap_path)
    if _bootstrap_text in sys.path:
        sys.path.remove(_bootstrap_text)
    sys.path.insert(0, _bootstrap_text)

from archon_paths import (
    ANALYSIS_RESULTS_DIR,
    KNOWLEDGE_ATLAS_DIR,
    OBSERVER_DIR,
    PROJECT_ROOT,
    SEARCH_RESULTS_DIR,
    WORLD_ATLAS_DIR,
    ensure_layout,
)
from Observer.observer_mutation_engine import (
    PRESETS,
    capture_baseline_provenance,
    create_mutation_run,
    parameter_choices,
)
from Analyzer_next.adapters.telemetry.experimental_conditions_routing import (
    ExperimentalConditionsError,
    ExperimentalConditionsRepository,
    ExperimentPlan,
    ExperimentPlanItem,
    ExperimentRole,
    InitialStateMode,
)
from Tools.archon_runtime_python import runtime_python_command, runtime_python_environment
from Analyzer_next.production.runtime_routes import (
    COMPATIBILITY_ROOT,
    cli_route,
    compatibility_route,
)

VERSION = "Project ARCHON Observer Laboratory v3.5.6"
OBSERVER_SCRIPT = (
    OBSERVER_DIR / "universe_search_observer_v441_validation_calibration.py"
)
MUTATION_ROOT = SEARCH_RESULTS_DIR / "mutation_runs"
HISTORY_FILE = MUTATION_ROOT / "launcher_history.json"
REQUIRED_CONTROLS_FILE = (
    ANALYSIS_RESULTS_DIR / "Mutations" / "required_controls.json"
)
CONTROL_RUN_ROOT = SEARCH_RESULTS_DIR / "required_control_runs"
CONTROL_RESOLUTION_FILENAME = "required_control_resolution.json"
TELEMETRY_DATABASE = (
    SEARCH_RESULTS_DIR / "observation_logs" / "telemetry.sqlite"
)
EXPERIMENTS_ROOT = ANALYSIS_RESULTS_DIR / "Experiments"
RESEARCH_CYCLE_RECORDS_ROOT = (
    EXPERIMENTS_ROOT / "ResearchCycleRecords"
)
RESEARCH_CYCLE_INDEX_FILE = (
    RESEARCH_CYCLE_RECORDS_ROOT / "research_cycle_index.json"
)
RUNTIME_REGISTRY_FILE = EXPERIMENTS_ROOT / "experiment_runtime_registry.json"
LAUNCH_AUTHORIZATION_REGISTRY_FILE = (
    EXPERIMENTS_ROOT / "launch_authorization_registry.json"
)
MANUAL_PLAN_REGISTRY_FILE = (
    EXPERIMENTS_ROOT / "manual_experiment_plan_registry.json"
)
MANUAL_RUNTIME_ROOT = EXPERIMENTS_ROOT / "ManualRuntimePackages"
LAUNCH_AUTHORIZATION_MODULE = (
    compatibility_route("experiment_launch_authorization.py")
)

AUTOMATED_RESEARCH_POLICY_FILE = (
    EXPERIMENTS_ROOT / "observer_automated_research_policy.json"
)
RESEARCH_DIRECTOR_REPORT_FILE = ANALYSIS_RESULTS_DIR / "research_director_report.json"
HUMAN_REVIEW_DECISIONS_FILE = ANALYSIS_RESULTS_DIR / "human_review_decisions.json"
HUMAN_REVIEW_IMPORT_CANDIDATE_FILE = (
    ANALYSIS_RESULTS_DIR / "human_review_import_candidate.json"
)
HUMAN_REVIEW_EDITING_INTERFACE_FILE = (
    ANALYSIS_RESULTS_DIR / "human_review_editing_interface.json"
)
HUMAN_REVIEW_COMMIT_MANIFEST_FILE = (
    ANALYSIS_RESULTS_DIR / "human_review_commit_manifest.json"
)
HUMAN_REVIEW_COMMIT_REQUEST_FILE = (
    ANALYSIS_RESULTS_DIR / "human_review_commit_request.json"
)
HUMAN_REVIEW_COMMIT_RESULT_FILE = (
    ANALYSIS_RESULTS_DIR / "human_review_commit_result.json"
)
HUMAN_REVIEW_RECEIPT_VERIFICATION_FILE = (
    ANALYSIS_RESULTS_DIR / "human_review_receipt_verification.json"
)
PATCH_APPLICATION_MANIFEST_FILE = (
    ANALYSIS_RESULTS_DIR / "patch_application_manifest.json"
)
PATCH_APPLICATION_REQUEST_FILE = (
    ANALYSIS_RESULTS_DIR / "patch_application_request.json"
)
PATCH_APPLICATION_RESULT_FILE = (
    ANALYSIS_RESULTS_DIR / "patch_application_result.json"
)
PATCH_APPLICATION_RECEIPT_VERIFICATION_FILE = (
    ANALYSIS_RESULTS_DIR / "patch_application_receipt_verification.json"
)
PATCH_LIFECYCLE_CLOSURE_FILE = (
    ANALYSIS_RESULTS_DIR / "patch_lifecycle_closure.json"
)
RESEARCH_DIRECTOR_MODULE = cli_route("research_director.py")
PLANNER_REVIEW_EDITOR_FILE = EXPERIMENTS_ROOT / "experiment_planner_review_editor.json"
ANALYZER_ENTRYPOINT = cli_route("analyze_results.py")
PRODUCTION_RESEARCH_CYCLE_OWNER = cli_route(
    "production_research_cycle_orchestrator.py"
)
PRODUCTION_LAUNCHER_HANDOFF = cli_route(
    "production_research_cycle_launcher_handoff.py"
)
PRODUCTION_RUNTIME_RECOVERY = (
    PROJECT_ROOT / "Analyzer_next/compatibility/legacy_analyzer" / "production_runtime_recovery.py"
)
SCIENTIFIC_TARGET_RESOLVER = cli_route("scientific_target_resolver.py")
SCIENTIFIC_PROTOCOL_RESOLVER = cli_route("scientific_protocol_resolver.py")
AUTOMATED_STAGE_MODULES = (
    ("Planner intake", cli_route("approved_action_planner_intake_compat.py")),
    ("Planner drafts", cli_route("experiment_planner_review.py")),
    ("Plan commit", cli_route("experiment_plan_commit.py")),
    ("Scientific target resolver", SCIENTIFIC_TARGET_RESOLVER),
    ("Scientific protocol resolver", SCIENTIFIC_PROTOCOL_RESOLVER),
    ("Runtime materialization", cli_route("experiment_runtime_materializer.py")),
    ("Launch authorization", compatibility_route("experiment_launch_authorization.py")),
    ("Execution dispatch", compatibility_route("experiment_execution_dispatch.py")),
    ("Runtime recovery", PRODUCTION_RUNTIME_RECOVERY),
    ("Production handoff", PRODUCTION_LAUNCHER_HANDOFF),
    ("Production owner", PRODUCTION_RESEARCH_CYCLE_OWNER),
)

SPEED_VALUES = list(range(1, 11)) + list(range(20, 101, 10)) + [
    200, 500, 1000
]


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_research_cycle_catalog(
    records_root: Path = RESEARCH_CYCLE_RECORDS_ROOT,
) -> dict[str, Any]:
    records_root = Path(records_root)
    index_path = records_root / "research_cycle_index.json"
    records_dir = records_root / "records"
    index = read_json(index_path, {})
    if not isinstance(index, dict):
        index = {}
    index_rows = [
        row
        for row in index.get("records", [])
        if isinstance(row, dict)
    ]
    index_verified = bool(
        index
        and index.get("content_hash")
        and index.get("content_hash") == canonical_hash(index_rows)
    )

    records: list[dict[str, Any]] = []
    invalid_count = 0
    missing_count = 0
    for index_row in index_rows:
        cycle_id = str(index_row.get("cycle_id") or "").strip()
        if not cycle_id or not all(
            character.isalnum() or character in "_.-"
            for character in cycle_id
        ):
            invalid_count += 1
            continue
        record_path = records_dir / f"{cycle_id}.json"
        record = read_json(record_path, {})
        if not isinstance(record, dict) or not record:
            missing_count += 1
            records.append(
                {
                    **index_row,
                    "cycle_id": cycle_id,
                    "current_stage": (
                        index_row.get("current_stage")
                        or "RECORD_MISSING"
                    ),
                    "next_required_action": "REBUILD_CYCLE_RECORDS",
                    "receipt_integrity": "NOT_VERIFIED",
                    "blockers": ["AUTHORITATIVE_RECORD_MISSING"],
                    "record_verified": False,
                    "record_path": str(record_path),
                }
            )
            continue

        declared_hash = record.get("record_hash")
        record_core = {
            key: value
            for key, value in record.items()
            if key != "record_hash"
        }
        record_verified = bool(
            declared_hash
            and declared_hash == canonical_hash(record_core)
            and declared_hash == index_row.get("record_hash")
        )
        if not record_verified:
            invalid_count += 1
        records.append(
            {
                **record,
                "record_verified": record_verified,
                "record_path": str(record_path),
            }
        )

    records.sort(
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )
    return {
        "available": bool(index),
        "index_path": str(index_path),
        "index_verified": index_verified,
        "count": len(records),
        "blocked_count": sum(
            1 for record in records if record.get("blockers")
        ),
        "invalid_count": invalid_count,
        "missing_count": missing_count,
        "records": records,
    }


def normalize_rule_id(value: Any) -> str:
    try:
        return f"{int(value):05d}"
    except Exception:
        return str(value)


def format_score(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else ""


def open_path(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        messagebox.showwarning("Path not found", str(path))
        return
    try:
        subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        messagebox.showerror("Could not open path", repr(exc))


def find_rule_file(rule_id: int) -> Path | None:
    matches = sorted(
        WORLD_ATLAS_DIR.rglob(f"rule_{rule_id:05d}_*/rule.json")
    )
    return matches[0] if matches else None


def observation_summary(rule_id: int) -> dict[str, Any]:
    logs = SEARCH_RESULTS_DIR / "observation_logs"
    candidates = []
    if logs.exists():
        candidates = sorted(
            logs.glob(f"rule_{rule_id:05d}_*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    mutation_base = MUTATION_ROOT / f"rule_{rule_id:05d}"
    mutation_dirs = (
        sorted(
            [p for p in mutation_base.glob("MUT-*") if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if mutation_base.exists()
        else []
    )
    latest_time = None
    paths = candidates + mutation_dirs
    if paths:
        latest_time = datetime.fromtimestamp(
            max(p.stat().st_mtime for p in paths)
        )
    return {
        "observed": bool(candidates),
        "observation_files": len(candidates),
        "mutation_runs": len(mutation_dirs),
        "last_run": (
            latest_time.strftime("%Y-%m-%d %H:%M")
            if latest_time else "-"
        ),
    }


def load_rules() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    index_path = WORLD_ATLAS_DIR / "atlas_index.json"
    index = read_json(index_path, [])

    if isinstance(index, list):
        for entry in index:
            if not isinstance(entry, dict):
                continue
            try:
                rid = int(entry.get("rule_id"))
            except Exception:
                continue
            metrics = entry.get("metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}
            folder = entry.get("folder")
            rows.append({
                "rule_id": rid,
                "score": entry.get("score", metrics.get("score")),
                "class": entry.get(
                    "class",
                    metrics.get("class", metrics.get("world_class", "")),
                ),
                "folder": folder,
                "genome_hash": entry.get("key") or entry.get("genome_hash"),
                "parents": (
                    entry.get("parent_a"),
                    entry.get("parent_b"),
                ),
            })

    if not rows:
        for rule_file in WORLD_ATLAS_DIR.rglob("rule.json"):
            payload = read_json(rule_file, {})
            if not isinstance(payload, dict):
                continue
            try:
                rid = int(payload["rule_id"])
            except Exception:
                continue
            rows.append({
                "rule_id": rid,
                "score": None,
                "class": rule_file.parent.parent.name,
                "folder": str(rule_file.parent),
                "genome_hash": rule_file.parent.name.rsplit("_", 1)[-1],
                "parents": (
                    payload.get("parent_a"),
                    payload.get("parent_b"),
                ),
            })

    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        rid = int(row["rule_id"])
        row.update(observation_summary(rid))
        by_id[rid] = row
    return sorted(by_id.values(), key=lambda x: x["rule_id"])


class ObserverLaboratory(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        ensure_layout()
        self.title(VERSION)
        self.geometry("1360x900")
        self.minsize(1100, 760)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.rules = load_rules()
        self.visible_rules = list(self.rules)
        self.selected_rule: dict[str, Any] | None = None

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()

        # batch_queue contains only runs still waiting to launch.
        # queue_runs is the durable visual lifecycle for the active batch:
        # Waiting -> Running -> Completed / Exit N. Finished rows remain visible.
        self.batch_queue: list[dict[str, Any]] = []
        self.queue_runs: list[dict[str, Any]] = []
        self.required_controls: list[dict[str, Any]] = []
        self.current_run: dict[str, Any] | None = None
        self.run_started_at: float | None = None

        self.rule_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.class_filter_var = tk.StringVar(value="All")
        self.status_filter_var = tk.StringVar(value="All")
        self.sort_var = tk.StringVar(value="Rule ID")

        self.speed_var = tk.IntVar(value=2)
        self.speed_text_var = tk.StringVar(value="2x")
        self.delay_var = tk.IntVar(value=30)
        self.cell_var = tk.IntVar(value=8)
        self.max_ticks_var = tk.IntVar(value=100000)
        self.minimum_horizon_var = tk.IntVar(value=100000)
        self.autosave_var = tk.IntVar(value=50000)
        self.sample_every_var = tk.IntVar(value=1)
        self.pressure_every_var = tk.IntVar(value=100)
        self.auto_stop_var = tk.BooleanVar(value=False)

        self.samples_var = tk.BooleanVar(value=True)
        self.events_var = tk.BooleanVar(value=True)
        self.pressure_var = tk.BooleanVar(value=True)
        self.chronicle_var = tk.BooleanVar(value=True)
        self.passport_var = tk.BooleanVar(value=True)
        self.log_var = tk.BooleanVar(value=True)
        self.sqlite_var = tk.BooleanVar(value=True)
        self.evidence_var = tk.BooleanVar(value=True)

        # Experimental Conditions provenance controls. Stage v1 supports the
        # canonical 96x64 torus baseline while preserving the full contract.
        self.experimental_run_var = tk.BooleanVar(value=False)
        self.experiment_var = tk.StringVar()
        self.condition_var = tk.StringVar()
        self.experiment_role_var = tk.StringVar(
            value=ExperimentRole.BASELINE.value
        )
        self.replicate_index_var = tk.IntVar(value=0)
        self.experiment_summary_var = tk.StringVar(
            value="Experimental provenance is disabled."
        )
        self._experiments_by_display: dict[str, Any] = {}
        self._conditions_by_display: dict[str, Any] = {}

        # Experiment Builder v1 state.
        self.plan_replicates_var = tk.IntVar(value=1)
        self.plan_role_var = tk.StringVar(
            value=ExperimentRole.TREATMENT.value
        )
        self.plan_enabled_var = tk.BooleanVar(value=True)
        self.plan_seed_mode_var = tk.StringVar(value="auto")
        self.plan_seed_var = tk.IntVar(value=0)
        self.plan_items: list[dict[str, Any]] = []
        self.plan_summary_var = tk.StringVar(
            value="Plan is empty."
        )
        self.slot_summary_var = tk.StringVar(
            value="Experiment slots have not been refreshed."
        )
        self._slot_rows: dict[str, dict[str, Any]] = {}

        # Production Experiment Queue v1. Runtime packages remain immutable;
        # the launcher only reads verified registries and materializes an
        # executable local queue after explicit human confirmation.
        self.production_summary_var = tk.StringVar(
            value="Production state has not been refreshed."
        )
        self.production_runtime_var = tk.StringVar()
        self._production_packages: dict[str, dict[str, Any]] = {}
        self.research_cycle_summary_var = tk.StringVar(
            value="Authoritative cycle state has not been refreshed."
        )
        self._research_cycles: dict[str, dict[str, Any]] = {}
        self.automated_research_running = False
        self.automated_research_stop = threading.Event()
        self.automated_research_status_var = tk.StringVar(
            value="Automated research queue is idle."
        )
        self.director_summary_var = tk.StringVar(
            value="Director proposals have not been refreshed."
        )

        self.mutation_mode_var = tk.StringVar(value="none")
        self.mutation_parameter_var = tk.StringVar()
        self.mutation_preset_var = tk.StringVar(value="balanced")
        self.mutation_intensity_var = tk.DoubleVar(value=0.50)
        self.mutation_count_var = tk.IntVar(value=1)
        self.mutation_seed_var = tk.IntVar(value=0)
        self.preview_var = tk.StringVar(
            value="Select a rule and mutation mode to preview changes."
        )

        self.command_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.gpu_status_var = tk.StringVar(value="GPU: configured")
        self.sqlite_status_var = tk.StringVar(value="SQLite: enabled")
        self.atlas_status_var = tk.StringVar(
            value=f"Atlas: {len(self.rules)} rules"
        )
        self.queue_status_var = tk.StringVar(value="Queue: 0")
        self.runtime_status_var = tk.StringVar(value="Run time: 00:00:00")

        self._build_style()
        self._build_ui()
        self._refresh_rule_table()
        self._refresh_history()
        self.after(100, self._drain_output)
        self.after(500, self._tick_status)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        # Linux desktop scaling can make Treeview text taller than Tk's
        # default row height, which causes neighboring rules to overlap.
        # Use a deliberately generous row height.
        style.configure("Treeview", rowheight=52)
        style.configure("Treeview.Heading", font=("", 10, "bold"))

        # Give Notebook tabs breathing room. The window has enough horizontal
        # space, so compact default tabs only make navigation harder to scan.
        style.configure(
            "TNotebook.Tab",
            padding=(18, 8),
            font=("", 10, "bold"),
        )

        style.configure("Header.TLabel", font=("", 16, "bold"))
        style.configure("Subheader.TLabel", font=("", 11, "bold"))
        style.configure("Launch.TButton", font=("", 11, "bold"))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="ARCHON Observer Laboratory",
            style="Header.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="Canonical runs, isolated mutations, queue and history",
        ).pack(side="left", padx=(14, 0), pady=(5, 0))

        # Keep the laboratory tabs and terminal output inside a vertical
        # resizable workspace. Large experiment tables must not push the log
        # outside the visible window.
        self.workspace_pane = ttk.Panedwindow(
            root,
            orient="vertical",
        )
        self.workspace_pane.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(self.workspace_pane)
        self.workspace_pane.add(self.notebook, weight=5)

        self.browser_tab = ttk.Frame(self.notebook, padding=8)
        self.run_tab = ttk.Frame(self.notebook, padding=8)
        self.experiments_tab = ttk.Frame(self.notebook, padding=8)
        self.mutation_tab = ttk.Frame(self.notebook, padding=8)
        self.controls_tab = ttk.Frame(self.notebook, padding=8)
        self.queue_tab = ttk.Frame(self.notebook, padding=8)
        self.history_tab = ttk.Frame(self.notebook, padding=8)
        self.settings_tab = ttk.Frame(self.notebook, padding=8)

        self.notebook.add(self.browser_tab, text="Rule Browser")
        self.notebook.add(self.run_tab, text="Run")
        self.notebook.add(self.experiments_tab, text="Experiments")
        self.notebook.add(self.mutation_tab, text="Mutations")
        self.notebook.add(self.controls_tab, text="Required Controls")
        self.notebook.add(self.queue_tab, text="Queue")
        self.notebook.add(self.history_tab, text="History")
        self.notebook.add(self.settings_tab, text="Settings")

        self._build_browser_tab()
        self._build_run_tab()
        self._build_experiments_tab()
        self._build_mutation_tab()
        self._build_controls_tab()
        self._build_queue_tab()
        self._build_history_tab()
        self._build_settings_tab()
        self.refresh_required_controls()

        output_frame = ttk.LabelFrame(
            self.workspace_pane,
            text="Observer Output",
            padding=6,
        )
        self.workspace_pane.add(output_frame, weight=2)

        output_toolbar = ttk.Frame(output_frame)
        output_toolbar.pack(fill="x", pady=(0, 4))
        ttk.Button(
            output_toolbar,
            text="Copy Log",
            command=self.copy_observer_log,
        ).pack(side="right")

        self.output = tk.Text(
            output_frame,
            height=20,
            wrap="word",
            state="disabled",
            font=("monospace", 9),
        )
        output_scroll = ttk.Scrollbar(
            output_frame,
            orient="vertical",
            command=self.output.yview,
        )
        self.output.configure(yscrollcommand=output_scroll.set)
        self.output.pack(side="left", fill="both", expand=True)
        output_scroll.pack(side="right", fill="y")

        status = ttk.Frame(root)
        status.pack(fill="x", pady=(6, 0))
        for variable in (
            self.gpu_status_var,
            self.sqlite_status_var,
            self.atlas_status_var,
            self.queue_status_var,
            self.runtime_status_var,
        ):
            ttk.Label(status, textvariable=variable).pack(
                side="left", padx=(0, 18)
            )
        ttk.Label(
            status,
            textvariable=self.status_var,
        ).pack(side="right")

    def _build_browser_tab(self) -> None:
        pane = ttk.Panedwindow(
            self.browser_tab,
            orient="horizontal",
        )
        pane.pack(fill="both", expand=True)

        table_side = ttk.Frame(pane)
        card_side = ttk.Frame(pane, width=390)
        pane.add(table_side, weight=4)
        pane.add(card_side, weight=2)

        controls = ttk.Frame(table_side)
        controls.pack(fill="x", pady=(0, 6))

        ttk.Label(controls, text="Search").pack(side="left")
        search = ttk.Entry(
            controls,
            textvariable=self.filter_var,
            width=24,
        )
        search.pack(side="left", padx=(6, 12))
        search.bind("<KeyRelease>", lambda _e: self._refresh_rule_table())

        ttk.Label(controls, text="Class").pack(side="left")
        classes = ["All"] + sorted({
            str(r.get("class") or "")
            for r in self.rules
            if str(r.get("class") or "")
        })
        class_combo = ttk.Combobox(
            controls,
            textvariable=self.class_filter_var,
            values=classes,
            state="readonly",
            width=20,
        )
        class_combo.pack(side="left", padx=(6, 12))
        class_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._refresh_rule_table(),
        )

        ttk.Label(controls, text="Status").pack(side="left")
        status_combo = ttk.Combobox(
            controls,
            textvariable=self.status_filter_var,
            values=("All", "Observed", "Not observed", "Has mutations"),
            state="readonly",
            width=15,
        )
        status_combo.pack(side="left", padx=(6, 12))
        status_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._refresh_rule_table(),
        )

        ttk.Label(controls, text="Sort").pack(side="left")
        sort_combo = ttk.Combobox(
            controls,
            textvariable=self.sort_var,
            values=("Rule ID", "Score high", "Score low", "Last run"),
            state="readonly",
            width=13,
        )
        sort_combo.pack(side="left", padx=(6, 12))
        sort_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._refresh_rule_table(),
        )

        ttk.Button(
            controls,
            text="Refresh Atlas",
            command=self.refresh_rules,
        ).pack(side="right")

        queue_controls = ttk.Frame(table_side)
        queue_controls.pack(fill="x", pady=(0, 6))
        ttk.Button(
            queue_controls,
            text="Add Selected to Queue",
            command=self.add_selected_rules_to_queue,
        ).pack(side="left")
        ttk.Button(
            queue_controls,
            text="Add All Visible",
            command=self.add_all_visible_to_queue,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            queue_controls,
            text="Launch Not Observed One by One",
            command=self.launch_not_observed_one_by_one,
            style="Launch.TButton",
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            queue_controls,
            text="Minimum completed horizon",
        ).pack(side="left", padx=(18, 6))
        ttk.Spinbox(
            queue_controls,
            textvariable=self.minimum_horizon_var,
            from_=1,
            to=100_000_000,
            increment=10_000,
            width=12,
        ).pack(side="left")

        columns = (
            "rule", "score", "class", "observed", "mutations", "last"
        )
        self.rule_tree = ttk.Treeview(
            table_side,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        headings = {
            "rule": "Rule",
            "score": "Score",
            "class": "Class",
            "observed": "Observed",
            "mutations": "Mutations",
            "last": "Last run",
        }
        widths = {
            "rule": 90,
            "score": 110,
            "class": 280,
            "observed": 100,
            "mutations": 100,
            "last": 155,
        }
        for key in columns:
            self.rule_tree.heading(key, text=headings[key])
            self.rule_tree.column(
                key,
                width=widths[key],
                anchor="w" if key == "class" else "center",
            )
        self.rule_tree.pack(fill="both", expand=True)
        self.rule_tree.bind(
            "<<TreeviewSelect>>",
            self._on_rule_selected,
        )

        card = ttk.LabelFrame(
            card_side,
            text="Selected Rule",
            padding=12,
        )
        card.pack(fill="both", expand=True, padx=(8, 0))

        self.card_rule = tk.StringVar(value="No rule selected")
        self.card_score = tk.StringVar(value="Score: -")
        self.card_class = tk.StringVar(value="Class: -")
        self.card_parents = tk.StringVar(value="Parents: -")
        self.card_hash = tk.StringVar(value="Genome hash: -")
        self.card_last = tk.StringVar(value="Last run: -")
        self.card_mutations = tk.StringVar(value="Mutation runs: 0")

        ttk.Label(
            card,
            textvariable=self.card_rule,
            style="Header.TLabel",
        ).pack(anchor="w", pady=(0, 12))
        for variable in (
            self.card_score,
            self.card_class,
            self.card_parents,
            self.card_hash,
            self.card_last,
            self.card_mutations,
        ):
            ttk.Label(
                card,
                textvariable=variable,
                wraplength=350,
            ).pack(anchor="w", pady=3)

        ttk.Separator(card).pack(fill="x", pady=12)

        ttk.Button(
            card,
            text="Run Observer",
            command=lambda: self._go_and_launch("run"),
            style="Launch.TButton",
        ).pack(fill="x", pady=3)
        ttk.Button(
            card,
            text="Configure Mutation",
            command=lambda: self.notebook.select(self.mutation_tab),
        ).pack(fill="x", pady=3)
        ttk.Button(
            card,
            text="Open Atlas Folder",
            command=self.open_selected_folder,
        ).pack(fill="x", pady=3)
        ttk.Button(
            card,
            text="Open Mutation Folder",
            command=self.open_selected_mutations,
        ).pack(fill="x", pady=3)

    def _build_run_tab(self) -> None:
        body = ttk.Frame(self.run_tab)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right.pack(side="right", fill="both", expand=True)

        selected = ttk.LabelFrame(
            left, text="Selected World", padding=10
        )
        selected.pack(fill="x", pady=(0, 10))
        self.run_selected_label = tk.StringVar(value="No rule selected")
        ttk.Label(
            selected,
            textvariable=self.run_selected_label,
            style="Subheader.TLabel",
        ).pack(anchor="w")

        simulation = ttk.LabelFrame(
            left, text="Simulation", padding=10
        )
        simulation.pack(fill="x", pady=(0, 10))
        self._combo_row(
            simulation, 0, "Speed", self.speed_text_var,
            [f"{x}x" for x in SPEED_VALUES],
        )
        self._spin_row(
            simulation, 1, "Maximum ticks", self.max_ticks_var,
            0, 100_000_000, 10_000,
        )
        self._spin_row(
            simulation, 2, "Autosave every", self.autosave_var,
            0, 10_000_000, 10_000,
        )
        self._spin_row(
            simulation, 3, "Sample every", self.sample_every_var,
            1, 100_000, 1,
        )
        self._spin_row(
            simulation, 4, "Pressure row every",
            self.pressure_every_var,
            1, 100_000, 10,
        )
        ttk.Checkbutton(
            simulation,
            text="Auto-stop after collapse",
            variable=self.auto_stop_var,
            command=self._update_command_preview,
        ).grid(
            row=5, column=0, columnspan=2,
            sticky="w", pady=(6, 0)
        )

        display = ttk.LabelFrame(
            right, text="Display", padding=10
        )
        display.pack(fill="x", pady=(0, 10))
        self._spin_row(
            display, 0, "Frame delay (ms)",
            self.delay_var, 0, 1000, 1,
        )
        self._spin_row(
            display, 1, "Cell size",
            self.cell_var, 2, 24, 1,
        )

        outputs = ttk.LabelFrame(
            right, text="Outputs and Telemetry", padding=10
        )
        outputs.pack(fill="x", pady=(0, 10))
        output_checks = [
            ("Samples CSV", self.samples_var),
            ("Events CSV", self.events_var),
            ("Pressure timeline CSV", self.pressure_var),
            ("Chronicle CSV", self.chronicle_var),
            ("Passport", self.passport_var),
            ("Observation log", self.log_var),
            ("SQLite telemetry", self.sqlite_var),
            ("Evidence Framework", self.evidence_var),
        ]
        for index, (label, variable) in enumerate(output_checks):
            ttk.Checkbutton(
                outputs,
                text=label,
                variable=variable,
                command=self._update_command_preview,
            ).grid(
                row=index // 2,
                column=index % 2,
                sticky="w",
                padx=(0, 18),
                pady=3,
            )

        preview = ttk.LabelFrame(
            body, text="Command Preview", padding=10
        )
        preview.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Label(
            preview,
            textvariable=self.command_var,
            wraplength=1000,
            justify="left",
        ).pack(fill="x")

        buttons = ttk.Frame(body)
        buttons.pack(side="bottom", fill="x", pady=(10, 0))
        self.launch_button = ttk.Button(
            buttons,
            text="Launch Observer",
            command=self.launch_canonical,
            style="Launch.TButton",
        )
        self.launch_button.pack(side="left")
        self.stop_button = ttk.Button(
            buttons,
            text="Stop",
            command=self.stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            buttons,
            text="Open Output Folder",
            command=lambda: open_path(
                SEARCH_RESULTS_DIR / "observation_logs"
            ),
        ).pack(side="left", padx=(8, 0))

    def _build_experiments_tab(self) -> None:
        # The Experiments page is taller than many desktop layouts. Keep the
        # complete Builder and Production Queue reachable instead of letting
        # lower sections disappear behind the shared Observer Output pane.
        viewport = ttk.Frame(self.experiments_tab)
        viewport.pack(fill="both", expand=True)

        canvas = tk.Canvas(viewport, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(
            viewport, orient="vertical", command=canvas.yview
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = ttk.Frame(canvas)
        body_window = canvas.create_window(
            (0, 0), window=body, anchor="nw"
        )

        def _sync_experiments_scrollregion(_event: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_experiments_width(event: tk.Event) -> None:
            canvas.itemconfigure(body_window, width=event.width)

        body.bind("<Configure>", _sync_experiments_scrollregion)
        canvas.bind("<Configure>", _sync_experiments_width)

        def _scroll_experiments(event: tk.Event) -> None:
            delta = getattr(event, "delta", 0)
            if delta:
                canvas.yview_scroll(-1 if delta > 0 else 1, "units")

        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", _scroll_experiments))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))

        header = ttk.LabelFrame(
            body, text="Experimental Run Context", padding=12
        )
        header.pack(fill="x", pady=(0, 10))

        ttk.Checkbutton(
            header,
            text="Attach selected experiment and condition to canonical runs",
            variable=self.experimental_run_var,
            command=self._experimental_controls_changed,
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(header, text="Experiment").grid(
            row=1, column=0, sticky="w", pady=(10, 3)
        )
        self.experiment_combo = ttk.Combobox(
            header,
            textvariable=self.experiment_var,
            state="readonly",
            width=54,
        )
        self.experiment_combo.grid(
            row=1, column=1, sticky="ew", padx=(10, 8), pady=(10, 3)
        )
        self.experiment_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._experimental_controls_changed(),
        )
        ttk.Button(
            header,
            text="Refresh",
            command=self.refresh_experimental_context,
        ).grid(row=1, column=2, sticky="e", pady=(10, 3))

        ttk.Label(header, text="Condition").grid(
            row=2, column=0, sticky="w", pady=3
        )
        self.condition_combo = ttk.Combobox(
            header,
            textvariable=self.condition_var,
            state="readonly",
            width=54,
        )
        self.condition_combo.grid(
            row=2, column=1, sticky="ew", padx=(10, 8), pady=3
        )
        self.condition_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._experimental_controls_changed(),
        )

        ttk.Label(header, text="Role").grid(
            row=3, column=0, sticky="w", pady=3
        )
        role_combo = ttk.Combobox(
            header,
            textvariable=self.experiment_role_var,
            values=tuple(item.value for item in ExperimentRole),
            state="readonly",
            width=24,
        )
        role_combo.grid(
            row=3, column=1, sticky="w", padx=(10, 8), pady=3
        )
        role_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._experimental_controls_changed(),
        )

        ttk.Label(header, text="Replicate index").grid(
            row=4, column=0, sticky="w", pady=3
        )
        replicate = ttk.Spinbox(
            header,
            textvariable=self.replicate_index_var,
            from_=0,
            to=1_000_000,
            increment=1,
            width=24,
            command=self._experimental_controls_changed,
        )
        replicate.grid(
            row=4, column=1, sticky="w", padx=(10, 8), pady=3
        )
        self.replicate_index_var.trace_add(
            "write",
            lambda *_args: self._experimental_controls_changed(),
        )

        header.columnconfigure(1, weight=1)

        summary = ttk.LabelFrame(
            body, text="Resolved Context", padding=12
        )
        summary.pack(fill="x", pady=(0, 10))
        ttk.Label(
            summary,
            textvariable=self.experiment_summary_var,
            wraplength=1050,
            justify="left",
        ).pack(anchor="w")

        slots = ttk.LabelFrame(
            body, text="Experiment Slot Manager", padding=12
        )
        slots.pack(fill="both", expand=False, pady=(0, 10))

        slot_actions = ttk.Frame(slots)
        slot_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(
            slot_actions, text="Refresh Slots",
            command=self.refresh_experiment_slots,
        ).pack(side="left")
        ttk.Button(
            slot_actions, text="Release Selected Slot",
            command=self.release_selected_experiment_slot,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            slot_actions, text="Release Failed / Interrupted",
            command=self.release_failed_experiment_slots,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            slot_actions, text="Reset Selected Experiment",
            command=self.reset_selected_experiment_slots,
        ).pack(side="right")

        slot_columns = (
            "rule", "role", "replicate", "arm", "run", "status", "tick"
        )
        self.slot_tree = ttk.Treeview(
            slots, columns=slot_columns, show="headings",
            selectmode="browse", height=5,
        )
        slot_labels = {
            "rule": "Rule", "role": "Role",
            "replicate": "Replicate", "arm": "Treatment arm",
            "run": "Run ID", "status": "Status", "tick": "Final tick",
        }
        slot_widths = {
            "rule": 70, "role": 95, "replicate": 80, "arm": 180,
            "run": 285, "status": 105, "tick": 90,
        }
        for key in slot_columns:
            self.slot_tree.heading(key, text=slot_labels[key])
            self.slot_tree.column(
                key, width=slot_widths[key],
                anchor="w" if key in {"arm", "run"} else "center",
            )
        self.slot_tree.pack(fill="both", expand=True)
        ttk.Label(
            slots, textvariable=self.slot_summary_var,
            wraplength=1100, justify="left",
        ).pack(anchor="w", pady=(8, 0))

        builder = ttk.LabelFrame(
            body, text="Manual Experiment Builder (sandbox)", padding=12
        )
        builder.pack(fill="x", expand=False, pady=(0, 10))

        controls = ttk.Frame(builder)
        controls.pack(fill="x", pady=(0, 8))

        ttk.Label(controls, text="Role").pack(side="left")
        self.plan_role_combo = ttk.Combobox(
            controls,
            textvariable=self.plan_role_var,
            values=tuple(item.value for item in ExperimentRole),
            state="readonly",
            width=14,
        )
        self.plan_role_combo.pack(side="left", padx=(6, 12))

        ttk.Label(controls, text="Replicates").pack(side="left")
        ttk.Spinbox(
            controls,
            textvariable=self.plan_replicates_var,
            from_=1,
            to=1000,
            increment=1,
            width=8,
        ).pack(side="left", padx=(6, 12))

        ttk.Checkbutton(
            controls,
            text="Enabled",
            variable=self.plan_enabled_var,
        ).pack(side="left", padx=(0, 12))

        ttk.Label(controls, text="Seed").pack(side="left")
        ttk.Combobox(
            controls,
            textvariable=self.plan_seed_mode_var,
            values=("auto", "fixed"),
            state="readonly",
            width=7,
        ).pack(side="left", padx=(6, 6))
        ttk.Spinbox(
            controls,
            textvariable=self.plan_seed_var,
            from_=0,
            to=2_147_483_647,
            increment=1,
            width=11,
        ).pack(side="left", padx=(0, 12))

        ttk.Button(
            controls,
            text="Add Selected Condition",
            command=self.add_selected_condition_to_plan,
        ).pack(side="left")

        ttk.Button(
            controls,
            text="Remove Selected Arm",
            command=self.remove_selected_plan_item,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            controls,
            text="Clear Plan",
            command=self.clear_experiment_plan,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            controls,
            text="Run Manual Experiment Plan",
            command=self.queue_experiment_plan,
            style="Launch.TButton",
        ).pack(side="right")

        plan_columns = (
            "condition", "role", "replicates", "seed",
            "ticks", "sample", "pressure", "enabled",
        )
        self.plan_tree = ttk.Treeview(
            builder,
            columns=plan_columns,
            show="headings",
            selectmode="browse",
            height=4,
        )
        plan_labels = {
            "condition": "Condition",
            "role": "Role",
            "replicates": "Replicates",
            "seed": "Seed",
            "ticks": "Max ticks",
            "sample": "Sample every",
            "pressure": "Pressure every",
            "enabled": "Enabled",
        }
        plan_widths = {
            "condition": 290,
            "role": 100,
            "replicates": 90,
            "seed": 115,
            "ticks": 100,
            "sample": 100,
            "pressure": 110,
            "enabled": 80,
        }
        for key in plan_columns:
            self.plan_tree.heading(key, text=plan_labels[key])
            self.plan_tree.column(
                key,
                width=plan_widths[key],
                anchor="w" if key == "condition" else "center",
            )
        self.plan_tree.pack(fill="both", expand=True)

        builder_actions = ttk.Frame(builder)
        builder_actions.pack(fill="x", pady=(8, 0))
        ttk.Label(
            builder_actions,
            textvariable=self.plan_summary_var,
        ).pack(side="left")

        director = ttk.LabelFrame(
            body, text="Research Director Approval Gateway", padding=12
        )
        director.pack(fill="both", expand=False, pady=(0, 10))

        director_actions = ttk.Frame(director)
        director_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(
            director_actions,
            text="Refresh Director Proposals",
            command=self.refresh_director_proposals,
        ).pack(side="left")
        ttk.Button(
            director_actions,
            text="Open Director Report",
            command=lambda: open_path(RESEARCH_DIRECTOR_REPORT_FILE),
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            director_actions,
            text="Reject Selected",
            command=self.reject_selected_director_proposal,
        ).pack(side="right", padx=(8, 0))
        self.director_primary_button = ttk.Button(
            director_actions,
            text="Select a proposal",
            command=self.approve_selected_director_proposal_and_launch,
            style="Launch.TButton",
            state="disabled",
        )
        self.director_primary_button.pack(side="right")

        director_columns = (
            "priority", "action", "title", "validation", "resolution", "runtime"
        )
        self.director_tree = ttk.Treeview(
            director,
            columns=director_columns,
            show="headings",
            selectmode="browse",
            height=5,
        )
        director_labels = {
            "priority": "Priority",
            "action": "Action",
            "title": "Proposal",
            "validation": "Validation",
            "resolution": "Resolution",
            "runtime": "Runtime",
        }
        director_widths = {
            "priority": 70,
            "action": 150,
            "title": 390,
            "validation": 120,
            "resolution": 225,
            "runtime": 90,
        }
        for key in director_columns:
            self.director_tree.heading(key, text=director_labels[key])
            self.director_tree.column(
                key,
                width=director_widths[key],
                anchor="center"
                if key in {"priority", "validation", "runtime"}
                else "w",
            )
        self.director_tree.pack(fill="both", expand=True)
        self.director_tree.bind(
            "<<TreeviewSelect>>",
            self._on_director_selection_changed,
        )
        ttk.Label(
            director,
            textvariable=self.director_summary_var,
            wraplength=1150,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        production = ttk.LabelFrame(
            body, text="Automated Research Execution", padding=12
        )
        production.pack(fill="both", expand=True, pady=(0, 10))

        production_actions = ttk.Frame(production)
        production_actions.pack(fill="x", pady=(0, 8))
        ttk.Label(
            production_actions,
            text=(
                "Execution begins only from an eligible Director proposal. "
                "This panel is a monitor, not a second launch point."
            ),
        ).pack(side="left")
        ttk.Button(
            production_actions,
            text="Stop Safely",
            command=self.stop_automated_research_queue,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            production_actions,
            text="Open Current Runtime",
            command=self.open_selected_runtime_package,
        ).pack(side="right")
        self.production_continue_button = ttk.Button(
            production_actions,
            text="Continue Authorized Pipeline",
            command=self.continue_authorized_pipeline,
            style="Launch.TButton",
            state="disabled",
        )
        self.production_continue_button.pack(side="right", padx=(8, 0))

        production_columns = (
            "runtime", "plan", "status", "runs", "unresolved", "authorized"
        )
        self.production_tree = ttk.Treeview(
            production,
            columns=production_columns,
            show="headings",
            selectmode="browse",
            height=5,
        )
        production_labels = {
            "runtime": "Runtime",
            "plan": "Plan",
            "status": "Status",
            "runs": "Runs",
            "unresolved": "Unresolved",
            "authorized": "Authorized",
        }
        production_widths = {
            "runtime": 230,
            "plan": 230,
            "status": 210,
            "runs": 70,
            "unresolved": 90,
            "authorized": 90,
        }
        for key in production_columns:
            self.production_tree.heading(key, text=production_labels[key])
            self.production_tree.column(
                key,
                width=production_widths[key],
                anchor="w"
                if key in {"runtime", "plan", "status"}
                else "center",
            )
        self.production_tree.pack(fill="both", expand=True)
        ttk.Label(
            production,
            textvariable=self.production_summary_var,
            wraplength=1150,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            production,
            textvariable=self.automated_research_status_var,
            wraplength=1150,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        cycles = ttk.LabelFrame(
            body, text="Authoritative Research Cycles", padding=12
        )
        cycles.pack(fill="both", expand=True, pady=(0, 10))

        cycle_actions = ttk.Frame(cycles)
        cycle_actions.pack(fill="x", pady=(0, 8))
        ttk.Label(
            cycle_actions,
            text=(
                "Current stage, blockers and next required action come only "
                "from ResearchCycleRecord."
            ),
        ).pack(side="left")
        ttk.Button(
            cycle_actions,
            text="Open Selected Record",
            command=self.open_selected_research_cycle,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            cycle_actions,
            text="Refresh Cycles",
            command=self.refresh_research_cycles,
        ).pack(side="right")

        cycle_columns = (
            "cycle", "observer", "stage", "next", "integrity", "blockers"
        )
        self.research_cycle_tree = ttk.Treeview(
            cycles,
            columns=cycle_columns,
            show="headings",
            selectmode="browse",
            height=5,
        )
        cycle_labels = {
            "cycle": "Cycle",
            "observer": "Observer run",
            "stage": "Current stage",
            "next": "Next required action",
            "integrity": "Integrity",
            "blockers": "Blockers",
        }
        cycle_widths = {
            "cycle": 235,
            "observer": 230,
            "stage": 220,
            "next": 250,
            "integrity": 105,
            "blockers": 75,
        }
        for key in cycle_columns:
            self.research_cycle_tree.heading(
                key, text=cycle_labels[key]
            )
            self.research_cycle_tree.column(
                key,
                width=cycle_widths[key],
                anchor="center"
                if key in {"integrity", "blockers"}
                else "w",
            )
        self.research_cycle_tree.pack(fill="both", expand=True)
        ttk.Label(
            cycles,
            textvariable=self.research_cycle_summary_var,
            wraplength=1150,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        note = ttk.LabelFrame(
            body, text="Integration Stage", padding=12
        )
        note.pack(fill="x")
        ttk.Label(
            note,
            text=(
                "Automated mode consumes research actions and plans already "
                "produced by Stage 6, advances eligible work through Stage 7, "
                "launches Observer tasks, validates their outputs, and continues "
                "until no eligible task remains. Observer is the visual monitor; "
                "experiment selection stays in the research pipeline."
            ),
            wraplength=1050,
            justify="left",
        ).pack(anchor="w")

        self.refresh_experimental_context()
        self.refresh_experiment_slots()
        self.refresh_director_proposals()
        self.refresh_production_state()
        self.refresh_research_cycles()

    def refresh_experimental_context(self) -> None:
        try:
            repository = ExperimentalConditionsRepository(
                TELEMETRY_DATABASE
            )
            experiments = repository.list_experiments()
            conditions = repository.list_conditions()
        except Exception as exc:
            self._experiments_by_display = {}
            self._conditions_by_display = {}
            self.experiment_combo.configure(values=())
            self.condition_combo.configure(values=())
            self.experiment_summary_var.set(
                f"Could not read experimental context: {exc}"
            )
            return

        self._experiments_by_display = {
            f"{item.experiment_id} | {item.title}": item
            for item in experiments
        }
        self._conditions_by_display = {
            (
                f"{item.condition_id} | {item.name} | "
                f"{item.field_width}×{item.field_height} "
                f"{item.topology.value}/{item.boundary_mode.value}"
            ): item
            for item in conditions
        }
        experiment_values = tuple(self._experiments_by_display)
        condition_values = tuple(self._conditions_by_display)
        self.experiment_combo.configure(values=experiment_values)
        self.condition_combo.configure(values=condition_values)

        if (
            self.experiment_var.get() not in self._experiments_by_display
            and experiment_values
        ):
            self.experiment_var.set(experiment_values[0])
        if (
            self.condition_var.get() not in self._conditions_by_display
            and condition_values
        ):
            self.condition_var.set(condition_values[0])
        self._experimental_controls_changed()

    def _selected_experimental_context(
        self,
        *,
        require_enabled: bool = True,
    ) -> dict[str, Any] | None:
        if require_enabled and not self.experimental_run_var.get():
            return None

        experiment = self._experiments_by_display.get(
            self.experiment_var.get()
        )
        condition = self._conditions_by_display.get(
            self.condition_var.get()
        )
        if experiment is None or condition is None:
            raise ValueError(
                "Select both an experiment and an experimental condition."
            )
        if not self.sqlite_var.get():
            raise ValueError(
                "Experimental runs require SQLite telemetry."
            )

        replicate_index = int(self.replicate_index_var.get())
        if replicate_index < 0:
            raise ValueError("Replicate index must be >= 0.")

        return {
            "experiment_id": experiment.experiment_id,
            "condition_id": condition.condition_id,
            "role": self.experiment_role_var.get(),
            "replicate_index": replicate_index,
            "field_width": condition.field_width,
            "field_height": condition.field_height,
            "topology": condition.topology.value,
            "boundary_mode": condition.boundary_mode.value,
            "initial_state_mode": condition.initial_state_mode.value,
        }

    def _experimental_controls_changed(self) -> None:
        try:
            context = self._selected_experimental_context(
                require_enabled=False
            )
            prefix = (
                "ENABLED" if self.experimental_run_var.get()
                else "DISABLED"
            )
            self.experiment_summary_var.set(
                f"{prefix}: {context['experiment_id']} → "
                f"{context['condition_id']} | role={context['role']} | "
                f"replicate={context['replicate_index']} | "
                f"{context['field_width']}×{context['field_height']} "
                f"{context['topology']}/{context['boundary_mode']} "
                f"{context['initial_state_mode']}"
            )
        except Exception as exc:
            self.experiment_summary_var.set(str(exc))
        self._update_command_preview()
        if hasattr(self, "slot_tree"):
            self.refresh_experiment_slots()

    def refresh_experiment_slots(self) -> None:
        if not hasattr(self, "slot_tree"):
            return
        self.slot_tree.delete(*self.slot_tree.get_children())
        self._slot_rows = {}
        experiment = self._experiments_by_display.get(self.experiment_var.get())
        if experiment is None:
            self.slot_summary_var.set("Select an experiment to inspect slots.")
            return
        try:
            connection = sqlite3.connect(str(TELEMETRY_DATABASE))
            connection.row_factory = sqlite3.Row
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(experiment_runs)"
                ).fetchall()
            }
            arm_expr = (
                "COALESCE(er.treatment_arm, '')"
                if "treatment_arm" in columns else "''"
            )
            rows = connection.execute(
                f"""
                SELECT er.experiment_run_id, er.experiment_id,
                       er.condition_id, er.rule_id, er.role,
                       er.replicate_index, {arm_expr} AS treatment_arm,
                       er.run_id, COALESCE(r.status, 'orphaned') AS status,
                       r.final_tick
                FROM experiment_runs er
                LEFT JOIN runs r ON r.run_id = er.run_id
                WHERE er.experiment_id = ?
                ORDER BY er.rule_id, er.role, er.replicate_index,
                         treatment_arm, er.created_at_utc
                """,
                (experiment.experiment_id,),
            ).fetchall()
        except Exception as exc:
            self.slot_summary_var.set(f"Could not read experiment slots: {exc}")
            return
        finally:
            try:
                connection.close()
            except Exception:
                pass
        for row in rows:
            key = str(row["experiment_run_id"])
            payload = dict(row)
            self._slot_rows[key] = payload
            self.slot_tree.insert(
                "", "end", iid=key, values=(
                    normalize_rule_id(row["rule_id"]), row["role"],
                    row["replicate_index"], row["treatment_arm"] or "-",
                    row["run_id"], str(row["status"]).upper(),
                    row["final_tick"] if row["final_tick"] is not None else "-",
                ),
            )
        self.slot_summary_var.set(
            f"Experiment {experiment.experiment_id}: {len(rows)} occupied slot(s). "
            "Releasing a slot removes only the experiment link; telemetry and run files remain."
        )

    def _release_experiment_run_ids(self, ids: list[str]) -> int:
        ids = [str(item) for item in ids if item]
        if not ids:
            return 0
        connection = sqlite3.connect(str(TELEMETRY_DATABASE))
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in ids)
            cursor = connection.execute(
                f"DELETE FROM experiment_runs WHERE experiment_run_id IN ({placeholders})",
                ids,
            )
            connection.commit()
            return int(cursor.rowcount)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def release_selected_experiment_slot(self) -> None:
        selection = self.slot_tree.selection()
        if not selection:
            messagebox.showwarning("Release slot", "Select an occupied slot first.")
            return
        key = str(selection[0])
        row = self._slot_rows.get(key, {})
        status = str(row.get("status") or "").lower()
        if status == "running":
            messagebox.showerror(
                "Release refused",
                "A RUNNING slot cannot be released. Stop the run first.",
            )
            return
        if not messagebox.askyesno(
            "Release selected slot?",
            f"Release {key}?\n\nRun: {row.get('run_id')}\n"
            "Only the experiment link will be removed. Telemetry and files remain.",
        ):
            return
        try:
            removed = self._release_experiment_run_ids([key])
        except Exception as exc:
            messagebox.showerror("Could not release slot", str(exc))
            return
        self.refresh_experiment_slots()
        self.status_var.set(f"Released {removed} experiment slot(s)")

    def release_failed_experiment_slots(self) -> None:
        ids = [
            key for key, row in self._slot_rows.items()
            if str(row.get("status") or "").lower()
            in {"failed", "stopped", "interrupted", "orphaned"}
        ]
        if not ids:
            messagebox.showinfo("Release slots", "No failed or interrupted slots found.")
            return
        if not messagebox.askyesno(
            "Release failed slots?",
            f"Release {len(ids)} failed/interrupted slot(s)?\n\n"
            "Telemetry and run files will remain untouched.",
        ):
            return
        try:
            removed = self._release_experiment_run_ids(ids)
        except Exception as exc:
            messagebox.showerror("Could not release slots", str(exc))
            return
        self.refresh_experiment_slots()
        self.status_var.set(f"Released {removed} failed/interrupted slot(s)")

    def reset_selected_experiment_slots(self) -> None:
        experiment = self._experiments_by_display.get(self.experiment_var.get())
        if experiment is None:
            messagebox.showwarning("Reset experiment", "Select an experiment first.")
            return
        running = [
            row for row in self._slot_rows.values()
            if str(row.get("status") or "").lower() == "running"
        ]
        if running:
            messagebox.showerror(
                "Reset refused",
                f"{len(running)} slot(s) are RUNNING. Stop them before reset.",
            )
            return
        ids = list(self._slot_rows)
        if not ids:
            messagebox.showinfo("Reset experiment", "The experiment has no occupied slots.")
            return
        if not messagebox.askyesno(
            "Reset selected experiment?",
            f"Release all {len(ids)} slot(s) for {experiment.experiment_id}?\n\n"
            "This enables a complete rerun. Existing telemetry and output files remain as history.",
            icon="warning",
        ):
            return
        try:
            removed = self._release_experiment_run_ids(ids)
        except Exception as exc:
            messagebox.showerror("Could not reset experiment", str(exc))
            return
        self.refresh_experiment_slots()
        self.status_var.set(f"Reset experiment slots: {removed} released")

    def add_selected_condition_to_plan(self) -> None:
        condition = self._conditions_by_display.get(
            self.condition_var.get()
        )
        if condition is None:
            messagebox.showerror(
                "Cannot add condition",
                "Select a condition first.",
            )
            return
        try:
            replicates = int(self.plan_replicates_var.get())
            if replicates < 1:
                raise ValueError("Replicates must be >= 1.")
            role = ExperimentRole(self.plan_role_var.get())
        except Exception as exc:
            messagebox.showerror("Invalid plan arm", str(exc))
            return

        duplicate = any(
            item["condition_id"] == condition.condition_id
            and item["role"] == role.value
            for item in self.plan_items
        )
        if duplicate:
            messagebox.showwarning(
                "Duplicate plan arm",
                "That condition and role are already present.",
            )
            return

        seed_mode = None
        resolved_seed = None
        if (
            condition.initial_state_mode
            is InitialStateMode.RANDOM_SEED
        ):
            seed_mode = self.plan_seed_mode_var.get()
            if seed_mode == "fixed":
                resolved_seed = int(self.plan_seed_var.get())
                if resolved_seed < 0:
                    messagebox.showerror(
                        "Invalid seed",
                        "Seed must be >= 0.",
                    )
                    return

        self.plan_items.append({
            "condition_id": condition.condition_id,
            "condition_name": condition.name,
            "role": role.value,
            "replicate_count": replicates,
            "seed_mode": seed_mode,
            "seed": resolved_seed,
            "max_ticks": int(self.max_ticks_var.get()),
            "sample_every": int(self.sample_every_var.get()),
            "pressure_every": int(self.pressure_every_var.get()),
            "enabled": bool(self.plan_enabled_var.get()),
        })
        self._refresh_plan_tree()

    def remove_selected_plan_item(self) -> None:
        selection = self.plan_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        if 0 <= index < len(self.plan_items):
            self.plan_items.pop(index)
        self._refresh_plan_tree()

    def clear_experiment_plan(self) -> None:
        self.plan_items.clear()
        self._refresh_plan_tree()

    def _refresh_plan_tree(self) -> None:
        self.plan_tree.delete(*self.plan_tree.get_children())
        for index, item in enumerate(self.plan_items):
            self.plan_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    f"{item['condition_id']} | {item['condition_name']}",
                    item["role"],
                    item["replicate_count"],
                    (
                        f"auto × {item['replicate_count']}"
                        if item.get("seed_mode") == "auto"
                        else (
                            item["seed"]
                            if item.get("seed") is not None
                            else "canonical"
                        )
                    ),
                    item["max_ticks"],
                    item["sample_every"],
                    item["pressure_every"],
                    "Yes" if item["enabled"] else "No",
                ),
            )
        enabled_runs = sum(
            item["replicate_count"]
            for item in self.plan_items
            if item["enabled"]
        )
        self.plan_summary_var.set(
            f"Arms: {len(self.plan_items)} | "
            f"Enabled runs: {enabled_runs}"
        )

    def _build_experiment_plan(self) -> ExperimentPlan:
        experiment = self._experiments_by_display.get(
            self.experiment_var.get()
        )
        if experiment is None:
            raise ValueError("Select an experiment first.")
        if not self.rule_var.get().strip():
            raise ValueError("Select a rule first.")
        if not self.sqlite_var.get():
            raise ValueError(
                "Experiment plans require SQLite telemetry."
            )

        items = tuple(
            ExperimentPlanItem(
                condition_id=item["condition_id"],
                role=ExperimentRole(item["role"]),
                replicate_count=int(item["replicate_count"]),
                max_ticks=int(item["max_ticks"]),
                sample_every=int(item["sample_every"]),
                pressure_every=int(item["pressure_every"]),
                enabled=bool(item["enabled"]),
                seed_mode=item.get("seed_mode"),
                seed=item.get("seed"),
            )
            for item in self.plan_items
        )
        return ExperimentPlan(
            experiment_id=experiment.experiment_id,
            rule_id=int(self.rule_var.get()),
            items=items,
            title=experiment.title,
            research_question=experiment.research_question,
            metadata={"builder_version": "experiment_builder_v1"},
        )

    def queue_experiment_plan(self) -> None:
        try:
            self._selected_rule_payload()
            repository = ExperimentalConditionsRepository(
                TELEMETRY_DATABASE
            )
            plan = self._build_experiment_plan()
            requests = repository.expand_plan(plan)
        except Exception as exc:
            messagebox.showerror(
                "Could not build experiment plan",
                str(exc),
            )
            return

        runs = []
        for request in requests:
            context = {
                "experiment_id": request.experiment_id,
                "condition_id": request.condition_id,
                "role": request.role.value,
                "replicate_index": request.replicate_index,
                "field_width": request.field_width,
                "field_height": request.field_height,
                "topology": request.topology.value,
                "boundary_mode": request.boundary_mode.value,
                "initial_state_mode": request.initial_state_mode.value,
                "seed": int(resolved_seed),
            }
            runs.append({
                "mutation_id": None,
                "run_dir": (
                    SEARCH_RESULTS_DIR / "observation_logs"
                ),
                "rule_file": None,
                "manifest_file": None,
                "mode": "experiment_plan",
                "rule_id": request.rule_id,
                "experimental_context": context,
                "max_ticks_override": request.max_ticks,
                "sample_every_override": request.sample_every,
                "pressure_every_override": request.pressure_every,
                "status": "Waiting",
            })

        if self.process is not None:
            messagebox.showwarning(
                "Observer is running",
                "Stop the current Observer before starting an experiment plan.",
            )
            return

        if self.batch_queue:
            replace = messagebox.askyesno(
                "Replace waiting queue?",
                (
                    "The waiting queue already contains "
                    f"{len(self.batch_queue)} run(s).\n\n"
                    "Replace it with this experiment plan?"
                ),
            )
            if not replace:
                return

        # The plan is one atomic scientific batch. Do not mix it silently with
        # old waiting runs and do not depend on the currently selected context.
        self.batch_queue = list(runs)
        self.queue_runs = list(runs)
        self._refresh_queue()
        self.notebook.select(self.queue_tab)
        self.status_var.set(
            f"Starting experiment plan: {len(runs)} run(s)"
        )
        self.start_queue()

    def _write_runtime_registry(self, packages: list[dict[str, Any]]) -> None:
        packages = sorted(
            packages, key=lambda item: str(item.get("runtime_id") or "")
        )
        ready = sum(
            1 for item in packages
            if item.get("status") == "READY_FOR_LAUNCH_REVIEW"
        )
        authorized = sum(
            1 for item in packages
            if item.get("status") == "LAUNCH_AUTHORIZED"
            and item.get("launch_authorized") is True
        )
        summary = {
            "committed_plan_count": len(packages),
            "materialized_count": len(packages),
            "blocked_count": 0,
            "ready_for_launch_review_count": ready,
            "needs_runtime_resolution_count": sum(
                1 for item in packages
                if item.get("status") == "NEEDS_RUNTIME_RESOLUTION"
            ),
            "launch_authorized_count": authorized,
        }
        payload = {
            "schema": "archon_experiment_runtime_registry_v1",
            "version": "1.0",
            "generated_at": datetime.now().astimezone().isoformat(),
            "mode": "MATERIALIZATION_WITH_MANUAL_BUILDER_SOURCE",
            "summary": summary,
            "packages": packages,
            "blocked_plans": [],
            "source_registry": {
                "path": str(MANUAL_PLAN_REGISTRY_FILE),
                "content_hash": canonical_hash(
                    read_json(MANUAL_PLAN_REGISTRY_FILE, {})
                ),
            },
            "policy": {
                "materialization_does_not_execute": True,
                "launch_authorized": authorized > 0,
                "separate_launch_authorization_required": True,
                "verified_committed_plans_only": False,
                "manual_builder_source_allowed": True,
            },
        }
        payload["content_hash"] = canonical_hash({
            "summary": summary,
            "packages": packages,
            "blocked_plans": [],
            "source_registry": payload["source_registry"],
        })
        atomic_json(RUNTIME_REGISTRY_FILE, payload)

    def publish_builder_runtime(self) -> None:
        try:
            self._selected_rule_payload()
            repository = ExperimentalConditionsRepository(TELEMETRY_DATABASE)
            plan = self._build_experiment_plan()
            requests = list(repository.expand_plan(plan))
            if not requests:
                raise ValueError("The Experiment Builder plan contains no enabled runs.")
        except Exception as exc:
            messagebox.showerror("Could not publish Builder plan", str(exc))
            return

        if not messagebox.askyesno(
            "Publish manual production runtime?",
            (
                f"Publish {len(requests)} run(s) from the current Builder plan?\n\n"
                "Source will be recorded as MANUAL_OBSERVER_BUILDER. "
                "Launch authorization will still be required."
            ),
        ):
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plan_fingerprint = canonical_hash({
            "experiment_id": plan.experiment_id,
            "rule_id": plan.rule_id,
            "items": self.plan_items,
            "timestamp": timestamp,
        })[:12].upper()
        plan_id = f"MANUAL-PLAN-{timestamp}-{plan_fingerprint}"
        runtime_id = f"MANUAL-RUNTIME-{timestamp}-{plan_fingerprint}"
        commit_id = f"MANUAL-COMMIT-{timestamp}-{plan_fingerprint}"
        runtime_dir = MANUAL_RUNTIME_ROOT / runtime_id
        runs_root = runtime_dir / "runs"
        runtime_dir.mkdir(parents=True, exist_ok=True)

        run_matrix: list[dict[str, Any]] = []
        for index, request in enumerate(requests, 1):
            run_id = f"{runtime_id}-RUN-{index:04d}"
            output_dir = runs_root / run_id
            topology = (
                "TORUS" if request.topology.value == "torus" else "PLANE"
            )
            boundary_aliases = {
                "wrap": "WRAP",
                "fixed_dead": "FIXED_DEAD",
                "fixed_alive": "FIXED_ALIVE",
                "reflective": "REFLECTIVE",
            }

            # Stage 6.5 requires every runtime row to carry an explicit seed.
            # ExperimentalConditions uses None for canonical/automatic seeds,
            # so materialize a stable deterministic integer instead of leaving
            # the production run matrix unresolved.
            resolved_seed = request.seed
            if resolved_seed is None:
                seed_material = {
                    "runtime_id": runtime_id,
                    "run_index": index,
                    "rule_id": normalize_rule_id(request.rule_id),
                    "condition_id": request.condition_id,
                    "replicate_index": int(request.replicate_index),
                    "initial_state_mode": request.initial_state_mode.value,
                }
                resolved_seed = int(
                    canonical_hash(seed_material)[:8], 16
                ) & 0x7FFFFFFF

            run_matrix.append({
                "run_id": run_id,
                "rule_id": normalize_rule_id(request.rule_id),
                "condition_id": request.condition_id,
                "role": request.role.value.upper(),
                "replicate_index": int(request.replicate_index),
                "seed": request.seed,
                "field_size": [
                    int(request.field_width), int(request.field_height)
                ],
                "topology": topology,
                "boundary_condition": boundary_aliases[
                    request.boundary_mode.value
                ],
                "initial_state_mode": request.initial_state_mode.value,
                "duration_ticks": int(request.max_ticks),
                "sample_interval": int(request.sample_every),
                "pressure_interval": int(request.pressure_every),
                "output_directory": str(output_dir),
                "status": "PENDING",
            })

        runtime_spec = {
            "runtime_id": runtime_id,
            "plan_id": plan_id,
            "commit_id": commit_id,
            "draft_id": None,
            "intake_id": None,
            "experiment_id": plan.experiment_id,
            "experiment_type": "manual_observer_builder",
            "rule_id": normalize_rule_id(plan.rule_id),
            "field_size": run_matrix[0]["field_size"],
            "topology": run_matrix[0]["topology"],
            "boundary_condition": run_matrix[0]["boundary_condition"],
            "duration_ticks": max(row["duration_ticks"] for row in run_matrix),
            "sample_interval": min(row["sample_interval"] for row in run_matrix),
            "checkpoint_interval": int(self.autosave_var.get()),
            "seed_policy": {
                "mode": "BUILDER_DECLARED",
                "materialized_seeds": [row["seed"] for row in run_matrix],
            },
            "control_mode": "BUILDER_DECLARED",
            "declared_controls": [],
            "perturbation": None,
            "run_matrix": run_matrix,
            "resource_profile": {"device": "AUTO", "max_workers": 1},
            "output_layout": {
                "runtime_root": str(runtime_dir),
                "runs_root": str(runs_root),
                "logs_root": str(runtime_dir / "logs"),
                "artifacts_root": str(runtime_dir / "artifacts"),
                "runtime_manifest": str(runtime_dir / "runtime_package.json"),
            },
            "evidence_contract": {
                "required_channels": [],
                "success_criteria": [],
                "provenance_required": True,
            },
            "source_plan": {
                "source_type": "MANUAL_OBSERVER_BUILDER",
                "requested_by": os.environ.get("USER") or "human",
                "builder_version": VERSION,
                "plan_hash": canonical_hash({
                    "experiment_id": plan.experiment_id,
                    "rule_id": plan.rule_id,
                    "items": self.plan_items,
                }),
                "manifest_hash": None,
                "manifest_path": str(MANUAL_PLAN_REGISTRY_FILE),
            },
        }
        package = {
            "schema": "archon_experiment_runtime_package_v1",
            "version": "1.0",
            "runtime_id": runtime_id,
            "status": "READY_FOR_LAUNCH_REVIEW",
            "created_at": datetime.now().astimezone().isoformat(),
            "updated_at": datetime.now().astimezone().isoformat(),
            "runtime_hash": canonical_hash(runtime_spec),
            "runtime": runtime_spec,
            "unresolved_fields": [],
            "launch_authorization": {
                "authorized": False,
                "authorization_id": None,
                "authorized_at": None,
                "authorized_by": None,
                "confirmation": None,
            },
            "policy": {
                "materialized_not_executed": True,
                "launch_authorized": False,
                "separate_launch_authorization_required": True,
                "runtime_fields_editable_before_authorization": True,
                "source_plan_immutable": True,
                "manual_builder_source": True,
                "does_not_change_governance_state": True,
                "does_not_change_scientific_metrics": True,
            },
        }
        package_path = runtime_dir / "runtime_package.json"
        atomic_json(package_path, package)

        manual_registry = read_json(MANUAL_PLAN_REGISTRY_FILE, {})
        rows = manual_registry.get("plans", []) if isinstance(manual_registry, dict) else []
        rows = [row for row in rows if row.get("plan_id") != plan_id]
        rows.append({
            "plan_id": plan_id,
            "commit_id": commit_id,
            "runtime_id": runtime_id,
            "source_type": "MANUAL_OBSERVER_BUILDER",
            "experiment_id": plan.experiment_id,
            "rule_id": normalize_rule_id(plan.rule_id),
            "run_count": len(run_matrix),
            "package_path": str(package_path),
            "status": "READY_FOR_LAUNCH_REVIEW",
            "created_at": package["created_at"],
        })
        manual_payload = {
            "schema": "archon_manual_experiment_plan_registry_v1",
            "version": "1.0",
            "updated_at": datetime.now().astimezone().isoformat(),
            "plan_count": len(rows),
            "plans": rows,
            "policy": {
                "human_authored": True,
                "governance_source_impersonation_forbidden": True,
                "separate_launch_authorization_required": True,
            },
        }
        manual_payload["content_hash"] = canonical_hash(rows)
        atomic_json(MANUAL_PLAN_REGISTRY_FILE, manual_payload)

        registry = read_json(RUNTIME_REGISTRY_FILE, {})
        packages = registry.get("packages", []) if isinstance(registry, dict) else []
        packages = [
            row for row in packages
            if isinstance(row, dict) and row.get("runtime_id") != runtime_id
        ]
        packages.append({
            "runtime_id": runtime_id,
            "plan_id": plan_id,
            "commit_id": commit_id,
            "status": package["status"],
            "runtime_hash": package["runtime_hash"],
            "package_path": str(package_path),
            "unresolved_count": 0,
            "run_count": len(run_matrix),
            "launch_authorized": False,
            "source_type": "MANUAL_OBSERVER_BUILDER",
            "created_at": package["created_at"],
            "updated_at": package["updated_at"],
        })
        self._write_runtime_registry(packages)
        self.refresh_production_state()
        if runtime_id in self._production_packages:
            self.production_tree.selection_set(runtime_id)
            self.production_tree.focus(runtime_id)
            self.production_tree.see(runtime_id)
        self.status_var.set(
            f"Published manual runtime {runtime_id}: {len(run_matrix)} run(s)"
        )
        messagebox.showinfo(
            "Builder runtime published",
            (
                f"Runtime {runtime_id} was created with {len(run_matrix)} run(s).\n\n"
                "Next: Authorize Selected Runtime."
            ),
        )

    def authorize_selected_runtime(self) -> None:
        try:
            entry = self._selected_runtime_entry()
            if entry.get("status") != "READY_FOR_LAUNCH_REVIEW":
                raise ValueError(
                    "Selected runtime is not READY_FOR_LAUNCH_REVIEW."
                )
            if int(entry.get("unresolved_count") or 0) != 0:
                raise ValueError("Selected runtime has unresolved fields.")
            if not LAUNCH_AUTHORIZATION_MODULE.is_file():
                raise ValueError(
                    f"Launch authorization module is missing: "
                    f"{LAUNCH_AUTHORIZATION_MODULE}"
                )
        except Exception as exc:
            messagebox.showerror("Could not authorize runtime", str(exc))
            return

        if not messagebox.askyesno(
            "Authorize selected runtime?",
            (
                f"Authorize runtime {entry.get('runtime_id')} for execution?\n\n"
                "Authorization does not launch Observer."
            ),
        ):
            return

        registry = read_json(RUNTIME_REGISTRY_FILE, {})
        authorization_id = (
            f"AUTH-{datetime.now().strftime('%Y%m%d_%H%M%S')}-"
            f"{secrets.token_hex(4).upper()}"
        )
        request = {
            "schema": "archon_launch_authorization_request_v1",
            "authorize": True,
            "authorization_id": authorization_id,
            "runtime_id": entry.get("runtime_id"),
            "expected_runtime_hash": entry.get("runtime_hash"),
            "expected_runtime_registry_hash": registry.get("content_hash"),
            "requested_at": datetime.now().astimezone().isoformat(),
            "requested_by": os.environ.get("USER") or "observer_launcher",
            "confirmation": "AUTHORIZE_EXPERIMENT_LAUNCH",
            "last_consumed_authorization_id": None,
        }
        atomic_json(
            EXPERIMENTS_ROOT / "launch_authorization_request.json",
            request,
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(LAUNCH_AUTHORIZATION_MODULE),
                "--analysis-root",
                str(ANALYSIS_RESULTS_DIR),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        result = read_json(
            EXPERIMENTS_ROOT / "launch_authorization_result.json", {}
        )
        self.refresh_production_state()
        if completed.returncode != 0 or result.get("authorized") is not True:
            reasons = result.get("reasons") or [completed.stdout[-1500:]]
            messagebox.showerror(
                "Runtime authorization refused",
                "\n".join(str(item) for item in reasons),
            )
            return
        runtime_id = str(entry.get("runtime_id"))
        if runtime_id in self._production_packages:
            self.production_tree.selection_set(runtime_id)
            self.production_tree.focus(runtime_id)
        self.status_var.set(f"Authorized production runtime {runtime_id}")
        messagebox.showinfo(
            "Runtime authorized",
            f"Runtime {runtime_id} is ready for Launch Experiment Plan Queue.",
        )

    @staticmethod
    def _adaptive_autosave_for_ticks(ticks: int | None) -> int:
        horizon = max(0, int(ticks or 0))
        if horizon <= 20_000:
            return 0
        if horizon <= 100_000:
            return 20_000
        return 50_000

    def _emit_automation(self, text: str) -> None:
        self.output_queue.put(f"[AUTO] {text}\\n")

    def _run_stage_module(self, label: str, module: Path) -> int:
        if not module.is_file():
            self._emit_automation(f"{label}: module missing: {module}")
            return 2
        command = [
            sys.executable, str(module),
            "--analysis-root", str(ANALYSIS_RESULTS_DIR),
        ]
        self._emit_automation(f"{label}: {' '.join(shlex.quote(x) for x in command)}")
        completed = subprocess.run(
            command, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        for line in completed.stdout.splitlines():
            self._emit_automation(f"{label}: {line}")
        return int(completed.returncode)

    def _run_production_owner_handoff(self) -> str:
        command = [
            sys.executable,
            str(PRODUCTION_LAUNCHER_HANDOFF),
            "--analysis-root",
            str(ANALYSIS_RESULTS_DIR),
            "--results-directory",
            str(SEARCH_RESULTS_DIR),
            "--analyzer-entrypoint",
            str(ANALYZER_ENTRYPOINT),
            "--observer-script",
            str(OBSERVER_SCRIPT),
            "--telemetry-database",
            str(TELEMETRY_DATABASE),
            "--knowledge-atlas-directory",
            str(KNOWLEDGE_ATLAS_DIR),
            "--world-atlas-directory",
            str(WORLD_ATLAS_DIR),
            "--requested-by",
            "Observer Laboratory v3.5",
            "--confirmation",
            "PREPARE_NEXT_PRODUCTION_RESEARCH_CYCLE",
        ]
        self._emit_automation(
            "Production handoff: "
            + " ".join(shlex.quote(item) for item in command)
        )
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        for line in completed.stdout.splitlines():
            self._emit_automation(f"Production handoff: {line}")
        result = read_json(
            EXPERIMENTS_ROOT / "production_launcher_handoff_result.json",
            {},
        )
        status = str(result.get("status") or "UNKNOWN")
        if completed.returncode != 0 or status == "REFUSED":
            reasons = result.get("reasons") or [f"returncode={completed.returncode}"]
            raise RuntimeError(
                "Production owner handoff refused: "
                + "; ".join(str(item) for item in reasons)
            )
        return status

    def _run_runtime_recovery(
        self,
        plan_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        command = [
            sys.executable,
            str(PRODUCTION_RUNTIME_RECOVERY),
            "--analysis-root",
            str(ANALYSIS_RESULTS_DIR),
            "--confirmation",
            "RECONCILE_STRANDED_PRODUCTION_RUNTIMES",
        ]
        for plan_id in sorted(set(plan_ids or [])):
            command.extend(["--plan-id", plan_id])
        self._emit_automation(
            "Runtime recovery: "
            + " ".join(shlex.quote(item) for item in command)
        )
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        for line in completed.stdout.splitlines():
            self._emit_automation(f"Runtime recovery: {line}")
        result = read_json(
            EXPERIMENTS_ROOT / "production_runtime_recovery_result.json",
            {},
        )
        if completed.returncode != 0 or result.get("status") == "REFUSED":
            reasons = result.get("reasons") or [
                f"returncode={completed.returncode}"
            ]
            raise RuntimeError(
                "Production runtime recovery refused: "
                + "; ".join(str(item) for item in reasons)
            )
        return result

    def _run_scientific_target_resolver(
        self,
        plan_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        command = [
            sys.executable,
            str(SCIENTIFIC_TARGET_RESOLVER),
            "--analysis-root",
            str(ANALYSIS_RESULTS_DIR),
            "--telemetry-database",
            str(TELEMETRY_DATABASE),
            "--confirmation",
            "RESOLVE_SCIENTIFIC_TARGETS",
        ]
        for plan_id in sorted(set(plan_ids or [])):
            command.extend(["--plan-id", plan_id])
        self._emit_automation(
            "Scientific target resolver: "
            + " ".join(shlex.quote(item) for item in command)
        )
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        for line in completed.stdout.splitlines():
            self._emit_automation(f"Scientific target resolver: {line}")
        result = read_json(
            EXPERIMENTS_ROOT / "scientific_target_resolution_result.json",
            {},
        )
        if (
            completed.returncode != 0
            or result.get("status") != "RESOLVED"
        ):
            reasons = result.get("reasons") or [
                f"returncode={completed.returncode}"
            ]
            raise RuntimeError(
                "Scientific target resolution requires human review: "
                + "; ".join(str(item) for item in reasons)
            )
        return result

    def _run_scientific_protocol_resolver(
        self,
        plan_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        command = [
            sys.executable,
            str(SCIENTIFIC_PROTOCOL_RESOLVER),
            "--analysis-root",
            str(ANALYSIS_RESULTS_DIR),
            "--confirmation",
            "RESOLVE_SCIENTIFIC_PROTOCOLS",
        ]
        for plan_id in sorted(set(plan_ids or [])):
            command.extend(["--plan-id", plan_id])
        self._emit_automation(
            "Scientific protocol resolver: "
            + " ".join(shlex.quote(item) for item in command)
        )
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        for line in completed.stdout.splitlines():
            self._emit_automation(
                f"Scientific protocol resolver: {line}"
            )
        result = read_json(
            EXPERIMENTS_ROOT
            / "scientific_protocol_resolution_result.json",
            {},
        )
        if (
            completed.returncode != 0
            or result.get("status") != "RESOLVED"
        ):
            reasons = result.get("reasons") or [
                f"returncode={completed.returncode}"
            ]
            raise RuntimeError(
                "Scientific protocol resolution requires human review: "
                + "; ".join(str(item) for item in reasons)
            )
        return result

    def _run_authoritative_production_owner(self) -> dict[str, Any]:
        command = [
            sys.executable,
            str(PRODUCTION_RESEARCH_CYCLE_OWNER),
            "--analysis-root",
            str(ANALYSIS_RESULTS_DIR),
            "--modules-root",
            str(COMPATIBILITY_ROOT),
        ]
        self._emit_automation(
            "Production owner: "
            + " ".join(shlex.quote(item) for item in command)
        )
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        for line in completed.stdout.splitlines():
            self._emit_automation(f"Production owner: {line}")
        result = read_json(
            EXPERIMENTS_ROOT / "production_research_cycle_result.json",
            {},
        )
        status = str(result.get("status") or "UNKNOWN")
        if completed.returncode != 0 or status not in {"COMPLETED", "REUSED"}:
            raise RuntimeError(
                "Authoritative production owner failed"
                f" at {result.get('failed_stage') or 'UNKNOWN'}: "
                f"{result.get('error') or status}"
            )
        return result

    @staticmethod
    def _request_action_key(payload: dict[str, Any]) -> str | None:
        preferred = (
            "commit", "authorize", "dispatch", "claim",
            "authorize_start", "run_loop", "run_cycle",
            "execute", "start", "continue_cycle",
        )
        for key in preferred:
            if key in payload and payload.get(key) is False:
                return key
        return None

    def _prepare_stage_request(
        self,
        request_path: Path,
        target_runtime_id: str | None = None,
    ) -> bool:
        payload = read_json(request_path, {})
        if not isinstance(payload, dict) or not payload:
            return False
        action_key = self._request_action_key(payload)
        # A refused launch-authorization request remains actionable on disk
        # (authorize=true) so the gateway can preserve the exact evidence that
        # failed.  On a later, explicitly confirmed scoped continuation, turn
        # only that matching refused request back into an inactive template.
        # This lets the normal preparation path mint a fresh one-shot AUTH id.
        if (
            not action_key
            and target_runtime_id
            and request_path.name == "launch_authorization_request.json"
            and payload.get("authorize") is True
        ):
            prior_result = read_json(
                request_path.parent / "launch_authorization_result.json",
                {},
            )
            if (
                isinstance(prior_result, dict)
                and prior_result.get("status") == "REFUSED"
                and prior_result.get("authorized") is False
                and str(prior_result.get("runtime_id") or "")
                == target_runtime_id
                and str(payload.get("runtime_id") or "")
                == target_runtime_id
            ):
                payload["authorize"] = False
                payload["authorization_id"] = None
                action_key = "authorize"
        # Execution dispatch has the same one-shot retry boundary.  A refused
        # request is intentionally left with dispatch=true as immutable
        # evidence of the failed attempt.  After a new explicit confirmation,
        # recycle only a REFUSED request for the selected runtime into an
        # inactive template.  Scoped preparation below then resolves the
        # current verified authorization and mints a fresh DISPATCH identity.
        if (
            not action_key
            and target_runtime_id
            and request_path.name == "execution_dispatch_request.json"
            and payload.get("dispatch") is True
        ):
            prior_result = read_json(
                request_path.parent / "execution_dispatch_result.json",
                {},
            )
            if (
                isinstance(prior_result, dict)
                and prior_result.get("status") == "REFUSED"
                and prior_result.get("dispatched") is False
                and str(prior_result.get("runtime_id") or "")
                == target_runtime_id
                and str(payload.get("runtime_id") or "")
                == target_runtime_id
            ):
                payload["dispatch"] = False
                payload["dispatch_id"] = None
                action_key = "dispatch"
        if not action_key:
            return False
        if target_runtime_id and action_key in {"authorize", "dispatch"}:
            runtime_registry = read_json(RUNTIME_REGISTRY_FILE, {})
            runtime_entries = {
                str(item.get("runtime_id")): item
                for item in (
                    runtime_registry.get("packages", [])
                    if isinstance(runtime_registry, dict)
                    else []
                )
                if isinstance(item, dict) and item.get("runtime_id")
            }
            runtime_entry = runtime_entries.get(target_runtime_id)
            if runtime_entry is None:
                return False
            if action_key == "authorize":
                if (
                    runtime_entry.get("status")
                    != "READY_FOR_LAUNCH_REVIEW"
                    or runtime_entry.get("launch_authorized") is not False
                    or int(runtime_entry.get("unresolved_count") or 0) != 0
                ):
                    return False
                payload.update({
                    "runtime_id": target_runtime_id,
                    "expected_runtime_hash": runtime_entry.get("runtime_hash"),
                    "expected_runtime_registry_hash": (
                        runtime_registry.get("content_hash")
                    ),
                })
            else:
                if (
                    runtime_entry.get("status") != "LAUNCH_AUTHORIZED"
                    or runtime_entry.get("launch_authorized") is not True
                ):
                    return False
                authorization_registry = read_json(
                    LAUNCH_AUTHORIZATION_REGISTRY_FILE, {}
                )
                authorization_entries = [
                    item
                    for item in (
                        authorization_registry.get("authorizations", [])
                        if isinstance(authorization_registry, dict)
                        else []
                    )
                    if (
                        isinstance(item, dict)
                        and str(item.get("runtime_id") or "")
                        == target_runtime_id
                        and item.get("verification_status") == "VERIFIED"
                        and item.get("execution_started") is not True
                        and item.get("lifecycle_status", "ACTIVE") == "ACTIVE"
                        and item.get("superseded") is not True
                    )
                ]
                if len(authorization_entries) != 1:
                    return False
                dispatch_registry = read_json(
                    EXPERIMENTS_ROOT / "execution_dispatch_registry.json", {}
                )
                if any(
                    isinstance(item, dict)
                    and str(item.get("runtime_id") or "")
                    == target_runtime_id
                    and item.get("status") != "SUPERSEDED"
                    for item in (
                        dispatch_registry.get("jobs", [])
                        if isinstance(dispatch_registry, dict)
                        else []
                    )
                ):
                    return False
                authorization = authorization_entries[0]
                payload.update({
                    "runtime_id": target_runtime_id,
                    "authorization_id": authorization.get(
                        "authorization_id"
                    ),
                    "expected_runtime_hash": runtime_entry.get("runtime_hash"),
                    "expected_runtime_registry_hash": (
                        runtime_registry.get("content_hash")
                    ),
                    "expected_authorization_registry_hash": (
                        authorization_registry.get("content_hash")
                    ),
                })
        # A refreshed template only becomes actionable when its target identity
        # and expected hashes have been resolved by the authoritative module.
        target_keys = (
            "draft_id", "runtime_id", "job_id", "claim_id",
            "manifest_id", "cycle_id",
        )
        has_target = any(payload.get(key) not in (None, "") for key in target_keys)
        if action_key not in {"run_loop", "continue_cycle"} and not has_target:
            return False
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        payload[action_key] = True
        payload["requested_at"] = datetime.now().astimezone().isoformat()
        payload["requested_by"] = "Observer Laboratory v3.5"
        # launch_authorization_request.json has two different identities:
        # runtime_id identifies the target while authorization_id identifies
        # this one-shot human-authorized action.  The inactive template leaves
        # authorization_id empty, so recovery must mint it after the user has
        # explicitly confirmed Continue Authorized Pipeline.  Generic *_id
        # filling intentionally excludes authorization_id because downstream
        # requests use it as a foreign key.
        if (
            action_key == "authorize"
            and not payload.get("authorization_id")
        ):
            payload["authorization_id"] = f"AUTH-{stamp}"
        instructions = payload.get("instructions", {})
        if isinstance(instructions, dict):
            confirmation = instructions.get("required_confirmation")
            if confirmation:
                payload["confirmation"] = confirmation
        for key in tuple(payload):
            if key.endswith("_id") and payload.get(key) is None and key not in {
                "draft_id", "runtime_id", "job_id", "claim_id",
                "authorization_id", "manifest_id", "task_id",
            }:
                payload[key] = f"AUTO-{stamp}"
        # The execution orchestrators expose autosave_every in their request.
        # Resolve it from the longest currently materialized task.
        if "autosave_every" in payload:
            registry = read_json(RUNTIME_REGISTRY_FILE, {})
            horizons: list[int] = []
            for entry in registry.get("packages", []) if isinstance(registry, dict) else []:
                package = read_json(Path(str(entry.get("package_path") or "")), {})
                runtime = package.get("runtime", {}) if isinstance(package, dict) else {}
                for row in runtime.get("run_matrix", []) if isinstance(runtime, dict) else []:
                    try:
                        horizons.append(int(row.get("duration_ticks") or 0))
                    except Exception:
                        pass
            payload["autosave_every"] = self._adaptive_autosave_for_ticks(
                max(horizons) if horizons else 0
            )
        atomic_json(request_path, payload)
        return True

    def _automate_action_stage(
        self, label: str, module: Path, request_name: str,
        *, maximum: int = 100,
        target_runtime_id: str | None = None,
    ) -> int:
        actions = 0
        for _ in range(maximum):
            if self.automated_research_stop.is_set():
                break
            # First pass refreshes the inactive request template and registries.
            rc = self._run_stage_module(label, module)
            if rc not in (0, 1):
                break
            request_path = EXPERIMENTS_ROOT / request_name
            if not self._prepare_stage_request(
                request_path,
                target_runtime_id=target_runtime_id,
            ):
                break
            rc = self._run_stage_module(label, module)
            if rc != 0:
                break
            actions += 1
        return actions

    def refresh_director_proposals(self) -> None:
        report = read_json(RESEARCH_DIRECTOR_REPORT_FILE, {})
        self._director_proposals = {}
        if hasattr(self, "director_tree"):
            self.director_tree.delete(*self.director_tree.get_children())
        if not isinstance(report, dict) or not report:
            self.director_summary_var.set(
                "Research Director report is missing. Run Analyzer first."
            )
            self._update_director_primary_button()
            return

        actions = {
            str(row.get("action_id")): row
            for row in report.get("actions", [])
            if isinstance(row, dict) and row.get("action_id")
        }
        proposals_container = report.get(
            "recommendation_patch_proposals", {}
        )
        proposals = (
            proposals_container.get("proposals", [])
            if isinstance(proposals_container, dict)
            else []
        )
        validation_container = report.get(
            "patch_proposal_validation", {}
        )
        validation_by_proposal = {
            str(row.get("proposal_id")): row
            for row in (
                validation_container.get("validations", [])
                if isinstance(validation_container, dict)
                else []
            )
            if isinstance(row, dict) and row.get("proposal_id")
        }
        resolution_container = report.get(
            "patch_conflict_resolution_plan", {}
        )
        resolution_by_proposal = {
            str(row.get("proposal_id")): row
            for row in (
                resolution_container.get("plans", [])
                if isinstance(resolution_container, dict)
                else []
            )
            if isinstance(row, dict) and row.get("proposal_id")
        }
        review_queue_container = report.get("human_review_queue", {})
        review_by_proposal = {
            str(row.get("proposal_id")): row
            for row in (
                review_queue_container.get("queue", [])
                if isinstance(review_queue_container, dict)
                else []
            )
            if isinstance(row, dict) and row.get("proposal_id")
        }

        decisions = read_json(HUMAN_REVIEW_DECISIONS_FILE, {})
        decision_by_proposal = {
            str(row.get("proposal_id")): str(
                row.get("decision") or ""
            ).upper()
            for row in (
                decisions.get("records", [])
                if isinstance(decisions, dict)
                else []
            )
            if isinstance(row, dict) and row.get("proposal_id")
        }

        counts = {
            "VALID": 0,
            "CONFLICTING": 0,
            "BLOCKED": 0,
            "OTHER": 0,
            "APPROVED": 0,
        }
        for proposal in proposals:
            if not isinstance(proposal, dict):
                continue
            proposal_id = str(proposal.get("proposal_id") or "")
            if not proposal_id:
                continue
            action_id = str(proposal.get("target_action_id") or "")
            action = actions.get(action_id, {})
            validation = validation_by_proposal.get(proposal_id, {})
            resolution = resolution_by_proposal.get(proposal_id, {})
            review = review_by_proposal.get(proposal_id, {})
            decision = decision_by_proposal.get(
                proposal_id,
                str(review.get("decision") or "PENDING_REVIEW").upper(),
            )
            if decision == "REJECTED":
                continue

            validation_status = str(
                validation.get("status")
                or review.get("validation_status")
                or "UNKNOWN"
            ).upper()
            resolution_type = str(
                resolution.get("resolution_type")
                or review.get("resolution_type")
                or ""
            )
            preferred_resolution = (
                resolution.get("preferred_resolution")
                or review.get("preferred_resolution")
            )
            application_allowed = bool(
                validation.get("application_allowed")
                or review.get("application_allowed")
            )

            row = {
                "proposal_id": proposal_id,
                "action_id": action_id,
                "action": action,
                "proposal": proposal,
                "decision": decision,
                "validation": validation,
                "validation_status": validation_status,
                "resolution": resolution,
                "resolution_type": resolution_type or None,
                "preferred_resolution": preferred_resolution,
                "application_allowed": application_allowed,
                "review": review,
            }
            self._director_proposals[proposal_id] = row

            if decision == "APPROVED":
                counts["APPROVED"] += 1
            if validation_status in counts:
                counts[validation_status] += 1
            else:
                counts["OTHER"] += 1

            resolution_label = (
                resolution_type.replace("_", " ").title()
                if resolution_type
                else "-"
            )
            self.director_tree.insert(
                "",
                "end",
                iid=proposal_id,
                values=(
                    action.get("priority", "-"),
                    action_id or "-",
                    action.get("title")
                    or proposal.get("title")
                    or proposal_id,
                    validation_status,
                    resolution_label,
                    action.get("estimated_runtime") or "-",
                ),
            )

        self.director_summary_var.set(
            f"Valid: {counts['VALID']} | "
            f"Conflicting: {counts['CONFLICTING']} | "
            f"Blocked: {counts['BLOCKED']} | "
            f"Approved records: {counts['APPROVED']}. "
            "Only VALID proposals can enter automated execution. "
            "Conflicts are recorded for revision; blocked proposals are deferred."
        )
        children = self.director_tree.get_children()
        if children:
            self.director_tree.selection_set(children[0])
            self.director_tree.focus(children[0])
        self._update_director_primary_button()

    def _on_director_selection_changed(self, _event: Any = None) -> None:
        self._update_director_primary_button()

    def _update_director_primary_button(self) -> None:
        button = getattr(self, "director_primary_button", None)
        tree = getattr(self, "director_tree", None)
        if button is None or tree is None:
            return
        selection = tree.selection()
        if not selection:
            button.configure(text="Select a proposal", state="disabled")
            return
        row = self._director_proposals.get(str(selection[0]), {})
        status = str(row.get("validation_status") or "UNKNOWN").upper()
        if status == "VALID":
            button.configure(text="Approve Valid & Launch", state="normal")
        elif status == "CONFLICTING":
            button.configure(
                text="Record Preferred Resolution",
                state="normal",
            )
        elif status == "BLOCKED":
            button.configure(
                text="Defer Blocked Proposal",
                state="normal",
            )
        else:
            button.configure(
                text=f"Unavailable: {status}",
                state="disabled",
            )

    def _selected_director_proposal(self) -> dict[str, Any]:
        selection = self.director_tree.selection()
        if not selection:
            raise ValueError("Select a Research Director proposal first.")
        proposal_id = str(selection[0])
        row = self._director_proposals.get(proposal_id)
        if not row:
            raise ValueError("Selected proposal is no longer available.")
        return row

    def _write_director_decision(
        self, proposal_id: str, decision: str, reason: str
    ) -> None:
        """Stage a valid editable row while preserving immutable review fields."""
        editing = read_json(HUMAN_REVIEW_EDITING_INTERFACE_FILE, {})
        rows = (
            editing.get("rows", [])
            if isinstance(editing, dict)
            else []
        )
        baseline = next(
            (
                dict(item)
                for item in rows
                if isinstance(item, dict)
                and str(item.get("proposal_id") or "") == proposal_id
            ),
            None,
        )
        if baseline is None:
            raise RuntimeError(
                "The selected proposal is absent from "
                "human_review_editing_interface.json."
            )

        # Preserve immutable fields exactly as emitted by Research Director:
        # review_id, proposal_id, priority, validation status, and preferred
        # resolution. Only the explicitly editable review fields are changed.
        stamp = datetime.now().astimezone().isoformat()
        candidate = dict(baseline)
        candidate.update(
            {
                "current_decision": str(decision).upper(),
                "decision_reason": reason,
                "reviewed_by": "observer_laboratory_human",
                "reviewed_at": stamp,
                "selected_resolution": baseline.get(
                    "selected_resolution"
                ),
                "revision_notes": (
                    "Conflict-aware review recorded by Observer Laboratory."
                    if str(decision).upper() == "NEEDS_REVISION"
                    else "Recommitted through Observer Laboratory governance gateway."
                ),
            }
        )

        atomic_json(
            HUMAN_REVIEW_IMPORT_CANDIDATE_FILE,
            {
                "schema": "archon_review_import_candidate_v1",
                "rows": [candidate],
                "instructions": {
                    "source": "Observer Laboratory Director Approval Gateway",
                    "automatic_import": False,
                    "automatic_patch_application": False,
                    "immutable_fields_preserved": True,
                },
            },
        )

    def _run_research_director_governance_pass(self, label: str) -> int:
        if not RESEARCH_DIRECTOR_MODULE.is_file():
            self._emit_automation(
                f"Research Director module missing: {RESEARCH_DIRECTOR_MODULE}"
            )
            return 1
        command = [
            sys.executable,
            str(RESEARCH_DIRECTOR_MODULE),
            str(SEARCH_RESULTS_DIR),
            "--root",
            str(ANALYSIS_RESULTS_DIR),
        ]
        self._emit_automation(
            f"{label}: {' '.join(shlex.quote(x) for x in command)}"
        )
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        for line in completed.stdout.splitlines()[-220:]:
            self._emit_automation(f"[Director] {line}")
        return int(completed.returncode)

    def _apply_director_governance_for_proposal(
        self, proposal_id: str
    ) -> None:
        """Commit the human decision, apply its patch, and verify ACTIVE lifecycle."""
        rc = self._run_research_director_governance_pass(
            "Director review manifest"
        )
        if rc != 0:
            raise RuntimeError(
                f"Research Director review pass failed with exit code {rc}."
            )

        commit_manifest = read_json(
            HUMAN_REVIEW_COMMIT_MANIFEST_FILE, {}
        )
        if not isinstance(commit_manifest, dict) or not commit_manifest.get(
            "available"
        ):
            raise RuntimeError(
                "Director did not produce an importable human-review commit "
                "manifest for the selected proposal."
            )

        commit_id = commit_manifest.get("commit_id")
        candidate_hash = commit_manifest.get("candidate_hash")
        decision_store_hash = commit_manifest.get(
            "expected_decision_store_hash"
        )
        if not all((commit_id, candidate_hash, decision_store_hash)):
            raise RuntimeError(
                "Human-review commit manifest is missing required identifiers."
            )

        atomic_json(
            HUMAN_REVIEW_COMMIT_REQUEST_FILE,
            {
                "schema": "archon_review_commit_request_v1",
                "commit": True,
                "commit_id": commit_id,
                "candidate_hash": candidate_hash,
                "expected_decision_store_hash": decision_store_hash,
                "requested_at": datetime.now().astimezone().isoformat(),
                "requested_by": "observer_laboratory_human",
                "confirmation": "COMMIT_REVIEW_DECISIONS",
                "last_consumed_commit_id": None,
            },
        )

        rc = self._run_research_director_governance_pass(
            "Director decision commit"
        )
        if rc != 0:
            raise RuntimeError(
                f"Research Director commit pass failed with exit code {rc}."
            )

        commit_result = read_json(HUMAN_REVIEW_COMMIT_RESULT_FILE, {})
        receipt_verification = read_json(
            HUMAN_REVIEW_RECEIPT_VERIFICATION_FILE, {}
        )
        if (
            not isinstance(commit_result, dict)
            or commit_result.get("status") != "COMMITTED"
            or not isinstance(receipt_verification, dict)
            or receipt_verification.get("status")
            not in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}
        ):
            raise RuntimeError(
                "Human-review decision was not committed and verified."
            )

        application_manifest = read_json(
            PATCH_APPLICATION_MANIFEST_FILE, {}
        )
        if (
            not isinstance(application_manifest, dict)
            or not application_manifest.get("available")
            or not application_manifest.get("final_ready")
        ):
            raise RuntimeError(
                "Director approval was committed, but no safe patch application "
                "manifest is ready."
            )

        manifest_id = application_manifest.get(
            "application_manifest_id"
        )
        manifest_hash = application_manifest.get("manifest_hash")
        source_commit_id = application_manifest.get("source_commit_id")
        if not all((manifest_id, manifest_hash, source_commit_id)):
            raise RuntimeError(
                "Patch application manifest is missing required identifiers."
            )

        atomic_json(
            PATCH_APPLICATION_REQUEST_FILE,
            {
                "schema": "archon_patch_application_request_v1",
                "apply": True,
                "application_manifest_id": manifest_id,
                "manifest_hash": manifest_hash,
                "source_commit_id": source_commit_id,
                "requested_at": datetime.now().astimezone().isoformat(),
                "requested_by": "observer_laboratory_human",
                "confirmation": "APPLY_RESEARCH_ACTION_PATCHES",
            },
        )

        rc = self._run_research_director_governance_pass(
            "Director patch application"
        )
        if rc != 0:
            raise RuntimeError(
                f"Research Director application pass failed with exit code {rc}."
            )

        application_result = read_json(
            PATCH_APPLICATION_RESULT_FILE, {}
        )
        application_receipt = read_json(
            PATCH_APPLICATION_RECEIPT_VERIFICATION_FILE, {}
        )
        lifecycle = read_json(PATCH_LIFECYCLE_CLOSURE_FILE, {})
        if (
            not isinstance(application_result, dict)
            or application_result.get("status") != "APPLIED"
            or not isinstance(application_receipt, dict)
            or application_receipt.get("status")
            not in {"VERIFIED", "VERIFIED_WITH_WARNINGS"}
            or not isinstance(lifecycle, dict)
            or lifecycle.get("status") != "ACTIVE"
        ):
            raise RuntimeError(
                "Governance patch was not applied as an ACTIVE verified lifecycle."
            )

        self._emit_automation(
            f"Governance ACTIVE for proposal {proposal_id}: "
            f"{application_receipt.get('application_id') or '-'}"
        )

    def approve_selected_director_proposal_and_launch(self) -> None:
        try:
            row = self._selected_director_proposal()
        except Exception as exc:
            messagebox.showerror("Director approval", str(exc))
            return

        action = row.get("action", {})
        proposal_id = str(row.get("proposal_id"))
        title = str(action.get("title") or proposal_id)
        rationale = str(
            action.get("rationale") or "No rationale supplied."
        )
        done_when = str(action.get("done_when") or "Not declared.")
        validation_status = str(
            row.get("validation_status") or "UNKNOWN"
        ).upper()
        resolution_type = str(row.get("resolution_type") or "")
        preferred_resolution = str(
            row.get("preferred_resolution") or ""
        )

        if validation_status == "BLOCKED":
            reason = preferred_resolution or (
                "This proposal depends on unresolved scientific prerequisites."
            )
            if not messagebox.askyesno(
                "Defer blocked proposal",
                f"{title}\n\nThis proposal is BLOCKED and cannot be "
                f"executed safely.\n\nDirector guidance:\n{reason}\n\n"
                "Record it as DEFERRED?",
            ):
                return
            self._write_director_decision(
                proposal_id,
                "DEFERRED",
                "Deferred in Observer Laboratory until Director dependencies "
                "are resolved and the proposal is revalidated.",
            )
            self.refresh_director_proposals()
            self.automated_research_status_var.set(
                f"Deferred blocked proposal {proposal_id}. "
                "No execution was started."
            )
            return

        if validation_status == "CONFLICTING":
            resolution_text = preferred_resolution or (
                "A manual resolution is required before this proposal can "
                "become VALID."
            )
            if not messagebox.askyesno(
                "Record conflict resolution",
                f"{title}\n\nValidation: CONFLICTING\n"
                f"Resolution type: {resolution_type or '-'}\n\n"
                f"Director guidance:\n{resolution_text}\n\n"
                "Record this preferred resolution as NEEDS_REVISION?\n\n"
                "This does not launch the experiment. The Director must "
                "produce a new VALID proposal after reconciliation.",
            ):
                return
            self._write_director_decision(
                proposal_id,
                "NEEDS_REVISION",
                "Conflict-aware review recorded in Observer Laboratory. "
                f"Requested resolution: {resolution_type or resolution_text}",
            )
            self.refresh_director_proposals()
            self.automated_research_status_var.set(
                f"Resolution recorded for {proposal_id}. "
                "Awaiting a revalidated VALID proposal; no execution started."
            )
            return

        if validation_status != "VALID":
            messagebox.showwarning(
                "Proposal unavailable",
                f"Proposal status is {validation_status}. "
                "Only VALID proposals can enter automated execution.",
            )
            return

        if not messagebox.askyesno(
            "Approve valid Research Director proposal",
            f"Approve and launch this VALID research direction?\n\n"
            f"{title}\n\nWhy:\n{rationale}\n\n"
            f"Done when:\n{done_when}\n\n"
            "The audited governance chain will commit the decision, apply "
            "the verified patch, then pass it to Stage 6 and Stage 7.",
        ):
            return

        self._write_director_decision(
            proposal_id,
            "APPROVED",
            "Approved in Observer Laboratory for automated execution after "
            "VALID proposal verification.",
        )
        self._approved_proposal_for_cycle = proposal_id
        self.refresh_director_proposals()
        self.launch_automated_research_queue()

    def reject_selected_director_proposal(self) -> None:
        try:
            row = self._selected_director_proposal()
        except Exception as exc:
            messagebox.showerror("Director rejection", str(exc))
            return
        proposal_id = str(row.get("proposal_id"))
        if not messagebox.askyesno(
            "Reject Research Director proposal",
            f"Reject proposal {proposal_id}?",
        ):
            return
        self._write_director_decision(
            proposal_id, "REJECTED", "Rejected in Observer Laboratory."
        )
        self.refresh_director_proposals()

    def _run_full_analyzer_for_governance(self) -> int:
        if not ANALYZER_ENTRYPOINT.is_file():
            self._emit_automation(f"Analyzer entrypoint missing: {ANALYZER_ENTRYPOINT}")
            return 1
        self._emit_automation("Refreshing Analyzer and Research Director governance state…")
        completed = subprocess.run(
            [*runtime_python_command(PROJECT_ROOT), str(ANALYZER_ENTRYPOINT)],
            cwd=str(PROJECT_ROOT), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        for line in completed.stdout.splitlines()[-300:]:
            self._emit_automation(f"[Analyzer] {line}")
        return int(completed.returncode)

    def _approve_planner_drafts_for_proposal(self, proposal_id: str) -> int:
        drafts_path = EXPERIMENTS_ROOT / "experiment_planner_drafts.json"
        drafts = read_json(drafts_path, {})
        if not isinstance(drafts, dict):
            return 0
        rows = []
        for draft in drafts.get("drafts", []):
            if not isinstance(draft, dict):
                continue
            provenance = draft.get("provenance", {})
            if not isinstance(provenance, dict):
                continue
            if str(provenance.get("source_proposal_id")) != proposal_id:
                continue
            if draft.get("source_active") is not True:
                continue
            validation = draft.get("validation", {})
            if isinstance(validation, dict) and validation.get("valid") is False:
                continue
            rows.append({
                "draft_id": draft.get("draft_id"),
                "expected_draft_hash": draft.get("draft_hash"),
                "decision": "APPROVED",
                "reviewed_at": datetime.now().astimezone().isoformat(),
                "reviewed_by": "observer_laboratory_human",
                "decision_reason": "Covered by explicit Director proposal approval.",
                "required_changes": [],
                "editable_patch": {},
            })
        if not rows:
            return 0
        atomic_json(PLANNER_REVIEW_EDITOR_FILE, {
            "schema": "archon_planner_review_editor_v1",
            "generated_at": datetime.now().astimezone().isoformat(),
            "mode": "SAFE_EDITOR",
            "rows": rows,
        })
        return len(rows)

    def copy_observer_log(self) -> None:
        content = self.output.get("1.0", "end-1c")
        if not content.strip():
            self.bell()
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update_idletasks()
        self.automated_research_status_var.set(
            f"Observer log copied to clipboard ({len(content):,} characters)."
        )

    def launch_automated_research_queue(self) -> None:
        if self.automated_research_running:
            messagebox.showinfo(
                "Automated research", "The automated queue is already running."
            )
            return
        if self.process is not None:
            messagebox.showwarning(
                "Observer is running",
                "Stop the manually launched Observer before starting automation.",
            )
            return
        self.automated_research_stop.clear()
        self.automated_research_running = True
        self.automated_research_status_var.set(
            "Starting Stage 6 → Stage 7 automated research queue…"
        )
        threading.Thread(
            target=self._automated_research_worker, daemon=True
        ).start()

    def continue_authorized_pipeline(self) -> None:
        if self.automated_research_running:
            messagebox.showinfo(
                "Authorized pipeline",
                "A production pipeline is already running.",
            )
            return
        if self.process is not None:
            messagebox.showwarning(
                "Observer is running",
                "Stop the manually launched Observer before continuing "
                "the authorized production pipeline.",
            )
            return
        selected_runtime_ids = self.production_tree.selection()
        if len(selected_runtime_ids) != 1:
            messagebox.showwarning(
                "Select one production plan",
                "Select exactly one runtime row in the lower production "
                "table. Its committed plan will be recovered; other plans "
                "will remain untouched.",
            )
            return
        selected_entry = self._production_packages.get(
            str(selected_runtime_ids[0]), {}
        )
        selected_runtime_id = str(
            selected_entry.get("runtime_id") or selected_runtime_ids[0]
        ).strip()
        selected_plan_id = str(selected_entry.get("plan_id") or "").strip()
        if not selected_plan_id:
            messagebox.showwarning(
                "Plan identity missing",
                "The selected runtime does not contain a committed plan_id.",
            )
            return
        selected_status = str(selected_entry.get("status") or "")
        if selected_status == "READY_FOR_LAUNCH_REVIEW":
            transition_text = (
                "The selected materialized runtime will be authorized, "
                "queued, and handed to the authoritative production owner. "
                "It will not be rematerialized."
            )
        else:
            transition_text = (
                "Outdated pre-E.3/E.4/E.5 runtimes will be marked SUPERSEDED "
                "and rebuilt from their verified committed plans. A current "
                "authorized runtime will continue through dispatch and the "
                "authoritative production owner."
            )
        if not messagebox.askyesno(
            "Continue authorized production pipeline?",
            (
                "Continue the selected production pipeline?\n\n"
                f"Selected runtime: {selected_runtime_id}\n"
                f"Selected plan: {selected_plan_id}\n\n"
                f"{transition_text}\n\n"
                "Multi-rule plans keep every declared independent parent "
                "rule and create a matched baseline/treatment group for each.\n\n"
                "This starts real Observer execution."
            ),
        ):
            return
        self._authorized_recovery_plan_ids = [selected_plan_id]
        self._authorized_recovery_runtime_id = selected_runtime_id
        self.automated_research_stop.clear()
        self.automated_research_running = True
        self.automated_research_status_var.set(
            "Reconciling and continuing authorized production work…"
        )
        threading.Thread(
            target=self._authorized_recovery_worker,
            daemon=True,
        ).start()

    def stop_automated_research_queue(self) -> None:
        self.automated_research_stop.set()
        self.automated_research_status_var.set(
            "Safe stop requested. The current module/run will finish first."
        )
        self._emit_automation("Safe stop requested.")

    def _authorized_recovery_worker(self) -> None:
        try:
            selected_plan_ids = list(
                getattr(self, "_authorized_recovery_plan_ids", [])
            )
            selected_runtime_id = str(
                getattr(self, "_authorized_recovery_runtime_id", "") or ""
            ).strip()
            selected_entry = self._production_packages.get(
                selected_runtime_id, {}
            )
            selected_status = str(selected_entry.get("status") or "")
            total_actions = 0
            superseded = 0
            if selected_status == "READY_FOR_LAUNCH_REVIEW":
                self._emit_automation(
                    "Selected runtime is already materialized: "
                    f"{selected_runtime_id}. Continuing with scoped "
                    "authorization and dispatch."
                )
                authorization_actions = self._automate_action_stage(
                    "Launch authorization",
                    compatibility_route("experiment_launch_authorization.py"),
                    "launch_authorization_request.json",
                    maximum=1,
                    target_runtime_id=selected_runtime_id,
                )
                if authorization_actions != 1:
                    raise RuntimeError(
                        "Selected READY_FOR_LAUNCH_REVIEW runtime was not "
                        "authorized."
                    )
                dispatch_actions = self._automate_action_stage(
                    "Execution dispatch",
                    compatibility_route("experiment_execution_dispatch.py"),
                    "execution_dispatch_request.json",
                    maximum=1,
                    target_runtime_id=selected_runtime_id,
                )
                if dispatch_actions != 1:
                    raise RuntimeError(
                        "Selected launch-authorized runtime was not queued."
                    )
                total_actions += authorization_actions + dispatch_actions
                mode = "READY_RUNTIME_CONTINUED"
            else:
                recovery = self._run_runtime_recovery(selected_plan_ids)
                mode = str(recovery.get("mode") or "UNKNOWN")
                superseded = int(recovery.get("superseded_count") or 0)
                self._emit_automation(
                    f"Recovery mode={mode}; superseded={superseded}."
                )
                if mode == "NO_RECOVERABLE_RUNTIME":
                    raise RuntimeError(
                        "No stranded launch-authorized runtime is available."
                    )

            if mode == "NEEDS_REMATERIALIZATION":
                recoverable_plan_ids = [
                    str(item)
                    for item in recovery.get("recoverable_plan_ids", [])
                    if str(item).strip()
                ]
                if not recoverable_plan_ids:
                    raise RuntimeError(
                        "Recovery did not identify a committed plan to "
                        "rematerialize."
                    )
                self._emit_automation(
                    "Scoped recovery plans: "
                    + ", ".join(sorted(set(recoverable_plan_ids)))
                )
                target_result = self._run_scientific_target_resolver(
                    recoverable_plan_ids
                )
                protocol_result = self._run_scientific_protocol_resolver(
                    recoverable_plan_ids
                )
                total_actions += 2
                self._emit_automation(
                    "Recovered scientific identities: "
                    f"targets={(target_result.get('summary') or {}).get('resolved_count', 0)}, "
                    f"protocols={(protocol_result.get('summary') or {}).get('resolved_count', 0)}."
                )
                for label, filename, request_name in (
                    (
                        "Runtime materialization",
                        "experiment_runtime_materializer.py",
                        "experiment_runtime_materialization_request.json",
                    ),
                    (
                        "Launch authorization",
                        "experiment_launch_authorization.py",
                        "launch_authorization_request.json",
                    ),
                    (
                        "Execution dispatch",
                        "Analyzer_next/compatibility/legacy_analyzer/experiment_execution_dispatch.py",
                        "execution_dispatch_request.json",
                    ),
                ):
                    total_actions += self._automate_action_stage(
                        label,
                        (
                            cli_route(filename)
                            if filename == "experiment_runtime_materializer.py"
                            else compatibility_route(filename)
                        ),
                        request_name,
                    )
            elif mode == "NEEDS_DISPATCH":
                total_actions += self._automate_action_stage(
                    "Execution dispatch",
                    compatibility_route("experiment_execution_dispatch.py"),
                    "execution_dispatch_request.json",
                    maximum=1,
                    target_runtime_id=selected_runtime_id,
                )
            elif mode not in {
                "READY_TO_HANDOFF",
                "READY_RUNTIME_CONTINUED",
            }:
                raise RuntimeError(f"Unsupported recovery mode: {mode}")

            owner_cycles = 0
            while (
                not self.automated_research_stop.is_set()
                and owner_cycles < 100
            ):
                handoff_status = self._run_production_owner_handoff()
                if handoff_status == "NO_ELIGIBLE_STAGE6_TASK":
                    break
                if handoff_status != "READY":
                    raise RuntimeError(
                        "Unexpected production handoff status: "
                        f"{handoff_status}"
                    )
                owner_result = self._run_authoritative_production_owner()
                owner_cycles += 1
                total_actions += 1
                self._emit_automation(
                    "Recovered production cycle completed: "
                    f"{owner_result.get('cycle_id') or '-'} → "
                    f"{owner_result.get('final_job_status') or '-'}"
                )
            if owner_cycles >= 100:
                raise RuntimeError(
                    "Production owner safety limit reached (100 task cycles)."
                )
            if owner_cycles == 0 and not self.automated_research_stop.is_set():
                raise RuntimeError(
                    "Authorized runtime recovery produced no eligible "
                    "Stage 6 task."
                )
            status = (
                "Authorized pipeline stopped safely."
                if self.automated_research_stop.is_set()
                else (
                    "Authorized pipeline completed: "
                    f"superseded={superseded}, actions={total_actions}, "
                    f"production_cycles={owner_cycles}."
                )
            )
            self.after(0, self.automated_research_status_var.set, status)
            self._emit_automation(status)
        except Exception as exc:
            message = f"Authorized pipeline recovery failed: {exc!r}"
            self._emit_automation(message)
            self.after(
                0,
                self.automated_research_status_var.set,
                message,
            )
        finally:
            self._authorized_recovery_plan_ids = []
            self._authorized_recovery_runtime_id = None
            self.automated_research_running = False
            self.after(0, self.refresh_production_state)
            self.after(0, self.refresh_research_cycles)
            self.after(0, self.refresh_director_proposals)

    def _automated_research_worker(self) -> None:
        try:
            self._emit_automation("Automated research queue started.")
            proposal_id = self._approved_proposal_for_cycle
            if proposal_id:
                self._apply_director_governance_for_proposal(proposal_id)
            self._run_stage_module(
                "Planner intake",
                PROJECT_ROOT / "Analyzer_next/compatibility/legacy_analyzer" / "approved_action_planner_intake.py",
            )
            self._run_stage_module(
                "Planner drafts",
                cli_route("experiment_planner_review.py"),
            )
            if proposal_id:
                approved_drafts = self._approve_planner_drafts_for_proposal(proposal_id)
                if approved_drafts:
                    self._emit_automation(
                        f"Human approval propagated to {approved_drafts} planner draft(s)."
                    )
                    self._run_stage_module(
                        "Planner drafts",
                        cli_route("experiment_planner_review.py"),
                    )
            stage_specs = (
                ("Plan commit", "experiment_plan_commit.py",
                 "experiment_plan_commit_request.json"),
                ("Runtime materialization", "experiment_runtime_materializer.py",
                 "experiment_runtime_materialization_request.json"),
                ("Launch authorization", "experiment_launch_authorization.py",
                 "launch_authorization_request.json"),
                ("Execution dispatch", "experiment_execution_dispatch.py",
                 "execution_dispatch_request.json"),
            )
            total_actions = 0
            for label, filename, request_name in stage_specs:
                if self.automated_research_stop.is_set():
                    break
                module = (
                    cli_route(filename)
                    if filename in {
                        "experiment_plan_commit.py",
                        "experiment_runtime_materializer.py",
                    }
                    else compatibility_route(filename)
                )
                total_actions += self._automate_action_stage(
                    label, module, request_name
                )

                if label == "Plan commit":
                    target_result = self._run_scientific_target_resolver()
                    total_actions += 1
                    self._emit_automation(
                        "Scientific targets resolved: "
                        f"{(target_result.get('summary') or {}).get('resolved_count', 0)}"
                    )
                    protocol_result = (
                        self._run_scientific_protocol_resolver()
                    )
                    total_actions += 1
                    protocol_summary = (
                        protocol_result.get("summary") or {}
                    )
                    self._emit_automation(
                        "Scientific protocols resolved: "
                        f"{protocol_summary.get('resolved_count', 0)}; "
                        "not required: "
                        f"{protocol_summary.get('not_required_count', 0)}"
                    )

                if label == "Runtime materialization":
                    runtime_registry = read_json(RUNTIME_REGISTRY_FILE, {})
                    runtime_summary = (
                        runtime_registry.get("summary", {})
                        if isinstance(runtime_registry, dict)
                        else {}
                    )
                    unresolved_count = int(
                        runtime_summary.get(
                            "needs_runtime_resolution_count", 0
                        ) or 0
                    )
                    if unresolved_count:
                        packages = (
                            runtime_registry.get("packages", [])
                            if isinstance(runtime_registry, dict)
                            else []
                        )
                        details = []
                        for package_entry in packages:
                            if not isinstance(package_entry, dict):
                                continue
                            if package_entry.get("status") != "NEEDS_RUNTIME_RESOLUTION":
                                continue
                            package_path = Path(
                                str(package_entry.get("package_path") or "")
                            )
                            package = read_json(package_path, {})
                            fields = []
                            for item in (
                                package.get("unresolved_fields", [])
                                if isinstance(package, dict)
                                else []
                            ):
                                if isinstance(item, dict):
                                    fields.append(
                                        str(
                                            item.get("field")
                                            or item.get("path")
                                            or item.get("name")
                                            or "unknown"
                                        )
                                    )
                                else:
                                    fields.append(str(item))
                            runtime_id = str(
                                package_entry.get("runtime_id") or "-"
                            )
                            details.append(
                                f"{runtime_id}: "
                                + (", ".join(fields) if fields else "unresolved fields")
                            )
                        detail_text = "; ".join(details)
                        raise RuntimeError(
                            "Runtime materialization requires scientific target "
                            "resolution before launch"
                            + (f": {detail_text}" if detail_text else ".")
                        )

            owner_cycles = 0
            while (
                not self.automated_research_stop.is_set()
                and owner_cycles < 100
            ):
                handoff_status = self._run_production_owner_handoff()
                if handoff_status == "NO_ELIGIBLE_STAGE6_TASK":
                    break
                if handoff_status != "READY":
                    raise RuntimeError(
                        f"Unexpected production handoff status: {handoff_status}"
                    )
                owner_result = self._run_authoritative_production_owner()
                owner_cycles += 1
                total_actions += 1
                self._emit_automation(
                    "Production cycle completed: "
                    f"{owner_result.get('cycle_id') or '-'} → "
                    f"{owner_result.get('final_job_status') or '-'}"
                )
            if owner_cycles >= 100:
                raise RuntimeError(
                    "Production owner safety limit reached (100 task cycles)."
                )

            intake = read_json(
                EXPERIMENTS_ROOT / "experiment_planner_intake.json", {}
            )
            drafts = read_json(
                EXPERIMENTS_ROOT / "experiment_planner_drafts.json", {}
            )
            runtime = read_json(RUNTIME_REGISTRY_FILE, {})
            intake_count = int(
                (intake.get("summary", {}) if isinstance(intake, dict) else {}).get(
                    "record_count", 0
                ) or 0
            )
            approved_count = int(
                (drafts.get("summary", {}) if isinstance(drafts, dict) else {}).get(
                    "approved_count", 0
                ) or 0
            )
            materialized = int(
                (runtime.get("summary", {}) if isinstance(runtime, dict) else {}).get(
                    "materialized_count", 0
                ) or 0
            )
            if self.automated_research_stop.is_set():
                status = "Automated queue stopped safely."
            elif total_actions == 0 and intake_count == 0:
                status = (
                    "No governance-approved research actions are available. "
                    "Research Director/Planner must first produce an active "
                    "approved experiment."
                )
            elif total_actions == 0 and approved_count == 0:
                status = (
                    "Research actions exist, but no valid human-approved planner "
                    "draft is ready for commit."
                )
            else:
                status = (
                    f"Automated cycle finished: actions={total_actions}, "
                    f"materialized={materialized}, "
                    f"production_cycles={owner_cycles}."
                )
            self.after(0, self.automated_research_status_var.set, status)
            self.after(0, self.refresh_production_state)
            self.after(0, self.refresh_research_cycles)
            self._emit_automation(status)
        except Exception as exc:
            message = f"Automated research failed: {exc!r}"
            self._emit_automation(message)
            self.after(0, self.automated_research_status_var.set, message)
        finally:
            self.automated_research_running = False
            self._approved_proposal_for_cycle = None
            self.after(0, self.refresh_director_proposals)

    def refresh_production_state(self) -> None:
        registry = read_json(RUNTIME_REGISTRY_FILE, {})
        authorizations = read_json(
            LAUNCH_AUTHORIZATION_REGISTRY_FILE, {}
        )
        dispatch_registry = read_json(
            EXPERIMENTS_ROOT / "execution_dispatch_registry.json", {}
        )
        packages = registry.get("packages", []) if isinstance(registry, dict) else []
        auth_rows = (
            authorizations.get("authorizations", [])
            if isinstance(authorizations, dict) else []
        )
        verified_auth = {
            str(row.get("runtime_id")): row
            for row in auth_rows
            if isinstance(row, dict)
            and row.get("runtime_id")
            and row.get("verification_status") == "VERIFIED"
            and row.get("lifecycle_status", "ACTIVE") == "ACTIVE"
            and row.get("superseded") is not True
        }

        self._production_packages = {}
        self.production_tree.delete(*self.production_tree.get_children())
        for index, item in enumerate(packages):
            if not isinstance(item, dict):
                continue
            runtime_id = str(item.get("runtime_id") or "")
            if not runtime_id:
                continue
            row = dict(item)
            row["verified_authorization"] = verified_auth.get(runtime_id)
            self._production_packages[runtime_id] = row
            authorized = bool(
                item.get("launch_authorized") is True
                and item.get("status") == "LAUNCH_AUTHORIZED"
                and runtime_id in verified_auth
            )
            self.production_tree.insert(
                "", "end", iid=runtime_id,
                values=(
                    runtime_id,
                    item.get("plan_id") or "-",
                    item.get("status") or "-",
                    item.get("run_count", 0),
                    item.get("unresolved_count", 0),
                    "Yes" if authorized else "No",
                ),
            )

        summary = registry.get("summary", {}) if isinstance(registry, dict) else {}
        intake = read_json(
            EXPERIMENTS_ROOT / "experiment_planner_intake.json", {}
        )
        intake_summary = intake.get("summary", {}) if isinstance(intake, dict) else {}
        self.production_summary_var.set(
            " | ".join((
                f"Intake: {intake_summary.get('record_count', 0)}",
                f"Committed: {summary.get('committed_plan_count', 0)}",
                f"Materialized: {summary.get('materialized_count', 0)}",
                f"Ready: {summary.get('ready_for_launch_review_count', 0)}",
                f"Authorized: {summary.get('launch_authorized_count', 0)}",
                f"Lifecycle: {intake_summary.get('lifecycle_status', '-')}",
            ))
        )
        dispatch_rows = (
            dispatch_registry.get("jobs", [])
            if isinstance(dispatch_registry, dict)
            else []
        )
        dispatched_runtime_ids = {
            str(item.get("runtime_id"))
            for item in dispatch_rows
            if isinstance(item, dict)
            and item.get("runtime_id")
            and item.get("status") != "SUPERSEDED"
        }
        active_dispatch_runtime_ids = {
            str(item.get("runtime_id"))
            for item in dispatch_rows
            if isinstance(item, dict)
            and item.get("runtime_id")
            and item.get("status") in {"QUEUED", "PARTIALLY_COMPLETED"}
            and (
                item.get("pending_tasks") in (None, "")
                or int(item.get("pending_tasks") or 0) > 0
            )
        }
        start_authorized_runtime_ids = {
            str(item.get("runtime_id"))
            for item in dispatch_rows
            if isinstance(item, dict)
            and item.get("runtime_id")
            and item.get("status") == "START_AUTHORIZED"
            and item.get("verification_status") == "VERIFIED"
            and item.get("execution_started") is False
            and item.get("observer_invoked") is False
        }
        recoverable = False
        for item in packages:
            if not isinstance(item, dict):
                continue
            runtime_id = str(item.get("runtime_id") or "")
            if item.get("status") == "SUPERSEDED":
                recoverable = True
                break
            if (
                item.get("status") == "READY_FOR_LAUNCH_REVIEW"
                and item.get("launch_authorized") is False
                and int(item.get("unresolved_count") or 0) == 0
            ):
                recoverable = True
                break
            if (
                item.get("status") == "LAUNCH_AUTHORIZED"
                and item.get("launch_authorized") is True
                and (
                    runtime_id not in dispatched_runtime_ids
                    or runtime_id in active_dispatch_runtime_ids
                    or runtime_id in start_authorized_runtime_ids
                )
            ):
                recoverable = True
                break
        if hasattr(self, "production_continue_button"):
            self.production_continue_button.configure(
                state="normal" if recoverable else "disabled"
            )
        if packages:
            first = str(packages[0].get("runtime_id") or "")
            if first and first in self._production_packages:
                self.production_tree.selection_set(first)
                self.production_tree.focus(first)

    def refresh_research_cycles(self) -> None:
        catalog = load_research_cycle_catalog()
        records = catalog.get("records", [])
        self._research_cycles = {}
        self.research_cycle_tree.delete(
            *self.research_cycle_tree.get_children()
        )
        for record in records:
            if not isinstance(record, dict):
                continue
            cycle_id = str(record.get("cycle_id") or "")
            if not cycle_id:
                continue
            self._research_cycles[cycle_id] = record
            observer_ids = record.get("observer_run_ids", [])
            observer_id = (
                str(observer_ids[0])
                if isinstance(observer_ids, list) and observer_ids
                else "-"
            )
            blockers = record.get("blockers", [])
            blocker_count = (
                len(blockers) if isinstance(blockers, list) else 0
            )
            integrity = (
                str(record.get("receipt_integrity") or "NOT_VERIFIED")
                if record.get("record_verified") is True
                else "RECORD_INVALID"
            )
            self.research_cycle_tree.insert(
                "",
                "end",
                iid=cycle_id,
                values=(
                    cycle_id,
                    observer_id,
                    record.get("current_stage") or "-",
                    record.get("next_required_action") or "-",
                    integrity,
                    blocker_count,
                ),
            )

        self.research_cycle_summary_var.set(
            " | ".join(
                (
                    f"Cycles: {catalog.get('count', 0)}",
                    f"Blocked: {catalog.get('blocked_count', 0)}",
                    (
                        "Index: VERIFIED"
                        if catalog.get("index_verified") is True
                        else "Index: NOT VERIFIED"
                    ),
                    f"Invalid: {catalog.get('invalid_count', 0)}",
                    f"Missing: {catalog.get('missing_count', 0)}",
                )
            )
        )
        if records:
            first = str(records[0].get("cycle_id") or "")
            if first and first in self._research_cycles:
                self.research_cycle_tree.selection_set(first)
                self.research_cycle_tree.focus(first)

    def open_selected_research_cycle(self) -> None:
        selection = self.research_cycle_tree.selection()
        if not selection:
            messagebox.showwarning(
                "No research cycle selected",
                "Select an authoritative research cycle first.",
            )
            return
        record = self._research_cycles.get(str(selection[0]), {})
        path = Path(str(record.get("record_path") or ""))
        open_path(path)

    def _selected_runtime_entry(self) -> dict[str, Any]:
        selection = self.production_tree.selection()
        if not selection:
            raise ValueError("Select a production runtime package first.")
        runtime_id = str(selection[0])
        entry = self._production_packages.get(runtime_id)
        if entry is None:
            raise ValueError("The selected runtime is no longer available.")
        return entry

    def open_selected_runtime_package(self) -> None:
        try:
            entry = self._selected_runtime_entry()
            path = Path(str(entry.get("package_path") or ""))
            open_path(path)
        except Exception as exc:
            messagebox.showerror("Could not open runtime", str(exc))

    @staticmethod
    def _runtime_topology(value: Any) -> str:
        aliases = {
            "TORUS": "torus", "torus": "torus",
            "PLANE": "bounded", "bounded": "bounded",
        }
        resolved = aliases.get(str(value))
        if resolved is None:
            raise ValueError(f"Unsupported runtime topology: {value!r}")
        return resolved

    @staticmethod
    def _runtime_boundary(value: Any) -> str:
        aliases = {
            "PERIODIC": "wrap", "WRAP": "wrap", "wrap": "wrap",
            "FIXED_DEAD": "fixed_dead", "fixed_dead": "fixed_dead",
            "FIXED_ALIVE": "fixed_alive", "fixed_alive": "fixed_alive",
            "REFLECTIVE": "reflective", "reflective": "reflective",
        }
        resolved = aliases.get(str(value))
        if resolved is None:
            raise ValueError(f"Unsupported runtime boundary: {value!r}")
        return resolved

    def _runtime_runs(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        package_path = Path(str(entry.get("package_path") or ""))
        package = read_json(package_path, {})
        if not isinstance(package, dict) or not package:
            raise ValueError(f"Runtime package is missing: {package_path}")
        unresolved = package.get("unresolved_fields", [])
        if unresolved:
            fields = ", ".join(
                str(row.get("field") or row)
                for row in unresolved
                if isinstance(row, dict)
            )
            raise ValueError(
                "Runtime has unresolved fields and cannot be queued: " + fields
            )
        runtime = package.get("runtime", {})
        matrix = runtime.get("run_matrix", []) if isinstance(runtime, dict) else []
        if not matrix:
            raise ValueError("Runtime package contains an empty run_matrix.")
        package_rule_id = runtime.get("rule_id")
        if package_rule_id is None and matrix:
            package_rule_id = matrix[0].get("rule_id")
        if package_rule_id is None:
            if self.selected_rule is None:
                raise ValueError(
                    "Runtime does not contain rule_id. Select the target rule "
                    "in Rule Browser before loading it."
                )
            rule_id = int(self.selected_rule["rule_id"])
        else:
            rule_id = int(str(package_rule_id))
        runtime_id = str(package.get("runtime_id") or entry.get("runtime_id"))
        plan_id = str(runtime.get("plan_id") or entry.get("plan_id") or runtime_id)
        sample_every = int(runtime.get("sample_interval") or self.sample_every_var.get())
        field_default = runtime.get("field_size") or [96, 64]

        runs: list[dict[str, Any]] = []
        for row in matrix:
            if not isinstance(row, dict):
                continue
            field = row.get("field_size") or field_default
            if not isinstance(field, (list, tuple)) or len(field) != 2:
                raise ValueError(f"Invalid field_size in {row.get('run_id')}")
            run_id = str(row.get("run_id") or "")
            if not run_id:
                raise ValueError("Runtime run is missing run_id.")
            context = {
                "experiment_id": plan_id,
                "condition_id": run_id,
                "role": str(row.get("role") or "TREATMENT").lower(),
                "replicate_index": int(row.get("replicate_index") or 0),
                "field_width": int(field[0]),
                "field_height": int(field[1]),
                "topology": self._runtime_topology(row.get("topology")),
                "boundary_mode": self._runtime_boundary(
                    row.get("boundary_condition")
                ),
                "initial_state_mode": "random_seed",
                "seed": int(row.get("seed")) if row.get("seed") is not None else None,
                "runtime_id": runtime_id,
                "plan_id": plan_id,
                "production_run_id": run_id,
            }
            runs.append({
                "mutation_id": None,
                "run_dir": Path(str(row.get("output_directory"))),
                "run_output_dir": Path(str(row.get("output_directory"))),
                "rule_file": None,
                "manifest_file": package_path,
                "mode": "production_experiment_plan",
                "rule_id": int(str(row.get("rule_id") or rule_id)),
                "experimental_context": context,
                "max_ticks_override": int(row.get("duration_ticks") or 0),
                "sample_every_override": sample_every,
                "pressure_every_override": int(self.pressure_every_var.get()),
                "production_runtime_id": runtime_id,
                "production_plan_id": plan_id,
                "production_run_id": run_id,
                "status": "Waiting",
            })
        return runs

    def load_selected_runtime_queue(self, *, launch: bool = False) -> None:
        try:
            entry = self._selected_runtime_entry()
            authorized = bool(
                entry.get("status") == "LAUNCH_AUTHORIZED"
                and entry.get("launch_authorized") is True
                and entry.get("verified_authorization")
            )
            if launch and not authorized:
                raise ValueError(
                    "This runtime is not launch-authorized with a verified "
                    "authorization receipt. Load is allowed for preview only."
                )
            runs = self._runtime_runs(entry)
        except Exception as exc:
            messagebox.showerror("Could not load production runtime", str(exc))
            return

        if self.process is not None:
            messagebox.showwarning(
                "Observer is running", "Stop the current Observer first."
            )
            return
        if self.batch_queue and not messagebox.askyesno(
            "Replace waiting queue?",
            f"Replace {len(self.batch_queue)} waiting run(s) with this runtime?",
        ):
            return
        package_path = Path(str(entry.get("package_path") or ""))
        package = read_json(package_path, {})
        runtime = package.get("runtime", {}) if isinstance(package, dict) else {}
        matrix = runtime.get("run_matrix", []) if isinstance(runtime, dict) else []
        carries_rule = bool(
            runtime.get("rule_id")
            or any(isinstance(row, dict) and row.get("rule_id") for row in matrix)
        )
        if not carries_rule:
            if self.selected_rule is None:
                messagebox.showerror(
                    "Rule selection required",
                    "Select the target rule in Rule Browser first.",
                )
                return
            if not messagebox.askyesno(
                "Bind runtime to selected rule",
                (
                    f"Runtime {entry.get('runtime_id')} does not contain rule_id.\n\n"
                    f"Bind all {len(runs)} run(s) to selected Rule "
                    f"{normalize_rule_id(self.selected_rule['rule_id'])}?"
                ),
            ):
                return

        self.batch_queue = list(runs)
        self.queue_runs = list(runs)
        self._refresh_queue()
        self.notebook.select(self.queue_tab)
        self.status_var.set(
            f"Loaded production runtime {entry.get('runtime_id')}: {len(runs)} run(s)"
        )
        if launch:
            self.start_queue()

    def launch_selected_runtime_queue(self) -> None:
        self.load_selected_runtime_queue(launch=True)

    def _build_mutation_tab(self) -> None:
        body = ttk.Panedwindow(
            self.mutation_tab,
            orient="horizontal",
        )
        body.pack(fill="both", expand=True)

        controls = ttk.Frame(body)
        preview = ttk.Frame(body)
        body.add(controls, weight=2)
        body.add(preview, weight=3)

        selected = ttk.LabelFrame(
            controls, text="Parent Rule", padding=10
        )
        selected.pack(fill="x", pady=(0, 10))
        self.mutation_selected_label = tk.StringVar(
            value="No rule selected"
        )
        ttk.Label(
            selected,
            textvariable=self.mutation_selected_label,
            style="Subheader.TLabel",
        ).pack(anchor="w")

        settings = ttk.LabelFrame(
            controls, text="Mutation Settings", padding=10
        )
        settings.pack(fill="x")

        ttk.Label(settings, text="Mode").grid(
            row=0, column=0, sticky="w"
        )
        self.mode_combo = ttk.Combobox(
            settings,
            textvariable=self.mutation_mode_var,
            values=("none", "single_parameter", "local_random", "preset"),
            state="readonly",
            width=24,
        )
        self.mode_combo.grid(
            row=0, column=1, sticky="ew", padx=(10, 0)
        )
        self.mode_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._mutation_mode_changed(),
        )

        ttk.Label(settings, text="Parameter").grid(
            row=1, column=0, sticky="w"
        )
        self.parameter_combo = ttk.Combobox(
            settings,
            textvariable=self.mutation_parameter_var,
            state="readonly",
            width=24,
        )
        self.parameter_combo.grid(
            row=1, column=1, sticky="ew", padx=(10, 0)
        )
        self.parameter_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.preview_mutation(),
        )

        ttk.Label(settings, text="Preset").grid(
            row=2, column=0, sticky="w"
        )
        self.preset_combo = ttk.Combobox(
            settings,
            textvariable=self.mutation_preset_var,
            values=tuple(PRESETS),
            state="readonly",
            width=24,
        )
        self.preset_combo.grid(
            row=2, column=1, sticky="ew", padx=(10, 0)
        )
        self.preset_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.preview_mutation(),
        )

        ttk.Label(settings, text="Intensity").grid(
            row=3, column=0, sticky="w"
        )
        intensity_frame = ttk.Frame(settings)
        intensity_frame.grid(
            row=3, column=1, sticky="ew", padx=(10, 0)
        )
        self.intensity_scale = ttk.Scale(
            intensity_frame,
            from_=0.05,
            to=3.0,
            orient="horizontal",
            variable=self.mutation_intensity_var,
            command=lambda _v: self._intensity_changed(),
        )
        self.intensity_scale.pack(
            side="left", fill="x", expand=True
        )
        self.intensity_value_label = ttk.Label(
            intensity_frame,
            text="0.50",
            width=6,
        )
        self.intensity_value_label.pack(side="left", padx=(8, 0))

        self._spin_row(
            settings, 4, "Mutation runs",
            self.mutation_count_var, 1, 100, 1,
        )
        self._spin_row(
            settings, 5, "Random seed (0=auto)",
            self.mutation_seed_var, 0, 2_147_483_647, 1,
        )

        ttk.Label(
            settings,
            text=(
                "Every mutation is isolated. Canonical Atlas rule.json "
                "files are never overwritten or auto-promoted."
            ),
            wraplength=370,
        ).grid(
            row=6, column=0, columnspan=2,
            sticky="w", pady=(12, 0)
        )

        mutation_buttons = ttk.Frame(controls)
        mutation_buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(
            mutation_buttons,
            text="Preview",
            command=self.preview_mutation,
        ).pack(side="left")
        ttk.Button(
            mutation_buttons,
            text="Queue Mutation Batch",
            command=self.queue_mutations,
            style="Launch.TButton",
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            mutation_buttons,
            text="Run Now",
            command=self.launch_mutations,
        ).pack(side="left", padx=(8, 0))

        preview_frame = ttk.LabelFrame(
            preview, text="Mutation Preview", padding=12
        )
        preview_frame.pack(
            fill="both", expand=True, padx=(10, 0)
        )
        self.preview_text = tk.Text(
            preview_frame,
            wrap="none",
            state="disabled",
            font=("monospace", 10),
        )
        preview_scroll_y = ttk.Scrollbar(
            preview_frame,
            orient="vertical",
            command=self.preview_text.yview,
        )
        preview_scroll_x = ttk.Scrollbar(
            preview_frame,
            orient="horizontal",
            command=self.preview_text.xview,
        )
        self.preview_text.configure(
            yscrollcommand=preview_scroll_y.set,
            xscrollcommand=preview_scroll_x.set,
        )
        self.preview_text.grid(
            row=0, column=0, sticky="nsew"
        )
        preview_scroll_y.grid(
            row=0, column=1, sticky="ns"
        )
        preview_scroll_x.grid(
            row=1, column=0, sticky="ew"
        )
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self._set_preview_text(self.preview_var.get())

    def _build_queue_tab(self) -> None:
        toolbar = ttk.Frame(self.queue_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(
            toolbar,
            text="Launch Queue",
            command=self.start_queue,
            style="Launch.TButton",
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Clear Waiting",
            command=self.clear_queue,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Stop Current",
            command=self.stop,
        ).pack(side="left", padx=(8, 0))

        columns = ("position", "rule", "mutation", "mode", "status", "folder")
        self.queue_tree = ttk.Treeview(
            self.queue_tab,
            columns=columns,
            show="headings",
        )
        labels = {
            "position": "#",
            "rule": "Rule",
            "mutation": "Mutation",
            "mode": "Mode",
            "status": "Status",
            "folder": "Output Folder",
        }
        widths = {
            "position": 50,
            "rule": 80,
            "mutation": 220,
            "mode": 140,
            "status": 100,
            "folder": 520,
        }
        for key in columns:
            self.queue_tree.heading(key, text=labels[key])
            self.queue_tree.column(
                key,
                width=widths[key],
                anchor="w" if key == "folder" else "center",
            )
        self.queue_tree.pack(fill="both", expand=True)
        self.queue_tree.bind(
            "<Double-1>", self._open_queue_item
        )

    def _build_controls_tab(self) -> None:
        toolbar = ttk.Frame(self.controls_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(
            toolbar,
            text="Refresh",
            command=self.refresh_required_controls,
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Queue Selected",
            command=self.queue_selected_control,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Queue All Required",
            command=self.queue_all_controls,
            style="Launch.TButton",
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Run Selected",
            command=self.run_selected_control,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Open Registry",
            command=lambda: open_path(REQUIRED_CONTROLS_FILE),
        ).pack(side="right")

        columns = (
            "rule", "ticks", "sample", "reason",
            "coverage", "source", "status",
        )
        self.controls_tree = ttk.Treeview(
            self.controls_tab,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        labels = {
            "rule": "Rule",
            "ticks": "Target ticks",
            "sample": "Sample every",
            "reason": "Reason",
            "coverage": "Coverage",
            "source": "Source mutation",
            "status": "Status",
        }
        widths = {
            "rule": 75,
            "ticks": 100,
            "sample": 105,
            "reason": 225,
            "coverage": 90,
            "source": 330,
            "status": 180,
        }
        for key in columns:
            self.controls_tree.heading(key, text=labels[key])
            self.controls_tree.column(
                key,
                width=widths[key],
                anchor="w" if key in {"reason", "source", "status"} else "center",
            )
        self.controls_tree.pack(fill="both", expand=True)
        self.controls_tree.bind(
            "<<TreeviewSelect>>",
            self._control_selection_changed,
        )
        self.controls_tree.bind(
            "<Double-1>",
            lambda _e: self.run_selected_control(),
        )

        self.control_detail_var = tk.StringVar(
            value=(
                "Run Analyzer to generate required_controls.json, then "
                "refresh this tab."
            )
        )
        ttk.Label(
            self.controls_tab,
            textvariable=self.control_detail_var,
            wraplength=1180,
            justify="left",
        ).pack(fill="x", pady=(8, 0))

    def _build_history_tab(self) -> None:
        toolbar = ttk.Frame(self.history_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(
            toolbar,
            text="Refresh History",
            command=self._refresh_history,
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Open Selected Folder",
            command=self.open_history_folder,
        ).pack(side="left", padx=(8, 0))

        columns = (
            "date", "rule", "mode", "mutation", "status", "folder"
        )
        self.history_tree = ttk.Treeview(
            self.history_tab,
            columns=columns,
            show="headings",
        )
        labels = {
            "date": "Date",
            "rule": "Rule",
            "mode": "Mode",
            "mutation": "Mutation",
            "status": "Status",
            "folder": "Folder",
        }
        widths = {
            "date": 150,
            "rule": 80,
            "mode": 140,
            "mutation": 230,
            "status": 100,
            "folder": 520,
        }
        for key in columns:
            self.history_tree.heading(key, text=labels[key])
            self.history_tree.column(
                key,
                width=widths[key],
                anchor="w" if key == "folder" else "center",
            )
        self.history_tree.pack(fill="both", expand=True)
        self.history_tree.bind(
            "<Double-1>",
            lambda _e: self.open_history_folder(),
        )

    def _build_settings_tab(self) -> None:
        left = ttk.LabelFrame(
            self.settings_tab,
            text="Environment",
            padding=12,
        )
        left.pack(fill="x", pady=(0, 10))
        rows = [
            ("Project root", PROJECT_ROOT),
            ("Observer script", OBSERVER_SCRIPT),
            ("Atlas", WORLD_ATLAS_DIR),
            ("Search results", SEARCH_RESULTS_DIR),
            ("Mutation root", MUTATION_ROOT),
            ("Required controls", REQUIRED_CONTROLS_FILE),
            ("Control runs", CONTROL_RUN_ROOT),
            ("Python", sys.executable),
            ("Field backend", os.environ.get(
                "ART_EVO_FIELD_BACKEND", "cupy"
            )),
        ]
        for index, (label, value) in enumerate(rows):
            ttk.Label(
                left,
                text=label,
                width=20,
            ).grid(row=index, column=0, sticky="w", pady=3)
            ttk.Label(
                left,
                text=str(value),
                wraplength=950,
            ).grid(row=index, column=1, sticky="w", pady=3)

        actions = ttk.LabelFrame(
            self.settings_tab,
            text="Folders",
            padding=12,
        )
        actions.pack(fill="x")
        ttk.Button(
            actions,
            text="Open Project Root",
            command=lambda: open_path(PROJECT_ROOT),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Open Atlas",
            command=lambda: open_path(WORLD_ATLAS_DIR),
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Open Mutation Root",
            command=lambda: open_path(MUTATION_ROOT),
        ).pack(side="left", padx=(8, 0))

    def _spin_row(
        self,
        parent: ttk.Widget,
        row: int,
        label: str,
        variable: tk.Variable,
        minimum: float,
        maximum: float,
        increment: float,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", pady=3
        )
        spin = ttk.Spinbox(
            parent,
            textvariable=variable,
            from_=minimum,
            to=maximum,
            increment=increment,
            width=20,
            command=self._update_command_preview,
        )
        spin.grid(
            row=row, column=1, sticky="ew",
            padx=(10, 0), pady=3
        )
        variable.trace_add(
            "write",
            lambda *_args: self._update_command_preview(),
        )

    def _combo_row(
        self,
        parent: ttk.Widget,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: list[str],
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", pady=3
        )
        combo = ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
            width=20,
        )
        combo.grid(
            row=row, column=1, sticky="ew",
            padx=(10, 0), pady=3
        )
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._speed_changed(),
        )

    def _speed_changed(self) -> None:
        text = self.speed_text_var.get().rstrip("x")
        try:
            self.speed_var.set(int(text))
        except Exception:
            return
        self._update_command_preview()

    def refresh_rules(self) -> None:
        self.rules = load_rules()
        self.atlas_status_var.set(
            f"Atlas: {len(self.rules)} rules"
        )
        self._refresh_rule_table()
        self.status_var.set("Atlas refreshed")

    def _refresh_rule_table(self) -> None:
        query = self.filter_var.get().strip().lower()
        class_filter = self.class_filter_var.get()
        status_filter = self.status_filter_var.get()

        rows = []
        for row in self.rules:
            rid = normalize_rule_id(row["rule_id"])
            klass = str(row.get("class") or "")
            if query and query not in rid and query not in klass.lower():
                continue
            if class_filter != "All" and klass != class_filter:
                continue
            if status_filter == "Observed" and not row.get("observed"):
                continue
            if status_filter == "Not observed" and row.get("observed"):
                continue
            if (
                status_filter == "Has mutations"
                and int(row.get("mutation_runs", 0)) <= 0
            ):
                continue
            rows.append(row)

        sort_mode = self.sort_var.get()
        if sort_mode == "Score high":
            rows.sort(
                key=lambda x: (
                    x.get("score")
                    if isinstance(x.get("score"), (int, float))
                    else -1e18
                ),
                reverse=True,
            )
        elif sort_mode == "Score low":
            rows.sort(
                key=lambda x: (
                    x.get("score")
                    if isinstance(x.get("score"), (int, float))
                    else 1e18
                )
            )
        elif sort_mode == "Last run":
            rows.sort(
                key=lambda x: x.get("last_run", ""),
                reverse=True,
            )
        else:
            rows.sort(key=lambda x: int(x["rule_id"]))

        self.visible_rules = rows
        self.rule_tree.delete(*self.rule_tree.get_children())
        for row in rows:
            rid = normalize_rule_id(row["rule_id"])
            self.rule_tree.insert(
                "", "end", iid=rid,
                values=(
                    rid,
                    format_score(row.get("score")),
                    row.get("class") or "",
                    "Yes" if row.get("observed") else "No",
                    row.get("mutation_runs", 0),
                    row.get("last_run", "-"),
                ),
            )

    def _on_rule_selected(self, _event=None) -> None:
        selected = self.rule_tree.selection()
        if not selected:
            return
        rid = int(selected[0])
        self.selected_rule = next(
            (r for r in self.rules if int(r["rule_id"]) == rid),
            None,
        )
        self.rule_var.set(f"{rid:05d}")
        self._update_rule_card()
        self._load_parameter_choices()
        self._update_command_preview()

    def _update_rule_card(self) -> None:
        row = self.selected_rule
        if row is None:
            return
        rid = normalize_rule_id(row["rule_id"])
        parents = row.get("parents") or (None, None)
        self.card_rule.set(f"Rule {rid}")
        self.card_score.set(
            f"Score: {format_score(row.get('score')) or '-'}"
        )
        self.card_class.set(
            f"Class: {row.get('class') or '-'}"
        )
        self.card_parents.set(
            f"Parents: {parents[0]} + {parents[1]}"
        )
        self.card_hash.set(
            f"Genome hash: {row.get('genome_hash') or '-'}"
        )
        self.card_last.set(
            f"Last run: {row.get('last_run', '-')}"
        )
        self.card_mutations.set(
            f"Mutation runs: {row.get('mutation_runs', 0)}"
        )
        self.run_selected_label.set(
            f"Rule {rid} | {row.get('class') or 'Unclassified'}"
        )
        self.mutation_selected_label.set(
            f"Rule {rid} | canonical parent"
        )

    def _selected_rule_payload(self) -> tuple[Path, dict[str, Any]]:
        if not self.rule_var.get().strip():
            raise ValueError("Select a rule in Rule Browser first.")
        rule_id = int(self.rule_var.get())
        rule_file = find_rule_file(rule_id)
        if rule_file is None:
            raise ValueError(
                f"Rule {rule_id:05d} was not found in Atlas."
            )
        payload = read_json(rule_file, None)
        if not isinstance(payload, dict):
            raise ValueError(f"Could not read {rule_file}")
        return rule_file, payload

    def _load_parameter_choices(self) -> None:
        try:
            _path, payload = self._selected_rule_payload()
        except Exception:
            self.parameter_combo["values"] = ()
            self.mutation_parameter_var.set("")
            return
        choices = parameter_choices(payload)
        self.parameter_combo["values"] = choices
        current = self.mutation_parameter_var.get()
        if current not in choices:
            self.mutation_parameter_var.set(
                choices[0] if choices else ""
            )

    def _mutation_mode_changed(self) -> None:
        mode = self.mutation_mode_var.get()
        self.parameter_combo.configure(
            state=(
                "readonly"
                if mode == "single_parameter"
                else "disabled"
            )
        )
        self.preset_combo.configure(
            state="readonly" if mode == "preset" else "disabled"
        )
        self.preview_mutation()

    def _intensity_changed(self) -> None:
        value = float(self.mutation_intensity_var.get())
        self.intensity_value_label.configure(text=f"{value:.2f}")
        self.preview_mutation()

    def preview_mutation(self) -> None:
        try:
            _rule_file, payload = self._selected_rule_payload()
        except Exception as exc:
            self._set_preview_text(str(exc))
            return

        mode = self.mutation_mode_var.get()
        if mode == "none":
            self._set_preview_text(
                "No mutation selected.\n\n"
                "The canonical rule will be observed unchanged."
            )
            return

        seed = int(self.mutation_seed_var.get())
        if seed == 0:
            seed = 1_234_567

        try:
            temp_root = MUTATION_ROOT / "_preview"
            run = create_mutation_run(
                original_rule=payload,
                mutation_root=temp_root,
                mode=mode,
                intensity=float(self.mutation_intensity_var.get()),
                seed=seed,
                parameter=(
                    self.mutation_parameter_var.get()
                    if mode == "single_parameter"
                    else None
                ),
                preset=self.mutation_preset_var.get(),
                sequence=1,
            )
            manifest = run["manifest"]
            lines = [
                f"Parent rule: {normalize_rule_id(payload.get('rule_id'))}",
                f"Mode: {mode}",
                f"Intensity: {self.mutation_intensity_var.get():.2f}",
                f"Seed used for preview: {seed}",
                f"Expected changed values: {manifest['change_count']}",
                "",
                "PATH".ljust(38) + "BEFORE".ljust(20) + "AFTER",
                "-" * 88,
            ]
            for change in manifest.get("changes", [])[:100]:
                lines.append(
                    str(change.get("path", "")).ljust(38)[:38]
                    + str(change.get("before", "")).ljust(20)[:20]
                    + str(change.get("after", ""))
                )
            if manifest.get("change_count", 0) > 100:
                lines.append(
                    f"... {manifest['change_count'] - 100} more changes"
                )
            self._set_preview_text("\n".join(lines))
            try:
                import shutil
                shutil.rmtree(run["run_dir"])
                parent = run["run_dir"].parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                if temp_root.exists() and not any(temp_root.rglob("*")):
                    temp_root.rmdir()
            except Exception:
                pass
        except Exception as exc:
            self._set_preview_text(f"Preview failed:\n{exc!r}")

    def _set_preview_text(self, text: str) -> None:
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.configure(state="disabled")

    def _common_flags(
        self,
        *,
        max_ticks_override: int | None = None,
        sample_every_override: int | None = None,
        pressure_every_override: int | None = None,
        force_no_auto_stop: bool = False,
        force_samples: bool = False,
        force_passport: bool = False,
    ) -> list[str]:
        max_ticks = (
            int(max_ticks_override)
            if max_ticks_override is not None
            else int(self.max_ticks_var.get())
        )
        flags = [
            "--cell", str(self.cell_var.get()),
            "--speed", str(self.speed_var.get()),
            "--delay", str(self.delay_var.get()),
            "--autosave-every", str(self.autosave_var.get()),
            "--sample-every", str(
                sample_every_override
                if sample_every_override is not None
                else self.sample_every_var.get()
            ),
            "--pressure-timeline-every",
            str(
                pressure_every_override
                if pressure_every_override is not None
                else self.pressure_every_var.get()
            ),
        ]
        if max_ticks > 0:
            flags.extend(["--max-ticks", str(max_ticks)])
        if self.auto_stop_var.get() and not force_no_auto_stop:
            flags.append("--auto-stop")
        if self.samples_var.get() or force_samples:
            flags.append("--samples-csv")
        if self.events_var.get():
            flags.append("--events-csv")
        if self.pressure_var.get():
            flags.append("--pressure-timeline-csv")
        if self.chronicle_var.get():
            flags.append("--chronicle-csv")
        if self.passport_var.get() or force_passport:
            flags.append("--passport")
        if self.log_var.get():
            flags.append("--log")
        if self.sqlite_var.get():
            flags.extend([
                "--telemetry-sqlite",
                "--telemetry-db",
                str(TELEMETRY_DATABASE),
            ])
        else:
            flags.append("--no-telemetry-sqlite")
        flags.append(
            "--evidence-framework"
            if self.evidence_var.get()
            else "--no-evidence-framework"
        )
        return flags

    def _base_command(
        self,
        run: dict[str, Any] | None = None,
    ) -> list[str]:
        selector = normalize_rule_id(
            run.get("rule_id")
            if run is not None and run.get("rule_id") is not None
            else self.rule_var.get()
        )
        is_mutation = run is not None and run.get("rule_file") is not None
        is_control = (
            run is not None
            and run.get("mode") == "required_control"
        )
        cmd = [
            *runtime_python_command(PROJECT_ROOT),
            str(OBSERVER_SCRIPT),
            str(SEARCH_RESULTS_DIR),
            selector,
            *self._common_flags(
                max_ticks_override=(
                    run.get("max_ticks_override")
                    if run is not None else None
                ),
                sample_every_override=(
                    run.get("sample_every_override")
                    if run is not None else None
                ),
                pressure_every_override=(
                    run.get("pressure_every_override")
                    if run is not None else None
                ),
                force_no_auto_stop=is_mutation or is_control,
                force_samples=is_control,
                force_passport=is_control,
            ),
        ]
        if run is not None and run.get("run_output_dir") is not None:
            cmd.extend([
                "--run-output-dir", str(run["run_output_dir"]),
            ])
        elif is_mutation:
            cmd.extend([
                "--run-output-dir", str(run["run_dir"]),
            ])
        if is_mutation:
            cmd.extend([
                "--rule-file", str(run["rule_file"]),
                "--mutation-manifest", str(run["manifest_file"]),
            ])

        if (
            run is not None
            and run.get("mode") in {
                "experiment_plan",
                "production_experiment_plan",
                "experimental_mutation",
                "canonical_queue",
                "canonical_backlog",
            }
        ):
            cmd.append("--exit-at-max-ticks")

        experiment_context = (
            run.get("experimental_context")
            if run is not None
            else self._selected_experimental_context()
        )
        if experiment_context is not None:
            cmd.extend([
                "--experiment-id",
                str(experiment_context["experiment_id"]),
                "--condition-id",
                str(experiment_context["condition_id"]),
                "--experiment-role",
                str(experiment_context["role"]),
                "--replicate-index",
                str(experiment_context["replicate_index"]),
                "--field-width",
                str(experiment_context["field_width"]),
                "--field-height",
                str(experiment_context["field_height"]),
                "--topology",
                str(experiment_context["topology"]),
                "--boundary-mode",
                str(experiment_context["boundary_mode"]),
                "--initial-state-mode",
                str(experiment_context["initial_state_mode"]),
            ])
            if experiment_context.get("treatment_arm"):
                cmd.extend([
                    "--treatment-arm",
                    str(experiment_context["treatment_arm"]),
                ])
            if experiment_context.get("seed") is not None:
                cmd.extend([
                    "--experiment-seed",
                    str(experiment_context["seed"]),
                ])
        return cmd

    def _update_command_preview(self) -> None:
        try:
            self.command_var.set(
                shlex.join(self._base_command())
            )
        except Exception:
            self.command_var.set(
                "Select a rule to build the Observer command."
            )

    def _prepare_mutation_runs(self) -> list[dict[str, Any]]:
        _rule_file, payload = self._selected_rule_payload()
        mode = self.mutation_mode_var.get()
        if mode == "none":
            raise ValueError(
                "Choose a mutation mode before preparing a mutation batch."
            )

        # Mutations are normally isolated runs, but when the Experiments tab
        # explicitly enables a context they must carry the same provenance as
        # canonical experimental runs.  Resolve it once before materializing
        # the batch so every run receives an immutable copy.
        experimental_context = self._selected_experimental_context()

        count = max(1, int(self.mutation_count_var.get()))
        base_seed = int(self.mutation_seed_var.get())
        if base_seed == 0:
            base_seed = int(time.time() * 1000) & 0x7FFFFFFF

        baseline_provenance = capture_baseline_provenance(
            original_rule=payload,
            results_root=SEARCH_RESULTS_DIR,
        )
        if baseline_provenance.get("status") != "resolved":
            raise ValueError(
                "No canonical baseline with a resolved passport was found. "
                "Run and save the selected rule canonically before preparing "
                "its mutation."
            )

        runs = []
        for index in range(1, count + 1):
            run = create_mutation_run(
                original_rule=payload,
                mutation_root=MUTATION_ROOT,
                mode=mode,
                intensity=float(self.mutation_intensity_var.get()),
                seed=base_seed + index - 1,
                parameter=(
                    self.mutation_parameter_var.get()
                    if mode == "single_parameter"
                    else None
                ),
                preset=self.mutation_preset_var.get(),
                sequence=index,
                baseline_provenance=baseline_provenance,
            )
            mutation_seed = base_seed + index - 1
            run["mode"] = (
                "experimental_mutation"
                if experimental_context is not None
                else mode
            )
            run["rule_id"] = int(payload["rule_id"])
            run["max_ticks_override"] = int(self.max_ticks_var.get())
            run["sample_every_override"] = int(
                self.sample_every_var.get()
            )
            run["pressure_every_override"] = int(
                self.pressure_every_var.get()
            )
            if experimental_context is not None:
                run_context = dict(experimental_context)
                # The mutation engine already materializes an explicit seed.
                # Publish that exact seed to the experimental telemetry layer
                # so treatment and matched control can be joined reliably.
                run_context["seed"] = mutation_seed
                parameter = (
                    self.mutation_parameter_var.get()
                    if mode == "single_parameter" else mode
                )
                intensity_code = int(round(float(self.mutation_intensity_var.get()) * 100))
                run_context["treatment_arm"] = (
                    f"{parameter}:I{intensity_code:03d}"
                )
                run["experimental_context"] = run_context
            else:
                run["experimental_context"] = None
            run["status"] = "Waiting"
            runs.append(run)
        return runs

    def _mutation_dir_for_control(
        self,
        control: dict[str, Any],
    ) -> Path | None:
        rule_id = normalize_rule_id(control.get("canonical_rule_id"))
        mutation_id = str(control.get("source_mutation_id") or "")
        if not mutation_id or Path(mutation_id).name != mutation_id:
            return None
        candidate = MUTATION_ROOT / f"rule_{rule_id}" / mutation_id
        if (candidate / "mutation_manifest.json").is_file():
            return candidate
        matches = [
            path.parent
            for path in MUTATION_ROOT.rglob("mutation_manifest.json")
            if path.parent.name == mutation_id
        ]
        return matches[0] if len(matches) == 1 else None

    def _control_resolution(
        self,
        control: dict[str, Any],
    ) -> dict[str, Any] | None:
        mutation_dir = self._mutation_dir_for_control(control)
        if mutation_dir is None:
            return None
        payload = read_json(
            mutation_dir / CONTROL_RESOLUTION_FILENAME,
            {},
        )
        if not isinstance(payload, dict):
            return None
        if (
            payload.get("schema")
            != "archon_required_control_resolution_v1"
            or str(payload.get("source_mutation_id") or "")
            != str(control.get("source_mutation_id") or "")
        ):
            return None
        samples_path = Path(str(payload.get("samples_path") or ""))
        return payload if samples_path.is_file() else None

    def refresh_required_controls(self) -> None:
        payload = read_json(REQUIRED_CONTROLS_FILE, {})
        controls = (
            payload.get("controls", [])
            if isinstance(payload, dict)
            else []
        )
        self.required_controls = [
            control for control in controls
            if isinstance(control, dict)
            and control.get("status") == "required"
        ]
        if not hasattr(self, "controls_tree"):
            return
        self.controls_tree.delete(*self.controls_tree.get_children())
        for index, control in enumerate(self.required_controls):
            mutation_dir = self._mutation_dir_for_control(control)
            resolution = self._control_resolution(control)
            if resolution is not None:
                status = "Completed; run Analyzer"
            elif mutation_dir is None:
                status = "Mutation not found"
            else:
                status = "Required"
            coverage = control.get("current_coverage_ratio")
            coverage_text = (
                f"{float(coverage) * 100:.2f}%"
                if isinstance(coverage, (int, float))
                else "-"
            )
            self.controls_tree.insert(
                "",
                "end",
                iid=f"control_{index}",
                values=(
                    normalize_rule_id(control.get("canonical_rule_id")),
                    control.get("target_ticks") or "-",
                    control.get("sample_interval") or "-",
                    control.get("reason") or "-",
                    coverage_text,
                    control.get("source_mutation_id") or "-",
                    status,
                ),
            )
        self.control_detail_var.set(
            f"Registry: {REQUIRED_CONTROLS_FILE} | "
            f"Required controls: {len(self.required_controls)}"
        )

    def _selected_control(self) -> dict[str, Any] | None:
        selected = self.controls_tree.selection()
        if not selected:
            return None
        try:
            index = int(selected[0].rsplit("_", 1)[-1])
            return self.required_controls[index]
        except (ValueError, IndexError):
            return None

    def _control_selection_changed(self, _event=None) -> None:
        control = self._selected_control()
        if control is None:
            return
        self.control_detail_var.set(
            f"Canonical rule {normalize_rule_id(control.get('canonical_rule_id'))} "
            f"will run unchanged to tick {control.get('target_ticks')} with "
            f"sample-every={control.get('sample_interval')}. "
            f"Requested by {control.get('source_mutation_id')}."
        )

    def _prepare_control_run(
        self,
        control: dict[str, Any],
    ) -> dict[str, Any]:
        rule_id = int(control.get("canonical_rule_id"))
        target_ticks = int(control.get("target_ticks"))
        sample_interval = int(control.get("sample_interval"))
        if target_ticks <= 0 or sample_interval <= 0:
            raise ValueError(
                "Control target_ticks and sample_interval must be positive."
            )

        rule_file = find_rule_file(rule_id)
        if rule_file is None:
            raise ValueError(
                f"Canonical rule {rule_id:05d} was not found in Atlas."
            )
        rule_payload = read_json(rule_file, {})
        expected_seed = control.get("canonical_rule_seed")
        if (
            expected_seed not in {None, ""}
            and str(rule_payload.get("seed")) != str(expected_seed)
        ):
            raise ValueError(
                f"Rule {rule_id:05d} seed does not match the control "
                f"request ({rule_payload.get('seed')} != {expected_seed})."
            )

        mutation_dir = self._mutation_dir_for_control(control)
        if mutation_dir is None:
            raise ValueError(
                f"Source mutation {control.get('source_mutation_id')} "
                "was not found."
            )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = (
            CONTROL_RUN_ROOT
            / f"rule_{rule_id:05d}"
            / str(control.get("source_mutation_id"))
            / timestamp
        )
        return {
            "mutation_id": (
                f"CONTROL:{control.get('source_mutation_id')}"
            ),
            "run_dir": run_dir,
            "run_output_dir": run_dir,
            "rule_file": None,
            "manifest_file": None,
            "mode": "required_control",
            "rule_id": rule_id,
            "status": "Waiting",
            "max_ticks_override": target_ticks,
            "sample_every_override": sample_interval,
            "control_request": dict(control),
            "control_resolution_path": (
                mutation_dir / CONTROL_RESOLUTION_FILENAME
            ),
        }

    def _queue_controls(
        self,
        controls: list[dict[str, Any]],
    ) -> int:
        queued = 0
        errors: list[str] = []
        existing = {
            str(run.get("control_request", {}).get("source_mutation_id"))
            for run in self.batch_queue
            if isinstance(run.get("control_request"), dict)
        }
        for control in controls:
            source_id = str(control.get("source_mutation_id") or "")
            if self._control_resolution(control) is not None:
                continue
            if source_id in existing:
                continue
            try:
                self.batch_queue.append(
                    self._prepare_control_run(control)
                )
                existing.add(source_id)
                queued += 1
            except Exception as exc:
                errors.append(f"{source_id}: {exc}")
        self._refresh_queue()
        if queued:
            self.notebook.select(self.queue_tab)
            self.status_var.set(f"Queued {queued} required control(s)")
        if errors:
            messagebox.showerror(
                "Could not queue some controls",
                "\n".join(errors),
            )
        return queued

    def queue_selected_control(self) -> None:
        control = self._selected_control()
        if control is None:
            messagebox.showinfo(
                "Select a control",
                "Select one required control first.",
            )
            return
        self._queue_controls([control])

    def queue_all_controls(self) -> None:
        if not self.required_controls:
            messagebox.showinfo(
                "No controls",
                "No required controls are listed.",
            )
            return
        queued = self._queue_controls(self.required_controls)
        if queued == 0:
            self.status_var.set(
                "All listed controls are already completed or queued"
            )

    def run_selected_control(self) -> None:
        if self.process is not None:
            messagebox.showwarning(
                "Observer is running",
                "Stop the current Observer first.",
            )
            return
        before = len(self.batch_queue)
        self.queue_selected_control()
        if len(self.batch_queue) > before:
            self.start_queue()

    def _finalize_control_run(self, run: dict[str, Any]) -> None:
        control = run.get("control_request")
        if not isinstance(control, dict):
            raise ValueError("Control request metadata is missing.")
        run_dir = Path(run["run_dir"])
        samples = sorted(
            run_dir.rglob("*_samples.csv"),
            key=lambda path: path.stat().st_mtime_ns,
        )
        if not samples:
            raise ValueError("Control samples CSV was not created.")
        samples_path = samples[-1].resolve()

        final_tick = None
        run_id = samples_path.name.removesuffix("_samples.csv")
        with samples_path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        ) as handle:
            for row in csv.DictReader(handle):
                try:
                    final_tick = int(float(row.get("tick", "")))
                except (TypeError, ValueError):
                    continue
        target_ticks = int(control.get("target_ticks"))
        if final_tick is None or final_tick < target_ticks:
            raise ValueError(
                f"Control stopped at tick {final_tick}; "
                f"target was {target_ticks}."
            )

        passport_candidates = sorted(
            [
                path for path in run_dir.rglob("*passport*.json")
                if path.name.startswith(run_id)
            ],
            key=lambda path: path.stat().st_mtime_ns,
        )
        passport_path = (
            passport_candidates[-1].resolve()
            if passport_candidates else None
        )
        resolution = {
            "schema": "archon_required_control_resolution_v1",
            "status": "completed",
            "completed": datetime.now().isoformat(timespec="seconds"),
            "source_mutation_id": control.get("source_mutation_id"),
            "canonical_rule_id": normalize_rule_id(
                control.get("canonical_rule_id")
            ),
            "canonical_rule_seed": control.get("canonical_rule_seed"),
            "target_ticks": target_ticks,
            "sample_interval": int(control.get("sample_interval")),
            "run_id": run_id,
            "samples_path": str(samples_path),
            "passport_path": (
                str(passport_path) if passport_path is not None else None
            ),
            "run_dir": str(run_dir.resolve()),
        }
        atomic_json(Path(run["control_resolution_path"]), resolution)
        self._append_output(
            "\nRequired control completed and linked to "
            f"{control.get('source_mutation_id')}.\n"
            "Run Mutation Analyzer to consume it.\n"
        )

    def _canonical_queue_run(self, rule_id: int, *, mode: str) -> dict[str, Any]:
        """Build one immutable canonical queue item from current UI settings."""
        return {
            "mutation_id": None,
            "run_dir": SEARCH_RESULTS_DIR / "observation_logs",
            "rule_file": None,
            "manifest_file": None,
            "mode": mode,
            "rule_id": int(rule_id),
            "experimental_context": None,
            "max_ticks_override": int(self.max_ticks_var.get()),
            "sample_every_override": int(self.sample_every_var.get()),
            "pressure_every_override": int(self.pressure_every_var.get()),
            "status": "Waiting",
        }

    def _queued_rule_ids(self) -> set[int]:
        return {
            int(item["rule_id"])
            for item in self.queue_runs
            if item.get("rule_id") is not None
            and item.get("mode") in {"canonical_queue", "canonical_backlog"}
            and item.get("status") in {"Waiting", "Running"}
        }

    def _append_canonical_rules(self, rule_ids: list[int], *, mode: str) -> int:
        existing = self._queued_rule_ids()
        added = []
        for rule_id in rule_ids:
            rid = int(rule_id)
            if rid in existing:
                continue
            run = self._canonical_queue_run(rid, mode=mode)
            self.batch_queue.append(run)
            self.queue_runs.append(run)
            existing.add(rid)
            added.append(run)
        self._refresh_queue()
        if added:
            self.notebook.select(self.queue_tab)
        return len(added)

    def add_selected_rules_to_queue(self) -> None:
        selected = [int(item) for item in self.rule_tree.selection()]
        if not selected:
            messagebox.showwarning("No rules selected", "Select one or more rules first.")
            return
        added = self._append_canonical_rules(selected, mode="canonical_queue")
        self.status_var.set(f"Added {added} selected canonical run(s)")

    def add_all_visible_to_queue(self) -> None:
        rule_ids = [int(row["rule_id"]) for row in self.visible_rules]
        added = self._append_canonical_rules(rule_ids, mode="canonical_queue")
        self.status_var.set(f"Added {added} visible canonical run(s)")

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _completed_canonical_horizons(self) -> dict[int, int]:
        """Return the greatest completed non-experimental horizon per rule."""
        if not TELEMETRY_DATABASE.exists():
            return {}
        connection = sqlite3.connect(str(TELEMETRY_DATABASE))
        connection.row_factory = sqlite3.Row
        try:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "runs" not in tables:
                return {}
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(runs)")
            }
            if not {"rule_id", "status"}.issubset(columns):
                return {}

            experimental_run_ids: set[str] = set()
            if "experiment_runs" in tables:
                exp_columns = {
                    row[1] for row in connection.execute(
                        "PRAGMA table_info(experiment_runs)"
                    )
                }
                if "run_id" in exp_columns:
                    experimental_run_ids = {
                        str(row[0]) for row in connection.execute(
                            "SELECT run_id FROM experiment_runs WHERE run_id IS NOT NULL"
                        )
                    }

            horizons: dict[int, int] = {}
            unresolved: list[tuple[str, int]] = []
            for row in connection.execute("SELECT * FROM runs"):
                data = dict(row)
                if str(data.get("status") or "").strip().lower() != "completed":
                    continue
                try:
                    rule_id = int(data.get("rule_id"))
                except Exception:
                    continue
                run_id = str(data.get("run_id") or "")
                if run_id and run_id in experimental_run_ids:
                    continue

                metadata = self._json_object(data.get("metadata_json"))
                if not metadata:
                    metadata = self._json_object(data.get("metadata"))
                experimental_context = metadata.get("experimental_context")
                role = data.get("role") or data.get("experiment_role")
                if role is None and isinstance(experimental_context, dict):
                    role = experimental_context.get("role")
                role_text = str(role or "").strip().lower().replace("_", " ")
                if experimental_context or role_text not in {"", "canonical", "canonical observation"}:
                    continue

                horizon = None
                for key in (
                    "final_tick", "final_tick_observed", "completed_tick",
                    "last_tick", "max_tick", "tick",
                ):
                    value = data.get(key)
                    if value is None:
                        value = metadata.get(key)
                    try:
                        if value is not None:
                            horizon = int(float(value))
                            break
                    except Exception:
                        pass
                if horizon is None and run_id:
                    unresolved.append((run_id, rule_id))
                    continue
                if horizon is not None:
                    horizons[rule_id] = max(horizons.get(rule_id, 0), horizon)

            if unresolved and "samples" in tables:
                sample_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(samples)")
                }
                if {"run_id", "tick"}.issubset(sample_columns):
                    for run_id, rule_id in unresolved:
                        row = connection.execute(
                            "SELECT MAX(tick) FROM samples WHERE run_id = ?",
                            (run_id,),
                        ).fetchone()
                        if row and row[0] is not None:
                            horizons[rule_id] = max(
                                horizons.get(rule_id, 0), int(row[0])
                            )
            return horizons
        finally:
            connection.close()

    def launch_not_observed_one_by_one(self) -> None:
        if self.process is not None:
            messagebox.showwarning(
                "Observer is running", "Stop the current Observer first."
            )
            return
        threshold = max(1, int(self.minimum_horizon_var.get()))
        target = max(1, int(self.max_ticks_var.get()))
        if target < threshold:
            messagebox.showerror(
                "Invalid horizon",
                "Maximum ticks must be at least the minimum completed horizon.",
            )
            return
        try:
            horizons = self._completed_canonical_horizons()
        except Exception as exc:
            messagebox.showerror("SQLite coverage check failed", repr(exc))
            return

        if self.batch_queue:
            replace = messagebox.askyesno(
                "Replace waiting queue?",
                f"The waiting queue contains {len(self.batch_queue)} run(s). Replace it?",
            )
            if not replace:
                return
            self.clear_queue()

        ordered = [int(row["rule_id"]) for row in self.visible_rules]
        waiting = []
        skipped = []
        for rule_id in ordered:
            observed_horizon = int(horizons.get(rule_id, 0))
            if observed_horizon >= threshold:
                run = self._canonical_queue_run(rule_id, mode="canonical_backlog")
                run["status"] = "Skipped: already observed"
                run["observed_horizon"] = observed_horizon
                skipped.append(run)
            else:
                waiting.append(self._canonical_queue_run(rule_id, mode="canonical_backlog"))

        self.batch_queue = list(waiting)
        self.queue_runs = skipped + waiting
        self._refresh_queue()
        self.notebook.select(self.queue_tab)
        self._append_output(
            f"\nCanonical backlog: {len(waiting)} waiting, {len(skipped)} skipped "
            f"at completed horizon >= {threshold}. Target={target}.\n"
        )
        if waiting:
            self.start_queue()
        else:
            self.status_var.set("All visible rules already satisfy canonical coverage")

    def launch_canonical(self) -> None:
        try:
            self._selected_rule_payload()
        except Exception as exc:
            messagebox.showerror("Cannot launch", str(exc))
            return
        if self.process is not None:
            messagebox.showwarning(
                "Observer is running",
                "Stop the current Observer first.",
            )
            return
        try:
            experimental_context = self._selected_experimental_context()
        except Exception as exc:
            messagebox.showerror("Cannot launch experiment", str(exc))
            return

        run = {
            "mutation_id": None,
            "run_dir": SEARCH_RESULTS_DIR / "observation_logs",
            "rule_file": None,
            "manifest_file": None,
            "mode": (
                "experimental"
                if experimental_context is not None
                else "canonical"
            ),
            "rule_id": int(self.rule_var.get()),
            "experimental_context": experimental_context,
            "status": "Waiting",
        }
        if self.batch_queue:
            replace = messagebox.askyesno(
                "Replace waiting queue?",
                (
                    "The waiting queue contains "
                    f"{len(self.batch_queue)} run(s).\n\n"
                    "Replace it with this single Observer run?"
                ),
            )
            if not replace:
                return
        self.batch_queue = [run]
        self.queue_runs = [run]
        self._refresh_queue()
        self.start_queue()

    def queue_mutations(self) -> None:
        try:
            runs = self._prepare_mutation_runs()
        except Exception as exc:
            messagebox.showerror(
                "Could not prepare mutation batch",
                str(exc),
            )
            return
        self.batch_queue.extend(runs)
        if not self.queue_runs or all(
            str(item.get("status", "")).lower()
            not in {"waiting", "running"}
            for item in self.queue_runs
        ):
            self.queue_runs = []
        self.queue_runs.extend(runs)
        self._refresh_queue()
        self.notebook.select(self.queue_tab)
        self.status_var.set(
            f"Queued {len(runs)} mutation run(s)"
        )

    def launch_mutations(self) -> None:
        if self.process is not None:
            messagebox.showwarning(
                "Observer is running",
                "Stop the current Observer first.",
            )
            return
        self.queue_mutations()
        if self.batch_queue:
            self.start_queue()

    def start_queue(self) -> None:
        if self.process is not None:
            return
        if not self.batch_queue:
            self.status_var.set("Queue is empty")
            return
        if not self.queue_runs:
            self.queue_runs = list(self.batch_queue)
        self.launch_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._launch_next()

    def _launch_next(self) -> None:
        if not self.batch_queue:
            self.process = None
            self.current_run = None
            self.launch_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            completed = sum(
                1 for item in self.queue_runs
                if item.get("status") == "Completed"
            )
            failed = sum(
                1 for item in self.queue_runs
                if item.get("status") in {"Failed", "Control incomplete"}
            )
            skipped = sum(
                1 for item in self.queue_runs
                if item.get("status") == "Skipped: already observed"
            )
            self.queue_status_var.set(
                f"Queue: {completed} completed, {failed} failed, "
                f"{skipped} skipped"
            )
            self.status_var.set("Queue completed")
            self._refresh_queue()
            self._append_output(
                f"\nQueue completed: {completed} completed, "
                f"{failed} failed, {skipped} skipped.\n"
            )
            self.refresh_rules()
            self._refresh_history()
            return

        run = self.batch_queue.pop(0)
        run["status"] = "Running"
        self.current_run = run
        self.run_started_at = time.time()
        self._refresh_queue(current=run)

        cmd = self._base_command(run)
        env = runtime_python_environment(PROJECT_ROOT)
        # Portable CPU default.  A user may opt into a configured CuPy/CUDA
        # installation by exporting ART_EVO_FIELD_BACKEND=cupy before launch.
        env.setdefault("ART_EVO_FIELD_BACKEND", "numpy")
        env["PYTHONUNBUFFERED"] = "1"

        self._append_output(
            "\n" + "=" * 80 + "\n"
            + "Launching:\n"
            + shlex.join(cmd)
            + "\n" + "=" * 80 + "\n"
        )
        context = run.get("experimental_context")
        if context:
            running_label = (
                f"{context['condition_id']} "
                f"[{context['role']} r{context['replicate_index']}]"
            )
        else:
            running_label = (
                run.get("mutation_id")
                or normalize_rule_id(run["rule_id"])
            )
        self.status_var.set(f"Running {running_label}")

        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except Exception as exc:
            run["status"] = "Failed"
            run["launch_error"] = repr(exc)
            self._record_history(run)
            self.process = None
            messagebox.showerror("Launch failed", repr(exc))
            self.after(250, self._launch_next)
            return

        threading.Thread(
            target=self._read_process_output,
            daemon=True,
        ).start()

    def _read_process_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self.output_queue.put(line)
        code = process.wait()
        self.output_queue.put(
            f"\n[Observer exited with code {code}]\n"
        )
        self.output_queue.put(
            ("__PROCESS_DONE__", code)
        )

    def _drain_output(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__PROCESS_DONE__":
                    code = int(item[1])
                    if self.current_run is not None:
                        status = "Completed" if code == 0 else "Failed"
                        if (
                            code == 0
                            and self.current_run.get("mode")
                            == "required_control"
                        ):
                            try:
                                self._finalize_control_run(self.current_run)
                            except Exception as exc:
                                status = "Control incomplete"
                                self._append_output(
                                    "\n[required control not linked] "
                                    f"{exc}\n"
                                )
                        self.current_run["status"] = status
                        self.current_run["exit_code"] = code
                        self._record_history(self.current_run)
                        self.refresh_required_controls()
                        self._refresh_queue()
                    self.process = None
                    self.run_started_at = None
                    self.after(250, self._launch_next)
                else:
                    self._append_output(str(item))
        except queue.Empty:
            pass
        self.after(100, self._drain_output)

    def _record_history(self, run: dict[str, Any]) -> None:
        history = read_json(HISTORY_FILE, [])
        if not isinstance(history, list):
            history = []
        history.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rule_id": normalize_rule_id(run.get("rule_id")),
            "mode": run.get("mode", "canonical"),
            "mutation_id": run.get("mutation_id"),
            "status": run.get("status"),
            "folder": str(run.get("run_dir") or ""),
            "exit_code": run.get("exit_code"),
        })
        atomic_json(HISTORY_FILE, history[-5000:])

    def _refresh_queue(
        self,
        current: dict[str, Any] | None = None,
    ) -> None:
        self.queue_tree.delete(*self.queue_tree.get_children())

        rows = list(self.queue_runs)
        if not rows:
            if current is not None:
                rows.append(current)
            rows.extend(self.batch_queue)

        for index, run in enumerate(rows, 1):
            self.queue_tree.insert(
                "", "end",
                values=(
                    index,
                    normalize_rule_id(run.get("rule_id")),
                    (
                        run.get("mutation_id")
                        or (
                            f"{run['experimental_context']['condition_id']} "
                            f"[{run['experimental_context']['role']}]"
                            if run.get("experimental_context")
                            else "Canonical"
                        )
                    ),
                    run.get("mode", "canonical"),
                    run.get("status", "Waiting"),
                    str(run.get("run_dir") or ""),
                ),
            )
        waiting = sum(
            1 for item in rows if item.get("status") == "Waiting"
        )
        running = sum(
            1 for item in rows if item.get("status") == "Running"
        )
        finished = len(rows) - waiting - running
        self.queue_status_var.set(
            f"Queue: {running} running, {waiting} waiting, "
            f"{finished} finished"
        )

    def clear_queue(self) -> None:
        waiting_ids = {
            id(item) for item in self.batch_queue
        }
        self.batch_queue.clear()
        self.queue_runs = [
            item for item in self.queue_runs
            if id(item) not in waiting_ids
        ]
        self._refresh_queue(
            current=self.current_run if self.process is not None else None
        )
        self.status_var.set("Waiting queue cleared")

    def _refresh_history(self) -> None:
        if not hasattr(self, "history_tree"):
            return
        self.history_tree.delete(*self.history_tree.get_children())
        history = read_json(HISTORY_FILE, [])
        if not isinstance(history, list):
            history = []
        for index, row in enumerate(reversed(history[-1000:])):
            self.history_tree.insert(
                "", "end",
                iid=f"history_{index}",
                values=(
                    row.get("date", ""),
                    row.get("rule_id", ""),
                    row.get("mode", ""),
                    row.get("mutation_id") or "Canonical",
                    row.get("status", ""),
                    row.get("folder", ""),
                ),
            )

    def stop(self) -> None:
        for item in self.batch_queue:
            if item.get("status") == "Waiting":
                item["status"] = "Cancelled"
        self.batch_queue.clear()
        self._refresh_queue()
        if self.process is None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.status_var.set("Stop requested")
        except Exception as exc:
            messagebox.showerror("Stop failed", repr(exc))

    def _append_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _tick_status(self) -> None:
        self.sqlite_status_var.set(
            "SQLite: enabled"
            if self.sqlite_var.get()
            else "SQLite: disabled"
        )
        if self.run_started_at is not None:
            elapsed = int(time.time() - self.run_started_at)
            hours, rem = divmod(elapsed, 3600)
            minutes, seconds = divmod(rem, 60)
            self.runtime_status_var.set(
                f"Run time: {hours:02d}:{minutes:02d}:{seconds:02d}"
            )
        else:
            self.runtime_status_var.set("Run time: 00:00:00")
        self.after(500, self._tick_status)

    def _go_and_launch(self, target: str) -> None:
        if target == "run":
            self.notebook.select(self.run_tab)
            self.after(100, self.launch_canonical)

    def open_selected_folder(self) -> None:
        if self.selected_rule is None:
            return
        folder = self.selected_rule.get("folder")
        if folder:
            open_path(Path(folder))
            return
        rule_file = find_rule_file(int(self.selected_rule["rule_id"]))
        if rule_file is not None:
            open_path(rule_file.parent)

    def open_selected_mutations(self) -> None:
        if self.selected_rule is None:
            return
        open_path(
            MUTATION_ROOT
            / f"rule_{int(self.selected_rule['rule_id']):05d}"
        )

    def _open_queue_item(self, _event=None) -> None:
        selected = self.queue_tree.selection()
        if not selected:
            return
        values = self.queue_tree.item(selected[0], "values")
        if len(values) >= 6 and values[5]:
            open_path(Path(values[5]))

    def open_history_folder(self) -> None:
        selected = self.history_tree.selection()
        if not selected:
            return
        values = self.history_tree.item(selected[0], "values")
        if len(values) >= 6 and values[5]:
            open_path(Path(values[5]))

    def on_close(self) -> None:
        if self.process is not None:
            if not messagebox.askyesno(
                "Observer is running",
                "Stop the current Observer and close the laboratory?",
            ):
                return
            try:
                self.batch_queue.clear()
                os.killpg(self.process.pid, signal.SIGTERM)
            except Exception:
                pass
        self.destroy()


def main() -> int:
    app = ObserverLaboratory()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ARCHON RELEASE2.4 source-proven relocated compatibility dependencies.
_ARCHON_RELEASE2_RELOCATED_COMPATIBILITY_FILES = (
    'Analyzer_next/compatibility/legacy_analyzer/approved_action_planner_intake.py',
    'Analyzer_next/compatibility/legacy_analyzer/experiment_execution_dispatch.py',
    'Analyzer_next/compatibility/legacy_analyzer/experiment_launch_authorization.py',
    'Analyzer_next/compatibility/legacy_analyzer/production_runtime_recovery.py',
)
