#!/usr/bin/env python3
"""
Universe Search v28.2 - Discovery Engine

Folder-safe idea/discovery layer above observer_network + network_dynamics.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_discoveries/ plus root mirror discovery_status.json.
- Turn high-value search results into persistent discovery objects with author, topic, confidence,
  lineage hints, replication counters and influence graph.
- Conservative first layer: records knowledge objects and annotations, no hard steering of core search.
"""
from __future__ import annotations

import json
import math
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

DISCOVERY_VERSION = "v28.3 Discovery Engine + Independent Replication"
DISCOVERY_DIR = "observer_discoveries"


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


def _disc_dir(results_dir: Path) -> Path:
    p = Path(results_dir) / DISCOVERY_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hash_obj(x: Any) -> str:
    try:
        raw = json.dumps(x, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:
        raw = repr(x)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:12]


def _rule_payload(rule: Any) -> Dict[str, Any]:
    if isinstance(rule, dict):
        return rule
    out: Dict[str, Any] = {}
    for k in ("rule_id", "birth_gen", "genome", "parents", "family", "name"):
        try:
            if hasattr(rule, k):
                out[k] = getattr(rule, k)
        except Exception:
            pass
    if not out:
        out = {"repr": repr(rule)[:300]}
    return out


def _load_archive(results_dir: Path) -> Dict[str, Any]:
    data = read_json(_disc_dir(results_dir) / "discoveries.json", {})
    return data if isinstance(data, dict) else {}


def _load_history(results_dir: Path) -> List[Dict[str, Any]]:
    data = read_json(_disc_dir(results_dir) / "discovery_history.json", [])
    return data if isinstance(data, list) else []


def _load_network(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / "observer_network" / "network_state.json", {}) or {}


def _load_institutions(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / "observer_institutions" / "institution_registry.json", {}) or {}


def _choose_author(results_dir: Path, metrics: Dict[str, Any]) -> str:
    network = _load_network(results_dir)
    central = network.get("central_institution")
    if central:
        return str(central)
    inst = _load_institutions(results_dir)
    for key in ("leading_institution", "lead_institution", "dominant_institution"):
        if isinstance(inst, dict) and inst.get(key):
            return str(inst.get(key))
    arch = metrics.get("observer_archetype") or metrics.get("species_id") or metrics.get("observer_species")
    if arch:
        return str(arch).replace("_observer", "") + "_institute"
    return "general_research_institute"




def _first_measurement(metrics: Dict[str, Any], *keys: str) -> Any:
    """Return the first present measurement without treating numeric zero as missing."""
    for key in keys:
        value = metrics.get(key)
        if value not in (None, ""):
            return value
    return None

def _infer_topic(metrics: Dict[str, Any]) -> str:
    candidates = [
        ("civilization", _first_measurement(metrics, "civilization_score", "emergence_score")),
        ("knowledge", _first_measurement(metrics, "knowledge_score", "information_score")),
        ("memory", _first_measurement(metrics, "memory_score", "field_memory", "stable_memory")),
        ("organism", _first_measurement(metrics, "organism_score", "organism_bonus")),
        ("crystal", _first_measurement(metrics, "quasi_particle_score", "crystal_defect_score")),
        ("stability", _first_measurement(metrics, "stability", "stochastic_stability")),
        ("novelty", _first_measurement(metrics, "novelty_behavior", "in_generation_diversity")),
    ]
    best = max(candidates, key=lambda kv: safe_float(kv[1], 0.0))
    return best[0] if safe_float(best[1], 0.0) > 0 else "general_pattern"


def _confidence(score: float, metrics: Dict[str, Any]) -> float:
    # Conservative: normalize score gently and mix in robust known probes when available.
    score_part = clamp(score / 180.0)
    novelty = clamp(metrics.get("novelty_behavior", 0.0))
    diversity = clamp(metrics.get("in_generation_diversity", 0.0))
    info = clamp(metrics.get("information_score", metrics.get("knowledge_score", 0.0)))
    org = clamp(metrics.get("organism_score", 0.0))
    crystal = clamp(metrics.get("quasi_particle_score", 0.0))
    return round(clamp(0.45 * score_part + 0.18 * novelty + 0.12 * diversity + 0.13 * info + 0.08 * org + 0.04 * crystal), 6)


def _importance(conf: float, metrics: Dict[str, Any]) -> float:
    novelty = clamp(metrics.get("novelty_behavior", 0.0))
    diversity = clamp(metrics.get("in_generation_diversity", 0.0))
    persistence = clamp(metrics.get("organism_survival", metrics.get("survival", 0.0)))
    return round(clamp(0.50 * conf + 0.25 * novelty + 0.15 * diversity + 0.10 * persistence), 6)


def _status_for(d: Dict[str, Any]) -> str:
    """Scientific status is based on independent rules, not repeated sightings."""
    independent_rules = safe_int(d.get("independent_rule_count"), 0)
    independent_seeds = safe_int(d.get("independent_seed_count"), 0)
    independent_runs = safe_int(d.get("independent_run_count"), 0)
    conf = safe_float(d.get("confidence"), 0.0)
    imp = safe_float(d.get("importance"), 0.0)

    if independent_rules >= 12 and independent_seeds >= 8 and conf > 0.80 and imp > 0.72:
        return "FOUNDATIONAL"
    if independent_rules >= 5 and independent_seeds >= 3 and conf > 0.68:
        return "SUPPORTED"
    if independent_rules >= 2:
        return "REPLICATED"
    if conf < 0.18:
        return "WEAK"
    return "NEW"


def _canonical_discovery_id(topic: str) -> str:
    """One persistent discovery object per scientific topic/claim family."""
    sig = _hash_obj({"topic": topic, "claim_family": topic})
    return f"DISC-{topic.upper()}-{sig}"


def _append_unique(values: List[Any], value: Any) -> None:
    marker = str(value)
    if marker and marker not in {str(x) for x in values}:
        values.append(value)


def _refresh_independence_counts(d: Dict[str, Any]) -> None:
    d["independent_rule_count"] = len(d.get("seen_rule_signatures", []) or [])
    d["independent_seed_count"] = len(d.get("seen_seeds", []) or [])
    d["independent_run_count"] = len(d.get("seen_runs", []) or [])
    d["replications"] = max(0, d["independent_rule_count"] - 1)


def initialize_discovery(results_dir: Path, script: str = "") -> Dict[str, Any]:
    results_dir = Path(results_dir)
    ddir = _disc_dir(results_dir)
    archive = _load_archive(results_dir)
    graph = read_json(ddir / "discovery_graph.json", {"nodes": {}, "edges": {}}) or {"nodes": {}, "edges": {}}
    status = {
        "version": DISCOVERY_VERSION,
        "active": True,
        "safe": True,
        "script": script,
        "created_at": now_s(),
        "discovery_count": len(archive),
        "graph_nodes": len(graph.get("nodes", {})) if isinstance(graph.get("nodes"), dict) else 0,
        "graph_edges": len(graph.get("edges", {})) if isinstance(graph.get("edges"), dict) else 0,
        "phase": "DISCOVERY_FOUNDATION" if len(archive) < 3 else "DISCOVERY_ACCUMULATION",
    }
    atomic_write_json(ddir / "discovery_status.json", status)
    atomic_write_json(results_dir / "discovery_status.json", status)
    return status


def apply_discovery_layer(results_dir: Path, generation: int, score_mode: str, observer_population: List[Dict[str, Any]], clean_results: List[Any], context: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    results_dir = Path(results_dir)
    ddir = _disc_dir(results_dir)
    context = context or {}
    archive = _load_archive(results_dir)
    history = _load_history(results_dir)
    created_at = now_s()
    run_id = str(
        context.get("search_run_id")
        or context.get("run_id")
        or context.get("session_id")
        or "unknown_run"
    )

    new_discoveries: List[Dict[str, Any]] = []
    top = list(clean_results or [])[: max(1, min(6, len(clean_results or [])))]

    for rank, item in enumerate(top, start=1):
        try:
            score, rule, metrics = item
        except Exception:
            continue

        metrics = metrics if isinstance(metrics, dict) else {}
        rule_data = _rule_payload(rule)
        rid = rule_data.get("rule_id") or metrics.get("rule_id") or rank
        topic = _infer_topic(metrics)
        did = _canonical_discovery_id(topic)
        rule_sig = _hash_obj(rule_data)
        seed = rule_data.get("seed")
        conf = _confidence(safe_float(score, 0.0), metrics)
        imp = _importance(conf, metrics)
        author = _choose_author(results_dir, metrics)

        existing = archive.get(did)
        if not isinstance(existing, dict):
            existing = {
                "id": did,
                "title": f"{topic.replace('_', ' ').title()} discovery",
                "topic": topic,
                "author": author,
                "generation": generation,
                "created_at": created_at,
                "last_seen_generation": generation,
                "last_seen_at": created_at,
                "score": round(safe_float(score, 0.0), 6),
                "confidence": conf,
                "importance": imp,
                "novelty": round(clamp(metrics.get("novelty_behavior", 0.0)), 6),
                "sightings": 0,
                "replications": 0,
                "citations": 0,
                "extensions": [],
                "seen_rules": [],
                "seen_rule_signatures": [],
                "seen_seeds": [],
                "seen_runs": [],
                "status": "NEW" if conf >= 0.18 else "WEAK",
                "metrics_hint": {
                    "observer_id": metrics.get("observer_id"),
                    "observer_archetype": metrics.get("observer_archetype"),
                    "organism_score": metrics.get("organism_score"),
                    "information_score": metrics.get("information_score"),
                    "quasi_particle_score": metrics.get("quasi_particle_score"),
                },
            }
            archive[did] = existing
            new_discoveries.append(existing)
            event_type = "NEW_DISCOVERY"
        else:
            event_type = "SIGHTING"

        before_rules = len(existing.get("seen_rule_signatures", []) or [])
        existing["last_seen_generation"] = generation
        existing["last_seen_at"] = created_at
        existing["sightings"] = safe_int(existing.get("sightings"), 0) + 1
        existing["score"] = round(max(safe_float(existing.get("score"), 0.0), safe_float(score, 0.0)), 6)
        existing["confidence"] = round(max(safe_float(existing.get("confidence"), 0.0), conf), 6)
        existing["importance"] = round(max(safe_float(existing.get("importance"), 0.0), imp), 6)
        existing["novelty"] = round(max(safe_float(existing.get("novelty"), 0.0), clamp(metrics.get("novelty_behavior", 0.0))), 6)

        existing.setdefault("seen_rules", [])
        existing.setdefault("seen_rule_signatures", [])
        existing.setdefault("seen_seeds", [])
        existing.setdefault("seen_runs", [])
        _append_unique(existing["seen_rules"], rid)
        _append_unique(existing["seen_rule_signatures"], rule_sig)
        if seed is not None:
            _append_unique(existing["seen_seeds"], seed)
        _append_unique(existing["seen_runs"], run_id)
        _refresh_independence_counts(existing)

        if len(existing["seen_rule_signatures"]) > before_rules:
            event_type = "INDEPENDENT_REPLICATION" if before_rules else event_type

        existing["status"] = _status_for(existing)

        history.append({
            "event_id": f"disc_evt_{generation}_{rank}_{did}"[:140],
            "type": event_type,
            "generation": generation,
            "created_at": created_at,
            "discovery_id": did,
            "topic": topic,
            "author": author,
            "rule_id": rid,
            "rule_signature": rule_sig,
            "seed": seed,
            "run_id": run_id,
            "confidence": conf,
            "importance": imp,
            "sightings": existing["sightings"],
            "independent_rules": existing["independent_rule_count"],
        })

    # Build simple idea graph: author -> discovery, plus topic links between discoveries.
    nodes: Dict[str, Any] = {}
    edges: Dict[str, Any] = {}
    by_topic: Dict[str, List[str]] = {}
    for did, d in archive.items():
        nodes[did] = {
            "id": did,
            "kind": "DISCOVERY",
            "topic": d.get("topic"),
            "status": d.get("status"),
            "confidence": d.get("confidence", 0.0),
            "importance": d.get("importance", 0.0),
        }
        author = d.get("author") or "unknown_institute"
        aid = f"INST-{author}"
        nodes.setdefault(aid, {"id": aid, "kind": "INSTITUTION", "name": author})
        edges[f"{aid}->{did}"] = {"source": aid, "target": did, "relation": "DISCOVERED", "weight": d.get("importance", 0.0)}
        by_topic.setdefault(str(d.get("topic") or "unknown"), []).append(did)
    for topic, ids in by_topic.items():
        ids_sorted = sorted(ids, key=lambda x: safe_float(archive.get(x, {}).get("generation"), 0.0))
        for a, b in zip(ids_sorted, ids_sorted[1:]):
            edges[f"{a}->{b}"] = {"source": a, "target": b, "relation": "TOPIC_LINEAGE", "topic": topic, "weight": 0.35}

    graph = {
        "version": DISCOVERY_VERSION,
        "updated_at": created_at,
        "nodes": nodes,
        "edges": edges,
        "topic_count": len(by_topic),
    }

    active = [d for d in archive.values() if d.get("status") not in ("ARCHIVED", "FAILED")]
    top_disc = sorted(active, key=lambda d: (safe_float(d.get("importance"), 0.0), safe_float(d.get("confidence"), 0.0)), reverse=True)[:8]
    status_counts: Dict[str, int] = {}
    for d in archive.values():
        status_counts[str(d.get("status") or "UNKNOWN")] = status_counts.get(str(d.get("status") or "UNKNOWN"), 0) + 1

    report = {
        "version": DISCOVERY_VERSION,
        "active": True,
        "safe": True,
        "generation": generation,
        "score_mode": score_mode,
        "created_at": created_at,
        "new_discoveries": len(new_discoveries),
        "discovery_count": len(archive),
        "history_events": len(history),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "status_counts": status_counts,
        "leading_discovery": top_disc[0].get("id") if top_disc else None,
        "leading_topic": top_disc[0].get("topic") if top_disc else None,
        "mean_confidence": round(sum(safe_float(d.get("confidence"), 0.0) for d in active) / max(1, len(active)), 6),
        "mean_importance": round(sum(safe_float(d.get("importance"), 0.0) for d in active) / max(1, len(active)), 6),
        "context": context,
    }

    atomic_write_json(ddir / "discoveries.json", archive)
    atomic_write_json(ddir / "discovery_history.json", history[-2000:])
    atomic_write_json(ddir / "discovery_graph.json", graph)
    atomic_write_json(ddir / "discovery_status.json", report)
    atomic_write_json(ddir / f"generation_{generation:02d}_discoveries.json", {"report": report, "new": new_discoveries, "top": top_disc})
    atomic_write_json(results_dir / "discovery_status.json", report)
    return observer_population, report


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    if not isinstance(status, dict):
        print(f"[{prefix}] no status")
        return
    if "new_discoveries" in status:
        print(
            f"[{prefix}] {DISCOVERY_VERSION} | "
            f"active={status.get('active')} safe={status.get('safe')} "
            f"new={status.get('new_discoveries',0)} total={status.get('discovery_count',0)} "
            f"mean_conf={safe_float(status.get('mean_confidence'),0):.3f} "
            f"lead={status.get('leading_discovery') or '-'} topic={status.get('leading_topic') or '-'}"
        )
    else:
        print(
            f"[{prefix}] {DISCOVERY_VERSION} | "
            f"active={status.get('active')} safe={status.get('safe')} "
            f"discoveries={status.get('discovery_count',0)} graph={status.get('graph_nodes',0)}/{status.get('graph_edges',0)} "
            f"phase={status.get('phase','-')}"
        )
