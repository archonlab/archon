#!/usr/bin/env python3
"""
Universe Search v29.0 - Research Programs

Folder-safe long-horizon research program layer above DiscoveryEngine.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_research_programs/ plus root mirror research_programs_status.json.
- Convert persistent discoveries + institutions into long-lived research programs.
- Conservative first layer: plans and annotations only, no hard steering of core search.
"""
from __future__ import annotations

import json
import math
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROGRAM_VERSION = "v29.0 Research Programs"
PROGRAM_DIR = "observer_research_programs"
DISCOVERY_DIR = "observer_discoveries"
INSTITUTION_DIR = "observer_institutions"

TOPIC_LABELS = {
    "memory": "Evolution of Long-Term Memory",
    "knowledge": "Knowledge Accumulation Dynamics",
    "information": "Information Transfer Mechanisms",
    "crystal": "Stable Crystal Morphologies",
    "stability": "Stability and Persistence Tests",
    "organism": "Organism-Like Pattern Formation",
    "civilization": "Observer Civilization Signals",
    "novelty": "Novelty and Search Diversity",
    "general_pattern": "General Pattern Research",
    "general": "General Pattern Research",
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


def _program_dir(results_dir: Path) -> Path:
    p = Path(results_dir) / PROGRAM_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hash(s: str) -> str:
    return hashlib.sha1(str(s).encode("utf-8", errors="replace")).hexdigest()[:10]


def _load_discoveries(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / DISCOVERY_DIR / "discoveries.json", {})
    return data if isinstance(data, dict) else {}


def _load_discovery_history(results_dir: Path) -> List[Dict[str, Any]]:
    data = read_json(Path(results_dir) / DISCOVERY_DIR / "discovery_history.json", [])
    return data if isinstance(data, list) else []


def _load_institutions(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / INSTITUTION_DIR / "institution_registry.json", {})
    if isinstance(data, dict):
        if isinstance(data.get("institutions"), dict):
            return data.get("institutions") or {}
        return data
    return {}


def _load_programs(results_dir: Path) -> Dict[str, Any]:
    data = read_json(_program_dir(results_dir) / "research_programs.json", {})
    return data if isinstance(data, dict) else {}


def _load_history(results_dir: Path) -> List[Dict[str, Any]]:
    data = read_json(_program_dir(results_dir) / "research_program_history.json", [])
    return data if isinstance(data, list) else []


def _normalize_topic(topic: Any) -> str:
    t = str(topic or "general_pattern").lower().strip()
    aliases = {
        "info": "information",
        "general": "general_pattern",
        "pattern": "general_pattern",
    }
    return aliases.get(t, t)


def _program_id(institution: str, topic: str) -> str:
    base = f"{institution}:{topic}"
    return f"PROG-{topic.upper().replace('-', '_')}-{_hash(base)}"


def _program_title(topic: str) -> str:
    return TOPIC_LABELS.get(topic, topic.replace("_", " ").title())


def _select_institution_for_topic(topic: str, discoveries: List[Dict[str, Any]], institutions: Dict[str, Any]) -> str:
    # Prefer existing discovery authors for this topic.
    counts: Dict[str, float] = {}
    for d in discoveries:
        if _normalize_topic(d.get("topic")) != topic:
            continue
        author = str(d.get("author") or d.get("discoverer") or "")
        if author:
            counts[author] = counts.get(author, 0.0) + 1.0 + safe_float(d.get("confidence"), 0.0)
    if counts:
        return max(counts.items(), key=lambda kv: kv[1])[0]

    # Fall back to institutions by specialization.
    topic_specs = {
        "memory": "MEMORY",
        "knowledge": "INFORMATION",
        "information": "INFORMATION",
        "crystal": "STRUCTURE",
        "stability": "TEMPORAL",
        "organism": "STRUCTURE",
        "civilization": "COMPLEXITY",
        "novelty": "GENERAL",
        "general_pattern": "GENERAL",
    }
    wanted = topic_specs.get(topic, "GENERAL")
    best_id, best_score = "general_research_institute", -1.0
    for iid, inst in institutions.items():
        if not isinstance(inst, dict):
            continue
        score = safe_float(inst.get("reputation"), 0.0) + 0.4 * safe_float(inst.get("innovation"), 0.0)
        if str(inst.get("specialization", "")).upper() == wanted:
            score += 0.75
        if score > best_score:
            best_id, best_score = str(iid), score
    return best_id


def _program_status(program: Dict[str, Any]) -> str:
    age = safe_int(program.get("age"), 0)
    evidence = safe_int(program.get("evidence_count"), 0)
    rep = safe_int(program.get("replications"), 0)
    fail = safe_int(program.get("failures"), 0)
    conf = safe_float(program.get("confidence"), 0.0)
    progress = safe_float(program.get("progress"), 0.0)
    if fail >= max(3, evidence) and age > 2:
        return "REJECTED"
    if rep >= 10 and conf > 0.78 and progress > 0.82:
        return "ACCEPTED"
    if rep >= 4 and conf > 0.62:
        return "REPLICATING"
    if evidence >= 2 and conf > 0.45:
        return "ACTIVE"
    if age > 6 and evidence == 0:
        return "DORMANT"
    return "SEED"


def initialize_programs(results_dir: Path, script: str = "") -> Dict[str, Any]:
    results_dir = Path(results_dir)
    pdir = _program_dir(results_dir)
    programs = _load_programs(results_dir)
    status_counts: Dict[str, int] = {}
    for p in programs.values():
        if isinstance(p, dict):
            status_counts[str(p.get("status", "UNKNOWN"))] = status_counts.get(str(p.get("status", "UNKNOWN")), 0) + 1
    status = {
        "version": PROGRAM_VERSION,
        "active": True,
        "safe": True,
        "script": script,
        "created_at": now_s(),
        "program_count": len(programs),
        "active_programs": sum(1 for p in programs.values() if isinstance(p, dict) and p.get("status") in ("SEED", "ACTIVE", "REPLICATING")),
        "status_counts": status_counts,
        "phase": "PROGRAM_FOUNDATION" if len(programs) < 3 else "PROGRAM_ACCUMULATION",
    }
    atomic_write_json(pdir / "research_programs_status.json", status)
    atomic_write_json(results_dir / "research_programs_status.json", status)
    return status


def _collect_current_discoveries(results_dir: Path, clean_results: List[Any] | None = None) -> List[Dict[str, Any]]:
    archive = _load_discoveries(results_dir)
    out: List[Dict[str, Any]] = []
    for d in archive.values():
        if isinstance(d, dict):
            out.append(d)
    # Fallback if discovery archive is still empty: derive weak program seeds from current top results.
    if not out and clean_results:
        for rank, item in enumerate(clean_results[:6], start=1):
            try:
                score, rule, metrics = item
            except Exception:
                continue
            metrics = metrics if isinstance(metrics, dict) else {}
            topic = "memory" if safe_float(metrics.get("memory_score"), 0.0) > 0.2 else "novelty" if safe_float(metrics.get("novelty_behavior"), 0.0) > 0.45 else "general_pattern"
            out.append({
                "id": f"SEED-{rank:03d}",
                "topic": topic,
                "author": str(metrics.get("observer_archetype") or "general_research_institute"),
                "confidence": clamp(safe_float(score, 0.0) / 180.0),
                "importance": clamp(safe_float(metrics.get("novelty_behavior", 0.0)) * 0.5 + safe_float(score, 0.0) / 300.0),
                "replications": 0,
                "status": "SEED",
            })
    return out


def apply_research_programs(results_dir: Path, generation: int, score_mode: str, observer_population: List[Dict[str, Any]], clean_results: List[Any], context: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    results_dir = Path(results_dir)
    pdir = _program_dir(results_dir)
    context = context or {}
    programs = _load_programs(results_dir)
    history = _load_history(results_dir)
    institutions = _load_institutions(results_dir)
    discoveries = _collect_current_discoveries(results_dir, clean_results)
    now = now_s()

    by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for d in discoveries:
        topic = _normalize_topic(d.get("topic"))
        by_topic.setdefault(topic, []).append(d)

    created = 0
    updated = 0
    for topic, ds in by_topic.items():
        institution = _select_institution_for_topic(topic, ds, institutions)
        pid = _program_id(institution, topic)
        old = programs.get(pid, {}) if isinstance(programs.get(pid), dict) else {}
        if not old:
            created += 1
            old = {
                "program_id": pid,
                "title": _program_title(topic),
                "topic": topic,
                "institution": institution,
                "created_generation": generation,
                "created_at": now,
                "age": 0,
                "discoveries": [],
                "status": "SEED",
            }
        else:
            updated += 1

        disc_ids = [str(d.get("id") or d.get("discovery_id") or d.get("rule_signature") or _hash(repr(d))) for d in ds]
        prev_disc = old.get("discoveries") if isinstance(old.get("discoveries"), list) else []
        merged_disc = list(dict.fromkeys([str(x) for x in prev_disc] + disc_ids))
        mean_conf = sum(safe_float(d.get("confidence"), 0.0) for d in ds) / max(1, len(ds))
        mean_imp = sum(safe_float(d.get("importance"), 0.0) for d in ds) / max(1, len(ds))
        replications = sum(safe_int(d.get("replications"), 0) for d in ds)
        failures = sum(1 for d in ds if str(d.get("status", "")).upper() in ("FAILED", "WEAK", "ARCHIVED"))
        old_conf = safe_float(old.get("confidence"), 0.0)
        confidence = round(clamp(max(old_conf * 0.88, mean_conf) + 0.03 * min(5, replications)), 6)
        evidence_count = len(merged_disc)
        age = safe_int(old.get("age"), 0) + 1
        progress = round(clamp(0.32 * confidence + 0.24 * min(1.0, evidence_count / 8.0) + 0.20 * min(1.0, replications / 10.0) + 0.14 * mean_imp + 0.10 * min(1.0, age / 12.0)), 6)
        old.update({
            "version": PROGRAM_VERSION,
            "updated_at": now,
            "last_generation": generation,
            "age": age,
            "institution": institution,
            "topic": topic,
            "title": old.get("title") or _program_title(topic),
            "discoveries": merged_disc,
            "evidence_count": evidence_count,
            "replications": safe_int(old.get("replications"), 0) + replications,
            "failures": safe_int(old.get("failures"), 0) + failures,
            "confidence": confidence,
            "importance": round(max(safe_float(old.get("importance"), 0.0), mean_imp), 6),
            "progress": progress,
            "research_question": old.get("research_question") or f"How does {topic.replace('_', ' ')} contribute to robust rule discovery?",
        })
        old["status"] = _program_status(old)
        programs[pid] = old

    # Age programs not touched this generation.
    touched = {_program_id(_select_institution_for_topic(t, ds, institutions), t) for t, ds in by_topic.items()}
    for pid, p in list(programs.items()):
        if not isinstance(p, dict) or pid in touched:
            continue
        p["age"] = safe_int(p.get("age"), 0) + 1
        p["staleness"] = safe_int(p.get("staleness"), 0) + 1
        # Gentle confidence decay for abandoned seeds.
        if p.get("status") in ("SEED", "DORMANT"):
            p["confidence"] = round(clamp(safe_float(p.get("confidence"), 0.0) * 0.985), 6)
        p["status"] = _program_status(p)
        p["updated_at"] = now

    # Build assignment for observer population. Conservative annotation only.
    active_programs = [p for p in programs.values() if isinstance(p, dict) and p.get("status") not in ("REJECTED", "RETIRED")]
    active_programs.sort(key=lambda p: (safe_float(p.get("progress"), 0.0), safe_float(p.get("confidence"), 0.0)), reverse=True)
    for i, obs in enumerate(observer_population or []):
        if isinstance(obs, dict) and active_programs:
            p = active_programs[i % len(active_programs)]
            obs["research_program_id"] = p.get("program_id")
            obs["research_program_topic"] = p.get("topic")

    status_counts: Dict[str, int] = {}
    for p in programs.values():
        if isinstance(p, dict):
            status_counts[str(p.get("status", "UNKNOWN"))] = status_counts.get(str(p.get("status", "UNKNOWN")), 0) + 1

    leading = active_programs[0] if active_programs else {}
    report = {
        "version": PROGRAM_VERSION,
        "active": True,
        "safe": True,
        "generation": generation,
        "score_mode": score_mode,
        "updated_at": now,
        "program_count": len(programs),
        "created_programs": created,
        "updated_programs": updated,
        "active_programs": len(active_programs),
        "status_counts": status_counts,
        "leading_program": leading.get("program_id"),
        "leading_topic": leading.get("topic"),
        "leading_institution": leading.get("institution"),
        "mean_progress": round(sum(safe_float(p.get("progress"), 0.0) for p in active_programs) / max(1, len(active_programs)), 6),
        "mean_confidence": round(sum(safe_float(p.get("confidence"), 0.0) for p in active_programs) / max(1, len(active_programs)), 6),
        "phase": "PROGRAM_FOUNDATION" if len(programs) < 3 else "PROGRAM_ACCUMULATION",
        "context": context,
    }

    history.append({
        "time": now,
        "generation": generation,
        "program_count": len(programs),
        "created": created,
        "updated": updated,
        "leading_program": report.get("leading_program"),
        "mean_progress": report.get("mean_progress"),
        "mean_confidence": report.get("mean_confidence"),
    })
    history = history[-1000:]

    # Program graph: program -> discoveries and institution.
    graph = {"nodes": {}, "edges": {}}
    for pid, p in programs.items():
        if not isinstance(p, dict):
            continue
        graph["nodes"][pid] = {"type": "program", "topic": p.get("topic"), "status": p.get("status")}
        inst = str(p.get("institution") or "unknown_institute")
        graph["nodes"].setdefault(inst, {"type": "institution"})
        graph["edges"][f"{inst}->{pid}"] = {"source": inst, "target": pid, "relation": "SPONSORS"}
        for did in p.get("discoveries", [])[:200]:
            did = str(did)
            graph["nodes"].setdefault(did, {"type": "discovery"})
            graph["edges"][f"{pid}->{did}"] = {"source": pid, "target": did, "relation": "INVESTIGATES"}

    atomic_write_json(pdir / "research_programs.json", programs)
    atomic_write_json(pdir / "research_program_history.json", history)
    atomic_write_json(pdir / "research_program_graph.json", graph)
    atomic_write_json(pdir / f"generation_{generation:02d}_programs.json", report)
    atomic_write_json(pdir / "research_programs_status.json", report)
    atomic_write_json(results_dir / "research_programs_status.json", report)

    return observer_population, report


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    if not isinstance(status, dict):
        print(f"[{prefix}] {PROGRAM_VERSION} | no status")
        return
    print(
        f"[{prefix}] {PROGRAM_VERSION} | "
        f"active={status.get('active')} safe={status.get('safe')} "
        f"programs={status.get('program_count', 0)} "
        f"active_programs={status.get('active_programs', 0)} "
        f"phase={status.get('phase', '-')}"
    )
