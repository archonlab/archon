#!/usr/bin/env python3
"""
Universe Search v34.1 - Closed Research Cycle

Folder-safe feedback layer above ParadigmEngine.

Purpose:
- read the current scientific stack status (experiments, discoveries, theories, paradigms)
- derive a small set of research-cycle directives
- append structured cycle intent before EvolutionPolicy is built
- write cycle status/history/directives without renaming old folders

This module is deliberately conservative. It does not replace core search; it nudges the
existing ResearchBridge/EvolutionPolicy path so the scientific stack can influence the next
population schedule. EvolutionPolicy remains the sole owner of ratios.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

CYCLE_VERSION = "v34.2 Closed Research Cycle + Scientific State"
CYCLE_DIR = "observer_research_cycle"


def now_s() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, safe_float(x, lo)))


def read_json(path: Path, default: Any = None) -> Any:
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(path)


def _cycle_dir(results_dir: Path) -> Path:
    p = Path(results_dir) / CYCLE_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _status(results_dir: Path, root_name: str, subdir: str | None = None, sub_name: str | None = None) -> Dict[str, Any]:
    root = read_json(Path(results_dir) / root_name, {})
    if isinstance(root, dict) and root:
        return root
    if subdir and sub_name:
        sub = read_json(Path(results_dir) / subdir / sub_name, {})
        if isinstance(sub, dict):
            return sub
    return {}


def _collect_stack(results_dir: Path) -> Dict[str, Any]:
    r = Path(results_dir)
    return {
        "network": _status(r, "observer_network_status.json", "observer_network", "network_status.json"),
        "network_dynamics": _status(r, "network_dynamics_status.json", "observer_network", "network_dynamics_status.json"),
        "discoveries": _status(r, "discovery_status.json", "observer_discoveries", "discovery_status.json"),
        "programs": _status(r, "research_programs_status.json", "observer_research_programs", "research_programs_status.json"),
        "teams": _status(r, "research_teams_status.json", "observer_research_teams", "research_teams_status.json"),
        "experiments": _status(r, "experiment_status.json", "observer_experiments", "experiment_status.json"),
        "theories": _status(r, "theory_engine_status.json", "observer_theories", "theory_status.json"),
        "paradigms": _status(r, "paradigm_engine_status.json", "observer_paradigms", "paradigm_status.json"),
        "institutions": _status(r, "observer_institutions_status.json", "observer_institutions", "institution_status.json"),
        "civilization": _status(r, "observer_civilization_status.json", "observer_civilization", "civilization_status.json"),
    }


def _derive_metrics(stack: Dict[str, Any]) -> Dict[str, Any]:
    exp = stack.get("experiments") or {}
    dis = stack.get("discoveries") or {}
    th = stack.get("theories") or {}
    pd = stack.get("paradigms") or {}
    pr = stack.get("programs") or {}
    tm = stack.get("teams") or {}
    net = stack.get("network") or {}

    experiments = safe_int(exp.get("experiments"), safe_int(exp.get("total"), 0))
    active_experiments = safe_int(exp.get("active_experiments"), 0)
    discoveries = safe_int(dis.get("discoveries"), safe_int(dis.get("total"), 0))
    theories = safe_int(th.get("theories"), safe_int(th.get("total"), 0))
    active_theories = safe_int(th.get("active_theories"), 0)
    paradigms = safe_int(pd.get("paradigms"), safe_int(pd.get("total"), 0))
    active_paradigms = safe_int(pd.get("active_paradigms"), 0)
    programs = safe_int(pr.get("programs"), 0)
    teams = safe_int(tm.get("teams"), 0)
    network_health = safe_float(net.get("health"), 0.0)
    paradigm_coherence = safe_float(pd.get("coherence"), safe_float(pd.get("lead_coherence"), 0.0))
    theory_confidence = safe_float(th.get("confidence"), safe_float(th.get("lead_confidence"), 0.0))

    infrastructure = clamp(
        0.18 * min(1.0, safe_int((stack.get("institutions") or {}).get("institutions"), 0) / 3.0)
        + 0.16 * min(1.0, programs / 3.0)
        + 0.16 * min(1.0, teams / 4.0)
        + 0.18 * network_health
        + 0.16 * min(1.0, experiments / 8.0)
        + 0.16 * min(1.0, discoveries / 8.0)
    )
    knowledge = clamp(
        0.30 * min(1.0, discoveries / 10.0)
        + 0.30 * min(1.0, theories / 4.0)
        + 0.25 * min(1.0, paradigms / 2.0)
        + 0.15 * max(theory_confidence, paradigm_coherence)
    )
    closure = clamp(0.50 * infrastructure + 0.50 * knowledge)

    return {
        "experiments": experiments,
        "active_experiments": active_experiments,
        "discoveries": discoveries,
        "programs": programs,
        "teams": teams,
        "theories": theories,
        "active_theories": active_theories,
        "paradigms": paradigms,
        "active_paradigms": active_paradigms,
        "network_health": round(network_health, 3),
        "theory_confidence": round(theory_confidence, 3),
        "paradigm_coherence": round(paradigm_coherence, 3),
        "infrastructure": round(infrastructure, 3),
        "knowledge": round(knowledge, 3),
        "closure": round(closure, 3),
    }


def _directives(metrics: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    directives: List[Dict[str, Any]] = []

    if metrics["programs"] <= 0:
        directives.append({
            "id": "CYCLE_FORM_PROGRAMS",
            "type": "program",
            "title": "Form first research programs",
            "mode": "explore",
            "urgency": "High",
            "expected_gain": "High",
            "reason": "Research teams and experiments need durable program targets.",
        })
    if metrics["teams"] <= 0:
        directives.append({
            "id": "CYCLE_FORM_TEAMS",
            "type": "team",
            "title": "Create execution teams for programs",
            "mode": "explore",
            "urgency": "High",
            "expected_gain": "High",
            "reason": "Scientific work cannot run without team-level executors.",
        })
    if metrics["experiments"] <= 0:
        directives.append({
            "id": "CYCLE_RUN_FOUNDATION_EXPERIMENTS",
            "type": "experiment",
            "title": "Run foundation experiments",
            "mode": "control",
            "urgency": "High",
            "expected_gain": "High",
            "reason": "Discovery and theory layers need experimental evidence.",
        })
    if metrics["discoveries"] <= 0:
        directives.append({
            "id": "CYCLE_SEED_DISCOVERY_OBJECTS",
            "type": "discovery",
            "title": "Seed first durable discovery objects",
            "mode": "explore",
            "urgency": "Medium",
            "expected_gain": "High",
            "reason": "The knowledge graph is empty.",
        })
    if metrics["theories"] <= 0 and metrics["discoveries"] >= 2:
        directives.append({
            "id": "CYCLE_SYNTHESIZE_THEORIES",
            "type": "theory",
            "title": "Synthesize discoveries into theory candidates",
            "mode": "exploit",
            "urgency": "Medium",
            "expected_gain": "High",
            "reason": "Enough discoveries may exist for theory candidates.",
        })
    if metrics["theories"] > 0 and metrics["paradigms"] <= 0:
        directives.append({
            "id": "CYCLE_GROUP_PARADIGMS",
            "type": "paradigm",
            "title": "Group active theories into proto-paradigms",
            "mode": "exploit",
            "urgency": "Medium",
            "expected_gain": "Medium",
            "reason": "Theories exist but no paradigm has stabilized.",
        })
    if metrics["network_health"] < 0.45:
        directives.append({
            "id": "CYCLE_REPAIR_NETWORK",
            "type": "network",
            "title": "Increase cross-institution collaboration",
            "mode": "explore",
            "urgency": "Medium",
            "expected_gain": "Medium",
            "reason": "Scientific network health is low.",
        })

    if metrics["closure"] < 0.22:
        phase = "OPEN_LOOP_FOUNDATION"
    elif metrics["closure"] < 0.45:
        phase = "EARLY_FEEDBACK_LOOP"
    elif metrics["closure"] < 0.70:
        phase = "ACTIVE_RESEARCH_LOOP"
    else:
        phase = "SELF_DIRECTED_RESEARCH_LOOP"

    if not directives:
        directives.append({
            "id": "CYCLE_BALANCE_RESEARCH",
            "type": "cycle",
            "title": "Balance exploration, validation, and paradigm refinement",
            "mode": "balanced",
            "urgency": "Medium",
            "expected_gain": "Medium",
            "reason": "No critical gap detected; keep the closed loop balanced.",
        })
    return phase, directives


def _scientific_state_directives(scientific_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    directives: List[Dict[str, Any]] = []
    if not isinstance(scientific_state, dict):
        return directives

    stagnation = safe_int(scientific_state.get("stagnation_generations"), 0)
    new_discoveries = safe_int(scientific_state.get("new_discoveries"), 0)
    positive_trials = safe_int(scientific_state.get("positive_trials"), 0)
    diversity_gain = safe_float(scientific_state.get("diversity_gain"), 0.0)
    novelty_gain = safe_float(scientific_state.get("novelty_gain"), 0.0)
    trend = str(scientific_state.get("adaptive_trend") or "").upper()

    if stagnation >= 3:
        directives.append({
            "id": "CYCLE_ESCAPE_EMPIRICAL_STAGNATION",
            "type": "adaptive_feedback",
            "title": "Escape empirical stagnation",
            "mode": "explore",
            "urgency": "High",
            "expected_gain": "High",
            "reason": f"No meaningful scientific gain for {stagnation} generations.",
        })
    if new_discoveries > 0 and positive_trials <= 0:
        directives.append({
            "id": "CYCLE_VALIDATE_NEW_DISCOVERIES",
            "type": "adaptive_feedback",
            "title": "Validate newly observed discoveries",
            "mode": "control",
            "urgency": "High",
            "expected_gain": "High",
            "reason": f"{new_discoveries} discoveries appeared without positive trials.",
        })
    if positive_trials >= 2:
        directives.append({
            "id": "CYCLE_REPLICATE_POSITIVE_TRIALS",
            "type": "adaptive_feedback",
            "title": "Replicate positive experimental signals",
            "mode": "replicate",
            "urgency": "Medium",
            "expected_gain": "High",
            "reason": f"{positive_trials} positive trials need independent replication.",
        })
    if diversity_gain < -0.04 or novelty_gain < -0.04:
        directives.append({
            "id": "CYCLE_RESTORE_SEARCH_DIVERSITY",
            "type": "adaptive_feedback",
            "title": "Restore novelty and family diversity",
            "mode": "explore",
            "urgency": "Medium",
            "expected_gain": "Medium",
            "reason": f"diversity_gain={diversity_gain:.3f}, novelty_gain={novelty_gain:.3f}",
        })
    if trend == "BREAKTHROUGH":
        directives.append({
            "id": "CYCLE_CONSOLIDATE_BREAKTHROUGH",
            "type": "adaptive_feedback",
            "title": "Consolidate and validate breakthrough",
            "mode": "control",
            "urgency": "High",
            "expected_gain": "High",
            "reason": "ScientificState reports a breakthrough generation.",
        })
    return directives


def build_cycle_state(results_dir: Path, generation: int | None = None, score_mode: str | None = None, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    context = dict(context or {})
    stack = _collect_stack(results_dir)
    metrics = _derive_metrics(stack)

    scientific_state = context.get("scientific_state")
    if hasattr(scientific_state, "to_dict"):
        scientific_state = scientific_state.to_dict()
    if not isinstance(scientific_state, dict):
        scientific_state = {}

    if scientific_state:
        metrics.update({
            "adaptive_trend": scientific_state.get("adaptive_trend"),
            "stagnation_generations": safe_int(scientific_state.get("stagnation_generations"), 0),
            "progress_score": safe_float(scientific_state.get("progress_score"), 0.0),
            "adaptive_risk": safe_float(scientific_state.get("adaptive_risk"), 0.0),
            "adaptive_maturity": safe_float(scientific_state.get("adaptive_maturity"), 0.0),
            "new_discoveries": safe_int(scientific_state.get("new_discoveries"), 0),
            "new_trials": safe_int(scientific_state.get("new_trials"), 0),
            "positive_trials": safe_int(scientific_state.get("positive_trials"), 0),
            "score_gain": safe_float(scientific_state.get("score_gain"), 0.0),
            "novelty_gain": safe_float(scientific_state.get("novelty_gain"), 0.0),
            "diversity_gain": safe_float(scientific_state.get("diversity_gain"), 0.0),
        })

    phase, directives = _directives(metrics)
    directives = _scientific_state_directives(scientific_state) + directives

    # Stable de-duplication by directive id.
    seen = set()
    unique_directives = []
    for directive in directives:
        directive_id = str(directive.get("id"))
        if directive_id in seen:
            continue
        seen.add(directive_id)
        unique_directives.append(directive)

    return {
        "version": CYCLE_VERSION,
        "time": now_s(),
        "active": True,
        "safe": True,
        "phase": phase,
        "generation": generation,
        "score_mode": score_mode,
        "metrics": metrics,
        "directives": unique_directives,
        "scientific_state": scientific_state,
        "context": context,
    }


def _write_cycle_state(results_dir: Path, state: Dict[str, Any], generation: int | None = None) -> Dict[str, Any]:
    d = _cycle_dir(results_dir)
    history = read_json(d / "cycle_history.json", [])
    if not isinstance(history, list):
        history = []
    history.append({
        "time": state.get("time"),
        "generation": state.get("generation"),
        "phase": state.get("phase"),
        "closure": (state.get("metrics") or {}).get("closure"),
        "directives": [x.get("id") for x in state.get("directives", [])],
    })
    history = history[-500:]

    atomic_write_json(d / "cycle_status.json", state)
    atomic_write_json(d / "cycle_directives.json", {"directives": state.get("directives", []), "phase": state.get("phase"), "metrics": state.get("metrics", {})})
    atomic_write_json(d / "cycle_history.json", history)
    if generation is not None:
        atomic_write_json(d / f"generation_{generation:02d}_cycle.json", state)

    # Root mirrors for easy visual inspection and legacy tooling.
    atomic_write_json(Path(results_dir) / "research_cycle_status.json", state)
    atomic_write_json(Path(results_dir) / "research_cycle_directives.json", {"directives": state.get("directives", []), "phase": state.get("phase"), "metrics": state.get("metrics", {})})
    return state


def initialize_research_cycle(results_dir: Path, script: str = "") -> Dict[str, Any]:
    state = build_cycle_state(Path(results_dir), generation=None, context={"script": script, "phase": "startup"})
    return _write_cycle_state(Path(results_dir), state)


def _action_label(action: Dict[str, Any]) -> str:
    for key in ("title", "name", "action", "id", "type", "kind"):
        value = action.get(key)
        if value:
            return str(value)
    return "unknown_action"


def apply_cycle_state_to_research_plan(plan: Any, state: Dict[str, Any]) -> Any:
    """Replace stale cycle intent with the current generation's directives.

    Director actions are preserved. Cycle actions are refreshed rather than
    accumulated, and ratios are intentionally left untouched because
    EvolutionPolicy is their sole owner.
    """
    try:
        if plan is None or not isinstance(state, dict):
            return plan

        directives = state.get("directives", [])
        if not isinstance(directives, list):
            directives = []

        actions = []
        for action in list(getattr(plan, "actions", []) or []):
            if not isinstance(action, dict):
                continue
            action_id = str(action.get("id") or "")
            if action.get("source") == "research_cycle" or action_id.startswith("CYCLE_"):
                continue
            actions.append(dict(action))

        generation = state.get("generation")
        phase = state.get("phase")
        for directive in directives:
            if not isinstance(directive, dict):
                continue
            row = dict(directive)
            row["source"] = "research_cycle"
            row["cycle_phase"] = phase
            row["cycle_generation"] = generation
            actions.append(row)

        plan.actions = actions
        plan.priorities = [_action_label(action) for action in actions]
        plan.action_types = sorted({
            str(action.get("type") or action.get("mode") or action.get("kind") or "unknown")
            for action in actions
        })

        notes = [
            str(note)
            for note in list(getattr(plan, "notes", []) or [])
            if not str(note).startswith("closed research cycle phase=")
        ]
        metrics = state.get("metrics", {}) if isinstance(state.get("metrics"), dict) else {}
        notes.append(
            f"closed research cycle phase={phase} generation={generation} "
            f"closure={metrics.get('closure')} directives={len(directives)}"
        )
        plan.notes = notes[-50:]
        plan.cycle_state = {
            "phase": phase,
            "generation": generation,
            "metrics": metrics,
            "directive_ids": [str(d.get("id")) for d in directives if isinstance(d, dict)],
        }
        scientific_state = state.get("scientific_state", {})
        if isinstance(scientific_state, dict) and scientific_state:
            plan.scientific_state = scientific_state
        return plan
    except Exception:
        return plan


def apply_cycle_to_research_plan(plan: Any, results_dir: Path) -> Any:
    """Attach startup cycle intent while preserving the ResearchBridge API."""
    try:
        if plan is None:
            return plan
        state = build_cycle_state(
            Path(results_dir),
            generation=None,
            context={"phase": "pre_policy"},
        )
        plan = apply_cycle_state_to_research_plan(plan, state)
        _write_cycle_state(Path(results_dir), state)
        return plan
    except Exception:
        return plan


def apply_research_cycle(results_dir: Path, generation: int, score_mode: str, observer_population: List[Dict[str, Any]], clean_results: List[Any], context: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    context = dict(context or {})
    context.update({"clean_results": len(clean_results or []), "population": len(observer_population or [])})
    state = build_cycle_state(Path(results_dir), generation=generation, score_mode=score_mode, context=context)
    _write_cycle_state(Path(results_dir), state, generation=generation)

    directives = state.get("directives", [])
    primary = directives[0].get("id") if directives else "CYCLE_NONE"
    phase = state.get("phase")
    for obs in observer_population or []:
        if isinstance(obs, dict):
            obs["research_cycle_phase"] = phase
            obs["research_cycle_directive"] = primary
            obs["cycle_closure"] = (state.get("metrics") or {}).get("closure", 0.0)
    return observer_population, state


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    metrics = status.get("metrics", {}) if isinstance(status, dict) else {}
    directives = status.get("directives", []) if isinstance(status, dict) else []
    lead = directives[0].get("id") if directives else "-"
    print(
        f"[{prefix}] {CYCLE_VERSION} | "
        f"active={status.get('active', True)} safe={status.get('safe', True)} "
        f"phase={status.get('phase','-')} closure={safe_float(metrics.get('closure'),0):.3f} "
        f"knowledge={safe_float(metrics.get('knowledge'),0):.3f} infra={safe_float(metrics.get('infrastructure'),0):.3f} "
        f"directives={len(directives)} lead={lead}"
    )
