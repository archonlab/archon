#!/usr/bin/env python3
"""
Universe Search Observer Civilization v26.0

Folder-safe civilization layer above observer_ecosystem.py.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_civilization/ plus a small
  root mirror observer_civilization_status.json.
- Use ecosystem/species data when present.
- Fall back conservatively if metrics are sparse.

This layer models collective memory, scientific schools, knowledge exchange and
civilizational maturity of observer species without touching universe_search_core.py.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CIV_VERSION = "v26.0 Observer Civilization"
CIV_DIR = "observer_civilization"
ECOLOGY_DIR = "observer_ecology"
DEFAULT_SPECIES = "generalist_observer"


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
    civ = results_dir / CIV_DIR
    civ.mkdir(parents=True, exist_ok=True)
    return {"results_dir": str(results_dir), "observer_civilization_dir": str(civ)}


def _load_ecosystem(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / ECOLOGY_DIR / "ecosystem_state.json", {}) or read_json(Path(results_dir) / "ecosystem_status.json", {}) or {}


def _load_registry(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / ECOLOGY_DIR / "species_registry.json", {}) or {}


def _load_previous_state(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / CIV_DIR / "civilization_state.json", {}) or {}


def _species_rows_from_ecosystem(eco: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = eco.get("species_rows")
    if isinstance(rows, list) and rows:
        return [r for r in rows if isinstance(r, dict)]
    sp = eco.get("species") if isinstance(eco.get("species"), dict) else {}
    out = []
    for name, row in sp.items():
        if isinstance(row, dict):
            r = dict(row); r.setdefault("species", name); out.append(r)
    return out


def _specialization_from_name(name: str, niche: str = "") -> str:
    n = (name or "").lower() + " " + (niche or "").lower()
    if "memory" in n or "knowledge" in n:
        return "memory_school"
    if "oscillation" in n or "temporal" in n:
        return "temporal_school"
    if "structure" in n or "localized" in n or "life" in n:
        return "structure_school"
    if "information" in n:
        return "information_school"
    if "complex" in n or "civil" in n or "organization" in n:
        return "organization_school"
    if "crystal" in n:
        return "crystal_school"
    return "generalist_school"


def _extract_species_from_observers(observer_population: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for obs in observer_population or []:
        if isinstance(obs, dict):
            species = str(obs.get("species") or obs.get("species_id") or DEFAULT_SPECIES)
            niche = str(obs.get("niche") or obs.get("observer_niche") or "unknown")
            fit = safe_float(obs.get("fitness", obs.get("ecological_fitness", obs.get("score", 0.0))), 0.0)
        else:
            species, niche, fit = DEFAULT_SPECIES, "unknown", 0.0
        if fit > 1.0:
            fit = min(1.0, fit / 100.0)
        row = buckets.setdefault(species, {"species": species, "niche": niche, "population": 0, "fitness_sum": 0.0, "best_fitness": 0.0})
        row["population"] += 1
        row["fitness_sum"] += fit
        row["best_fitness"] = max(row.get("best_fitness", 0.0), fit)
    out = []
    for row in buckets.values():
        pop = max(1, safe_int(row.get("population"), 1))
        row["ecological_fitness"] = round(safe_float(row.get("fitness_sum"), 0.0) / pop, 6)
        out.append(row)
    return out


def _merge_species(results_dir: Path, observer_population: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    eco_rows = _species_rows_from_ecosystem(_load_ecosystem(results_dir))
    obs_rows = _extract_species_from_observers(observer_population)
    by_name: Dict[str, Dict[str, Any]] = {}
    for row in eco_rows + obs_rows:
        name = str(row.get("species") or row.get("species_id") or DEFAULT_SPECIES)
        old = by_name.setdefault(name, {"species": name})
        old.update({k: v for k, v in row.items() if k not in ("fitness_sum",)})
    return list(by_name.values())


def _knowledge_domains_for_school(school: str) -> List[str]:
    return {
        "memory_school": ["knowledge_persistence", "lineage_memory", "replication_evidence"],
        "temporal_school": ["oscillation_detection", "cycle_mapping", "stability_timing"],
        "structure_school": ["localized_life", "morphology", "spatial_scaffolds"],
        "information_school": ["information_dynamics", "compression", "transfer_patterns"],
        "organization_school": ["emergence", "feedback", "civilization_signatures"],
        "crystal_school": ["crystal_defects", "phase_boundaries", "quasi_particles"],
        "generalist_school": ["broad_scan", "triage", "novelty_detection"],
    }.get(school, ["broad_scan"])


def _civilization_stage(maturity: float, species_count: int, schools_count: int, memory_score: float, exchange_score: float) -> str:
    m = clamp(maturity)
    if species_count <= 0:
        return "EMPTY"
    if m < 0.18:
        return "BAND"
    if m < 0.32:
        return "TRIBE"
    if m < 0.48:
        return "PROTO_SCHOOL"
    if m < 0.64:
        return "RESEARCH_COMMONS"
    if m < 0.80:
        return "SCIENTIFIC_CIVILIZATION"
    if memory_score > 0.70 and exchange_score > 0.60 and schools_count >= 4:
        return "KNOWLEDGE_FEDERATION"
    return "MATURE_CIVILIZATION"


def build_schools(species_rows: List[Dict[str, Any]], previous: Dict[str, Any]) -> Dict[str, Any]:
    prev_schools = previous.get("schools") if isinstance(previous.get("schools"), dict) else {}
    schools: Dict[str, Dict[str, Any]] = {}
    for row in species_rows:
        species = str(row.get("species") or DEFAULT_SPECIES)
        niche = str(row.get("niche") or "unknown")
        school_id = _specialization_from_name(species, niche)
        school = schools.setdefault(school_id, {
            "school_id": school_id,
            "species": [],
            "population": 0,
            "fitness_sum": 0.0,
            "domains": _knowledge_domains_for_school(school_id),
        })
        pop = safe_int(row.get("population"), 0)
        fit = safe_float(row.get("ecological_fitness", row.get("avg_fitness", row.get("fitness", 0.0))), 0.0)
        if fit > 1.0:
            fit = min(1.0, fit / 100.0)
        school["species"].append(species)
        school["population"] += pop
        school["fitness_sum"] += fit * max(1, pop)
    for sid, school in schools.items():
        pop = max(1, safe_int(school.get("population"), 1))
        school["fitness"] = round(safe_float(school.get("fitness_sum"), 0.0) / pop, 6)
        prev = prev_schools.get(sid, {}) if isinstance(prev_schools, dict) else {}
        prev_age = safe_int(prev.get("age"), 0)
        school["age"] = prev_age + 1
        school["status"] = "FOUNDING"
        if school["age"] >= 3 and school["fitness"] > 0.55:
            school["status"] = "ESTABLISHED"
        if school["fitness"] > 0.72:
            school["status"] = "LEADING"
        if school["population"] <= 1 and school["fitness"] < 0.25:
            school["status"] = "FRAGILE"
        school.pop("fitness_sum", None)
    return schools


def build_collective_memory(schools: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
    prev_mem = previous.get("collective_memory") if isinstance(previous.get("collective_memory"), dict) else {}
    entries = prev_mem.get("entries") if isinstance(prev_mem.get("entries"), dict) else {}
    entries = dict(entries or {})
    for sid, school in schools.items():
        domains = school.get("domains") or []
        for domain in domains:
            row = entries.setdefault(domain, {
                "domain": domain,
                "supporting_schools": [],
                "strength": 0.0,
                "age": 0,
                "last_seen": now_s(),
            })
            if sid not in row["supporting_schools"]:
                row["supporting_schools"].append(sid)
            fit = safe_float(school.get("fitness"), 0.0)
            pop_bonus = min(0.25, safe_int(school.get("population"), 0) / 80.0)
            row["strength"] = round(clamp(0.72 * safe_float(row.get("strength"), 0.0) + 0.28 * clamp(fit + pop_bonus)), 6)
            row["age"] = safe_int(row.get("age"), 0) + 1
            row["last_seen"] = now_s()
    # gentle forgetting for inactive domains
    active_domains = {d for s in schools.values() for d in (s.get("domains") or [])}
    for domain, row in list(entries.items()):
        if domain not in active_domains:
            row["strength"] = round(safe_float(row.get("strength"), 0.0) * 0.97, 6)
            if row["strength"] < 0.02:
                entries.pop(domain, None)
    strengths = [safe_float(e.get("strength"), 0.0) for e in entries.values()]
    memory_score = round(sum(strengths) / max(1, len(strengths)), 6)
    return {
        "version": CIV_VERSION,
        "updated_at": now_s(),
        "domain_count": len(entries),
        "memory_score": memory_score,
        "entries": dict(sorted(entries.items(), key=lambda kv: safe_float(kv[1].get("strength"), 0.0), reverse=True)),
    }


def build_exchange_network(schools: Dict[str, Any]) -> Dict[str, Any]:
    ids = sorted(schools.keys())
    links = []
    matrix: Dict[str, Dict[str, float]] = {sid: {} for sid in ids}
    for a in ids:
        domains_a = set(schools[a].get("domains") or [])
        for b in ids:
            if a == b:
                matrix[a][b] = 0.0
                continue
            domains_b = set(schools[b].get("domains") or [])
            overlap = len(domains_a & domains_b)
            complement = len(domains_a ^ domains_b)
            fit = (safe_float(schools[a].get("fitness"), 0.0) + safe_float(schools[b].get("fitness"), 0.0)) / 2.0
            score = clamp(0.12 * overlap + 0.06 * min(5, complement) + 0.32 * fit)
            matrix[a][b] = round(score, 4)
            if score >= 0.24:
                links.append({"from": a, "to": b, "strength": round(score, 4), "type": "knowledge_exchange"})
    links.sort(key=lambda x: safe_float(x.get("strength"), 0.0), reverse=True)
    possible = max(1, len(ids) * max(1, len(ids) - 1))
    exchange_score = round(sum(safe_float(x.get("strength"), 0.0) for x in links) / possible, 6)
    return {"version": CIV_VERSION, "updated_at": now_s(), "school_count": len(ids), "exchange_score": exchange_score, "matrix": matrix, "links": links[:50]}


def compute_civilization(results_dir: Path, observer_population: Optional[Iterable[Any]] = None, generation: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ensure_dirs(results_dir)
    results_dir = Path(results_dir)
    civ_dir = results_dir / CIV_DIR
    prev = _load_previous_state(results_dir)
    eco = _load_ecosystem(results_dir)
    species_rows = _merge_species(results_dir, observer_population)
    if not species_rows:
        species_rows = [{"species": DEFAULT_SPECIES, "niche": "unknown", "population": safe_int((eco or {}).get("observer_count"), 0), "ecological_fitness": 0.0}]
    schools = build_schools(species_rows, prev)
    memory = build_collective_memory(schools, prev)
    exchange = build_exchange_network(schools)
    species_count = len({str(r.get("species") or DEFAULT_SPECIES) for r in species_rows})
    observers = sum(safe_int(r.get("population"), 0) for r in species_rows)
    school_count = len(schools)
    avg_school_fitness = round(sum(safe_float(s.get("fitness"), 0.0) for s in schools.values()) / max(1, school_count), 6)
    ecosystem_health = safe_float(eco.get("ecosystem_health"), 0.0)
    memory_score = safe_float(memory.get("memory_score"), 0.0)
    exchange_score = safe_float(exchange.get("exchange_score"), 0.0)
    diversity_score = clamp(species_count / 8.0 * 0.65 + school_count / 7.0 * 0.35)
    maturity = round(clamp(0.24 * ecosystem_health + 0.24 * memory_score + 0.18 * exchange_score + 0.18 * avg_school_fitness + 0.16 * diversity_score), 6)
    stage = _civilization_stage(maturity, species_count, school_count, memory_score, exchange_score)
    prev_stage = str(prev.get("stage") or "NONE")
    events: List[Dict[str, Any]] = []
    if prev_stage and prev_stage != stage:
        events.append({"event": "CIV_STAGE_CHANGE", "from": prev_stage, "to": stage, "generation": generation})
    for sid, school in schools.items():
        if safe_int(school.get("age"), 0) == 1:
            events.append({"event": "SCHOOL_FOUNDING", "school": sid, "generation": generation})
        elif school.get("status") == "LEADING":
            events.append({"event": "SCHOOL_ASCENDANT", "school": sid, "generation": generation})
    if memory_score >= 0.60 and safe_float((prev.get("collective_memory") or {}).get("memory_score"), 0.0) < 0.60:
        events.append({"event": "COLLECTIVE_MEMORY_THRESHOLD", "memory_score": memory_score, "generation": generation})
    recommendations: List[str] = []
    if species_count < 3:
        recommendations.append("increase_observer_species_diversity")
    if memory_score < 0.35:
        recommendations.append("strengthen_collective_memory")
    if exchange_score < 0.20 and school_count > 1:
        recommendations.append("increase_knowledge_exchange")
    if ecosystem_health < 0.45:
        recommendations.append("stabilize_observer_ecosystem_before_civilization_expansion")
    if not recommendations:
        recommendations.append("maintain_research_civilization_growth")
    state = {
        "version": CIV_VERSION,
        "updated_at": now_s(),
        "generation": generation,
        "active": True,
        "safe": True,
        "influences_evolution": False,
        "stage": stage,
        "previous_stage": prev_stage,
        "maturity": maturity,
        "species_count": species_count,
        "observer_count": observers,
        "school_count": school_count,
        "dominant_species": eco.get("dominant_species") or (species_rows[0].get("species") if species_rows else None),
        "leading_school": max(schools.values(), key=lambda s: safe_float(s.get("fitness"), 0.0)).get("school_id") if schools else None,
        "ecosystem_health": round(ecosystem_health, 6),
        "collective_memory_score": memory_score,
        "knowledge_exchange_score": exchange_score,
        "school_fitness": avg_school_fitness,
        "diversity_score": round(diversity_score, 6),
        "schools": schools,
        "collective_memory": memory,
        "exchange_network": {"exchange_score": exchange_score, "links": exchange.get("links", [])[:20]},
        "events": events,
        "recommendations": recommendations,
        "context": context or {},
        "compatibility": {"renames_existing_files": False, "moves_existing_files": False, "writes_only_new_namespace": True},
    }
    atomic_write_json(civ_dir / "civilization_state.json", state)
    atomic_write_json(civ_dir / "civilization_status.json", state)
    atomic_write_json(results_dir / "observer_civilization_status.json", state)
    atomic_write_json(civ_dir / "knowledge_library.json", memory)
    atomic_write_json(civ_dir / "schools.json", {"version": CIV_VERSION, "updated_at": now_s(), "schools": schools})
    atomic_write_json(civ_dir / "knowledge_exchange_network.json", exchange)
    if generation is not None:
        atomic_write_json(civ_dir / f"generation_{generation:02d}_civilization.json", state)
        if events:
            old_events = read_json(civ_dir / "civilization_events.json", []) or []
            if not isinstance(old_events, list):
                old_events = []
            old_events.extend([{**e, "timestamp": now_s()} for e in events])
            atomic_write_json(civ_dir / "civilization_events.json", old_events[-1000:])
    return state


def initialize_civilization(results_dir: Path, observer_population: Optional[Iterable[Any]] = None, *, script: str = "unknown") -> Dict[str, Any]:
    return compute_civilization(results_dir, observer_population, generation=None, context={"script": script, "phase": "initialize"})


def record_civilization_generation(results_dir: Path, generation: int, score_mode: str, observer_population: Optional[Iterable[Any]], clean_results: Optional[List[Any]], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = dict(context or {})
    ctx["score_mode"] = score_mode
    ctx["clean_result_count"] = len(clean_results or [])
    return compute_civilization(results_dir, observer_population, generation=generation, context=ctx)


def apply_civilization_layer(results_dir: Path, generation: int, score_mode: str, observer_population: Optional[Iterable[Any]], clean_results: Optional[List[Any]], context: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    state = record_civilization_generation(results_dir, generation, score_mode, observer_population, clean_results, context)
    schools = state.get("schools") if isinstance(state.get("schools"), dict) else {}
    new_pop: List[Dict[str, Any]] = []
    for obs in observer_population or []:
        if isinstance(obs, dict):
            o = dict(obs)
        else:
            o = {"raw_type": type(obs).__name__}
        sp = str(o.get("species") or o.get("species_id") or DEFAULT_SPECIES)
        school_id = _specialization_from_name(sp, str(o.get("niche") or o.get("observer_niche") or ""))
        school = schools.get(school_id, {}) if isinstance(schools, dict) else {}
        o["civilization_generation"] = generation
        o["civilization_stage"] = state.get("stage")
        o["research_school"] = school_id
        o["collective_memory_score"] = state.get("collective_memory_score")
        o["knowledge_exchange_score"] = state.get("knowledge_exchange_score")
        old = safe_float(o.get("ecosystem_selection_weight", o.get("ecology_selection_weight", o.get("fitness", 0.0))), 0.0)
        if old > 1.0:
            old = min(1.0, old / 100.0)
        school_fit = safe_float(school.get("fitness"), 0.0)
        # Gentle ordering only; civilization is a knowledge layer, not a hard survival gate.
        o["civilization_selection_weight"] = round(0.78 * old + 0.12 * school_fit + 0.10 * safe_float(state.get("maturity"), 0.0), 6)
        new_pop.append(o)
    new_pop.sort(key=lambda o: (safe_float(o.get("civilization_selection_weight"), 0.0), safe_float(o.get("ecosystem_selection_weight", 0.0))), reverse=True)
    return new_pop or list(observer_population or []), state


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    print(
        f"[{prefix}] {CIV_VERSION} | active={status.get('active')} safe={status.get('safe')} "
        f"stage={status.get('stage')} maturity={safe_float(status.get('maturity'),0.0):.3f} "
        f"species={status.get('species_count',0)} schools={status.get('school_count',0)} "
        f"memory={safe_float(status.get('collective_memory_score'),0.0):.3f} "
        f"exchange={safe_float(status.get('knowledge_exchange_score'),0.0):.3f} "
        f"lead={status.get('leading_school') or '-'}"
    )
