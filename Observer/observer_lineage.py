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


class ObserverLineageMixin:
    def _torus_distance_xy(self, ax, ay, bx, by):
            w, h = base.W, base.H
            dx = abs(ax - bx)
            dy = abs(ay - by)
            dx = min(dx, w - dx)
            dy = min(dy, h - dy)
            return math.sqrt(dx * dx + dy * dy)

    def _ensure_family_stats(self, family_id: int, tick: int):
            stats = self.family_stats.get(family_id)
            if stats is None:
                stats = {
                    "family_id": family_id,
                    "birth_tick": tick,
                    "born": 0,
                    "dead": 0,
                    "living": 0,
                    "peak_living": 0,
                    "max_generation": 0,
                    "largest_colony": 0,
                    "mass": 0,
                    "largest_mass": 0,
                }
                self.family_stats[family_id] = stats
            return stats

    def _update_dynasty_stats(self, tick: int, total_living_mass: int):
            # Reset live counters, then rebuild from active tracks.
            for stats in self.family_stats.values():
                stats["living"] = 0
                stats["mass"] = 0
                stats["max_generation"] = 0
                stats["largest_colony"] = 0

            active_tracks = [
                t for t in self.tracks.values()
                if t.get("alive", False) and tick - t.get("last_seen", tick) <= self.track_missing_grace
            ]

            for t in active_tracks:
                fid = t["family_id"]
                stats = self._ensure_family_stats(fid, t.get("birth_tick", tick))
                stats["living"] += 1
                stats["mass"] += int(t.get("size", 0))
                stats["max_generation"] = max(stats["max_generation"], int(t.get("generation", 0)))
                stats["largest_colony"] = max(stats["largest_colony"], int(t.get("size", 0)))
                stats["largest_mass"] = max(stats.get("largest_mass", 0), stats["mass"])

            for stats in self.family_stats.values():
                stats["peak_living"] = max(stats.get("peak_living", 0), stats.get("living", 0))

            if not self.family_stats:
                return {
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
                }

            leader = max(
                self.family_stats.values(),
                key=lambda s: (s.get("mass", 0), s.get("living", 0), s.get("born", 0))
            )

            age = max(1, tick - leader.get("birth_tick", tick))
            born = leader.get("born", 0)
            dead = leader.get("dead", 0)
            living = leader.get("living", 0)
            mass = leader.get("mass", 0)

            dominance = mass / max(1, total_living_mass)
            survival = living / max(1, born)
            turnover = (born + dead) / age * 1000.0
            birth_rate = born / age * 1000.0
            death_rate = dead / age * 1000.0

            self.dynasty_leader_id = leader["family_id"]
            self.dynasty_line = (
                f"F{leader['family_id']} age={age} born={born} live={living} dead={dead} "
                f"peak={leader.get('peak_living', 0)} dom={dominance:.2f} surv={survival:.2f} "
                f"turn={turnover:.1f}/k gen={leader.get('max_generation', 0)} mass={mass}"
            )

            return {
                "dynasty_leader_id": leader["family_id"],
                "dynasty_line": self.dynasty_line,
                "dynasty_age": age,
                "dynasty_born": born,
                "dynasty_living": living,
                "dynasty_dead": dead,
                "dynasty_peak_living": leader.get("peak_living", 0),
                "dynasty_dominance": dominance,
                "dynasty_survival": survival,
                "dynasty_turnover": turnover,
                "dynasty_birth_rate": birth_rate,
                "dynasty_death_rate": death_rate,
                "dynasty_max_generation": leader.get("max_generation", 0),
                "dynasty_largest_colony": leader.get("largest_colony", 0),
                "dynasty_mass": mass,
            }

    def _update_demography_stats(self, tick: int):
            active_tracks = [
                t for t in self.tracks.values()
                if t.get("alive", False) and tick - t.get("last_seen", tick) <= self.track_missing_grace
            ]
            alive = len(active_tracks)
            born = self.total_colonies_born
            dead = self.total_colonies_dead
            age_base = max(1, tick - (self.birth_tick or 0))

            mean_life = sum(self.colony_lifetimes) / max(1, len(self.colony_lifetimes))
            birth_rate = born / age_base * 1000.0
            death_rate = dead / age_base * 1000.0
            turnover = (born + dead) / age_base * 1000.0
            replacement = born / max(1, dead)
            survival = alive / max(1, born)

            self.demography_line = (
                f"born={born} dead={dead} alive={alive} life={mean_life:.1f}/{self.max_colony_lifetime} "
                f"b/d={birth_rate:.1f}/{death_rate:.1f}/k repl={replacement:.2f} surv={survival:.2f}"
            )

            return {
                "demo_born_total": born,
                "demo_dead_total": dead,
                "demo_alive_tracked": alive,
                "demo_mean_life": mean_life,
                "demo_max_life": self.max_colony_lifetime,
                "demo_birth_rate_1000": birth_rate,
                "demo_death_rate_1000": death_rate,
                "demo_turnover_1000": turnover,
                "demo_replacement": replacement,
                "demo_survival_ratio": survival,
                "demography_line": self.demography_line,
            }

    def _update_lineage_tracking(self, component_records, tick: int):
            previous = {
                tid: dict(track)
                for tid, track in self.tracks.items()
                if tick - track.get("last_seen", tick) <= self.track_missing_grace
            }

            assigned = []
            used_tracks = set()
            new_colonies = 0

            for comp in component_records:
                best_tid = None
                best_dist = None

                for tid, track in previous.items():
                    if tid in used_tracks:
                        continue
                    dist = self._torus_distance_xy(comp["cx"], comp["cy"], track["cx"], track["cy"])
                    if best_dist is None or dist < best_dist:
                        best_dist = dist
                        best_tid = tid

                if best_tid is not None and best_dist <= self.track_match_radius:
                    track = self.tracks[best_tid]
                    track.update({
                        "cx": comp["cx"],
                        "cy": comp["cy"],
                        "size": comp["size"],
                        "last_seen": tick,
                        "alive": True,
                    })
                    used_tracks.add(best_tid)
                    assigned.append(best_tid)
                    continue

                parent_id = None
                parent_dist = None
                for tid, track in previous.items():
                    dist = self._torus_distance_xy(comp["cx"], comp["cy"], track["cx"], track["cy"])
                    if parent_dist is None or dist < parent_dist:
                        parent_dist = dist
                        parent_id = tid

                if parent_id is not None and parent_dist <= self.offspring_radius:
                    parent = previous[parent_id]
                    family_id = parent["family_id"]
                    generation = parent.get("generation", 0) + 1
                else:
                    family_id = self.next_family_id
                    self.next_family_id += 1
                    generation = 0

                colony_id = self.next_colony_id
                self.next_colony_id += 1
                self.tracks[colony_id] = {
                    "id": colony_id,
                    "family_id": family_id,
                    "parent_id": parent_id,
                    "generation": generation,
                    "birth_tick": tick,
                    "last_seen": tick,
                    "cx": comp["cx"],
                    "cy": comp["cy"],
                    "size": comp["size"],
                    "alive": True,
                }
                new_colonies += 1
                assigned.append(colony_id)

                stats = self._ensure_family_stats(family_id, tick)
                stats["born"] += 1
                stats["largest_colony"] = max(stats.get("largest_colony", 0), comp["size"])
                self.total_colonies_born += 1

                if parent_id is None:
                    self.add_event(tick, "family-founded", f"family={family_id} colony={colony_id} size={comp['size']}")
                else:
                    self.add_event(tick, "colony-offspring", f"colony={colony_id} from={parent_id} family={family_id} gen={generation} size={comp['size']}")

            for tid, track in list(self.tracks.items()):
                if tid not in assigned and tick - track.get("last_seen", tick) > self.track_missing_grace:
                    if track.get("alive", True):
                        track["alive"] = False
                        self.extinct_colonies_total += 1
                        stats = self._ensure_family_stats(track["family_id"], track.get("birth_tick", tick))
                        stats["dead"] += 1
                        self.total_colonies_dead += 1
                        life = max(0, tick - int(track.get("birth_tick", tick)))
                        self.colony_lifetimes.append(life)
                        self.max_colony_lifetime = max(self.max_colony_lifetime, life)
                        self.add_event(tick, "colony-extinct", f"colony={tid} family={track['family_id']} age={life}")

            active_tracks = [
                t for t in self.tracks.values()
                if t.get("alive", False) and tick - t.get("last_seen", tick) <= self.track_missing_grace
            ]

            family_counts = {}
            family_oldest_birth = {}
            for t in active_tracks:
                fid = t["family_id"]
                family_counts[fid] = family_counts.get(fid, 0) + 1
                family_oldest_birth[fid] = min(family_oldest_birth.get(fid, t["birth_tick"]), t["birth_tick"])

            ever_families = {t["family_id"] for t in self.tracks.values()}
            active_families_set = set(family_counts)
            self.extinct_families_total = len(ever_families - active_families_set)

            self.active_families = len(active_families_set)
            self.active_colonies_tracked = len(active_tracks)
            self.new_colonies_this_tick = new_colonies
            self.largest_family_size = max(family_counts.values()) if family_counts else 0
            self.deepest_generation = max((t.get("generation", 0) for t in active_tracks), default=0)
            self.oldest_lineage_age = max((tick - b for b in family_oldest_birth.values()), default=0)

            top_families = sorted(family_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
            self.lineage_summary = ",".join(f"F{fid}:{count}" for fid, count in top_families)

            return {
                "active_families": self.active_families,
                "active_colonies_tracked": self.active_colonies_tracked,
                "new_colonies_this_tick": self.new_colonies_this_tick,
                "extinct_colonies_total": self.extinct_colonies_total,
                "extinct_families_total": self.extinct_families_total,
                "largest_family_size": self.largest_family_size,
                "deepest_generation": self.deepest_generation,
                "oldest_lineage_age": self.oldest_lineage_age,
                "lineage_summary": self.lineage_summary,
            }

    def _center_distance(self, a, b):
            if a is None or b is None:
                return 0.0
            ax, ay = a
            bx, by = b
            if ax is None or bx is None:
                return 0.0
            w, h = base.W, base.H
            dx = abs(ax - bx)
            dy = abs(ay - by)
            dx = min(dx, w - dx)
            dy = min(dy, h - dy)
            return math.sqrt(dx * dx + dy * dy)

    def _track_object_events(self, tick, objects, largest):
            if self._stable_objects is None:
                self._stable_objects = objects
                self._stable_since = tick
                self._prev_objects = objects
                if objects > 0:
                    self.add_event(tick, "birth", f"first detected objects={objects}, largest={largest}")
                return

            if objects != self._prev_objects:
                self._prev_objects = objects
                self._stable_since = tick
                return

            if tick - (self._stable_since or tick) < self.event_grace:
                return

            if objects != self._stable_objects:
                old = self._stable_objects
                new = objects
                if old == 0 and new > 0:
                    self.add_event(tick, "birth", f"objects {old}->{new}, largest={largest}")
                elif old > 0 and new == 0:
                    self.add_event(tick, "death", f"objects {old}->0")
                elif new > old:
                    self.add_event(tick, "split/birth", f"objects {old}->{new}, largest={largest}")
                elif new < old:
                    self.add_event(tick, "merge/death", f"objects {old}->{new}, largest={largest}")
                self._stable_objects = objects

