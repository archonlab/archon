#!/usr/bin/env python3
"""
Universe Search Evolution Policy v24.4

Single-owner adaptive policy layer between normalized research intent and Universe Search.
It does not know cellular automata internals. It translates high-level research
intent into generation-building parameters. This module alone owns ratio adjustment:
- explore / exploit / control allocation
- adaptive mutation intensity
- local-neighbourhood search allocation
- compact policy snapshots for logs

Safe design goal: if anything is missing or malformed, return a conservative
legacy-like policy instead of crashing the search.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


POLICY_VERSION = "v24.5 Evolution Policy + Scientific State Feedback"


def _sf(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _si(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _norm3(explore: float, exploit: float, control: float) -> Tuple[float, float, float]:
    explore = max(0.0, explore)
    exploit = max(0.0, exploit)
    control = max(0.0, control)
    total = explore + exploit + control
    if total <= 0:
        return 0.35, 0.45, 0.20
    return explore / total, exploit / total, control / total


def _action_text(plan: Any) -> str:
    bits: List[str] = []
    try:
        for a in getattr(plan, "actions", []) or []:
            if isinstance(a, dict):
                for k in ("title", "name", "action", "type", "mode", "kind", "description"):
                    if a.get(k):
                        bits.append(str(a.get(k)))
            else:
                bits.append(str(a))
    except Exception:
        pass
    try:
        bits.extend([str(x) for x in (getattr(plan, "priorities", []) or [])])
    except Exception:
        pass
    return " ".join(bits).lower()


def _intent_modes(plan: Any) -> set[str]:
    """Collect explicit structured modes without interpreting them twice."""
    modes: set[str] = set()
    try:
        for action in getattr(plan, "actions", []) or []:
            if not isinstance(action, dict):
                continue
            mode = str(action.get("mode") or "").strip().lower()
            if mode:
                modes.add(mode)
            action_type = str(action.get("type") or action.get("kind") or "").strip().lower()
            if action_type in {"explore", "exploit", "control", "local", "replicate", "replication"}:
                modes.add(action_type)
    except Exception:
        pass
    return modes


@dataclass
class EvolutionPolicy:
    version: str = POLICY_VERSION
    active: bool = False
    mode: str = "legacy"
    stage: str = "unknown"
    trend: str = "unknown"
    maturity: float = 0.0
    risk: float = 0.0

    explore_ratio: float = 0.35
    exploit_ratio: float = 0.45
    control_ratio: float = 0.20
    local_ratio: float = 0.0

    mutation_rate: float = 0.06
    mutation_intensity: float = 0.08
    crossover_bias: float = 0.50
    elite_fraction: float = 0.10
    random_fraction: float = 0.35
    control_fraction: float = 0.20
    neighbourhood_radius: int = 1
    replication_bias: float = 0.0

    population_size: int = 80
    elite_count: int = 8
    target_explore: int = 0
    target_exploit: int = 0
    target_control: int = 0
    target_local: int = 0

    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_evolution_policy(
    plan: Any,
    population_size: int,
    elite_count: int,
    random_immigrants: int = 0,
) -> EvolutionPolicy:
    """Create a safe adaptive policy from ResearchPlan-like object."""
    p = EvolutionPolicy(population_size=int(population_size), elite_count=int(elite_count))
    p.active = bool(plan is not None and getattr(plan, "active", False))

    if not p.active:
        p.mode = "legacy"
        p.reasons.append("no active research plan")
        remaining = max(0, population_size - elite_count)
        p.target_explore = min(max(0, random_immigrants), remaining)
        p.target_exploit = max(0, remaining - p.target_explore)
        p.target_control = 0
        return p

    p.mode = "research_guided_adaptive"
    p.stage = str(getattr(plan, "stage", "unknown") or "unknown")
    p.trend = str(getattr(plan, "trend", "unknown") or "unknown")
    p.maturity = _clamp(_sf(getattr(plan, "maturity", 0.0)), 0.0, 1.0)
    p.risk = _clamp(_sf(getattr(plan, "risk", 0.0)), 0.0, 1.0)

    ratios = getattr(plan, "ratios", {}) or {}
    explore, exploit, control = _norm3(
        _sf(ratios.get("explore", 0.35)),
        _sf(ratios.get("exploit", 0.45)),
        _sf(ratios.get("control", 0.20)),
    )
    p.reasons.append("neutral baseline received from ResearchBridge")

    # Interpret Director actions and current-cycle directives exactly once here.
    text = _action_text(plan)
    modes = _intent_modes(plan)
    if "control" in modes or "negative" in text or "control" in text:
        control += 0.06
        p.reasons.append("control intent")
    if "explore" in modes or "independent" in text or "divers" in text or "explore" in text:
        explore += 0.08
        p.reasons.append("exploration intent")
    if "exploit" in modes:
        exploit += 0.06
        p.reasons.append("exploitation intent")
    if "local" in modes or "neighbour" in text or "neighborhood" in text or "local" in text:
        p.local_ratio += 0.14
        exploit += 0.04
        p.reasons.append("local neighbourhood intent")
    if "replicate" in modes or "replication" in modes or "replicate" in text:
        p.replication_bias += 0.20
        exploit += 0.06
        p.reasons.append("replication intent")

    if p.risk >= 0.65:
        control += 0.06
        explore += 0.04
        exploit -= 0.10
        p.reasons.append("high research risk")
    if p.maturity < 0.35:
        explore += 0.06
        control += 0.03
        exploit -= 0.09
        p.reasons.append("early maturity")
    scientific_state = getattr(plan, "scientific_state", {}) or {}
    if hasattr(scientific_state, "to_dict"):
        scientific_state = scientific_state.to_dict()
    if not isinstance(scientific_state, dict):
        scientific_state = {}

    adaptive_trend = str(scientific_state.get("adaptive_trend") or "").upper()
    stagnation_generations = _si(scientific_state.get("stagnation_generations"), 0)
    progress_score = _clamp(_sf(scientific_state.get("progress_score"), 0.0), 0.0, 1.0)
    diversity_gain = _sf(scientific_state.get("diversity_gain"), 0.0)
    novelty_gain = _sf(scientific_state.get("novelty_gain"), 0.0)
    new_discoveries = _si(scientific_state.get("new_discoveries"), 0)
    positive_trials = _si(scientific_state.get("positive_trials"), 0)

    if stagnation_generations >= 4:
        explore += min(0.16, 0.04 + 0.025 * stagnation_generations)
        exploit -= 0.08
        p.reasons.append(f"scientific-state stagnation x{stagnation_generations}")
    elif stagnation_generations >= 2:
        explore += 0.06
        exploit -= 0.03
        p.reasons.append(f"scientific-state plateau x{stagnation_generations}")

    if adaptive_trend == "BREAKTHROUGH":
        exploit += 0.10
        control += 0.04
        explore -= 0.08
        p.reasons.append("scientific-state breakthrough consolidation")
    elif adaptive_trend == "IMPROVING":
        exploit += 0.05
        explore -= 0.02
        p.reasons.append("scientific-state improving")
    elif adaptive_trend == "STAGNATING":
        explore += 0.07
        p.reasons.append("scientific-state stagnating")

    if new_discoveries > 0 and positive_trials <= 0:
        control += min(0.10, 0.02 * new_discoveries)
        p.reasons.append("new discoveries need validation")
    if positive_trials >= 2:
        exploit += min(0.08, 0.02 * positive_trials)
        p.replication_bias += 0.08
        p.reasons.append("positive trial replication")
    if diversity_gain < -0.04:
        explore += 0.07
        p.reasons.append("diversity decline correction")
    if novelty_gain < -0.04:
        explore += 0.05
        p.reasons.append("novelty decline correction")
    if progress_score >= 0.45:
        control += 0.03
        exploit += 0.03
        p.reasons.append("high progress consolidation")

    if "stagnat" in p.trend.lower():
        explore += 0.12
        exploit -= 0.08
        p.reasons.append("stagnation escape")
    elif "improv" in p.trend.lower():
        exploit += 0.08
        explore -= 0.04
        p.reasons.append("improving trend")

    explore, exploit, control = _norm3(explore, exploit, control)
    p.explore_ratio = round(explore, 4)
    p.exploit_ratio = round(exploit, 4)
    p.control_ratio = round(control, 4)

    # Policy parameters. Mutation rises with exploration/risk and drops with maturity/replication.
    mutation = 0.035 + explore * 0.14 + control * 0.04 + p.risk * 0.035 - p.maturity * 0.025
    if p.replication_bias > 0:
        mutation *= 0.88
    p.mutation_rate = round(_clamp(mutation, 0.015, 0.24), 4)
    p.mutation_intensity = round(_clamp(0.04 + p.mutation_rate * 0.90 + explore * 0.08, 0.03, 0.35), 4)
    p.crossover_bias = round(_clamp(0.35 + exploit * 0.40 + p.replication_bias * 0.15, 0.25, 0.90), 4)
    p.local_ratio = round(_clamp(p.local_ratio + max(0.0, exploit - 0.30) * 0.12, 0.0, 0.35), 4)
    p.neighbourhood_radius = int(1 + round(_clamp(p.mutation_intensity * 10, 0, 3)))

    p.elite_fraction = round(_clamp(elite_count / max(1, population_size), 0.02, 0.30), 4)
    p.random_fraction = p.explore_ratio
    p.control_fraction = p.control_ratio

    remaining = max(0, int(population_size) - int(elite_count))
    target_explore = int(round(remaining * p.explore_ratio))
    target_control = int(round(remaining * p.control_ratio))
    target_exploit = max(0, remaining - target_explore - target_control)

    # Keep at least the old random-immigrant floor inside exploration when possible.
    if random_immigrants > 0 and remaining > 0:
        target_explore = max(target_explore, min(int(random_immigrants), remaining))
    overflow = max(0, target_explore + target_control + target_exploit - remaining)
    if overflow:
        target_exploit = max(0, target_exploit - overflow)

    target_local = int(round(target_exploit * p.local_ratio))
    target_local = min(target_local, target_exploit)
    target_exploit = max(0, target_exploit - target_local)

    p.target_explore = int(target_explore)
    p.target_exploit = int(target_exploit)
    p.target_control = int(target_control)
    p.target_local = int(target_local)
    return p



@dataclass
class EvolutionStrategy:
    version: str = "v24.3 Evolution Strategy"
    name: str = "BALANCED_RESEARCH"
    stage: str = "unknown"
    goal: str = "balanced research progress"
    mutation_profile: str = "normal"
    selection_profile: str = "mixed"
    exploration_pressure: float = 0.0
    exploitation_pressure: float = 0.0
    control_pressure: float = 0.0
    local_search_pressure: float = 0.0
    risk_posture: str = "normal"
    expected_gain: str = "medium"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_evolution_strategy(policy: EvolutionPolicy) -> EvolutionStrategy:
    """Translate numeric policy into a named research strategy.

    This is deliberately conservative: it does not change scoring. It gives the
    search loop an explicit high-level mode that can be logged, compared and used
    by future guided mutation modules.
    """
    p = policy or EvolutionPolicy()
    ex = _sf(getattr(p, "explore_ratio", 0.0))
    xp = _sf(getattr(p, "exploit_ratio", 0.0))
    ct = _sf(getattr(p, "control_ratio", 0.0))
    lc = _sf(getattr(p, "local_ratio", 0.0))
    risk = _sf(getattr(p, "risk", 0.0))
    maturity = _sf(getattr(p, "maturity", 0.0))
    trend = str(getattr(p, "trend", "") or "").lower()
    stage = str(getattr(p, "stage", "unknown") or "unknown")

    st = EvolutionStrategy(stage=stage)
    st.exploration_pressure = round(ex, 4)
    st.exploitation_pressure = round(xp, 4)
    st.control_pressure = round(ct, 4)
    st.local_search_pressure = round(lc, 4)

    if risk >= 0.65:
        st.risk_posture = "cautious_high_risk"
        st.notes.append("high research risk keeps negative controls active")
    elif maturity >= 0.65:
        st.risk_posture = "mature_low_risk"
    else:
        st.risk_posture = "normal"

    if "stagn" in trend:
        st.name = "DIVERSIFY_ESCAPE"
        st.goal = "escape stagnation with broader search"
        st.mutation_profile = "high"
        st.selection_profile = "diversity_first"
        st.expected_gain = "high_if_new_family_found"
        st.notes.append("trend indicates stagnation")
    elif ct >= 0.30 and risk >= 0.55:
        st.name = "CONTROL_CALIBRATION"
        st.goal = "increase negative-control coverage and reduce false positives"
        st.mutation_profile = "moderate"
        st.selection_profile = "controls_plus_exploration"
        st.expected_gain = "high_for_validation"
        st.notes.append("control pressure dominates because risk is high")
    elif ex >= 0.48:
        st.name = "EXPLORATION_SWEEP"
        st.goal = "collect independent rules and widen the search space"
        st.mutation_profile = "high"
        st.selection_profile = "novelty_and_diversity"
        st.expected_gain = "high_for_discovery"
        st.notes.append("exploration pressure is dominant")
    elif lc >= 0.12 or xp >= 0.48:
        st.name = "LOCAL_REPLICATION"
        st.goal = "replicate and refine promising candidates"
        st.mutation_profile = "focused"
        st.selection_profile = "elite_neighbourhoods"
        st.expected_gain = "medium_high_for_replication"
        st.notes.append("local/exploit pressure is dominant")
    elif maturity >= 0.55 and risk < 0.45:
        st.name = "CONSENSUS_REFINEMENT"
        st.goal = "stabilize mature principles and reduce noise"
        st.mutation_profile = "low"
        st.selection_profile = "elite_and_replication"
        st.expected_gain = "medium_for_confidence"
        st.notes.append("maturity is high enough for refinement")
    else:
        st.name = "BALANCED_RESEARCH"
        st.goal = "balance discovery, replication and controls"
        st.mutation_profile = "normal"
        st.selection_profile = "mixed"
        st.expected_gain = "medium"

    return st


def write_strategy_snapshot(results_dir: Path, policy: EvolutionPolicy, strategy: EvolutionStrategy, extra: Optional[Dict[str, Any]] = None) -> Path:
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "evolution_strategy_status.json"
    payload = {
        "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "strategy": strategy.to_dict(),
        "policy": policy.to_dict() if policy is not None else None,
    }
    if extra:
        payload["extra"] = extra
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def write_policy_snapshot(results_dir: Path, policy: EvolutionPolicy, extra: Optional[Dict[str, Any]] = None) -> Path:
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "evolution_policy_status.json"
    payload = policy.to_dict()
    payload["written_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if extra:
        payload["extra"] = extra
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def append_policy_log(results_dir: Path, payload: Dict[str, Any]) -> Path:
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "adaptive_evolution_log.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        else:
            data = []
    except Exception:
        data = []
    item = dict(payload)
    item["written_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data.append(item)
    data = data[-300:]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path
