#!/usr/bin/env python3
"""
Universe Search Observer Ecosystem v25.4

Folder-safe ecosystem layer above observer_ecology.py.

Contract:
- Do NOT rename or move legacy files.
- Write only into universe_search_v23_results/observer_ecology/ plus a small
  root mirror ecosystem_status.json.
- Use existing species/ecological-selection data when present.
- Fall back conservatively if metrics are sparse.

This layer models species population dynamics, niche competition and cooperation
without requiring changes to universe_search_core.py.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ECOSYSTEM_VERSION = "v25.4 Observer Ecosystem"
OBSERVER_ECOLOGY_DIR = "observer_ecology"
STRATEGY_LOGS_DIR = "strategy_logs"
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


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
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
    eco_dir = results_dir / OBSERVER_ECOLOGY_DIR
    strat_dir = results_dir / STRATEGY_LOGS_DIR
    eco_dir.mkdir(parents=True, exist_ok=True)
    strat_dir.mkdir(parents=True, exist_ok=True)
    return {"results_dir": str(results_dir), "observer_ecology_dir": str(eco_dir), "strategy_logs_dir": str(strat_dir)}


def _load_registry(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / OBSERVER_ECOLOGY_DIR / "species_registry.json", {}) or {}


def _load_selection_state(results_dir: Path) -> Dict[str, Any]:
    return read_json(Path(results_dir) / OBSERVER_ECOLOGY_DIR / "ecological_selection_state.json", {}) or {}


def _species_from_observers(observer_population: Optional[Iterable[Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for obs in observer_population or []:
        if not isinstance(obs, dict):
            obs = {"species": DEFAULT_SPECIES}
        sp = str(obs.get("species") or obs.get("species_id") or DEFAULT_SPECIES)
        row = out.setdefault(sp, {
            "species": sp,
            "niche": obs.get("niche") or "unknown",
            "population": 0,
            "fitness_sum": 0.0,
            "best_fitness": 0.0,
            "selection_sum": 0.0,
        })
        row["population"] += 1
        fit = safe_float(obs.get("ecological_fitness", obs.get("fitness", obs.get("score", 0.0))), 0.0)
        if fit > 1.0:
            fit = min(1.0, fit / 100.0)
        row["fitness_sum"] += fit
        row["best_fitness"] = max(safe_float(row.get("best_fitness"), 0.0), fit)
        row["selection_sum"] += safe_float(obs.get("ecology_selection_weight"), fit)
    for row in out.values():
        pop = max(1, safe_int(row.get("population"), 1))
        row["avg_fitness"] = round(safe_float(row.get("fitness_sum"), 0.0) / pop, 6)
        row["avg_selection_weight"] = round(safe_float(row.get("selection_sum"), 0.0) / pop, 6)
    return out


def _species_from_registry(results_dir: Path) -> Dict[str, Dict[str, Any]]:
    reg = _load_registry(results_dir)
    out: Dict[str, Dict[str, Any]] = {}
    for sp in reg.get("species", []) or []:
        if not isinstance(sp, dict):
            continue
        name = str(sp.get("species") or sp.get("species_id") or DEFAULT_SPECIES)
        out[name] = {
            "species": name,
            "niche": sp.get("niche") or "unknown",
            "population": safe_int(sp.get("count"), 0),
            "avg_fitness": safe_float(sp.get("avg_fitness"), 0.0),
            "best_fitness": safe_float(sp.get("max_fitness"), 0.0),
            "role": sp.get("role"),
        }
    return out


def _merge_species(results_dir: Path, observer_population: Optional[Iterable[Any]]) -> Dict[str, Dict[str, Any]]:
    merged = _species_from_registry(results_dir)
    from_obs = _species_from_observers(observer_population)
    for name, row in from_obs.items():
        base = merged.setdefault(name, {"species": name, "niche": row.get("niche") or "unknown"})
        base.update({k: v for k, v in row.items() if k not in ("fitness_sum", "selection_sum")})
    state = _load_selection_state(results_dir)
    state_species = state.get("species") if isinstance(state.get("species"), dict) else {}
    for name, erow in state_species.items():
        base = merged.setdefault(str(name), {"species": str(name), "niche": erow.get("niche") or "unknown"})
        base["ecological_fitness"] = safe_float(erow.get("ecological_fitness"), base.get("avg_fitness", 0.0))
        base["extinction_risk"] = safe_float(erow.get("extinction_risk"), 0.0)
        base["desired_population"] = safe_int(erow.get("desired_population"), safe_int(base.get("population"), 0))
        base["status"] = erow.get("status") or base.get("status") or "ACTIVE"
    return merged


def _niche_key(row: Dict[str, Any]) -> str:
    return str(row.get("niche") or "unknown")


def _cooperation_score(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    if a.get("species") == b.get("species"):
        return 0.0
    niche_a = _niche_key(a)
    niche_b = _niche_key(b)
    # Different-but-adjacent knowledge roles cooperate; same niche competes.
    if niche_a == niche_b:
        return -0.18
    pairs = {niche_a, niche_b}
    if {"knowledge_detection", "information_dynamics"}.issubset(pairs):
        return 0.24
    if {"knowledge_persistence", "feedback_organization"}.issubset(pairs):
        return 0.22
    if {"localized_life", "complexity"}.issubset(pairs):
        return 0.20
    if {"crystal_defects", "knowledge_detection"}.issubset(pairs):
        return 0.18
    if {"complex_organization", "knowledge_detection"}.issubset(pairs):
        return 0.21
    if {"temporal_patterns", "persistence"}.issubset(pairs):
        return 0.16
    return 0.05


def build_synergy_matrix(species_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    matrix: Dict[str, Dict[str, float]] = {}
    links: List[Dict[str, Any]] = []
    for a in species_rows:
        sa = str(a.get("species"))
        matrix.setdefault(sa, {})
        for b in species_rows:
            sb = str(b.get("species"))
            if sa == sb:
                matrix[sa][sb] = 0.0
                continue
            val = round(_cooperation_score(a, b), 4)
            matrix[sa][sb] = val
            if abs(val) >= 0.15:
                links.append({"from": sa, "to": sb, "type": "cooperation" if val > 0 else "competition", "strength": val})
    links.sort(key=lambda x: abs(safe_float(x.get("strength"))), reverse=True)
    return {"version": ECOSYSTEM_VERSION, "updated_at": now_s(), "matrix": matrix, "strong_links": links[:50]}


def build_niche_competition(species_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    niches: Dict[str, Dict[str, Any]] = {}
    for row in species_rows:
        niche = _niche_key(row)
        bucket = niches.setdefault(niche, {"niche": niche, "species": [], "population": 0, "best_fitness": 0.0, "winner": None})
        pop = safe_int(row.get("population"), 0)
        fit = safe_float(row.get("ecological_fitness", row.get("avg_fitness", 0.0)), 0.0)
        bucket["species"].append(row.get("species"))
        bucket["population"] += pop
        if fit >= safe_float(bucket.get("best_fitness"), 0.0):
            bucket["best_fitness"] = round(fit, 6)
            bucket["winner"] = row.get("species")
    vals = list(niches.values())
    vals.sort(key=lambda x: (x.get("population", 0), x.get("best_fitness", 0.0)), reverse=True)
    return {"version": ECOSYSTEM_VERSION, "updated_at": now_s(), "niche_count": len(vals), "niches": vals}


def compute_ecosystem(results_dir: Path, observer_population: Optional[Iterable[Any]] = None, generation: Optional[int] = None, strategy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ensure_dirs(results_dir)
    eco_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    species_map = _merge_species(results_dir, observer_population)
    rows: List[Dict[str, Any]] = []
    total_pop = max(1, sum(safe_int(r.get("population"), 0) for r in species_map.values()))
    prev = read_json(eco_dir / "ecosystem_state.json", {}) or {}
    prev_species = prev.get("species") if isinstance(prev.get("species"), dict) else {}
    for name, row in species_map.items():
        pop = safe_int(row.get("population"), 0)
        eco_fit = safe_float(row.get("ecological_fitness", row.get("avg_fitness", 0.0)), 0.0)
        if eco_fit > 1.0:
            eco_fit = min(1.0, eco_fit / 100.0)
        risk = safe_float(row.get("extinction_risk"), max(0.0, 1.0 - eco_fit), 0.0) if False else safe_float(row.get("extinction_risk"), max(0.0, 1.0 - eco_fit))
        previous = prev_species.get(name, {}) if isinstance(prev_species, dict) else {}
        prev_pop = safe_int(previous.get("population"), pop)
        trend = "stable"
        if pop > prev_pop:
            trend = "expanding"
        elif pop < prev_pop:
            trend = "contracting"
        pressure = round(max(0.0, min(1.0, 0.55 * eco_fit + 0.25 * (pop / total_pop) + 0.20 * (1.0 - risk))), 6)
        status = str(row.get("status") or "ACTIVE")
        if risk >= 0.72:
            status = "AT_RISK"
        if pressure >= 0.70:
            status = "KEYSTONE"
        rows.append({
            "species": name,
            "niche": row.get("niche") or "unknown",
            "population": pop,
            "previous_population": prev_pop,
            "population_trend": trend,
            "ecological_fitness": round(eco_fit, 6),
            "extinction_risk": round(risk, 6),
            "ecosystem_pressure": pressure,
            "desired_population": safe_int(row.get("desired_population"), pop),
            "status": status,
            "role": row.get("role"),
        })
    rows.sort(key=lambda x: (x.get("ecosystem_pressure", 0.0), x.get("population", 0)), reverse=True)
    dominant = rows[0]["species"] if rows else None
    keystone = [r for r in rows if r.get("status") == "KEYSTONE"]
    at_risk = [r for r in rows if r.get("status") == "AT_RISK"]
    richness = len(rows)
    evenness = 0.0
    if rows:
        shares = [safe_int(r.get("population"), 0) / total_pop for r in rows if safe_int(r.get("population"), 0) > 0]
        if shares:
            h = -sum(p * math.log(p) for p in shares)
            evenness = h / math.log(max(2, len(shares)))
    synergy = build_synergy_matrix(rows)
    niches = build_niche_competition(rows)
    ecosystem_health = round(max(0.0, min(1.0, 0.35 * (richness / max(1, min(8, richness + 1))) + 0.30 * evenness + 0.25 * (sum(safe_float(r.get("ecological_fitness"), 0.0) for r in rows) / max(1, len(rows))) + 0.10 * (1.0 - (len(at_risk) / max(1, len(rows)))))), 6)
    recommendations: List[str] = []
    if richness < 3:
        recommendations.append("increase_species_diversity")
    if len(at_risk) > max(0, richness // 3):
        recommendations.append("protect_at_risk_species_or_add_controls")
    if evenness < 0.45 and richness > 1:
        recommendations.append("reduce_single_species_dominance")
    if not recommendations:
        recommendations.append("maintain_balanced_ecosystem")
    state = {
        "version": ECOSYSTEM_VERSION,
        "updated_at": now_s(),
        "generation": generation,
        "active": True,
        "safe": True,
        "influences_evolution": True,
        "species_count": richness,
        "observer_count": total_pop,
        "dominant_species": dominant,
        "keystone_species": [r.get("species") for r in keystone],
        "at_risk_species": [r.get("species") for r in at_risk],
        "ecosystem_health": ecosystem_health,
        "evenness": round(evenness, 6),
        "species": {r["species"]: r for r in rows},
        "species_rows": rows,
        "niche_competition": {"niche_count": niches.get("niche_count"), "niches": niches.get("niches", [])[:20]},
        "synergy_summary": {"strong_links": synergy.get("strong_links", [])[:20]},
        "recommendations": recommendations,
        "strategy_context": strategy or {},
        "compatibility": {"renames_existing_files": False, "moves_existing_files": False, "writes_only_new_namespace": True},
    }
    atomic_write_json(eco_dir / "ecosystem_state.json", state)
    atomic_write_json(eco_dir / "ecosystem_status.json", state)
    atomic_write_json(Path(results_dir) / "ecosystem_status.json", state)
    atomic_write_json(eco_dir / "synergy_matrix.json", synergy)
    atomic_write_json(eco_dir / "niche_competition.json", niches)
    return state


def initialize_ecosystem(results_dir: Path, observer_population: Optional[Iterable[Any]] = None, *, script: str = "unknown") -> Dict[str, Any]:
    state = compute_ecosystem(results_dir, observer_population, generation=None, strategy={"script": script, "phase": "initialize"})
    return state


def record_ecosystem_generation(
    results_dir: Path,
    generation: int,
    score_mode: str,
    observer_population: Optional[Iterable[Any]],
    clean_results: Optional[List[Any]],
    strategy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # clean_results is accepted for future use. v25.4 mostly consumes ecology state.
    ctx = dict(strategy or {})
    ctx["score_mode"] = score_mode
    state = compute_ecosystem(results_dir, observer_population, generation=generation, strategy=ctx)
    eco_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    atomic_write_json(eco_dir / f"generation_{generation:02d}_ecosystem.json", state)
    return state


def apply_ecosystem_dynamics(
    results_dir: Path,
    generation: int,
    score_mode: str,
    observer_population: Optional[Iterable[Any]],
    clean_results: Optional[List[Any]],
    strategy: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    state = record_ecosystem_generation(results_dir, generation, score_mode, observer_population, clean_results, strategy)
    species_state = state.get("species") if isinstance(state.get("species"), dict) else {}
    new_pop: List[Dict[str, Any]] = []
    for obs in observer_population or []:
        if isinstance(obs, dict):
            o = dict(obs)
        else:
            o = {"raw_type": type(obs).__name__}
        sp = str(o.get("species") or o.get("species_id") or DEFAULT_SPECIES)
        row = species_state.get(sp, {}) if isinstance(species_state, dict) else {}
        o["ecosystem_generation"] = generation
        o["ecosystem_pressure"] = safe_float(row.get("ecosystem_pressure"), 0.0)
        o["ecosystem_status"] = row.get("status", "ACTIVE")
        o["ecosystem_health"] = state.get("ecosystem_health")
        o["species_population_trend"] = row.get("population_trend")
        # Gentle ordering only: do not delete observers or mutate genomes here.
        old_weight = safe_float(o.get("ecology_selection_weight", o.get("fitness", 0.0)), 0.0)
        if old_weight > 1.0:
            old_weight = min(1.0, old_weight / 100.0)
        o["ecosystem_selection_weight"] = round(0.70 * old_weight + 0.30 * safe_float(row.get("ecosystem_pressure"), 0.0), 6)
        new_pop.append(o)
    new_pop.sort(key=lambda o: (safe_float(o.get("ecosystem_selection_weight"), 0.0), safe_float(o.get("ecology_selection_weight", 0.0))), reverse=True)
    return new_pop or list(observer_population or []), state


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    print(
        f"[{prefix}] {ECOSYSTEM_VERSION} | active={status.get('active')} safe={status.get('safe')} "
        f"species={status.get('species_count',0)} observers={status.get('observer_count',0)} "
        f"health={safe_float(status.get('ecosystem_health'),0.0):.3f} "
        f"dominant={status.get('dominant_species') or '-'} "
        f"keystone={','.join(status.get('keystone_species') or []) or '-'} "
        f"risk={','.join(status.get('at_risk_species') or []) or '-'}"
    )
