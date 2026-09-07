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


class ObserverChronicleMixin:
    def _chronicle_severity(self, event: str, pressure=None, risk=None, details: str = ""):
            pressure_v = 0.0 if pressure is None or pressure == "" else float(pressure)
            risk_v = 0.0 if risk is None or risk == "" else float(risk)

            historic = {
                "NEW_SUPER_DYNASTY",
                "ECOSYSTEM_REBUILD",
                "ECOSYSTEM_COLLAPSE",
            }
            critical = {
                "MASS_EXTINCTION_START",
                "PRESSURE_PEAK",
                "COLLAPSE",
                "FIELD_SATURATION",
            }
            major = {
                "ERA_BEGIN",
                "ERA_END",
                "PHASE_CHANGE",
                "EVO_PHASE_CHANGE",
                "DOMINANCE_SHIFT",
                "DYNASTY_DOMINANT",
                "DYNASTY_EXTINCT",
                "NEW_DYNASTY",
                "RECOVERY",
            }
            normal = {
                "COLONY_EXTINCT",
                "FIRST_LARGE_STRUCTURE",
            }

            if event in historic or pressure_v >= 0.75 or risk_v >= 0.70:
                return "HISTORIC"
            if event in critical or pressure_v >= 0.55 or risk_v >= 0.55:
                return "CRITICAL"
            if event in major or pressure_v >= 0.35 or risk_v >= 0.35:
                return "MAJOR"
            if event in normal:
                return "NORMAL"
            return "MINOR"

    def _chronicle_should_write(self, tick: int, event: str, severity: str):
            # Keep important events, throttle low-value spam.
            cooldown = {
                "MINOR": 200,
                "NORMAL": 80,
                "MAJOR": 0,
                "CRITICAL": 0,
                "HISTORIC": 0,
            }.get(severity, 0)
            last = self.chronicle_last_tick_by_event.get(event)
            if last is not None and cooldown and tick - last < cooldown:
                return False
            self.chronicle_last_tick_by_event[event] = tick
            return True

    def _chronicle(self, tick: int, event: str, family=None, colony=None, phase=None, pressure=None, risk=None, cause=None, details: str = "", severity: str | None = None):
            severity = severity or self._chronicle_severity(event, pressure=pressure, risk=risk, details=details)
            self.chronicle_counts[event] = self.chronicle_counts.get(event, 0) + 1
            self.chronicle_severity_counts[severity] = self.chronicle_severity_counts.get(severity, 0) + 1
            self.last_chronicle_severity = severity
            self.last_chronicle_event_line = f"{tick}: [{severity}] {event} {details}".strip()

            if severity in ("MAJOR", "CRITICAL", "HISTORIC"):
                self.history_book.append({
                    "tick": tick,
                    "severity": severity,
                    "event": event,
                    "family": family,
                    "colony": colony,
                    "phase": phase,
                    "pressure": None if pressure is None else round(float(pressure), 6),
                    "risk": None if risk is None else round(float(risk), 6),
                    "cause": cause,
                    "details": details,
                })
                if len(self.history_book) > self.history_book_limit:
                    self.history_book = self.history_book[-self.history_book_limit:]

            if not self._chronicle_should_write(tick, event, severity):
                return

            if self._chronicle_writer is None:
                return

            row = {
                "tick": tick,
                "severity": severity,
                "event": event,
                "family": "" if family is None else family,
                "colony": "" if colony is None else colony,
                "phase": "" if phase is None else phase,
                "pressure": "" if pressure is None else round(float(pressure), 6),
                "risk": "" if risk is None else round(float(risk), 6),
                "cause": "" if cause is None else cause,
                "details": details,
            }
            self._chronicle_writer.writerow(row)
            self._chronicle_rows_since_flush += 1
            if self._chronicle_rows_since_flush >= self.live_flush_every:
                self._chronicle_file.flush()
                self._chronicle_rows_since_flush = 0

    def add_event(self, tick: int, event_type: str, detail: str):
            ev = {"tick": tick, "type": event_type, "detail": detail}
            if self.events and self.events[-1] == ev:
                return
            self.events.append(ev)
            self.last_event = f"{tick}: {event_type} - {detail}"
            if self._event_writer:
                self._event_writer.writerow(ev)
                self._event_file.flush()

            # Mirror selected observer events into the readable Evolution Chronicle.
            if event_type == "family-founded":
                fam = re.search(r"family=(\d+)", detail)
                col = re.search(r"colony=(\d+)", detail)
                self._chronicle(tick, "NEW_DYNASTY", family=fam.group(1) if fam else None, colony=col.group(1) if col else None, details=detail)
            elif event_type == "colony-offspring":
                fam = re.search(r"family=(\d+)", detail)
                col = re.search(r"colony=(\d+)", detail)
                self._chronicle(tick, "COLONY_BIRTH", family=fam.group(1) if fam else None, colony=col.group(1) if col else None, details=detail)
            elif event_type == "colony-extinct":
                fam = re.search(r"family=(\d+)", detail)
                col = re.search(r"colony=(\d+)", detail)
                self._chronicle(tick, "COLONY_EXTINCT", family=fam.group(1) if fam else None, colony=col.group(1) if col else None, details=detail)
            elif event_type in ("collapse", "legacy-check", "field-saturation", "first-large-structure"):
                self._chronicle(tick, event_type.upper().replace("-", "_"), details=detail)

    def _sparkline(self, values, width: int = 18):
            vals = list(values)[-width:]
            if not vals:
                return "." * width
            chars = "._-~=+#@"  # 8 levels, ASCII-safe for Windows/Tk.
            out = []
            for v in vals:
                try:
                    x = max(0.0, min(1.0, float(v)))
                except Exception:
                    x = 0.0
                out.append(chars[min(len(chars) - 1, int(round(x * (len(chars) - 1))))])
            return ("." * max(0, width - len(out))) + "".join(out)

    def _update_evo_timeline(self, tick: int, evo: dict):
            item = {
                "tick": tick,
                "S": float(evo.get("evo_stress", 0.0) or 0.0),
                "A": float(evo.get("evo_adapt", 0.0) or 0.0),
                "P": float(evo.get("evo_pressure", 0.0) or 0.0),
                "R": float(evo.get("evo_extinction_risk", 0.0) or 0.0),
            }
            self.evo_timeline.append(item)

            def series(key):
                return [x[key] for x in self.evo_timeline]

            def trend(key):
                vals = series(key)
                if len(vals) < 2:
                    return 0.0
                span = min(24, len(vals) - 1)
                return vals[-1] - vals[-1 - span]

            line = (
                f"TL S:{self._sparkline(series('S'))} "
                f"A:{self._sparkline(series('A'))} "
                f"P:{self._sparkline(series('P'))} "
                f"R:{self._sparkline(series('R'))}"
            )
            self.evo_timeline_line = line

            return {
                "evo_timeline_line": line,
                "evo_stress_trend": trend("S"),
                "evo_adapt_trend": trend("A"),
                "evo_pressure_trend": trend("P"),
                "evo_risk_trend": trend("R"),
                "evo_timeline_len": len(self.evo_timeline),
            }

    def _write_pressure_timeline_row(self, tick: int, evo: dict, evo_tl: dict, colony_dist: dict, dynasty: dict, demo: dict,
                                         ecosystem_phase: str, objects: int, total_living_mass: int, largest: int):
            if self._pressure_timeline_writer is None:
                return
            if tick % self.pressure_timeline_every != 0:
                return

            row = {
                "tick": tick,
                "phase": evo.get("evo_phase", ""),
                "stress": round(float(evo.get("evo_stress", 0.0) or 0.0), 6),
                "adapt": round(float(evo.get("evo_adapt", 0.0) or 0.0), 6),
                "pressure": round(float(evo.get("evo_pressure", 0.0) or 0.0), 6),
                "recovery": round(float(evo.get("evo_recovery", 0.0) or 0.0), 6),
                "risk": round(float(evo.get("evo_extinction_risk", 0.0) or 0.0), 6),
                "src_frag_pct": round(float(evo.get("evo_src_frag_pct", 0.0) or 0.0), 6),
                "src_death_pct": round(float(evo.get("evo_src_death_pct", 0.0) or 0.0), 6),
                "src_loss_pct": round(float(evo.get("evo_src_loss_pct", 0.0) or 0.0), 6),
                "src_inst_pct": round(float(evo.get("evo_src_inst_pct", 0.0) or 0.0), 6),
                "src_dom_pct": round(float(evo.get("evo_src_dom_pct", 0.0) or 0.0), 6),
                "cause": evo.get("evo_cause", ""),
                "stress_trend": round(float(evo_tl.get("evo_stress_trend", 0.0) or 0.0), 6),
                "adapt_trend": round(float(evo_tl.get("evo_adapt_trend", 0.0) or 0.0), 6),
                "pressure_trend": round(float(evo_tl.get("evo_pressure_trend", 0.0) or 0.0), 6),
                "risk_trend": round(float(evo_tl.get("evo_risk_trend", 0.0) or 0.0), 6),
                "ecosystem_phase": ecosystem_phase,
                "objects": objects,
                "mass": total_living_mass,
                "largest": largest,
                "families": colony_dist.get("active_families", 0),
                "dynasty_id": dynasty.get("dynasty_leader_id"),
                "dynasty_dominance": round(float(dynasty.get("dynasty_dominance", 0.0) or 0.0), 6),
                "demo_birth_rate_1000": round(float(demo.get("demo_birth_rate_1000", 0.0) or 0.0), 6),
                "demo_death_rate_1000": round(float(demo.get("demo_death_rate_1000", 0.0) or 0.0), 6),
                "demo_replacement": round(float(demo.get("demo_replacement", 0.0) or 0.0), 6),
                "demo_survival_ratio": round(float(demo.get("demo_survival_ratio", 0.0) or 0.0), 6),
            }
            self._pressure_timeline_writer.writerow(row)
            self._pressure_rows_since_flush += 1
            if self._pressure_rows_since_flush >= self.live_flush_every:
                self._pressure_timeline_file.flush()
                self._pressure_rows_since_flush = 0

    def _update_chronicle_signals(self, tick: int, growth_phase: str, evo: dict, demo: dict, lineage: dict, dynasty: dict,
                                      objects: int, total_living_mass: int, largest: int):
            pressure = float(evo.get("evo_pressure", 0.0) or 0.0)
            stress = float(evo.get("evo_stress", 0.0) or 0.0)
            risk = float(evo.get("evo_extinction_risk", 0.0) or 0.0)
            cause = evo.get("evo_cause", "")
            evo_phase = evo.get("evo_phase", "")

            story_era = self._story_era_name(
                tick=tick,
                alive=(objects > 0 and total_living_mass > 0),
                growth_phase=growth_phase,
                evo=evo,
                demo=demo,
                dynasty=dynasty,
                ecosystem_health=(largest / max(1, max(self.peak_largest, largest))),
                fragmentation_index=(objects / max(1, total_living_mass)),
                objects=objects,
                total_living_mass=total_living_mass,
            )
            self._update_story_era(
                tick=tick,
                era_name=story_era,
                pressure=pressure,
                risk=risk,
                cause=cause,
                objects=objects,
                total_living_mass=total_living_mass,
                largest=largest,
            )

            # Era journal: higher-level ecological age changes.
            if self.current_era is None:
                self.current_era = growth_phase
                self.era_start_tick = tick
                self._chronicle(
                    tick, "ERA_BEGIN", phase=growth_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"era={growth_phase} obj={objects} mass={total_living_mass} L={largest}"
                )

            if self.last_growth_phase_seen is None:
                self.last_growth_phase_seen = growth_phase
            elif growth_phase != self.last_growth_phase_seen:
                old_phase = self.last_growth_phase_seen
                duration = tick - (self.era_start_tick or tick)
                self._chronicle(
                    tick, "ERA_END", phase=old_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"era={old_phase} duration={duration} obj={objects} mass={total_living_mass} L={largest}"
                )
                self._chronicle(
                    tick, "PHASE_CHANGE", phase=growth_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"{old_phase}->{growth_phase} obj={objects} mass={total_living_mass} L={largest}"
                )
                self._chronicle(
                    tick, "ERA_BEGIN", phase=growth_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"era={growth_phase} after={old_phase} obj={objects} mass={total_living_mass} L={largest}"
                )
                self.last_growth_phase_seen = growth_phase
                self.current_era = growth_phase
                self.era_start_tick = tick

            if self.last_evo_phase_seen is None:
                self.last_evo_phase_seen = evo_phase
            elif evo_phase != self.last_evo_phase_seen:
                self._chronicle(
                    tick, "EVO_PHASE_CHANGE", phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"{self.last_evo_phase_seen}->{evo_phase} stress={stress:.3f}"
                )
                self.last_evo_phase_seen = evo_phase

            if pressure >= 0.55 and (self.last_pressure_peak_tick is None or tick - self.last_pressure_peak_tick >= 500):
                self._chronicle(
                    tick, "PRESSURE_PEAK", phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                    details=evo.get("evo_source_line", "")
                )
                self.last_pressure_peak_tick = tick

            death_rate = float(demo.get("demo_death_rate_1000", 0.0) or 0.0)
            birth_rate = float(demo.get("demo_birth_rate_1000", 0.0) or 0.0)

            # Collapse/rebuild markers. These are intentionally conservative to avoid log spam.
            if not self.ecosystem_collapsed and objects <= 2 and (risk >= 0.50 or total_living_mass <= max(10, largest * 2)):
                self.ecosystem_collapsed = True
                self.ecosystem_collapse_tick = tick
                self._chronicle(
                    tick, "ECOSYSTEM_COLLAPSE", phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"obj={objects} mass={total_living_mass} largest={largest} death/k={death_rate:.1f}"
                )
            elif self.ecosystem_collapsed and objects >= 6 and total_living_mass > max(60, largest * 3) and pressure < 0.45:
                duration = tick - (self.ecosystem_collapse_tick or tick)
                self.ecosystem_collapsed = False
                self._chronicle(
                    tick, "ECOSYSTEM_REBUILD", phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"duration={duration} obj={objects} mass={total_living_mass} birth/k={birth_rate:.1f}"
                )

            if not self.in_mass_extinction and (death_rate >= 80.0 or risk >= 0.55 or pressure >= 0.65):
                self.in_mass_extinction = True
                self.mass_extinction_start_tick = tick
                self.mass_extinction_peak_pressure = pressure
                self._chronicle(
                    tick, "MASS_EXTINCTION_START", phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"death/k={death_rate:.1f} obj={objects} mass={total_living_mass}"
                )
            elif self.in_mass_extinction:
                self.mass_extinction_peak_pressure = max(self.mass_extinction_peak_pressure, pressure)
                if death_rate < 35.0 and pressure < 0.35 and risk < 0.40:
                    duration = tick - (self.mass_extinction_start_tick or tick)
                    self._chronicle(
                        tick, "RECOVERY", phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                        details=f"duration={duration} peak_pressure={self.mass_extinction_peak_pressure:.3f} birth/k={birth_rate:.1f}"
                    )
                    self.in_mass_extinction = False
                    self.mass_extinction_start_tick = None
                    self.mass_extinction_peak_pressure = 0.0

            dom = float(dynasty.get("dynasty_dominance", 0.0) or 0.0)
            leader = dynasty.get("dynasty_leader_id")

            # Dominance shift: new ruling family, even before absolute dominance.
            if leader is not None and dom >= 0.35 and self.last_dominant_family is not None and leader != self.last_dominant_family:
                old = self.last_dominant_family
                self._chronicle(
                    tick, "DOMINANCE_SHIFT", family=leader, phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"old_family={old} new_family={leader} share={dom:.3f} mass={dynasty.get('dynasty_mass')}"
                )
                self.last_dominant_family = leader
            elif leader is not None and dom >= 0.35 and self.last_dominant_family is None:
                self.last_dominant_family = leader

            if leader is not None and dom >= 0.50 and leader not in self.dominance_reported_for_family:
                self.dominance_reported_for_family.add(leader)
                self.last_dominant_family = leader
                self._chronicle(
                    tick, "DYNASTY_DOMINANT", family=leader, phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"share={dom:.3f} living={dynasty.get('dynasty_living')} mass={dynasty.get('dynasty_mass')}"
                )

            if leader is not None and dom >= 0.70 and leader not in self.super_dynasty_reported_for_family:
                self.super_dynasty_reported_for_family.add(leader)
                self._chronicle(
                    tick, "NEW_SUPER_DYNASTY", family=leader, phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                    details=f"share={dom:.3f} living={dynasty.get('dynasty_living')} mass={dynasty.get('dynasty_mass')} survival={demo.get('demo_survival_ratio',0):.3f}"
                )

            # Detect family extinction when a family that was alive disappears.
            current_counts = {}
            for tr in self.tracks.values():
                if tr.get("alive", False) and tick - tr.get("last_seen", tick) <= self.track_missing_grace:
                    fid = tr.get("family_id")
                    current_counts[fid] = current_counts.get(fid, 0) + 1
            for fid, prev_count in list(self.family_live_counts_prev.items()):
                if prev_count > 0 and current_counts.get(fid, 0) == 0:
                    self._chronicle(
                        tick, "DYNASTY_EXTINCT", family=fid, phase=evo_phase, pressure=pressure, risk=risk, cause=cause,
                        details=f"previous_living={prev_count}"
                    )
            self.family_live_counts_prev = current_counts

    def _story_era_name(self, tick: int, alive: bool, growth_phase: str, evo: dict, demo: dict, dynasty: dict,
                            ecosystem_health: float, fragmentation_index: float, objects: int, total_living_mass: int):
            pressure = float(evo.get("evo_pressure", 0.0) or 0.0)
            risk = float(evo.get("evo_extinction_risk", 0.0) or 0.0)
            adapt = float(evo.get("evo_adapt", 0.0) or 0.0)
            dom = float(dynasty.get("dynasty_dominance", 0.0) or 0.0)
            death_rate = float(demo.get("demo_death_rate_1000", 0.0) or 0.0)
            birth_rate = float(demo.get("demo_birth_rate_1000", 0.0) or 0.0)

            if not alive or objects <= 0 or total_living_mass <= 0:
                return "Genesis"
            if risk >= 0.60 or pressure >= 0.65 or death_rate >= 90.0:
                return "Extinction"
            if pressure >= 0.45 or risk >= 0.45:
                return "Crisis"
            if growth_phase == "birth" or tick < 500:
                return "Birth"
            if self.ecosystem_collapsed and objects >= 3:
                return "Rebuild"
            if growth_phase == "expanding" or birth_rate > death_rate * 1.6:
                return "Expansion"
            if fragmentation_index >= 0.060 or growth_phase == "reorganizing":
                return "Fragmentation"
            if dom >= 0.60:
                return "Dynasty"
            if ecosystem_health >= 0.74 and adapt >= 0.70 and pressure < 0.25:
                return "Equilibrium"
            if growth_phase == "declining":
                return "Decline"
            return "Competition"

    def _era_age(self, tick: int):
            if self.story_era_start_tick is None:
                return 0
            return max(0, tick - self.story_era_start_tick)

    def _update_story_era(self, tick: int, era_name: str, pressure: float, risk: float, cause: str,
                              objects: int, total_living_mass: int, largest: int):
            # Birth is a special early era: if it appears before 500 ticks, count it from tick 0.
            # This prevents the dashboard from showing "Birth 0t" at tick 200-400.
            if self.story_era is None:
                self.story_era = era_name
                self.story_era_start_tick = 0 if era_name == "Birth" and tick < 500 else tick
                self.story_era_count = 1
                age = self._era_age(tick)
                self.story_era_line = f"ERA #{self.story_era_count} {era_name} {age}t"
                self._chronicle(
                    tick, "STORY_ERA_BEGIN", phase=era_name, pressure=pressure, risk=risk, cause=cause,
                    details=f"era={era_name} age={age} obj={objects} mass={total_living_mass} L={largest}",
                    severity="MAJOR",
                )
                return self.story_era_line

            # Candidate smoothing: do not switch eras on a one-tick wobble.
            if era_name != self.story_era:
                if self.story_pending_era != era_name:
                    self.story_pending_era = era_name
                    self.story_pending_since = tick

                pending_age = tick - (self.story_pending_since if self.story_pending_since is not None else tick)
                current_age = self._era_age(tick)
                force_switch = era_name in ("Crisis", "Extinction", "Rebuild")
                can_switch = force_switch or (pending_age >= self.story_era_min_duration and current_age >= self.story_era_min_duration)

                if can_switch:
                    old = self.story_era
                    duration = self._era_age(tick)
                    end_sev = "HISTORIC" if duration >= 5000 else ("MAJOR" if duration >= 500 else "NORMAL")
                    self._chronicle(
                        tick, "STORY_ERA_END", phase=old, pressure=pressure, risk=risk, cause=cause,
                        details=f"era={old} duration={duration} next={era_name} obj={objects} mass={total_living_mass} L={largest}",
                        severity=end_sev,
                    )
                    begin_sev = "HISTORIC" if era_name in ("Extinction", "Rebuild", "Dynasty") else "MAJOR"
                    self.story_era = era_name
                    self.story_era_start_tick = tick
                    self.story_era_count += 1
                    self.story_pending_era = None
                    self.story_pending_since = None
                    self._chronicle(
                        tick, "STORY_ERA_BEGIN", phase=era_name, pressure=pressure, risk=risk, cause=cause,
                        details=f"era={era_name} after={old} obj={objects} mass={total_living_mass} L={largest}",
                        severity=begin_sev,
                    )
            else:
                self.story_pending_era = None
                self.story_pending_since = None

            age = self._era_age(tick)
            self.story_era_line = f"ERA #{self.story_era_count} {self.story_era} {age}t"
            return self.story_era_line

