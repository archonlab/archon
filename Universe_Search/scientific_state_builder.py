#!/usr/bin/env python3
"""
ARCHON Scientific State Builder v1.0

Builds one canonical ScientificState after each Universe Search generation.
It consumes current in-memory results plus durable status files produced by the
scientific stack. It writes:

Results/Universe_Search/scientific_state/
    current_state.json
    state_history.json
    generation_XX_state.json
"""
from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from Universe_Search.scientific_state import ScientificState

BUILDER_VERSION = "v1.0 Scientific State Builder"
STATE_DIR = "scientific_state"


def now_s() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def read_json(path: Path, default: Any = None) -> Any:
    try:
        path = Path(path)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _state_dir(results_dir: Path) -> Path:
    path = Path(results_dir) / STATE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_status(results_dir: Path, root_name: str, subdir: str, sub_name: str) -> Dict[str, Any]:
    root = read_json(Path(results_dir) / root_name, {})
    if isinstance(root, dict) and root:
        return root
    nested = read_json(Path(results_dir) / subdir / sub_name, {})
    return nested if isinstance(nested, dict) else {}


def _load_previous(
    results_dir: Path,
    generation: Optional[int] = None,
    search_run_id: Optional[str] = None,
) -> Optional[ScientificState]:
    data = read_json(_state_dir(results_dir) / "current_state.json", None)
    if isinstance(data, dict):
        same_generation = (
            generation is not None
            and safe_int(data.get("generation"), -1) == safe_int(generation, -2)
            and str(data.get("search_run_id")) == str(search_run_id)
        )
        if not same_generation:
            return ScientificState.from_dict(data)

        # A repeated build of the same run/generation must compare against the
        # preceding generation, not against its own already-written snapshot.
        history = read_json(_state_dir(results_dir) / "state_history.json", [])
        if isinstance(history, list):
            for row in reversed(history):
                if not isinstance(row, dict):
                    continue
                if (
                    safe_int(row.get("generation"), -1) == safe_int(generation, -2)
                    and str(row.get("search_run_id")) == str(search_run_id)
                ):
                    continue
                return ScientificState.from_dict(row)
    return None


def _rule_family(rule: Any, metrics: Dict[str, Any]) -> str:
    for key in ("family", "rule_family", "lineage_family", "observer_archetype", "species_id"):
        value = metrics.get(key)
        if value not in (None, ""):
            return str(value)
    try:
        value = getattr(rule, "family", None)
        if value not in (None, ""):
            return str(value)
    except Exception:
        pass
    try:
        parents = (getattr(rule, "parent_a", -1), getattr(rule, "parent_b", -1))
        if parents != (-1, -1):
            return f"lineage:{parents[0]}:{parents[1]}"
    except Exception:
        pass
    return "unknown"


def _discovery_summary(results_dir: Path) -> Dict[str, int]:
    status = _load_status(
        results_dir,
        "discovery_status.json",
        "observer_discoveries",
        "discovery_status.json",
    )
    archive = read_json(Path(results_dir) / "observer_discoveries" / "discoveries.json", {})
    rows = list(archive.values()) if isinstance(archive, dict) else []
    return {
        "total": safe_int(status.get("discovery_count"), safe_int(status.get("discoveries"), len(rows))),
        "new": safe_int(status.get("new_discoveries"), 0),
        "supported": sum(1 for row in rows if isinstance(row, dict) and row.get("status") in {"SUPPORTED", "FOUNDATIONAL"}),
        "foundational": sum(1 for row in rows if isinstance(row, dict) and row.get("status") == "FOUNDATIONAL"),
    }


def _experiment_summary(results_dir: Path, generation: int) -> Dict[str, int]:
    status = _load_status(
        results_dir,
        "experiment_status.json",
        "observer_experiments",
        "experiment_status.json",
    )
    archive = read_json(Path(results_dir) / "observer_experiments" / "experiments.json", {})
    rows = list(archive.values()) if isinstance(archive, dict) else []
    new_trials = 0
    positive_trials = 0
    repeatable = 0
    successful = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("repeatable"):
            repeatable += 1
        if row.get("status") == "SUCCESS":
            successful += 1
        for trial in row.get("trials", []) or []:
            if not isinstance(trial, dict):
                continue
            if safe_int(trial.get("generation"), -1) == generation:
                new_trials += 1
                if trial.get("status") == "POSITIVE":
                    positive_trials += 1
    return {
        "total": safe_int(status.get("experiments"), safe_int(status.get("total"), len(rows))),
        "new_trials": new_trials,
        "positive_trials": positive_trials,
        "successful": successful,
        "repeatable": repeatable,
    }


def _theory_summary(results_dir: Path) -> Dict[str, int]:
    status = _load_status(
        results_dir,
        "theory_engine_status.json",
        "observer_theories",
        "theory_status.json",
    )
    return {
        "total": safe_int(status.get("theories"), safe_int(status.get("total"), 0)),
        "active": safe_int(status.get("active_theories"), 0),
    }


def _paradigm_summary(results_dir: Path) -> Dict[str, int]:
    status = _load_status(
        results_dir,
        "paradigm_engine_status.json",
        "observer_paradigms",
        "paradigm_status.json",
    )
    return {
        "total": safe_int(status.get("paradigms"), safe_int(status.get("total"), 0)),
        "active": safe_int(status.get("active_paradigms"), 0),
    }


def _adaptive_signals(
    previous: Optional[ScientificState],
    score_gain: float,
    novelty_gain: float,
    diversity_gain: float,
    new_discoveries: int,
    new_trials: int,
    positive_trials: int,
    best_ever_improved: bool,
) -> Tuple[int, str, float, float, float, List[str]]:
    signals: List[str] = []
    progress = 0.0

    if best_ever_improved:
        progress += 0.30
        signals.append("best-ever score improved")
    if score_gain > 0.01:
        progress += min(0.20, score_gain / 50.0)
        signals.append("generation score improved")
    if new_discoveries > 0:
        progress += min(0.25, new_discoveries * 0.05)
        signals.append(f"{new_discoveries} new discoveries")
    if positive_trials > 0:
        progress += min(0.15, positive_trials * 0.04)
        signals.append(f"{positive_trials} positive trials")
    elif new_trials > 0:
        progress += min(0.07, new_trials * 0.01)
        signals.append(f"{new_trials} new trials")
    if novelty_gain > 0.01:
        progress += min(0.10, novelty_gain)
        signals.append("novelty increased")
    if diversity_gain > 0.01:
        progress += min(0.10, diversity_gain)
        signals.append("diversity increased")

    progress = max(0.0, min(1.0, progress))

    meaningful = (
        best_ever_improved
        or new_discoveries > 0
        or positive_trials > 0
        or score_gain > 0.02
        or novelty_gain > 0.025
        or diversity_gain > 0.025
    )
    previous_stagnation = previous.stagnation_generations if previous else 0
    stagnation = 0 if meaningful else previous_stagnation + 1

    if progress >= 0.45:
        trend = "BREAKTHROUGH"
    elif progress >= 0.18:
        trend = "IMPROVING"
    elif stagnation >= 4:
        trend = "STAGNATING"
    elif stagnation >= 2:
        trend = "PLATEAU"
    else:
        trend = "MIXED"

    # Adaptive risk is operational uncertainty, not safety risk.
    risk = 0.18
    risk += min(0.30, stagnation * 0.055)
    risk += 0.10 if diversity_gain < -0.04 else 0.0
    risk += 0.08 if novelty_gain < -0.04 else 0.0
    risk -= min(0.18, progress * 0.25)
    risk = max(0.0, min(1.0, risk))

    previous_maturity = previous.adaptive_maturity if previous else 0.0
    maturity_gain = (
        min(0.025, new_discoveries * 0.003)
        + min(0.025, positive_trials * 0.004)
        + (0.012 if best_ever_improved else 0.0)
    )
    maturity = max(previous_maturity, min(1.0, previous_maturity + maturity_gain))

    if not signals:
        signals.append("no meaningful scientific gain detected")
    return stagnation, trend, progress, risk, maturity, signals


def build_scientific_state(
    results_dir: Path,
    generation: int,
    score_mode: str,
    clean_results: List[Any],
    best_ever: Any = None,
    guided_info: Optional[Dict[str, Any]] = None,
    cycle_state: Optional[Dict[str, Any]] = None,
    search_run_id: str = "unknown",
) -> ScientificState:
    results_dir = Path(results_dir)
    previous = _load_previous(results_dir, generation, search_run_id)

    scores: List[float] = []
    novelty: List[float] = []
    diversity: List[float] = []
    family_distribution: Dict[str, int] = {}
    best_rule_id = None

    for item in clean_results or []:
        try:
            score, rule, metrics = item
        except Exception:
            continue
        metrics = metrics if isinstance(metrics, dict) else {}
        scores.append(safe_float(score))
        novelty.append(safe_float(metrics.get("novelty_behavior"), 0.0))
        diversity.append(safe_float(metrics.get("in_generation_diversity"), 0.0))
        family = _rule_family(rule, metrics)
        family_distribution[family] = family_distribution.get(family, 0) + 1

    if clean_results:
        try:
            best_rule_id = safe_int(getattr(clean_results[0][1], "rule_id", None), None)
        except Exception:
            best_rule_id = None

    best_score = max(scores) if scores else 0.0
    mean_score = statistics.fmean(scores) if scores else 0.0
    median_score = statistics.median(scores) if scores else 0.0
    mean_novelty = statistics.fmean(novelty) if novelty else 0.0
    mean_diversity = statistics.fmean(diversity) if diversity else 0.0

    previous_best = previous.best_score if previous else best_score
    previous_novelty = previous.mean_novelty if previous else mean_novelty
    previous_diversity = previous.mean_diversity if previous else mean_diversity

    score_gain = best_score - previous_best
    novelty_gain = mean_novelty - previous_novelty
    diversity_gain = mean_diversity - previous_diversity

    best_ever_score = 0.0
    if best_ever is not None:
        try:
            best_ever_score = safe_float(best_ever[0])
        except Exception:
            pass
    previous_best_ever = previous.best_ever_score if previous else best_ever_score
    # Persisted scores are rounded to six decimals.  Comparing the next raw
    # float with a 1e-9 epsilon makes the discarded floating-point tail look
    # like a fresh record on every later generation.  A gain must exceed the
    # storage precision to count as a genuine best-ever improvement.
    best_ever_improved = best_ever_score > previous_best_ever + 1e-6

    discoveries = _discovery_summary(results_dir)
    experiments = _experiment_summary(results_dir, generation)
    theories = _theory_summary(results_dir)
    paradigms = _paradigm_summary(results_dir)

    stagnation, trend, progress, risk, maturity, signals = _adaptive_signals(
        previous=previous,
        score_gain=score_gain,
        novelty_gain=novelty_gain,
        diversity_gain=diversity_gain,
        new_discoveries=discoveries["new"],
        new_trials=experiments["new_trials"],
        positive_trials=experiments["positive_trials"],
        best_ever_improved=best_ever_improved,
    )

    guided_info = guided_info if isinstance(guided_info, dict) else {}
    made = guided_info.get("made", {}) if isinstance(guided_info.get("made"), dict) else {}
    refs = guided_info.get("reference_controls", {}) if isinstance(guided_info.get("reference_controls"), dict) else {}
    policy = guided_info.get("policy", {}) if isinstance(guided_info.get("policy"), dict) else {}
    cycle_state = cycle_state if isinstance(cycle_state, dict) else {}
    directives = cycle_state.get("directives", []) if isinstance(cycle_state.get("directives"), list) else []

    state = ScientificState(
        generation=int(generation),
        score_mode=str(score_mode),
        search_run_id=str(search_run_id),
        written_at=now_s(),
        population_evaluated=len(clean_results or []),
        valid_worlds=len(clean_results or []),
        best_rule_id=best_rule_id,
        best_score=round(best_score, 6),
        mean_score=round(mean_score, 6),
        median_score=round(median_score, 6),
        score_gain=round(score_gain, 6),
        best_ever_score=round(best_ever_score, 6),
        best_ever_improved=bool(best_ever_improved),
        mean_novelty=round(mean_novelty, 6),
        mean_diversity=round(mean_diversity, 6),
        novelty_gain=round(novelty_gain, 6),
        diversity_gain=round(diversity_gain, 6),
        discoveries=discoveries["total"],
        new_discoveries=discoveries["new"],
        supported_discoveries=discoveries["supported"],
        foundational_discoveries=discoveries["foundational"],
        experiments=experiments["total"],
        new_trials=experiments["new_trials"],
        positive_trials=experiments["positive_trials"],
        successful_experiments=experiments["successful"],
        repeatable_experiments=experiments["repeatable"],
        theories=theories["total"],
        active_theories=theories["active"],
        paradigms=paradigms["total"],
        active_paradigms=paradigms["active"],
        reference_controls_available=safe_int(refs.get("available"), 0),
        reference_controls_used=safe_int(made.get("reference_control"), safe_int(refs.get("used"), 0)),
        reference_control_fallback_used=safe_int(made.get("lower_tail_control"), safe_int(refs.get("fallback_used"), 0)),
        family_count=len(family_distribution),
        family_distribution=dict(sorted(family_distribution.items(), key=lambda kv: (-kv[1], kv[0]))),
        stagnation_generations=stagnation,
        adaptive_trend=trend,
        progress_score=round(progress, 6),
        adaptive_risk=round(risk, 6),
        adaptive_maturity=round(maturity, 6),
        policy_ratios=dict(guided_info.get("ratios", {}) or {}),
        policy_reasons=list(policy.get("reasons", []) or []),
        cycle_phase=str(cycle_state.get("phase", "unknown")),
        cycle_directives=[str(row.get("id")) for row in directives if isinstance(row, dict)],
        signals=signals,
        source_files={
            "discoveries": str(results_dir / "observer_discoveries" / "discoveries.json"),
            "experiments": str(results_dir / "observer_experiments" / "experiments.json"),
            "cycle": str(results_dir / "research_cycle_status.json"),
        },
    )
    return state


def write_scientific_state(results_dir: Path, state: ScientificState) -> Dict[str, Any]:
    results_dir = Path(results_dir)
    state_dir = _state_dir(results_dir)
    payload = state.to_dict()

    history = read_json(state_dir / "state_history.json", [])
    if not isinstance(history, list):
        history = []
    # Defensive idempotency: replacing the same run/generation is legitimate
    # (for example after a resumed finalisation), but it must not create a
    # duplicate history entry or make that generation its own predecessor.
    same_generation = (
        history
        and isinstance(history[-1], dict)
        and str(history[-1].get("search_run_id")) == str(payload.get("search_run_id"))
        and safe_int(history[-1].get("generation"), -1) == safe_int(payload.get("generation"), -2)
    )
    if same_generation:
        history[-1] = payload
    else:
        history.append(payload)
    history = history[-1000:]

    atomic_write_json(state_dir / "current_state.json", payload)
    atomic_write_json(state_dir / "state_history.json", history)
    atomic_write_json(state_dir / f"generation_{state.generation:02d}_state.json", payload)
    atomic_write_json(results_dir / "scientific_state.json", payload)
    return payload


def build_and_write_scientific_state(**kwargs: Any) -> ScientificState:
    state = build_scientific_state(**kwargs)
    write_scientific_state(kwargs["results_dir"], state)
    return state
