#!/usr/bin/env python3
"""
Universe Search v30.0 - Research Teams

Folder-safe team layer above ResearchPrograms.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_research_teams/ plus root mirror research_teams_status.json.
- Convert institutions + programs into persistent research teams.
- Conservative first layer: teams annotate observer population and maintain team history; no hard steering of core search yet.
"""
from __future__ import annotations

import json
import math
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

TEAM_VERSION = "v30.0 Research Teams"
TEAM_DIR = "observer_research_teams"
PROGRAM_DIR = "observer_research_programs"
INSTITUTION_DIR = "observer_institutions"
DISCOVERY_DIR = "observer_discoveries"

DEFAULT_TOPICS = [
    "memory",
    "novelty",
    "stability",
    "general_pattern",
]

TOPIC_TO_TEAM_NAME = {
    "memory": "Memory Dynamics Team",
    "knowledge": "Knowledge Transfer Team",
    "information": "Information Flow Team",
    "crystal": "Crystal Morphology Team",
    "stability": "Stability Replication Team",
    "organism": "Organism Pattern Team",
    "civilization": "Civilization Signal Team",
    "novelty": "Exploration and Novelty Team",
    "general_pattern": "General Pattern Team",
    "general": "General Pattern Team",
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
        path = Path(path)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(path)


def _team_dir(results_dir: Path) -> Path:
    p = Path(results_dir) / TEAM_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hash(s: Any) -> str:
    return hashlib.sha1(str(s).encode("utf-8", errors="replace")).hexdigest()[:10]


def _normalize_topic(topic: Any) -> str:
    t = str(topic or "general_pattern").lower().strip()
    aliases = {"info": "information", "general": "general_pattern", "pattern": "general_pattern"}
    return aliases.get(t, t)


def _team_id(institution: str, program_id: str, topic: str, idx: int = 0) -> str:
    base = f"{institution}:{program_id}:{topic}:{idx}"
    return f"TEAM-{topic.upper().replace('-', '_')}-{_hash(base)}"


def _team_title(topic: str, institution: str) -> str:
    base = TOPIC_TO_TEAM_NAME.get(topic, topic.replace("_", " ").title() + " Team")
    return f"{base} @ {institution}"


def _load_programs(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / PROGRAM_DIR / "research_programs.json", {})
    return data if isinstance(data, dict) else {}


def _load_institutions(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / INSTITUTION_DIR / "institution_registry.json", {})
    if isinstance(data, dict):
        if isinstance(data.get("institutions"), dict):
            return data.get("institutions") or {}
        # Some older layers write registry directly keyed by institute.
        return {k: v for k, v in data.items() if isinstance(v, dict)}
    return {}


def _load_discoveries(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / DISCOVERY_DIR / "discoveries.json", {})
    return data if isinstance(data, dict) else {}


def _load_teams(results_dir: Path) -> Dict[str, Any]:
    data = read_json(_team_dir(results_dir) / "research_teams.json", {})
    return data if isinstance(data, dict) else {}


def _load_history(results_dir: Path) -> List[Dict[str, Any]]:
    data = read_json(_team_dir(results_dir) / "research_team_history.json", [])
    return data if isinstance(data, list) else []


def _program_records(results_dir: Path) -> List[Dict[str, Any]]:
    programs = _load_programs(results_dir)
    out: List[Dict[str, Any]] = []
    for pid, p in programs.items():
        if isinstance(p, dict):
            q = dict(p)
            q.setdefault("program_id", pid)
            out.append(q)
    return out


def _fallback_seed_programs(results_dir: Path) -> List[Dict[str, Any]]:
    """When discoveries/programs are still empty, seed teams from current institutions."""
    institutions = _load_institutions(results_dir)
    seeds: List[Dict[str, Any]] = []
    if institutions:
        for idx, (iid, inst) in enumerate(institutions.items()):
            if not isinstance(inst, dict):
                continue
            spec = str(inst.get("specialization") or inst.get("topic") or "general_pattern").lower()
            topic = "memory" if "memory" in spec else "information" if "info" in spec else "novelty" if "novel" in spec else DEFAULT_TOPICS[idx % len(DEFAULT_TOPICS)]
            seeds.append({
                "program_id": f"SEED-PROGRAM-{_hash(iid + topic)}",
                "topic": topic,
                "title": f"Seed Program: {topic.replace('_', ' ').title()}",
                "institution": str(iid),
                "status": "SEED",
                "progress": safe_float(inst.get("reuse", inst.get("reputation", 0.25)), 0.25),
                "confidence": safe_float(inst.get("reputation", inst.get("maturity", 0.25)), 0.25),
                "evidence_count": 0,
            })
    if not seeds:
        # Minimal bootstrap that mirrors current young state.
        seeds.append({
            "program_id": "SEED-PROGRAM-MEMORY",
            "topic": "memory",
            "title": "Seed Program: Memory Dynamics",
            "institution": "memory_institute",
            "status": "SEED",
            "progress": 0.22,
            "confidence": 0.24,
            "evidence_count": 0,
        })
        seeds.append({
            "program_id": "SEED-PROGRAM-GENERAL",
            "topic": "general_pattern",
            "title": "Seed Program: General Pattern Research",
            "institution": "general_research_institute",
            "status": "SEED",
            "progress": 0.18,
            "confidence": 0.20,
            "evidence_count": 0,
        })
    return seeds


def _candidate_programs(results_dir: Path, clean_results: List[Any] | None = None) -> List[Dict[str, Any]]:
    programs = _program_records(results_dir)
    if programs:
        return programs
    return _fallback_seed_programs(results_dir)


def _team_status(team: Dict[str, Any]) -> str:
    age = safe_int(team.get("age"), 0)
    prod = safe_float(team.get("productivity"), 0.0)
    skill = safe_float(team.get("skill"), 0.0)
    assigned = safe_int(team.get("assigned_observers"), 0)
    failures = safe_int(team.get("failures"), 0)
    if assigned <= 0 and age > 2:
        return "INACTIVE"
    if failures >= 5 and prod < 0.18:
        return "AT_RISK"
    if prod > 0.70 and skill > 0.65:
        return "LEADING"
    if prod > 0.38 or assigned >= 4:
        return "ACTIVE"
    return "SEED"


def _skill_for_topic(topic: str, observer: Dict[str, Any]) -> float:
    arch = str(observer.get("observer_archetype") or observer.get("archetype") or observer.get("species_id") or "").lower()
    species = str(observer.get("species_id") or "").lower()
    text = f"{arch} {species}"
    score = 0.30
    if topic == "memory" and "memory" in text:
        score += 0.45
    if topic in ("knowledge", "information") and ("info" in text or "knowledge" in text):
        score += 0.45
    if topic == "crystal" and "crystal" in text:
        score += 0.45
    if topic == "stability" and ("stability" in text or "temporal" in text):
        score += 0.40
    if topic == "novelty" and ("novel" in text or "explor" in text):
        score += 0.40
    if topic == "civilization" and "civil" in text:
        score += 0.45
    if topic in ("general", "general_pattern") and ("general" in text or not text.strip()):
        score += 0.20
    score += 0.20 * clamp(observer.get("fitness", 0.0) / 120.0)
    return round(clamp(score), 6)


def initialize_teams(results_dir: Path, script: str = "") -> Dict[str, Any]:
    results_dir = Path(results_dir)
    tdir = _team_dir(results_dir)
    teams = _load_teams(results_dir)
    status_counts: Dict[str, int] = {}
    for t in teams.values():
        if isinstance(t, dict):
            status_counts[str(t.get("status", "UNKNOWN"))] = status_counts.get(str(t.get("status", "UNKNOWN")), 0) + 1
    status = {
        "version": TEAM_VERSION,
        "active": True,
        "safe": True,
        "script": script,
        "created_at": now_s(),
        "team_count": len(teams),
        "active_teams": sum(1 for t in teams.values() if isinstance(t, dict) and t.get("status") in ("SEED", "ACTIVE", "LEADING")),
        "status_counts": status_counts,
        "phase": "TEAM_FOUNDATION" if len(teams) < 3 else "TEAM_ACCUMULATION",
    }
    atomic_write_json(tdir / "research_teams_status.json", status)
    atomic_write_json(results_dir / "research_teams_status.json", status)
    return status


def apply_research_teams(results_dir: Path, generation: int, score_mode: str, observer_population: List[Dict[str, Any]], clean_results: List[Any], context: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    results_dir = Path(results_dir)
    tdir = _team_dir(results_dir)
    context = context or {}
    teams = _load_teams(results_dir)
    history = _load_history(results_dir)
    programs = _candidate_programs(results_dir, clean_results)
    discoveries = _load_discoveries(results_dir)
    now = now_s()

    created = 0
    updated = 0

    # Build or update teams from programs. Conservative default: one team per program/topic.
    for idx, p in enumerate(programs):
        if not isinstance(p, dict):
            continue
        topic = _normalize_topic(p.get("topic"))
        inst = str(p.get("institution") or p.get("lead_institution") or "general_research_institute")
        program_id = str(p.get("program_id") or p.get("id") or f"SEED-PROGRAM-{_hash(inst+topic)}")
        tid = _team_id(inst, program_id, topic, 0)
        old = teams.get(tid, {}) if isinstance(teams.get(tid), dict) else {}
        if not old:
            created += 1
            old = {
                "team_id": tid,
                "title": _team_title(topic, inst),
                "institution": inst,
                "program_id": program_id,
                "topic": topic,
                "created_generation": generation,
                "created_at": now,
                "age": 0,
                "members": [],
                "status": "SEED",
            }
        else:
            updated += 1
        # Team inherits program state.
        inherited_progress = safe_float(p.get("progress"), 0.0)
        inherited_conf = safe_float(p.get("confidence"), 0.0)
        inherited_evidence = safe_int(p.get("evidence_count"), len(p.get("discoveries", []) if isinstance(p.get("discoveries"), list) else []))
        old.update({
            "version": TEAM_VERSION,
            "updated_at": now,
            "last_generation": generation,
            "age": safe_int(old.get("age"), 0) + 1,
            "institution": inst,
            "program_id": program_id,
            "topic": topic,
            "program_status": p.get("status", "SEED"),
            "program_progress": inherited_progress,
            "program_confidence": inherited_conf,
            "evidence_count": inherited_evidence,
        })
        teams[tid] = old

    # Age untouched teams.
    current_team_ids = { _team_id(str(p.get("institution") or p.get("lead_institution") or "general_research_institute"), str(p.get("program_id") or p.get("id") or f"SEED-PROGRAM-{_hash(str(p))}"), _normalize_topic(p.get("topic")), 0) for p in programs if isinstance(p, dict) }
    for tid, t in teams.items():
        if isinstance(t, dict) and tid not in current_team_ids:
            t["age"] = safe_int(t.get("age"), 0) + 1
            t["staleness"] = safe_int(t.get("staleness"), 0) + 1

    # Assign observer population to best fitting teams.
    active_teams = [t for t in teams.values() if isinstance(t, dict) and t.get("status") not in ("RETIRED",)]
    active_teams.sort(key=lambda t: (safe_float(t.get("program_progress"), 0.0), safe_float(t.get("program_confidence"), 0.0)), reverse=True)

    for t in active_teams:
        t["members"] = []
        t["assigned_observers"] = 0
        t["mean_member_skill"] = 0.0

    if active_teams:
        for idx, obs in enumerate(observer_population or []):
            if not isinstance(obs, dict):
                continue
            # Prefer topic fit but keep round-robin diversity.
            scored = []
            for t in active_teams:
                topic = _normalize_topic(t.get("topic"))
                fit = _skill_for_topic(topic, obs)
                fit += 0.08 * safe_float(t.get("program_progress"), 0.0)
                fit += 0.04 * (1.0 - min(1.0, safe_int(t.get("assigned_observers"), 0) / 8.0))
                scored.append((fit, t))
            scored.sort(key=lambda kv: kv[0], reverse=True)
            # Every third assignment uses the next best team to prevent monoculture.
            chosen = scored[1][1] if len(scored) > 1 and idx % 3 == 2 else scored[0][1]
            skill = _skill_for_topic(_normalize_topic(chosen.get("topic")), obs)
            obs["research_team_id"] = chosen.get("team_id")
            obs["research_team_topic"] = chosen.get("topic")
            obs["research_team_institution"] = chosen.get("institution")
            obs["research_team_skill"] = skill
            chosen.setdefault("members", []).append(obs.get("id", idx))
            chosen["assigned_observers"] = safe_int(chosen.get("assigned_observers"), 0) + 1

    # Estimate team productivity from current clean results and discoveries.
    top_metrics = []
    for item in (clean_results or [])[:12]:
        try:
            _score, _rule, metrics = item
            if isinstance(metrics, dict):
                top_metrics.append(metrics)
        except Exception:
            pass

    for t in active_teams:
        topic = _normalize_topic(t.get("topic"))
        assigned = safe_int(t.get("assigned_observers"), 0)
        skills = []
        for obs in observer_population or []:
            if isinstance(obs, dict) and obs.get("research_team_id") == t.get("team_id"):
                skills.append(safe_float(obs.get("research_team_skill"), 0.0))
        mean_skill = sum(skills) / max(1, len(skills))
        topic_signal = 0.0
        for m in top_metrics:
            if topic == "memory":
                topic_signal += safe_float(m.get("memory_score"), 0.0) + safe_float(m.get("field_memory"), 0.0)
            elif topic in ("knowledge", "information"):
                topic_signal += safe_float(m.get("information_score", m.get("knowledge_score", 0.0)), 0.0)
            elif topic == "crystal":
                topic_signal += safe_float(m.get("quasi_particle_score", m.get("crystal_defect_score", 0.0)), 0.0)
            elif topic == "stability":
                topic_signal += safe_float(m.get("stability", m.get("stochastic_stability", 0.0)), 0.0)
            elif topic == "organism":
                topic_signal += safe_float(m.get("organism_score", 0.0), 0.0)
            elif topic == "novelty":
                topic_signal += safe_float(m.get("novelty_behavior", 0.0), 0.0)
            else:
                topic_signal += safe_float(m.get("in_generation_diversity", 0.0), 0.0)
        topic_signal = clamp(topic_signal / max(1, len(top_metrics)))
        discovery_bonus = 0.0
        for d in discoveries.values():
            if isinstance(d, dict) and _normalize_topic(d.get("topic")) == topic:
                discovery_bonus += 0.05 + 0.08 * safe_float(d.get("confidence"), 0.0)
        discovery_bonus = clamp(discovery_bonus, 0.0, 0.30)
        productivity = round(clamp(0.35 * mean_skill + 0.25 * topic_signal + 0.20 * safe_float(t.get("program_progress"), 0.0) + 0.12 * min(1.0, assigned / 8.0) + 0.08 * discovery_bonus), 6)
        t["mean_member_skill"] = round(mean_skill, 6)
        t["topic_signal"] = round(topic_signal, 6)
        t["productivity"] = productivity
        t["skill"] = round(clamp(0.65 * mean_skill + 0.35 * safe_float(t.get("program_confidence"), 0.0)), 6)
        t["discoveries_claimed"] = safe_int(t.get("discoveries_claimed"), 0) + (1 if discovery_bonus > 0.08 and productivity > 0.45 else 0)
        t["experiments"] = safe_int(t.get("experiments"), 0) + max(1, assigned)
        if productivity < 0.18 and safe_int(t.get("age"), 0) > 2:
            t["failures"] = safe_int(t.get("failures"), 0) + 1
        t["status"] = _team_status(t)

    status_counts: Dict[str, int] = {}
    for t in teams.values():
        if isinstance(t, dict):
            status_counts[str(t.get("status", "UNKNOWN"))] = status_counts.get(str(t.get("status", "UNKNOWN")), 0) + 1
    active_teams = [t for t in teams.values() if isinstance(t, dict) and t.get("status") not in ("RETIRED", "INACTIVE")]
    leading = max(active_teams, key=lambda t: safe_float(t.get("productivity"), 0.0), default={})
    mean_prod = sum(safe_float(t.get("productivity"), 0.0) for t in active_teams) / max(1, len(active_teams))
    mean_skill = sum(safe_float(t.get("skill"), 0.0) for t in active_teams) / max(1, len(active_teams))

    report = {
        "version": TEAM_VERSION,
        "active": True,
        "safe": True,
        "generation": generation,
        "score_mode": score_mode,
        "updated_at": now,
        "team_count": len(teams),
        "created_teams": created,
        "updated_teams": updated,
        "active_teams": len(active_teams),
        "status_counts": status_counts,
        "leading_team": leading.get("team_id"),
        "leading_topic": leading.get("topic"),
        "leading_institution": leading.get("institution"),
        "mean_productivity": round(mean_prod, 6),
        "mean_skill": round(mean_skill, 6),
        "phase": "TEAM_FOUNDATION" if len(teams) < 3 else "TEAM_OPERATION",
        "context": context,
    }

    history.append({
        "time": now,
        "generation": generation,
        "team_count": len(teams),
        "created": created,
        "updated": updated,
        "active_teams": len(active_teams),
        "leading_team": report.get("leading_team"),
        "mean_productivity": report.get("mean_productivity"),
        "mean_skill": report.get("mean_skill"),
    })
    history = history[-1000:]

    # Team graph: institution -> program -> team -> observers.
    graph = {"nodes": {}, "edges": {}}
    for tid, t in teams.items():
        if not isinstance(t, dict):
            continue
        inst = str(t.get("institution") or "unknown_institute")
        pid = str(t.get("program_id") or "unknown_program")
        graph["nodes"][inst] = {"type": "institution"}
        graph["nodes"][pid] = {"type": "program", "topic": t.get("topic")}
        graph["nodes"][tid] = {"type": "team", "topic": t.get("topic"), "status": t.get("status")}
        graph["edges"][f"{inst}->{pid}"] = {"source": inst, "target": pid, "relation": "SPONSORS"}
        graph["edges"][f"{pid}->{tid}"] = {"source": pid, "target": tid, "relation": "EXECUTED_BY"}
        for member in (t.get("members") or [])[:200]:
            oid = f"observer:{member}"
            graph["nodes"][oid] = {"type": "observer"}
            graph["edges"][f"{tid}->{oid}"] = {"source": tid, "target": oid, "relation": "HAS_MEMBER"}

    atomic_write_json(tdir / "research_teams.json", teams)
    atomic_write_json(tdir / "research_team_history.json", history)
    atomic_write_json(tdir / "research_team_graph.json", graph)
    atomic_write_json(tdir / f"generation_{generation:02d}_teams.json", report)
    atomic_write_json(tdir / "research_teams_status.json", report)
    atomic_write_json(results_dir / "research_teams_status.json", report)

    return observer_population, report


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    if not isinstance(status, dict):
        print(f"[{prefix}] {TEAM_VERSION} | no status")
        return
    print(
        f"[{prefix}] {TEAM_VERSION} | "
        f"active={status.get('active')} safe={status.get('safe')} "
        f"teams={status.get('team_count', 0)} "
        f"active_teams={status.get('active_teams', 0)} "
        f"phase={status.get('phase', '-')}"
    )
