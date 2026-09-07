#!/usr/bin/env python3
"""
Universe Search v28.1 - Scientific Dynamics

Folder-safe dynamic layer above observer_network.py.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_network/ plus root mirror network_dynamics_status.json.
- Add a living history for institution relationships: splits, merges, retirements, challenges, collaborations.
- Conservative first layer: records events and gentle annotations, no hard steering of the core search.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DYNAMICS_VERSION = "v28.1 Scientific Dynamics"
NETWORK_DIR = "observer_network"
EVENT_TYPES = ("SPLIT", "MERGE", "RETIRE", "COLLABORATION", "COMPETITION", "MENTORSHIP", "PARADIGM_PRESSURE", "STABILIZATION")


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


def _network_dir(results_dir: Path) -> Path:
    p = Path(results_dir) / NETWORK_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_network(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / NETWORK_DIR / "network_state.json", {}) or {}


def _load_prev_dynamics(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / NETWORK_DIR / "network_dynamics_state.json", {}) or {}


def _load_events(results_dir: Path) -> List[Dict[str, Any]]:
    data = read_json(Path(results_dir) / NETWORK_DIR / "institution_events.json", [])
    return data if isinstance(data, list) else []


def _node_name(node_id: str) -> str:
    return str(node_id).replace("_", " ").title()


def _event_id(event_type: str, generation: int, subject: str, suffix: str = "") -> str:
    raw = f"{generation}:{event_type}:{subject}:{suffix}".lower().replace(" ", "_")
    return "evt_" + "".join(ch for ch in raw if ch.isalnum() or ch in "_:-")[:120]


def _append_unique(events: List[Dict[str, Any]], event: Dict[str, Any]) -> None:
    eid = event.get("event_id")
    if not eid:
        events.append(event)
        return
    if not any(e.get("event_id") == eid for e in events):
        events.append(event)


def _relation_counts(edges: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for e in edges.values():
        rel = str(e.get("relation") or "UNKNOWN")
        out[rel] = out.get(rel, 0) + 1
    return out


def _institution_scores(nodes: Dict[str, Dict[str, Any]], edges: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    scores: Dict[str, Dict[str, float]] = {}
    for iid, node in nodes.items():
        scores[iid] = {
            "reputation": clamp(node.get("reputation", 0.0)),
            "resource_share": clamp(node.get("resource_share", 0.0)),
            "incoming": safe_float(node.get("incoming_weight"), 0.0),
            "outgoing": safe_float(node.get("outgoing_weight"), 0.0),
            "degree": safe_float(node.get("weighted_degree"), 0.0),
        }
    # fall back from edge list if observer_network did not annotate nodes yet
    for e in edges.values():
        s = str(e.get("source") or "")
        t = str(e.get("target") or "")
        w = safe_float(e.get("weight"), 0.0)
        if s in scores:
            scores[s]["outgoing"] += w
            scores[s]["degree"] += w
        if t in scores:
            scores[t]["incoming"] += w
            scores[t]["degree"] += w
    return scores


def _make_events(network: Dict[str, Any], generation: int, prev: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = network.get("nodes") if isinstance(network.get("nodes"), dict) else {}
    edges = network.get("edges") if isinstance(network.get("edges"), dict) else {}
    metrics = {
        "density": clamp(network.get("network_density", 0.0)),
        "health": clamp(network.get("network_health", 0.0)),
        "diversity": clamp(network.get("network_diversity", 0.0)),
        "institution_count": safe_int(network.get("institution_count"), len(nodes)),
        "edge_count": safe_int(network.get("edge_count"), len(edges)),
        "central": network.get("central_institution"),
        "dominant_relation": network.get("dominant_relation") or "NONE",
    }
    scores = _institution_scores(nodes, edges)
    events: List[Dict[str, Any]] = []
    created_at = now_s()

    central = metrics["central"]
    if central:
        central_degree = scores.get(str(central), {}).get("degree", 0.0)
        total_degree = sum(v.get("degree", 0.0) for v in scores.values()) or 1.0
        dominance = clamp(central_degree / total_degree)
        if dominance > 0.62 and metrics["institution_count"] >= 2:
            events.append({
                "event_id": _event_id("PARADIGM_PRESSURE", generation, str(central)),
                "type": "PARADIGM_PRESSURE",
                "generation": generation,
                "created_at": created_at,
                "institution": central,
                "severity": round(dominance, 6),
                "reason": "central_institution_dominance",
                "interpretation": f"{_node_name(str(central))} is becoming a dominant scientific hub.",
            })
        elif dominance > 0.38:
            events.append({
                "event_id": _event_id("STABILIZATION", generation, str(central)),
                "type": "STABILIZATION",
                "generation": generation,
                "created_at": created_at,
                "institution": central,
                "severity": round(dominance, 6),
                "reason": "healthy_central_hub",
                "interpretation": f"{_node_name(str(central))} stabilizes the current scientific network.",
            })

    # Split candidates: high reputation, high outgoing influence, enough network health to support branching.
    for iid, score in scores.items():
        rep = score.get("reputation", 0.0)
        out = score.get("outgoing", 0.0)
        deg = score.get("degree", 0.0)
        if rep > 0.56 and out > 0.55 and metrics["health"] > 0.45:
            child = f"{iid}_branch_{generation:02d}"
            events.append({
                "event_id": _event_id("SPLIT", generation, iid, child),
                "type": "SPLIT",
                "generation": generation,
                "created_at": created_at,
                "parent": iid,
                "child_candidate": child,
                "strength": round(clamp(0.45 * rep + 0.35 * out + 0.20 * metrics["health"]), 6),
                "reason": "high_reputation_high_outgoing_influence",
                "interpretation": f"{_node_name(iid)} has enough influence to seed a daughter laboratory.",
            })
        # Retirement candidates: weak and disconnected.
        if rep < 0.18 and deg < 0.10 and metrics["institution_count"] > 2:
            events.append({
                "event_id": _event_id("RETIRE", generation, iid),
                "type": "RETIRE",
                "generation": generation,
                "created_at": created_at,
                "institution": iid,
                "strength": round(clamp(1.0 - rep - deg), 6),
                "reason": "low_reputation_low_connectivity",
                "interpretation": f"{_node_name(iid)} is at risk of retirement from the active network.",
            })

    # Merge candidates: strong collaboration edge between similar-strength institutions.
    for e in edges.values():
        rel = str(e.get("relation") or "")
        if rel != "COLLABORATION":
            continue
        src = str(e.get("source") or "")
        dst = str(e.get("target") or "")
        w = safe_float(e.get("weight"), 0.0)
        if src in scores and dst in scores and w > 0.48:
            rep_gap = abs(scores[src].get("reputation", 0.0) - scores[dst].get("reputation", 0.0))
            if rep_gap < 0.18:
                result = f"{src}_{dst}_consortium"
                events.append({
                    "event_id": _event_id("MERGE", generation, src, dst),
                    "type": "MERGE",
                    "generation": generation,
                    "created_at": created_at,
                    "institutions": [src, dst],
                    "result_candidate": result,
                    "strength": round(clamp(w * (1.0 - rep_gap)), 6),
                    "reason": "strong_collaboration_close_reputation",
                    "interpretation": f"{_node_name(src)} and {_node_name(dst)} could form a joint research consortium.",
                })

    # Relation-level headline event.
    rel_counts = _relation_counts(edges)
    if rel_counts:
        dom_rel = max(rel_counts.items(), key=lambda kv: kv[1])[0]
        events.append({
            "event_id": _event_id(dom_rel, generation, str(dom_rel)),
            "type": dom_rel if dom_rel in EVENT_TYPES else "COLLABORATION",
            "generation": generation,
            "created_at": created_at,
            "relation": dom_rel,
            "count": rel_counts.get(dom_rel, 0),
            "reason": "dominant_network_relation",
            "interpretation": f"The network is currently shaped mostly by {dom_rel.lower()} links.",
        })

    # If network is tiny, create a bootstrap collaboration event so the chronicle is not empty.
    if not events and metrics["institution_count"] >= 1:
        events.append({
            "event_id": _event_id("COLLABORATION", generation, str(central or "network"), "bootstrap"),
            "type": "COLLABORATION",
            "generation": generation,
            "created_at": created_at,
            "institution": central or next(iter(nodes.keys()), "unknown_institution"),
            "strength": round(metrics["health"], 6),
            "reason": "network_bootstrap",
            "interpretation": "The scientific network enters a stable observation phase.",
        })
    return events


def _lineage_from_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    lineage: Dict[str, Any] = {"version": DYNAMICS_VERSION, "nodes": {}, "edges": []}
    for e in events:
        typ = e.get("type")
        if typ == "SPLIT":
            parent = str(e.get("parent") or "")
            child = str(e.get("child_candidate") or "")
            if parent and child:
                lineage["nodes"].setdefault(parent, {"institution_id": parent, "status": "ACTIVE"})
                lineage["nodes"][child] = {"institution_id": child, "status": "CANDIDATE", "parent": parent, "created_by_event": e.get("event_id")}
                lineage["edges"].append({"source": parent, "target": child, "relation": "SPLIT_CANDIDATE", "event_id": e.get("event_id")})
        elif typ == "MERGE":
            result = str(e.get("result_candidate") or "")
            inst = e.get("institutions") if isinstance(e.get("institutions"), list) else []
            if result and inst:
                lineage["nodes"][result] = {"institution_id": result, "status": "CONSORTIUM_CANDIDATE", "parents": inst, "created_by_event": e.get("event_id")}
                for p in inst:
                    lineage["nodes"].setdefault(str(p), {"institution_id": str(p), "status": "ACTIVE"})
                    lineage["edges"].append({"source": str(p), "target": result, "relation": "MERGE_CANDIDATE", "event_id": e.get("event_id")})
        elif typ == "RETIRE":
            iid = str(e.get("institution") or "")
            if iid:
                lineage["nodes"].setdefault(iid, {"institution_id": iid})
                lineage["nodes"][iid]["status"] = "RETIREMENT_RISK"
                lineage["nodes"][iid]["retirement_event"] = e.get("event_id")
    return lineage


def _metrics_from_events(network: Dict[str, Any], events: List[Dict[str, Any]], all_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for e in events:
        typ = str(e.get("type") or "UNKNOWN")
        counts[typ] = counts.get(typ, 0) + 1
    all_counts: Dict[str, int] = {}
    for e in all_events:
        typ = str(e.get("type") or "UNKNOWN")
        all_counts[typ] = all_counts.get(typ, 0) + 1
    splits = counts.get("SPLIT", 0)
    merges = counts.get("MERGE", 0)
    retires = counts.get("RETIRE", 0)
    paradigm = counts.get("PARADIGM_PRESSURE", 0)
    health = clamp(network.get("network_health", 0.0))
    dynamism = clamp((splits * 0.22 + merges * 0.18 + paradigm * 0.12 + len(events) * 0.05) / max(1.0, safe_int(network.get("institution_count"), 1)))
    volatility = clamp(retires * 0.22 + paradigm * 0.10 + (1.0 - health) * 0.35)
    if paradigm:
        phase = "PARADIGM_TENSION"
    elif splits:
        phase = "BRANCHING_SCIENCE"
    elif merges:
        phase = "CONSORTIUM_FORMATION"
    elif retires:
        phase = "INSTITUTIONAL_PRUNING"
    elif health > 0.65:
        phase = "STABLE_SCIENTIFIC_NETWORK"
    else:
        phase = "EARLY_NETWORK_DYNAMICS"
    return {
        "event_count": len(events),
        "total_event_count": len(all_events),
        "event_type_counts": counts,
        "all_event_type_counts": all_counts,
        "network_dynamism": round(dynamism, 6),
        "network_volatility": round(volatility, 6),
        "dynamic_phase": phase,
    }


def initialize_dynamics(results_dir: Path, script: str = "") -> Dict[str, Any]:
    results_dir = Path(results_dir)
    net = _network_dir(results_dir)
    network = _load_network(results_dir)
    prev = _load_prev_dynamics(results_dir)
    events = _load_events(results_dir)
    state = {
        "version": DYNAMICS_VERSION,
        "created_at": prev.get("created_at") if isinstance(prev, dict) and prev.get("created_at") else now_s(),
        "updated_at": now_s(),
        "script": script,
        "active": True,
        "safe": True,
        "phase": "DYNAMICS_FOUNDATION",
        "network_health": clamp(network.get("network_health", 0.0)),
        "institution_count": safe_int(network.get("institution_count"), 0),
        "edge_count": safe_int(network.get("edge_count"), 0),
        "known_events": len(events),
        "dynamic_phase": prev.get("dynamic_phase") or "EARLY_NETWORK_DYNAMICS",
    }
    atomic_write_json(net / "network_dynamics_state.json", state)
    atomic_write_json(net / "network_dynamics_status.json", state)
    atomic_write_json(results_dir / "network_dynamics_status.json", state)
    return state


def apply_network_dynamics(results_dir: Path, generation: int, score_mode: str, observer_population: Optional[Iterable[Any]], clean_results: Optional[List[Any]], context: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    results_dir = Path(results_dir)
    net = _network_dir(results_dir)
    network = _load_network(results_dir)
    prev = _load_prev_dynamics(results_dir)
    old_events = _load_events(results_dir)
    new_events = _make_events(network, generation, prev)
    all_events = list(old_events)
    for e in new_events:
        _append_unique(all_events, e)
    lineage = _lineage_from_events(all_events)
    metrics = _metrics_from_events(network, new_events, all_events)
    pop: List[Dict[str, Any]] = []
    phase = metrics.get("dynamic_phase")
    volatility = safe_float(metrics.get("network_volatility"), 0.0)
    dynamism = safe_float(metrics.get("network_dynamism"), 0.0)
    for i, o in enumerate(observer_population or []):
        row = dict(o) if isinstance(o, dict) else {"value": o}
        row["network_dynamics_context"] = {
            "phase": phase,
            "dynamism": round(dynamism, 6),
            "volatility": round(volatility, 6),
            "event_count": metrics.get("event_count", 0),
        }
        # Gentle annotation only. Do not overwrite core fitness.
        row["network_dynamics_affinity"] = round(clamp(dynamism * 0.55 + (0.05 if i % 5 == 0 else 0.0)), 6)
        pop.append(row)
    state = {
        "version": DYNAMICS_VERSION,
        "created_at": prev.get("created_at") if isinstance(prev, dict) and prev.get("created_at") else now_s(),
        "updated_at": now_s(),
        "generation": generation,
        "score_mode": score_mode,
        "active": True,
        "safe": True,
        "phase": "SCIENTIFIC_DYNAMICS",
        "context": context or {},
        "network_summary": {
            "institution_count": safe_int(network.get("institution_count"), 0),
            "edge_count": safe_int(network.get("edge_count"), 0),
            "network_health": clamp(network.get("network_health", 0.0)),
            "central_institution": network.get("central_institution"),
            "dominant_relation": network.get("dominant_relation"),
        },
        "events": new_events,
        **metrics,
        "observer_count": len(pop),
        "result_count": len(clean_results or []),
    }
    atomic_write_json(net / "network_dynamics_state.json", state)
    atomic_write_json(net / "network_dynamics_status.json", state)
    atomic_write_json(net / "institution_events.json", all_events[-5000:])
    atomic_write_json(net / "network_history.json", {"version": DYNAMICS_VERSION, "events": all_events[-5000:], "summary": metrics})
    atomic_write_json(net / "institution_lineage.json", lineage)
    atomic_write_json(net / f"generation_{generation:02d}_network_dynamics.json", state)
    atomic_write_json(results_dir / "network_dynamics_status.json", state)
    return pop, state


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    if not isinstance(status, dict):
        print(f"[{prefix}] unavailable")
        return
    print(
        f"[{prefix}] {DYNAMICS_VERSION} | "
        f"active={status.get('active')} safe={status.get('safe')} "
        f"phase={status.get('dynamic_phase') or status.get('phase')} "
        f"events={status.get('event_count', status.get('known_events', 0))} "
        f"total={status.get('total_event_count', status.get('known_events', 0))} "
        f"dynamism={safe_float(status.get('network_dynamism'), 0):.3f} "
        f"volatility={safe_float(status.get('network_volatility'), 0):.3f}"
    )


if __name__ == "__main__":
    import sys
    rd = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("universe_search_v23_results")
    st = initialize_dynamics(rd, script="network_dynamics.py")
    print_status("NetworkDynamics", st)
