#!/usr/bin/env python3
"""
Universe Search v27.0 - Emergent Knowledge Institutions

Folder-safe institution layer above observer_civilization.py.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_institutions/ plus a small
  root mirror observer_institutions_status.json.
- Institutions are derived from schools/species/civilization signals, not hard gates.
- If inputs are sparse, fall back conservatively and keep the old search alive.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

INSTITUTION_VERSION = "v27.0 Emergent Knowledge Institutions"
INST_DIR = "observer_institutions"
CIV_DIR = "observer_civilization"
ECOLOGY_DIR = "observer_ecology"
DEFAULT_INSTITUTION = "general_research_institute"


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
    inst = results_dir / INST_DIR
    inst.mkdir(parents=True, exist_ok=True)
    return {"results_dir": str(results_dir), "observer_institutions_dir": str(inst)}


def _load_civilization(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / CIV_DIR / "civilization_state.json", {}) or read_json(Path(results_dir) / "observer_civilization_status.json", {}) or {}


def _load_previous_state(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / INST_DIR / "institution_state.json", {}) or {}


def _institution_from_school(school_id: str) -> Tuple[str, str]:
    s = (school_id or "").lower()
    if "memory" in s:
        return "memory_institute", "MEMORY"
    if "temporal" in s or "oscillation" in s:
        return "temporal_dynamics_lab", "TEMPORAL"
    if "structure" in s:
        return "structure_mapping_lab", "STRUCTURE"
    if "information" in s:
        return "information_sciences_institute", "INFORMATION"
    if "organization" in s or "civil" in s or "complex" in s:
        return "complexity_academy", "COMPLEXITY"
    return DEFAULT_INSTITUTION, "GENERAL"


def _institution_label(inst_id: str) -> str:
    labels = {
        "memory_institute": "Memory Institute",
        "temporal_dynamics_lab": "Temporal Dynamics Lab",
        "structure_mapping_lab": "Structure Mapping Lab",
        "information_sciences_institute": "Information Sciences Institute",
        "complexity_academy": "Complexity Academy",
        DEFAULT_INSTITUTION: "General Research Institute",
    }
    return labels.get(inst_id, inst_id.replace("_", " ").title())


def _school_rows(civ: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    schools = civ.get("schools") if isinstance(civ.get("schools"), dict) else {}
    return {str(k): v for k, v in schools.items() if isinstance(v, dict)}


def _collect_discoveries(clean_results: Optional[List[Any]], generation: Optional[int]) -> List[Dict[str, Any]]:
    discoveries: List[Dict[str, Any]] = []
    for rank, item in enumerate(clean_results or []):
        try:
            score, rule, metrics = item
        except Exception:
            continue
        if not isinstance(metrics, dict):
            continue
        score_f = safe_float(score, 0.0)
        # Conservative: only archive notable candidates.
        if score_f < 60 and safe_float(metrics.get("observer_score"), 0.0) < 30 and safe_float(metrics.get("information_score"), 0.0) < 0.35:
            continue
        rule_id = None
        try:
            rule_id = getattr(rule, "rule_id", None)
        except Exception:
            rule_id = None
        topic = "general"
        if safe_float(metrics.get("information_score"), 0.0) > 0.45 or safe_float(metrics.get("memory_score"), 0.0) > 0.35:
            topic = "memory"
        elif safe_float(metrics.get("macro_scaffold"), 0.0) > 0.5 or safe_float(metrics.get("organism_bonus"), 0.0) > 0:
            topic = "structure"
        elif safe_float(metrics.get("crystal_defect_bonus"), 0.0) > 0:
            topic = "crystal"
        elif safe_float(metrics.get("novelty_behavior"), 0.0) > 0.55:
            topic = "novelty"
        discoveries.append({
            "discovery_id": f"gen{generation or 0:02d}_rank{rank+1:03d}",
            "generation": generation,
            "rank": rank + 1,
            "rule_id": rule_id,
            "topic": topic,
            "score": round(score_f, 6),
            "observer_score": round(safe_float(metrics.get("observer_score"), 0.0), 6),
            "novelty": round(safe_float(metrics.get("novelty_behavior"), 0.0), 6),
            "confidence": round(clamp(score_f / 140.0), 6),
        })
    return discoveries[:40]


def _load_archive(results_dir: Path) -> Dict[str, Any]:
    archive = read_json(Path(results_dir) / INST_DIR / "knowledge_archive.json", {}) or {}
    if not isinstance(archive, dict):
        archive = {}
    archive.setdefault("version", INSTITUTION_VERSION)
    archive.setdefault("entries", {})
    archive.setdefault("updated_at", now_s())
    return archive


def _update_archive(results_dir: Path, discoveries: List[Dict[str, Any]], institutions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    archive = _load_archive(results_dir)
    entries = archive.setdefault("entries", {})
    # Pick likely owner by topic specialization.
    topic_to_spec = {
        "memory": "MEMORY",
        "structure": "STRUCTURE",
        "crystal": "STRUCTURE",
        "novelty": "GENERAL",
        "general": "GENERAL",
    }
    for d in discoveries:
        spec = topic_to_spec.get(d.get("topic"), "GENERAL")
        owner = DEFAULT_INSTITUTION
        best_rep = -1.0
        for iid, inst in institutions.items():
            if inst.get("specialization") == spec or owner == DEFAULT_INSTITUTION:
                rep = safe_float(inst.get("reputation"), 0.0)
                if rep > best_rep:
                    owner, best_rep = iid, rep
        key = str(d.get("discovery_id"))
        old = entries.get(key, {}) if isinstance(entries.get(key), dict) else {}
        old.update(d)
        old.setdefault("first_seen", now_s())
        old["last_seen"] = now_s()
        old["discoverer"] = owner
        old["citations"] = safe_int(old.get("citations"), 0)
        old["replications"] = safe_int(old.get("replications"), 0)
        old["importance"] = round(clamp(0.55 * safe_float(d.get("confidence"), 0.0) + 0.25 * safe_float(d.get("novelty"), 0.0) + 0.20 * (1.0 if d.get("rank") == 1 else 0.2)), 6)
        entries[key] = old
    archive["updated_at"] = now_s()
    archive["entry_count"] = len(entries)
    return archive


def _build_institutions(civ: Dict[str, Any], prev: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    schools = _school_rows(civ)
    prev_regs = prev.get("institutions") if isinstance(prev.get("institutions"), dict) else {}
    institutions: Dict[str, Dict[str, Any]] = {}
    if not schools:
        schools = {"general_school": {"fitness": 0.25, "age": 1, "status": "ACTIVE"}}
    for school_id, school in schools.items():
        inst_id, spec = _institution_from_school(school_id)
        old = prev_regs.get(inst_id, {}) if isinstance(prev_regs.get(inst_id), dict) else {}
        school_fit = safe_float(school.get("fitness"), 0.0)
        old_rep = safe_float(old.get("reputation"), 0.2)
        maturity = safe_float(civ.get("maturity"), 0.0)
        memory = safe_float(civ.get("collective_memory_score"), 0.0)
        exchange = safe_float(civ.get("knowledge_exchange_score"), 0.0)
        reputation = clamp(0.55 * old_rep + 0.25 * school_fit + 0.10 * maturity + 0.05 * memory + 0.05 * exchange)
        innovation = clamp(0.45 * school_fit + 0.35 * maturity + 0.20 * exchange)
        credibility = clamp(0.50 * reputation + 0.25 * memory + 0.25 * maturity)
        institutions[inst_id] = {
            "institution_id": inst_id,
            "label": _institution_label(inst_id),
            "specialization": spec,
            "source_schools": sorted(set((old.get("source_schools") if isinstance(old.get("source_schools"), list) else []) + [school_id])),
            "status": "ACTIVE",
            "age": safe_int(old.get("age"), 0) + 1,
            "reputation": round(reputation, 6),
            "innovation": round(innovation, 6),
            "credibility": round(credibility, 6),
            "replication_score": round(clamp(0.40 * credibility + 0.30 * memory + 0.30 * exchange), 6),
            "resource_share": 0.0,
        }
    # Normalize resource allocation: reputation + innovation + credibility.
    total = sum(safe_float(i.get("reputation"), 0.0) + safe_float(i.get("innovation"), 0.0) + safe_float(i.get("credibility"), 0.0) for i in institutions.values()) or 1.0
    for inst in institutions.values():
        raw = safe_float(inst.get("reputation"), 0.0) + safe_float(inst.get("innovation"), 0.0) + safe_float(inst.get("credibility"), 0.0)
        inst["resource_share"] = round(clamp(raw / total), 6)
    return institutions


def _citation_network(institutions: Dict[str, Dict[str, Any]], archive: Dict[str, Any], civ: Dict[str, Any]) -> Dict[str, Any]:
    ids = list(institutions.keys())
    entries = archive.get("entries") if isinstance(archive.get("entries"), dict) else {}
    links = []
    exchange = safe_float(civ.get("knowledge_exchange_score"), 0.0)
    for i, a in enumerate(ids):
        for b in ids:
            if a == b:
                continue
            ia, ib = institutions[a], institutions[b]
            affinity = 0.12 + 0.38 * exchange
            if ia.get("specialization") == ib.get("specialization"):
                affinity += 0.18
            weight = clamp(affinity * (0.35 + safe_float(ib.get("reputation"), 0.0)))
            if weight >= 0.10:
                links.append({"from": a, "to": b, "weight": round(weight, 6), "relation": "citation" if weight >= 0.25 else "weak_reference"})
    citation_count = sum(safe_int(v.get("citations"), 0) for v in entries.values() if isinstance(v, dict)) + len(links)
    return {"version": INSTITUTION_VERSION, "updated_at": now_s(), "links": links[:100], "citation_count": citation_count, "institution_count": len(ids)}


def compute_institutions(results_dir: Path, observer_population: Optional[Iterable[Any]] = None, clean_results: Optional[List[Any]] = None, generation: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    results_dir = Path(results_dir)
    dirs = ensure_dirs(results_dir)
    inst_dir = Path(dirs["observer_institutions_dir"])
    civ = _load_civilization(results_dir)
    prev = _load_previous_state(results_dir)
    institutions = _build_institutions(civ, prev)
    discoveries = _collect_discoveries(clean_results, generation)
    archive = _update_archive(results_dir, discoveries, institutions)
    citation = _citation_network(institutions, archive, civ)
    institution_count = len(institutions)
    archive_entries = safe_int(archive.get("entry_count"), len(archive.get("entries", {}) if isinstance(archive.get("entries"), dict) else {}))
    avg_rep = sum(safe_float(i.get("reputation"), 0.0) for i in institutions.values()) / max(1, institution_count)
    avg_innovation = sum(safe_float(i.get("innovation"), 0.0) for i in institutions.values()) / max(1, institution_count)
    knowledge_reuse = clamp(safe_float(citation.get("citation_count"), 0.0) / max(1, archive_entries + institution_count))
    resource_efficiency = clamp(0.40 * avg_rep + 0.30 * avg_innovation + 0.30 * safe_float(civ.get("maturity"), 0.0))
    institutional_maturity = round(clamp(0.26 * avg_rep + 0.22 * avg_innovation + 0.18 * knowledge_reuse + 0.18 * resource_efficiency + 0.16 * safe_float(civ.get("maturity"), 0.0)), 6)
    leading = None
    if institutions:
        leading = max(institutions.values(), key=lambda x: safe_float(x.get("reputation"), 0.0)).get("institution_id")
    stage = "PRE_INSTITUTIONAL"
    if institutional_maturity >= 0.72 and institution_count >= 4:
        stage = "RESEARCH_COMMONWEALTH"
    elif institutional_maturity >= 0.55 and institution_count >= 3:
        stage = "ACADEMIC_NETWORK"
    elif institutional_maturity >= 0.35 and institution_count >= 2:
        stage = "EARLY_INSTITUTIONS"
    elif institution_count >= 1:
        stage = "PROTO_INSTITUTION"
    prev_stage = str(prev.get("stage") or "NONE")
    events: List[Dict[str, Any]] = []
    if prev_stage != stage:
        events.append({"event": "INSTITUTION_STAGE_CHANGE", "from": prev_stage, "to": stage, "generation": generation})
    prev_insts = set((prev.get("institutions") or {}).keys()) if isinstance(prev.get("institutions"), dict) else set()
    for iid in sorted(set(institutions) - prev_insts):
        events.append({"event": "INSTITUTION_FOUNDING", "institution": iid, "generation": generation})
    recommendations: List[str] = []
    if institution_count < 3:
        recommendations.append("encourage_new_research_institutions")
    if archive_entries < 10:
        recommendations.append("increase_archived_discoveries")
    if knowledge_reuse < 0.25 and institution_count > 1:
        recommendations.append("increase_cross_institution_citations")
    if resource_efficiency < 0.35:
        recommendations.append("rebalance_compute_budget")
    if not recommendations:
        recommendations.append("maintain_institutional_research_growth")
    state = {
        "version": INSTITUTION_VERSION,
        "updated_at": now_s(),
        "generation": generation,
        "active": True,
        "safe": True,
        "influences_evolution": False,
        "stage": stage,
        "previous_stage": prev_stage,
        "institution_count": institution_count,
        "archive_entries": archive_entries,
        "citation_count": safe_int(citation.get("citation_count"), 0),
        "knowledge_reuse": round(knowledge_reuse, 6),
        "resource_efficiency": round(resource_efficiency, 6),
        "institutional_maturity": institutional_maturity,
        "leading_institution": leading,
        "institutions": institutions,
        "discoveries_this_generation": discoveries[:20],
        "events": events,
        "recommendations": recommendations,
        "context": context or {},
        "compatibility": {"renames_existing_files": False, "moves_existing_files": False, "writes_only_new_namespace": True},
    }
    atomic_write_json(inst_dir / "institution_state.json", state)
    atomic_write_json(inst_dir / "institution_registry.json", {"version": INSTITUTION_VERSION, "updated_at": now_s(), "institutions": institutions})
    atomic_write_json(inst_dir / "knowledge_archive.json", archive)
    atomic_write_json(inst_dir / "citation_network.json", citation)
    atomic_write_json(inst_dir / "institution_reputation.json", {"version": INSTITUTION_VERSION, "updated_at": now_s(), "reputation": {k: v.get("reputation") for k, v in institutions.items()}})
    atomic_write_json(inst_dir / "resource_allocation.json", {"version": INSTITUTION_VERSION, "updated_at": now_s(), "allocation": {k: v.get("resource_share") for k, v in institutions.items()}})
    atomic_write_json(inst_dir / "institution_status.json", state)
    atomic_write_json(results_dir / "observer_institutions_status.json", state)
    if generation is not None:
        atomic_write_json(inst_dir / f"generation_{generation:02d}_institutions.json", state)
        if events:
            old_events = read_json(inst_dir / "institution_history.json", []) or []
            if not isinstance(old_events, list):
                old_events = []
            old_events.extend([{**e, "timestamp": now_s()} for e in events])
            atomic_write_json(inst_dir / "institution_history.json", old_events[-1500:])
    return state


def initialize_institutions(results_dir: Path, observer_population: Optional[Iterable[Any]] = None, *, script: str = "unknown") -> Dict[str, Any]:
    return compute_institutions(results_dir, observer_population=observer_population, generation=None, context={"script": script, "phase": "initialize"})


def record_institutions_generation(results_dir: Path, generation: int, score_mode: str, observer_population: Optional[Iterable[Any]], clean_results: Optional[List[Any]], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = dict(context or {})
    ctx["score_mode"] = score_mode
    ctx["clean_result_count"] = len(clean_results or [])
    return compute_institutions(results_dir, observer_population=observer_population, clean_results=clean_results, generation=generation, context=ctx)


def apply_institution_layer(results_dir: Path, generation: int, score_mode: str, observer_population: Optional[Iterable[Any]], clean_results: Optional[List[Any]], context: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    state = record_institutions_generation(results_dir, generation, score_mode, observer_population, clean_results, context)
    institutions = state.get("institutions") if isinstance(state.get("institutions"), dict) else {}
    new_pop: List[Dict[str, Any]] = []
    for obs in observer_population or []:
        o = dict(obs) if isinstance(obs, dict) else {"raw_type": type(obs).__name__}
        school = str(o.get("research_school") or "general_school")
        inst_id, _ = _institution_from_school(school)
        inst = institutions.get(inst_id, {}) if isinstance(institutions, dict) else {}
        o["institution_generation"] = generation
        o["institution_id"] = inst_id
        o["institution_stage"] = state.get("stage")
        o["institutional_maturity"] = state.get("institutional_maturity")
        old = safe_float(o.get("civilization_selection_weight", o.get("ecosystem_selection_weight", o.get("ecology_selection_weight", o.get("fitness", 0.0)))), 0.0)
        if old > 1.0:
            old = min(1.0, old / 100.0)
        rep = safe_float(inst.get("reputation"), 0.0)
        innovation = safe_float(inst.get("innovation"), 0.0)
        o["institution_selection_weight"] = round(0.76 * old + 0.12 * rep + 0.07 * innovation + 0.05 * safe_float(state.get("institutional_maturity"), 0.0), 6)
        new_pop.append(o)
    new_pop.sort(key=lambda o: (safe_float(o.get("institution_selection_weight"), 0.0), safe_float(o.get("civilization_selection_weight", 0.0))), reverse=True)
    return new_pop or list(observer_population or []), state


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    print(
        f"[{prefix}] {INSTITUTION_VERSION} | active={status.get('active')} safe={status.get('safe')} "
        f"stage={status.get('stage')} maturity={safe_float(status.get('institutional_maturity'),0.0):.3f} "
        f"institutions={status.get('institution_count',0)} archive={status.get('archive_entries',0)} "
        f"citations={status.get('citation_count',0)} reuse={safe_float(status.get('knowledge_reuse'),0.0):.3f} "
        f"lead={status.get('leading_institution') or '-'}"
    )
