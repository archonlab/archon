#!/usr/bin/env python3
"""
Universe Search v31.0 - Experiment Engine

Folder-safe experiment layer above ResearchTeams.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_experiments/ plus root mirror experiment_status.json.
- Convert team activity + current generation metrics into experiment records.
- Conservative first layer: experiment tracking and observer annotations only; no hard steering of core search yet.
"""
from __future__ import annotations

import json
import math
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXPERIMENT_VERSION = "v31.1 Experiment Engine + Trial History"
EXPERIMENT_DIR = "observer_experiments"
TEAM_DIR = "observer_research_teams"
PROGRAM_DIR = "observer_research_programs"
DISCOVERY_DIR = "observer_discoveries"

TOPIC_HYPOTHESES = {
    "memory": "Test whether long-lived field memory improves observer fitness and repeatability.",
    "knowledge": "Test whether knowledge accumulation predicts validated emergence.",
    "information": "Measure information transfer as a precursor to stable organization.",
    "crystal": "Probe crystal-like morphologies for stable but possibly non-living patterns.",
    "stability": "Replicate persistence and stochastic stability claims across independent rules.",
    "organism": "Test organism-like components for survival and bounded turnover.",
    "civilization": "Probe whether observer civilizations generate reusable collective knowledge.",
    "novelty": "Explore high-novelty rules for previously unseen mechanisms.",
    "general_pattern": "Measure broad pattern quality as baseline experimental control.",
}


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


def _exp_dir(results_dir: Path) -> Path:
    p = Path(results_dir) / EXPERIMENT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hash(s: Any) -> str:
    return hashlib.sha1(str(s).encode("utf-8", errors="replace")).hexdigest()[:10]


def _normalize_topic(topic: Any) -> str:
    t = str(topic or "general_pattern").lower().strip()
    aliases = {"info": "information", "general": "general_pattern", "pattern": "general_pattern"}
    return aliases.get(t, t)


def _load_teams(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / TEAM_DIR / "research_teams.json", {})
    return data if isinstance(data, dict) else {}


def _load_programs(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / PROGRAM_DIR / "research_programs.json", {})
    return data if isinstance(data, dict) else {}


def _load_discoveries(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / DISCOVERY_DIR / "discoveries.json", {})
    return data if isinstance(data, dict) else {}


def _load_experiments(results_dir: Path) -> Dict[str, Any]:
    data = read_json(_exp_dir(results_dir) / "experiments.json", {})
    return data if isinstance(data, dict) else {}


def _load_history(results_dir: Path) -> List[Dict[str, Any]]:
    data = read_json(_exp_dir(results_dir) / "experiment_history.json", [])
    return data if isinstance(data, list) else []


def _metric_signal(topic: str, metrics: Dict[str, Any]) -> float:
    topic = _normalize_topic(topic)
    if topic == "memory":
        return clamp(safe_float(metrics.get("memory_score"), 0.0) + 0.5 * safe_float(metrics.get("field_memory"), 0.0))
    if topic in ("knowledge", "information"):
        return clamp(safe_float(metrics.get("information_score", metrics.get("knowledge_score", 0.0)), 0.0))
    if topic == "crystal":
        return clamp(safe_float(metrics.get("quasi_particle_score", metrics.get("crystal_defect_score", 0.0)), 0.0))
    if topic == "stability":
        return clamp(safe_float(metrics.get("stability", metrics.get("stochastic_stability", 0.0)), 0.0))
    if topic == "organism":
        return clamp(safe_float(metrics.get("organism_score", 0.0), 0.0))
    if topic == "civilization":
        return clamp(safe_float(metrics.get("civilization_score", metrics.get("observer_civilization", 0.0)), 0.0))
    if topic == "novelty":
        return clamp(safe_float(metrics.get("novelty_behavior", 0.0), 0.0))
    return clamp(0.5 * safe_float(metrics.get("in_generation_diversity", 0.0), 0.0) + 0.5 * safe_float(metrics.get("novelty_behavior", 0.0), 0.0))


def _top_metrics(clean_results: List[Any], limit: int = 16) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in (clean_results or [])[:limit]:
        try:
            _score, _rule, metrics = item
            if isinstance(metrics, dict):
                out.append(metrics)
        except Exception:
            pass
    return out


def _experiment_id(team_id: str, topic: str, experiment_type: str) -> str:
    """Stable experiment identity; generations become trials, not new experiments."""
    key = f"{team_id}:{topic}:{experiment_type}"
    return f"EXP-{topic.upper().replace('-', '_')}-{_hash(key)}"


def _trial_status(confidence: float, evidence: float) -> str:
    if confidence >= 0.70 and evidence >= 0.60:
        return "POSITIVE"
    if confidence >= 0.45 or evidence >= 0.42:
        return "MIXED"
    if confidence < 0.20 and evidence < 0.18:
        return "NEGATIVE"
    return "WEAK_SIGNAL"


def _aggregate_experiment(exp: Dict[str, Any]) -> None:
    trials = [t for t in exp.get("trials", []) if isinstance(t, dict)]
    trial_count = len(trials)
    positive = sum(1 for t in trials if t.get("status") == "POSITIVE")
    negative = sum(1 for t in trials if t.get("status") == "NEGATIVE")
    generations = {safe_int(t.get("generation"), -1) for t in trials}
    generations.discard(-1)

    mean_evidence = sum(safe_float(t.get("evidence_score"), 0.0) for t in trials) / max(1, trial_count)
    mean_confidence = sum(safe_float(t.get("confidence"), 0.0) for t in trials) / max(1, trial_count)
    repeatable = positive >= 2 and len(generations) >= 2

    if trial_count >= 3 and positive >= 2 and repeatable and mean_confidence >= 0.62:
        status = "SUCCESS"
    elif trial_count >= 2 and positive >= 1:
        status = "SUPPORTED"
    elif trial_count >= 3 and negative >= 2:
        status = "FAILED"
    elif trial_count >= 2:
        status = "MIXED"
    else:
        status = "ACTIVE"

    exp["trial_count"] = trial_count
    exp["positive_trials"] = positive
    exp["negative_trials"] = negative
    exp["independent_generations"] = len(generations)
    exp["repeatable"] = repeatable
    exp["mean_evidence"] = round(mean_evidence, 6)
    exp["mean_confidence"] = round(mean_confidence, 6)
    exp["evidence_score"] = round(mean_evidence, 6)
    exp["confidence"] = round(mean_confidence, 6)
    exp["status"] = status


def _experiment_type(topic: str, context: Dict[str, Any] | None = None) -> str:
    context = context or {}
    strategy = str((context.get("strategy") or {}).get("strategy") or context.get("strategy") or "").upper()
    if "CONTROL" in strategy:
        return "NEGATIVE_CONTROL" if topic in ("general_pattern", "stability", "crystal") else "CONTROLLED_PROBE"
    if topic == "novelty":
        return "EXPLORATION"
    if topic in ("stability", "memory"):
        return "REPLICATION"
    return "MEASUREMENT"


def _status_from_scores(confidence: float, evidence: float, repeatable: bool) -> str:
    if confidence >= 0.70 and evidence >= 0.60 and repeatable:
        return "SUCCESS"
    if confidence >= 0.45 or evidence >= 0.42:
        return "MIXED"
    if confidence < 0.20 and evidence < 0.18:
        return "FAILED"
    return "WEAK_SIGNAL"


def initialize_experiments(results_dir: Path, script: str = "") -> Dict[str, Any]:
    results_dir = Path(results_dir)
    edir = _exp_dir(results_dir)
    experiments = _load_experiments(results_dir)
    status_counts: Dict[str, int] = {}
    for e in experiments.values():
        if isinstance(e, dict):
            status_counts[str(e.get("status", "UNKNOWN"))] = status_counts.get(str(e.get("status", "UNKNOWN")), 0) + 1
    status = {
        "version": EXPERIMENT_VERSION,
        "active": True,
        "safe": True,
        "script": script,
        "created_at": now_s(),
        "experiment_count": len(experiments),
        "active_experiments": sum(1 for e in experiments.values() if isinstance(e, dict) and e.get("status") not in ("FAILED", "ARCHIVED")),
        "status_counts": status_counts,
        "phase": "EXPERIMENT_FOUNDATION" if len(experiments) < 3 else "EXPERIMENT_ACCUMULATION",
    }
    atomic_write_json(edir / "experiment_status.json", status)
    atomic_write_json(results_dir / "experiment_status.json", status)
    return status


def apply_experiment_engine(results_dir: Path, generation: int, score_mode: str, observer_population: List[Dict[str, Any]], clean_results: List[Any], context: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    results_dir = Path(results_dir)
    edir = _exp_dir(results_dir)
    context = context or {}
    teams = _load_teams(results_dir)
    programs = _load_programs(results_dir)
    discoveries = _load_discoveries(results_dir)
    experiments = _load_experiments(results_dir)
    history = _load_history(results_dir)
    metrics_list = _top_metrics(clean_results)
    now = now_s()

    active_teams = [t for t in teams.values() if isinstance(t, dict) and t.get("status") not in ("RETIRED", "INACTIVE")]
    if not active_teams:
        active_teams = [
            {"team_id": "TEAM-SEED-MEMORY", "topic": "memory", "institution": "memory_institute", "program_id": "SEED-PROGRAM-MEMORY", "productivity": 0.20, "skill": 0.25, "assigned_observers": max(1, len(observer_population or []) // 2)},
            {"team_id": "TEAM-SEED-GENERAL", "topic": "general_pattern", "institution": "general_research_institute", "program_id": "SEED-PROGRAM-GENERAL", "productivity": 0.18, "skill": 0.20, "assigned_observers": max(1, len(observer_population or []) // 2)},
        ]

    new_count = 0
    updated_count = 0
    generation_experiments: List[Dict[str, Any]] = []

    for idx, team in enumerate(active_teams):
        if not isinstance(team, dict):
            continue

        topic = _normalize_topic(team.get("topic"))
        tid = str(team.get("team_id") or f"TEAM-SEED-{idx}")
        exp_type = _experiment_type(topic, context)
        eid = _experiment_id(tid, topic, exp_type)

        topic_signals = [_metric_signal(topic, m) for m in metrics_list]
        mean_signal = sum(topic_signals) / max(1, len(topic_signals))
        best_signal = max(topic_signals) if topic_signals else 0.0
        novelty = sum(safe_float(m.get("novelty_behavior"), 0.0) for m in metrics_list) / max(1, len(metrics_list))
        diversity = sum(safe_float(m.get("in_generation_diversity"), 0.0) for m in metrics_list) / max(1, len(metrics_list))
        team_productivity = safe_float(team.get("productivity"), 0.0)
        team_skill = safe_float(team.get("skill"), 0.0)
        program_id = str(team.get("program_id") or "")
        program = programs.get(program_id, {}) if isinstance(programs.get(program_id), dict) else {}
        program_conf = safe_float(program.get("confidence"), safe_float(team.get("program_confidence"), 0.0))

        discovery_support = 0.0
        for d in discoveries.values():
            if isinstance(d, dict) and _normalize_topic(d.get("topic")) == topic:
                independent_rules = safe_int(d.get("independent_rule_count"), 0)
                discovery_support += 0.03 + 0.04 * safe_float(d.get("confidence"), 0.0) + 0.01 * min(10, independent_rules)
        discovery_support = clamp(discovery_support, 0.0, 0.30)

        evidence = round(clamp(0.45 * mean_signal + 0.20 * best_signal + 0.18 * team_productivity + 0.10 * program_conf + 0.07 * discovery_support), 6)
        confidence = round(clamp(0.50 * evidence + 0.20 * team_skill + 0.15 * diversity + 0.10 * novelty + 0.05 * program_conf), 6)
        trial_status = _trial_status(confidence, evidence)

        exp = experiments.get(eid)
        if not isinstance(exp, dict):
            new_count += 1
            exp = {
                "experiment_id": eid,
                "created_at": now,
                "created_generation": generation,
                "team_id": tid,
                "program_id": program_id,
                "institution": team.get("institution"),
                "topic": topic,
                "hypothesis": TOPIC_HYPOTHESES.get(topic, TOPIC_HYPOTHESES["general_pattern"]),
                "experiment_type": exp_type,
                "trials": [],
                "legacy_experiment_ids": [],
            }
        else:
            updated_count += 1

        exp.setdefault("trials", [])
        trial_id = f"{eid}-TRIAL-{generation:04d}"
        existing_trial = next(
            (t for t in exp["trials"] if isinstance(t, dict) and t.get("trial_id") == trial_id),
            None,
        )

        trial = {
            "trial_id": trial_id,
            "generation": generation,
            "created_at": now,
            "score_mode": score_mode,
            "status": trial_status,
            "evidence_score": evidence,
            "confidence": confidence,
            "mean_topic_signal": round(mean_signal, 6),
            "best_topic_signal": round(best_signal, 6),
            "novelty": round(clamp(novelty), 6),
            "diversity": round(clamp(diversity), 6),
            "team_productivity": round(team_productivity, 6),
            "team_skill": round(team_skill, 6),
            "program_confidence": round(program_conf, 6),
            "discovery_support": round(discovery_support, 6),
            "sample_size": len(metrics_list),
            "observer_count": safe_int(team.get("assigned_observers"), 0),
            "context": context,
        }

        if existing_trial is None:
            exp["trials"].append(trial)
        else:
            existing_trial.update(trial)

        exp["version"] = EXPERIMENT_VERSION
        exp["updated_at"] = now
        exp["last_generation"] = generation
        exp["score_mode"] = score_mode
        exp["experiment_type"] = exp_type
        exp["last_trial_status"] = trial_status
        exp["last_trial_id"] = trial_id
        _aggregate_experiment(exp)

        experiments[eid] = exp
        generation_experiments.append(exp)

    team_to_exps: Dict[str, List[Dict[str, Any]]] = {}
    for exp in generation_experiments:
        team_to_exps.setdefault(str(exp.get("team_id")), []).append(exp)

    for idx, obs in enumerate(observer_population or []):
        if not isinstance(obs, dict):
            continue
        tid = str(obs.get("research_team_id") or "")
        candidates = team_to_exps.get(tid) or generation_experiments
        if candidates:
            chosen = candidates[idx % len(candidates)]
            obs["experiment_id"] = chosen.get("experiment_id")
            obs["experiment_topic"] = chosen.get("topic")
            obs["experiment_confidence"] = chosen.get("confidence")
            obs["experiment_trial_count"] = chosen.get("trial_count")
            obs["experiment_role"] = "executor"

    status_counts: Dict[str, int] = {}
    for e in experiments.values():
        if isinstance(e, dict):
            status_counts[str(e.get("status", "UNKNOWN"))] = status_counts.get(str(e.get("status", "UNKNOWN")), 0) + 1

    active = [e for e in experiments.values() if isinstance(e, dict) and e.get("status") not in ("FAILED", "ARCHIVED")]
    successes = [e for e in experiments.values() if isinstance(e, dict) and e.get("status") == "SUCCESS"]
    best = max(active, key=lambda e: safe_float(e.get("confidence"), 0.0), default={})
    mean_conf = sum(safe_float(e.get("confidence"), 0.0) for e in active) / max(1, len(active))
    mean_evidence = sum(safe_float(e.get("evidence_score"), 0.0) for e in active) / max(1, len(active))
    total_trials = sum(safe_int(e.get("trial_count"), 0) for e in experiments.values() if isinstance(e, dict))

    report = {
        "version": EXPERIMENT_VERSION,
        "active": True,
        "safe": True,
        "generation": generation,
        "score_mode": score_mode,
        "updated_at": now,
        "experiment_count": len(experiments),
        "trial_count": total_trials,
        "new_experiments": new_count,
        "updated_experiments": updated_count,
        "active_experiments": len(active),
        "successful_experiments": len(successes),
        "status_counts": status_counts,
        "mean_confidence": round(mean_conf, 6),
        "mean_evidence": round(mean_evidence, 6),
        "best_experiment": best.get("experiment_id"),
        "best_topic": best.get("topic"),
        "best_team": best.get("team_id"),
        "phase": "EXPERIMENT_FOUNDATION" if len(experiments) < 4 else "EXPERIMENT_OPERATION",
        "context": context,
    }

    history.append({
        "time": now,
        "generation": generation,
        "experiment_count": len(experiments),
        "trial_count": total_trials,
        "new_experiments": new_count,
        "active_experiments": len(active),
        "successful_experiments": len(successes),
        "mean_confidence": report["mean_confidence"],
        "mean_evidence": report["mean_evidence"],
        "best_experiment": report["best_experiment"],
        "best_topic": report["best_topic"],
    })
    history = history[-1000:]

    graph = {"nodes": {}, "edges": {}}
    for eid, e in experiments.items():
        if not isinstance(e, dict):
            continue
        tid = str(e.get("team_id") or "unknown_team")
        pid = str(e.get("program_id") or "unknown_program")
        inst = str(e.get("institution") or "unknown_institute")
        graph["nodes"][inst] = {"type": "institution"}
        graph["nodes"][pid] = {"type": "program", "topic": e.get("topic")}
        graph["nodes"][tid] = {"type": "team", "topic": e.get("topic")}
        graph["nodes"][eid] = {
            "type": "experiment",
            "topic": e.get("topic"),
            "status": e.get("status"),
            "confidence": e.get("confidence"),
            "trial_count": e.get("trial_count", 0),
        }
        graph["edges"][f"{inst}->{pid}"] = {"source": inst, "target": pid, "relation": "SPONSORS"}
        graph["edges"][f"{pid}->{tid}"] = {"source": pid, "target": tid, "relation": "EXECUTED_BY"}
        graph["edges"][f"{tid}->{eid}"] = {"source": tid, "target": eid, "relation": "RUNS"}

    atomic_write_json(edir / "experiments.json", experiments)
    atomic_write_json(edir / "experiment_history.json", history)
    atomic_write_json(edir / "experiment_graph.json", graph)
    atomic_write_json(
        edir / f"generation_{generation:02d}_experiments.json",
        {
            "report": report,
            "experiments": generation_experiments,
            "trials": [
                next(
                    (t for t in e.get("trials", []) if t.get("generation") == generation),
                    None,
                )
                for e in generation_experiments
            ],
        },
    )
    atomic_write_json(edir / "experiment_status.json", report)
    atomic_write_json(results_dir / "experiment_status.json", report)

    return observer_population, report


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    if not isinstance(status, dict):
        print(f"[{prefix}] {EXPERIMENT_VERSION} | no status")
        return
    print(
        f"[{prefix}] {EXPERIMENT_VERSION} | "
        f"active={status.get('active')} safe={status.get('safe')} "
        f"experiments={status.get('experiment_count', 0)} "
        f"active_experiments={status.get('active_experiments', 0)} "
        f"success={status.get('successful_experiments', 0)} "
        f"phase={status.get('phase', '-')}"
    )
