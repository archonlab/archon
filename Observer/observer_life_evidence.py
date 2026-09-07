#!/usr/bin/env python3
"""Conservative competing-hypothesis model for Observer life evidence.

This layer does not alter the world or the legacy ``alive`` signal.  It asks
which explanation best fits the observed dynamics and reports evidence rather
than declaring every sufficiently large defect object alive.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable


LIFE_EVIDENCE_VERSION = "v5.1 Life Evidence Model"


def _clamp(value: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return lo


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    return sum(rows) / len(rows) if rows else 0.0


class ObserverLifeEvidenceMixin:
    """Evaluate life against non-living alternative hypotheses."""

    def _init_life_evidence_model(self) -> None:
        self.life_evidence_history = deque(maxlen=5000)
        self.life_evidence_peak = 0.0
        self.life_evidence_peak_tick = None
        self.life_evidence_verdict = "INSUFFICIENT_EVIDENCE"
        self.life_evidence_prev_verdict = None
        self.life_evidence_line = "LIFE evidence unavailable"
        self.life_evidence_event_counts = {}

    def _update_life_evidence_model(
        self,
        *,
        tick: int,
        alive: bool,
        changed: int,
        field_cells: int,
        defect_cells: int,
        objects: int,
        total_living_mass: int,
        largest: int,
        morphology: Dict[str, Any],
        lineage: Dict[str, Any],
        dynasty: Dict[str, Any],
        demo: Dict[str, Any],
        evo: Dict[str, Any],
        know: Dict[str, Any],
        fb: Dict[str, Any],
        emg: Dict[str, Any],
        val: Dict[str, Any],
        history: Dict[str, Any],
    ) -> Dict[str, Any]:
        field_cells = max(1, int(field_cells))
        activity = _clamp(changed / max(1.0, field_cells * 0.20))
        occupancy = _clamp(defect_cells / field_cells)
        localization = _clamp(1.0 - max(0.0, occupancy - 0.45) / 0.45)
        bounded_mass = _clamp(total_living_mass / max(1.0, field_cells * 0.20))
        object_support = _clamp(objects / 6.0)

        stability = _clamp(history.get("stability_index"))
        identity = _clamp(getattr(self, "identity_persistence", 0.0))
        morphology_score = _clamp(morphology.get("morphology_score"))
        shape_complexity = _mean([
            _clamp(morphology.get("morphology_edge_complexity")),
            _clamp(morphology.get("morphology_branching")),
            _clamp(1.0 - abs(_clamp(morphology.get("morphology_bbox_fill")) - 0.55) / 0.55),
        ])
        lattice = _clamp(morphology.get("morphology_lattice_score"))
        shape_change = _clamp(float(morphology.get("morphology_change_rate") or 0.0) / 0.30)

        deepest_generation = max(0, int(lineage.get("deepest_generation") or 0))
        active_families = max(0, int(lineage.get("active_families") or 0))
        lineage_depth = _clamp(deepest_generation / 4.0)
        family_support = _clamp(active_families / 3.0)
        replacement = _clamp(demo.get("demo_replacement"))
        survival = _clamp(demo.get("demo_survival_ratio"))
        turnover = _clamp(float(demo.get("demo_turnover_1000") or 0.0) / 20.0)
        reproduction = _mean([lineage_depth, family_support, replacement, min(turnover, survival)])

        adaptation = _mean([
            _clamp(evo.get("evo_adapt")),
            _clamp(know.get("knowledge_adaptation")),
            _clamp(fb.get("feedback_self_direction")),
            _clamp(fb.get("feedback_environment_impact")),
        ])
        information = _mean([
            _clamp(know.get("knowledge_memory")),
            _clamp(know.get("knowledge_score")),
            _clamp(getattr(self, "information_survival", 0.0)),
        ])
        organization = _mean([morphology_score, shape_complexity, object_support, bounded_mass])
        validation = _clamp(val.get("validation_quality"))
        emergence = _clamp(emg.get("emergence_score"))

        # Alternatives are explicit competitors, not merely penalties hidden in
        # a single life score.
        oscillation = _clamp(
            0.32 * activity + 0.30 * stability + 0.20 * lattice + 0.18 * (1.0 - shape_change)
            - 0.28 * reproduction - 0.20 * adaptation
        )
        attractor = _clamp(
            0.36 * stability + 0.28 * identity + 0.20 * localization + 0.16 * bounded_mass
            - 0.22 * reproduction - 0.14 * adaptation
        )
        crystal = _clamp(
            0.48 * lattice + 0.24 * stability + 0.18 * occupancy + 0.10 * activity
            - 0.25 * reproduction - 0.18 * adaptation
        )
        active_structure = _clamp(
            0.26 * float(bool(alive)) + 0.22 * activity + 0.20 * localization
            + 0.18 * organization + 0.14 * identity - 0.18 * reproduction
        )
        adaptive_organization = _clamp(
            0.24 * organization + 0.23 * reproduction + 0.25 * adaptation
            + 0.16 * information + 0.12 * emergence
        )

        axes = {
            "bounded_organization": _clamp(organization * localization),
            "persistent_identity": _mean([identity, stability]),
            "reproduction_lineage": reproduction,
            "adaptive_response": adaptation,
            "information_retention": information,
        }
        strong_axes = [name for name, score in axes.items() if score >= 0.42]
        independent_support = _clamp(len(strong_axes) / len(axes))
        life_raw = _clamp(
            0.21 * axes["bounded_organization"]
            + 0.20 * axes["persistent_identity"]
            + 0.23 * reproduction
            + 0.22 * adaptation
            + 0.14 * information
        )
        alternative_penalty = max(oscillation, crystal) * (1.0 - 0.55 * reproduction) * 0.30
        saturation_penalty = _clamp((occupancy - 0.70) / 0.25) * 0.22
        life_score = _clamp(life_raw - alternative_penalty - saturation_penalty)

        hypotheses = {
            "PASSIVE_OSCILLATION": oscillation,
            "STABLE_ATTRACTOR": attractor,
            "CRYSTAL_DYNAMICS": crystal,
            "ACTIVE_STRUCTURE": active_structure,
            "ADAPTIVE_ORGANIZATION": adaptive_organization,
            "LIFE_CANDIDATE": life_score,
        }
        ranked = sorted(hypotheses.items(), key=lambda row: (-row[1], row[0]))
        winner, winner_score = ranked[0]
        runner_up, runner_up_score = ranked[1]
        margin = max(0.0, winner_score - runner_up_score)

        life_gate = len(strong_axes) >= 3 and reproduction >= 0.32 and (adaptation >= 0.30 or information >= 0.42)
        strongest_nonliving = max(oscillation, attractor, crystal, active_structure)
        # Adaptive organization is supporting evidence on the road to a life
        # candidate, not a mutually exclusive non-living explanation.  A life
        # verdict may therefore sit just below ADAPTIVE_ORGANIZATION while it
        # must still match or beat every explicitly non-living alternative.
        if life_gate and life_score >= 0.62 and life_score >= strongest_nonliving - 0.03:
            verdict = "LIFE_CANDIDATE"
        elif adaptive_organization >= 0.58 and len(strong_axes) >= 3:
            verdict = "ADAPTIVE_ORGANIZATION"
        elif winner_score < 0.28:
            verdict = "INSUFFICIENT_EVIDENCE"
        else:
            verdict = winner

        coverage = _clamp(min(1.0, tick / 2000.0))
        confidence = _clamp((0.45 * winner_score + 0.30 * margin + 0.25 * validation) * (0.55 + 0.45 * coverage))
        uncertainty = _clamp(1.0 - confidence)
        positive = sorted(axes.items(), key=lambda row: (-row[1], row[0]))
        positive_labels = [f"{name}:{score:.2f}" for name, score in positive if score >= 0.32]
        alternatives = [f"{name}:{score:.2f}" for name, score in ranked if name != "LIFE_CANDIDATE"]
        warnings = []
        if occupancy >= 0.70:
            warnings.append("field saturation")
        if max(oscillation, crystal) >= life_score:
            warnings.append("non-life explanation is at least as strong as life")
        if reproduction < 0.32:
            warnings.append("lineage/reproduction evidence is weak")
        if adaptation < 0.30:
            warnings.append("adaptive-response evidence is weak")
        if validation < 0.45:
            warnings.append("observer validation quality is limited")

        if life_score > self.life_evidence_peak:
            self.life_evidence_peak = life_score
            self.life_evidence_peak_tick = tick
        if verdict != self.life_evidence_prev_verdict:
            old = self.life_evidence_prev_verdict or "NONE"
            self.life_evidence_event_counts["verdict_shift"] = self.life_evidence_event_counts.get("verdict_shift", 0) + 1
            if hasattr(self, "add_event"):
                self.add_event(tick, "life-evidence-shift", f"{old}->{verdict} confidence={confidence:.3f}")
            self.life_evidence_prev_verdict = verdict

        self.life_evidence_verdict = verdict
        self.life_evidence_line = (
            f"LIFE {verdict} score={life_score:.2f} conf={confidence:.2f} "
            f"alt={runner_up if winner == 'LIFE_CANDIDATE' else winner}:{(runner_up_score if winner == 'LIFE_CANDIDATE' else winner_score):.2f}"
        )
        result = {
            "life_evidence_version": LIFE_EVIDENCE_VERSION,
            "life_evidence_verdict": verdict,
            "life_evidence_score": life_score,
            "life_evidence_confidence": confidence,
            "life_evidence_uncertainty": uncertainty,
            "life_evidence_peak": self.life_evidence_peak,
            "life_evidence_peak_tick": self.life_evidence_peak_tick,
            "life_evidence_winner": winner,
            "life_evidence_runner_up": runner_up,
            "life_evidence_margin": margin,
            "life_evidence_gate_passed": life_gate,
            "life_evidence_strong_axes": ", ".join(strong_axes),
            "life_evidence_positive": ", ".join(positive_labels),
            "life_evidence_alternatives": ", ".join(alternatives),
            "life_evidence_warnings": "; ".join(warnings),
            "life_evidence_line": self.life_evidence_line,
            "life_evidence_axes": {key: round(value, 6) for key, value in axes.items()},
            "life_evidence_hypotheses": {key: round(value, 6) for key, value in hypotheses.items()},
        }
        self.life_evidence_history.append({"tick": tick, **result})
        return result
