#!/usr/bin/env python3
"""
Universe Search Observer v5.0 Modular Phase 1

Standalone life observer/viewer for Universe Search.

New in v1.2:
- Writes live samples CSV while the world is running.
- Computes organism "health" = largest_object / peak_largest.
- Tracks center of mass and drift speed.
- Writes a life passport JSON + Markdown summary.
- Tracks legacy / post-collapse structure.
- Estimates identity persistence and information survival.
- Still writes event CSV and observation log.

Project layout:
    Project_ARCHON/
    ├── Observer/
    ├── Universe_Search/
    ├── Results/Universe_Search/
    └── Atlas/Worlds/

Examples from the project root:
    python3 -m Observer.universe_search_observer_v441_validation_calibration Results/Universe_Search 185 --log --passport
    python3 -m Observer.universe_search_observer_v441_validation_calibration Results/Universe_Search best --samples-csv --passport
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import re
import sys

from collections import deque
from datetime import datetime
from pathlib import Path

# Support both package execution and direct execution from Observer/.
_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent
_TELEMETRY_ROOT = _BOOTSTRAP_ROOT / "Telemetry"

for _bootstrap_path in (_TELEMETRY_ROOT, _BOOTSTRAP_ROOT):
    _bootstrap_text = str(_bootstrap_path)
    if _bootstrap_text in sys.path:
        sys.path.remove(_bootstrap_text)
    sys.path.insert(0, _bootstrap_text)

from archon_paths import (
    ATLAS_DIR,
    PROJECT_ROOT,
    SEARCH_RESULTS_DIR,
    WORLD_ATLAS_DIR,
    ensure_layout,
)

try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None

try:
    from Universe_Search import universe_search_core as base
except Exception as e:
    print("Could not import Universe_Search.universe_search_core")
    print(f"Expected project root: {PROJECT_ROOT}")
    print("Import error:", repr(e))
    raise


# ---------------- Loading worlds ----------------

def bounded_batch_steps(
    current_tick: int,
    requested_steps: int,
    max_ticks: int | None,
) -> int:
    """Return a frame batch that cannot cross an exact tick horizon."""
    requested = max(0, int(requested_steps))
    if not max_ticks:
        return requested
    remaining = max(0, int(max_ticks) - int(current_tick))
    return min(requested, remaining)


def iter_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_dicts(value)


def parse_rule_id(text):
    try:
        return int(text)
    except Exception:
        m = re.search(r"(\d+)", str(text))
        return int(m.group(1)) if m else None


def collect_world_records(results_dir: Path):
    records = []
    files = sorted(results_dir.glob("generation*.json"))
    files += sorted(results_dir.glob("best*.json"))

    # Canonical world library. Keep migration fallbacks until old data is moved.
    atlas_sources = [WORLD_ATLAS_DIR]
    legacy_results_atlas = results_dir / "atlas"
    if legacy_results_atlas.exists() and legacy_results_atlas != WORLD_ATLAS_DIR:
        atlas_sources.append(legacy_results_atlas)

    for atlas_dir in atlas_sources:
        if atlas_dir.exists():
            files += sorted(atlas_dir.rglob("*.json"))

    # Some current projects still keep indexes directly under Atlas/.
    for index_name in ("atlas_index.json", "atlas_index.jsonl"):
        index_path = ATLAS_DIR / index_name
        if index_path.exists():
            files.append(index_path)

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in iter_dicts(data):
            if not isinstance(node, dict):
                continue

            rule = None
            score = None
            metrics = {}

            if isinstance(node.get("rule"), dict):
                rule = node.get("rule")
                score = node.get("score")
                if isinstance(node.get("metrics"), dict):
                    metrics = node.get("metrics")
            elif "rule_id" in node and any(k in node for k in ("weights", "thresholds", "seed", "parent_a", "parent_b", "diffusion", "inertia", "damping", "terms")):
                rule = node

            if not isinstance(rule, dict):
                continue

            rid = rule.get("rule_id")
            if rid is None:
                continue

            gen = None
            m = re.search(r"generation[_-]?(\d+)", path.name)
            if m:
                gen = int(m.group(1))

            records.append({
                "rule_id": int(rid),
                "score": score if isinstance(score, (int, float)) else None,
                "metrics": metrics or {},
                "rule": rule,
                "source": str(path),
                "generation": gen,
                "class": metrics.get("class") or metrics.get("world_class") or metrics.get("classification"),
            })

    by_id = {}
    for rec in records:
        rid = rec["rule_id"]
        old = by_id.get(rid)
        if old is None:
            by_id[rid] = rec
            continue
        old_score = old["score"] if old["score"] is not None else -1e18
        new_score = rec["score"] if rec["score"] is not None else -1e18
        if new_score >= old_score:
            by_id[rid] = rec

    return list(by_id.values())


def choose_record(results_dir: Path, selector: str, extra: str | None = None):
    records = collect_world_records(results_dir)
    if not records:
        raise SystemExit(f"No world records found in {results_dir}")

    selector_l = str(selector).strip().lower()

    if selector_l not in ("best", "top", "outlier", "family", "list"):
        rid = parse_rule_id(selector_l)
        if rid is not None:
            for rec in records:
                if rec["rule_id"] == rid:
                    return rec
            raise SystemExit(f"Rule {rid} not found in {results_dir}")

    scored = [r for r in records if r["score"] is not None]
    scored.sort(key=lambda r: r["score"], reverse=True)

    if selector_l == "list":
        print("Top available worlds:")
        for i, r in enumerate(scored[:30], 1):
            m = r["metrics"]
            print(
                f"{i:02d}. rule {r['rule_id']:05d} "
                f"score={r['score'] if r['score'] is not None else 'n/a'} "
                f"gen={r.get('generation')} "
                f"memory={m.get('memory_trace_score')} "
                f"tracks={m.get('persistent_tracks')} "
                f"flow={m.get('ms_flow')} "
                f"rotation={m.get('ms_rotation_flow')} "
                f"crystal={m.get('crystal_order')} "
                f"quasi={m.get('quasi_particle_score')}"
            )
        raise SystemExit(0)

    if selector_l == "best":
        return scored[0] if scored else records[0]

    if selector_l == "top":
        n = max(1, int(extra or "1"))
        return scored[min(n - 1, len(scored) - 1)] if scored else records[0]

    if selector_l == "family":
        fam = (extra or "").lower().strip()
        if not fam:
            raise SystemExit('Family name required, e.g. family "Entity Memory Ecology"')
        matches = []
        for r in records:
            klass = str(r.get("class") or r["metrics"].get("class") or "")
            if fam in klass.lower():
                matches.append(r)
        if not matches:
            raise SystemExit(f"No records found for family: {extra}")
        matches.sort(key=lambda r: r["score"] if r["score"] is not None else -1e18, reverse=True)
        return matches[0]

    if selector_l == "outlier":
        md = results_dir / "research_report" / "research_summary.md"
        if md.exists():
            text = md.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"### rule\s+(\d+)", text, flags=re.I)
            if m:
                rid = int(m.group(1))
                for r in records:
                    if r["rule_id"] == rid:
                        return r

        def weird(r):
            m = r["metrics"]
            return (
                float(m.get("ms_flow", 0) or 0) * 4
                + float(m.get("ms_rotation_flow", 0) or 0) * 4
                + float(m.get("defect_motion", 0) or 0) * 2
                + float(m.get("quasi_particle_score", 0) or 0)
            )
        return max(records, key=weird)

    raise SystemExit(f"Unknown selector: {selector}")


# ---------------- Visuals ----------------

def rgb_hex(a: float):
    a = max(0.0, min(1.0, float(a)))
    blue = int((1.0 - a) * 230)
    yellow = int(a * 255)
    green = int(120 + 90 * (1.0 - abs(a - 0.5) * 2))
    return f"#{yellow:02x}{green:02x}{blue:02x}"


# ---------------- Observer ----------------

from Observer.observer_chronicle import ObserverChronicleMixin
from Observer.observer_ecology_metrics import ObserverEcologyMetricsMixin
from Observer.observer_scientific_layers import ObserverScientificLayersMixin
from Observer.observer_geometry_morphology import ObserverGeometryMorphologyMixin
from Observer.observer_lineage import ObserverLineageMixin
from Observer.observer_life_evidence import ObserverLifeEvidenceMixin

from Observer.observer_evidence_integration import LiveObserverEvidenceSession
from Observer.observer_lifecycle_telemetry import (
    LifecycleTelemetryShadowPublisher,
)
from Observer.observer_lifecycle_signal_bridge import (
    ObserverLifecycleSignalBridge,
)
from Observer.observer_lifecycle_ui import build_lifecycle_ui_snapshot
from Observer.observer_morphology_runtime import (
    build_morphology_runtime_snapshot,
)

from Scientific_Ontology.observer_state import ObserverState
from Scientific_Ontology.lifecycle_summary import summarize_lifecycle_state
from Scientific_Ontology.lifecycle_temporal_integrity import (
    assess_lifecycle_temporal_integrity,
)

from Telemetry.telemetry import ErrorPolicy, Telemetry
from Telemetry.writers.csv_writer import CsvWriter
from Telemetry.writers.sqlite_writer import SQLiteWriter, SQLiteWriterConfig
from Experiments.experimental_conditions import (
    BoundaryMode,
    ExperimentalConditionsError,
    ExperimentalConditionsRepository,
    ExperimentRole,
    InitialStateMode,
    Topology,
)


class _TelemetryChannelProxy:
    """Compatibility bridge for mixins that still call DictWriter.writerow()."""

    def __init__(self, telemetry: Telemetry, channel: str):
        self.telemetry = telemetry
        self.channel = channel

    def writerow(self, row):
        self.telemetry.emit(self.channel, row)

    def writeheader(self):
        # Headers are owned by CsvWriter.
        return None


class _TelemetryFileProxy:
    """Compatibility bridge for legacy file.flush()/close() calls."""

    def __init__(self, telemetry: Telemetry):
        self.telemetry = telemetry

    def flush(self):
        if not self.telemetry.closed:
            self.telemetry.flush()

    def close(self):
        # LifeObserver.close_live_files() owns the single final close.
        return None


class LifeObserver(
    ObserverChronicleMixin,
    ObserverEcologyMetricsMixin,
    ObserverScientificLayersMixin,
    ObserverGeometryMorphologyMixin,
    ObserverLineageMixin,
    ObserverLifeEvidenceMixin,
):
    def __init__(
        self,
        threshold: float = 0.18,
        min_object_cells: int = 8,
        collapse_grace: int = 250,
        sample_every: int = 1,
        event_grace: int = 5,
        live_flush_every: int = 100,
        samples_path: Path | None = None,
        events_path: Path | None = None,
        pressure_timeline_path: Path | None = None,
        pressure_timeline_every: int = 100,
        chronicle_path: Path | None = None,
        topology: str = "torus",
        boundary_mode: str = "wrap",
    ):
        self.threshold = threshold
        self.min_object_cells = min_object_cells
        self.collapse_grace = collapse_grace
        self.sample_every = max(1, sample_every)
        self.event_grace = max(1, event_grace)
        self.live_flush_every = max(1, live_flush_every)
        self.topology = str(topology)
        self.boundary_mode = str(boundary_mode)

        self.samples_path = samples_path
        self.events_path = events_path
        self.pressure_timeline_path = pressure_timeline_path
        self.pressure_timeline_every = max(1, int(pressure_timeline_every or 100))
        self.chronicle_path = chronicle_path
        self._sample_file = None
        self._sample_writer = None
        self._event_file = None
        self._event_writer = None
        self._pressure_timeline_file = None
        self._chronicle_file = None
        self._pressure_timeline_writer = None
        self._pressure_rows_since_flush = 0
        self._chronicle_file = None
        self._chronicle_writer = None
        self._chronicle_rows_since_flush = 0

        self.birth_tick = None
        self.last_alive_tick = None
        self.collapse_tick = None

        self.peak_cells = 0
        self.peak_objects = 0
        self.peak_largest = 0
        self.peak_total_living_mass = 0
        self.peak_top10_mass = 0
        self.peak_tick = None
        self.longest_age = 0

        # Ecology dynamics:
        # distinguishes real colony growth from single-object fragmentation.
        self.prev_total_living_mass = None
        self.prev_defect_cells = None
        self.prev_objects_count = None
        self.mass_delta = 0
        self.defect_delta = 0
        self.object_delta = 0
        self.event_window_ticks = 1000

        # Colony size distribution.
        self.large_colonies = 0
        self.medium_colonies = 0
        self.small_colonies = 0
        self.dominance_ratio = 0.0
        self.top3_mass = 0
        self.top5_mass = 0
        self.top_sizes = []

        # Population history over a rolling window.
        self.history_window_ticks = 1000
        self.population_history = deque(maxlen=5000)
        self.history_delta_objects = 0
        self.history_delta_mass = 0
        self.history_delta_largest = 0
        self.mass_growth_per_tick = 0.0
        self.objects_growth_per_tick = 0.0
        self.largest_growth_per_tick = 0.0
        self.stability_index = 0.0

        # High-level ecosystem phase.
        self.ecosystem_phase = "WARMUP"
        self.prev_ecosystem_phase = None
        self.phase_min_window = 200

        # Evolution chronicle state.
        self.chronicle_counts = {}
        self.last_growth_phase_seen = None
        self.last_evo_phase_seen = None
        self.last_pressure_peak_tick = None
        self.in_pressure_crisis = False
        self.in_mass_extinction = False
        self.mass_extinction_start_tick = None
        self.mass_extinction_peak_pressure = 0.0
        self.last_dominant_family = None
        self.dominance_reported_for_family = set()
        self.super_dynasty_reported_for_family = set()
        self.family_live_counts_prev = {}
        self.current_era = None
        self.era_start_tick = None
        self.story_era = None
        self.story_era_start_tick = None
        self.story_era_line = ""
        self.story_era_count = 0
        self.story_era_min_duration = 120
        self.story_pending_era = None
        self.story_pending_since = None
        self.ecosystem_collapsed = False
        self.ecosystem_collapse_tick = None
        self.last_chronicle_event_line = ""
        self.last_chronicle_severity = ""
        self.history_book = []
        self.history_book_limit = 2000
        self.chronicle_severity_counts = {"MINOR": 0, "NORMAL": 0, "MAJOR": 0, "CRITICAL": 0, "HISTORIC": 0}
        self.chronicle_last_tick_by_event = {}

        # Probabilistic colony tracking.
        self.next_colony_id = 1
        self.next_family_id = 1
        self.tracks = {}
        self.track_match_radius = 12.0
        self.offspring_radius = 18.0
        self.track_missing_grace = 50

        self.active_families = 0
        self.active_colonies_tracked = 0
        self.new_colonies_this_tick = 0
        self.extinct_colonies_total = 0
        self.extinct_families_total = 0
        self.largest_family_size = 0
        self.deepest_generation = 0
        self.oldest_lineage_age = 0
        self.lineage_summary = ""

        # Dynasty stats: long-term family/species biography.
        self.family_stats = {}
        self.dynasty_leader_id = None
        self.dynasty_line = ""

        # Global demography: whole-ecosystem birth/death/lifetime pressure.
        self.total_colonies_born = 0
        self.total_colonies_dead = 0
        self.colony_lifetimes = []
        self.max_colony_lifetime = 0
        self.demography_line = ""

        # Evolution pressure timeline: compact sparkline history, no images needed.
        self.evo_timeline = deque(maxlen=96)
        self.evo_timeline_line = ""

        # Civilization layer: interpret mature colony ecologies as proto-social systems.
        # This does not change the simulation. It observes cities, trade, conflict,
        # specialization, technology, cohesion, and civilizational rise/fall.
        self.civilization_history = deque(maxlen=5000)
        self.civilization_stage = "NONE"
        self.prev_civilization_stage = None
        self.civilization_started_tick = None
        self.civilization_peak_score = 0.0
        self.civilization_peak_tick = None
        self.civilization_count = 0
        self.civilization_line = ""
        self.civilization_last_event = ""
        self.civilization_event_counts = {}
        self.civilization_stage_min_duration = 160
        self.civilization_pending_stage = None
        self.civilization_pending_since = None

        # Knowledge layer: cultural memory inside families. It observes whether
        # stable lineages can accumulate, lose, and exchange useful information.
        self.knowledge_axes = ("exploration", "cooperation", "aggression", "efficiency", "adaptation", "memory")
        self.family_knowledge = {}
        self.knowledge_history = deque(maxlen=5000)
        self.knowledge_line = "KNOW none"
        self.knowledge_peak_score = 0.0
        self.knowledge_peak_tick = None
        self.knowledge_memory_peak = 0.0
        self.knowledge_memory_peak_tick = None
        self.knowledge_last_event = ""
        self.knowledge_event_counts = {}
        self.knowledge_discoveries = set()
        self.knowledge_decay_base = 0.002

        # Feedback layer: measures whether accumulated information begins to
        # buffer pressure, improve survival, and redirect the future trajectory.
        # This layer is intentionally conservative: it does not rewrite the core
        # cellular automaton, but creates a causal proxy that can be compared
        # across rules, generations, and long runs.
        self.feedback_history = deque(maxlen=5000)
        self.feedback_line = "FB none"
        self.feedback_peak_score = 0.0
        self.feedback_peak_tick = None
        self.feedback_event_counts = {}
        self.feedback_last_event = ""
        self.feedback_prev_regime = None
        self.feedback_prev_score = 0.0

        # Emergence Evidence layer: combines independent observer signals into
        # a conservative confidence score. It does not change the world. It
        # only asks: how much evidence do we have that stable complex
        # organization emerged from the rule dynamics?
        self.emergence_history = deque(maxlen=5000)
        self.emergence_line = "EMG none"
        self.emergence_peak_score = 0.0
        self.emergence_peak_tick = None
        self.emergence_prev_confidence = "NONE"
        self.emergence_last_event = ""
        self.emergence_event_counts = {}

        # Validation & Calibration layer: audits the observer itself.
        # It estimates whether the current emergence verdict is stable,
        # explainable, and internally consistent. No world dynamics are changed.
        self.validation_history = deque(maxlen=5000)
        self.validation_line = "VAL none"
        self.validation_quality_peak = 0.0
        self.validation_last_event = ""
        self.validation_event_counts = {}
        self.validation_prev_grade = "NONE"

        # Phase 2: conservative competing-hypothesis life evidence.  The old
        # size-based ``alive`` flag remains available for compatibility.
        self._init_life_evidence_model()

        # Morphology layer: shape-level diagnostics.
        # Stage 13.1 observes geometry only. It does not change world dynamics,
        # lineage tracking, validation, stopping logic, or scores.
        self.morphology_history = deque(maxlen=5000)
        self.morphology_line = "MORPH none"
        self.morphology_prev_signature = None
        self.morphology_stable_ticks = 0
        self.morphology_peak_complexity = 0.0
        self.morphology_peak_change = 0.0
        self.morphology_prev_class = None
        self.morphology_class_start_tick = None
        self.morphology_class_counts = {}
        self.morphology_transition_count = 0
        self.morphology_major_transition_count = 0
        self.morphology_longest_stable_ticks = 0
        self.morphology_last_event = ""
        self.morphology_score_peak = 0.0
        self.morphology_dominant_class = "none"
        self.boundary_prev_complete_tick = {side: None for side in ("top", "right", "bottom", "left")}

        self.identity_health_sum = 0.0
        self.identity_health_samples = 0
        self.identity_persistence = 0.0
        self.post_collapse_structure = 0.0
        self.legacy_score = 0.0
        self.information_survival = 0.0
        self.expansion_front_speed = 0.0
        self.first_large_structure_tick = None
        self.first_full_field_tick = None

        self.center_start = None
        self.center_current = None
        self.center_prev = None
        self.total_drift = 0.0
        self.max_step_drift = 0.0

        self.samples = []
        self.events = []
        self.last_event = "no events yet"

        self.current = {
            "objects": 0,
            "defect_cells": 0,
            "largest": 0,
            "total_living_mass": 0,
            "top10_mass": 0,
            "mean_object_size": 0.0,
            "ecosystem_health": 0.0,
            "mass_delta": 0,
            "defect_delta": 0,
            "object_delta": 0,
            "fragmentation_index": 0.0,
            "split_rate_1000": 0.0,
            "merge_rate_1000": 0.0,
            "birth_rate_1000": 0.0,
            "death_rate_1000": 0.0,
            "growth_phase": "seed",
            "large_colonies": 0,
            "medium_colonies": 0,
            "small_colonies": 0,
            "top3_mass": 0,
            "top5_mass": 0,
            "dominance_ratio": 0.0,
            "top_sizes": [],
            "history_delta_objects": 0,
            "history_delta_mass": 0,
            "history_delta_largest": 0,
            "mass_growth_per_tick": 0.0,
            "objects_growth_per_tick": 0.0,
            "largest_growth_per_tick": 0.0,
            "stability_index": 0.0,
            "history_window": 0,
            "ecosystem_phase": "WARMUP",
            "active_families": 0,
            "active_colonies_tracked": 0,
            "new_colonies_this_tick": 0,
            "extinct_colonies_total": 0,
            "extinct_families_total": 0,
            "largest_family_size": 0,
            "deepest_generation": 0,
            "oldest_lineage_age": 0,
            "lineage_summary": "",
            "dynasty_leader_id": None,
            "dynasty_line": "",
            "dynasty_age": 0,
            "dynasty_born": 0,
            "dynasty_living": 0,
            "dynasty_dead": 0,
            "dynasty_peak_living": 0,
            "dynasty_dominance": 0.0,
            "dynasty_survival": 0.0,
            "dynasty_turnover": 0.0,
            "dynasty_birth_rate": 0.0,
            "dynasty_death_rate": 0.0,
            "dynasty_max_generation": 0,
            "dynasty_largest_colony": 0,
            "dynasty_mass": 0,
            "demo_born_total": 0,
            "demo_dead_total": 0,
            "demo_alive_tracked": 0,
            "demo_mean_life": 0.0,
            "demo_max_life": 0,
            "demo_birth_rate_1000": 0.0,
            "demo_death_rate_1000": 0.0,
            "demo_turnover_1000": 0.0,
            "demo_replacement": 0.0,
            "demo_survival_ratio": 0.0,
            "demography_line": "",
            "evo_stress": 0.0,
            "evo_adapt": 0.0,
            "evo_pressure": 0.0,
            "evo_recovery": 0.0,
            "evo_extinction_risk": 0.0,
            "evo_phase": "SEED",
            "evolution_line": "",
            "evo_src_frag_pct": 0.0,
            "evo_src_death_pct": 0.0,
            "evo_src_loss_pct": 0.0,
            "evo_src_inst_pct": 0.0,
            "evo_src_dom_pct": 0.0,
            "evo_cause": "NONE",
            "evo_source_line": "",
            "evo_timeline_line": "",
            "evo_stress_trend": 0.0,
            "evo_adapt_trend": 0.0,
            "evo_pressure_trend": 0.0,
            "evo_risk_trend": 0.0,
            "evo_timeline_len": 0,
            "chronicle_last": "",
            "chronicle_last_severity": "",
            "history_book_len": 0,
            "civ_stage": "NONE",
            "civ_score": 0.0,
            "civ_age": 0,
            "civ_cities": 0,
            "civ_capital_size": 0,
            "civ_urban_mass": 0,
            "civ_urbanization": 0.0,
            "civ_trade_index": 0.0,
            "civ_conflict_index": 0.0,
            "civ_cohesion": 0.0,
            "civ_specialization": 0.0,
            "civ_tech_index": 0.0,
            "civ_culture_index": 0.0,
            "civ_collapse_risk": 0.0,
            "civ_line": "",
            "civ_peak_score": 0.0,
            "civ_peak_tick": None,
            "civ_count": 0,
            "knowledge_score": 0.0,
            "knowledge_peak_score": 0.0,
            "knowledge_age": 0,
            "knowledge_families": 0,
            "knowledge_dominant_family": None,
            "knowledge_dominant_axis": "none",
            "knowledge_exploration": 0.0,
            "knowledge_cooperation": 0.0,
            "knowledge_aggression": 0.0,
            "knowledge_efficiency": 0.0,
            "knowledge_adaptation": 0.0,
            "knowledge_memory": 0.0,
            "knowledge_memory_peak": 0.0,
            "knowledge_memory_peak_tick": None,
            "knowledge_transfer": 0.0,
            "knowledge_loss": 0.0,
            "knowledge_discoveries": "",
            "knowledge_line": "KNOW none",
            "feedback_score": 0.0,
            "feedback_peak_score": 0.0,
            "feedback_regime": "NONE",
            "feedback_survival_bonus": 0.0,
            "feedback_pressure_buffer": 0.0,
            "feedback_effective_pressure": 0.0,
            "feedback_effective_risk": 0.0,
            "feedback_self_direction": 0.0,
            "feedback_environment_impact": 0.0,
            "feedback_knowledge_impact": 0.0,
            "feedback_response_capacity": 0.0,
            "feedback_response_opportunity": 0.0,
            "feedback_observed_response": 0.0,
            "feedback_legacy_score": 0.0,
            "feedback_metric_version": "2.0",
            "feedback_metric_independence_status": "STRUCTURALLY_INDEPENDENT_V2",
            "feedback_line": "FB none",
            "emergence_score": 0.0,
            "emergence_peak_score": 0.0,
            "emergence_confidence": "NONE",
            "emergence_evidence_count": 0,
            "emergence_positive_evidence": "",
            "emergence_negative_evidence": "",
            "emergence_complexity_index": 0.0,
            "emergence_stability_signal": 0.0,
            "emergence_line": "EMG none",
            "validation_quality": 0.0,
            "validation_grade": "NONE",
            "validation_repeatability": 0.0,
            "validation_stability_confidence": 0.0,
            "validation_false_positive_risk": 0.0,
            "validation_false_negative_risk": 0.0,
            "validation_noise_sensitivity": 0.0,
            "validation_warning": "",
            "validation_explain": "",
            "validation_line": "VAL none",
            **build_morphology_runtime_snapshot(),
            "bbox_min_x": None,
            "bbox_max_x": None,
            "bbox_min_y": None,
            "bbox_max_y": None,
            "bbox_width": 0,
            "bbox_height": 0,
            "top_edge_fill": 0.0,
            "right_edge_fill": 0.0,
            "bottom_edge_fill": 0.0,
            "left_edge_fill": 0.0,
            "top_edge_run": 0.0,
            "right_edge_run": 0.0,
            "bottom_edge_run": 0.0,
            "left_edge_run": 0.0,
            "story_era": "Genesis",
            "story_era_age": 0,
            "story_era_line": "ERA Genesis 0t",
            "story_era_count": 0,
            "alive": False,
            "age": 0,
            "changed": 0,
            "health": 0.0,
            "cx": None,
            "cy": None,
            "step_drift": 0.0,
            "total_drift": 0.0,
            "legacy_score": 0.0,
            "identity_persistence": 0.0,
            "information_survival": 0.0,
            "post_collapse_structure": 0.0,
        }

        self._prev_grid = None
        self._prev_objects = None
        self._stable_objects = None
        self._stable_since = None
        self._samples_since_flush = 0

        # Evidence Framework v1 integration. Configured by main() after the
        # rule record and output directory are known.
        self._evidence_session = None
        self._evidence_enabled = False
        self._evidence_last_tick = None
        self._evidence_last_result = None

        # Telemetry is configured by main() after run_id and database path
        # are known. Until then all compatibility writer attributes stay None.
        self.telemetry = None
        self.telemetry_run_id = None
        self.telemetry_database_path = None

        # Scientific Ontology Stage 1B. This is a read-only publication layer:
        # it mirrors the existing Observer snapshot without changing any
        # classifier, event, auto-stop, CSV, or SQLite behaviour.
        self.observer_state = None
        self.observer_state_world_id = None
        self.observer_state_run_id = None
        self.observer_state_version = None
        self._ontology_lifecycle_publisher = (
            LifecycleTelemetryShadowPublisher()
        )
        self._ontology_lifecycle_signal_bridge = (
            ObserverLifecycleSignalBridge(
                extinction_grace_ticks=self.collapse_grace,
            )
        )

    def configure_observer_state_contract(
        self,
        *,
        world_id: str,
        run_id: str,
        observer_version: str,
    ):
        """Configure identity metadata for the read-only ObserverState mirror.

        Stage 1B deliberately does not replace legacy fields or write the
        contract into sample telemetry. It only publishes a canonical nested
        snapshot in ``self.current["observer_state"]`` and passports.
        """
        self.observer_state_world_id = str(world_id)
        self.observer_state_run_id = str(run_id)
        self.observer_state_version = str(observer_version)
        self._ontology_lifecycle_publisher.reset()
        self._ontology_lifecycle_signal_bridge.reset()
        self._publish_observer_state()

    def _publish_observer_state(self):
        """Build and attach a canonical read-only mirror of ``self.current``."""
        if not all((
            self.observer_state_world_id,
            self.observer_state_run_id,
            self.observer_state_version,
        )):
            return None

        # Avoid recursively wrapping a previously published contract.
        source = dict(self.current)
        source.pop("observer_state", None)
        state = ObserverState.from_legacy_snapshot(
            source,
            world_id=self.observer_state_world_id,
            run_id=self.observer_state_run_id,
            observer_version=self.observer_state_version,
        )
        self.observer_state = state
        self.current["observer_state"] = state.to_dict()
        self._ontology_lifecycle_publisher.publish(
            state,
            getattr(self, "telemetry", None),
        )
        return state

    def _passport_observer_state(self, final_tick):
        """Build a fresh, temporally valid ObserverState for one passport.

        Runtime publication is intentionally cached for telemetry and UI use.
        A passport is a persistence boundary, so it must not serialize an
        earlier cached state when ``self.current`` has advanced.  The
        ``final_tick`` supplied by every save path is the observed run horizon.
        """
        if not all((
            self.observer_state_world_id,
            self.observer_state_run_id,
            self.observer_state_version,
        )):
            observer_state = (
                self.observer_state.to_dict()
                if self.observer_state is not None
                else None
            )
            return (
                observer_state,
                summarize_lifecycle_state(observer_state),
                None,
            )

        source = dict(self.current)
        source.pop("observer_state", None)
        try:
            current_tick = max(0, int(source.get("tick", 0)))
        except (TypeError, ValueError):
            current_tick = 0
        try:
            persisted_tick = max(current_tick, int(final_tick))
        except (TypeError, ValueError):
            persisted_tick = current_tick
        source["tick"] = persisted_tick

        state = ObserverState.from_legacy_snapshot(
            source,
            world_id=self.observer_state_world_id,
            run_id=self.observer_state_run_id,
            observer_version=self.observer_state_version,
        )
        observer_state = state.to_dict()
        lifecycle_summary = summarize_lifecycle_state(observer_state)
        raw_events = observer_state.get("events")
        integrity = assess_lifecycle_temporal_integrity(
            lifecycle_summary,
            raw_events,
            raw_events_available=isinstance(raw_events, list),
        )
        if integrity["status"] != "valid":
            codes = ", ".join(integrity.get("issue_codes") or ["unknown"])
            raise RuntimeError(
                "Refusing to write a temporally invalid lifecycle passport: "
                f"{codes}"
            )

        self.observer_state = state
        self.current["observer_state"] = observer_state
        return observer_state, lifecycle_summary, integrity

    def configure_telemetry(
        self,
        *,
        run_id: str,
        rule_id: int,
        world_id: str,
        observer_version: str,
        database_path: Path | None,
        source_path: str | None = None,
        run_metadata: dict | None = None,
        enable_sqlite: bool = True,
    ):
        """Configure dual CSV + SQLite telemetry without changing mixins."""

        if self.telemetry is not None and not self.telemetry.closed:
            self.telemetry.close()

        writers = []

        csv_writer = CsvWriter(
            samples_path=self.samples_path,
            events_path=self.events_path,
            pressure_path=self.pressure_timeline_path,
            chronicle_path=self.chronicle_path,
            flush_every=self.live_flush_every,
            pressure_flush_every=max(1, self.live_flush_every),
            chronicle_flush_every=max(1, self.live_flush_every),
            strict=True,
        )
        writers.append(csv_writer)

        sqlite_writer = None
        if enable_sqlite:
            if database_path is None:
                raise ValueError(
                    "database_path is required when SQLite telemetry is enabled"
                )
            sqlite_writer = SQLiteWriter(
                database_path=database_path,
                run_id=run_id,
                rule_id=rule_id,
                world_id=world_id,
                observer_version=observer_version,
                source_path=source_path,
                metadata={
                    "samples_csv": str(self.samples_path) if self.samples_path else None,
                    "events_csv": str(self.events_path) if self.events_path else None,
                    "pressure_csv": (
                        str(self.pressure_timeline_path)
                        if self.pressure_timeline_path
                        else None
                    ),
                    "chronicle_csv": (
                        str(self.chronicle_path)
                        if self.chronicle_path
                        else None
                    ),
                    **dict(run_metadata or {}),
                },
                config=SQLiteWriterConfig(
                    batch_size=max(50, self.live_flush_every),
                    duplicate_sample_policy="replace",
                    duplicate_pressure_policy="replace",
                    finalize_on_close=True,
                    close_status="completed",
                ),
            )
            writers.append(sqlite_writer)

        self.telemetry = Telemetry(
            writers,
            error_policy=ErrorPolicy.RAISE,
            disable_writer_after_error=False,
        )
        self.telemetry_run_id = run_id
        self.telemetry_database_path = (
            Path(database_path) if database_path is not None else None
        )

        # Existing Observer and mixin code can continue using writerow()/flush().
        self._sample_writer = _TelemetryChannelProxy(
            self.telemetry,
            "sample",
        ) if self.samples_path is not None else None
        self._event_writer = _TelemetryChannelProxy(
            self.telemetry,
            "event",
        ) if self.events_path is not None else None
        self._pressure_timeline_writer = _TelemetryChannelProxy(
            self.telemetry,
            "pressure",
        ) if self.pressure_timeline_path is not None else None
        self._chronicle_writer = _TelemetryChannelProxy(
            self.telemetry,
            "chronicle",
        ) if self.chronicle_path is not None else None

        flush_proxy = _TelemetryFileProxy(self.telemetry)
        self._sample_file = (
            flush_proxy if self.samples_path is not None else None
        )
        self._event_file = (
            flush_proxy if self.events_path is not None else None
        )
        self._pressure_timeline_file = (
            flush_proxy
            if self.pressure_timeline_path is not None
            else None
        )
        self._chronicle_file = (
            flush_proxy if self.chronicle_path is not None else None
        )

        # Stage 2B shadow output: publish any canonical lifecycle events that
        # were already present when the ObserverState contract was configured.
        # This does not append to the legacy UI event list or affect control
        # flow, collapse handling, auto-stop, or Analyzer classification.
        self._ontology_lifecycle_publisher.publish(
            self.observer_state,
            self.telemetry,
        )

        print(
            f"[telemetry] run_id={run_id} "
            f"csv={'on' if any((self.samples_path, self.events_path, self.pressure_timeline_path, self.chronicle_path)) else 'off'} "
            f"sqlite={'on' if sqlite_writer is not None else 'off'}"
        )
        if sqlite_writer is not None:
            print(f"[telemetry] database: {database_path}")

    def _open_live_files(self):
        """Deprecated compatibility hook.

        Live storage is now configured through configure_telemetry().
        """
        return None

    def close_live_files(self):
        if self.telemetry is not None:
            self.telemetry.close()

        self._sample_file = None
        self._sample_writer = None
        self._event_file = None
        self._event_writer = None
        self._pressure_timeline_file = None
        self._pressure_timeline_writer = None
        self._chronicle_file = None
        self._chronicle_writer = None


    @staticmethod
    def _boundary_geometry(mask):
        """Measure the occupied bounding box and completion of each boundary side."""
        h = len(mask)
        w = len(mask[0]) if h else 0
        coords = [(x, y) for y in range(h) for x in range(w) if mask[y][x]]
        empty = {
            "bbox_min_x": None, "bbox_max_x": None,
            "bbox_min_y": None, "bbox_max_y": None,
            "bbox_width": 0, "bbox_height": 0,
            "top_edge_fill": 0.0, "right_edge_fill": 0.0,
            "bottom_edge_fill": 0.0, "left_edge_fill": 0.0,
            "top_edge_run": 0.0, "right_edge_run": 0.0,
            "bottom_edge_run": 0.0, "left_edge_run": 0.0,
        }
        if not coords:
            return empty

        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        bw, bh = max_x - min_x + 1, max_y - min_y + 1

        top = [bool(mask[min_y][x]) for x in range(min_x, max_x + 1)]
        bottom = [bool(mask[max_y][x]) for x in range(min_x, max_x + 1)]
        left = [bool(mask[y][min_x]) for y in range(min_y, max_y + 1)]
        right = [bool(mask[y][max_x]) for y in range(min_y, max_y + 1)]

        def fill(values):
            return sum(values) / max(1, len(values))

        def longest_run(values):
            best = current = 0
            for value in values:
                current = current + 1 if value else 0
                best = max(best, current)
            return best / max(1, len(values))

        return {
            "bbox_min_x": min_x, "bbox_max_x": max_x,
            "bbox_min_y": min_y, "bbox_max_y": max_y,
            "bbox_width": bw, "bbox_height": bh,
            "top_edge_fill": fill(top), "right_edge_fill": fill(right),
            "bottom_edge_fill": fill(bottom), "left_edge_fill": fill(left),
            "top_edge_run": longest_run(top), "right_edge_run": longest_run(right),
            "bottom_edge_run": longest_run(bottom), "left_edge_run": longest_run(left),
        }

    def update(self, grid, tick):
        if tick % self.sample_every:
            return self.current

        mask, defect_cells, center = self._defect_mask(grid)
        boundary = self._boundary_geometry(mask)
        component_records = self._component_records(mask)
        sizes = [r["size"] for r in component_records]
        objects = len(sizes)
        largest = sizes[0] if sizes else 0

        # Ecosystem metrics: better for colony worlds where life is distributed
        # across many fragments instead of one dominant object.
        total_living_mass = sum(sizes)
        top10_mass = sum(sizes[:10])
        mean_object_size = total_living_mass / objects if objects else 0.0
        morphology = self._update_morphology_layer(tick, component_records, total_living_mass)
        morphology.update(boundary)

        self.peak_total_living_mass = max(self.peak_total_living_mass, total_living_mass)
        self.peak_top10_mass = max(self.peak_top10_mass, top10_mass)

        changed = 0
        if self._prev_grid is not None:
            h = len(grid)
            w = len(grid[0]) if h else 0
            for y in range(h):
                for x in range(w):
                    if abs(float(grid[y][x]) - float(self._prev_grid[y][x])) > 0.05:
                        changed += 1
        self._prev_grid = [list(row) for row in grid]

        alive = largest >= self.min_object_cells

        if alive:
            if self.birth_tick is None:
                self.birth_tick = tick
                self.add_event(tick, "life-start", f"largest={largest}, objects={objects}")
            self.last_alive_tick = tick

            if largest > self.peak_largest:
                self.peak_largest = largest
                self.peak_tick = tick
                self.add_event(tick, "peak-largest", f"largest={largest}, objects={objects}")

            self.peak_cells = max(self.peak_cells, defect_cells)
            self.peak_objects = max(self.peak_objects, objects)

            if center[0] is not None:
                self.center_current = center
                if self.center_start is None:
                    self.center_start = center
                if self.center_prev is not None:
                    step = self._center_distance(self.center_prev, center)
                    self.total_drift += step
                    self.max_step_drift = max(self.max_step_drift, step)
                self.center_prev = center

        age = 0
        if self.birth_tick is not None and self.last_alive_tick is not None:
            age = self.last_alive_tick - self.birth_tick
            self.longest_age = max(self.longest_age, age)

        health = largest / self.peak_largest if self.peak_largest else 0.0
        ecosystem_health = (
            total_living_mass / self.peak_total_living_mass
            if self.peak_total_living_mass
            else 0.0
        )

        if self.prev_total_living_mass is None:
            mass_delta = 0
            defect_delta = 0
            object_delta = 0
        else:
            mass_delta = total_living_mass - self.prev_total_living_mass
            defect_delta = defect_cells - self.prev_defect_cells
            object_delta = objects - self.prev_objects_count

        self.prev_total_living_mass = total_living_mass
        self.prev_defect_cells = defect_cells
        self.prev_objects_count = objects

        self.mass_delta = mass_delta
        self.defect_delta = defect_delta
        self.object_delta = object_delta

        fragmentation_index = objects / total_living_mass if total_living_mass else 0.0
        colony_dist = self._colony_size_distribution(sizes)

        self.large_colonies = colony_dist["large_colonies"]
        self.medium_colonies = colony_dist["medium_colonies"]
        self.small_colonies = colony_dist["small_colonies"]
        self.top3_mass = colony_dist["top3_mass"]
        self.top5_mass = colony_dist["top5_mass"]
        self.dominance_ratio = colony_dist["dominance_ratio"]
        self.top_sizes = colony_dist["top_sizes"]

        lineage = self._update_lineage_tracking(component_records, tick)
        dynasty = self._update_dynasty_stats(tick, total_living_mass)
        demo = self._update_demography_stats(tick)

        history = self._update_population_history(
            tick=tick,
            objects=objects,
            total_living_mass=total_living_mass,
            largest=largest,
        )
        self.history_delta_objects = history["history_delta_objects"]
        self.history_delta_mass = history["history_delta_mass"]
        self.history_delta_largest = history["history_delta_largest"]
        self.mass_growth_per_tick = history["mass_growth_per_tick"]
        self.objects_growth_per_tick = history["objects_growth_per_tick"]
        self.largest_growth_per_tick = history["largest_growth_per_tick"]
        self.stability_index = history["stability_index"]

        ecosystem_phase = self._ecosystem_phase(history, alive)
        self.ecosystem_phase = ecosystem_phase

        if self.prev_ecosystem_phase is None:
            self.prev_ecosystem_phase = ecosystem_phase
        elif ecosystem_phase != self.prev_ecosystem_phase:
            self.add_event(
                tick,
                "phase-change",
                f"{self.prev_ecosystem_phase}->{ecosystem_phase} "
                f"(Δobj={history['history_delta_objects']:+d}, Δmass={history['history_delta_mass']:+d}, "
                f"Δlargest={history['history_delta_largest']:+d}, stability={history['stability_index']:.2f})"
            )
            self.prev_ecosystem_phase = ecosystem_phase

        if alive:
            self.identity_health_sum += health
            self.identity_health_samples += 1
            self.identity_persistence = self.identity_health_sum / max(1, self.identity_health_samples)

        grid_height = len(grid)
        grid_width = len(grid[0]) if grid_height else 0
        field_cells = max(1, grid_width * grid_height)
        if self.first_large_structure_tick is None and largest >= max(self.min_object_cells, int(field_cells * 0.03)):
            self.first_large_structure_tick = tick
            self.add_event(tick, "first-large-structure", f"largest={largest}")
        if self.first_full_field_tick is None and defect_cells >= int(field_cells * 0.65):
            self.first_full_field_tick = tick
            self.add_event(tick, "field-saturation", f"defects={defect_cells}")

        if self.first_large_structure_tick is not None and self.first_full_field_tick is not None and self.first_full_field_tick > self.first_large_structure_tick:
            radius_proxy = math.sqrt(max(1, defect_cells) / math.pi)
            self.expansion_front_speed = radius_proxy / max(1, self.first_full_field_tick - self.first_large_structure_tick)

        if self.collapse_tick is not None or (self.birth_tick is not None and not alive):
            self.post_collapse_structure = defect_cells / max(1, self.peak_cells)
            # Legacy = structure left behind after living-object collapse, discounted if it is just full-field soup.
            soup_penalty = 0.35 if defect_cells > field_cells * 0.70 else 1.0
            self.legacy_score = max(0.0, min(1.0, self.post_collapse_structure * soup_penalty))
            self.information_survival = max(0.0, min(1.0,
                0.45 * self.identity_persistence +
                0.35 * self.legacy_score +
                0.20 * min(1.0, self.longest_age / max(1, tick))
            ))

        self._track_object_events(tick, objects, largest)

        split_rate_1000, merge_rate_1000, birth_rate_1000, death_rate_1000 = self._recent_event_rates(tick)
        growth_phase = self._growth_phase(
            tick=tick,
            alive=alive,
            total_living_mass=total_living_mass,
            ecosystem_health=ecosystem_health,
            mass_delta=mass_delta,
            split_rate=split_rate_1000,
            merge_rate=merge_rate_1000,
        )

        evo = self._evolution_pressure(
            alive=alive,
            ecosystem_health=ecosystem_health,
            fragmentation_index=fragmentation_index,
            dominance_ratio=colony_dist["dominance_ratio"],
            history=history,
            demo=demo,
            split_rate_1000=split_rate_1000,
            merge_rate_1000=merge_rate_1000,
        )
        evo_tl = self._update_evo_timeline(tick, evo)
        self._write_pressure_timeline_row(
            tick=tick,
            evo=evo,
            evo_tl=evo_tl,
            colony_dist=colony_dist,
            dynasty=dynasty,
            demo=demo,
            ecosystem_phase=growth_phase,
            objects=objects,
            total_living_mass=total_living_mass,
            largest=largest,
        )
        self._update_chronicle_signals(
            tick=tick,
            growth_phase=growth_phase,
            evo=evo,
            demo=demo,
            lineage=lineage,
            dynasty=dynasty,
            objects=objects,
            total_living_mass=total_living_mass,
            largest=largest,
        )

        civ = self._update_civilization_layer(
            tick=tick,
            component_records=component_records,
            sizes=sizes,
            total_living_mass=total_living_mass,
            largest=largest,
            colony_dist=colony_dist,
            history=history,
            lineage=lineage,
            dynasty=dynasty,
            demo=demo,
            evo=evo,
            growth_phase=growth_phase,
            ecosystem_health=ecosystem_health,
            fragmentation_index=fragmentation_index,
        )
        know = self._update_knowledge_layer(
            tick=tick,
            civ=civ,
            lineage=lineage,
            dynasty=dynasty,
            demo=demo,
            evo=evo,
            history=history,
            growth_phase=growth_phase,
            ecosystem_health=ecosystem_health,
            fragmentation_index=fragmentation_index,
        )
        fb = self._update_feedback_layer(
            tick=tick,
            know=know,
            civ=civ,
            evo=evo,
            demo=demo,
            history=history,
            ecosystem_health=ecosystem_health,
            fragmentation_index=fragmentation_index,
        )
        emg = self._update_emergence_evidence_layer(
            tick=tick,
            alive=alive,
            lineage=lineage,
            dynasty=dynasty,
            demo=demo,
            evo=evo,
            civ=civ,
            know=know,
            fb=fb,
            history=history,
            ecosystem_health=ecosystem_health,
            objects=objects,
            total_living_mass=total_living_mass,
            largest=largest,
            fragmentation_index=fragmentation_index,
        )
        val = self._update_validation_calibration_layer(
            tick=tick, emg=emg, lineage=lineage, dynasty=dynasty, demo=demo,
            evo=evo, civ=civ, know=know, fb=fb, history=history, alive=alive,
            objects=objects, total_living_mass=total_living_mass,
            fragmentation_index=fragmentation_index,
        )
        life_ev = self._update_life_evidence_model(
            tick=tick,
            alive=alive,
            changed=changed,
            field_cells=field_cells,
            defect_cells=defect_cells,
            objects=objects,
            total_living_mass=total_living_mass,
            largest=largest,
            morphology=morphology,
            lineage=lineage,
            dynasty=dynasty,
            demo=demo,
            evo=evo,
            know=know,
            fb=fb,
            emg=emg,
            val=val,
            history=history,
        )

        if (
            not alive
            and self.birth_tick is not None
            and self.collapse_tick is None
            and self.last_alive_tick is not None
            and tick - self.last_alive_tick >= self.collapse_grace
        ):
            self.collapse_tick = self.last_alive_tick
            self.add_event(tick, "collapse", f"last_alive={self.last_alive_tick}, lifetime={self.longest_age}")
            self.add_event(tick, "legacy-check", f"post_collapse_structure={self.post_collapse_structure:.3f}, legacy={self.legacy_score:.3f}")

        # Stage 2B.1 shadow integration: translate live detector outputs into
        # explicit lifecycle fields.  The ObserverState adapter and Stage 2B
        # publisher handle typing, deduplication, CSV, and SQLite publication.
        # No legacy field, event, threshold, or control-flow decision changes.
        ontology_lifecycle_fields = (
            self._ontology_lifecycle_signal_bridge.observe(
                tick=tick,
                defect_cells=defect_cells,
                alive=alive,
                birth_tick=self.birth_tick,
                collapse_tick=self.collapse_tick,
                ecosystem_collapsed=self.ecosystem_collapsed,
                ecosystem_collapse_tick=self.ecosystem_collapse_tick,
                objects=objects,
                total_living_mass=total_living_mass,
                largest=largest,
                evolution_pressure=evo.get("evo_pressure"),
                extinction_risk=evo.get("evo_extinction_risk"),
                life_evidence_verdict=life_ev.get("life_evidence_verdict"),
                life_evidence_gate_passed=bool(
                    life_ev.get("life_evidence_gate_passed", False)
                ),
                life_evidence_confidence=life_ev.get(
                    "life_evidence_confidence"
                ),
            )
        )

        self.current = {
            # Stage 2C.1: keep the canonical snapshot aligned with the
            # observation that produced these metrics.  Previously the
            # sample row carried ``tick`` but ObserverState rebuilt from
            # ``self.current`` silently fell back to tick 0.
            "tick": tick,
            "objects": objects,
            "defect_cells": defect_cells,
            "largest": largest,
            "total_living_mass": total_living_mass,
            "top10_mass": top10_mass,
            "mean_object_size": mean_object_size,
            "ecosystem_health": ecosystem_health,
            "mass_delta": mass_delta,
            "defect_delta": defect_delta,
            "object_delta": object_delta,
            "fragmentation_index": fragmentation_index,
            "split_rate_1000": split_rate_1000,
            "merge_rate_1000": merge_rate_1000,
            "birth_rate_1000": birth_rate_1000,
            "death_rate_1000": death_rate_1000,
            "growth_phase": growth_phase,
            "large_colonies": colony_dist["large_colonies"],
            "medium_colonies": colony_dist["medium_colonies"],
            "small_colonies": colony_dist["small_colonies"],
            "top3_mass": colony_dist["top3_mass"],
            "top5_mass": colony_dist["top5_mass"],
            "dominance_ratio": colony_dist["dominance_ratio"],
            "top_sizes": colony_dist["top_sizes"],
            "history_delta_objects": history["history_delta_objects"],
            "history_delta_mass": history["history_delta_mass"],
            "history_delta_largest": history["history_delta_largest"],
            "mass_growth_per_tick": history["mass_growth_per_tick"],
            "objects_growth_per_tick": history["objects_growth_per_tick"],
            "largest_growth_per_tick": history["largest_growth_per_tick"],
            "stability_index": history["stability_index"],
            "history_window": history["history_window"],
            "ecosystem_phase": ecosystem_phase,
            "story_era": self.story_era or "",
            "story_era_age": self._era_age(tick),
            "story_era_line": self.story_era_line,
            "story_era_count": self.story_era_count,
            "active_families": lineage["active_families"],
            "active_colonies_tracked": lineage["active_colonies_tracked"],
            "new_colonies_this_tick": lineage["new_colonies_this_tick"],
            "extinct_colonies_total": lineage["extinct_colonies_total"],
            "extinct_families_total": lineage["extinct_families_total"],
            "largest_family_size": lineage["largest_family_size"],
            "deepest_generation": lineage["deepest_generation"],
            "oldest_lineage_age": lineage["oldest_lineage_age"],
            "lineage_summary": lineage["lineage_summary"],
            "dynasty_leader_id": dynasty["dynasty_leader_id"],
            "dynasty_line": dynasty["dynasty_line"],
            "dynasty_age": dynasty["dynasty_age"],
            "dynasty_born": dynasty["dynasty_born"],
            "dynasty_living": dynasty["dynasty_living"],
            "dynasty_dead": dynasty["dynasty_dead"],
            "dynasty_peak_living": dynasty["dynasty_peak_living"],
            "dynasty_dominance": dynasty["dynasty_dominance"],
            "dynasty_survival": dynasty["dynasty_survival"],
            "dynasty_turnover": dynasty["dynasty_turnover"],
            "dynasty_birth_rate": dynasty["dynasty_birth_rate"],
            "dynasty_death_rate": dynasty["dynasty_death_rate"],
            "dynasty_max_generation": dynasty["dynasty_max_generation"],
            "dynasty_largest_colony": dynasty["dynasty_largest_colony"],
            "dynasty_mass": dynasty["dynasty_mass"],
            "demo_born_total": demo["demo_born_total"],
            "demo_dead_total": demo["demo_dead_total"],
            "demo_alive_tracked": demo["demo_alive_tracked"],
            "demo_mean_life": demo["demo_mean_life"],
            "demo_max_life": demo["demo_max_life"],
            "demo_birth_rate_1000": demo["demo_birth_rate_1000"],
            "demo_death_rate_1000": demo["demo_death_rate_1000"],
            "demo_turnover_1000": demo["demo_turnover_1000"],
            "demo_replacement": demo["demo_replacement"],
            "demo_survival_ratio": demo["demo_survival_ratio"],
            "demography_line": demo["demography_line"],
            "evo_stress": evo["evo_stress"],
            "evo_adapt": evo["evo_adapt"],
            "evo_pressure": evo["evo_pressure"],
            "evo_recovery": evo["evo_recovery"],
            "evo_extinction_risk": evo["evo_extinction_risk"],
            "evo_phase": evo["evo_phase"],
            "evolution_line": evo["evolution_line"],
            "evo_src_frag_pct": evo["evo_src_frag_pct"],
            "evo_src_death_pct": evo["evo_src_death_pct"],
            "evo_src_loss_pct": evo["evo_src_loss_pct"],
            "evo_src_inst_pct": evo["evo_src_inst_pct"],
            "evo_src_dom_pct": evo["evo_src_dom_pct"],
            "evo_cause": evo["evo_cause"],
            "evo_source_line": evo["evo_source_line"],
            "evo_timeline_line": evo_tl["evo_timeline_line"],
            "evo_stress_trend": evo_tl["evo_stress_trend"],
            "evo_adapt_trend": evo_tl["evo_adapt_trend"],
            "evo_pressure_trend": evo_tl["evo_pressure_trend"],
            "evo_risk_trend": evo_tl["evo_risk_trend"],
            "evo_timeline_len": evo_tl["evo_timeline_len"],
            "chronicle_last": self.last_chronicle_event_line,
            "chronicle_last_severity": self.last_chronicle_severity,
            "history_book_len": len(self.history_book),
            "civ_stage": civ["civ_stage"],
            "civ_score": civ["civ_score"],
            "civ_age": civ["civ_age"],
            "civ_cities": civ["civ_cities"],
            "civ_capital_size": civ["civ_capital_size"],
            "civ_urban_mass": civ["civ_urban_mass"],
            "civ_urbanization": civ["civ_urbanization"],
            "civ_trade_index": civ["civ_trade_index"],
            "civ_conflict_index": civ["civ_conflict_index"],
            "civ_cohesion": civ["civ_cohesion"],
            "civ_specialization": civ["civ_specialization"],
            "civ_tech_index": civ["civ_tech_index"],
            "civ_culture_index": civ["civ_culture_index"],
            "civ_collapse_risk": civ["civ_collapse_risk"],
            "civ_line": civ["civ_line"],
            "civ_peak_score": civ["civ_peak_score"],
            "civ_peak_tick": civ["civ_peak_tick"],
            "civ_count": civ["civ_count"],
            "knowledge_score": know["knowledge_score"],
            "knowledge_peak_score": know["knowledge_peak_score"],
            "knowledge_age": know["knowledge_age"],
            "knowledge_families": know["knowledge_families"],
            "knowledge_dominant_family": know["knowledge_dominant_family"],
            "knowledge_dominant_axis": know["knowledge_dominant_axis"],
            "knowledge_exploration": know["knowledge_exploration"],
            "knowledge_cooperation": know["knowledge_cooperation"],
            "knowledge_aggression": know["knowledge_aggression"],
            "knowledge_efficiency": know["knowledge_efficiency"],
            "knowledge_adaptation": know["knowledge_adaptation"],
            "knowledge_memory": know["knowledge_memory"],
            "knowledge_memory_peak": know["knowledge_memory_peak"],
            "knowledge_memory_peak_tick": know["knowledge_memory_peak_tick"],
            "knowledge_transfer": know["knowledge_transfer"],
            "knowledge_loss": know["knowledge_loss"],
            "knowledge_discoveries": know["knowledge_discoveries"],
            "knowledge_line": know["knowledge_line"],
            "feedback_score": fb["feedback_score"],
            "feedback_peak_score": fb["feedback_peak_score"],
            "feedback_regime": fb["feedback_regime"],
            "feedback_survival_bonus": fb["feedback_survival_bonus"],
            "feedback_pressure_buffer": fb["feedback_pressure_buffer"],
            "feedback_effective_pressure": fb["feedback_effective_pressure"],
            "feedback_effective_risk": fb["feedback_effective_risk"],
            "feedback_self_direction": fb["feedback_self_direction"],
            "feedback_environment_impact": fb["feedback_environment_impact"],
            "feedback_knowledge_impact": fb["feedback_knowledge_impact"],
            "feedback_response_capacity": fb["feedback_response_capacity"],
            "feedback_response_opportunity": fb["feedback_response_opportunity"],
            "feedback_observed_response": fb["feedback_observed_response"],
            "feedback_legacy_score": fb["feedback_legacy_score"],
            "feedback_metric_version": fb["feedback_metric_version"],
            "feedback_metric_independence_status": fb[
                "feedback_metric_independence_status"
            ],
            "feedback_line": fb["feedback_line"],
            "emergence_score": emg["emergence_score"],
            "emergence_peak_score": emg["emergence_peak_score"],
            "emergence_confidence": emg["emergence_confidence"],
            "emergence_evidence_count": emg["emergence_evidence_count"],
            "emergence_positive_evidence": emg["emergence_positive_evidence"],
            "emergence_negative_evidence": emg["emergence_negative_evidence"],
            "emergence_complexity_index": emg["emergence_complexity_index"],
            "emergence_stability_signal": emg["emergence_stability_signal"],
            "emergence_line": emg["emergence_line"],
            "validation_quality": val["validation_quality"],
            "validation_grade": val["validation_grade"],
            "validation_repeatability": val["validation_repeatability"],
            "validation_stability_confidence": val["validation_stability_confidence"],
            "validation_false_positive_risk": val["validation_false_positive_risk"],
            "validation_false_negative_risk": val["validation_false_negative_risk"],
            "validation_noise_sensitivity": val["validation_noise_sensitivity"],
            "validation_warning": val["validation_warning"],
            "validation_explain": val["validation_explain"],
            "validation_line": val["validation_line"],
            **build_morphology_runtime_snapshot(morphology),
            "bbox_min_x": boundary["bbox_min_x"],
            "bbox_max_x": boundary["bbox_max_x"],
            "bbox_min_y": boundary["bbox_min_y"],
            "bbox_max_y": boundary["bbox_max_y"],
            "bbox_width": boundary["bbox_width"],
            "bbox_height": boundary["bbox_height"],
            "top_edge_fill": boundary["top_edge_fill"],
            "right_edge_fill": boundary["right_edge_fill"],
            "bottom_edge_fill": boundary["bottom_edge_fill"],
            "left_edge_fill": boundary["left_edge_fill"],
            "top_edge_run": boundary["top_edge_run"],
            "right_edge_run": boundary["right_edge_run"],
            "bottom_edge_run": boundary["bottom_edge_run"],
            "left_edge_run": boundary["left_edge_run"],
            "alive": alive,
            "age": age,
            "changed": changed,
            "health": health,
            "cx": center[0],
            "cy": center[1],
            "step_drift": self.max_step_drift,
            "total_drift": self.total_drift,
            "identity_persistence": self.identity_persistence,
            "legacy_score": self.legacy_score,
            "information_survival": self.information_survival,
            "post_collapse_structure": self.post_collapse_structure,
            "expansion_front_speed": self.expansion_front_speed,
            **ontology_lifecycle_fields,
            **life_ev,
        }

        # Stage 1C publishes the canonical state and serializes only its compact
        # scalar projection into telemetry. Legacy control flow remains intact.
        self._publish_observer_state()
        observer_state_telemetry = (
            self.observer_state.to_telemetry_dict()
            if self.observer_state is not None
            else {
                "life_state": "unknown",
                "life_score": None,
                "life_confidence": None,
                "life_uncertainty": None,
                "structural_state": "unknown",
                "ecology_state": "unknown",
                "identity_state": "unknown",
                "knowledge_state": "unknown",
            }
        )

        sample = {
            "tick": tick,
            "alive": alive,
            **observer_state_telemetry,
            "objects": objects,
            "largest": largest,
            "total_living_mass": total_living_mass,
            "top10_mass": top10_mass,
            "mean_object_size": round(mean_object_size, 6),
            "ecosystem_health": round(ecosystem_health, 6),
            "mass_delta": mass_delta,
            "defect_delta": defect_delta,
            "object_delta": object_delta,
            "fragmentation_index": round(fragmentation_index, 6),
            "split_rate_1000": round(split_rate_1000, 6),
            "merge_rate_1000": round(merge_rate_1000, 6),
            "birth_rate_1000": round(birth_rate_1000, 6),
            "death_rate_1000": round(death_rate_1000, 6),
            "growth_phase": growth_phase,
            "large_colonies": colony_dist["large_colonies"],
            "medium_colonies": colony_dist["medium_colonies"],
            "small_colonies": colony_dist["small_colonies"],
            "top3_mass": colony_dist["top3_mass"],
            "top5_mass": colony_dist["top5_mass"],
            "dominance_ratio": round(colony_dist["dominance_ratio"], 6),
            "top_sizes": " ".join(str(s) for s in colony_dist["top_sizes"]),
            "history_delta_objects": history["history_delta_objects"],
            "history_delta_mass": history["history_delta_mass"],
            "history_delta_largest": history["history_delta_largest"],
            "mass_growth_per_tick": round(history["mass_growth_per_tick"], 6),
            "objects_growth_per_tick": round(history["objects_growth_per_tick"], 6),
            "largest_growth_per_tick": round(history["largest_growth_per_tick"], 6),
            "stability_index": round(history["stability_index"], 6),
            "history_window": history["history_window"],
            "ecosystem_phase": ecosystem_phase,
            "story_era": self.story_era or "",
            "story_era_age": self._era_age(tick),
            "story_era_line": self.story_era_line,
            "story_era_count": self.story_era_count,
            "active_families": lineage["active_families"],
            "active_colonies_tracked": lineage["active_colonies_tracked"],
            "new_colonies_this_tick": lineage["new_colonies_this_tick"],
            "extinct_colonies_total": lineage["extinct_colonies_total"],
            "extinct_families_total": lineage["extinct_families_total"],
            "largest_family_size": lineage["largest_family_size"],
            "deepest_generation": lineage["deepest_generation"],
            "oldest_lineage_age": lineage["oldest_lineage_age"],
            "lineage_summary": lineage["lineage_summary"],
            "dynasty_leader_id": dynasty["dynasty_leader_id"],
            "dynasty_line": dynasty["dynasty_line"],
            "dynasty_age": dynasty["dynasty_age"],
            "dynasty_born": dynasty["dynasty_born"],
            "dynasty_living": dynasty["dynasty_living"],
            "dynasty_dead": dynasty["dynasty_dead"],
            "dynasty_peak_living": dynasty["dynasty_peak_living"],
            "dynasty_dominance": round(dynasty["dynasty_dominance"], 6),
            "dynasty_survival": round(dynasty["dynasty_survival"], 6),
            "dynasty_turnover": round(dynasty["dynasty_turnover"], 6),
            "dynasty_birth_rate": round(dynasty["dynasty_birth_rate"], 6),
            "dynasty_death_rate": round(dynasty["dynasty_death_rate"], 6),
            "dynasty_max_generation": dynasty["dynasty_max_generation"],
            "dynasty_largest_colony": dynasty["dynasty_largest_colony"],
            "dynasty_mass": dynasty["dynasty_mass"],
            "demo_born_total": demo["demo_born_total"],
            "demo_dead_total": demo["demo_dead_total"],
            "demo_alive_tracked": demo["demo_alive_tracked"],
            "demo_mean_life": round(demo["demo_mean_life"], 6),
            "demo_max_life": demo["demo_max_life"],
            "demo_birth_rate_1000": round(demo["demo_birth_rate_1000"], 6),
            "demo_death_rate_1000": round(demo["demo_death_rate_1000"], 6),
            "demo_turnover_1000": round(demo["demo_turnover_1000"], 6),
            "demo_replacement": round(demo["demo_replacement"], 6),
            "demo_survival_ratio": round(demo["demo_survival_ratio"], 6),
            "demography_line": demo["demography_line"],
            "evo_stress": round(evo["evo_stress"], 6),
            "evo_adapt": round(evo["evo_adapt"], 6),
            "evo_pressure": round(evo["evo_pressure"], 6),
            "evo_recovery": round(evo["evo_recovery"], 6),
            "evo_extinction_risk": round(evo["evo_extinction_risk"], 6),
            "evo_phase": evo["evo_phase"],
            "evolution_line": evo["evolution_line"],
            "evo_src_frag_pct": round(evo["evo_src_frag_pct"], 6),
            "evo_src_death_pct": round(evo["evo_src_death_pct"], 6),
            "evo_src_loss_pct": round(evo["evo_src_loss_pct"], 6),
            "evo_src_inst_pct": round(evo["evo_src_inst_pct"], 6),
            "evo_src_dom_pct": round(evo["evo_src_dom_pct"], 6),
            "evo_cause": evo["evo_cause"],
            "evo_source_line": evo["evo_source_line"],
            "evo_timeline_line": evo_tl["evo_timeline_line"],
            "evo_stress_trend": round(evo_tl["evo_stress_trend"], 6),
            "evo_adapt_trend": round(evo_tl["evo_adapt_trend"], 6),
            "evo_pressure_trend": round(evo_tl["evo_pressure_trend"], 6),
            "evo_risk_trend": round(evo_tl["evo_risk_trend"], 6),
            "evo_timeline_len": evo_tl["evo_timeline_len"],
            "civ_stage": civ["civ_stage"],
            "civ_score": round(civ["civ_score"], 6),
            "civ_age": civ["civ_age"],
            "civ_cities": civ["civ_cities"],
            "civ_capital_size": civ["civ_capital_size"],
            "civ_urban_mass": civ["civ_urban_mass"],
            "civ_urbanization": round(civ["civ_urbanization"], 6),
            "civ_trade_index": round(civ["civ_trade_index"], 6),
            "civ_conflict_index": round(civ["civ_conflict_index"], 6),
            "civ_cohesion": round(civ["civ_cohesion"], 6),
            "civ_specialization": round(civ["civ_specialization"], 6),
            "civ_tech_index": round(civ["civ_tech_index"], 6),
            "civ_culture_index": round(civ["civ_culture_index"], 6),
            "civ_collapse_risk": round(civ["civ_collapse_risk"], 6),
            "civ_line": civ["civ_line"],
            "civ_peak_score": round(civ["civ_peak_score"], 6),
            "civ_peak_tick": civ["civ_peak_tick"],
            "civ_count": civ["civ_count"],
            "knowledge_score": round(know["knowledge_score"], 6),
            "knowledge_peak_score": round(know["knowledge_peak_score"], 6),
            "knowledge_age": know["knowledge_age"],
            "knowledge_families": know["knowledge_families"],
            "knowledge_dominant_family": know["knowledge_dominant_family"],
            "knowledge_dominant_axis": know["knowledge_dominant_axis"],
            "knowledge_exploration": round(know["knowledge_exploration"], 6),
            "knowledge_cooperation": round(know["knowledge_cooperation"], 6),
            "knowledge_aggression": round(know["knowledge_aggression"], 6),
            "knowledge_efficiency": round(know["knowledge_efficiency"], 6),
            "knowledge_adaptation": round(know["knowledge_adaptation"], 6),
            "knowledge_memory": round(know["knowledge_memory"], 6),
            "knowledge_memory_peak": round(know["knowledge_memory_peak"], 6),
            "knowledge_memory_peak_tick": know["knowledge_memory_peak_tick"],
            "knowledge_transfer": round(know["knowledge_transfer"], 6),
            "knowledge_loss": round(know["knowledge_loss"], 6),
            "knowledge_discoveries": know["knowledge_discoveries"],
            "knowledge_line": know["knowledge_line"],
            "feedback_score": round(fb["feedback_score"], 6),
            "feedback_peak_score": round(fb["feedback_peak_score"], 6),
            "feedback_regime": fb["feedback_regime"],
            "feedback_survival_bonus": round(fb["feedback_survival_bonus"], 6),
            "feedback_pressure_buffer": round(fb["feedback_pressure_buffer"], 6),
            "feedback_effective_pressure": round(fb["feedback_effective_pressure"], 6),
            "feedback_effective_risk": round(fb["feedback_effective_risk"], 6),
            "feedback_self_direction": round(fb["feedback_self_direction"], 6),
            "feedback_environment_impact": round(fb["feedback_environment_impact"], 6),
            "feedback_knowledge_impact": round(fb["feedback_knowledge_impact"], 6),
            "feedback_response_capacity": round(fb["feedback_response_capacity"], 6),
            "feedback_response_opportunity": round(fb["feedback_response_opportunity"], 6),
            "feedback_observed_response": round(fb["feedback_observed_response"], 6),
            "feedback_legacy_score": round(fb["feedback_legacy_score"], 6),
            "feedback_metric_version": fb["feedback_metric_version"],
            "feedback_metric_independence_status": fb[
                "feedback_metric_independence_status"
            ],
            "feedback_line": fb["feedback_line"],
            "emergence_score": round(emg["emergence_score"], 6),
            "emergence_peak_score": round(emg["emergence_peak_score"], 6),
            "emergence_confidence": emg["emergence_confidence"],
            "emergence_evidence_count": emg["emergence_evidence_count"],
            "emergence_positive_evidence": emg["emergence_positive_evidence"],
            "emergence_negative_evidence": emg["emergence_negative_evidence"],
            "emergence_complexity_index": round(emg["emergence_complexity_index"], 6),
            "emergence_stability_signal": round(emg["emergence_stability_signal"], 6),
            "emergence_line": emg["emergence_line"],
            "validation_quality": round(val["validation_quality"], 6),
            "validation_grade": val["validation_grade"],
            "validation_repeatability": round(val["validation_repeatability"], 6),
            "validation_stability_confidence": round(val["validation_stability_confidence"], 6),
            "validation_false_positive_risk": round(val["validation_false_positive_risk"], 6),
            "validation_false_negative_risk": round(val["validation_false_negative_risk"], 6),
            "validation_noise_sensitivity": round(val["validation_noise_sensitivity"], 6),
            "validation_warning": val["validation_warning"],
            "validation_explain": val["validation_explain"],
            "validation_line": val["validation_line"],
            "morphology_compactness": round(morphology["morphology_compactness"], 6),
            "morphology_aspect": round(morphology["morphology_aspect"], 6),
            "morphology_edge_complexity": round(morphology["morphology_edge_complexity"], 6),
            "morphology_bbox_fill": round(morphology["morphology_bbox_fill"], 6),
            "morphology_symmetry": round(morphology["morphology_symmetry"], 6),
            "morphology_branching": round(morphology["morphology_branching"], 6),
            "morphology_filament_score": round(morphology["morphology_filament_score"], 6),
            "morphology_lattice_score": round(morphology["morphology_lattice_score"], 6),
            "morphology_change_rate": round(morphology["morphology_change_rate"], 6),
            "morphology_stability_ticks": morphology["morphology_stability_ticks"],
            "morphology_peak_complexity": round(morphology["morphology_peak_complexity"], 6),
            "morphology_class": morphology["morphology_class"],
            "morphology_line": morphology["morphology_line"],
            "bbox_min_x": boundary["bbox_min_x"],
            "bbox_max_x": boundary["bbox_max_x"],
            "bbox_min_y": boundary["bbox_min_y"],
            "bbox_max_y": boundary["bbox_max_y"],
            "bbox_width": boundary["bbox_width"],
            "bbox_height": boundary["bbox_height"],
            "top_edge_fill": round(boundary["top_edge_fill"], 6),
            "right_edge_fill": round(boundary["right_edge_fill"], 6),
            "bottom_edge_fill": round(boundary["bottom_edge_fill"], 6),
            "left_edge_fill": round(boundary["left_edge_fill"], 6),
            "top_edge_run": round(boundary["top_edge_run"], 6),
            "right_edge_run": round(boundary["right_edge_run"], 6),
            "bottom_edge_run": round(boundary["bottom_edge_run"], 6),
            "left_edge_run": round(boundary["left_edge_run"], 6),
            "defect_cells": defect_cells,
            "changed": changed,
            "age": age,
            "health": round(health, 6),
            "cx": None if center[0] is None else round(center[0], 4),
            "cy": None if center[1] is None else round(center[1], 4),
            "step_drift": round(self.max_step_drift, 6),
            "total_drift": round(self.total_drift, 6),
            "identity_persistence": round(self.identity_persistence, 6),
            "legacy_score": round(self.legacy_score, 6),
            "information_survival": round(self.information_survival, 6),
            "post_collapse_structure": round(self.post_collapse_structure, 6),
            "expansion_front_speed": round(self.expansion_front_speed, 6),
        }
        self.samples.append(sample)

        if self._sample_writer:
            self._sample_writer.writerow(sample)
            self._samples_since_flush += 1
            if self._samples_since_flush >= self.live_flush_every:
                self._sample_file.flush()
                self._samples_since_flush = 0

        return self.current

    def life_stage(self):
        c = self.current
        if self.collapse_tick is not None:
            return "dead"
        if not c["alive"]:
            return "no-object"
        h = c["health"]
        if c["age"] < 200:
            return "juvenile"
        if h >= 0.75:
            return "adult"
        if h >= 0.35:
            return "old"
        return "critical"

    def configure_evidence_framework(
        self,
        *,
        rec,
        results_dir: Path,
        run_id: str,
        observer_version: str = "5.0",
        enabled: bool = True,
        enable_timeline: bool = True,
    ):
        """Attach one run-local Evidence Framework session."""
        self._evidence_enabled = bool(enabled)
        if not self._evidence_enabled:
            self._evidence_session = None
            return

        self._evidence_session = LiveObserverEvidenceSession(
            world_id=f"rule_{int(rec['rule_id']):05d}",
            run_id=str(run_id),
            observer_version=str(observer_version),
            output_root=Path(results_dir) / "observation_logs",
            enable_timeline=enable_timeline,
        )

    def write_evidence_outputs(self, rec, final_tick, reason="checkpoint"):
        """Run, export, and timeline the Evidence Framework checkpoint."""
        if not self._evidence_enabled or self._evidence_session is None:
            return None
        if self._evidence_last_tick == int(final_tick):
            return self._evidence_last_result

        try:
            result = self._evidence_session.checkpoint(
                current=self.current,
                tick=int(final_tick),
                rule_record=rec,
                reason=str(reason),
            )
        except Exception as exc:
            print(f"[evidence] checkpoint failed at tick {final_tick}: {exc!r}")
            return None

        self._evidence_last_tick = int(final_tick)
        self._evidence_last_result = result
        report = result.pipeline_result.report
        leader = report.leading_hypothesis_id or "none"
        print(
            f"[evidence] saved tick={final_tick} "
            f"hypotheses={len(report.hypotheses)} "
            f"unknowns={len(report.unknowns)} "
            f"conflicts={len(report.conflicts)} "
            f"leader={leader}"
        )
        print(f"[evidence] directory: {result.export_result.export_dir}")
        if result.timeline_path:
            print(f"[evidence] timeline: {result.timeline_path}")
        return result

    def status_text(self):
        c = self.current
        if self.collapse_tick is not None:
            return (
                f"DEAD at tick={self.collapse_tick} | lifetime={self.longest_age} | "
                f"peak_largest={self.peak_largest} | peak_defects={self.peak_cells} | "
                f"legacy={self.legacy_score:.2f} info={self.information_survival:.2f}"
            )
        return (
            f"{self.life_stage().upper()} / {c.get('growth_phase', 'seed')} | "
            f"evidence={c.get('life_evidence_verdict', 'INSUFFICIENT_EVIDENCE')} "
            f"({c.get('life_evidence_score', 0.0):.2f}/{c.get('life_evidence_confidence', 0.0):.2f}) | "
            f"objects={c['objects']} | largest={c['largest']} | "
            f"mass={c.get('total_living_mass', 0)} Δm={c.get('mass_delta', 0)} top10={c.get('top10_mass', 0)} | "
            f"health={c['health']:.2f} eco={c.get('ecosystem_health', 0.0):.2f} frag={c.get('fragmentation_index', 0.0):.3f} dom={c.get('dominance_ratio', 0.0):.2f} | "
            f"L/M/S={c.get('large_colonies', 0)}/{c.get('medium_colonies', 0)}/{c.get('small_colonies', 0)} top={c.get('top_sizes', [])[:5]} | "
            f"split={c.get('split_rate_1000', 0.0):.1f}/k merge={c.get('merge_rate_1000', 0.0):.1f}/k | "
            f"defects={c['defect_cells']} Δd={c.get('defect_delta', 0)} | changed={c['changed']} | "
            f"age={c['age']} | drift={c['total_drift']:.1f} | "
            f"id={c['identity_persistence']:.2f} legacy={c['legacy_score']:.2f} info={c['information_survival']:.2f} | "
            f"CIV={c.get('civ_stage', 'NONE')} score={c.get('civ_score', 0.0):.2f} cities={c.get('civ_cities', 0)} "
            f"tech={c.get('civ_tech_index', 0.0):.2f} trade={c.get('civ_trade_index', 0.0):.2f} risk={c.get('civ_collapse_risk', 0.0):.2f} | "
            f"KNOW={c.get('knowledge_score', 0.0):.2f} axis={c.get('knowledge_dominant_axis', 'none')} disc={c.get('knowledge_discoveries', '')}"
        )

    def event_text(self):
        return f"event: {self.last_event}"

    def passport(self, rec, final_tick):
        m = rec.get("metrics") or {}
        (
            observer_state,
            lifecycle_summary,
            lifecycle_write_integrity,
        ) = self._passport_observer_state(final_tick)
        return {
            "created": datetime.now().isoformat(timespec="seconds"),
            "observer_state": observer_state,
            "lifecycle_summary": lifecycle_summary,
            "lifecycle_write_integrity": lifecycle_write_integrity,
            "rule_id": rec.get("rule_id"),
            "score": rec.get("score"),
            "source": rec.get("source"),
            "generation": rec.get("generation"),
            "metrics": {
                "memory_trace_score": m.get("memory_trace_score"),
                "persistent_tracks": m.get("persistent_tracks"),
                "ms_flow": m.get("ms_flow"),
                "ms_rotation_flow": m.get("ms_rotation_flow"),
                "crystal_order": m.get("crystal_order"),
                "quasi_particle_score": m.get("quasi_particle_score"),
                "information_survival": m.get("information_survival"),
                "identity_persistence": m.get("identity_persistence"),
                "legacy_score": m.get("legacy_score"),
                "post_collapse_structure": m.get("post_collapse_structure"),
                "expansion_front_speed": m.get("expansion_front_speed"),
                "collapse_stage": m.get("collapse_stage"),
            },
            "life": {
                "final_tick_observed": final_tick,
                "birth_tick": self.birth_tick,
                "last_alive_tick": self.last_alive_tick,
                "collapse_tick": self.collapse_tick,
                "longest_observed_age": self.longest_age,
                "peak_tick": self.peak_tick,
                "peak_objects": self.peak_objects,
                "peak_largest_object_cells": self.peak_largest,
                "peak_total_living_mass": self.peak_total_living_mass,
                "peak_top10_mass": self.peak_top10_mass,
                "final_total_living_mass": self.current.get("total_living_mass", 0),
                "final_top10_mass": self.current.get("top10_mass", 0),
                "mean_object_size_final": round(self.current.get("mean_object_size", 0.0), 6),
                "ecosystem_health_final": round(self.current.get("ecosystem_health", 0.0), 6),
                "mass_delta_final": self.current.get("mass_delta", 0),
                "defect_delta_final": self.current.get("defect_delta", 0),
                "object_delta_final": self.current.get("object_delta", 0),
                "fragmentation_index_final": round(self.current.get("fragmentation_index", 0.0), 6),
                "split_rate_1000_final": round(self.current.get("split_rate_1000", 0.0), 6),
                "merge_rate_1000_final": round(self.current.get("merge_rate_1000", 0.0), 6),
                "birth_rate_1000_final": round(self.current.get("birth_rate_1000", 0.0), 6),
                "death_rate_1000_final": round(self.current.get("death_rate_1000", 0.0), 6),
                "growth_phase_final": self.current.get("growth_phase", "seed"),
                "large_colonies_final": self.current.get("large_colonies", 0),
                "medium_colonies_final": self.current.get("medium_colonies", 0),
                "small_colonies_final": self.current.get("small_colonies", 0),
                "top3_mass_final": self.current.get("top3_mass", 0),
                "top5_mass_final": self.current.get("top5_mass", 0),
                "dominance_ratio_final": round(self.current.get("dominance_ratio", 0.0), 6),
                "top_sizes_final": self.current.get("top_sizes", []),
                "history_delta_objects_final": self.current.get("history_delta_objects", 0),
                "history_delta_mass_final": self.current.get("history_delta_mass", 0),
                "history_delta_largest_final": self.current.get("history_delta_largest", 0),
                "mass_growth_per_tick_final": round(self.current.get("mass_growth_per_tick", 0.0), 6),
                "objects_growth_per_tick_final": round(self.current.get("objects_growth_per_tick", 0.0), 6),
                "largest_growth_per_tick_final": round(self.current.get("largest_growth_per_tick", 0.0), 6),
                "stability_index_final": round(self.current.get("stability_index", 0.0), 6),
                "history_window_final": self.current.get("history_window", 0),
                "ecosystem_phase_final": self.current.get("ecosystem_phase", "WARMUP"),
                "active_families_final": self.current.get("active_families", 0),
                "active_colonies_tracked_final": self.current.get("active_colonies_tracked", 0),
                "new_colonies_this_tick_final": self.current.get("new_colonies_this_tick", 0),
                "extinct_colonies_total_final": self.current.get("extinct_colonies_total", 0),
                "extinct_families_total_final": self.current.get("extinct_families_total", 0),
                "largest_family_size_final": self.current.get("largest_family_size", 0),
                "deepest_generation_final": self.current.get("deepest_generation", 0),
                "oldest_lineage_age_final": self.current.get("oldest_lineage_age", 0),
                "lineage_summary_final": self.current.get("lineage_summary", ""),
                "dynasty_leader_id_final": self.current.get("dynasty_leader_id", None),
                "dynasty_line_final": self.current.get("dynasty_line", ""),
                "dynasty_age_final": self.current.get("dynasty_age", 0),
                "dynasty_born_final": self.current.get("dynasty_born", 0),
                "dynasty_living_final": self.current.get("dynasty_living", 0),
                "dynasty_dead_final": self.current.get("dynasty_dead", 0),
                "dynasty_peak_living_final": self.current.get("dynasty_peak_living", 0),
                "dynasty_dominance_final": round(self.current.get("dynasty_dominance", 0.0), 6),
                "dynasty_survival_final": round(self.current.get("dynasty_survival", 0.0), 6),
                "dynasty_turnover_final": round(self.current.get("dynasty_turnover", 0.0), 6),
                "dynasty_birth_rate_final": round(self.current.get("dynasty_birth_rate", 0.0), 6),
                "dynasty_death_rate_final": round(self.current.get("dynasty_death_rate", 0.0), 6),
                "dynasty_max_generation_final": self.current.get("dynasty_max_generation", 0),
                "dynasty_largest_colony_final": self.current.get("dynasty_largest_colony", 0),
                "dynasty_mass_final": self.current.get("dynasty_mass", 0),
                "demo_born_total_final": self.current.get("demo_born_total", 0),
                "demo_dead_total_final": self.current.get("demo_dead_total", 0),
                "demo_alive_tracked_final": self.current.get("demo_alive_tracked", 0),
                "demo_mean_life_final": round(self.current.get("demo_mean_life", 0.0), 6),
                "demo_max_life_final": self.current.get("demo_max_life", 0),
                "demo_birth_rate_1000_final": round(self.current.get("demo_birth_rate_1000", 0.0), 6),
                "demo_death_rate_1000_final": round(self.current.get("demo_death_rate_1000", 0.0), 6),
                "demo_turnover_1000_final": round(self.current.get("demo_turnover_1000", 0.0), 6),
                "demo_replacement_final": round(self.current.get("demo_replacement", 0.0), 6),
                "demo_survival_ratio_final": round(self.current.get("demo_survival_ratio", 0.0), 6),
                "demography_line_final": self.current.get("demography_line", ""),
                "evolution_line_final": self.current.get("evolution_line", ""),
                "evo_phase_final": self.current.get("evo_phase", ""),
                "evo_stress_final": round(self.current.get("evo_stress", 0.0), 6),
                "evo_adapt_final": round(self.current.get("evo_adapt", 0.0), 6),
                "evo_pressure_final": round(self.current.get("evo_pressure", 0.0), 6),
                "evo_recovery_final": round(self.current.get("evo_recovery", 0.0), 6),
                "evo_extinction_risk_final": round(self.current.get("evo_extinction_risk", 0.0), 6),
                "evo_source_line_final": self.current.get("evo_source_line", ""),
                "evo_cause_final": self.current.get("evo_cause", ""),
                "evo_src_frag_pct_final": round(self.current.get("evo_src_frag_pct", 0.0), 6),
                "evo_src_death_pct_final": round(self.current.get("evo_src_death_pct", 0.0), 6),
                "evo_src_loss_pct_final": round(self.current.get("evo_src_loss_pct", 0.0), 6),
                "evo_src_inst_pct_final": round(self.current.get("evo_src_inst_pct", 0.0), 6),
                "evo_src_dom_pct_final": round(self.current.get("evo_src_dom_pct", 0.0), 6),
                "evo_timeline_line_final": self.current.get("evo_timeline_line", ""),
                "evo_stress_trend_final": round(self.current.get("evo_stress_trend", 0.0), 6),
                "evo_adapt_trend_final": round(self.current.get("evo_adapt_trend", 0.0), 6),
                "evo_pressure_trend_final": round(self.current.get("evo_pressure_trend", 0.0), 6),
                "evo_risk_trend_final": round(self.current.get("evo_risk_trend", 0.0), 6),
                "evo_timeline_len_final": self.current.get("evo_timeline_len", 0),
                "chronicle_counts": self.chronicle_counts,
                "chronicle_severity_counts": self.chronicle_severity_counts,
                "chronicle_last_event": self.last_chronicle_event_line,
                "history_book_events": self.history_book[-80:],
                "story_era_final": self.story_era,
                "story_era_age_final": max(0, final_tick - self.story_era_start_tick) if self.story_era_start_tick is not None else 0,
                "story_era_count_final": self.story_era_count,
                "civilization_stage_final": self.current.get("civ_stage", "NONE"),
                "civilization_score_final": round(self.current.get("civ_score", 0.0), 6),
                "civilization_age_final": self.current.get("civ_age", 0),
                "civilization_cities_final": self.current.get("civ_cities", 0),
                "civilization_capital_size_final": self.current.get("civ_capital_size", 0),
                "civilization_urban_mass_final": self.current.get("civ_urban_mass", 0),
                "civilization_urbanization_final": round(self.current.get("civ_urbanization", 0.0), 6),
                "civilization_trade_index_final": round(self.current.get("civ_trade_index", 0.0), 6),
                "civilization_conflict_index_final": round(self.current.get("civ_conflict_index", 0.0), 6),
                "civilization_cohesion_final": round(self.current.get("civ_cohesion", 0.0), 6),
                "civilization_specialization_final": round(self.current.get("civ_specialization", 0.0), 6),
                "civilization_tech_index_final": round(self.current.get("civ_tech_index", 0.0), 6),
                "civilization_culture_index_final": round(self.current.get("civ_culture_index", 0.0), 6),
                "civilization_collapse_risk_final": round(self.current.get("civ_collapse_risk", 0.0), 6),
                "civilization_line_final": self.current.get("civ_line", ""),
                "civilization_peak_score": round(self.civilization_peak_score, 6),
                "civilization_peak_tick": self.civilization_peak_tick,
                "civilization_count": self.civilization_count,
                "civilization_event_counts": self.civilization_event_counts,
                "civilization_recent_history": list(self.civilization_history)[-80:],
                "knowledge_score_final": round(self.current.get("knowledge_score", 0.0), 6),
                "knowledge_peak_score": round(self.knowledge_peak_score, 6),
                "knowledge_peak_tick": self.knowledge_peak_tick,
                "knowledge_age_final": self.current.get("knowledge_age", 0),
                "knowledge_families_final": self.current.get("knowledge_families", 0),
                "knowledge_dominant_family_final": self.current.get("knowledge_dominant_family", None),
                "knowledge_dominant_axis_final": self.current.get("knowledge_dominant_axis", "none"),
                "knowledge_exploration_final": round(self.current.get("knowledge_exploration", 0.0), 6),
                "knowledge_cooperation_final": round(self.current.get("knowledge_cooperation", 0.0), 6),
                "knowledge_aggression_final": round(self.current.get("knowledge_aggression", 0.0), 6),
                "knowledge_efficiency_final": round(self.current.get("knowledge_efficiency", 0.0), 6),
                "knowledge_adaptation_final": round(self.current.get("knowledge_adaptation", 0.0), 6),
                "knowledge_memory_final": round(self.current.get("knowledge_memory", 0.0), 6),
                "knowledge_memory_peak": round(self.knowledge_memory_peak, 6),
                "knowledge_memory_peak_tick": self.knowledge_memory_peak_tick,
                "knowledge_transfer_final": round(self.current.get("knowledge_transfer", 0.0), 6),
                "knowledge_loss_final": round(self.current.get("knowledge_loss", 0.0), 6),
                "knowledge_discoveries": self.current.get("knowledge_discoveries", ""),
                "knowledge_line_final": self.current.get("knowledge_line", ""),
                "knowledge_event_counts": self.knowledge_event_counts,
                "knowledge_recent_history": list(self.knowledge_history)[-80:],
                "feedback_score_final": round(self.current.get("feedback_score", 0.0), 6),
                "feedback_peak_score": round(self.feedback_peak_score, 6),
                "feedback_peak_tick": self.feedback_peak_tick,
                "feedback_regime_final": self.current.get("feedback_regime", "NONE"),
                "feedback_survival_bonus_final": round(self.current.get("feedback_survival_bonus", 0.0), 6),
                "feedback_pressure_buffer_final": round(self.current.get("feedback_pressure_buffer", 0.0), 6),
                "feedback_effective_pressure_final": round(self.current.get("feedback_effective_pressure", 0.0), 6),
                "feedback_effective_risk_final": round(self.current.get("feedback_effective_risk", 0.0), 6),
                "feedback_self_direction_final": round(self.current.get("feedback_self_direction", 0.0), 6),
                "feedback_environment_impact_final": round(self.current.get("feedback_environment_impact", 0.0), 6),
                "feedback_knowledge_impact_final": round(self.current.get("feedback_knowledge_impact", 0.0), 6),
                "feedback_response_capacity_final": round(self.current.get("feedback_response_capacity", 0.0), 6),
                "feedback_response_opportunity_final": round(self.current.get("feedback_response_opportunity", 0.0), 6),
                "feedback_observed_response_final": round(self.current.get("feedback_observed_response", 0.0), 6),
                "feedback_legacy_score_final": round(self.current.get("feedback_legacy_score", 0.0), 6),
                "feedback_metric_version": self.current.get("feedback_metric_version", "2.0"),
                "feedback_metric_independence_status": self.current.get(
                    "feedback_metric_independence_status",
                    "STRUCTURALLY_INDEPENDENT_V2",
                ),
                "feedback_line_final": self.current.get("feedback_line", ""),
                "feedback_event_counts": self.feedback_event_counts,
                "feedback_recent_history": list(self.feedback_history)[-80:],
                "emergence_score_final": round(self.current.get("emergence_score", 0.0), 6),
                "emergence_peak_score": round(self.emergence_peak_score, 6),
                "emergence_peak_tick": self.emergence_peak_tick,
                "emergence_confidence_final": self.current.get("emergence_confidence", "NONE"),
                "emergence_evidence_count_final": self.current.get("emergence_evidence_count", 0),
                "emergence_positive_evidence_final": self.current.get("emergence_positive_evidence", ""),
                "emergence_negative_evidence_final": self.current.get("emergence_negative_evidence", ""),
                "emergence_complexity_index_final": round(self.current.get("emergence_complexity_index", 0.0), 6),
                "emergence_stability_signal_final": round(self.current.get("emergence_stability_signal", 0.0), 6),
                "emergence_line_final": self.current.get("emergence_line", ""),
                "emergence_event_counts": self.emergence_event_counts,
                "emergence_recent_history": list(self.emergence_history)[-80:],
                "validation_quality_final": round(self.current.get("validation_quality", 0.0), 6),
                "validation_quality_peak": round(self.validation_quality_peak, 6),
                "validation_grade_final": self.current.get("validation_grade", "NONE"),
                "validation_repeatability_final": round(self.current.get("validation_repeatability", 0.0), 6),
                "validation_stability_confidence_final": round(self.current.get("validation_stability_confidence", 0.0), 6),
                "validation_false_positive_risk_final": round(self.current.get("validation_false_positive_risk", 0.0), 6),
                "validation_false_negative_risk_final": round(self.current.get("validation_false_negative_risk", 0.0), 6),
                "validation_noise_sensitivity_final": round(self.current.get("validation_noise_sensitivity", 0.0), 6),
                "validation_warning_final": self.current.get("validation_warning", ""),
                "validation_explain_final": self.current.get("validation_explain", ""),
                "validation_line_final": self.current.get("validation_line", ""),
                "validation_event_counts": self.validation_event_counts,
                "validation_recent_history": list(self.validation_history)[-80:],
                "life_evidence_version": self.current.get("life_evidence_version", ""),
                "life_evidence_verdict_final": self.current.get("life_evidence_verdict", "INSUFFICIENT_EVIDENCE"),
                "life_evidence_score_final": round(self.current.get("life_evidence_score", 0.0), 6),
                "life_evidence_confidence_final": round(self.current.get("life_evidence_confidence", 0.0), 6),
                "life_evidence_uncertainty_final": round(self.current.get("life_evidence_uncertainty", 1.0), 6),
                "life_evidence_peak": round(self.life_evidence_peak, 6),
                "life_evidence_peak_tick": self.life_evidence_peak_tick,
                "life_evidence_winner_final": self.current.get("life_evidence_winner", ""),
                "life_evidence_runner_up_final": self.current.get("life_evidence_runner_up", ""),
                "life_evidence_margin_final": round(self.current.get("life_evidence_margin", 0.0), 6),
                "life_evidence_gate_passed_final": bool(self.current.get("life_evidence_gate_passed", False)),
                "life_evidence_strong_axes_final": self.current.get("life_evidence_strong_axes", ""),
                "life_evidence_positive_final": self.current.get("life_evidence_positive", ""),
                "life_evidence_alternatives_final": self.current.get("life_evidence_alternatives", ""),
                "life_evidence_warnings_final": self.current.get("life_evidence_warnings", ""),
                "life_evidence_axes_final": self.current.get("life_evidence_axes", {}),
                "life_evidence_hypotheses_final": self.current.get("life_evidence_hypotheses", {}),
                "life_evidence_event_counts": self.life_evidence_event_counts,
                "life_evidence_recent_history": list(self.life_evidence_history)[-80:],
                "peak_defect_cells": self.peak_cells,
                "total_center_drift": round(self.total_drift, 6),
                "max_step_drift": round(self.max_step_drift, 6),
                "final_life_stage": self.life_stage(),
                "identity_persistence_observed": round(self.identity_persistence, 6),
                "legacy_score_observed": round(self.legacy_score, 6),
                "information_survival_observed": round(self.information_survival, 6),
                "post_collapse_structure_observed": round(self.post_collapse_structure, 6),
                "expansion_front_speed_observed": round(self.expansion_front_speed, 6),
                "first_large_structure_tick": self.first_large_structure_tick,
                "field_saturation_tick": self.first_full_field_tick,
            },
            "events": self.events,
        }

    def write_outputs(self, root_dir: Path, rec, final_tick, write_log=True, write_passport=True):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rid = rec["rule_id"]
        out_dir = root_dir / "observation_logs"
        out_dir.mkdir(parents=True, exist_ok=True)

        passport = self.passport(rec, final_tick)

        if write_passport:
            json_path = out_dir / f"rule_{rid:05d}_{stamp}_passport.json"
            json_path.write_text(json.dumps(passport, indent=2, ensure_ascii=False), encoding="utf-8")

            md_path = out_dir / f"rule_{rid:05d}_{stamp}_passport.md"
            md_path.write_text(self.passport_markdown(passport), encoding="utf-8")

            print(f"Passport saved: {json_path}")
            print(f"Passport markdown saved: {md_path}")

        if write_log:
            log_path = out_dir / f"rule_{rid:05d}_{stamp}_log.txt"
            self.write_log(log_path, rec, final_tick)
            print(f"Observation log saved: {log_path}")

        self.write_evidence_outputs(
            rec,
            final_tick,
            reason="observer-output",
        )

    def passport_markdown(self, data):
        life = data["life"]
        metrics = data["metrics"]
        lifecycle = data.get("lifecycle_summary") or {}
        lines = [
            f"# Life Passport: Rule {data['rule_id']:05d}",
            "",
            f"- Score: **{data['score']}**",
            f"- Source: `{data['source']}`",
            f"- Generation: **{data['generation']}**",
            "",
            "## Original Metrics",
            f"- Memory: **{metrics.get('memory_trace_score')}**",
            f"- Tracks: **{metrics.get('persistent_tracks')}**",
            f"- Flow: **{metrics.get('ms_flow')}**",
            f"- Rotation: **{metrics.get('ms_rotation_flow')}**",
            f"- Crystal order: **{metrics.get('crystal_order')}**",
            f"- Quasi-particle score: **{metrics.get('quasi_particle_score')}**",
            "",
            "## Typed Lifecycle Summary (Shadow)",
            f"- Phase: **{lifecycle.get('phase', 'unavailable')}**",
            f"- History status: **{lifecycle.get('history_status', 'unavailable')}**",
            f"- Observed through tick: **{lifecycle.get('observed_through_tick')}**",
            f"- Typed event count: **{lifecycle.get('event_count', 0)}**",
            f"- Event types: **{lifecycle.get('event_types', [])}**",
            f"- First ticks: **{lifecycle.get('first_ticks', {})}**",
            f"- Latest event: **{lifecycle.get('latest_event_type')} @ {lifecycle.get('latest_event_tick')}**",
            "",
            "## Life Summary",
            f"- Birth tick: **{life.get('birth_tick')}**",
            f"- Last alive tick: **{life.get('last_alive_tick')}**",
            f"- Collapse tick: **{life.get('collapse_tick')}**",
            f"- Longest observed age: **{life.get('longest_observed_age')}**",
            f"- Peak tick: **{life.get('peak_tick')}**",
            f"- Peak objects: **{life.get('peak_objects')}**",
            f"- Peak largest object cells: **{life.get('peak_largest_object_cells')}**",
            f"- Peak total living mass: **{life.get('peak_total_living_mass')}**",
            f"- Peak top-10 mass: **{life.get('peak_top10_mass')}**",
            f"- Final total living mass: **{life.get('final_total_living_mass')}**",
            f"- Final top-10 mass: **{life.get('final_top10_mass')}**",
            f"- Mean object size final: **{life.get('mean_object_size_final')}**",
            f"- Ecosystem health final: **{life.get('ecosystem_health_final')}**",
            f"- Growth phase final: **{life.get('growth_phase_final')}**",
            f"- Mass delta final: **{life.get('mass_delta_final')}**",
            f"- Defect delta final: **{life.get('defect_delta_final')}**",
            f"- Object delta final: **{life.get('object_delta_final')}**",
            f"- Fragmentation index final: **{life.get('fragmentation_index_final')}**",
            f"- Split rate / 1000 ticks final: **{life.get('split_rate_1000_final')}**",
            f"- Merge rate / 1000 ticks final: **{life.get('merge_rate_1000_final')}**",
            f"- Birth rate / 1000 ticks final: **{life.get('birth_rate_1000_final')}**",
            f"- Death rate / 1000 ticks final: **{life.get('death_rate_1000_final')}**",
            f"- Large / Medium / Small colonies final: **{life.get('large_colonies_final')} / {life.get('medium_colonies_final')} / {life.get('small_colonies_final')}**",
            f"- Top 3 mass final: **{life.get('top3_mass_final')}**",
            f"- Top 5 mass final: **{life.get('top5_mass_final')}**",
            f"- Dominance ratio final: **{life.get('dominance_ratio_final')}**",
            f"- Top sizes final: **{life.get('top_sizes_final')}**",
            f"- History window final: **{life.get('history_window_final')}**",
            f"- History delta objects final: **{life.get('history_delta_objects_final')}**",
            f"- History delta mass final: **{life.get('history_delta_mass_final')}**",
            f"- History delta largest final: **{life.get('history_delta_largest_final')}**",
            f"- Mass growth per tick final: **{life.get('mass_growth_per_tick_final')}**",
            f"- Objects growth per tick final: **{life.get('objects_growth_per_tick_final')}**",
            f"- Largest growth per tick final: **{life.get('largest_growth_per_tick_final')}**",
            f"- Stability index final: **{life.get('stability_index_final')}**",
            f"- Ecosystem phase final: **{life.get('ecosystem_phase_final')}**",
            f"- Active families final: **{life.get('active_families_final')}**",
            f"- Active tracked colonies final: **{life.get('active_colonies_tracked_final')}**",
            f"- Extinct colonies total final: **{life.get('extinct_colonies_total_final')}**",
            f"- Extinct families total final: **{life.get('extinct_families_total_final')}**",
            f"- Largest family size final: **{life.get('largest_family_size_final')}**",
            f"- Deepest generation final: **{life.get('deepest_generation_final')}**",
            f"- Oldest lineage age final: **{life.get('oldest_lineage_age_final')}**",
            f"- Lineage summary final: **{life.get('lineage_summary_final')}**",
            f"- Dynasty leader final: **{life.get('dynasty_leader_id_final')}**",
            f"- Dynasty line final: **{life.get('dynasty_line_final')}**",
            f"- Dynasty age final: **{life.get('dynasty_age_final')}**",
            f"- Dynasty born/living/dead final: **{life.get('dynasty_born_final')} / {life.get('dynasty_living_final')} / {life.get('dynasty_dead_final')}**",
            f"- Dynasty peak living final: **{life.get('dynasty_peak_living_final')}**",
            f"- Dynasty dominance final: **{life.get('dynasty_dominance_final')}**",
            f"- Dynasty survival final: **{life.get('dynasty_survival_final')}**",
            f"- Dynasty turnover final: **{life.get('dynasty_turnover_final')}**",
            f"- Dynasty birth/death rate final: **{life.get('dynasty_birth_rate_final')} / {life.get('dynasty_death_rate_final')}**",
            f"- Dynasty max generation final: **{life.get('dynasty_max_generation_final')}**",
            f"- Dynasty largest colony final: **{life.get('dynasty_largest_colony_final')}**",
            f"- Dynasty mass final: **{life.get('dynasty_mass_final')}**",
            f"- Demography final: **{life.get('demography_line_final')}**",
            f"- Demo born/dead/alive final: **{life.get('demo_born_total_final')} / {life.get('demo_dead_total_final')} / {life.get('demo_alive_tracked_final')}**",
            f"- Demo mean/max life final: **{life.get('demo_mean_life_final')} / {life.get('demo_max_life_final')}**",
            f"- Demo birth/death/turnover per 1000 ticks final: **{life.get('demo_birth_rate_1000_final')} / {life.get('demo_death_rate_1000_final')} / {life.get('demo_turnover_1000_final')}**",
            f"- Demo replacement/survival final: **{life.get('demo_replacement_final')} / {life.get('demo_survival_ratio_final')}**",
            f"- Evolution pressure final: **{life.get('evolution_line_final')}**",
            f"- Evo phase/stress/adapt/pressure final: **{life.get('evo_phase_final')} / {life.get('evo_stress_final')} / {life.get('evo_adapt_final')} / {life.get('evo_pressure_final')}**",
            f"- Evo recovery/risk final: **{life.get('evo_recovery_final')} / {life.get('evo_extinction_risk_final')}**",
            f"- Evo pressure source final: **{life.get('evo_source_line_final')}**",
            f"- Evo cause final: **{life.get('evo_cause_final')}**",
            f"- Evo source percentages F/D/L/I/M final: **{life.get('evo_src_frag_pct_final')} / {life.get('evo_src_death_pct_final')} / {life.get('evo_src_loss_pct_final')} / {life.get('evo_src_inst_pct_final')} / {life.get('evo_src_dom_pct_final')}**",
            f"- Evo timeline final: **{life.get('evo_timeline_line_final')}**",
            f"- Evo trends S/A/P/R final: **{life.get('evo_stress_trend_final')} / {life.get('evo_adapt_trend_final')} / {life.get('evo_pressure_trend_final')} / {life.get('evo_risk_trend_final')}**",
            f"- Evo timeline length final: **{life.get('evo_timeline_len_final')}**",
            f"- Chronicle counts: **{life.get('chronicle_counts')}**",
            f"- Chronicle severity counts: **{life.get('chronicle_severity_counts')}**",
            f"- Last chronicle event: **{life.get('chronicle_last_event')}**",
            f"- History book stored events: **{len(life.get('history_book_events') or [])}**",
            f"- Story era final: **{life.get('story_era_final')} ({life.get('story_era_age_final')} ticks)**",
            f"- Story era count: **{life.get('story_era_count_final')}**",
            "",
            "## Civilization Layer",
            f"- Civilization final: **{life.get('civilization_line_final')}**",
            f"- Civilization stage/score/age: **{life.get('civilization_stage_final')} / {life.get('civilization_score_final')} / {life.get('civilization_age_final')}**",
            f"- Cities/capital/urban mass: **{life.get('civilization_cities_final')} / {life.get('civilization_capital_size_final')} / {life.get('civilization_urban_mass_final')}**",
            f"- Urbanization/trade/conflict: **{life.get('civilization_urbanization_final')} / {life.get('civilization_trade_index_final')} / {life.get('civilization_conflict_index_final')}**",
            f"- Cohesion/specialization/tech/culture: **{life.get('civilization_cohesion_final')} / {life.get('civilization_specialization_final')} / {life.get('civilization_tech_index_final')} / {life.get('civilization_culture_index_final')}**",
            f"- Civilization collapse risk: **{life.get('civilization_collapse_risk_final')}**",
            f"- Civilization peak score/tick: **{life.get('civilization_peak_score')} / {life.get('civilization_peak_tick')}**",
            f"- Civilization count: **{life.get('civilization_count')}**",
            f"- Civilization event counts: **{life.get('civilization_event_counts')}**",
            f"- Civilization recent history rows: **{len(life.get('civilization_recent_history') or [])}**",
            "",
            "## Knowledge Layer",
            f"- Knowledge final: **{life.get('knowledge_line_final')}**",
            f"- Knowledge score/peak/tick: **{life.get('knowledge_score_final')} / {life.get('knowledge_peak_score')} / {life.get('knowledge_peak_tick')}**",
            f"- Knowledge families/dominant: **{life.get('knowledge_families_final')} / F{life.get('knowledge_dominant_family_final')} / {life.get('knowledge_dominant_axis_final')}**",
            f"- Knowledge axes exploration/cooperation/aggression: **{life.get('knowledge_exploration_final')} / {life.get('knowledge_cooperation_final')} / {life.get('knowledge_aggression_final')}**",
            f"- Knowledge axes efficiency/adaptation/memory: **{life.get('knowledge_efficiency_final')} / {life.get('knowledge_adaptation_final')} / {life.get('knowledge_memory_final')}**",
            f"- Transfer/loss: **{life.get('knowledge_transfer_final')} / {life.get('knowledge_loss_final')}**",
            f"- Discoveries: **{life.get('knowledge_discoveries')}**",
            f"- Knowledge event counts: **{life.get('knowledge_event_counts')}**",
            f"- Knowledge recent history rows: **{len(life.get('knowledge_recent_history') or [])}**",
            "",
            "## Feedback Layer",
            f"- Feedback final: **{life.get('feedback_line_final')}**",
            f"- Feedback score/peak/tick: **{life.get('feedback_score_final')} / {life.get('feedback_peak_score')} / {life.get('feedback_peak_tick')}**",
            f"- Feedback regime: **{life.get('feedback_regime_final')}**",
            f"- Survival/buffer/effective pressure/risk: **{life.get('feedback_survival_bonus_final')} / {life.get('feedback_pressure_buffer_final')} / {life.get('feedback_effective_pressure_final')} / {life.get('feedback_effective_risk_final')}**",
            f"- Self direction/environment/knowledge impact: **{life.get('feedback_self_direction_final')} / {life.get('feedback_environment_impact_final')} / {life.get('feedback_knowledge_impact_final')}**",
            f"- Feedback event counts: **{life.get('feedback_event_counts')}**",
            f"- Feedback recent history rows: **{len(life.get('feedback_recent_history') or [])}**",
            "",
            "## Emergence Evidence Layer",
            f"- Emergence final: **{life.get('emergence_line_final')}**",
            f"- Emergence score/peak/tick: **{life.get('emergence_score_final')} / {life.get('emergence_peak_score')} / {life.get('emergence_peak_tick')}**",
            f"- Emergence confidence/evidence: **{life.get('emergence_confidence_final')} / {life.get('emergence_evidence_count_final')}**",
            f"- Positive evidence: **{life.get('emergence_positive_evidence_final')}**",
            f"- Negative evidence: **{life.get('emergence_negative_evidence_final')}**",
            f"- Complexity/stability: **{life.get('emergence_complexity_index_final')} / {life.get('emergence_stability_signal_final')}**",
            f"- Emergence event counts: **{life.get('emergence_event_counts')}**",
            f"- Emergence recent history rows: **{len(life.get('emergence_recent_history') or [])}**",
            "",
            "## Validation & Calibration Layer",
            f"- Validation final: **{life.get('validation_line_final')}**",
            f"- Quality/peak/grade: **{life.get('validation_quality_final')} / {life.get('validation_quality_peak')} / {life.get('validation_grade_final')}**",
            f"- Repeatability/stability confidence: **{life.get('validation_repeatability_final')} / {life.get('validation_stability_confidence_final')}**",
            f"- False positive/false negative/noise: **{life.get('validation_false_positive_risk_final')} / {life.get('validation_false_negative_risk_final')} / {life.get('validation_noise_sensitivity_final')}**",
            f"- Warning: **{life.get('validation_warning_final')}**",
            f"- Explain: **{life.get('validation_explain_final')}**",
            f"- Validation event counts: **{life.get('validation_event_counts')}**",
            f"- Validation recent history rows: **{len(life.get('validation_recent_history') or [])}**",
            "",
            "## Life Evidence Model",
            f"- Verdict: **{life.get('life_evidence_verdict_final')}**",
            f"- Life score / confidence / uncertainty: **{life.get('life_evidence_score_final')} / {life.get('life_evidence_confidence_final')} / {life.get('life_evidence_uncertainty_final')}**",
            f"- Winning hypothesis / runner-up / margin: **{life.get('life_evidence_winner_final')} / {life.get('life_evidence_runner_up_final')} / {life.get('life_evidence_margin_final')}**",
            f"- Life gate passed: **{life.get('life_evidence_gate_passed_final')}**",
            f"- Strong independent axes: **{life.get('life_evidence_strong_axes_final')}**",
            f"- Positive evidence: **{life.get('life_evidence_positive_final')}**",
            f"- Alternative explanations: **{life.get('life_evidence_alternatives_final')}**",
            f"- Warnings: **{life.get('life_evidence_warnings_final')}**",
            f"- Evidence axes: **{life.get('life_evidence_axes_final')}**",
            f"- Hypothesis scores: **{life.get('life_evidence_hypotheses_final')}**",
            f"- Peak score / tick: **{life.get('life_evidence_peak')} / {life.get('life_evidence_peak_tick')}**",
            f"- Verdict shifts: **{life.get('life_evidence_event_counts')}**",
            "",
            f"- Peak defect cells: **{life.get('peak_defect_cells')}**",
            f"- Total center drift: **{life.get('total_center_drift')}**",
            f"- Final stage: **{life.get('final_life_stage')}**",
            "",
            "## Information / Legacy",
            f"- Identity persistence: **{life.get('identity_persistence_observed')}**",
            f"- Legacy score: **{life.get('legacy_score_observed')}**",
            f"- Information survival: **{life.get('information_survival_observed')}**",
            f"- Post-collapse structure: **{life.get('post_collapse_structure_observed')}**",
            f"- Expansion front speed: **{life.get('expansion_front_speed_observed')}**",
            f"- First large structure tick: **{life.get('first_large_structure_tick')}**",
            f"- Field saturation tick: **{life.get('field_saturation_tick')}**",
            "",
            "## Event Timeline",
            "",
        ]
        if data["events"]:
            for ev in data["events"]:
                lines.append(f"- tick **{ev['tick']}**: `{ev['type']}` - {ev['detail']}")
        else:
            lines.append("- No events recorded.")
        return "\n".join(lines) + "\n"

    def write_log(self, path: Path, rec, final_tick):
        data = self.passport(rec, final_tick)
        lines = [
            "Universe Search Observation Log",
            "=" * 36,
            "",
            f"Created: {data['created']}",
            f"Rule: {data['rule_id']:05d}",
            f"Score: {data['score']}",
            f"Source: {data['source']}",
            f"Generation: {data['generation']}",
            "",
            "Life observation",
            "----------------",
            json.dumps(data["life"], indent=2, ensure_ascii=False),
            "",
            "Event timeline",
            "--------------",
        ]
        for ev in data["events"]:
            lines.append(f"tick={ev['tick']} | {ev['type']} | {ev['detail']}")
        lines += ["", "Recent samples", "--------------"]
        for s in self.samples[-30:]:
            lines.append(str(s))
        path.write_text("\n".join(lines), encoding="utf-8")


# ---------------- Tk viewer ----------------

class WorldViewer:
    def __init__(self, root, rule, rec, args, observer: LifeObserver):
        self.root = root
        self.rule = rule
        self.rec = rec
        self.args = args
        self.observer = observer
        simulation_rule = rule
        if args.initial_state_mode == InitialStateMode.RANDOM_SEED.value:
            if args.experiment_seed is None:
                raise ValueError(
                    "random_seed requires --experiment-seed"
                )
            simulation_rule = copy.deepcopy(rule)
            simulation_rule.seed = int(args.experiment_seed)
            print(
                "[experiment] random initial state uses Search seed_field "
                f"with experiment_seed={simulation_rule.seed}"
            )

        self.sim = base.FieldSim(
            simulation_rule,
            width=args.field_width,
            height=args.field_height,
            topology=args.topology,
            boundary_mode=args.boundary_mode,
        )
        self.tick = 0
        self.running = True
        self.closed = False
        self.last_autosave_tick = 0
        self.last_save_tick = 0
        self.speed_label = f"x{self.args.speed}"
        self._perf_last_wall = None
        self._perf_last_tick = 0
        self._perf_fps = 0.0
        self._perf_tps = 0.0
        self._perf_frame_ms = 0.0
        # Rendering is an optional presentation layer. Scientific observation,
        # telemetry, checkpoints, and the instrument panel continue while the
        # cell visualization is disabled.
        self.visualization_enabled = True

        root.title(
            "Universe Search Observer v5.0 Scientific Ontology "
            f"- rule {rec['rule_id']:05d}"
        )

        # Stage 14.2 UI: adaptive Linux/Windows layout.
        # The universe canvas expands to the whole left side of the window;
        # the right panel keeps a stable instrument width; chronicle stays below.
        self.panel_min_width = 360
        self.panel_default_width = 650
        self.panel_width = self._load_panel_width()
        self._panel_drag_start_x = 0
        self._panel_drag_start_width = self.panel_width
        self._layout_cell = max(1, int(args.cell or 1))
        self._layout_field_x = 0
        self._layout_field_y = 0
        self._layout_field_w = self.sim.width * self._layout_cell
        self._layout_field_h = self.sim.height * self._layout_cell

        try:
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            start_w = min(max(1280, self.sim.width * args.cell + self.panel_width + 80), max(900, sw - 80))
            start_h = min(max(720, self.sim.height * args.cell + 190), max(640, sh - 80))
            root.geometry(f"{start_w}x{start_h}+20+20")
            root.minsize(1000, 650)
        except Exception:
            pass

        self.main_frame = tk.Frame(root, bg="#111111")
        self.main_frame.pack(fill="both", expand=True)

        # Left column: universe canvas + chronicle directly below the simulation.
        self.left_col = tk.Frame(self.main_frame, bg="#111111")

        # Do not request a canvas as large as field_size × cell_size. On large
        # scientific fields that requested size can push the instrument panel
        # beyond the visible desktop. The canvas instead consumes the space
        # remaining after the stable right-hand panel is laid out.
        self.canvas = tk.Canvas(
            self.left_col,
            bg="black",
            highlightthickness=0,
        )
        self.canvas.pack(side="top", fill="both", expand=True)

        self.chronicle_frame = tk.Frame(self.left_col, padx=8, pady=4, bg="#111111")
        self.chronicle_frame.pack(side="bottom", fill="x")
        self.chronicle_expanded = True
        self.chronicle_title = tk.Label(
            self.chronicle_frame,
            text="LEGACY CHRONICLE",
            anchor="w",
            justify="left",
            font=("Consolas", 10, "bold"),
            fg="#ffffff",
            bg="#222222",
            padx=6,
            pady=2,
            cursor="hand2",
        )
        self.chronicle_title.pack(fill="x")
        self.chronicle_title.config(text="▼ LEGACY CHRONICLE")
        self.chronicle_title.bind("<Button-1>", self._toggle_chronicle)
        self.chronicle_label = tk.Label(
            self.chronicle_frame,
            text="",
            anchor="w",
            justify="left",
            font=("Consolas", 9),
            fg="#dddddd",
            bg="#111111",
            padx=6,
            wraplength=max(640, self.sim.width * args.cell - 20),
        )
        self.chronicle_label.pack(fill="x")

        # Right column: compact instrument panel. The narrow separator on its
        # left can be dragged horizontally to resize the panel.
        self.sidebar_visible = True
        self.panel = tk.Frame(self.main_frame, padx=8, pady=6, bg="#111111", width=self.panel_width)
        self.panel.pack(side="right", fill="y", expand=False, padx=10)
        self.panel.pack_propagate(False)

        self.panel_resize_handle = tk.Frame(
            self.main_frame,
            width=7,
            bg="#333333",
            cursor="sb_h_double_arrow",
        )
        self.panel_resize_handle.pack(side="right", fill="y")
        self.panel_resize_handle.pack_propagate(False)
        self.panel_resize_handle.bind("<ButtonPress-1>", self._start_panel_resize)
        self.panel_resize_handle.bind("<B1-Motion>", self._resize_panel)
        self.panel_resize_handle.bind("<ButtonRelease-1>", self._finish_panel_resize)
        self.panel_resize_handle.bind("<Double-Button-1>", self._reset_panel_width)

        # Pack the flexible universe column after the fixed instrument column.
        # This guarantees that the panel receives space first on constrained
        # desktops and makes the world viewport genuinely adaptive.
        self.left_col.pack(side="left", fill="both", expand=True)

        self.panel_labels = {}
        self.panel_sections = {}
        self._build_panel()

        # The focus button remains on the universe side, so the instrument
        # panel can always be restored after it has been hidden.
        self.sidebar_toggle = tk.Button(
            self.left_col,
            text="◀ PANEL",
            command=self.toggle_sidebar,
            anchor="center",
            font=("Consolas", 9, "bold"),
            fg="#ffffff",
            bg="#222222",
            activeforeground="#ffffff",
            activebackground="#333333",
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
        )
        self.sidebar_toggle.place(relx=1.0, x=-10, y=10, anchor="ne")
        self.sidebar_toggle.lift()

        self.info = tk.Label(root, text="", anchor="w", justify="left", font=("Consolas", 9))
        self.info.pack(fill="x")

        self.rects = []
        for y in range(self.sim.height):
            row = []
            for x in range(self.sim.width):
                row.append(self.canvas.create_rectangle(
                    0, 0, 1, 1,
                    outline="",
                    fill="#000000",
                ))
            self.rects.append(row)
        self.visualization_notice = self.canvas.create_text(
            0, 0,
            text="VISUALIZATION OFF\nSimulation, telemetry and instruments remain active",
            fill="#bbbbbb",
            font=("Consolas", 14, "bold"),
            justify="center",
            state="hidden",
        )

        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.root.after(50, self._relayout_world)

        root.bind("<space>", self.toggle)
        root.bind("<Right>", self.single_step)
        root.bind("<r>", self.reset)
        root.bind("<s>", self.save_now)
        root.bind("<Tab>", self.toggle_sidebar)
        root.bind("v", self.toggle_visualization)
        root.bind("V", self.toggle_visualization)

        # Speed hotkeys:
        # 1 = normal, 2 = fast, 3 = turbo, 4 = ultra
        root.bind("1", lambda e: self.set_speed(1, "x1 normal"))
        root.bind("2", lambda e: self.set_speed(10, "x10 fast"))
        root.bind("3", lambda e: self.set_speed(100, "x100 turbo"))
        root.bind("4", lambda e: self.set_speed(1000, "x1000 ultra"))
        root.bind("0", self.toggle)

        root.bind("<Escape>", lambda e: self.close(ask=True))
        root.protocol("WM_DELETE_WINDOW", lambda: self.close(ask=True))

        self.draw()
        self.loop()

    def _panel_header(self, parent, title, command):
        label = tk.Button(
            parent,
            text=f"▼ {title}",
            anchor="w",
            justify="left",
            font=("Consolas", 10, "bold"),
            fg="#ffffff",
            bg="#222222",
            activeforeground="#ffffff",
            activebackground="#333333",
            padx=6,
            pady=1,
            relief="flat",
            command=command,
            cursor="hand2",
        )
        label.pack(fill="x", pady=(3, 1))
        return label

    def _panel_value(self, parent, key, default=""):
        # Panel rows must keep a predictable height.  In particular, wrapping
        # the keyboard help at a fixed 360 px made PERFORMANCE grow to four
        # lines on scaled Linux desktops and overlap the bottom status bar.
        wrap = 360 if key == "event" else 0
        label = tk.Label(
            parent,
            text=default,
            anchor="w",
            justify="left",
            font=("Consolas", 9),
            fg="#dddddd",
            bg="#111111",
            padx=6,
            wraplength=wrap,
        )
        label.pack(fill="x")
        self.panel_labels[key] = label
        return label

    def _create_panel_section(self, title, keys, expanded=True):
        section = tk.Frame(self.panel_content, bg="#111111")
        section.pack(fill="x")

        body = tk.Frame(section, bg="#111111")
        state = {
            "expanded": bool(expanded),
            "body": body,
        }
        header = self._panel_header(
            section,
            title,
            lambda section_title=title: self._toggle_panel_section(section_title),
        )
        state["header"] = header
        self.panel_sections[title] = state

        for key in keys:
            self._panel_value(body, key)

        if expanded:
            body.pack(fill="x")
        else:
            header.config(text=f"▶ {title}")
        return section

    def _toggle_panel_section(self, title):
        state = self.panel_sections.get(title)
        if not state:
            return
        if state["expanded"]:
            state["body"].pack_forget()
            state["header"].config(text=f"▶ {title}")
            state["expanded"] = False
        else:
            state["body"].pack(fill="x")
            state["header"].config(text=f"▼ {title}")
            state["expanded"] = True
        self.panel_content.update_idletasks()
        self._sync_panel_scrollregion()

    def _toggle_chronicle(self, event=None):
        self.chronicle_expanded = not self.chronicle_expanded
        if self.chronicle_expanded:
            self.chronicle_label.pack(fill="x")
            self.chronicle_title.config(text="▼ LEGACY CHRONICLE")
        else:
            self.chronicle_label.pack_forget()
            self.chronicle_title.config(text="▶ LEGACY CHRONICLE")
        self.root.after_idle(self._relayout_world)
        return "break"

    def _sync_panel_scrollregion(self, event=None):
        try:
            self.panel_scroll_canvas.configure(
                scrollregion=self.panel_scroll_canvas.bbox("all")
            )
        except Exception:
            pass

    def _resize_panel_content(self, event):
        try:
            self.panel_scroll_canvas.itemconfigure(
                self.panel_window,
                width=max(1, event.width),
            )
        except Exception:
            pass

    def _scroll_panel(self, event):
        delta = 0
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        elif getattr(event, "delta", 0):
            delta = -1 if event.delta > 0 else 1
        if delta:
            self.panel_scroll_canvas.yview_scroll(delta * 3, "units")
        return "break"

    def _bind_panel_scroll(self, event=None):
        self.root.bind_all("<MouseWheel>", self._scroll_panel)
        self.root.bind_all("<Button-4>", self._scroll_panel)
        self.root.bind_all("<Button-5>", self._scroll_panel)

    def _unbind_panel_scroll(self, event=None):
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")

    def _panel_settings_path(self):
        return (
            Path(self.args.results_dir).expanduser().resolve()
            / ".archon_observer_ui.json"
        )

    def _load_panel_width(self):
        env_width = os.environ.get("OBSERVER_PANEL_WIDTH")
        if env_width is not None:
            try:
                return max(self.panel_min_width, int(env_width))
            except (TypeError, ValueError):
                pass

        try:
            data = json.loads(self._panel_settings_path().read_text(encoding="utf-8"))
            saved_width = int(data.get("panel_width", self.panel_default_width))
            return max(self.panel_min_width, saved_width)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return self.panel_default_width

    def _save_panel_width(self):
        try:
            settings_path = self._panel_settings_path()
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = json.loads(settings_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                data = {}
            data["panel_width"] = int(self.panel_width)
            temp_path = settings_path.with_name(
                f"{settings_path.name}.{os.getpid()}.tmp"
            )
            temp_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(settings_path)
        except OSError:
            pass

    def _start_panel_resize(self, event):
        self._panel_drag_start_x = int(event.x_root)
        self._panel_drag_start_width = int(self.panel.winfo_width())
        self.panel_resize_handle.configure(bg="#777777")
        return "break"

    def _resize_panel(self, event):
        delta = self._panel_drag_start_x - int(event.x_root)
        available_width = max(
            self.panel_min_width,
            int(self.root.winfo_width()) - 320,
        )
        self.panel_width = min(
            available_width,
            max(self.panel_min_width, self._panel_drag_start_width + delta),
        )
        self.panel.configure(width=self.panel_width)
        self.root.after_idle(self._relayout_world)
        return "break"

    def _finish_panel_resize(self, event=None):
        self.panel_resize_handle.configure(bg="#333333")
        self._save_panel_width()
        return "break"

    def _reset_panel_width(self, event=None):
        self.panel_width = self.panel_default_width
        self.panel.configure(width=self.panel_width)
        self._save_panel_width()
        self.root.after_idle(self._relayout_world)
        return "break"

    def toggle_sidebar(self, event=None):
        if self.sidebar_visible:
            self.panel_resize_handle.pack_forget()
            self.panel.pack_forget()
            self.sidebar_toggle.config(text="PANEL ▶")
            self.sidebar_visible = False
        else:
            self.panel.pack(side="right", fill="y", expand=False, padx=10)
            self.panel_resize_handle.pack(side="right", fill="y")
            self.sidebar_toggle.config(text="◀ PANEL")
            self.sidebar_visible = True
        self.sidebar_toggle.lift()
        self.root.after_idle(self._relayout_world)
        return "break"

    def _on_canvas_resize(self, event=None):
        self._relayout_world()

    def _relayout_world(self):
        # Fit the whole W x H world into the available canvas area while
        # preserving square cells. This fixes the Linux "tiny top-left" view.
        try:
            canvas_w = max(1, int(self.canvas.winfo_width()))
            canvas_h = max(1, int(self.canvas.winfo_height()))
        except Exception:
            return

        cell = max(1, min(canvas_w // max(1, self.sim.width), canvas_h // max(1, self.sim.height)))
        field_w = self.sim.width * cell
        field_h = self.sim.height * cell
        field_x = max(0, (canvas_w - field_w) // 2)
        field_y = max(0, (canvas_h - field_h) // 2)

        if (cell, field_x, field_y, field_w, field_h) == (
            self._layout_cell,
            self._layout_field_x,
            self._layout_field_y,
            self._layout_field_w,
            self._layout_field_h,
        ):
            return

        self._layout_cell = cell
        self._layout_field_x = field_x
        self._layout_field_y = field_y
        self._layout_field_w = field_w
        self._layout_field_h = field_h

        if hasattr(self, "visualization_notice"):
            self.canvas.coords(
                self.visualization_notice,
                max(1, canvas_w) / 2,
                max(1, canvas_h) / 2,
            )

        for y in range(self.sim.height):
            y0 = field_y + y * cell
            y1 = y0 + cell
            for x in range(self.sim.width):
                x0 = field_x + x * cell
                self.canvas.coords(self.rects[y][x], x0, y0, x0 + cell, y1)

        if hasattr(self, "chronicle_label"):
            self.chronicle_label.config(wraplength=max(300, canvas_w - 24))

    def _build_panel(self):
        # Stage 2C.3 label contract retained by the accordion implementation:
        # self._panel_header("ONTOLOGY / LIFECYCLE")
        toolbar = tk.Frame(self.panel, bg="#111111")
        toolbar.pack(fill="x", pady=(0, 3))
        tk.Label(
            toolbar,
            text="INSTRUMENTS",
            anchor="w",
            font=("Consolas", 10, "bold"),
            fg="#bbbbbb",
            bg="#111111",
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            toolbar,
            text="Tab: focus",
            anchor="e",
            font=("Consolas", 8),
            fg="#777777",
            bg="#111111",
        ).pack(side="right")

        scroll_frame = tk.Frame(self.panel, bg="#111111")
        scroll_frame.pack(fill="both", expand=True)
        self.panel_scroll_canvas = tk.Canvas(
            scroll_frame,
            bg="#111111",
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = tk.Scrollbar(
            scroll_frame,
            orient="vertical",
            command=self.panel_scroll_canvas.yview,
        )
        self.panel_scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.panel_scroll_canvas.pack(side="left", fill="both", expand=True)

        self.panel_content = tk.Frame(self.panel_scroll_canvas, bg="#111111")
        self.panel_window = self.panel_scroll_canvas.create_window(
            (0, 0),
            window=self.panel_content,
            anchor="nw",
        )
        self.panel_content.bind("<Configure>", self._sync_panel_scrollregion)
        self.panel_scroll_canvas.bind("<Configure>", self._resize_panel_content)
        self.panel_scroll_canvas.bind("<Enter>", self._bind_panel_scroll)
        self.panel_scroll_canvas.bind("<Leave>", self._unbind_panel_scroll)
        self.panel_content.bind("<Enter>", self._bind_panel_scroll)
        self.panel_content.bind("<Leave>", self._unbind_panel_scroll)

        self._create_panel_section(
            "UNIVERSE",
            ("status", "world", "phase", "era"),
            expanded=True,
        )
        self._create_panel_section(
            "LIFE",
            ("life_evidence", "life", "life_births", "life_survival", "lineage"),
            expanded=True,
        )
        self._create_panel_section(
            "ONTOLOGY / LIFECYCLE",
            (
                "ontology_state",
                "ontology_coverage",
                "ontology_first",
                "ontology_confidence",
                "ontology_terminal",
            ),
            expanded=True,
        )
        self._create_panel_section(
            "PRESSURE",
            ("pressure", "pressure_cause"),
            expanded=False,
        )
        self._create_panel_section(
            "MORPHOLOGY",
            ("morph_class", "morph_shape1", "morph_shape2", "morph_change"),
            expanded=False,
        )
        self._create_panel_section(
            "KNOWLEDGE / EVIDENCE",
            ("knowledge", "feedback", "emergence", "validation"),
            expanded=False,
        )
        self._create_panel_section(
            "PERFORMANCE",
            ("perf", "perf2", "keys"),
            expanded=False,
        )
        performance_body = self.panel_sections["PERFORMANCE"]["body"]
        self.visualization_button = tk.Button(
            performance_body,
            text="Visualization: ON",
            command=self.toggle_visualization,
            anchor="w",
            font=("Consolas", 9, "bold"),
            fg="#7CFF8A",
            bg="#222222",
            activeforeground="#ffffff",
            activebackground="#333333",
            relief="flat",
            padx=6,
            pady=4,
            cursor="hand2",
        )
        self.visualization_button.pack(fill="x", pady=(4, 2))
        self._sync_panel_scrollregion()

    def _set_panel(self, key, text, fg=None):
        label = self.panel_labels.get(key)
        if label is not None:
            if fg:
                label.config(text=str(text), fg=fg)
            else:
                label.config(text=str(text))

    def _set_chronicle(self, text):
        if hasattr(self, "chronicle_label"):
            self.chronicle_label.config(text=str(text))

    def _score_color(self, value):
        try:
            v = float(value)
        except Exception:
            v = 0.0
        if v >= 0.80:
            return "#7CFF8A"
        if v >= 0.55:
            return "#FFF17A"
        if v >= 0.35:
            return "#FFB86B"
        return "#FF6B6B"

    def _bar(self, value, width=10):
        try:
            v = max(0.0, min(1.0, float(value)))
        except Exception:
            v = 0.0
        filled = int(round(v * width))
        return "█" * filled + "░" * (width - filled)

    def _meter(self, name, value):
        return f"{name:<4} {self._bar(value)} {float(value or 0):.2f}"

    def _chronicle_compact(self, text):
        text = str(text).replace("event: ", "ev: ")
        text = text.replace("phase-change - ", "")
        text = text.replace(" -> ", "→")
        text = text.replace("STABLE", "STAB")
        text = text.replace("REORGANIZING", "REORG")
        text = text.replace("FRAGMENTATION", "FRAG")
        text = text.replace("EXPANSION", "EXP")
        text = text.replace("COLLAPSE", "COLL")
        return text

    def _update_panel(self, c, metrics, phase_short, event_text, autosave_text):
        def n(value, digits=2):
            try:
                return f"{float(value):.{digits}f}"
            except Exception:
                return "n/a"

        def first(*keys, default=0):
            for key in keys:
                v = c.get(key)
                if v not in (None, "", "n/a"):
                    return v
            return default

        self._set_panel("status", f"Rule {self.rec['rule_id']:05d} | tick {self.tick} | {self.speed_label}")
        self._set_panel("world", f"[SEARCH] score {n(self.rec.get('score'),2)} | mem {n(metrics.get('memory_trace_score'),1)} | tr {metrics.get('persistent_tracks')}")
        self._set_panel("phase", f"[LEGACY] eco {phase_short} | evo {c.get('evo_phase','SEED')}")
        self._set_panel(
            "era",
            f"era {c.get('story_era','')} {c.get('story_era_age',0)}t | Δo {c.get('history_delta_objects',0):+d} Δm {c.get('history_delta_mass',0):+d} | stab {c.get('stability_index',0):.2f}"
        )

        born = first("dynasty_born", "demo_born_total", default=0)
        live = first("dynasty_living", "demo_alive_tracked", default=0)
        dead = first("dynasty_dead", "demo_dead_total", default=0)
        peak = first("dynasty_peak_living", default=0)
        surv = first("dynasty_survival", "demo_survival_ratio", default=0.0)
        turn = first("dynasty_turnover", "demo_turnover_1000", default=0.0)

        life_score = float(c.get("life_evidence_score", 0.0) or 0.0)
        life_conf = float(c.get("life_evidence_confidence", 0.0) or 0.0)
        self._set_panel(
            "life_evidence",
            f"[LEGACY] {c.get('life_evidence_verdict','INSUFFICIENT_EVIDENCE')} | score {life_score:.2f} | conf {life_conf:.2f}",
            self._score_color(life_score),
        )

        self._set_panel(
            "life",
            f"obj {c.get('objects',0):>3} | mass {c.get('total_living_mass',0):>4} | L {c.get('largest',0):>4} | H {c.get('health',0):.2f}"
        )
        self._set_panel(
            "life_births",
            f"born {born} | live {live} | dead {dead}"
        )
        self._set_panel(
            "life_survival",
            f"peak {peak} | surv {float(surv or 0):.2f} | turn {float(turn or 0):.2f} | dom {c.get('dominance_ratio',0):.2f}"
        )
        self._set_panel(
            "lineage",
            f"fam {c.get('active_families',0)} | trk {c.get('active_colonies_tracked',0)} | gen {c.get('deepest_generation',0)} | old {c.get('oldest_lineage_age',0)}"
        )

        lifecycle_ui = build_lifecycle_ui_snapshot(
            c.get("observer_state")
        )
        self._set_panel(
            "ontology_state",
            lifecycle_ui["state"],
            self._score_color(life_score),
        )
        self._set_panel(
            "ontology_coverage",
            lifecycle_ui["coverage"],
        )
        self._set_panel("ontology_first", lifecycle_ui["first"])
        self._set_panel(
            "ontology_confidence",
            lifecycle_ui["confidence"],
        )
        self._set_panel(
            "ontology_terminal",
            lifecycle_ui["terminal"],
        )

        risk = c.get("evo_extinction_risk", 0.0)
        self._set_panel(
            "pressure",
            f"stress {c.get('evo_stress',0):.2f} | adapt {c.get('evo_adapt',0):.2f} | press {c.get('evo_pressure',0):.2f} | risk {risk:.2f}",
            self._score_color(1.0 - float(risk or 0))
        )
        self._set_panel(
            "pressure_cause",
            f"cause {c.get('evo_cause','NONE')} | F{c.get('evo_src_frag_pct',0):.0f} D{c.get('evo_src_death_pct',0):.0f} L{c.get('evo_src_loss_pct',0):.0f} I{c.get('evo_src_inst_pct',0):.0f} M{c.get('evo_src_dom_pct',0):.0f}"
        )

        morph_class = c.get("morphology_class") or "n/a"
        morph_score = c.get("morphology_score", 0.0)
        self._set_panel("morph_class", f"{morph_class} {self._bar(morph_score)} {morph_score:.2f}", self._score_color(morph_score))
        self._set_panel(
            "morph_shape1",
            f"Cmp {c.get('morphology_compactness',0):.2f} | Asp {c.get('morphology_aspect',0):.2f} | Edge {c.get('morphology_edge_complexity',0):.2f}"
        )
        self._set_panel(
            "morph_shape2",
            f"Fill {c.get('morphology_bbox_fill',0):.2f} | Sym {c.get('morphology_symmetry',0):.2f} | Br {c.get('morphology_branching',0):.2f}"
        )
        self._set_panel(
            "morph_change",
            f"Δshape {c.get('morphology_change_rate',0):.3f} | stable {c.get('morphology_stability_ticks',0)} | dom {c.get('morphology_dominant_class','')}"
        )

        know_score = c.get("knowledge_score", 0.0)
        fb_score = c.get("feedback_score", 0.0)
        emg_score = c.get("emergence_score", 0.0)
        val_q = c.get("validation_quality", 0.0)
        self._set_panel("knowledge", self._meter("KNOW", know_score), self._score_color(know_score))
        self._set_panel("feedback", self._meter("FB", fb_score), self._score_color(fb_score))
        self._set_panel("emergence", self._meter("EMG", emg_score) + f" {c.get('emergence_confidence','')}", self._score_color(emg_score))
        self._set_panel("validation", self._meter("VAL", val_q) + f" {c.get('validation_grade','')}", self._score_color(val_q))

        self._set_panel(
            "perf",
            f"FPS {self._perf_fps:.1f} | TPS {self._perf_tps:.1f} | draw {self._perf_frame_ms:.1f} ms",
        )
        self._set_panel(
            "perf2",
            f"step/frame {self.args.speed} | render "
            f"{'on' if self.visualization_enabled else 'off'} | "
            f"autosave {self.args.autosave_every or 'off'}",
        )

        compact_event = self._chronicle_compact(event_text)
        self._set_chronicle(compact_event)
        self._set_panel(
            "keys",
            "Space pause | → step | S save | V visualization | Esc exit\n1/2/3/4 speed",
        )

    def toggle_visualization(self, event=None):
        self.visualization_enabled = not self.visualization_enabled
        if self.visualization_enabled:
            self.visualization_button.config(
                text="Visualization: ON",
                fg="#7CFF8A",
            )
            self.canvas.itemconfigure(self.visualization_notice, state="hidden")
            for row in self.rects:
                for item in row:
                    self.canvas.itemconfigure(item, state="normal")
            self.root.after_idle(self._relayout_world)
            print("[performance] visualization enabled")
        else:
            self.visualization_button.config(
                text="Visualization: OFF",
                fg="#FFB86B",
            )
            for row in self.rects:
                for item in row:
                    self.canvas.itemconfigure(item, state="hidden")
            self.canvas.itemconfigure(self.visualization_notice, state="normal")
            self.canvas.tag_raise(self.visualization_notice)
            print(
                "[performance] visualization disabled; simulation, Observer, "
                "telemetry and panel remain active"
            )
        self._set_panel(
            "perf2",
            f"step/frame {self.args.speed} | render "
            f"{'on' if self.visualization_enabled else 'off'} | "
            f"autosave {self.args.autosave_every or 'off'}",
        )
        return "break"

    def toggle(self, event=None):
        self.running = not self.running

    def set_speed(self, speed: int, label: str):
        self.args.speed = speed
        self.speed_label = label
        print(f"[speed] {label} ({speed} step(s) per frame)")

    def single_step(self, event=None):
        self.sim.step()
        self.tick += 1
        self.draw()

    def reset(self, event=None):
        self.sim = base.FieldSim(self.rule)
        self.tick = 0
        # full observer reset would require rebuilding files; avoid silently overwriting
        self.observer.add_event(self.tick, "manual-reset", "simulation reset requested")

    def save_now(self, event=None):
        self.save_checkpoint(reason="manual")

    def _observer_output_root(self):
        """Keep isolated mutation passports inside their mutation run."""
        if self.args.run_output_dir:
            return Path(self.args.run_output_dir).expanduser().resolve()
        return Path(self.args.results_dir).expanduser().resolve()

    def save_checkpoint(self, reason="autosave"):
        self.observer.write_outputs(
            self._observer_output_root(),
            self.rec,
            self.tick,
            write_log=True,
            write_passport=True,
        )
        self.last_save_tick = self.tick
        print(f"[{reason}] checkpoint saved at tick {self.tick}")

    def close(self, ask=True):
        if self.closed:
            return

        if ask:
            unsaved = max(0, self.tick - self.last_save_tick)
            msg = (
                f"Current tick: {self.tick}\n"
                f"Last save tick: {self.last_save_tick}\n"
                f"Unsaved ticks: {unsaved}\n\n"
                "Choose what to do:"
            )

            dialog = tk.Toplevel(self.root)
            dialog.title("Close Universe Observer?")
            dialog.resizable(False, False)
            dialog.transient(self.root)
            dialog.grab_set()

            label = tk.Label(dialog, text=msg, justify="left", padx=18, pady=14, font=("Consolas", 10))
            label.pack(fill="both")

            buttons = tk.Frame(dialog, padx=12, pady=12)
            buttons.pack(fill="x")

            choice = {"value": "cancel"}

            def choose(value):
                choice["value"] = value
                dialog.destroy()

            tk.Button(buttons, text="💾 Save && Exit", width=20, command=lambda: choose("save")).pack(side="left", padx=5)
            tk.Button(buttons, text="❌ Exit without Saving", width=22, command=lambda: choose("exit")).pack(side="left", padx=5)
            tk.Button(buttons, text="↩ Cancel", width=14, command=lambda: choose("cancel")).pack(side="left", padx=5)

            dialog.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
            self.root.wait_window(dialog)

            if choice["value"] == "cancel":
                return

            if choice["value"] == "save":
                self.save_checkpoint(reason="exit-save")

        self.closed = True

        if (self.args.log or self.args.passport) and self.tick != self.last_save_tick:
            self.observer.write_outputs(
                self._observer_output_root(),
                self.rec,
                self.tick,
                write_log=self.args.log,
                write_passport=self.args.passport,
            )

        self._save_panel_width()
        self.observer.close_live_files()
        self.root.destroy()

    def draw(self):
        frame_start = datetime.now().timestamp()
        now = frame_start
        if self._perf_last_wall is not None:
            dt = max(1e-6, now - self._perf_last_wall)
            self._perf_fps = 0.85 * self._perf_fps + 0.15 * (1.0 / dt)
            self._perf_tps = 0.85 * self._perf_tps + 0.15 * ((self.tick - self._perf_last_tick) / dt)
        self._perf_last_wall = now
        self._perf_last_tick = self.tick

        if self.visualization_enabled:
            for y in range(self.sim.height):
                for x in range(self.sim.width):
                    self.canvas.itemconfig(
                        self.rects[y][x],
                        fill=rgb_hex(self.sim.a[y][x]),
                    )

        # Observation and persistence are independent of visualization.
        self.observer.update(self.sim.a, self.tick)
        metrics = self.rec.get("metrics") or {}
        c = self.observer.current

        def n(value, digits=2):
            try:
                return f"{float(value):.{digits}f}"
            except Exception:
                return "n/a"

        def cut(value, max_len=120):
            value = str(value)
            return value if len(value) <= max_len else value[:max_len - 3] + "..."

        phase = str(c.get("ecosystem_phase", "WARMUP"))
        phase_short = {
            "WARMUP": "WARM",
            "EXPANSION": "EXP",
            "FRAGMENTATION": "FRAG",
            "MERGING": "MERGE",
            "STABLE": "STAB",
            "REORGANIZING": "REORG",
            "COLLAPSE": "COLL",
            "COLLAPSED": "DEAD",
        }.get(phase, phase[:6])

        ev = self.observer.event_text()
        if ev.startswith("event: "):
            ev = "ev: " + ev[7:]

        autosave_text = f" | save{self.args.autosave_every}" if self.args.autosave_every else ""
        sev = c.get("chronicle_last_severity", "")
        ev_line = cut(self._chronicle_compact((f"[{sev}] " if sev else "") + ev), 96)

        self._update_panel(c, metrics, phase_short, ev_line, autosave_text)

        status = (
            f"t={self.tick} r={self.rec['rule_id']:05d} sc={n(self.rec.get('score'),2)} | "
            f"obj={c.get('objects',0)} mass={c.get('total_living_mass',0)} L={c.get('largest',0)} | "
            f"P={phase_short} {c.get('evo_phase','SEED')} | "
            f"MORPH {c.get('morphology_class','n/a')} {c.get('morphology_score',0):.2f} | "
            f"{self.speed_label}"
        )
        timeline = cut(c.get("evo_timeline_line", "TL"), 132)
        self._perf_frame_ms = (datetime.now().timestamp() - frame_start) * 1000.0
        status_bar = (
            f"tick {self.tick} | rule {self.rec['rule_id']:05d} | speed {self.speed_label} | "
            f"autosave {self.args.autosave_every or 0} | fps {self._perf_fps:.1f} | gpu/cupy if backend enabled"
        )
        self.info.config(text="\n".join([status_bar, timeline, ev_line]))


    def loop(self):
        if self.running:
            batch_steps = bounded_batch_steps(
                self.tick,
                self.args.speed,
                self.args.max_ticks,
            )
            for _ in range(batch_steps):
                self.sim.step()
                self.tick += 1

            self.draw()

            if self.args.autosave_every and self.tick - self.last_autosave_tick >= self.args.autosave_every:
                self.save_checkpoint(reason="autosave")
                self.last_autosave_tick = self.tick

            if self.args.auto_stop and self.observer.collapse_tick is not None:
                print(self.observer.status_text())
                self.observer.write_outputs(
                    self._observer_output_root(),
                    self.rec,
                    self.tick,
                    write_log=self.args.log,
                    write_passport=self.args.passport,
                )
                self.running = False

            if self.args.max_ticks and self.tick >= self.args.max_ticks:
                print(f"Reached max ticks: {self.args.max_ticks}")
                self.running = False

                if self.args.exit_at_max_ticks:
                    # A queued scientific run must become self-contained:
                    # persist the exact horizon, finalize SQLite/CSV writers,
                    # close the window, and return code 0 to the Launcher.
                    self.save_checkpoint(reason="max-ticks")
                    print(
                        "[queue] max-ticks checkpoint finalized; "
                        "closing Observer"
                    )
                    self.root.after_idle(
                        lambda: self.close(ask=False)
                    )
                else:
                    self.observer.write_outputs(
                        self._observer_output_root(),
                        self.rec,
                        self.tick,
                        write_log=self.args.log,
                        write_passport=self.args.passport,
                    )

        self.root.after(self.args.delay, self.loop)


# ---------- Stage 9: lightweight LifeObserver profiling ----------
def _life_observer_profile_report(self, top_n=16):
    prof = getattr(self, "_observer_profile", None)
    if not prof:
        return "Observer profiler: no data"
    items=[]
    for name,data in prof.items():
        calls=int(data.get("calls",0)); total=float(data.get("total",0.0))
        if calls:
            items.append((total,calls,name,total/calls))
    items.sort(reverse=True)
    total_update=prof.get("update",{}).get("total",0.0)
    sub_total=sum(float(d.get("total",0.0)) for n,d in prof.items() if n!="update")
    lines=["","=== LifeObserver profile ===",f"update total: {total_update:.4f}s","top methods:"]
    for total,calls,name,avg in items[:top_n]:
        pct=(total/total_update*100.0) if total_update else 0.0
        lines.append(f"  {name:36s} {total:9.4f}s {calls:7d} calls {avg*1000:8.3f} ms/call {pct:6.2f}%")
    return "\n".join(lines)

def _enable_life_observer_profiling():
    import os,time
    if getattr(LifeObserver,"_observer_profiler_enabled",False):
        return
    methods=["update","_defect_mask","_component_records","_components","_track_object_events","_recent_event_rates","_growth_phase","_colony_size_distribution","_update_population_history","_ecosystem_phase","_evolution_pressure","_update_evo_timeline","_write_pressure_timeline_row","_update_chronicle_signals","_update_civilization_layer","_update_knowledge_layer","_update_feedback_layer","_update_emergence_evidence_layer","_update_validation_calibration_layer","_update_lineage_tracking","_update_dynasty_stats","_update_demography_stats","_background_by_parity","_era_age"]
    def wrap(name,fn):
        def w(self,*a,**k):
            prof=getattr(self,"_observer_profile",None)
            if prof is None:
                prof={}; self._observer_profile=prof; self._observer_profile_updates=0
            t0=time.perf_counter()
            try:
                return fn(self,*a,**k)
            finally:
                dt=time.perf_counter()-t0
                r=prof.setdefault(name,{"calls":0,"total":0.0})
                r["calls"]+=1; r["total"]+=dt
                if name=="update":
                    self._observer_profile_updates+=1
                    every=int(os.environ.get("ART_EVO_OBSERVER_PROFILE_EVERY","200"))
                    if every>0 and self._observer_profile_updates%every==0:
                        print(_life_observer_profile_report(self))
        w._observer_profile_wrapped=True
        return w
    for n in methods:
        fn=getattr(LifeObserver,n,None)
        if fn is not None and not getattr(fn,"_observer_profile_wrapped",False):
            setattr(LifeObserver,n,wrap(n,fn))
    LifeObserver.profile_report=_life_observer_profile_report
    LifeObserver._observer_profiler_enabled=True

if os.environ.get("ART_EVO_OBSERVER_PROFILE","").lower() in ("1","true","yes","on"):
    _enable_life_observer_profiling()


def run_headless_observation(rule, rec, args, observer):
    """Run the canonical Observer engine without constructing presentation UI."""
    if int(args.max_ticks or 0) <= 0:
        raise SystemExit("--headless requires --max-ticks greater than zero")
    simulation_rule = rule
    if args.initial_state_mode == InitialStateMode.RANDOM_SEED.value:
        if args.experiment_seed is None:
            raise SystemExit("random_seed requires --experiment-seed")
        simulation_rule = copy.deepcopy(rule)
        simulation_rule.seed = int(args.experiment_seed)
    simulation = base.FieldSim(
        simulation_rule,
        width=args.field_width,
        height=args.field_height,
        topology=args.topology,
        boundary_mode=args.boundary_mode,
    )
    final_tick = 0
    output_root = (
        Path(args.run_output_dir).expanduser().resolve()
        if args.run_output_dir
        else Path(args.results_dir).expanduser().resolve()
    )
    try:
        observer.update(simulation.a, final_tick)
        for final_tick in range(1, int(args.max_ticks) + 1):
            simulation.step()
            observer.update(simulation.a, final_tick)
            if args.auto_stop and observer.collapse_tick is not None:
                break
        observer.write_outputs(
            output_root,
            rec,
            final_tick,
            write_log=args.log,
            write_passport=args.passport,
        )
    finally:
        observer.close_live_files()
    print(
        "ARCHON_HEADLESS_OBSERVER_JSON="
        + json.dumps({
            "mode": "canonical-headless",
            "rule_id": int(rec["rule_id"]),
            "run_id": str(observer.telemetry_run_id),
            "final_tick": int(final_tick),
            "samples": len(observer.samples),
            "events": len(observer.events),
        }, sort_keys=True)
    )


def main():
    parser = argparse.ArgumentParser(description="Universe Search Observer v5.1 Mutation Runs")
    parser.add_argument("results_dir", help="Results folder, e.g. universe_search_v20_results")
    parser.add_argument("selector", help="rule id, best, top, outlier, family, list")
    parser.add_argument("extra", nargs="?", help="top number or family name")
    parser.add_argument(
        "--rule-file",
        default=None,
        help="Load an explicit isolated rule JSON instead of the canonical Atlas payload.",
    )
    parser.add_argument(
        "--run-output-dir",
        default=None,
        help="Write this run's CSV, passport and evidence files into a dedicated directory.",
    )
    parser.add_argument(
        "--mutation-manifest",
        default=None,
        help="Optional mutation manifest path recorded in run provenance.",
    )

    parser.add_argument("--cell", type=int, default=8)
    parser.add_argument("--speed", type=int, default=2, help="Initial simulation steps per visual frame. Hotkeys: 1=x1, 2=x10, 3=x100, 4=x1000")
    parser.add_argument("--delay", type=int, default=30)

    parser.add_argument("--defect-threshold", type=float, default=0.18)
    parser.add_argument("--min-object-cells", type=int, default=8)
    parser.add_argument("--collapse-grace", type=int, default=250)
    parser.add_argument("--sample-every", type=int, default=1)
    parser.add_argument("--event-grace", type=int, default=5)
    parser.add_argument("--live-flush-every", type=int, default=100)

    parser.add_argument("--auto-stop", action="store_true")
    parser.add_argument(
        "--headless",
        action="store_true",
        help=(
            "Run canonical simulation, observation, telemetry and evidence "
            "without Tk UI. Requires --max-ticks."
        ),
    )
    parser.add_argument("--max-ticks", type=int, default=0)
    parser.add_argument(
        "--exit-at-max-ticks",
        action="store_true",
        help=(
            "At max_ticks, save final outputs, close telemetry, and exit "
            "automatically. Intended for queued experiment-plan runs."
        ),
    )
    parser.add_argument(
        "--autosave-every",
        type=int,
        default=0,
        help="Save passport and log every N ticks. Example: --autosave-every 50000",
    )
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--passport", action="store_true")
    parser.add_argument(
        "--evidence-framework",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable Evidence Framework v1 exports. Default: enabled.",
    )
    parser.add_argument(
        "--evidence-timeline",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Maintain evidence timeline across saved checkpoints. Default: enabled.",
    )
    parser.add_argument("--samples-csv", action="store_true")
    parser.add_argument("--events-csv", action="store_true")
    parser.add_argument("--pressure-timeline-csv", action="store_true",
                        help="Write a compact evolution pressure timeline CSV.")
    parser.add_argument("--pressure-timeline-every", type=int, default=100,
                        help="Write one pressure timeline row every N ticks. Default: 100.")
    parser.add_argument("--chronicle-csv", action="store_true",
                        help="Write readable evolution chronicle CSV with key events.")
    parser.add_argument(
        "--telemetry-sqlite",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write Telemetry to SQLite in parallel with CSV. Default: enabled.",
    )
    parser.add_argument(
        "--telemetry-db",
        default=None,
        help=(
            "SQLite database path. Default: "
            "<results_dir>/observation_logs/telemetry.sqlite"
        ),
    )

    # Experimental Conditions v1. These arguments establish provenance and
    # SQLite links only. World geometry changes are enabled in a later stage.
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument("--condition-id", default=None)
    parser.add_argument(
        "--experiment-role",
        choices=tuple(item.value for item in ExperimentRole),
        default=None,
    )
    parser.add_argument("--replicate-index", type=int, default=0)
    parser.add_argument(
        "--treatment-arm",
        default="",
        help="Stable treatment-arm identity, e.g. diffusion:I050",
    )
    parser.add_argument("--field-width", type=int, default=96)
    parser.add_argument("--field-height", type=int, default=64)
    parser.add_argument(
        "--topology",
        choices=tuple(item.value for item in Topology),
        default=Topology.TORUS.value,
    )
    parser.add_argument(
        "--boundary-mode",
        choices=tuple(item.value for item in BoundaryMode),
        default=BoundaryMode.WRAP.value,
    )
    parser.add_argument(
        "--initial-state-mode",
        choices=tuple(item.value for item in InitialStateMode),
        default=InitialStateMode.CANONICAL_SEED.value,
    )
    parser.add_argument("--experiment-seed", type=int, default=None)
    parser.add_argument("--saved-state-path", default=None)
    parser.add_argument("--parent-run-id", default=None)

    args = parser.parse_args()
    ensure_layout()

    results_dir = Path(args.results_dir).expanduser().resolve()
    if not results_dir.exists():
        raise SystemExit(
            f"Results folder not found: {results_dir}\n"
            f"Canonical ARCHON results folder: {SEARCH_RESULTS_DIR}"
        )
    rec = choose_record(results_dir, args.selector, args.extra)

    if args.rule_file:
        explicit_rule_path = Path(args.rule_file).expanduser().resolve()
        if not explicit_rule_path.exists():
            raise SystemExit(f"Explicit rule file not found: {explicit_rule_path}")
        try:
            explicit_payload = json.loads(
                explicit_rule_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise SystemExit(
                f"Could not read explicit rule file {explicit_rule_path}: {exc!r}"
            )
        if not isinstance(explicit_payload, dict):
            raise SystemExit(
                f"Explicit rule file must contain one JSON object: {explicit_rule_path}"
            )
        rec = dict(rec)
        rec["rule"] = explicit_payload
        rec["source"] = str(explicit_rule_path)
        rec["mutation_manifest"] = args.mutation_manifest
        if explicit_payload.get("rule_id") is not None:
            rec["rule_id"] = int(explicit_payload["rule_id"])
        print(f"[mutation-run] explicit rule: {explicit_rule_path}")
        if args.mutation_manifest:
            print(f"[mutation-run] manifest: {args.mutation_manifest}")

    rule = base.rule_from_dict(rec["rule"])

    print('[v4.2] Knowledge Layer: family knowledge, discoveries, transfer/loss, and civilization learning')
    print(f"Loaded rule {rec['rule_id']:05d} from {rec['source']}")
    print(f"Score: {rec.get('score')}")
    m = rec.get("metrics") or {}
    print(
        "Metrics:",
        f"memory={m.get('memory_trace_score')}",
        f"tracks={m.get('persistent_tracks')}",
        f"flow={m.get('ms_flow')}",
        f"rotation={m.get('ms_rotation_flow')}",
        f"crystal={m.get('crystal_order')}",
        f"quasi={m.get('quasi_particle_score')}",
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (
        Path(args.run_output_dir).expanduser().resolve()
        if args.run_output_dir
        else results_dir / "observation_logs"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    samples_path = out_dir / f"rule_{rec['rule_id']:05d}_{stamp}_samples.csv" if args.samples_csv else None
    events_path = out_dir / f"rule_{rec['rule_id']:05d}_{stamp}_events.csv" if args.events_csv else None
    pressure_timeline_path = out_dir / f"rule_{rec['rule_id']:05d}_{stamp}_pressure_timeline.csv" if args.pressure_timeline_csv else None
    chronicle_path = out_dir / f"rule_{rec['rule_id']:05d}_{stamp}_chronicle.csv" if args.chronicle_csv else None

    observer = LifeObserver(
        threshold=args.defect_threshold,
        min_object_cells=args.min_object_cells,
        collapse_grace=args.collapse_grace,
        sample_every=args.sample_every,
        event_grace=args.event_grace,
        live_flush_every=args.live_flush_every,
        samples_path=samples_path,
        events_path=events_path,
        pressure_timeline_path=pressure_timeline_path,
        pressure_timeline_every=args.pressure_timeline_every,
        chronicle_path=chronicle_path,
        topology=args.topology,
        boundary_mode=args.boundary_mode,
    )

    telemetry_db_path = (
        Path(args.telemetry_db).expanduser().resolve()
        if args.telemetry_db
        else out_dir / "telemetry.sqlite"
    )
    run_id = f"rule_{rec['rule_id']:05d}_{stamp}"

    experiment_fields = (
        args.experiment_id,
        args.condition_id,
        args.experiment_role,
    )
    has_experiment_context = any(value is not None for value in experiment_fields)
    if has_experiment_context and not all(
        value is not None for value in experiment_fields
    ):
        raise SystemExit(
            "Experimental run requires --experiment-id, --condition-id, "
            "and --experiment-role together."
        )
    if args.replicate_index < 0:
        raise SystemExit("--replicate-index must be >= 0")
    if args.experiment_seed is not None and args.experiment_seed < 0:
        raise SystemExit("--experiment-seed must be >= 0")
    treatment_arm = str(args.treatment_arm or "").strip()
    if treatment_arm and args.experiment_role != ExperimentRole.TREATMENT.value:
        raise SystemExit("--treatment-arm requires --experiment-role treatment")

    experiment_repository = None
    experiment_condition = None
    experiment_metadata = {}

    if has_experiment_context:
        if not args.telemetry_sqlite:
            raise SystemExit(
                "Experimental runs require SQLite telemetry. "
                "Remove --no-telemetry-sqlite."
            )
        try:
            experiment_repository = ExperimentalConditionsRepository(
                telemetry_db_path
            )
            experiment_repository.get_experiment(args.experiment_id)
            experiment_condition = experiment_repository.get_condition(
                args.condition_id
            )
        except ExperimentalConditionsError as exc:
            raise SystemExit(f"Experimental context is invalid: {exc}") from exc

        requested_condition = {
            "field_width": int(args.field_width),
            "field_height": int(args.field_height),
            "topology": str(args.topology),
            "boundary_mode": str(args.boundary_mode),
            "initial_state_mode": str(args.initial_state_mode),
        }
        stored_condition = {
            "field_width": experiment_condition.field_width,
            "field_height": experiment_condition.field_height,
            "topology": experiment_condition.topology.value,
            "boundary_mode": experiment_condition.boundary_mode.value,
            "initial_state_mode": experiment_condition.initial_state_mode.value,
        }
        if requested_condition != stored_condition:
            raise SystemExit(
                "CLI condition parameters do not match the stored condition. "
                f"requested={requested_condition} stored={stored_condition}"
            )

        # Stage 1 only records provenance. Refuse unsupported environments
        # rather than silently pretending the simulation used them.
        supported_environment = (
            (
                stored_condition["topology"] == Topology.TORUS.value
                and stored_condition["boundary_mode"]
                == BoundaryMode.WRAP.value
            )
            or (
                stored_condition["topology"] == Topology.BOUNDED.value
                and stored_condition["boundary_mode"]
                == BoundaryMode.FIXED_DEAD.value
            )
        )
        if (
            not supported_environment
            or stored_condition["initial_state_mode"]
            not in {
                InitialStateMode.CANONICAL_SEED.value,
                InitialStateMode.RANDOM_SEED.value,
            }
        ):
            raise SystemExit(
                "Supported runtime environments are torus/wrap and "
                "bounded/fixed_dead with canonical_seed or random_seed."
            )
        if args.saved_state_path:
            raise SystemExit(
                "--saved-state-path is not active in integration v1."
            )

        experiment_metadata = {
            "experimental_context": {
                "experiment_id": args.experiment_id,
                "condition_id": args.condition_id,
                "role": args.experiment_role,
                "replicate_index": int(args.replicate_index),
                "field_width": experiment_condition.field_width,
                "field_height": experiment_condition.field_height,
                "topology": experiment_condition.topology.value,
                "boundary_mode": experiment_condition.boundary_mode.value,
                "initial_state_mode": (
                    experiment_condition.initial_state_mode.value
                ),
                "experiment_seed": args.experiment_seed,
                "parent_run_id": args.parent_run_id,
                "integration_stage": "initial_state_random_seed_v1",
            }
        }
        print(
            "[experiment] "
            f"experiment={args.experiment_id} "
            f"condition={args.condition_id} "
            f"role={args.experiment_role} "
            f"replicate={args.replicate_index}"
        )
        print(
            "[experiment] environment="
            f"{experiment_condition.field_width}x"
            f"{experiment_condition.field_height} "
            f"{experiment_condition.topology.value}/"
            f"{experiment_condition.boundary_mode.value} "
            f"{experiment_condition.initial_state_mode.value} "
            f"seed={args.experiment_seed} "
            "(initial state v1)"
        )

    observer.configure_observer_state_contract(
        world_id=f"rule_{rec['rule_id']:05d}",
        run_id=run_id,
        observer_version="5.0-scientific-ontology-stage1b",
    )

    observer.configure_telemetry(
        run_id=run_id,
        rule_id=int(rec["rule_id"]),
        world_id=f"rule_{rec['rule_id']:05d}",
        observer_version="5.0-telemetry-sqlite-v1",
        database_path=telemetry_db_path,
        source_path=rec.get("source"),
        run_metadata=experiment_metadata,
        enable_sqlite=args.telemetry_sqlite,
    )

    if has_experiment_context:
        try:
            experiment_run_id = f"ERUN-{run_id}"
            retry_of_queue_id = str(
                os.environ.get("ARCHON_OL2_RETRY_OF_QUEUE_ID") or ""
            ).strip()
            retry_context = (
                {
                    "source": "OL2_QUEUE_RETRY_CLONE",
                    "retry_of_queue_id": retry_of_queue_id,
                }
                if retry_of_queue_id
                else None
            )
            experiment_repository.link_run(
                experiment_run_id=experiment_run_id,
                experiment_id=args.experiment_id,
                run_id=run_id,
                condition_id=args.condition_id,
                rule_id=int(rec["rule_id"]),
                role=args.experiment_role,
                replicate_index=int(args.replicate_index),
                treatment_arm=treatment_arm,
                parent_run_id=args.parent_run_id,
                metadata={
                    "integration_stage": "observer_initial_state_random_seed_v1",
                    "experiment_seed": args.experiment_seed,
                    "treatment_arm": treatment_arm,
                    "source_path": rec.get("source"),
                },
                retry_context=retry_context,
            )
        except ExperimentalConditionsError as exc:
            # The run has just been registered, so a failed experimental link
            # must abort before simulation begins.
            raise SystemExit(
                f"Could not register experiment run link: {exc}"
            ) from exc
        print(
            "[experiment] linked "
            f"experiment_run_id={experiment_run_id} run_id={run_id}"
        )

    observer.configure_evidence_framework(
        rec=rec,
        results_dir=results_dir,
        run_id=run_id,
        observer_version="5.0-evidence-v1",
        enabled=args.evidence_framework,
        enable_timeline=args.evidence_timeline,
    )

    if args.headless:
        run_headless_observation(rule, rec, args, observer)
        return

    if tk is None:
        raise SystemExit("tkinter is not available.")

    root = tk.Tk()
    WorldViewer(root, rule, rec, args, observer)
    root.mainloop()


if __name__ == "__main__":
    main()
