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


class ObserverGeometryMorphologyMixin:
    @staticmethod
    def _median(values):
            values = sorted(values)
            n = len(values)
            if n == 0:
                return 0.0
            mid = n // 2
            return float(values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2)

    def _background_by_parity(self, grid):
            """Stage 11: reduce Python overhead while preserving identical results."""
            even = []
            odd = []
            even_append = even.append
            odd_append = odd.append

            h = len(grid)
            w = len(grid[0]) if h else 0

            for y in range(h):
                row = grid[y]
                if y & 1:
                    for x in range(0, w, 2):
                        odd_append(float(row[x]))
                    for x in range(1, w, 2):
                        even_append(float(row[x]))
                else:
                    for x in range(0, w, 2):
                        even_append(float(row[x]))
                    for x in range(1, w, 2):
                        odd_append(float(row[x]))

            return self._median(even), self._median(odd)

    def _defect_mask(self, grid):
            """Return defect mask, defect count and center of mass.

            Stage 10: same logic as before, but with fewer Python lookups inside
            the hot nested loop. This keeps behavior unchanged.
            """
            h = len(grid)
            w = len(grid[0]) if h else 0
            even_med, odd_med = self._background_by_parity(grid)

            mask = [[False] * w for _ in range(h)]
            threshold = self.threshold

            count = 0
            sx = 0.0
            sy = 0.0

            for y in range(h):
                row = grid[y]
                mask_row = mask[y]

                # Parity alternates across x. Start depends on y.
                bg_even = even_med if (y & 1) == 0 else odd_med
                bg_odd = odd_med if (y & 1) == 0 else even_med

                for x in range(w):
                    bg = bg_odd if (x & 1) else bg_even
                    if abs(float(row[x]) - bg) >= threshold:
                        mask_row[x] = True
                        count += 1
                        sx += x
                        sy += y

            center = (sx / count, sy / count) if count else (None, None)
            return mask, count, center

    def _components(self, mask):
            records = self._component_records(mask)
            return [r["size"] for r in records]

    def _component_records(self, mask):
            h = len(mask)
            w = len(mask[0]) if h else 0
            seen = [[False] * w for _ in range(h)]
            records = []
            dirs=((1,0),(-1,0),(0,1),(0,-1))
            min_cells=self.min_object_cells

            for y0,row in enumerate(mask):
                seen_row=seen[y0]
                for x0,alive in enumerate(row):
                    if (not alive) or seen_row[x0]:
                        continue

                    q=deque([(x0,y0)])
                    seen_row[x0]=True
                    cells=[]
                    sx=0.0
                    sy=0.0

                    while q:
                        x,y=q.popleft()
                        cells.append((x,y))
                        sx+=x
                        sy+=y
                        for dx,dy in dirs:
                            nx = x + dx
                            ny = y + dy
                            if getattr(
                                self,
                                "boundary_mode",
                                "wrap",
                            ) == "wrap":
                                nx %= w
                                ny %= h
                            elif not (
                                0 <= nx < w
                                and 0 <= ny < h
                            ):
                                continue
                            if mask[ny][nx] and not seen[ny][nx]:
                                seen[ny][nx]=True
                                q.append((nx,ny))

                    size=len(cells)
                    if size>=min_cells:
                        records.append({
                            "size":size,
                            "cx":sx/size,
                            "cy":sy/size,
                            "cells":cells,
                        })

            records.sort(key=lambda r:r["size"],reverse=True)
            return records

    def _update_morphology_layer(self, tick: int, component_records, total_living_mass: int):
            """Observe colony morphology without changing simulation results.

            Stage 13.3 completes the first morphology layer:
            shape class, morphology score, transitions, stable-shape age,
            dominant class, and major morphology events.
            """
            def register_class(morph_class: str, change: float, score: float):
                prev = self.morphology_prev_class
                event = ""

                self.morphology_class_counts[morph_class] = self.morphology_class_counts.get(morph_class, 0) + 1
                self.morphology_dominant_class = max(self.morphology_class_counts, key=self.morphology_class_counts.get)

                if prev is None:
                    self.morphology_prev_class = morph_class
                    self.morphology_class_start_tick = tick
                    event = f"morph-start:{morph_class}"
                elif morph_class != prev:
                    old_age = tick - (self.morphology_class_start_tick if self.morphology_class_start_tick is not None else tick)
                    self.morphology_transition_count += 1
                    if change >= 0.055 or old_age >= 250:
                        self.morphology_major_transition_count += 1
                        event = f"morph-shift:{prev}->{morph_class} age={old_age} chg={change:.3f}"
                        self.add_event(tick, "morph-shift", event)
                    else:
                        event = f"morph-flicker:{prev}->{morph_class}"
                    self.morphology_prev_class = morph_class
                    self.morphology_class_start_tick = tick

                self.morphology_score_peak = max(self.morphology_score_peak, score)
                self.morphology_last_event = event or self.morphology_last_event

            def empty_item(change=0.0):
                signature = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                if change <= 0.015:
                    self.morphology_stable_ticks += 1
                else:
                    self.morphology_stable_ticks = 0
                self.morphology_longest_stable_ticks = max(self.morphology_longest_stable_ticks, self.morphology_stable_ticks)
                self.morphology_prev_signature = signature
                morph_class = "none"
                score = 0.0
                register_class(morph_class, change, score)
                line = f"MORPH none score=0.00 chg={change:.3f} stable={self.morphology_stable_ticks}"
                self.morphology_line = line
                item = {
                    "morphology_compactness": 0.0,
                    "morphology_aspect": 0.0,
                    "morphology_edge_complexity": 0.0,
                    "morphology_bbox_fill": 0.0,
                    "morphology_symmetry": 0.0,
                    "morphology_branching": 0.0,
                    "morphology_filament_score": 0.0,
                    "morphology_lattice_score": 0.0,
                    "morphology_score": score,
                    "morphology_change_rate": change,
                    "morphology_stability_ticks": self.morphology_stable_ticks,
                    "morphology_longest_stable_ticks": self.morphology_longest_stable_ticks,
                    "morphology_peak_complexity": self.morphology_peak_complexity,
                    "morphology_score_peak": self.morphology_score_peak,
                    "morphology_transition_count": self.morphology_transition_count,
                    "morphology_major_transition_count": self.morphology_major_transition_count,
                    "morphology_class": morph_class,
                    "morphology_dominant_class": self.morphology_dominant_class,
                    "morphology_last_event": self.morphology_last_event,
                    "morphology_line": line,
                }
                self.morphology_history.append({"tick": tick, **item})
                return item

            if not component_records or total_living_mass <= 0:
                change = 0.0 if self.morphology_prev_signature is None else 1.0
                return empty_item(change)

            records = component_records[:12]
            total_weight = 0
            compact_sum = 0.0
            aspect_sum = 0.0
            edge_sum = 0.0
            fill_sum = 0.0
            symmetry_sum = 0.0
            branching_sum = 0.0
            filament_sum = 0.0
            lattice_sum = 0.0

            for rec in records:
                cells = rec.get("cells") or []
                size = int(rec.get("size", 0) or len(cells))
                if size <= 0 or not cells:
                    continue

                min_x = min_y = 10**9
                max_x = max_y = -1
                for x, y in cells:
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    if y > max_y:
                        max_y = y

                bw = max(1, max_x - min_x + 1)
                bh = max(1, max_y - min_y + 1)
                bbox_area = max(1, bw * bh)
                bbox_fill = size / bbox_area
                aspect = max(bw, bh) / max(1, min(bw, bh))

                cellset = set(cells)
                perimeter = 0
                endpoints = 0
                junctions = 0
                symmetry_hits = 0

                for x, y in cells:
                    n = 0
                    if (x + 1, y) in cellset:
                        n += 1
                    else:
                        perimeter += 1
                    if (x - 1, y) in cellset:
                        n += 1
                    else:
                        perimeter += 1
                    if (x, y + 1) in cellset:
                        n += 1
                    else:
                        perimeter += 1
                    if (x, y - 1) in cellset:
                        n += 1
                    else:
                        perimeter += 1

                    if n <= 1:
                        endpoints += 1
                    elif n >= 3:
                        junctions += 1

                    mx = min_x + max_x - x
                    my = min_y + max_y - y
                    if (mx, y) in cellset:
                        symmetry_hits += 1
                    if (x, my) in cellset:
                        symmetry_hits += 1

                compactness = (4.0 * math.pi * size) / max(1.0, float(perimeter * perimeter))
                edge_complexity = perimeter / max(1.0, math.sqrt(size))
                symmetry = symmetry_hits / max(1, 2 * size)
                branching = (endpoints + 2 * junctions) / max(1, size)
                filament_score = max(0.0, min(1.0, (aspect - 1.0) / 4.0 + (1.0 - bbox_fill) * 0.35))
                lattice_score = max(0.0, min(1.0, bbox_fill * 0.55 + symmetry * 0.25 + max(0.0, 1.0 - branching) * 0.20))

                total_weight += size
                compact_sum += compactness * size
                aspect_sum += aspect * size
                edge_sum += edge_complexity * size
                fill_sum += bbox_fill * size
                symmetry_sum += symmetry * size
                branching_sum += branching * size
                filament_sum += filament_score * size
                lattice_sum += lattice_score * size

            if total_weight <= 0:
                return empty_item(0.0 if self.morphology_prev_signature is None else 1.0)

            compactness = compact_sum / total_weight
            aspect = aspect_sum / total_weight
            edge_complexity = edge_sum / total_weight
            bbox_fill = fill_sum / total_weight
            symmetry = symmetry_sum / total_weight
            branching = branching_sum / total_weight
            filament_score = filament_sum / total_weight
            lattice_score = lattice_sum / total_weight

            if filament_score >= 0.62 and aspect >= 2.3:
                morph_class = "FILAMENT"
            elif lattice_score >= 0.62 and bbox_fill >= 0.45:
                morph_class = "LATTICE"
            elif branching >= 0.42 and edge_complexity >= 4.0:
                morph_class = "DENDRITE"
            elif compactness >= 0.20 and bbox_fill >= 0.50:
                morph_class = "BLOB"
            elif edge_complexity >= 5.0 or bbox_fill <= 0.32:
                morph_class = "RAGGED"
            else:
                morph_class = "MIXED"

            signature = (
                round(compactness, 4),
                round(aspect, 4),
                round(edge_complexity, 4),
                round(bbox_fill, 4),
                round(symmetry, 4),
                round(branching, 4),
                round(filament_score, 4),
            )

            if self.morphology_prev_signature is None:
                change = 0.0
            else:
                prev = self.morphology_prev_signature
                change = sum(abs(signature[i] - prev[i]) for i in range(len(signature))) / len(signature)

            if change <= 0.015:
                self.morphology_stable_ticks += 1
            else:
                self.morphology_stable_ticks = 0

            self.morphology_prev_signature = signature
            self.morphology_longest_stable_ticks = max(self.morphology_longest_stable_ticks, self.morphology_stable_ticks)
            self.morphology_peak_complexity = max(self.morphology_peak_complexity, edge_complexity)
            self.morphology_peak_change = max(self.morphology_peak_change, change)

            organization = max(0.0, min(1.0, 0.28 * symmetry + 0.24 * lattice_score + 0.20 * min(1.0, compactness * 3.0) + 0.18 * min(1.0, edge_complexity / 7.0) + 0.10 * (1.0 - min(1.0, change * 8.0))))
            diversity = max(0.0, min(1.0, 0.55 * filament_score + 0.45 * branching))
            morphology_score = max(0.0, min(1.0, 0.70 * organization + 0.30 * diversity))

            register_class(morph_class, change, morphology_score)

            line = (
                f"MORPH {morph_class} score={morphology_score:.2f} "
                f"C={compactness:.2f} A={aspect:.2f} E={edge_complexity:.2f} "
                f"F={bbox_fill:.2f} S={symmetry:.2f} B={branching:.2f} "
                f"chg={change:.3f} stable={self.morphology_stable_ticks}"
            )
            self.morphology_line = line

            item = {
                "morphology_compactness": compactness,
                "morphology_aspect": aspect,
                "morphology_edge_complexity": edge_complexity,
                "morphology_bbox_fill": bbox_fill,
                "morphology_symmetry": symmetry,
                "morphology_branching": branching,
                "morphology_filament_score": filament_score,
                "morphology_lattice_score": lattice_score,
                "morphology_score": morphology_score,
                "morphology_change_rate": change,
                "morphology_stability_ticks": self.morphology_stable_ticks,
                "morphology_longest_stable_ticks": self.morphology_longest_stable_ticks,
                "morphology_peak_complexity": self.morphology_peak_complexity,
                "morphology_score_peak": self.morphology_score_peak,
                "morphology_transition_count": self.morphology_transition_count,
                "morphology_major_transition_count": self.morphology_major_transition_count,
                "morphology_class": morph_class,
                "morphology_dominant_class": self.morphology_dominant_class,
                "morphology_last_event": self.morphology_last_event,
                "morphology_line": line,
            }
            self.morphology_history.append({"tick": tick, **item})
            return item

