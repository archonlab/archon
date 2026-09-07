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


class ObserverScientificLayersMixin:
    @staticmethod
    def _clamp01(value):
            try:
                return max(0.0, min(1.0, float(value)))
            except Exception:
                return 0.0

    def _civilization_stage_name(self, score: float, cities: int, tech: float, trade: float, culture: float, conflict: float, collapse_risk: float):
            if cities <= 0 or score < 0.12:
                return "NONE"
            if collapse_risk >= 0.72 and score >= 0.20:
                return "COLLAPSE"
            if score >= 0.78 and tech >= 0.68 and culture >= 0.55:
                return "SPACE_AGE" if trade >= 0.55 and conflict < 0.45 else "EMPIRE"
            if score >= 0.58 and cities >= 3:
                return "EMPIRE" if conflict >= 0.42 else "CIVILIZATION"
            if score >= 0.38 and cities >= 2:
                return "CITY_STATES"
            if score >= 0.22:
                return "PROTO_CITY"
            return "TRIBE"

    def _update_civilization_layer(self, tick: int, component_records, sizes, total_living_mass: int, largest: int,
                                       colony_dist: dict, history: dict, lineage: dict, dynasty: dict, demo: dict,
                                       evo: dict, growth_phase: str, ecosystem_health: float, fragmentation_index: float):
            # City = a large enough stable colony. Threshold adapts to world size, so small worlds can still urbanize.
            field_cells = max(1, base.W * base.H)
            city_threshold = max(40, int(field_cells * 0.012), int(max(1, self.peak_largest) * 0.20))
            city_records = [r for r in component_records if int(r.get("size", 0)) >= city_threshold]
            cities = len(city_records)
            capital_size = max((int(r.get("size", 0)) for r in city_records), default=0)
            urban_mass = sum(int(r.get("size", 0)) for r in city_records)
            urbanization = urban_mass / max(1, total_living_mass)

            active_families = int(lineage.get("active_families", 0) or 0)
            active_colonies = int(lineage.get("active_colonies_tracked", 0) or 0)
            stability = float(history.get("stability_index", 0.0) or 0.0)
            mass_growth = float(history.get("mass_growth_per_tick", 0.0) or 0.0)
            object_growth = float(history.get("objects_growth_per_tick", 0.0) or 0.0)
            dom = float(dynasty.get("dynasty_dominance", 0.0) or 0.0)
            pressure = float(evo.get("evo_pressure", 0.0) or 0.0)
            risk = float(evo.get("evo_extinction_risk", 0.0) or 0.0)
            adapt = float(evo.get("evo_adapt", 0.0) or 0.0)
            death_rate = float(demo.get("demo_death_rate_1000", 0.0) or 0.0)
            birth_rate = float(demo.get("demo_birth_rate_1000", 0.0) or 0.0)
            replacement = float(demo.get("demo_replacement", 0.0) or 0.0)
            survival = float(demo.get("demo_survival_ratio", 0.0) or 0.0)

            diversity = self._clamp01(active_families / 8.0)
            network_density = self._clamp01(active_colonies / 24.0)
            city_density = self._clamp01(cities / 6.0)
            city_mass_score = self._clamp01(urban_mass / max(1, int(field_cells * 0.18)))
            capital_score = self._clamp01(capital_size / max(1, int(field_cells * 0.10)))
            growth_score = self._clamp01((mass_growth + 2.0) / 8.0)
            replacement_score = self._clamp01(replacement / 2.2)
            survival_score = self._clamp01(survival * 2.2)

            trade_index = self._clamp01(0.35 * network_density + 0.25 * diversity + 0.20 * city_density + 0.20 * stability)
            conflict_index = self._clamp01(0.35 * pressure + 0.25 * risk + 0.20 * max(0.0, 1.0 - survival_score) + 0.20 * max(0.0, death_rate / 120.0))
            cohesion = self._clamp01(0.40 * stability + 0.25 * min(dom, 0.75) / 0.75 + 0.20 * survival_score + 0.15 * max(0.0, 1.0 - fragmentation_index * 18.0))
            specialization = self._clamp01(0.30 * city_density + 0.25 * diversity + 0.20 * network_density + 0.15 * self._clamp01(abs(object_growth) / 0.08) + 0.10 * urbanization)
            tech_index = self._clamp01(0.28 * adapt + 0.22 * stability + 0.18 * trade_index + 0.16 * specialization + 0.16 * city_mass_score)
            culture_index = self._clamp01(0.30 * cohesion + 0.25 * diversity + 0.20 * stability + 0.15 * min(1.0, max(0, tick - (self.birth_tick or tick)) / 8000.0) + 0.10 * city_density)
            collapse_risk = self._clamp01(0.42 * risk + 0.25 * pressure + 0.18 * max(0.0, 1.0 - cohesion) + 0.15 * max(0.0, 1.0 - ecosystem_health))

            civ_score = self._clamp01(
                0.18 * city_mass_score +
                0.14 * capital_score +
                0.14 * trade_index +
                0.14 * tech_index +
                0.13 * culture_index +
                0.12 * cohesion +
                0.09 * diversity +
                0.06 * growth_score
            )
            if cities == 0:
                civ_score *= 0.35
            if conflict_index >= 0.65:
                civ_score *= 0.88

            raw_stage = self._civilization_stage_name(civ_score, cities, tech_index, trade_index, culture_index, conflict_index, collapse_risk)

            # Stage smoothing: civilization should not flicker because one city breathes for a tick.
            if self.prev_civilization_stage is None:
                stage = raw_stage
                self.prev_civilization_stage = stage
            elif raw_stage != self.prev_civilization_stage:
                if self.civilization_pending_stage != raw_stage:
                    self.civilization_pending_stage = raw_stage
                    self.civilization_pending_since = tick
                pending_age = tick - (self.civilization_pending_since if self.civilization_pending_since is not None else tick)
                force = raw_stage in ("COLLAPSE", "SPACE_AGE")
                if force or pending_age >= self.civilization_stage_min_duration:
                    old = self.prev_civilization_stage
                    stage = raw_stage
                    self.prev_civilization_stage = stage
                    self.civilization_pending_stage = None
                    self.civilization_pending_since = None
                    self.civilization_event_counts["stage_change"] = self.civilization_event_counts.get("stage_change", 0) + 1
                    self.civilization_last_event = f"{tick}: {old}->{stage} score={civ_score:.3f} cities={cities} tech={tech_index:.3f}"
                    self._chronicle(
                        tick, "CIV_STAGE_CHANGE", phase=stage, pressure=pressure, risk=collapse_risk,
                        details=f"{old}->{stage} score={civ_score:.3f} cities={cities} trade={trade_index:.3f} tech={tech_index:.3f} conflict={conflict_index:.3f}",
                        severity="HISTORIC" if stage in ("SPACE_AGE", "COLLAPSE") else "MAJOR",
                    )
                else:
                    stage = self.prev_civilization_stage
            else:
                stage = self.prev_civilization_stage
                self.civilization_pending_stage = None
                self.civilization_pending_since = None

            if stage != "NONE" and self.civilization_started_tick is None:
                self.civilization_started_tick = tick
                self.civilization_count += 1
                self.civilization_event_counts["birth"] = self.civilization_event_counts.get("birth", 0) + 1
                self.civilization_last_event = f"{tick}: civilization birth stage={stage} cities={cities}"
                self._chronicle(
                    tick, "CIVILIZATION_BIRTH", phase=stage, pressure=pressure, risk=collapse_risk,
                    details=f"stage={stage} score={civ_score:.3f} cities={cities} urban={urbanization:.3f} families={active_families}",
                    severity="HISTORIC",
                )
            elif stage == "NONE" and self.civilization_started_tick is not None and civ_score < 0.08:
                age = tick - self.civilization_started_tick
                self.civilization_event_counts["fall"] = self.civilization_event_counts.get("fall", 0) + 1
                self.civilization_last_event = f"{tick}: civilization fall age={age} peak={self.civilization_peak_score:.3f}"
                self._chronicle(
                    tick, "CIVILIZATION_FALL", phase=stage, pressure=pressure, risk=collapse_risk,
                    details=f"age={age} peak_score={self.civilization_peak_score:.3f} peak_tick={self.civilization_peak_tick}",
                    severity="HISTORIC",
                )
                self.civilization_started_tick = None

            if civ_score > self.civilization_peak_score:
                old_peak = self.civilization_peak_score
                self.civilization_peak_score = civ_score
                self.civilization_peak_tick = tick
                if civ_score >= 0.50 and civ_score - old_peak >= 0.08:
                    self.civilization_event_counts["renaissance"] = self.civilization_event_counts.get("renaissance", 0) + 1
                    self._chronicle(
                        tick, "CIV_RENAISSANCE", phase=stage, pressure=pressure, risk=collapse_risk,
                        details=f"score={civ_score:.3f} cities={cities} tech={tech_index:.3f} culture={culture_index:.3f}",
                        severity="MAJOR",
                    )

            civ_age = 0 if self.civilization_started_tick is None else max(0, tick - self.civilization_started_tick)
            self.civilization_stage = stage
            self.civilization_line = (
                f"CIV {stage} score={civ_score:.2f} age={civ_age} cities={cities} cap={capital_size} "
                f"urban={urbanization:.2f} trade={trade_index:.2f} tech={tech_index:.2f} "
                f"culture={culture_index:.2f} conflict={conflict_index:.2f} risk={collapse_risk:.2f}"
            )
            civ = {
                "civ_stage": stage,
                "civ_score": civ_score,
                "civ_age": civ_age,
                "civ_cities": cities,
                "civ_capital_size": capital_size,
                "civ_urban_mass": urban_mass,
                "civ_urbanization": urbanization,
                "civ_trade_index": trade_index,
                "civ_conflict_index": conflict_index,
                "civ_cohesion": cohesion,
                "civ_specialization": specialization,
                "civ_tech_index": tech_index,
                "civ_culture_index": culture_index,
                "civ_collapse_risk": collapse_risk,
                "civ_line": self.civilization_line,
                "civ_peak_score": self.civilization_peak_score,
                "civ_peak_tick": self.civilization_peak_tick,
                "civ_count": self.civilization_count,
            }
            self.civilization_history.append({"tick": tick, **civ})
            return civ

    def _discovery_name(self, score: float, axis_avg: dict, civ: dict):
            # Soft milestones. They are not "real tech" in the automaton, they are
            # labels for persistent information patterns that look like learning.
            if score >= 0.78 and axis_avg.get("memory", 0.0) >= 0.62 and axis_avg.get("efficiency", 0.0) >= 0.58:
                return "COMPUTATION"
            if score >= 0.68 and axis_avg.get("exploration", 0.0) >= 0.58:
                return "NAVIGATION"
            if score >= 0.58 and axis_avg.get("cooperation", 0.0) >= 0.52 and civ.get("civ_cities", 0) >= 2:
                return "WRITING"
            if score >= 0.48 and axis_avg.get("efficiency", 0.0) >= 0.44:
                return "ENGINEERING"
            if score >= 0.38 and axis_avg.get("adaptation", 0.0) >= 0.36:
                return "MEDICINE"
            if score >= 0.28 and civ.get("civ_urbanization", 0.0) >= 0.20:
                return "AGRICULTURE"
            if score >= 0.18 and axis_avg.get("memory", 0.0) >= 0.16:
                return "ORAL_TRADITION"
            return None

    def _update_knowledge_layer(self, tick: int, civ: dict, lineage: dict, dynasty: dict, demo: dict, evo: dict,
                                    history: dict, growth_phase: str, ecosystem_health: float, fragmentation_index: float):
            active_tracks = [
                t for t in self.tracks.values()
                if t.get("alive", False) and tick - int(t.get("last_seen", tick)) <= self.track_missing_grace
            ]
            family_mass = {}
            family_count = {}
            family_age = {}
            family_gen = {}
            for t in active_tracks:
                fid = int(t.get("family_id", 0) or 0)
                family_mass[fid] = family_mass.get(fid, 0.0) + float(t.get("size", 0) or 0)
                family_count[fid] = family_count.get(fid, 0) + 1
                family_age[fid] = max(family_age.get(fid, 0), max(0, tick - int(t.get("birth_tick", tick))))
                family_gen[fid] = max(family_gen.get(fid, 0), int(t.get("generation", 0) or 0))

            # Decay unused/extinct family knowledge. The world forgets, but not instantly.
            active_fids = set(family_mass)
            for fid in list(self.family_knowledge):
                if fid not in active_fids:
                    for ax in self.knowledge_axes:
                        self.family_knowledge[fid][ax] *= 0.995
                    if max(self.family_knowledge[fid].values()) < 0.015:
                        del self.family_knowledge[fid]

            stability = float(history.get("stability_index", 0.0) or 0.0)
            mass_growth = float(history.get("mass_growth_per_tick", 0.0) or 0.0)
            object_growth = float(history.get("objects_growth_per_tick", 0.0) or 0.0)
            pressure = float(evo.get("evo_pressure", 0.0) or 0.0)
            risk = float(evo.get("evo_extinction_risk", 0.0) or 0.0)
            adapt = float(evo.get("evo_adapt", 0.0) or 0.0)
            trade = float(civ.get("civ_trade_index", 0.0) or 0.0)
            conflict = float(civ.get("civ_conflict_index", 0.0) or 0.0)
            cohesion = float(civ.get("civ_cohesion", 0.0) or 0.0)
            specialization = float(civ.get("civ_specialization", 0.0) or 0.0)
            urban = float(civ.get("civ_urbanization", 0.0) or 0.0)
            tech = float(civ.get("civ_tech_index", 0.0) or 0.0)
            culture = float(civ.get("civ_culture_index", 0.0) or 0.0)
            survival = float(demo.get("demo_survival_ratio", 0.0) or 0.0)
            replacement = float(demo.get("demo_replacement", 0.0) or 0.0)

            transfer = self._clamp01(0.42 * trade + 0.28 * cohesion + 0.18 * culture + 0.12 * specialization)
            loss = self._clamp01(0.38 * risk + 0.28 * conflict + 0.18 * pressure + 0.16 * max(0.0, 1.0 - ecosystem_health))

            total_mass = max(1.0, sum(family_mass.values()))
            weighted_before = {ax: 0.0 for ax in self.knowledge_axes}
            for fid, mass in family_mass.items():
                k = self.family_knowledge.setdefault(fid, {ax: 0.0 for ax in self.knowledge_axes})
                for ax in self.knowledge_axes:
                    weighted_before[ax] += k.get(ax, 0.0) * (mass / total_mass)

            for fid, mass in family_mass.items():
                k = self.family_knowledge.setdefault(fid, {ax: 0.0 for ax in self.knowledge_axes})
                mass_share = mass / total_mass
                age_score = self._clamp01(family_age.get(fid, 0) / 3500.0)
                gen_score = self._clamp01(family_gen.get(fid, 0) / 9.0)
                colony_score = self._clamp01(family_count.get(fid, 0) / 8.0)
                local_learning = self._clamp01(0.30 * age_score + 0.24 * gen_score + 0.20 * colony_score + 0.14 * mass_share + 0.12 * survival)

                impulses = {
                    "exploration": self._clamp01(0.36 * max(0.0, mass_growth) / 6.0 + 0.24 * max(0.0, object_growth) / 0.08 + 0.22 * trade + 0.18 * urban),
                    "cooperation": self._clamp01(0.34 * cohesion + 0.28 * trade + 0.20 * survival + 0.18 * culture),
                    "aggression": self._clamp01(0.45 * conflict + 0.30 * pressure + 0.15 * risk + 0.10 * max(0.0, 1.0 - cohesion)),
                    "efficiency": self._clamp01(0.30 * specialization + 0.25 * stability + 0.20 * urban + 0.15 * tech + 0.10 * replacement),
                    "adaptation": self._clamp01(0.36 * adapt + 0.22 * survival + 0.20 * max(0.0, 1.0 - risk) + 0.12 * stability + 0.10 * ecosystem_health),
                    "memory": self._clamp01(0.36 * age_score + 0.22 * gen_score + 0.20 * culture + 0.12 * stability + 0.10 * cohesion),
                }
                for ax in self.knowledge_axes:
                    incoming = weighted_before[ax] * transfer * 0.018
                    learning = impulses[ax] * (0.010 + 0.018 * local_learning)
                    forgetting = (self.knowledge_decay_base + 0.018 * loss) * (0.55 if ax == "memory" else 1.0)
                    k[ax] = self._clamp01(k.get(ax, 0.0) * (1.0 - forgetting) + learning + incoming)

            axis_avg = {ax: 0.0 for ax in self.knowledge_axes}
            dominant_family = None
            dominant_family_score = 0.0
            for fid, mass in family_mass.items():
                k = self.family_knowledge.get(fid, {})
                family_score = sum(k.get(ax, 0.0) for ax in self.knowledge_axes) / len(self.knowledge_axes)
                if family_score > dominant_family_score:
                    dominant_family_score = family_score
                    dominant_family = fid
                for ax in self.knowledge_axes:
                    axis_avg[ax] += k.get(ax, 0.0) * (mass / total_mass)

            knowledge_score = self._clamp01(
                0.18 * axis_avg["memory"] +
                0.17 * axis_avg["cooperation"] +
                0.17 * axis_avg["adaptation"] +
                0.16 * axis_avg["efficiency"] +
                0.14 * axis_avg["exploration"] +
                0.08 * axis_avg["aggression"] +
                0.10 * tech
            )
            if axis_avg["memory"] > self.knowledge_memory_peak:
                self.knowledge_memory_peak = axis_avg["memory"]
                self.knowledge_memory_peak_tick = tick
            dominant_axis = max(axis_avg.items(), key=lambda kv: kv[1])[0] if axis_avg else "none"

            if knowledge_score > self.knowledge_peak_score:
                old = self.knowledge_peak_score
                self.knowledge_peak_score = knowledge_score
                self.knowledge_peak_tick = tick
                if knowledge_score >= 0.32 and knowledge_score - old >= 0.07:
                    self.knowledge_event_counts["knowledge_bloom"] = self.knowledge_event_counts.get("knowledge_bloom", 0) + 1
                    self._chronicle(
                        tick, "KNOWLEDGE_BLOOM", family=dominant_family, phase=dominant_axis,
                        pressure=pressure, risk=loss,
                        details=f"score={knowledge_score:.3f} axis={dominant_axis} transfer={transfer:.3f} loss={loss:.3f}",
                        severity="MAJOR",
                    )

            discovery = self._discovery_name(knowledge_score, axis_avg, civ)
            if discovery and discovery not in self.knowledge_discoveries:
                self.knowledge_discoveries.add(discovery)
                self.knowledge_event_counts["discovery"] = self.knowledge_event_counts.get("discovery", 0) + 1
                self.knowledge_last_event = f"{tick}: {discovery} score={knowledge_score:.3f}"
                self._chronicle(
                    tick, "KNOWLEDGE_DISCOVERY", family=dominant_family, phase=discovery,
                    pressure=pressure, risk=loss,
                    details=f"{discovery} score={knowledge_score:.3f} dominant_axis={dominant_axis}",
                    severity="HISTORIC" if discovery in ("WRITING", "COMPUTATION") else "MAJOR",
                )

            if loss >= 0.66 and knowledge_score >= 0.20:
                self.knowledge_event_counts["knowledge_loss"] = self.knowledge_event_counts.get("knowledge_loss", 0) + 1
                if tick - self.chronicle_last_tick_by_event.get("KNOWLEDGE_LOSS", -10**9) > 700:
                    self._chronicle(
                        tick, "KNOWLEDGE_LOSS", family=dominant_family, phase=dominant_axis,
                        pressure=pressure, risk=loss,
                        details=f"score={knowledge_score:.3f} loss={loss:.3f} conflict={conflict:.3f} risk={risk:.3f}",
                        severity="CRITICAL" if loss >= 0.80 else "MAJOR",
                    )

            knowledge_age = 0 if self.birth_tick is None else max(0, tick - self.birth_tick)
            discoveries_text = ";".join(sorted(self.knowledge_discoveries))
            self.knowledge_line = (
                f"KNOW score={knowledge_score:.2f} peak={self.knowledge_peak_score:.2f} fam={len(family_mass)} "
                f"dom=F{dominant_family if dominant_family is not None else '-'} axis={dominant_axis} "
                f"E/C/A/G/F/M={axis_avg['exploration']:.2f}/{axis_avg['cooperation']:.2f}/{axis_avg['adaptation']:.2f}/"
                f"{axis_avg['aggression']:.2f}/{axis_avg['efficiency']:.2f}/{axis_avg['memory']:.2f} "
                f"xfer={transfer:.2f} loss={loss:.2f} discoveries={len(self.knowledge_discoveries)}"
            )
            know = {
                "knowledge_score": knowledge_score,
                "knowledge_peak_score": self.knowledge_peak_score,
                "knowledge_peak_tick": self.knowledge_peak_tick,
                "knowledge_age": knowledge_age,
                "knowledge_families": len(family_mass),
                "knowledge_dominant_family": dominant_family,
                "knowledge_dominant_axis": dominant_axis,
                "knowledge_exploration": axis_avg["exploration"],
                "knowledge_cooperation": axis_avg["cooperation"],
                "knowledge_aggression": axis_avg["aggression"],
                "knowledge_efficiency": axis_avg["efficiency"],
                "knowledge_adaptation": axis_avg["adaptation"],
                "knowledge_memory": axis_avg["memory"],
                "knowledge_memory_peak": self.knowledge_memory_peak,
                "knowledge_memory_peak_tick": self.knowledge_memory_peak_tick,
                "knowledge_transfer": transfer,
                "knowledge_loss": loss,
                "knowledge_discoveries": discoveries_text,
                "knowledge_event_counts": dict(self.knowledge_event_counts),
                "knowledge_line": self.knowledge_line,
                "knowledge_last_event": self.knowledge_last_event,
            }
            self.knowledge_history.append({"tick": tick, **know})
            return know

    def _feedback_regime_name(self, score: float, buffer: float, self_direction: float, risk: float):
            if score < 0.08:
                return "NONE"
            if risk >= 0.78 and buffer < 0.12:
                return "FEEDBACK_FAILURE"
            if score >= 0.55 and self_direction >= 0.45:
                return "SELF_REGULATING"
            if score >= 0.38 and buffer >= 0.22:
                return "ADAPTIVE_LOOP"
            if score >= 0.22:
                return "CULTURAL_FEEDBACK"
            return "WEAK_FEEDBACK"

    def _update_feedback_layer(self, tick: int, know: dict, civ: dict, evo: dict, demo: dict, history: dict,
                                   ecosystem_health: float, fragmentation_index: float):
            # Feedback metric v2 deliberately separates the measured response
            # of the world from the knowledge scaffold that may help explain
            # that response.  In v1, five of the six positive score terms were
            # built directly from the same knowledge axes used by KNOW.  That
            # made KNOW/FB coupling largely true by construction.
            exploration = float(know.get("knowledge_exploration", 0.0) or 0.0)
            cooperation = float(know.get("knowledge_cooperation", 0.0) or 0.0)
            aggression = float(know.get("knowledge_aggression", 0.0) or 0.0)
            efficiency = float(know.get("knowledge_efficiency", 0.0) or 0.0)
            adaptation = float(know.get("knowledge_adaptation", 0.0) or 0.0)
            memory = float(know.get("knowledge_memory", 0.0) or 0.0)
            knowledge_score = float(know.get("knowledge_score", 0.0) or 0.0)

            pressure = float(evo.get("evo_pressure", 0.0) or 0.0)
            risk = float(evo.get("evo_extinction_risk", 0.0) or 0.0)
            stress = float(evo.get("evo_stress", 0.0) or 0.0)
            evo_adapt = float(evo.get("evo_adapt", 0.0) or 0.0)
            evo_recovery = float(evo.get("evo_recovery", 0.0) or 0.0)
            survival = float(demo.get("demo_survival_ratio", 0.0) or 0.0)
            replacement = float(demo.get("demo_replacement", 0.0) or 0.0)
            stability = float(history.get("stability_index", 0.0) or 0.0)
            mass_growth = float(history.get("mass_growth_per_tick", 0.0) or 0.0)
            trade = float(civ.get("civ_trade_index", 0.0) or 0.0)
            cohesion = float(civ.get("civ_cohesion", 0.0) or 0.0)
            conflict = float(civ.get("civ_conflict_index", 0.0) or 0.0)
            culture = float(civ.get("civ_culture_index", 0.0) or 0.0)
            tech = float(civ.get("civ_tech_index", 0.0) or 0.0)

            knowledge_impact = self._clamp01(
                0.20 * adaptation + 0.18 * efficiency + 0.18 * cooperation +
                0.16 * memory + 0.12 * exploration + 0.08 * tech + 0.08 * culture
            )
            legacy_pressure_buffer = self._clamp01(
                0.34 * adaptation + 0.24 * efficiency + 0.20 * memory +
                0.14 * cooperation + 0.08 * max(0.0, 1.0 - conflict)
            )
            legacy_survival_bonus = self._clamp01(
                0.28 * cooperation + 0.24 * adaptation + 0.22 * efficiency +
                0.14 * memory + 0.12 * max(0.0, replacement)
            )
            legacy_expansion_bonus = self._clamp01(
                0.42 * exploration + 0.20 * aggression
                + 0.18 * trade + 0.20 * tech
            )
            legacy_aggression_cost = self._clamp01(
                0.55 * aggression + 0.25 * conflict + 0.20 * pressure
            )
            environment_impact = self._clamp01(
                0.26 * survival + 0.24 * stability + 0.18 * ecosystem_health +
                0.14 * max(0.0, mass_growth) / 6.0 + 0.10 * trade + 0.08 * cohesion
            )

            # Outcome/response terms below do not read KNOW or any knowledge
            # axis.  They are still observational proxies, not proof of a
            # causal loop; feedback_response_opportunity records whether the
            # world was challenged enough for response evidence to exist.
            response_capacity = self._clamp01(
                0.26 * evo_adapt
                + 0.22 * evo_recovery
                + 0.18 * survival
                + 0.14 * stability
                + 0.10 * ecosystem_health
                + 0.10 * max(0.0, replacement)
            )
            response_opportunity = self._clamp01(
                max(pressure, stress, risk)
            )
            observed_response = self._clamp01(
                response_opportunity
                * (
                    0.34 * evo_recovery
                    + 0.26 * evo_adapt
                    + 0.20 * survival
                    + 0.12 * stability
                    + 0.08 * ecosystem_health
                )
            )
            pressure_buffer = response_capacity
            survival_bonus = self._clamp01(
                0.34 * survival
                + 0.24 * evo_recovery
                + 0.18 * stability
                + 0.14 * max(0.0, replacement)
                + 0.10 * max(0.0, 1.0 - risk)
            )
            expansion_bonus = self._clamp01(
                0.34 * max(0.0, mass_growth) / 6.0
                + 0.26 * trade
                + 0.22 * tech
                + 0.18 * cohesion
            )
            aggression_cost = self._clamp01(
                0.42 * conflict + 0.30 * pressure + 0.28 * stress
            )
            self_direction = self._clamp01(
                0.30 * response_capacity
                + 0.22 * observed_response
                + 0.18 * evo_recovery
                + 0.12 * survival
                + 0.10 * stability
                + 0.08 * max(0.0, 1.0 - risk)
            )

            effective_pressure = max(
                0.0,
                pressure * (1.0 - 0.34 * response_capacity)
                + 0.10 * aggression_cost,
            )
            effective_risk = self._clamp01(
                risk
                * (
                    1.0
                    - 0.30 * survival_bonus
                    - 0.20 * evo_recovery
                )
                + 0.18 * aggression_cost
            )
            score = self._clamp01(
                0.28 * response_capacity
                + 0.22 * observed_response
                + 0.18 * survival_bonus
                + 0.14 * self_direction
                + 0.10 * environment_impact
                + 0.06 * expansion_bonus
                - 0.08 * aggression_cost
            )
            legacy_self_direction = self._clamp01(
                0.36 * knowledge_impact
                + 0.24 * legacy_pressure_buffer
                + 0.18 * legacy_survival_bonus
                + 0.12 * environment_impact
                + 0.10 * max(0.0, knowledge_score - risk)
            )
            legacy_score = self._clamp01(
                0.26 * knowledge_impact
                + 0.20 * legacy_pressure_buffer
                + 0.18 * legacy_survival_bonus
                + 0.16 * legacy_self_direction
                + 0.10 * environment_impact
                + 0.06 * legacy_expansion_bonus
                - 0.08 * legacy_aggression_cost
            )

            regime = self._feedback_regime_name(score, pressure_buffer, self_direction, effective_risk)
            if score > self.feedback_peak_score:
                old_peak = self.feedback_peak_score
                self.feedback_peak_score = score
                self.feedback_peak_tick = tick
                if score >= 0.26 and score - old_peak >= 0.06:
                    self.feedback_event_counts["gain"] = self.feedback_event_counts.get("gain", 0) + 1
                    self.feedback_last_event = f"{tick}: feedback gain score={score:.3f} buffer={pressure_buffer:.3f}"
                    self._chronicle(
                        tick, "FEEDBACK_GAIN", family=know.get("knowledge_dominant_family"), phase=regime,
                        pressure=effective_pressure, risk=effective_risk,
                        details=f"score={score:.3f} buffer={pressure_buffer:.3f} survival_bonus={survival_bonus:.3f} self_direction={self_direction:.3f}",
                        severity="MAJOR" if score >= 0.38 else "MINOR",
                    )

            if self.feedback_prev_regime is None:
                self.feedback_prev_regime = regime
            elif regime != self.feedback_prev_regime:
                old = self.feedback_prev_regime
                self.feedback_prev_regime = regime
                self.feedback_event_counts["regime_shift"] = self.feedback_event_counts.get("regime_shift", 0) + 1
                self.feedback_last_event = f"{tick}: {old}->{regime} score={score:.3f}"
                self._chronicle(
                    tick, "CULTURAL_SHIFT", family=know.get("knowledge_dominant_family"), phase=regime,
                    pressure=effective_pressure, risk=effective_risk,
                    details=f"{old}->{regime} knowledge={knowledge_impact:.3f} env={environment_impact:.3f}",
                    severity="MAJOR" if regime in ("ADAPTIVE_LOOP", "SELF_REGULATING") else "MINOR",
                )

            if pressure >= 0.50 and pressure_buffer >= 0.25 and effective_risk < risk * 0.82:
                if tick - self.chronicle_last_tick_by_event.get("ADAPTATION_SUCCESS", -10**9) > 900:
                    self.feedback_event_counts["adaptation_success"] = self.feedback_event_counts.get("adaptation_success", 0) + 1
                    self._chronicle(
                        tick, "ADAPTATION_SUCCESS", family=know.get("knowledge_dominant_family"), phase=regime,
                        pressure=effective_pressure, risk=effective_risk,
                        details=f"raw_risk={risk:.3f} effective_risk={effective_risk:.3f} buffer={pressure_buffer:.3f}",
                        severity="MAJOR",
                    )

            if effective_risk >= 0.72 and score < 0.22 and knowledge_score >= 0.16:
                if tick - self.chronicle_last_tick_by_event.get("FEEDBACK_FAILURE", -10**9) > 900:
                    self.feedback_event_counts["failure"] = self.feedback_event_counts.get("failure", 0) + 1
                    self._chronicle(
                        tick, "FEEDBACK_FAILURE", family=know.get("knowledge_dominant_family"), phase=regime,
                        pressure=effective_pressure, risk=effective_risk,
                        details=f"score={score:.3f} raw_pressure={pressure:.3f} effective_risk={effective_risk:.3f}",
                        severity="CRITICAL",
                    )

            if memory >= 0.35 and know.get("knowledge_loss", 0.0) >= 0.55 and effective_risk < risk:
                if tick - self.chronicle_last_tick_by_event.get("KNOWLEDGE_RESCUE", -10**9) > 1000:
                    self.feedback_event_counts["rescue"] = self.feedback_event_counts.get("rescue", 0) + 1
                    self._chronicle(
                        tick, "KNOWLEDGE_RESCUE", family=know.get("knowledge_dominant_family"), phase=regime,
                        pressure=effective_pressure, risk=effective_risk,
                        details=f"memory={memory:.3f} loss={know.get('knowledge_loss', 0.0):.3f} rescued={risk - effective_risk:.3f}",
                        severity="MAJOR",
                    )

            self.feedback_prev_score = score
            self.feedback_line = (
                f"FB {regime} score={score:.2f} peak={self.feedback_peak_score:.2f} "
                f"buf={pressure_buffer:.2f} surv+={survival_bonus:.2f} pEff={effective_pressure:.2f} "
                f"riskEff={effective_risk:.2f} self={self_direction:.2f} K/E={knowledge_impact:.2f}/{environment_impact:.2f}"
            )
            fb = {
                "feedback_score": score,
                "feedback_peak_score": self.feedback_peak_score,
                "feedback_peak_tick": self.feedback_peak_tick,
                "feedback_regime": regime,
                "feedback_survival_bonus": survival_bonus,
                "feedback_pressure_buffer": pressure_buffer,
                "feedback_effective_pressure": effective_pressure,
                "feedback_effective_risk": effective_risk,
                "feedback_self_direction": self_direction,
                "feedback_environment_impact": environment_impact,
                "feedback_knowledge_impact": knowledge_impact,
                "feedback_response_capacity": response_capacity,
                "feedback_response_opportunity": response_opportunity,
                "feedback_observed_response": observed_response,
                "feedback_legacy_score": legacy_score,
                "feedback_metric_version": "2.0",
                "feedback_metric_independence_status": (
                    "STRUCTURALLY_INDEPENDENT_V2"
                ),
                "feedback_expansion_bonus": expansion_bonus,
                "feedback_aggression_cost": aggression_cost,
                "feedback_line": self.feedback_line,
                "feedback_last_event": self.feedback_last_event,
                "feedback_event_counts": dict(self.feedback_event_counts),
            }
            self.feedback_history.append({"tick": tick, **fb})
            return fb

    def _emergence_confidence_name(self, score: float, evidence_count: int):
            if score >= 0.82 and evidence_count >= 8:
                return "VERY_HIGH"
            if score >= 0.66 and evidence_count >= 6:
                return "HIGH"
            if score >= 0.45 and evidence_count >= 4:
                return "MEDIUM"
            if score >= 0.22 and evidence_count >= 2:
                return "LOW"
            return "NONE"

    def _update_emergence_evidence_layer(self, tick: int, alive: bool, lineage: dict, dynasty: dict,
                                             demo: dict, evo: dict, civ: dict, know: dict, fb: dict,
                                             history: dict, ecosystem_health: float, objects: int,
                                             total_living_mass: int, largest: int, fragmentation_index: float):
            age = 0 if self.birth_tick is None else max(0, tick - self.birth_tick)
            stability = float(history.get("stability_index", 0.0) or 0.0)
            complexity_index = self._clamp01(
                0.18 * min(1.0, objects / 18.0) +
                0.16 * min(1.0, total_living_mass / 450.0) +
                0.14 * min(1.0, largest / 180.0) +
                0.14 * min(1.0, (lineage.get("active_families", 0) or 0) / 6.0) +
                0.12 * min(1.0, (lineage.get("deepest_generation", 0) or 0) / 6.0) +
                0.10 * min(1.0, (civ.get("civ_cities", 0) or 0) / 5.0) +
                0.08 * (civ.get("civ_specialization", 0.0) or 0.0) +
                0.08 * (civ.get("civ_urbanization", 0.0) or 0.0)
            )
            stability_signal = self._clamp01(
                0.34 * stability +
                0.20 * ecosystem_health +
                0.16 * min(1.0, age / 1200.0) +
                0.12 * max(0.0, 1.0 - abs(history.get("mass_growth_per_tick", 0.0) or 0.0) / 9.0) +
                0.10 * (demo.get("demo_survival_ratio", 0.0) or 0.0) +
                0.08 * max(0.0, 1.0 - fragmentation_index * 18.0)
            )
            positive = []
            negative = []

            def add_pos(key, cond):
                if cond:
                    positive.append(key)

            def add_neg(key, cond):
                if cond:
                    negative.append(key)

            add_pos("life", alive and age >= 80)
            add_pos("stable_life", alive and age >= 300 and stability_signal >= 0.42)
            add_pos("multi_colony", objects >= 5 and total_living_mass >= 90)
            add_pos("families", (lineage.get("active_families", 0) or 0) >= 2)
            add_pos("generations", (lineage.get("deepest_generation", 0) or 0) >= 3)
            add_pos("dynasty", (dynasty.get("dynasty_age", 0) or 0) >= 250 and (dynasty.get("dynasty_living", 0) or 0) >= 2)
            add_pos("civilization", civ.get("civ_stage", "NONE") not in ("NONE", "COLLAPSE") and (civ.get("civ_score", 0.0) or 0.0) >= 0.22)
            add_pos("knowledge", (know.get("knowledge_score", 0.0) or 0.0) >= 0.20)
            add_pos("discoveries", bool(know.get("knowledge_discoveries", "")))
            add_pos("feedback", fb.get("feedback_regime", "NONE") in ("CULTURAL_FEEDBACK", "ADAPTIVE_LOOP", "SELF_REGULATING"))
            add_pos("self_direction", (fb.get("feedback_self_direction", 0.0) or 0.0) >= 0.35)
            add_pos("complexity", complexity_index >= 0.45)
            add_pos("low_risk", (fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)) or 0.0) <= 0.42)

            add_neg("extinct", (not alive) and self.birth_tick is not None and self.collapse_tick is not None)
            add_neg("high_risk", (fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)) or 0.0) >= 0.70)
            add_neg("collapse_risk", (civ.get("civ_collapse_risk", 0.0) or 0.0) >= 0.66)
            add_neg("knowledge_loss", (know.get("knowledge_loss", 0.0) or 0.0) >= 0.68)
            add_neg("fragmented_soup", fragmentation_index >= 0.12 and stability < 0.35)
            add_neg("no_lineage", alive and age >= 300 and (lineage.get("active_families", 0) or 0) == 0)

            positive_count = len(positive)
            negative_count = len(negative)
            evidence_balance = self._clamp01((positive_count - 0.7 * negative_count) / 12.0)
            layer_score = self._clamp01(
                0.16 * (1.0 if alive else 0.0) +
                0.14 * stability_signal +
                0.13 * complexity_index +
                0.12 * (civ.get("civ_score", 0.0) or 0.0) +
                0.12 * (know.get("knowledge_score", 0.0) or 0.0) +
                0.11 * (fb.get("feedback_score", 0.0) or 0.0) +
                0.08 * min(1.0, (lineage.get("deepest_generation", 0) or 0) / 6.0) +
                0.07 * (demo.get("demo_survival_ratio", 0.0) or 0.0) +
                0.07 * evidence_balance
            )
            risk_penalty = self._clamp01(
                0.34 * (fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)) or 0.0) +
                0.26 * (civ.get("civ_collapse_risk", 0.0) or 0.0) +
                0.22 * (know.get("knowledge_loss", 0.0) or 0.0) +
                0.18 * max(0.0, fragmentation_index - 0.10) * 5.0
            )
            score = self._clamp01(layer_score * (1.0 - 0.22 * risk_penalty))
            confidence = self._emergence_confidence_name(score, positive_count)

            if score > self.emergence_peak_score:
                old_peak = self.emergence_peak_score
                self.emergence_peak_score = score
                self.emergence_peak_tick = tick
                if score >= 0.45 and score - old_peak >= 0.05:
                    self.emergence_event_counts["candidate"] = self.emergence_event_counts.get("candidate", 0) + 1
                    self.emergence_last_event = f"{tick}: emergence candidate score={score:.3f} confidence={confidence}"
                    self._chronicle(
                        tick, "EMERGENCE_CANDIDATE", phase=confidence,
                        pressure=fb.get("feedback_effective_pressure", evo.get("evo_pressure", 0.0)),
                        risk=fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)),
                        details=f"score={score:.3f} evidence={positive_count} pos={','.join(positive[:6])}",
                        severity="MAJOR" if confidence in ("HIGH", "VERY_HIGH") else "NORMAL",
                    )

            if confidence != self.emergence_prev_confidence:
                old = self.emergence_prev_confidence
                self.emergence_prev_confidence = confidence
                if confidence in ("HIGH", "VERY_HIGH") and old not in ("HIGH", "VERY_HIGH"):
                    self.emergence_event_counts["confirmed"] = self.emergence_event_counts.get("confirmed", 0) + 1
                    self._chronicle(
                        tick, "EMERGENCE_CONFIRMED", phase=confidence,
                        pressure=fb.get("feedback_effective_pressure", evo.get("evo_pressure", 0.0)),
                        risk=fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)),
                        details=f"score={score:.3f} evidence={positive_count} complexity={complexity_index:.3f} stability={stability_signal:.3f}",
                        severity="HISTORIC" if confidence == "VERY_HIGH" else "MAJOR",
                    )
                elif old in ("HIGH", "VERY_HIGH") and confidence in ("NONE", "LOW", "MEDIUM"):
                    self.emergence_event_counts["collapse"] = self.emergence_event_counts.get("collapse", 0) + 1
                    self._chronicle(
                        tick, "EMERGENCE_COLLAPSE", phase=f"{old}->{confidence}",
                        pressure=fb.get("feedback_effective_pressure", evo.get("evo_pressure", 0.0)),
                        risk=fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)),
                        details=f"score={score:.3f} negative={negative_count} neg={','.join(negative[:6])}",
                        severity="CRITICAL",
                    )
                elif old in ("NONE", "LOW") and confidence in ("MEDIUM", "HIGH", "VERY_HIGH"):
                    self.emergence_event_counts["recovery"] = self.emergence_event_counts.get("recovery", 0) + 1
                    self._chronicle(
                        tick, "EMERGENCE_RECOVERY", phase=f"{old}->{confidence}",
                        pressure=fb.get("feedback_effective_pressure", evo.get("evo_pressure", 0.0)),
                        risk=fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)),
                        details=f"score={score:.3f} evidence={positive_count}",
                        severity="NORMAL",
                    )

            pos_text = ";".join(positive)
            neg_text = ";".join(negative)
            self.emergence_line = (
                f"EMG {confidence} score={score:.2f} peak={self.emergence_peak_score:.2f} "
                f"ev={positive_count}/{negative_count} comp={complexity_index:.2f} stab={stability_signal:.2f} "
                f"pos={','.join(positive[:4]) if positive else '-'} neg={','.join(negative[:3]) if negative else '-'}"
            )
            emg = {
                "emergence_score": score,
                "emergence_peak_score": self.emergence_peak_score,
                "emergence_peak_tick": self.emergence_peak_tick,
                "emergence_confidence": confidence,
                "emergence_evidence_count": positive_count,
                "emergence_negative_count": negative_count,
                "emergence_positive_evidence": pos_text,
                "emergence_negative_evidence": neg_text,
                "emergence_complexity_index": complexity_index,
                "emergence_stability_signal": stability_signal,
                "emergence_risk_penalty": risk_penalty,
                "emergence_line": self.emergence_line,
                "emergence_event_counts": dict(self.emergence_event_counts),
                "emergence_last_event": self.emergence_last_event,
            }
            self.emergence_history.append({"tick": tick, **emg})
            return emg

    def _validation_grade_name(self, quality: float):
            if quality >= 0.82:
                return "VERY_HIGH"
            if quality >= 0.66:
                return "HIGH"
            if quality >= 0.48:
                return "MEDIUM"
            if quality >= 0.25:
                return "LOW"
            return "NONE"

    def _update_validation_calibration_layer(self, tick: int, emg: dict, lineage: dict, dynasty: dict,
                                                 demo: dict, evo: dict, civ: dict, know: dict, fb: dict,
                                                 history: dict, alive: bool, objects: int,
                                                 total_living_mass: int, fragmentation_index: float):
            """Audit the observer's own verdict without changing the world.

            The goal is not to prove that a civilization exists. The goal is to
            estimate how trustworthy, stable, and explainable the current Observer
            reading is.
            """
            score = float(emg.get("emergence_score", 0.0) or 0.0)
            confidence = str(emg.get("emergence_confidence", "NONE") or "NONE")
            pos_count = int(emg.get("emergence_evidence_count", 0) or 0)
            neg_count = int(emg.get("emergence_negative_count", 0) or 0)
            complexity = float(emg.get("emergence_complexity_index", 0.0) or 0.0)
            stab_signal = float(emg.get("emergence_stability_signal", 0.0) or 0.0)

            recent = list(self.emergence_history)[-80:]
            if len(recent) >= 6:
                vals = [float(x.get("emergence_score", 0.0) or 0.0) for x in recent]
                mean = sum(vals) / len(vals)
                var = sum((v - mean) ** 2 for v in vals) / len(vals)
                volatility = math.sqrt(var)
                repeatability = self._clamp01(1.0 - volatility * 4.5)
                drift = abs(vals[-1] - vals[0])
                stability_conf = self._clamp01(0.65 * repeatability + 0.35 * (1.0 - min(1.0, drift * 2.6)))
            else:
                repeatability = 0.0
                stability_conf = 0.0
                volatility = 1.0
                drift = 1.0

            signal_depth = self._clamp01(
                0.22 * min(1.0, pos_count / 10.0) +
                0.15 * min(1.0, (lineage.get("active_families", 0) or 0) / 5.0) +
                0.13 * min(1.0, (lineage.get("deepest_generation", 0) or 0) / 5.0) +
                0.12 * (civ.get("civ_score", 0.0) or 0.0) +
                0.13 * (know.get("knowledge_score", 0.0) or 0.0) +
                0.13 * (fb.get("feedback_score", 0.0) or 0.0) +
                0.12 * complexity
            )
            consistency = self._clamp01(
                0.26 * (1.0 - abs((know.get("knowledge_score", 0.0) or 0.0) - (fb.get("feedback_knowledge_impact", 0.0) or 0.0))) +
                0.24 * (1.0 - abs((civ.get("civ_score", 0.0) or 0.0) - complexity)) +
                0.20 * (1.0 - abs((history.get("stability_index", 0.0) or 0.0) - stab_signal)) +
                0.16 * (1.0 if alive or score < 0.35 else 0.35) +
                0.14 * (1.0 - min(1.0, neg_count / 5.0))
            )
            noise_sensitivity = self._clamp01(
                0.45 * volatility * 3.0 +
                0.25 * abs(float(history.get("mass_growth_per_tick", 0.0) or 0.0)) / 8.0 +
                0.20 * fragmentation_index * 4.0 +
                0.10 * (1.0 - stab_signal)
            )
            false_positive_risk = self._clamp01(
                (0.36 if score >= 0.58 and signal_depth < 0.42 else 0.0) +
                (0.22 if confidence in ("HIGH", "VERY_HIGH") and (know.get("knowledge_score", 0.0) or 0.0) < 0.18 else 0.0) +
                (0.18 if confidence in ("HIGH", "VERY_HIGH") and (fb.get("feedback_score", 0.0) or 0.0) < 0.18 else 0.0) +
                (0.16 if pos_count < 5 and score >= 0.50 else 0.0) +
                (0.16 if total_living_mass < 80 and score >= 0.50 else 0.0) +
                0.12 * neg_count / 4.0
            )
            rich_world = self._clamp01(
                0.25 * min(1.0, objects / 14.0) +
                0.20 * min(1.0, total_living_mass / 350.0) +
                0.18 * min(1.0, (lineage.get("deepest_generation", 0) or 0) / 5.0) +
                0.17 * (know.get("knowledge_score", 0.0) or 0.0) +
                0.12 * (fb.get("feedback_score", 0.0) or 0.0) +
                0.08 * stab_signal
            )
            false_negative_risk = self._clamp01(
                (0.40 if rich_world >= 0.62 and score < 0.40 else 0.0) +
                (0.18 if (lineage.get("deepest_generation", 0) or 0) >= 4 and score < 0.45 else 0.0) +
                (0.16 if (know.get("knowledge_score", 0.0) or 0.0) >= 0.45 and score < 0.45 else 0.0) +
                (0.16 if (fb.get("feedback_score", 0.0) or 0.0) >= 0.45 and score < 0.45 else 0.0) +
                0.10 * max(0.0, rich_world - score)
            )
            warning_bits = []
            if false_positive_risk >= 0.45:
                warning_bits.append("false_positive")
            if false_negative_risk >= 0.45:
                warning_bits.append("false_negative")
            if noise_sensitivity >= 0.55:
                warning_bits.append("noise_sensitive")
            if repeatability < 0.45 and len(recent) >= 20:
                warning_bits.append("unstable_score")
            warning = ",".join(warning_bits) if warning_bits else "ok"

            quality = self._clamp01(
                0.25 * repeatability +
                0.18 * stability_conf +
                0.19 * signal_depth +
                0.18 * consistency +
                0.10 * min(1.0, pos_count / 10.0) +
                0.10 * (1.0 - max(false_positive_risk, false_negative_risk, noise_sensitivity * 0.75))
            )
            grade = self._validation_grade_name(quality)
            self.validation_quality_peak = max(self.validation_quality_peak, quality)

            contributions = {
                "life": 0.08 * (1.0 if alive else 0.0),
                "families": 0.11 * min(1.0, (lineage.get("active_families", 0) or 0) / 5.0),
                "generations": 0.10 * min(1.0, (lineage.get("deepest_generation", 0) or 0) / 5.0),
                "civilization": 0.14 * (civ.get("civ_score", 0.0) or 0.0),
                "knowledge": 0.16 * (know.get("knowledge_score", 0.0) or 0.0),
                "feedback": 0.16 * (fb.get("feedback_score", 0.0) or 0.0),
                "stability": 0.13 * stab_signal,
                "evidence": 0.12 * min(1.0, pos_count / 10.0),
            }
            top = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)[:4]
            penalty = max(false_positive_risk, false_negative_risk, noise_sensitivity * 0.75)
            explain = ";".join(f"{k}:{v:.2f}" for k, v in top) + f";penalty:{penalty:.2f}"

            if grade != self.validation_prev_grade:
                old = self.validation_prev_grade
                self.validation_prev_grade = grade
                self.validation_event_counts["grade_shift"] = self.validation_event_counts.get("grade_shift", 0) + 1
                self.validation_last_event = f"{tick}: validation {old}->{grade} quality={quality:.3f} warn={warning}"
                if grade in ("HIGH", "VERY_HIGH"):
                    self.validation_event_counts["confidence_high"] = self.validation_event_counts.get("confidence_high", 0) + 1
                    self._chronicle(tick, "OBSERVER_CONFIDENCE_HIGH", phase=grade,
                                    pressure=fb.get("feedback_effective_pressure", evo.get("evo_pressure", 0.0)),
                                    risk=fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)),
                                    details=f"quality={quality:.3f} repeat={repeatability:.3f} signal={signal_depth:.3f}",
                                    severity="NORMAL")
                elif warning != "ok":
                    self.validation_event_counts["warning"] = self.validation_event_counts.get("warning", 0) + 1
                    self._chronicle(tick, "VALIDATION_WARNING", phase=grade,
                                    pressure=fb.get("feedback_effective_pressure", evo.get("evo_pressure", 0.0)),
                                    risk=fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)),
                                    details=f"warn={warning} fp={false_positive_risk:.3f} fn={false_negative_risk:.3f} noise={noise_sensitivity:.3f}",
                                    severity="MAJOR" if max(false_positive_risk, false_negative_risk) >= 0.6 else "NORMAL")

            if warning == "ok" and quality >= 0.55 and tick % 500 == 0:
                self.validation_event_counts["pass"] = self.validation_event_counts.get("pass", 0) + 1
                self._chronicle(tick, "VALIDATION_PASS", phase=grade,
                                pressure=fb.get("feedback_effective_pressure", evo.get("evo_pressure", 0.0)),
                                risk=fb.get("feedback_effective_risk", evo.get("evo_extinction_risk", 0.0)),
                                details=f"quality={quality:.3f} repeat={repeatability:.3f} consistency={consistency:.3f}",
                                severity="NORMAL")

            self.validation_line = (
                f"VAL {grade} q={quality:.2f} rep={repeatability:.2f} stab={stability_conf:.2f} "
                f"fp={false_positive_risk:.2f} fn={false_negative_risk:.2f} noise={noise_sensitivity:.2f} "
                f"warn={warning} why={','.join(k for k, _ in top)}"
            )
            val = {
                "validation_quality": quality,
                "validation_quality_peak": self.validation_quality_peak,
                "validation_grade": grade,
                "validation_repeatability": repeatability,
                "validation_stability_confidence": stability_conf,
                "validation_signal_depth": signal_depth,
                "validation_consistency": consistency,
                "validation_noise_sensitivity": noise_sensitivity,
                "validation_false_positive_risk": false_positive_risk,
                "validation_false_negative_risk": false_negative_risk,
                "validation_warning": warning,
                "validation_explain": explain,
                "validation_line": self.validation_line,
                "validation_event_counts": dict(self.validation_event_counts),
                "validation_last_event": self.validation_last_event,
            }
            self.validation_history.append({"tick": tick, **val})
            return val
