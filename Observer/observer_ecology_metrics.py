#!/usr/bin/env python3
"""
Project ARCHON Observer v5.0 modular layer.

This module contains methods extracted verbatim from the v4.4.2 LifeObserver.
It deliberately preserves calculations and public method names.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from Universe_Search import universe_search_core as base


class ObserverEcologyMetricsMixin:
    def _recent_event_rates(self, tick: int):
            window_start = max(0, tick - self.event_window_ticks)
            split = merge = birth = death = 0
            for ev in self.events:
                if ev.get("tick", -1) < window_start:
                    continue
                t = str(ev.get("type", ""))
                if "split" in t:
                    split += 1
                if "merge" in t:
                    merge += 1
                if t == "birth" or t == "life-start":
                    birth += 1
                if t == "death" or t == "collapse":
                    death += 1
            scale = 1000.0 / max(1, min(self.event_window_ticks, max(1, tick)))
            return split * scale, merge * scale, birth * scale, death * scale

    def _update_population_history(self, tick: int, objects: int, total_living_mass: int, largest: int):
            point = {
                "tick": tick,
                "objects": objects,
                "mass": total_living_mass,
                "largest": largest,
            }
            self.population_history.append(point)

            if len(self.population_history) <= 1:
                return {
                    "history_delta_objects": 0,
                    "history_delta_mass": 0,
                    "history_delta_largest": 0,
                    "mass_growth_per_tick": 0.0,
                    "objects_growth_per_tick": 0.0,
                    "largest_growth_per_tick": 0.0,
                    "stability_index": 0.0,
                    "history_window": 0,
                }

            cutoff = tick - self.history_window_ticks
            base_point = self.population_history[0]
            for p in self.population_history:
                if p["tick"] >= cutoff:
                    base_point = p
                    break

            dt = max(1, tick - base_point["tick"])
            d_objects = objects - base_point["objects"]
            d_mass = total_living_mass - base_point["mass"]
            d_largest = largest - base_point["largest"]

            mass_growth = d_mass / dt
            objects_growth = d_objects / dt
            largest_growth = d_largest / dt

            # 1.0 = almost frozen / stable, 0.0 = turbulent.
            # Uses relative change of mass, object count and largest colony over the history window.
            mass_scale = max(1, max(total_living_mass, base_point["mass"]))
            object_scale = max(1, max(objects, base_point["objects"]))
            largest_scale = max(1, max(largest, base_point["largest"]))
            relative_motion = (
                abs(d_mass) / mass_scale +
                abs(d_objects) / object_scale +
                abs(d_largest) / largest_scale
            ) / 3.0
            stability = max(0.0, min(1.0, 1.0 - relative_motion))

            return {
                "history_delta_objects": d_objects,
                "history_delta_mass": d_mass,
                "history_delta_largest": d_largest,
                "mass_growth_per_tick": mass_growth,
                "objects_growth_per_tick": objects_growth,
                "largest_growth_per_tick": largest_growth,
                "stability_index": stability,
                "history_window": dt,
            }

    def _ecosystem_phase(self, history, alive: bool):
            if self.collapse_tick is not None:
                return "COLLAPSED"

            if not alive:
                return "SEED"

            dt = history.get("history_window", 0)
            if dt < self.phase_min_window:
                return "WARMUP"

            d_objects = history.get("history_delta_objects", 0)
            d_mass = history.get("history_delta_mass", 0)
            d_largest = history.get("history_delta_largest", 0)
            stability = history.get("stability_index", 0.0)

            # Adaptive thresholds: enough to ignore tiny flicker, but not blind to colony dynamics.
            mass_threshold = max(20, int(abs(self.peak_total_living_mass) * 0.08))
            object_threshold = max(3, int(max(1, self.peak_objects) * 0.15))
            largest_threshold = max(15, int(max(1, self.peak_largest) * 0.10))

            if d_mass <= -mass_threshold * 2 and d_largest <= -largest_threshold:
                if d_objects >= object_threshold:
                    return "FRAGMENTATION"
                return "COLLAPSE"

            if d_mass >= mass_threshold and d_objects >= object_threshold:
                return "EXPANSION"

            if d_mass <= -mass_threshold and d_objects >= object_threshold:
                return "FRAGMENTATION"

            if d_mass >= mass_threshold and d_objects <= -object_threshold:
                return "MERGING"

            if abs(d_mass) <= mass_threshold and abs(d_objects) <= object_threshold and stability >= 0.80:
                return "STABLE"

            if d_largest <= -largest_threshold and d_objects > 0:
                return "FRAGMENTATION"

            if d_largest >= largest_threshold and d_objects < 0:
                return "MERGING"

            return "REORGANIZING"

    def _evolution_pressure(self, alive: bool, ecosystem_health: float, fragmentation_index: float, dominance_ratio: float,
                                history: dict, demo: dict, split_rate_1000: float, merge_rate_1000: float):
            # Stress rises when the world fragments, loses mass, has high death pressure, or becomes too dominated by one family.
            growth = float(history.get("mass_growth_per_tick", 0.0) or 0.0)
            stability = float(history.get("stability_index", 0.0) or 0.0)
            death = float(demo.get("demo_death_rate_1000", 0.0) or 0.0)
            birth = float(demo.get("demo_birth_rate_1000", 0.0) or 0.0)
            survival = float(demo.get("demo_survival_ratio", 0.0) or 0.0)
            replacement = float(demo.get("demo_replacement", 0.0) or 0.0)

            frag_stress = min(1.0, fragmentation_index * 4.0)
            death_stress = min(1.0, death / 120.0)
            loss_stress = min(1.0, max(0.0, -growth) / 2.0)
            dominance_stress = max(0.0, dominance_ratio - 0.72) / 0.28 if dominance_ratio > 0.72 else 0.0
            instability_stress = 1.0 - stability

            contrib = {
                "F": 0.30 * frag_stress,
                "D": 0.25 * death_stress,
                "L": 0.20 * loss_stress,
                "I": 0.15 * instability_stress,
                "M": 0.10 * dominance_stress,
            }

            raw_stress = sum(contrib.values())
            stress = max(0.0, min(1.0, raw_stress))

            # Percent breakdown of raw stress sources. If stress is tiny, keep it readable and zeroed.
            denom = raw_stress if raw_stress > 1e-9 else 1.0
            src_pct = {k: max(0.0, min(100.0, v / denom * 100.0)) for k, v in contrib.items()}
            cause_key = max(contrib, key=contrib.get) if raw_stress > 1e-9 else "N"
            cause_name = {
                "F": "FRAG",
                "D": "DEATH",
                "L": "LOSS",
                "I": "INST",
                "M": "MONO",
                "N": "NONE",
            }.get(cause_key, "NONE")

            reproduction = min(1.0, birth / 180.0)
            recovery = min(1.0, max(0.0, growth) / 2.0)
            replacement_ok = min(1.0, replacement / 2.0)
            split_merge_balance = 1.0 - min(1.0, abs(split_rate_1000 - merge_rate_1000) / 180.0)

            adapt = max(0.0, min(1.0,
                0.25 * ecosystem_health +
                0.25 * survival +
                0.20 * replacement_ok +
                0.15 * recovery +
                0.15 * reproduction
            ))

            pressure = max(0.0, min(1.0, stress * (1.0 - 0.45 * adapt)))
            extinction_risk = max(0.0, min(1.0,
                0.55 * stress +
                0.30 * (1.0 - survival) +
                0.15 * (1.0 - ecosystem_health)
            ))

            if not alive:
                phase = "SEED"
            elif pressure >= 0.70:
                phase = "CRISIS"
            elif stress >= 0.55 and adapt >= 0.55:
                phase = "ADAPT"
            elif birth > death * 1.6 and growth > 0:
                phase = "BOOM"
            elif death > birth * 1.2 or growth < -1.0:
                phase = "DECLINE"
            elif adapt >= 0.70 and stress < 0.35:
                phase = "FIT"
            else:
                phase = "TENSE"

            line = f"{phase} stress={stress:.2f} adapt={adapt:.2f} press={pressure:.2f} rec={recovery:.2f} risk={extinction_risk:.2f}"
            source_line = (
                f"SRC F{src_pct['F']:.0f} D{src_pct['D']:.0f} L{src_pct['L']:.0f} "
                f"I{src_pct['I']:.0f} M{src_pct['M']:.0f} cause={cause_name}"
            )

            return {
                "evo_stress": stress,
                "evo_adapt": adapt,
                "evo_pressure": pressure,
                "evo_recovery": recovery,
                "evo_extinction_risk": extinction_risk,
                "evo_phase": phase,
                "evolution_line": line,
                "evo_src_frag_pct": src_pct["F"],
                "evo_src_death_pct": src_pct["D"],
                "evo_src_loss_pct": src_pct["L"],
                "evo_src_inst_pct": src_pct["I"],
                "evo_src_dom_pct": src_pct["M"],
                "evo_cause": cause_name,
                "evo_source_line": source_line,
            }

    def _growth_phase(self, tick: int, alive: bool, total_living_mass: int, ecosystem_health: float, mass_delta: int, split_rate: float, merge_rate: float):
            if self.collapse_tick is not None:
                return "collapsed"
            if not alive or total_living_mass <= 0:
                return "seed"
            if tick < 500:
                return "birth"
            if mass_delta > 5 or split_rate > merge_rate + 1.0:
                return "expanding"
            if ecosystem_health >= 0.75 and abs(mass_delta) <= 5:
                return "mature"
            if ecosystem_health >= 0.45:
                return "reorganizing"
            return "declining"

    def _colony_size_distribution(self, sizes):
            # Buckets are intentionally simple and human-readable:
            # small  = minimal stable fragments
            # medium = real local colonies
            # large  = dominant city/continent chunks
            small = sum(1 for s in sizes if 8 <= s < 15)
            medium = sum(1 for s in sizes if 15 <= s < 40)
            large = sum(1 for s in sizes if s >= 40)

            top3_mass = sum(sizes[:3])
            top5_mass = sum(sizes[:5])
            total = sum(sizes)
            dominance_ratio = (sizes[0] / total) if sizes and total else 0.0
            top_sizes = list(sizes[:10])

            return {
                "small_colonies": small,
                "medium_colonies": medium,
                "large_colonies": large,
                "top3_mass": top3_mass,
                "top5_mass": top5_mass,
                "dominance_ratio": dominance_ratio,
                "top_sizes": top_sizes,
            }

