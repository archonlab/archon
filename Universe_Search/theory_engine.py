#!/usr/bin/env python3
"""
Universe Search v32.0 - Theory Engine

Folder-safe theory-formation layer above ExperimentEngine.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_theories/ plus root mirror theory_engine_status.json.
- Promote repeated experimental/discovery/research-program signals into theory candidates.
- Conservative first layer: tracks theories and annotates observers only; no hard steering of core search yet.
"""
from __future__ import annotations

import json
import math
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

THEORY_VERSION = "v32.0 Theory Engine"
THEORY_DIR = "observer_theories"
EXPERIMENT_DIR = "observer_experiments"
DISCOVERY_DIR = "observer_discoveries"
PROGRAM_DIR = "observer_research_programs"
TEAM_DIR = "observer_research_teams"
INSTITUTION_DIR = "observer_institutions"

TOPIC_THEORY_NAMES = {
    "memory": "Memory Persistence Theory",
    "knowledge": "Knowledge Accumulation Theory",
    "information": "Information Transfer Theory",
    "crystal": "Crystal-Stability Boundary Theory",
    "stability": "Stability-Replication Theory",
    "organism": "Organism-Like Persistence Theory",
    "civilization": "Observer Civilization Knowledge Theory",
    "novelty": "Novelty Search Theory",
    "general_pattern": "General Pattern Formation Theory",
}

TOPIC_EXPLANATIONS = {
    "memory": "Long-lived field memory may increase persistence and repeatability in promising rule families.",
    "knowledge": "Knowledge accumulation may precede stronger validated emergence and reusable observations.",
    "information": "Information transfer may act as an early scaffold for stable organization.",
    "crystal": "Crystal-like structures may be stable without necessarily indicating life-like dynamics.",
    "stability": "Replicated persistence across generations may separate signal from transient pattern noise.",
    "organism": "Bounded turnover and survival-like components may indicate organism-like behavior.",
    "civilization": "Collective observer memory and exchange may improve research continuity across generations.",
    "novelty": "High novelty may expose mechanisms outside currently dominant research lineages.",
    "general_pattern": "Baseline pattern quality remains useful as a control against over-reading complex visuals.",
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


def _theory_dir(results_dir: Path) -> Path:
    p = Path(results_dir) / THEORY_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hash(s: Any) -> str:
    return hashlib.sha1(str(s).encode("utf-8", errors="replace")).hexdigest()[:10]


def _normalize_topic(topic: Any) -> str:
    t = str(topic or "general_pattern").lower().strip()
    aliases = {"info": "information", "general": "general_pattern", "pattern": "general_pattern", "patterns": "general_pattern"}
    return aliases.get(t, t)


def _load_dict(results_dir: Path, subdir: str, filename: str) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / subdir / filename, {})
    return data if isinstance(data, dict) else {}


def _load_list(results_dir: Path, subdir: str, filename: str) -> List[Dict[str, Any]]:
    data = read_json(Path(results_dir) / subdir / filename, [])
    return data if isinstance(data, list) else []


def _load_theories(results_dir: Path) -> Dict[str, Any]:
    data = read_json(_theory_dir(results_dir) / "theories.json", {})
    return data if isinstance(data, dict) else {}


def _load_history(results_dir: Path) -> List[Dict[str, Any]]:
    data = read_json(_theory_dir(results_dir) / "theory_history.json", [])
    return data if isinstance(data, list) else []


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


def _theory_id(topic: str) -> str:
    return f"TH-{topic.upper().replace('-', '_')}-{_hash(topic)[:6]}"


def _status(confidence: float, evidence_count: int, replications: int, contradictions: int) -> str:
    if contradictions >= max(2, evidence_count // 2) and evidence_count >= 3:
        return "CONTESTED"
    if confidence >= 0.88 and replications >= 12 and evidence_count >= 18:
        return "ACCEPTED"
    if confidence >= 0.75 and replications >= 5 and evidence_count >= 8:
        return "SUPPORTED"
    if confidence >= 0.55 and evidence_count >= 3:
        return "CANDIDATE"
    if confidence >= 0.35 or evidence_count > 0:
        return "HYPOTHESIS_SEED"
    return "EMPTY"


def _collect_topic_evidence(results_dir: Path, clean_results: List[Any]) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}

    def b(topic: str) -> Dict[str, Any]:
        topic = _normalize_topic(topic)
        if topic not in buckets:
            buckets[topic] = {
                "topic": topic,
                "experiments": [],
                "discoveries": [],
                "programs": [],
                "teams": [],
                "metric_signals": [],
                "contradictions": 0,
                "replications": 0,
                "authors": set(),
            }
        return buckets[topic]

    experiments = _load_dict(results_dir, EXPERIMENT_DIR, "experiments.json")
    discoveries = _load_dict(results_dir, DISCOVERY_DIR, "discoveries.json")
    programs = _load_dict(results_dir, PROGRAM_DIR, "research_programs.json")
    teams = _load_dict(results_dir, TEAM_DIR, "research_teams.json")

    for eid, e in experiments.items():
        if not isinstance(e, dict):
            continue
        topic = _normalize_topic(e.get("topic"))
        bb = b(topic)
        bb["experiments"].append(eid)
        status = str(e.get("status", "")).upper()
        if status in ("SUCCESS", "MIXED"):
            bb["replications"] += 1 if e.get("repeatable") else 0
        if status in ("FAILED", "CONTRADICTED"):
            bb["contradictions"] += 1
        inst = e.get("institution") or e.get("author")
        if inst:
            bb["authors"].add(str(inst))

    for did, d in discoveries.items():
        if not isinstance(d, dict):
            continue
        topic = _normalize_topic(d.get("topic"))
        bb = b(topic)
        bb["discoveries"].append(did)
        if safe_float(d.get("confidence"), 0) >= 0.55:
            bb["replications"] += safe_int(d.get("replications"), 0)
        inst = d.get("author") or d.get("institution")
        if inst:
            bb["authors"].add(str(inst))

    for pid, p in programs.items():
        if not isinstance(p, dict):
            continue
        topic = _normalize_topic(p.get("topic"))
        bb = b(topic)
        bb["programs"].append(pid)
        if p.get("status") in ("FAILED", "CLOSED"):
            bb["contradictions"] += 1
        inst = p.get("institution")
        if inst:
            bb["authors"].add(str(inst))

    for tid, t in teams.items():
        if not isinstance(t, dict):
            continue
        topic = _normalize_topic(t.get("topic"))
        bb = b(topic)
        bb["teams"].append(tid)
        inst = t.get("institution")
        if inst:
            bb["authors"].add(str(inst))

    for item in (clean_results or [])[:24]:
        try:
            _score, _rule, metrics = item
            if isinstance(metrics, dict):
                topic = _topic_from_metrics(metrics)
                signal = max(
                    safe_float(metrics.get("memory_score"), 0),
                    safe_float(metrics.get("information_score", metrics.get("knowledge_score", 0)), 0),
                    safe_float(metrics.get("quasi_particle_score", 0), 0),
                    safe_float(metrics.get("organism_score", 0), 0),
                    safe_float(metrics.get("novelty_behavior", 0), 0),
                    safe_float(metrics.get("stability", 0), 0),
                )
                b(topic)["metric_signals"].append(clamp(signal))
        except Exception:
            pass

    # JSON friendliness
    for bb in buckets.values():
        bb["authors"] = sorted(list(bb.get("authors", [])))
    return buckets


def initialize_theories(results_dir: Path, script: str = "") -> Dict[str, Any]:
    results_dir = Path(results_dir)
    tdir = _theory_dir(results_dir)
    theories = _load_theories(results_dir)
    status_counts: Dict[str, int] = {}
    for t in theories.values():
        if isinstance(t, dict):
            s = str(t.get("status", "UNKNOWN"))
            status_counts[s] = status_counts.get(s, 0) + 1
    status = {
        "version": THEORY_VERSION,
        "active": True,
        "safe": True,
        "script": script,
        "created_at": now_s(),
        "theories": len(theories),
        "active_theories": sum(1 for t in theories.values() if isinstance(t, dict) and t.get("status") not in ("REJECTED", "ARCHIVED", "EMPTY")),
        "status_counts": status_counts,
        "phase": "THEORY_FOUNDATION" if len(theories) < 3 else "THEORY_ACCUMULATION",
    }
    atomic_write_json(tdir / "theory_status.json", status)
    atomic_write_json(results_dir / "theory_engine_status.json", status)
    return status


def apply_theory_engine(results_dir: Path, generation: int, score_mode: str, observer_population: List[Dict[str, Any]], clean_results: List[Any], context: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    results_dir = Path(results_dir)
    tdir = _theory_dir(results_dir)
    context = context or {}
    theories = _load_theories(results_dir)
    history = _load_history(results_dir)
    topic_evidence = _collect_topic_evidence(results_dir, clean_results)
    now = now_s()

    created = 0
    updated = 0
    generation_theories: List[Dict[str, Any]] = []

    for topic, ev in sorted(topic_evidence.items()):
        evidence_count = len(ev.get("experiments", [])) + len(ev.get("discoveries", [])) + len(ev.get("programs", []))
        signals = ev.get("metric_signals", []) or []
        mean_signal = sum(signals) / max(1, len(signals))
        replications = safe_int(ev.get("replications"), 0)
        contradictions = safe_int(ev.get("contradictions"), 0)
        author_diversity = len(ev.get("authors", []))
        if evidence_count == 0 and mean_signal < 0.08:
            continue
        tid = _theory_id(topic)
        prev = theories.get(tid, {}) if isinstance(theories.get(tid), dict) else {}
        old_evidence = safe_int(prev.get("evidence_count"), 0)
        old_rep = safe_int(prev.get("replications"), 0)
        old_contra = safe_int(prev.get("contradictions"), 0)
        total_evidence = old_evidence + evidence_count
        total_rep = old_rep + replications
        total_contra = old_contra + contradictions
        novelty = clamp(mean_signal * 0.45 + min(1.0, evidence_count / 8.0) * 0.30 + min(1.0, author_diversity / 4.0) * 0.25)
        confidence = clamp(
            0.22
            + 0.30 * min(1.0, total_evidence / 10.0)
            + 0.22 * min(1.0, total_rep / 8.0)
            + 0.18 * mean_signal
            + 0.12 * min(1.0, author_diversity / 4.0)
            - 0.25 * min(1.0, total_contra / max(1, total_evidence))
        )
        status = _status(confidence, total_evidence, total_rep, total_contra)
        theory = {
            "theory_id": tid,
            "name": TOPIC_THEORY_NAMES.get(topic, f"{topic.title()} Theory"),
            "topic": topic,
            "explanation": TOPIC_EXPLANATIONS.get(topic, "A candidate explanatory frame induced from repeated observations."),
            "status": status,
            "birth_generation": prev.get("birth_generation", generation),
            "last_seen_generation": generation,
            "updated_at": now,
            "evidence_count": total_evidence,
            "new_evidence": evidence_count,
            "replications": total_rep,
            "contradictions": total_contra,
            "confidence": round(confidence, 6),
            "novelty": round(novelty, 6),
            "mean_signal": round(mean_signal, 6),
            "authors": sorted(set((prev.get("authors") or []) + (ev.get("authors") or []))),
            "supporting_experiments": sorted(set((prev.get("supporting_experiments") or []) + (ev.get("experiments") or [])))[-100:],
            "supporting_discoveries": sorted(set((prev.get("supporting_discoveries") or []) + (ev.get("discoveries") or [])))[-100:],
            "supporting_programs": sorted(set((prev.get("supporting_programs") or []) + (ev.get("programs") or [])))[-100:],
            "lineage": prev.get("lineage") or [],
        }
        if tid in theories:
            updated += 1
        else:
            created += 1
            theory["lineage"] = [f"born:generation:{generation}", f"topic:{topic}"]
        theories[tid] = theory
        generation_theories.append(theory)

    graph = {
        "version": THEORY_VERSION,
        "generated_at": now,
        "nodes": [],
        "edges": [],
    }
    for tid, t in theories.items():
        if not isinstance(t, dict):
            continue
        graph["nodes"].append({"id": tid, "topic": t.get("topic"), "status": t.get("status"), "confidence": t.get("confidence")})
        for did in t.get("supporting_discoveries") or []:
            graph["edges"].append({"source": did, "target": tid, "type": "supports_theory"})
        for eid in t.get("supporting_experiments") or []:
            graph["edges"].append({"source": eid, "target": tid, "type": "evidence_for"})

    # Annotate observers with strongest theory topic if possible.
    active_theories = [t for t in theories.values() if isinstance(t, dict) and t.get("status") not in ("EMPTY", "ARCHIVED", "REJECTED")]
    active_theories.sort(key=lambda t: safe_float(t.get("confidence"), 0), reverse=True)
    lead_theory = active_theories[0] if active_theories else None
    annotated: List[Dict[str, Any]] = []
    for i, obs in enumerate(observer_population or []):
        if not isinstance(obs, dict):
            annotated.append(obs)
            continue
        o = dict(obs)
        if lead_theory:
            o.setdefault("theory_context_id", lead_theory.get("theory_id"))
            o.setdefault("theory_context_topic", lead_theory.get("topic"))
        annotated.append(o)

    history_event = {
        "time": now,
        "generation": generation,
        "created": created,
        "updated": updated,
        "theory_count": len(theories),
        "active_theories": len(active_theories),
        "lead_theory": lead_theory.get("theory_id") if lead_theory else None,
        "lead_confidence": lead_theory.get("confidence") if lead_theory else 0.0,
    }
    history.append(history_event)
    history = history[-500:]

    status_counts: Dict[str, int] = {}
    for t in theories.values():
        if isinstance(t, dict):
            s = str(t.get("status", "UNKNOWN"))
            status_counts[s] = status_counts.get(s, 0) + 1
    status = {
        "version": THEORY_VERSION,
        "active": True,
        "safe": True,
        "generation": generation,
        "theories": len(theories),
        "active_theories": len(active_theories),
        "created": created,
        "updated": updated,
        "status_counts": status_counts,
        "lead_theory": lead_theory.get("theory_id") if lead_theory else None,
        "lead_topic": lead_theory.get("topic") if lead_theory else None,
        "lead_confidence": lead_theory.get("confidence") if lead_theory else 0.0,
        "phase": "THEORY_FOUNDATION" if len(theories) < 3 else "THEORY_ACCUMULATION",
    }

    atomic_write_json(tdir / "theories.json", theories)
    atomic_write_json(tdir / "theory_history.json", history)
    atomic_write_json(tdir / "theory_graph.json", graph)
    atomic_write_json(tdir / "theory_status.json", status)
    atomic_write_json(tdir / f"generation_{generation:02d}_theories.json", generation_theories)
    atomic_write_json(results_dir / "theory_engine_status.json", status)

    return annotated or observer_population, status


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    if not isinstance(status, dict):
        print(f"[{prefix}] no status")
        return
    print(
        f"[{prefix}] {status.get('version', THEORY_VERSION)} | "
        f"active={status.get('active')} safe={status.get('safe')} "
        f"theories={status.get('theories',0)} active_theories={status.get('active_theories',0)} "
        f"created={status.get('created',0)} lead={status.get('lead_topic') or '-'} "
        f"confidence={safe_float(status.get('lead_confidence'),0):.3f} "
        f"phase={status.get('phase','-')}"
    )
