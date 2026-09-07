#!/usr/bin/env python3
"""
Universe Search v33.0 - Paradigm Engine

Folder-safe paradigm layer above TheoryEngine.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_paradigms/ plus root mirror paradigm_engine_status.json.
- Group compatible theories/discoveries/programs into broader scientific paradigms.
- Conservative first layer: tracks paradigms and annotates observers only; no hard steering of core search yet.
"""
from __future__ import annotations

import json
import math
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

PARADIGM_VERSION = "v33.0 Paradigm Engine"
PARADIGM_DIR = "observer_paradigms"
THEORY_DIR = "observer_theories"
DISCOVERY_DIR = "observer_discoveries"
PROGRAM_DIR = "observer_research_programs"
NETWORK_DIR = "observer_network"
INSTITUTION_DIR = "observer_institutions"

TOPIC_PARADIGM_NAMES = {
    "memory": "Memory-Centered Research Paradigm",
    "knowledge": "Knowledge Accumulation Paradigm",
    "information": "Information Scaffold Paradigm",
    "crystal": "Crystal-Control Boundary Paradigm",
    "stability": "Stability and Replication Paradigm",
    "organism": "Organism-Like Persistence Paradigm",
    "civilization": "Collective Observer Civilization Paradigm",
    "novelty": "Novelty-Driven Exploration Paradigm",
    "general_pattern": "General Pattern Science Paradigm",
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


def _paradigm_dir(results_dir: Path) -> Path:
    p = Path(results_dir) / PARADIGM_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hash(s: Any) -> str:
    return hashlib.sha1(str(s).encode("utf-8", errors="replace")).hexdigest()[:10]


def _normalize_topic(topic: Any) -> str:
    t = str(topic or "general_pattern").lower().strip()
    aliases = {
        "info": "information", "general": "general_pattern", "pattern": "general_pattern",
        "patterns": "general_pattern", "memory_hunter": "memory", "knowledge_memory": "knowledge",
    }
    return aliases.get(t, t)


def _load_dict(results_dir: Path, subdir: str, filename: str) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / subdir / filename, {})
    return data if isinstance(data, dict) else {}


def _load_list(results_dir: Path, subdir: str, filename: str) -> List[Dict[str, Any]]:
    data = read_json(Path(results_dir) / subdir / filename, [])
    return data if isinstance(data, list) else []


def _load_paradigms(results_dir: Path) -> Dict[str, Any]:
    data = read_json(_paradigm_dir(results_dir) / "paradigms.json", {})
    return data if isinstance(data, dict) else {}


def _load_history(results_dir: Path) -> List[Dict[str, Any]]:
    data = read_json(_paradigm_dir(results_dir) / "paradigm_history.json", [])
    return data if isinstance(data, list) else []


def _paradigm_id(topic: str) -> str:
    return f"PD-{topic.upper().replace('-', '_')}-{_hash(topic)[:6]}"


def _topic_from_metrics(metrics: Dict[str, Any]) -> str:
    candidates = {
        "memory": safe_float(metrics.get("memory_score"), 0) + 0.5 * safe_float(metrics.get("field_memory"), 0),
        "information": safe_float(metrics.get("information_score", metrics.get("knowledge_score", 0)), 0),
        "crystal": safe_float(metrics.get("quasi_particle_score", metrics.get("crystal_defect_score", 0)), 0),
        "stability": safe_float(metrics.get("stability", metrics.get("stochastic_stability", 0)), 0),
        "organism": safe_float(metrics.get("organism_score"), 0),
        "civilization": safe_float(metrics.get("civilization_score", metrics.get("observer_civilization", 0)), 0),
        "novelty": safe_float(metrics.get("novelty_behavior"), 0),
    }
    topic, val = max(candidates.items(), key=lambda kv: kv[1])
    return topic if val > 0.05 else "general_pattern"


def _status(coherence: float, theory_count: int, discovery_count: int, contradictions: int, age: int) -> str:
    if contradictions >= max(2, theory_count + discovery_count // 2) and (theory_count + discovery_count) >= 3:
        return "CRISIS"
    if coherence >= 0.88 and theory_count >= 5 and discovery_count >= 12 and age >= 6:
        return "DOMINANT"
    if coherence >= 0.74 and theory_count >= 3 and discovery_count >= 5:
        return "ESTABLISHED"
    if coherence >= 0.56 and (theory_count >= 1 or discovery_count >= 2):
        return "EMERGING"
    return "PROTO_PARADIGM"


def _extract_theory_topics(theories: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for tid, th in theories.items():
        if not isinstance(th, dict):
            continue
        topic = _normalize_topic(th.get("topic") or th.get("lead_topic") or th.get("domain") or "general_pattern")
        item = dict(th)
        item.setdefault("id", tid)
        buckets.setdefault(topic, []).append(item)
    return buckets


def _extract_discovery_topics(discoveries: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    items = discoveries.values() if isinstance(discoveries, dict) else []
    for d in items:
        if not isinstance(d, dict):
            continue
        topic = _normalize_topic(d.get("topic") or d.get("domain") or d.get("lead_topic") or "general_pattern")
        buckets.setdefault(topic, []).append(d)
    return buckets


def _extract_program_topics(programs: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    items = programs.values() if isinstance(programs, dict) else []
    for p in items:
        if not isinstance(p, dict):
            continue
        topic = _normalize_topic(p.get("topic") or p.get("domain") or p.get("specialization") or "general_pattern")
        buckets.setdefault(topic, []).append(p)
    return buckets


def _mean(items: List[float], default: float = 0.0) -> float:
    vals = [safe_float(x, 0.0) for x in items if x is not None]
    return sum(vals) / len(vals) if vals else default


def _network_pressure(results_dir: Path) -> float:
    st = read_json(Path(results_dir) / "observer_network_status.json", {})
    if not isinstance(st, dict):
        st = read_json(Path(results_dir) / NETWORK_DIR / "network_status.json", {}) or {}
    return clamp(0.45 * safe_float(st.get("health"), 0.0) + 0.35 * safe_float(st.get("density"), 0.0) + 0.20 * safe_float(st.get("edges"), 0.0) / 10.0)


def _build_paradigm_from_topic(results_dir: Path, topic: str, theories_for_topic: List[Dict[str, Any]], discoveries_for_topic: List[Dict[str, Any]], programs_for_topic: List[Dict[str, Any]], old: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    pid = _paradigm_id(topic)
    now = now_s()
    prev = old.get(pid, {}) if isinstance(old.get(pid), dict) else {}

    theory_conf = _mean([safe_float(t.get("confidence", t.get("lead_confidence", 0))) for t in theories_for_topic], 0.0)
    discovery_conf = _mean([safe_float(d.get("confidence", d.get("importance", 0))) for d in discoveries_for_topic], 0.0)
    program_progress = _mean([safe_float(p.get("progress", p.get("confidence", 0))) for p in programs_for_topic], 0.0)
    evidence_count = sum(safe_int(t.get("evidence_count", t.get("evidence", 0))) for t in theories_for_topic)
    contradictions = sum(safe_int(t.get("contradictions", 0)) for t in theories_for_topic) + sum(safe_int(d.get("contradictions", 0)) for d in discoveries_for_topic)
    replications = sum(safe_int(t.get("replications", 0)) for t in theories_for_topic) + sum(safe_int(d.get("replications", 0)) for d in discoveries_for_topic)
    network = _network_pressure(results_dir)

    theory_count = len(theories_for_topic)
    discovery_count = len(discoveries_for_topic)
    program_count = len(programs_for_topic)
    age = safe_int(prev.get("age"), 0) + 1

    support_mass = clamp((theory_count * 0.20 + discovery_count * 0.06 + program_count * 0.08 + replications * 0.035) / 2.0)
    quality = clamp(0.45 * theory_conf + 0.30 * discovery_conf + 0.15 * program_progress + 0.10 * network)
    contradiction_penalty = clamp(contradictions / max(1.0, theory_count + discovery_count + replications))
    coherence = clamp(0.48 * quality + 0.38 * support_mass + 0.14 * network - 0.30 * contradiction_penalty)

    status = _status(coherence, theory_count, discovery_count, contradictions, age)
    paradigm = {
        "id": pid,
        "topic": topic,
        "name": TOPIC_PARADIGM_NAMES.get(topic, TOPIC_PARADIGM_NAMES["general_pattern"]),
        "status": status,
        "created_at": prev.get("created_at") or now,
        "updated_at": now,
        "age": age,
        "coherence": round(coherence, 4),
        "quality": round(quality, 4),
        "support_mass": round(support_mass, 4),
        "network_support": round(network, 4),
        "theory_count": theory_count,
        "discovery_count": discovery_count,
        "program_count": program_count,
        "evidence_count": evidence_count,
        "replications": replications,
        "contradictions": contradictions,
        "theories": [t.get("id") for t in theories_for_topic if t.get("id")],
        "discoveries": [d.get("id") for d in discoveries_for_topic if d.get("id")],
        "programs": [p.get("id") for p in programs_for_topic if p.get("id")],
        "lineage": prev.get("lineage", []) + ([prev.get("status")] if prev.get("status") and prev.get("status") != status else []),
    }
    return pid, paradigm


def _write_outputs(results_dir: Path, paradigms: Dict[str, Any], history: List[Dict[str, Any]], status: Dict[str, Any], generation: int | None = None) -> None:
    pdir = _paradigm_dir(results_dir)
    atomic_write_json(pdir / "paradigms.json", paradigms)
    atomic_write_json(pdir / "paradigm_history.json", history[-1000:])

    graph = {"nodes": [], "edges": []}
    for pid, p in paradigms.items():
        graph["nodes"].append({"id": pid, "topic": p.get("topic"), "status": p.get("status"), "coherence": p.get("coherence")})
        for tid in p.get("theories", []) or []:
            graph["edges"].append({"from": tid, "to": pid, "type": "supports_paradigm"})
        for did in p.get("discoveries", []) or []:
            graph["edges"].append({"from": did, "to": pid, "type": "evidence_for_paradigm"})
    atomic_write_json(pdir / "paradigm_graph.json", graph)
    atomic_write_json(pdir / "paradigm_status.json", status)
    atomic_write_json(Path(results_dir) / "paradigm_engine_status.json", status)
    if generation is not None:
        atomic_write_json(pdir / f"generation_{generation:02d}_paradigms.json", {"status": status, "paradigms": paradigms})


def initialize_paradigms(results_dir: Path, script: str = "") -> Dict[str, Any]:
    results_dir = Path(results_dir)
    pdir = _paradigm_dir(results_dir)
    paradigms = _load_paradigms(results_dir)
    theories = _load_dict(results_dir, THEORY_DIR, "theories.json")
    status = {
        "version": PARADIGM_VERSION,
        "active": True,
        "safe": True,
        "script": script,
        "phase": "PARADIGM_FOUNDATION" if not paradigms else "PARADIGM_TRACKING",
        "paradigms": len(paradigms),
        "active_paradigms": sum(1 for p in paradigms.values() if isinstance(p, dict) and p.get("status") not in ("ARCHIVED", "CRISIS")),
        "theories": len(theories),
        "dominant": max(paradigms.values(), key=lambda p: safe_float(p.get("coherence"), 0)).get("id") if paradigms else "",
        "coherence": round(_mean([safe_float(p.get("coherence"), 0) for p in paradigms.values() if isinstance(p, dict)], 0.0), 4),
        "timestamp": now_s(),
    }
    atomic_write_json(pdir / "paradigm_status.json", status)
    atomic_write_json(results_dir / "paradigm_engine_status.json", status)
    return status


def apply_paradigm_engine(results_dir: Path, generation: int, score_mode: str, observer_population: List[Dict[str, Any]], clean_results: List[Tuple[Any, Any, Dict[str, Any]]], context: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    results_dir = Path(results_dir)
    old_paradigms = _load_paradigms(results_dir)
    theories = _load_dict(results_dir, THEORY_DIR, "theories.json")
    discoveries = _load_dict(results_dir, DISCOVERY_DIR, "discoveries.json")
    programs = _load_dict(results_dir, PROGRAM_DIR, "research_programs.json")

    theory_b = _extract_theory_topics(theories)
    discovery_b = _extract_discovery_topics(discoveries)
    program_b = _extract_program_topics(programs)

    # Also let current generation metrics seed a weak topic bucket, so the layer is alive before true theories exist.
    current_topics: Dict[str, int] = {}
    for _, _, m in clean_results or []:
        if isinstance(m, dict):
            current_topics[_topic_from_metrics(m)] = current_topics.get(_topic_from_metrics(m), 0) + 1

    topics = set(theory_b) | set(discovery_b) | set(program_b)
    # Conservative: if there are no upstream theory/discovery/program objects, do not create real paradigms yet.
    if not topics and current_topics:
        topics = set()

    paradigms: Dict[str, Any] = dict(old_paradigms)
    created = 0
    updated = 0
    for topic in sorted(topics):
        pid, p = _build_paradigm_from_topic(
            results_dir,
            topic,
            theory_b.get(topic, []),
            discovery_b.get(topic, []),
            program_b.get(topic, []),
            paradigms,
        )
        if pid not in paradigms:
            created += 1
        else:
            updated += 1
        paradigms[pid] = p

    # Annotate observers with leading paradigm context.
    lead = None
    if paradigms:
        lead = max(paradigms.values(), key=lambda p: safe_float(p.get("coherence"), 0.0))
    for obs in observer_population or []:
        if isinstance(obs, dict):
            obs["paradigm_engine_version"] = PARADIGM_VERSION
            obs["paradigm_id"] = (lead or {}).get("id", "")
            obs["paradigm_topic"] = (lead or {}).get("topic", "")
            obs["paradigm_status"] = (lead or {}).get("status", "")
            obs["paradigm_coherence"] = safe_float((lead or {}).get("coherence"), 0.0)

    active = [p for p in paradigms.values() if isinstance(p, dict) and p.get("status") not in ("ARCHIVED", "CRISIS")]
    coherence = _mean([safe_float(p.get("coherence"), 0) for p in active], 0.0)
    dominant = max(active, key=lambda p: safe_float(p.get("coherence"), 0.0)) if active else {}
    phase = "PARADIGM_FOUNDATION"
    if len(active) >= 1:
        phase = "PROTO_PARADIGM"
    if any(p.get("status") in ("ESTABLISHED", "DOMINANT") for p in active):
        phase = "PARADIGM_FORMATION"
    if any(p.get("status") == "CRISIS" for p in paradigms.values() if isinstance(p, dict)):
        phase = "PARADIGM_CRISIS"

    status = {
        "version": PARADIGM_VERSION,
        "active": True,
        "safe": True,
        "generation": generation,
        "score_mode": score_mode,
        "phase": phase,
        "paradigms": len(paradigms),
        "active_paradigms": len(active),
        "created": created,
        "updated": updated,
        "theories": len(theories),
        "discoveries": len(discoveries),
        "programs": len(programs),
        "dominant": dominant.get("id", ""),
        "dominant_topic": dominant.get("topic", ""),
        "dominant_status": dominant.get("status", ""),
        "coherence": round(coherence, 4),
        "timestamp": now_s(),
    }
    history = _load_history(results_dir)
    history.append({"generation": generation, "timestamp": now_s(), **status})
    _write_outputs(results_dir, paradigms, history, status, generation=generation)
    return observer_population, status


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    print(
        f"[{prefix}] {PARADIGM_VERSION} | "
        f"active={status.get('active')} safe={status.get('safe')} "
        f"paradigms={status.get('paradigms',0)} active_paradigms={status.get('active_paradigms',0)} "
        f"created={status.get('created',0)} dominant={status.get('dominant_topic') or '-'} "
        f"coherence={safe_float(status.get('coherence'),0):.3f} phase={status.get('phase','-')}"
    )


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir", nargs="?", default="universe_search_v23_results")
    args = ap.parse_args()
    st = initialize_paradigms(Path(args.results_dir), script="standalone")
    print_status("ParadigmEngine", st)
