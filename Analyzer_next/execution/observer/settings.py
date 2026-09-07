#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared configuration for the modular Observer launcher."""
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

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[3]
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
from Analyzer_next.production.runtime_routes import (
    COMPATIBILITY_ROOT,
    cli_route,
    compatibility_route,
)

VERSION = "Project ARCHON Observer Laboratory v3.5.4"
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
ANALYZER_LAUNCHER = PROJECT_ROOT / "ANALYZER.sh"
ANALYZER_ENTRYPOINT = cli_route("analyze_results.py")
PRODUCTION_RESEARCH_CYCLE_OWNER = cli_route(
    "production_research_cycle_orchestrator.py"
)
PRODUCTION_LAUNCHER_HANDOFF = cli_route(
    "production_research_cycle_launcher_handoff.py"
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
    ("Production handoff", PRODUCTION_LAUNCHER_HANDOFF),
    ("Production owner", PRODUCTION_RESEARCH_CYCLE_OWNER),
)

SPEED_VALUES = list(range(1, 11)) + list(range(20, 101, 10)) + [
    200, 500, 1000
]

# ARCHON RELEASE2.4 source-proven relocated compatibility dependencies.
_ARCHON_RELEASE2_RELOCATED_COMPATIBILITY_FILES = (
    'Analyzer_next/compatibility/legacy_analyzer/experiment_execution_dispatch.py',
    'Analyzer_next/compatibility/legacy_analyzer/experiment_launch_authorization.py',
)
