"""Conservative shadow bridge from live Observer signals to lifecycle fields.

The bridge gives already-existing detectors explicit scientific meanings.  It
does not append legacy events, change thresholds, stop a run, or classify a
world.  In particular, the historical size-based ``life-start`` signal is
treated as population emergence, never as evidence that life has emerged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ORGANIZATION_VERDICTS = frozenset({
    "ADAPTIVE_ORGANIZATION",
    "LIFE_CANDIDATE",
})


@dataclass
class ObserverLifecycleSignalBridge:
    """Track the first unambiguous lifecycle transitions in one Observer run."""

    extinction_grace_ticks: int
    structure_birth_tick: int | None = None
    population_emergence_tick: int | None = None
    organization_onset_tick: int | None = None
    organization_onset_confidence: float | None = None
    life_evidence_onset_tick: int | None = None
    life_evidence_onset_confidence: float | None = None
    population_collapse_tick: int | None = None
    ecological_collapse_tick: int | None = None
    structural_extinction_tick: int | None = None
    _empty_since_tick: int | None = None
    _ecology_established_tick: int | None = None
    _previous_ecosystem_collapsed: bool | None = None

    def __post_init__(self) -> None:
        self.extinction_grace_ticks = max(1, int(self.extinction_grace_ticks))

    def reset(self) -> None:
        """Reset run-local transition memory without touching Observer state."""

        self.structure_birth_tick = None
        self.population_emergence_tick = None
        self.organization_onset_tick = None
        self.organization_onset_confidence = None
        self.life_evidence_onset_tick = None
        self.life_evidence_onset_confidence = None
        self.population_collapse_tick = None
        self.ecological_collapse_tick = None
        self.structural_extinction_tick = None
        self._empty_since_tick = None
        self._ecology_established_tick = None
        self._previous_ecosystem_collapsed = None

    def observe(
        self,
        *,
        tick: int,
        defect_cells: int,
        alive: bool,
        birth_tick: int | None,
        collapse_tick: int | None,
        ecosystem_collapsed: bool,
        ecosystem_collapse_tick: int | None,
        life_evidence_verdict: str | None,
        life_evidence_gate_passed: bool,
        life_evidence_confidence: float | None,
        objects: int = 0,
        total_living_mass: int = 0,
        largest: int = 0,
        evolution_pressure: float | None = None,
        extinction_risk: float | None = None,
    ) -> dict[str, Any]:
        """Observe one sampled state and return explicit Stage 2A fields."""

        tick = int(tick)
        defect_cells = max(0, int(defect_cells))
        verdict = str(life_evidence_verdict or "").strip().upper()
        evidence_confidence = _bounded_confidence(life_evidence_confidence)
        objects = max(0, int(objects))
        total_living_mass = max(0, int(total_living_mass))
        largest = max(0, int(largest))
        pressure = _bounded_confidence(evolution_pressure)
        risk = _bounded_confidence(extinction_risk)
        detector_collapsed = bool(ecosystem_collapsed)

        if defect_cells > 0:
            if self.structure_birth_tick is None:
                self.structure_birth_tick = tick
            self._empty_since_tick = None
        elif self.structure_birth_tick is not None:
            if self._empty_since_tick is None:
                self._empty_since_tick = tick
            if (
                self.structural_extinction_tick is None
                and tick - self._empty_since_tick >= self.extinction_grace_ticks
            ):
                self.structural_extinction_tick = self._empty_since_tick

        # ``alive`` is the established operational population detector.  Its
        # semantics are deliberately narrower than organization or life.
        if alive and self.population_emergence_tick is None:
            self.population_emergence_tick = (
                int(birth_tick) if birth_tick is not None else tick
            )

        if (
            verdict in ORGANIZATION_VERDICTS
            and self.organization_onset_tick is None
        ):
            self.organization_onset_tick = tick
            self.organization_onset_confidence = evidence_confidence

        if (
            verdict == "LIFE_CANDIDATE"
            and bool(life_evidence_gate_passed)
            and self.life_evidence_onset_tick is None
        ):
            self.life_evidence_onset_tick = tick
            self.life_evidence_onset_confidence = evidence_confidence

        population_collapse = _confirmed_tick(collapse_tick, current_tick=tick)
        if (
            population_collapse is not None
            and self.population_emergence_tick is not None
            and not alive
            and self.population_collapse_tick is None
        ):
            self.population_collapse_tick = population_collapse

        # Chronicle can label a sparse initial state as ECOSYSTEM_COLLAPSE.
        # Ontology requires temporal evidence instead: first observe a formed
        # ecology, then a detector transition accompanied by deterioration.
        ecology_formed = (
            not detector_collapsed
            and objects >= 6
            and total_living_mass > max(60, largest * 3)
            and pressure is not None
            and pressure < 0.45
        )
        if ecology_formed and self._ecology_established_tick is None:
            self._ecology_established_tick = tick

        ecological_collapse = _confirmed_tick(
            ecosystem_collapse_tick,
            current_tick=tick,
        )
        collapse_transition = (
            self._previous_ecosystem_collapsed is False
            and detector_collapsed
        )
        ecology_deteriorated = (
            objects <= 2
            and (
                (risk is not None and risk >= 0.50)
                or total_living_mass <= max(10, largest * 2)
            )
        )
        if (
            self._ecology_established_tick is not None
            and collapse_transition
            and ecology_deteriorated
            and ecological_collapse is not None
            and ecological_collapse > self._ecology_established_tick
            and self.ecological_collapse_tick is None
        ):
            self.ecological_collapse_tick = ecological_collapse
        self._previous_ecosystem_collapsed = detector_collapsed

        result: dict[str, Any] = {
            "structure_birth_tick": self.structure_birth_tick,
            "population_emergence_tick": self.population_emergence_tick,
            "organization_onset_tick": self.organization_onset_tick,
            "life_evidence_onset_tick": self.life_evidence_onset_tick,
            "population_collapse_tick": self.population_collapse_tick,
            "ecological_collapse_tick": self.ecological_collapse_tick,
            "structural_extinction_tick": self.structural_extinction_tick,
        }
        if self.structure_birth_tick is not None:
            result["structure_birth_tick_confidence"] = 1.0
        if self.population_emergence_tick is not None:
            result["population_emergence_tick_confidence"] = 1.0
        if self.organization_onset_tick is not None:
            result["organization_onset_tick_confidence"] = (
                self.organization_onset_confidence
            )
        if self.life_evidence_onset_tick is not None:
            result["life_evidence_onset_tick_confidence"] = (
                self.life_evidence_onset_confidence
            )
        if self.population_collapse_tick is not None:
            result["population_collapse_tick_confidence"] = 1.0
        if self.ecological_collapse_tick is not None:
            result["ecological_collapse_tick_confidence"] = 0.75
        if self.structural_extinction_tick is not None:
            result["structural_extinction_tick_confidence"] = 1.0
        return result


def _bounded_confidence(value: Any) -> float | None:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _confirmed_tick(value: Any, *, current_tick: int) -> int | None:
    """Accept only an initialized detector tick from the observed past."""

    if value is None or isinstance(value, bool):
        return None
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return None
    if candidate < 0 or candidate > int(current_tick):
        return None
    return candidate


__all__ = [
    "ORGANIZATION_VERDICTS",
    "ObserverLifecycleSignalBridge",
]
