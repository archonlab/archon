#!/usr/bin/env python3
"""
Universe Search v28.0 - Scientific Network

Folder-safe network layer above observer_institutions.py.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_network/ plus root mirror observer_network_status.json.
- Build institution relations from institution_registry / knowledge_archive / citation_network.
- Conservative first layer: observe and annotate, no hard steering of the core search.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

NETWORK_VERSION = "v28.0 Scientific Network"
NETWORK_DIR = "observer_network"
INST_DIR = "observer_institutions"
DEFAULT_INSTITUTION = "general_research_institute"

REL_COLLABORATION = "COLLABORATION"
REL_CITATION = "CITATION"
REL_COMPETITION = "COMPETITION"
REL_MENTORSHIP = "MENTORSHIP"


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


def ensure_dirs(results_dir: Path) -> Dict[str, str]:
    results_dir = Path(results_dir)
    net = results_dir / NETWORK_DIR
    net.mkdir(parents=True, exist_ok=True)
    return {"results_dir": str(results_dir), "observer_network_dir": str(net)}


def _load_institution_state(results_dir: Path) -> Dict[str, Any]:
    base = Path(results_dir) / INST_DIR
    return (
        read_json(base / "institution_state.json", None)
        or read_json(base / "institution_status.json", None)
        or read_json(Path(results_dir) / "observer_institutions_status.json", None)
        or {}
    )


def _load_registry(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / INST_DIR / "institution_registry.json", {}) or {}
    inst = data.get("institutions") if isinstance(data.get("institutions"), dict) else None
    if inst is None:
        state = _load_institution_state(results_dir)
        inst = state.get("institutions") if isinstance(state.get("institutions"), dict) else {}
    return inst or {}


def _load_archive(results_dir: Path) -> Dict[str, Any]:
    data = read_json(Path(results_dir) / INST_DIR / "knowledge_archive.json", {}) or {}
    entries = data.get("entries") if isinstance(data.get("entries"), dict) else {}
    return entries or {}


def _load_previous(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / NETWORK_DIR / "network_state.json", {}) or {}


def _node_label(inst_id: str) -> str:
    return str(inst_id).replace("_", " ").title()


def _build_nodes(registry: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not registry:
        registry = {DEFAULT_INSTITUTION: {"specialization": "GENERAL", "reputation": 0.2, "resource_share": 1.0}}
    nodes: Dict[str, Dict[str, Any]] = {}
    for inst_id, row in registry.items():
        if not isinstance(row, dict):
            row = {}
        rep = clamp(row.get("reputation", 0.2))
        res = clamp(row.get("resource_share", 0.0))
        spec = str(row.get("specialization") or "GENERAL").upper()
        nodes[str(inst_id)] = {
            "institution_id": str(inst_id),
            "label": row.get("label") or _node_label(str(inst_id)),
            "specialization": spec,
            "reputation": round(rep, 6),
            "resource_share": round(res, 6),
            "status": row.get("status") or "ACTIVE",
            "network_role": "UNCLASSIFIED",
        }
    return nodes


def _edge_key(a: str, b: str, rel: str) -> str:
    return f"{a}->{b}:{rel}"


def _add_edge(edges: Dict[str, Dict[str, Any]], source: str, target: str, relation: str, weight: float, reason: str) -> None:
    if not source or not target or source == target:
        return
    key = _edge_key(source, target, relation)
    old = edges.get(key, {})
    old_weight = safe_float(old.get("weight"), 0.0)
    edges[key] = {
        "edge_id": key,
        "source": source,
        "target": target,
        "relation": relation,
        "weight": round(clamp(max(old_weight, weight)), 6),
        "reason": reason,
        "updated_at": now_s(),
    }


def _build_edges(nodes: Dict[str, Dict[str, Any]], archive: Dict[str, Dict[str, Any]], prev: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    old_edges = prev.get("edges") if isinstance(prev.get("edges"), dict) else {}
    edges: Dict[str, Dict[str, Any]] = {k: v for k, v in old_edges.items() if isinstance(v, dict)}
    ids = list(nodes.keys())
    # Reputation gradient -> mentorship edges.
    for a in ids:
        for b in ids:
            if a == b:
                continue
            ra = safe_float(nodes[a].get("reputation"), 0.0)
            rb = safe_float(nodes[b].get("reputation"), 0.0)
            if ra - rb > 0.22:
                _add_edge(edges, a, b, REL_MENTORSHIP, min(1.0, (ra - rb) * 1.3), "reputation_gradient")
            elif abs(ra - rb) < 0.08 and nodes[a].get("specialization") == nodes[b].get("specialization"):
                _add_edge(edges, a, b, REL_COMPETITION, 0.25 + ra * 0.25, "same_specialization_close_reputation")
    # Archive discoveries -> citation/collaboration approximations.
    by_owner: Dict[str, List[Dict[str, Any]]] = {}
    topic_owner: Dict[str, str] = {}
    for did, d in archive.items():
        if not isinstance(d, dict):
            continue
        owner = str(d.get("discoverer") or DEFAULT_INSTITUTION)
        by_owner.setdefault(owner, []).append(d)
        topic = str(d.get("topic") or "general")
        imp = safe_float(d.get("importance"), 0.0)
        if topic not in topic_owner or imp > safe_float(topic_owner.get(topic + "_importance"), 0.0):
            topic_owner[topic] = owner
            topic_owner[topic + "_importance"] = str(imp)
    for owner, discoveries in by_owner.items():
        if owner not in nodes:
            continue
        for d in discoveries[:80]:
            topic = str(d.get("topic") or "general")
            leading = topic_owner.get(topic)
            if leading and leading in nodes and leading != owner:
                w = clamp(0.2 + safe_float(d.get("importance"), 0.0) * 0.6)
                _add_edge(edges, owner, leading, REL_CITATION, w, f"uses_{topic}_knowledge")
                _add_edge(edges, owner, leading, REL_COLLABORATION, w * 0.55, f"shared_{topic}_topic")
    # Sparse fallback: connect top two institutions gently.
    if not edges and len(ids) >= 2:
        sorted_ids = sorted(ids, key=lambda x: safe_float(nodes[x].get("reputation"), 0.0), reverse=True)
        _add_edge(edges, sorted_ids[0], sorted_ids[1], REL_COLLABORATION, 0.3, "sparse_network_bootstrap")
    return edges


def _network_metrics(nodes: Dict[str, Dict[str, Any]], edges: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    n = max(1, len(nodes))
    max_edges = max(1, n * (n - 1))
    density = clamp(len(edges) / max_edges)
    relation_counts: Dict[str, int] = {}
    weighted_degree: Dict[str, float] = {k: 0.0 for k in nodes}
    incoming: Dict[str, float] = {k: 0.0 for k in nodes}
    outgoing: Dict[str, float] = {k: 0.0 for k in nodes}
    for e in edges.values():
        rel = str(e.get("relation") or "UNKNOWN")
        relation_counts[rel] = relation_counts.get(rel, 0) + 1
        w = safe_float(e.get("weight"), 0.0)
        s = str(e.get("source") or "")
        t = str(e.get("target") or "")
        if s in weighted_degree:
            weighted_degree[s] += w
            outgoing[s] += w
        if t in weighted_degree:
            weighted_degree[t] += w
            incoming[t] += w
    central = max(weighted_degree.items(), key=lambda kv: kv[1])[0] if weighted_degree else None
    dominant_relation = max(relation_counts.items(), key=lambda kv: kv[1])[0] if relation_counts else "NONE"
    # Diversity by specialization.
    spec_counts: Dict[str, int] = {}
    for node in nodes.values():
        spec = str(node.get("specialization") or "GENERAL")
        spec_counts[spec] = spec_counts.get(spec, 0) + 1
    entropy = 0.0
    for c in spec_counts.values():
        p = c / max(1, sum(spec_counts.values()))
        if p > 0:
            entropy -= p * math.log(p + 1e-12, 2)
    max_entropy = math.log(max(1, len(spec_counts)), 2) if len(spec_counts) > 1 else 1.0
    diversity = clamp(entropy / max_entropy) if max_entropy else 0.0
    citation_ratio = relation_counts.get(REL_CITATION, 0) / max(1, len(edges))
    collaboration_ratio = relation_counts.get(REL_COLLABORATION, 0) / max(1, len(edges))
    competition_ratio = relation_counts.get(REL_COMPETITION, 0) / max(1, len(edges))
    health = clamp(0.30 * density + 0.25 * diversity + 0.20 * collaboration_ratio + 0.15 * citation_ratio + 0.10 * (1.0 - min(1.0, competition_ratio)))
    for iid, node in nodes.items():
        indeg = incoming.get(iid, 0.0)
        outdeg = outgoing.get(iid, 0.0)
        if iid == central:
            role = "HUB"
        elif indeg > outdeg * 1.3 and indeg > 0.25:
            role = "AUTHORITY"
        elif outdeg > indeg * 1.3 and outdeg > 0.25:
            role = "BROKER"
        else:
            role = "PARTICIPANT"
        node["network_role"] = role
        node["incoming_weight"] = round(indeg, 6)
        node["outgoing_weight"] = round(outdeg, 6)
        node["weighted_degree"] = round(weighted_degree.get(iid, 0.0), 6)
    return {
        "institution_count": len(nodes),
        "edge_count": len(edges),
        "network_density": round(density, 6),
        "network_diversity": round(diversity, 6),
        "network_health": round(health, 6),
        "central_institution": central,
        "dominant_relation": dominant_relation,
        "relation_counts": relation_counts,
    }


def _annotate_population(observer_population: Optional[Iterable[Any]], metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    pop: List[Dict[str, Any]] = []
    central = metrics.get("central_institution") or DEFAULT_INSTITUTION
    health = safe_float(metrics.get("network_health"), 0.0)
    for i, o in enumerate(observer_population or []):
        row = dict(o) if isinstance(o, dict) else {"value": o}
        row["network_context"] = {
            "central_institution": central,
            "network_health": round(health, 6),
            "network_generation_tag": "scientific_network_v28",
        }
        # Gentle annotation only. Do not overwrite core fitness.
        row["network_affinity"] = round(clamp(health * 0.5 + (0.1 if i % 3 == 0 else 0.0)), 6)
        pop.append(row)
    return pop


def initialize_network(results_dir: Path, observer_population: Optional[Iterable[Any]] = None, script: str = "") -> Dict[str, Any]:
    results_dir = Path(results_dir)
    dirs = ensure_dirs(results_dir)
    registry = _load_registry(results_dir)
    archive = _load_archive(results_dir)
    prev = _load_previous(results_dir)
    nodes = _build_nodes(registry)
    edges = _build_edges(nodes, archive, prev)
    metrics = _network_metrics(nodes, edges)
    state = {
        "version": NETWORK_VERSION,
        "created_at": prev.get("created_at") if isinstance(prev, dict) and prev.get("created_at") else now_s(),
        "updated_at": now_s(),
        "script": script,
        "active": True,
        "safe": True,
        "phase": "NETWORK_FOUNDATION",
        "nodes": nodes,
        "edges": edges,
        **metrics,
        "observer_count": len(list(observer_population or [])),
        "dirs": dirs,
    }
    net_dir = results_dir / NETWORK_DIR
    atomic_write_json(net_dir / "network_state.json", state)
    atomic_write_json(net_dir / "institution_network.json", {"version": NETWORK_VERSION, "nodes": nodes, "edges": edges, **metrics})
    atomic_write_json(net_dir / "network_status.json", state)
    atomic_write_json(results_dir / "observer_network_status.json", state)
    return state


def apply_network_layer(results_dir: Path, generation: int, score_mode: str, observer_population: Optional[Iterable[Any]], clean_results: Optional[List[Any]], context: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    results_dir = Path(results_dir)
    registry = _load_registry(results_dir)
    archive = _load_archive(results_dir)
    prev = _load_previous(results_dir)
    nodes = _build_nodes(registry)
    edges = _build_edges(nodes, archive, prev)
    metrics = _network_metrics(nodes, edges)
    new_pop = _annotate_population(observer_population, metrics)
    state = {
        "version": NETWORK_VERSION,
        "created_at": prev.get("created_at") if isinstance(prev, dict) and prev.get("created_at") else now_s(),
        "updated_at": now_s(),
        "generation": generation,
        "score_mode": score_mode,
        "active": True,
        "safe": True,
        "phase": "SCIENTIFIC_NETWORK",
        "context": context or {},
        "nodes": nodes,
        "edges": edges,
        "observer_count": len(new_pop),
        "result_count": len(clean_results or []),
        **metrics,
    }
    net_dir = results_dir / NETWORK_DIR
    net_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(net_dir / "network_state.json", state)
    atomic_write_json(net_dir / "institution_network.json", {"version": NETWORK_VERSION, "updated_at": now_s(), "nodes": nodes, "edges": edges, **metrics})
    atomic_write_json(net_dir / "network_status.json", state)
    atomic_write_json(net_dir / f"generation_{generation:02d}_network.json", state)
    atomic_write_json(net_dir / "citation_network_v28.json", {"version": NETWORK_VERSION, "edges": {k: v for k, v in edges.items() if v.get("relation") == REL_CITATION}})
    atomic_write_json(results_dir / "observer_network_status.json", state)
    return new_pop, state


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    if not isinstance(status, dict):
        print(f"[{prefix}] unavailable")
        return
    print(
        f"[{prefix}] {NETWORK_VERSION} | "
        f"active={status.get('active')} safe={status.get('safe')} "
        f"institutions={status.get('institution_count',0)} edges={status.get('edge_count',0)} "
        f"density={safe_float(status.get('network_density'),0):.3f} "
        f"health={safe_float(status.get('network_health'),0):.3f} "
        f"central={status.get('central_institution') or '-'} relation={status.get('dominant_relation') or '-'}"
    )


if __name__ == "__main__":
    import sys
    rd = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("universe_search_v23_results")
    st = initialize_network(rd, [])
    print_status("ObserverNetwork", st)
