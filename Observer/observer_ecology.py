#!/usr/bin/env python3
"""
Universe Search Observer Ecology v25.2

Observer Species Registry layer.

Design rule:
- Do NOT rename or move existing Universe Search / Analyzer files.
- Do NOT change scoring or evolution yet.
- Write only into observer_ecology/ and strategy_logs/ plus small root status mirrors.
- v25.1 adds stable observer species classification and species-level registry.

This module is defensive by design: strange observer shapes produce conservative
"generalist_observer" species instead of failing the search run.
"""

from __future__ import annotations

import json
import math
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ECOLOGY_VERSION = "v25.1 Observer Species Registry"
OBSERVER_ECOLOGY_DIR = "observer_ecology"
STRATEGY_LOGS_DIR = "strategy_logs"

DEFAULT_SPECIES = "generalist_observer"
DEFAULT_NICHE = "general_observation"

# Published species catalog. This is intentionally stable because Analyzer and
# future Search stages may learn to refer to these names.
SPECIES_CATALOG: Dict[str, Dict[str, Any]] = {
    "generalist_observer": {
        "niche": "general_observation",
        "role": "balanced all-purpose observer",
        "signals": ["legacy_score", "dynamic_score", "observer_score"],
    },
    "memory_hunter": {
        "niche": "knowledge_detection",
        "role": "tracks memory, persistence and information retention",
        "signals": ["memory_trace_score", "information_survival", "identity_persistence"],
    },
    "oscillation_tracker": {
        "niche": "temporal_patterns",
        "role": "tracks periodicity, breathing and temporal structure",
        "signals": ["breathing_score", "crystal_period_x", "crystal_period_y", "temporal_stability"],
    },
    "stability_reader": {
        "niche": "persistence",
        "role": "tracks survival, persistence and long-lived organization",
        "signals": ["organism_lifetime", "organism_survived_probe", "stability"],
    },
    "structure_mapper": {
        "niche": "localized_life",
        "role": "tracks organisms, entities, islands and spatial structure",
        "signals": ["entity_count", "best_entity_quality", "islands", "macro_scaffold"],
    },
    "information_scout": {
        "niche": "information_dynamics",
        "role": "tracks entropy, information dynamics and signal transfer",
        "signals": ["information_entropy_mean", "information_temporal_stability", "information_bonus"],
    },
    "complexity_probe": {
        "niche": "complexity",
        "role": "tracks novelty, diversity and complex organization",
        "signals": ["novelty_behavior", "in_generation_diversity", "nested_score_raw"],
    },
    "crystal_scout": {
        "niche": "crystal_defects",
        "role": "tracks crystals, defects and quasi-particle structure",
        "signals": ["crystal_order", "defect_density", "quasi_particle_score"],
    },
    "civilization_probe": {
        "niche": "complex_organization",
        "role": "tracks civilization-like and multi-layer organization signals",
        "signals": ["emergence_score", "feedback_score", "knowledge_score"],
    },
}

SPECIES_HINTS = [
    ("memory", "memory_hunter"), ("knowledge", "memory_hunter"),
    ("osc", "oscillation_tracker"), ("period", "oscillation_tracker"), ("breath", "oscillation_tracker"),
    ("stable", "stability_reader"), ("stability", "stability_reader"), ("survival", "stability_reader"),
    ("organism", "structure_mapper"), ("entity", "structure_mapper"), ("island", "structure_mapper"),
    ("info", "information_scout"), ("information", "information_scout"), ("entropy", "information_scout"),
    ("novel", "complexity_probe"), ("complex", "complexity_probe"), ("diversity", "complexity_probe"),
    ("crystal", "crystal_scout"), ("defect", "crystal_scout"), ("quasi", "crystal_scout"),
    ("civil", "civilization_probe"), ("feedback", "civilization_probe"), ("emerg", "civilization_probe"),
]


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


def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def ensure_ecology_dirs(results_dir: Path) -> Dict[str, str]:
    results_dir = Path(results_dir)
    ecology_dir = results_dir / OBSERVER_ECOLOGY_DIR
    strategy_dir = results_dir / STRATEGY_LOGS_DIR
    ecology_dir.mkdir(parents=True, exist_ok=True)
    strategy_dir.mkdir(parents=True, exist_ok=True)
    return {
        "results_dir": str(results_dir),
        "observer_ecology_dir": str(ecology_dir),
        "strategy_logs_dir": str(strategy_dir),
    }


def observer_id(observer: Dict[str, Any], fallback: int) -> str:
    for key in ("id", "observer_id", "name"):
        v = observer.get(key)
        if v is not None:
            return str(v)
    return f"observer_{fallback:04d}"


def _flatten_text(observer: Dict[str, Any]) -> str:
    bits: List[str] = []
    for key in ("species", "species_id", "archetype", "name", "kind", "role", "observer_type", "note"):
        v = observer.get(key)
        if v is not None:
            bits.append(str(v).lower())
    # Weights/features are often the real genome of an observer. Preserve only keys,
    # not large nested content.
    for key in ("weights", "features", "genome", "focus", "metrics"):
        v = observer.get(key)
        if isinstance(v, dict):
            bits.extend(str(k).lower() for k in v.keys())
        elif isinstance(v, list):
            bits.extend(str(x).lower() for x in v[:20])
        elif v is not None:
            bits.append(str(v).lower())
    return " ".join(bits)


def infer_species(observer: Dict[str, Any]) -> Tuple[str, str, str]:
    explicit = str(observer.get("species") or observer.get("species_name") or "").strip()
    if explicit in SPECIES_CATALOG:
        niche = SPECIES_CATALOG[explicit]["niche"]
        return explicit, niche, "explicit"

    text = _flatten_text(observer)
    for needle, species in SPECIES_HINTS:
        if needle in text:
            niche = SPECIES_CATALOG[species]["niche"]
            return species, niche, f"hint:{needle}"

    # Numeric fallback: if an observer is just a genome/weights dict, derive a coarse
    # species from the strongest known signal key.
    best_species = DEFAULT_SPECIES
    best_weight = 0.0
    weights = observer.get("weights") if isinstance(observer.get("weights"), dict) else {}
    for species, meta in SPECIES_CATALOG.items():
        score = 0.0
        for sig in meta.get("signals", []):
            for k, v in weights.items():
                if str(sig).lower() in str(k).lower():
                    score += abs(safe_float(v, 0.0))
        if score > best_weight:
            best_weight = score
            best_species = species
    if best_weight > 0:
        return best_species, SPECIES_CATALOG[best_species]["niche"], "weights"
    return DEFAULT_SPECIES, DEFAULT_NICHE, "fallback"


def stable_species_lineage_id(observer: Dict[str, Any], species: str, oid: str) -> str:
    seed = {
        "species": species,
        "observer_id": oid,
        "archetype": observer.get("archetype"),
        "parent_id": observer.get("parent_id"),
        "parent_species": observer.get("parent_species"),
    }
    raw = json.dumps(seed, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{species}:{h}"


def summarize_observer_population(observer_population: Optional[Iterable[Any]]) -> Dict[str, Any]:
    species: Dict[str, Dict[str, Any]] = {}
    individuals: List[Dict[str, Any]] = []
    if not observer_population:
        return {
            "observer_count": 0,
            "species_count": 0,
            "species": [],
            "individuals": [],
            "dominant_species": None,
            "species_catalog": SPECIES_CATALOG,
        }

    for i, raw in enumerate(observer_population):
        if not isinstance(raw, dict):
            raw = {"raw_type": type(raw).__name__}
        sp, niche, reason = infer_species(raw)
        oid = observer_id(raw, i)
        fitness = safe_float(raw.get("fitness", raw.get("score", raw.get("observer_score", 0.0))))
        lineage_id = stable_species_lineage_id(raw, sp, oid)
        parent_species = raw.get("parent_species") or raw.get("species_parent") or None
        entry = {
            "observer_id": oid,
            "species": sp,
            "species_id": sp,
            "lineage_id": lineage_id,
            "parent_species": parent_species,
            "niche": niche,
            "fitness": round(fitness, 6),
            "archetype": raw.get("archetype", raw.get("kind", "unknown")),
            "classification_reason": reason,
            "generation": raw.get("generation", raw.get("born_generation")),
        }
        individuals.append(entry)
        bucket = species.setdefault(sp, {
            "species": sp,
            "species_id": sp,
            "niche": niche,
            "role": SPECIES_CATALOG.get(sp, {}).get("role", "unknown"),
            "count": 0,
            "fitness_sum": 0.0,
            "fitness_max": None,
            "observer_ids": [],
            "lineage_ids": [],
            "parents": {},
            "classification_reasons": {},
        })
        bucket["count"] += 1
        bucket["fitness_sum"] += fitness
        bucket["fitness_max"] = fitness if bucket["fitness_max"] is None else max(bucket["fitness_max"], fitness)
        bucket["observer_ids"].append(oid)
        bucket["lineage_ids"].append(lineage_id)
        if parent_species:
            bucket["parents"][str(parent_species)] = bucket["parents"].get(str(parent_species), 0) + 1
        bucket["classification_reasons"][reason] = bucket["classification_reasons"].get(reason, 0) + 1

    species_list = []
    for sp, d in species.items():
        count = max(1, int(d["count"]))
        species_list.append({
            "species": sp,
            "species_id": d["species_id"],
            "niche": d["niche"],
            "role": d["role"],
            "count": d["count"],
            "avg_fitness": round(d["fitness_sum"] / count, 6),
            "max_fitness": round(safe_float(d["fitness_max"]), 6),
            "observer_ids": d["observer_ids"][:50],
            "lineage_ids": d["lineage_ids"][:50],
            "parents": d["parents"],
            "classification_reasons": d["classification_reasons"],
        })
    species_list.sort(key=lambda x: (x["count"], x["max_fitness"]), reverse=True)
    dominant = species_list[0]["species"] if species_list else None
    return {
        "observer_count": len(individuals),
        "species_count": len(species_list),
        "species": species_list,
        "individuals": individuals[:1000],
        "dominant_species": dominant,
        "species_catalog": SPECIES_CATALOG,
    }


def summarize_results(clean_results: Optional[List[Any]]) -> Dict[str, Any]:
    if not clean_results:
        return {
            "valid_worlds": 0,
            "top_score": 0.0,
            "dominant_observer_archetype": None,
            "observer_archetypes": {},
            "signal_summary": {},
        }
    archetypes: Dict[str, int] = {}
    signals = {
        "memory_trace_score": [], "organism_lifetime": [], "information_survival": [],
        "best_entity_quality": [], "novelty_behavior": [], "in_generation_diversity": [],
        "observer_score": [], "information_entropy_mean": [], "identity_persistence": [],
        "crystal_order": [], "defect_density": [], "quasi_particle_score": [],
    }
    top_score = safe_float(clean_results[0][0]) if clean_results else 0.0
    for score, rule, metrics in clean_results:
        if not isinstance(metrics, dict):
            continue
        arch = str(metrics.get("observer_archetype", metrics.get("observer_id", "unknown")))
        archetypes[arch] = archetypes.get(arch, 0) + 1
        for k in signals:
            signals[k].append(safe_float(metrics.get(k, 0.0)))
    signal_summary = {}
    for k, vals in signals.items():
        if vals:
            signal_summary[k] = {"mean": round(sum(vals) / len(vals), 6), "max": round(max(vals), 6)}
    dominant_arch = None
    if archetypes:
        dominant_arch = sorted(archetypes.items(), key=lambda kv: kv[1], reverse=True)[0][0]
    return {
        "valid_worlds": len(clean_results),
        "top_score": round(top_score, 6),
        "dominant_observer_archetype": dominant_arch,
        "observer_archetypes": dict(sorted(archetypes.items(), key=lambda kv: kv[1], reverse=True)[:20]),
        "signal_summary": signal_summary,
    }


def build_niche_map(species_summary: Dict[str, Any], result_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    niches: Dict[str, Dict[str, Any]] = {}
    for sp in species_summary.get("species", []):
        niche = sp.get("niche") or DEFAULT_NICHE
        bucket = niches.setdefault(niche, {
            "niche": niche,
            "species": [],
            "observer_count": 0,
            "best_species": None,
            "best_fitness": 0.0,
            "roles": [],
        })
        bucket["species"].append(sp.get("species"))
        bucket["roles"].append(sp.get("role"))
        bucket["observer_count"] += safe_int(sp.get("count"), 0)
        mf = safe_float(sp.get("max_fitness"), 0.0)
        if mf >= safe_float(bucket.get("best_fitness"), 0.0):
            bucket["best_fitness"] = round(mf, 6)
            bucket["best_species"] = sp.get("species")
    return {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "niche_count": len(niches),
        "niches": sorted(niches.values(), key=lambda x: x["observer_count"], reverse=True),
        "result_context": result_summary or {},
    }


def update_lineage_tree(results_dir: Path, species_summary: Dict[str, Any], generation: Optional[int] = None) -> Dict[str, Any]:
    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    path = ecology_dir / "lineage_tree.json"
    old = read_json(path, {}) or {}
    if not isinstance(old, dict):
        old = {}
    history = old.get("history") if isinstance(old.get("history"), list) else []
    snapshot = {
        "time": now_s(),
        "generation": generation,
        "species_count": species_summary.get("species_count", 0),
        "observer_count": species_summary.get("observer_count", 0),
        "dominant_species": species_summary.get("dominant_species"),
        "species": [
            {
                "species": s.get("species"), "species_id": s.get("species_id"),
                "niche": s.get("niche"), "count": s.get("count"),
                "max_fitness": s.get("max_fitness"), "parents": s.get("parents", {}),
            }
            for s in species_summary.get("species", [])[:30]
        ],
    }
    history.append(snapshot)
    history = history[-1000:]
    out = {"version": ECOLOGY_VERSION, "updated_at": now_s(), "history_count": len(history), "history": history}
    atomic_write_json(path, out)
    return out


def write_species_registry(results_dir: Path, species_summary: Dict[str, Any], *, script: str = "unknown") -> Path:
    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    registry = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "script": script,
        "schema": "observer_species_registry_v1",
        **species_summary,
    }
    path = ecology_dir / "species_registry.json"
    atomic_write_json(path, registry)
    return path


def initialize_ecology(results_dir: Path, observer_population: Optional[Iterable[Any]] = None, *, script: str = "unknown") -> Dict[str, Any]:
    paths = ensure_ecology_dirs(results_dir)
    species_summary = summarize_observer_population(observer_population)
    niche_map = build_niche_map(species_summary)
    lineage = update_lineage_tree(results_dir, species_summary, generation=None)

    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    registry_path = write_species_registry(results_dir, species_summary, script=script)
    status = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "script": script,
        "mode": "species_registry_foundation",
        "active": True,
        "influences_evolution": False,
        "compatibility": {
            "renames_existing_files": False,
            "moves_existing_files": False,
            "writes_only_new_namespace": True,
        },
        "paths": paths,
        "observer_count": species_summary.get("observer_count", 0),
        "species_count": species_summary.get("species_count", 0),
        "dominant_species": species_summary.get("dominant_species"),
        "species_names": [s.get("species") for s in species_summary.get("species", [])],
        "lineage_history_count": lineage.get("history_count", 0),
        "files": {"species_registry": str(registry_path), "niche_map": str(ecology_dir / "niche_map.json")},
    }
    atomic_write_json(ecology_dir / "niche_map.json", niche_map)
    atomic_write_json(ecology_dir / "ecology_status.json", status)
    atomic_write_json(Path(results_dir) / "observer_ecology_status.json", status)
    return status


def record_generation_ecology(
    results_dir: Path,
    generation: int,
    score_mode: str,
    observer_population: Optional[Iterable[Any]],
    clean_results: Optional[List[Any]],
    strategy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_ecology_dirs(results_dir)
    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    strategy_dir = Path(results_dir) / STRATEGY_LOGS_DIR
    species_summary = summarize_observer_population(observer_population)
    result_summary = summarize_results(clean_results)
    niche_map = build_niche_map(species_summary, result_summary)
    lineage = update_lineage_tree(results_dir, species_summary, generation=generation)

    snapshot = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "generation": generation,
        "score_mode": score_mode,
        "influences_evolution": False,
        "species_summary": species_summary,
        "result_summary": result_summary,
        "strategy_context": strategy or {},
    }
    atomic_write_json(ecology_dir / f"generation_{generation:02d}_ecology.json", snapshot)
    write_species_registry(results_dir, species_summary, script=f"generation_{generation:02d}")
    atomic_write_json(ecology_dir / "niche_map.json", niche_map)

    status = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "mode": "species_registry_foundation",
        "active": True,
        "influences_evolution": False,
        "generation": generation,
        "score_mode": score_mode,
        "observer_count": species_summary.get("observer_count", 0),
        "species_count": species_summary.get("species_count", 0),
        "dominant_species": species_summary.get("dominant_species"),
        "species_names": [s.get("species") for s in species_summary.get("species", [])],
        "valid_worlds": result_summary.get("valid_worlds", 0),
        "top_score": result_summary.get("top_score", 0.0),
        "lineage_history_count": lineage.get("history_count", 0),
        "files": {
            "species_registry": str(ecology_dir / "species_registry.json"),
            "niche_map": str(ecology_dir / "niche_map.json"),
            "lineage_tree": str(ecology_dir / "lineage_tree.json"),
            "generation_snapshot": str(ecology_dir / f"generation_{generation:02d}_ecology.json"),
        },
    }
    atomic_write_json(ecology_dir / "ecology_status.json", status)
    atomic_write_json(Path(results_dir) / "observer_ecology_status.json", status)

    if strategy:
        atomic_write_json(strategy_dir / f"generation_{generation:02d}_strategy_context.json", strategy)
    return status


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    names = status.get("species_names") or []
    names_s = ",".join(str(x) for x in names[:4]) if names else "-"
    print(
        f"[{prefix}] {ECOLOGY_VERSION} | active={status.get('active')} "
        f"safe={status.get('compatibility', {}).get('writes_only_new_namespace', True)} "
        f"species={status.get('species_count', 0)} observers={status.get('observer_count', 0)} "
        f"dominant={status.get('dominant_species') or '-'} registry={names_s}"
    )

# ---------------------------------------------------------------------------
# v25.2 Observer Speciation layer
# ---------------------------------------------------------------------------
# These definitions intentionally override a few v25.1 functions above while
# keeping the old file/folder contract intact. Existing Analyzer/Search files keep
# working because we only add new files under observer_ecology/ and mirror the same
# observer_ecology_status.json root status.

ECOLOGY_VERSION = "v25.2 Observer Speciation"

DERIVED_SPECIES_CATALOG: Dict[str, Dict[str, Any]] = {
    "memory_stability_hunter": {
        "parent": "memory_hunter",
        "niche": "knowledge_persistence",
        "role": "tracks memory that survives long-lived organization",
        "signals": ["memory_trace_score", "identity_persistence", "organism_lifetime"],
    },
    "crystal_memory_hunter": {
        "parent": "memory_hunter",
        "niche": "crystal_memory",
        "role": "tracks memory stored in crystal/defect structures",
        "signals": ["memory_trace_score", "crystal_order", "defect_density"],
    },
    "adaptive_feedback_probe": {
        "parent": "civilization_probe",
        "niche": "feedback_organization",
        "role": "tracks feedback loops and adaptive self-regulation",
        "signals": ["feedback_score", "emergence_score", "information_survival"],
    },
    "entropy_cartographer": {
        "parent": "information_scout",
        "niche": "entropy_topology",
        "role": "tracks entropy patterns and information flow landscapes",
        "signals": ["information_entropy_mean", "information_temporal_stability", "novelty_behavior"],
    },
    "organism_architect": {
        "parent": "structure_mapper",
        "niche": "entity_architecture",
        "role": "tracks high-quality organisms and persistent spatial scaffolds",
        "signals": ["best_entity_quality", "entity_count", "organism_lifetime"],
    },
    "civil_memory_archivist": {
        "parent": "civilization_probe",
        "niche": "civilizational_memory",
        "role": "tracks complex organization with durable knowledge memory",
        "signals": ["emergence_score", "knowledge_score", "memory_trace_score"],
    },
}


def _mean_signal(result_summary: Dict[str, Any], key: str) -> float:
    signals = result_summary.get("signal_summary") if isinstance(result_summary, dict) else {}
    if not isinstance(signals, dict):
        return 0.0
    item = signals.get(key) or {}
    if isinstance(item, dict):
        return safe_float(item.get("mean", item.get("max", 0.0)), 0.0)
    return safe_float(item, 0.0)


def _max_signal(result_summary: Dict[str, Any], key: str) -> float:
    signals = result_summary.get("signal_summary") if isinstance(result_summary, dict) else {}
    if not isinstance(signals, dict):
        return 0.0
    item = signals.get(key) or {}
    if isinstance(item, dict):
        return safe_float(item.get("max", item.get("mean", 0.0)), 0.0)
    return safe_float(item, 0.0)


def _species_index(species_summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for sp in species_summary.get("species", []) or []:
        if isinstance(sp, dict) and sp.get("species"):
            out[str(sp.get("species"))] = sp
    return out


def _speciation_score(candidate: Dict[str, Any], species_summary: Dict[str, Any], result_summary: Dict[str, Any]) -> float:
    parent = str(candidate.get("parent") or DEFAULT_SPECIES)
    sindex = _species_index(species_summary)
    parent_data = sindex.get(parent, {})
    parent_count = safe_float(parent_data.get("count", 0.0), 0.0)
    parent_fit = safe_float(parent_data.get("max_fitness", parent_data.get("avg_fitness", 0.0)), 0.0)
    signal_vals = []
    for sig in candidate.get("signals", []) or []:
        signal_vals.append(max(_mean_signal(result_summary, sig), _max_signal(result_summary, sig) * 0.66))
    signal_score = sum(signal_vals) / max(1, len(signal_vals))
    world_score = safe_float(result_summary.get("top_score", 0.0), 0.0)
    # Works with both tiny normalized signals and big old legacy scores.
    world_norm = min(1.0, max(0.0, world_score / 10.0))
    parent_presence = min(1.0, parent_count / max(1.0, safe_float(species_summary.get("observer_count", 1), 1)))
    return round(min(1.0, 0.36 * signal_score + 0.22 * parent_fit + 0.20 * world_norm + 0.22 * parent_presence), 6)


def infer_speciation_events(
    results_dir: Path,
    species_summary: Dict[str, Any],
    result_summary: Dict[str, Any],
    generation: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Create conservative candidate branching events from observed species + signals.

    This does not mutate the actual observer population yet. It only records which
    species lines deserve future ecological pressure.
    """
    sindex = _species_index(species_summary)
    events: List[Dict[str, Any]] = []
    if not sindex:
        return events
    for child, meta in DERIVED_SPECIES_CATALOG.items():
        parent = str(meta.get("parent") or DEFAULT_SPECIES)
        if parent not in sindex:
            continue
        score = _speciation_score(meta, species_summary, result_summary)
        # Low threshold because early runs may have sparse metrics. Below 0.22 is
        # mostly noise, so we keep the event as a watchlist only if it passes.
        if score < 0.22:
            continue
        event_type = "CANDIDATE_SPECIATION"
        if score >= 0.58:
            event_type = "SPECIATION_CONFIRMED"
        elif score >= 0.40:
            event_type = "SPECIATION_PRESSURE"
        events.append({
            "time": now_s(),
            "generation": generation,
            "event_type": event_type,
            "parent_species": parent,
            "child_species": child,
            "niche": meta.get("niche"),
            "role": meta.get("role"),
            "score": score,
            "signals": list(meta.get("signals", [])),
            "parent_count": safe_int(sindex.get(parent, {}).get("count"), 0),
            "parent_max_fitness": safe_float(sindex.get(parent, {}).get("max_fitness"), 0.0),
            "valid_worlds": safe_int(result_summary.get("valid_worlds"), 0),
            "top_score": safe_float(result_summary.get("top_score"), 0.0),
        })
    events.sort(key=lambda x: (x.get("event_type") == "SPECIATION_CONFIRMED", x.get("score", 0)), reverse=True)
    return events[:20]


def update_species_tree(
    results_dir: Path,
    species_summary: Dict[str, Any],
    speciation_events: List[Dict[str, Any]],
    generation: Optional[int] = None,
) -> Dict[str, Any]:
    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    path = ecology_dir / "species_tree.json"
    old = read_json(path, {}) or {}
    if not isinstance(old, dict):
        old = {}
    nodes = old.get("nodes") if isinstance(old.get("nodes"), dict) else {}
    edges = old.get("edges") if isinstance(old.get("edges"), list) else []
    event_history = old.get("event_history") if isinstance(old.get("event_history"), list) else []

    # Stable catalog/base nodes.
    for sp, meta in SPECIES_CATALOG.items():
        nodes.setdefault(sp, {
            "species": sp,
            "parent": None,
            "niche": meta.get("niche"),
            "role": meta.get("role"),
            "origin": "catalog",
            "first_seen_generation": None,
            "last_seen_generation": None,
            "seen_count": 0,
            "best_fitness": 0.0,
            "status": "catalog",
        })
    for sp in species_summary.get("species", []) or []:
        name = str(sp.get("species"))
        if not name:
            continue
        n = nodes.setdefault(name, {
            "species": name,
            "parent": None,
            "niche": sp.get("niche"),
            "role": sp.get("role"),
            "origin": "observed",
            "first_seen_generation": generation,
            "last_seen_generation": generation,
            "seen_count": 0,
            "best_fitness": 0.0,
            "status": "observed",
        })
        if n.get("first_seen_generation") is None:
            n["first_seen_generation"] = generation
        n["last_seen_generation"] = generation
        n["seen_count"] = safe_int(n.get("seen_count"), 0) + 1
        n["best_fitness"] = round(max(safe_float(n.get("best_fitness"), 0.0), safe_float(sp.get("max_fitness"), 0.0)), 6)
        n["status"] = "active"

    for ev in speciation_events:
        child = str(ev.get("child_species"))
        parent = str(ev.get("parent_species") or DEFAULT_SPECIES)
        if not child:
            continue
        node = nodes.setdefault(child, {
            "species": child,
            "parent": parent,
            "niche": ev.get("niche"),
            "role": ev.get("role"),
            "origin": "speciation_candidate",
            "first_seen_generation": generation,
            "last_seen_generation": generation,
            "seen_count": 0,
            "best_fitness": 0.0,
            "status": "candidate",
        })
        node["parent"] = parent
        node["niche"] = ev.get("niche") or node.get("niche")
        node["role"] = ev.get("role") or node.get("role")
        node["last_seen_generation"] = generation
        node["speciation_score"] = ev.get("score")
        node["status"] = "branched" if ev.get("event_type") == "SPECIATION_CONFIRMED" else "candidate"
        edge_key = (parent, child)
        if not any((e.get("parent"), e.get("child")) == edge_key for e in edges):
            edges.append({"parent": parent, "child": child, "first_seen_generation": generation, "event_type": ev.get("event_type")})
        event_history.append(ev)

    event_history = event_history[-1000:]
    out = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "generation": generation,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "event_count": len(event_history),
        "nodes": nodes,
        "edges": edges,
        "event_history": event_history,
    }
    atomic_write_json(path, out)
    atomic_write_json(ecology_dir / "speciation_events.json", {"version": ECOLOGY_VERSION, "updated_at": now_s(), "events": event_history})
    return out


def initialize_ecology(results_dir: Path, observer_population: Optional[Iterable[Any]] = None, *, script: str = "unknown") -> Dict[str, Any]:
    paths = ensure_ecology_dirs(results_dir)
    species_summary = summarize_observer_population(observer_population)
    result_summary = {"valid_worlds": 0, "top_score": 0.0, "signal_summary": {}}
    speciation_events = infer_speciation_events(results_dir, species_summary, result_summary, generation=None)
    species_tree = update_species_tree(results_dir, species_summary, speciation_events, generation=None)
    niche_map = build_niche_map(species_summary)
    lineage = update_lineage_tree(results_dir, species_summary, generation=None)

    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    registry_path = write_species_registry(results_dir, species_summary, script=script)
    status = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "script": script,
        "mode": "observer_speciation_foundation",
        "active": True,
        "influences_evolution": False,
        "compatibility": {
            "renames_existing_files": False,
            "moves_existing_files": False,
            "writes_only_new_namespace": True,
        },
        "paths": paths,
        "observer_count": species_summary.get("observer_count", 0),
        "species_count": species_summary.get("species_count", 0),
        "dominant_species": species_summary.get("dominant_species"),
        "species_names": [s.get("species") for s in species_summary.get("species", [])],
        "speciation_candidates": len(speciation_events),
        "species_tree_nodes": species_tree.get("node_count", 0),
        "species_tree_edges": species_tree.get("edge_count", 0),
        "lineage_history_count": lineage.get("history_count", 0),
        "files": {
            "species_registry": str(registry_path),
            "niche_map": str(ecology_dir / "niche_map.json"),
            "lineage_tree": str(ecology_dir / "lineage_tree.json"),
            "species_tree": str(ecology_dir / "species_tree.json"),
            "speciation_events": str(ecology_dir / "speciation_events.json"),
        },
    }
    atomic_write_json(ecology_dir / "niche_map.json", niche_map)
    atomic_write_json(ecology_dir / "ecology_status.json", status)
    atomic_write_json(Path(results_dir) / "observer_ecology_status.json", status)
    return status


def record_generation_ecology(
    results_dir: Path,
    generation: int,
    score_mode: str,
    observer_population: Optional[Iterable[Any]],
    clean_results: Optional[List[Any]],
    strategy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_ecology_dirs(results_dir)
    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    strategy_dir = Path(results_dir) / STRATEGY_LOGS_DIR
    species_summary = summarize_observer_population(observer_population)
    result_summary = summarize_results(clean_results)
    speciation_events = infer_speciation_events(results_dir, species_summary, result_summary, generation=generation)
    species_tree = update_species_tree(results_dir, species_summary, speciation_events, generation=generation)
    niche_map = build_niche_map(species_summary, result_summary)
    lineage = update_lineage_tree(results_dir, species_summary, generation=generation)

    snapshot = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "generation": generation,
        "score_mode": score_mode,
        "influences_evolution": False,
        "species_summary": species_summary,
        "result_summary": result_summary,
        "speciation_events": speciation_events,
        "species_tree_summary": {
            "nodes": species_tree.get("node_count", 0),
            "edges": species_tree.get("edge_count", 0),
            "events": species_tree.get("event_count", 0),
        },
        "strategy_context": strategy or {},
    }
    atomic_write_json(ecology_dir / f"generation_{generation:02d}_ecology.json", snapshot)
    write_species_registry(results_dir, species_summary, script=f"generation_{generation:02d}")
    atomic_write_json(ecology_dir / "niche_map.json", niche_map)

    status = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "mode": "observer_speciation_foundation",
        "active": True,
        "influences_evolution": False,
        "generation": generation,
        "score_mode": score_mode,
        "observer_count": species_summary.get("observer_count", 0),
        "species_count": species_summary.get("species_count", 0),
        "dominant_species": species_summary.get("dominant_species"),
        "species_names": [s.get("species") for s in species_summary.get("species", [])],
        "valid_worlds": result_summary.get("valid_worlds", 0),
        "top_score": result_summary.get("top_score", 0.0),
        "speciation_candidates": len(speciation_events),
        "strongest_speciation": speciation_events[0] if speciation_events else None,
        "species_tree_nodes": species_tree.get("node_count", 0),
        "species_tree_edges": species_tree.get("edge_count", 0),
        "lineage_history_count": lineage.get("history_count", 0),
        "files": {
            "species_registry": str(ecology_dir / "species_registry.json"),
            "niche_map": str(ecology_dir / "niche_map.json"),
            "lineage_tree": str(ecology_dir / "lineage_tree.json"),
            "species_tree": str(ecology_dir / "species_tree.json"),
            "speciation_events": str(ecology_dir / "speciation_events.json"),
            "generation_snapshot": str(ecology_dir / f"generation_{generation:02d}_ecology.json"),
        },
    }
    atomic_write_json(ecology_dir / "ecology_status.json", status)
    atomic_write_json(Path(results_dir) / "observer_ecology_status.json", status)

    if strategy:
        atomic_write_json(strategy_dir / f"generation_{generation:02d}_strategy_context.json", strategy)
    return status


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    names = status.get("species_names") or []
    names_s = ",".join(str(x) for x in names[:4]) if names else "-"
    strongest = status.get("strongest_speciation") or {}
    branch = "-"
    if isinstance(strongest, dict) and strongest.get("child_species"):
        branch = f"{strongest.get('parent_species')}->{strongest.get('child_species')}:{safe_float(strongest.get('score'),0):.2f}"
    print(
        f"[{prefix}] {ECOLOGY_VERSION} | active={status.get('active')} "
        f"safe={status.get('compatibility', {}).get('writes_only_new_namespace', True)} "
        f"species={status.get('species_count', 0)} observers={status.get('observer_count', 0)} "
        f"dominant={status.get('dominant_species') or '-'} candidates={status.get('speciation_candidates', 0)} "
        f"tree={status.get('species_tree_nodes', 0)}/{status.get('species_tree_edges', 0)} branch={branch} registry={names_s}"
    )


# ---------------------------------------------------------------------------
# v25.3 Ecological Selection layer
# ---------------------------------------------------------------------------
# These definitions override v25.2 generation handling with a conservative,
# folder-safe selection pressure. It does not rename/move legacy files. It only
# annotates/reorders observer_population and writes extra state under
# observer_ecology/ plus a root mirror ecological_selection_status.json.

ECOLOGY_VERSION = "v25.3 Ecological Selection"


def _normalize_score(score: Any) -> float:
    v = safe_float(score, 0.0)
    # Old Search scores can be large. Keep useful ordering while clamping.
    if v <= 0:
        return 0.0
    return max(0.0, min(1.0, v / 140.0))


def _observer_species_map(observer_population: Optional[Iterable[Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for i, raw in enumerate(observer_population or []):
        if not isinstance(raw, dict):
            continue
        oid = str(raw.get("id", raw.get("observer_id", raw.get("name", f"observer_{i:04d}"))))
        sp, _, _ = infer_species(raw)
        out[oid] = sp
    return out


def _result_species_scores(observer_population: Optional[Iterable[Any]], clean_results: Optional[List[Any]]) -> Dict[str, Dict[str, Any]]:
    oid_to_species = _observer_species_map(observer_population)
    buckets: Dict[str, Dict[str, Any]] = {}
    for item in clean_results or []:
        try:
            score, _rule, metrics = item
        except Exception:
            continue
        if not isinstance(metrics, dict):
            continue
        oid = str(metrics.get("observer_id", ""))
        sp = oid_to_species.get(oid)
        if not sp:
            # Fallback through archetype text.
            sp, _, _ = infer_species({"archetype": metrics.get("observer_archetype"), "metrics": list(metrics.keys())})
        b = buckets.setdefault(sp, {"species": sp, "scores": [], "hits": 0, "best_score": 0.0})
        ns = _normalize_score(score)
        b["scores"].append(ns)
        b["hits"] += 1
        b["best_score"] = max(safe_float(b.get("best_score"), 0.0), ns)
    for sp, b in buckets.items():
        vals = b.get("scores") or []
        b["mean_score"] = round(sum(vals) / max(1, len(vals)), 6)
        b["best_score"] = round(safe_float(b.get("best_score"), 0.0), 6)
    return buckets


def _load_selection_state(results_dir: Path) -> Dict[str, Any]:
    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    state = read_json(ecology_dir / "ecological_selection_state.json", {}) or {}
    return state if isinstance(state, dict) else {}


def _ecological_species_selection(
    results_dir: Path,
    generation: int,
    score_mode: str,
    observer_population: Optional[Iterable[Any]],
    clean_results: Optional[List[Any]],
    strategy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute species-level pressure and save it.

    This is the ecological selection *state*. It is deliberately conservative:
    it measures and annotates selection pressure, while actual mutation/crossover
    is still delegated to the old observer evolution code.
    """
    ensure_ecology_dirs(results_dir)
    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    strategy_dir = Path(results_dir) / STRATEGY_LOGS_DIR

    species_summary = summarize_observer_population(observer_population)
    result_summary = summarize_results(clean_results)
    speciation_events = infer_speciation_events(results_dir, species_summary, result_summary, generation=generation)
    species_tree = update_species_tree(results_dir, species_summary, speciation_events, generation=generation)
    niche_map = build_niche_map(species_summary, result_summary)
    lineage = update_lineage_tree(results_dir, species_summary, generation=generation)
    result_scores = _result_species_scores(observer_population, clean_results)
    prev = _load_selection_state(results_dir)
    prev_species = prev.get("species") if isinstance(prev.get("species"), dict) else {}

    rows: List[Dict[str, Any]] = []
    total_obs = max(1, safe_int(species_summary.get("observer_count"), 0))
    for sp in species_summary.get("species", []) or []:
        name = str(sp.get("species") or DEFAULT_SPECIES)
        count = safe_int(sp.get("count"), 0)
        registry_fit = safe_float(sp.get("avg_fitness", sp.get("max_fitness", 0.0)), 0.0)
        # observer fitness can already be in arbitrary old scale; normalize softly.
        registry_norm = max(0.0, min(1.0, registry_fit if registry_fit <= 1.0 else registry_fit / 100.0))
        rb = result_scores.get(name, {})
        result_fit = 0.65 * safe_float(rb.get("mean_score"), 0.0) + 0.35 * safe_float(rb.get("best_score"), 0.0)
        evidence_hits = safe_int(rb.get("hits"), 0)
        abundance = count / total_obs
        ecological_fitness = round(max(0.0, min(1.0, 0.42 * registry_norm + 0.43 * result_fit + 0.15 * min(1.0, evidence_hits / max(1, len(clean_results or []))))), 6)
        old = prev_species.get(name, {}) if isinstance(prev_species, dict) else {}
        weak_streak = safe_int(old.get("weak_streak"), 0)
        strong_streak = safe_int(old.get("strong_streak"), 0)
        if ecological_fitness < 0.22:
            weak_streak += 1
            strong_streak = 0
        elif ecological_fitness >= 0.58:
            strong_streak += 1
            weak_streak = 0
        else:
            weak_streak = max(0, weak_streak - 1)
            strong_streak = max(0, strong_streak - 1)
        # Suggested population share, not a hard rewrite yet.
        desired_share = max(0.05, min(0.55, 0.15 + ecological_fitness * 0.55 + abundance * 0.30))
        desired_count = max(1, int(round(desired_share * total_obs)))
        extinction_risk = round(max(0.0, min(1.0, 0.70 * (1.0 - ecological_fitness) + 0.20 * min(1.0, weak_streak / 4.0) + 0.10 * (1.0 - min(1.0, count / 3.0)))), 6)
        status = "ACTIVE"
        if weak_streak >= 4 and count <= 1:
            status = "EXTINCT_RISK"
        elif weak_streak >= 2:
            status = "DECLINING"
        elif strong_streak >= 2:
            status = "EXPANDING"
        rows.append({
            "species": name,
            "niche": sp.get("niche"),
            "population": count,
            "previous_population": safe_int(old.get("population"), count),
            "desired_population": desired_count,
            "population_delta_target": desired_count - count,
            "registry_fitness": round(registry_norm, 6),
            "result_fitness": round(result_fit, 6),
            "ecological_fitness": ecological_fitness,
            "evidence_hits": evidence_hits,
            "weak_streak": weak_streak,
            "strong_streak": strong_streak,
            "extinction_risk": extinction_risk,
            "status": status,
        })

    rows.sort(key=lambda x: (x.get("ecological_fitness", 0), -x.get("extinction_risk", 0), x.get("population", 0)), reverse=True)
    dominant = rows[0]["species"] if rows else species_summary.get("dominant_species")
    strongest = rows[0] if rows else None
    weakest = sorted(rows, key=lambda x: (x.get("extinction_risk", 0), -x.get("ecological_fitness", 0)), reverse=True)[0] if rows else None
    next_state = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "generation": generation,
        "score_mode": score_mode,
        "species": {r["species"]: r for r in rows},
    }
    atomic_write_json(ecology_dir / "ecological_selection_state.json", next_state)

    report = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "generation": generation,
        "score_mode": score_mode,
        "influences_evolution": True,
        "mode": "ecological_selection",
        "species_count": species_summary.get("species_count", 0),
        "observer_count": species_summary.get("observer_count", 0),
        "dominant_species": dominant,
        "strongest_species": strongest,
        "highest_extinction_risk": weakest,
        "species_dynamics": rows,
        "result_summary": result_summary,
        "speciation_events": speciation_events,
        "species_tree_summary": {"nodes": species_tree.get("node_count", 0), "edges": species_tree.get("edge_count", 0), "events": species_tree.get("event_count", 0)},
        "lineage_history_count": lineage.get("history_count", 0),
        "strategy_context": strategy or {},
        "compatibility": {"renames_existing_files": False, "moves_existing_files": False, "writes_only_new_namespace": True},
    }

    atomic_write_json(ecology_dir / f"generation_{generation:02d}_ecological_selection.json", report)
    atomic_write_json(ecology_dir / "ecological_selection_status.json", report)
    atomic_write_json(Path(results_dir) / "ecological_selection_status.json", report)
    atomic_write_json(ecology_dir / "niche_map.json", niche_map)
    write_species_registry(results_dir, species_summary, script=f"ecological_selection_generation_{generation:02d}")
    if strategy:
        atomic_write_json(strategy_dir / f"generation_{generation:02d}_ecological_selection_context.json", strategy)
    return report


def apply_ecological_selection(
    results_dir: Path,
    generation: int,
    score_mode: str,
    observer_population: Optional[Iterable[Any]],
    clean_results: Optional[List[Any]],
    strategy: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Annotate and rank observer_population by species ecological pressure.

    This is intentionally low-risk: no legacy files are renamed, no observers are
    destructively deleted. But order + annotations now reflect ecology, so the next
    observer evolution round sees a pressure gradient instead of a flat pool.
    """
    report = _ecological_species_selection(results_dir, generation, score_mode, observer_population, clean_results, strategy)
    weights = {str(r.get("species")): r for r in report.get("species_dynamics", []) if isinstance(r, dict)}
    new_pop: List[Dict[str, Any]] = []
    for i, raw in enumerate(observer_population or []):
        if isinstance(raw, dict):
            obs = dict(raw)
        else:
            obs = {"raw_type": type(raw).__name__}
        sp, niche, reason = infer_species(obs)
        row = weights.get(sp, {})
        eco_fit = safe_float(row.get("ecological_fitness"), 0.0)
        risk = safe_float(row.get("extinction_risk"), 0.0)
        base_fit = safe_float(obs.get("fitness", obs.get("score", obs.get("observer_score", 0.0))), 0.0)
        base_norm = max(0.0, min(1.0, base_fit if base_fit <= 1.0 else base_fit / 100.0))
        selection_weight = round(max(0.0, 0.60 * eco_fit + 0.25 * base_norm + 0.15 * (1.0 - risk)), 6)
        obs["species"] = sp
        obs["species_id"] = sp
        obs["niche"] = niche
        obs["species_classification_reason"] = reason
        obs["ecology_generation"] = generation
        obs["ecological_fitness"] = eco_fit
        obs["ecology_selection_weight"] = selection_weight
        obs["extinction_risk"] = risk
        obs["species_status"] = row.get("status", "ACTIVE")
        new_pop.append(obs)
    # Rank by ecology but preserve diversity by limiting consecutive same-species blocks.
    new_pop.sort(key=lambda o: (safe_float(o.get("ecology_selection_weight"), 0.0), safe_float(o.get("fitness", 0.0))), reverse=True)
    # Simple diversity weave: first pass take best of each species, then fill rest.
    by_sp: Dict[str, List[Dict[str, Any]]] = {}
    for obs in new_pop:
        by_sp.setdefault(str(obs.get("species", DEFAULT_SPECIES)), []).append(obs)
    woven: List[Dict[str, Any]] = []
    while len(woven) < len(new_pop):
        progressed = False
        for sp in sorted(by_sp.keys(), key=lambda k: safe_float(weights.get(k, {}).get("ecological_fitness"), 0.0), reverse=True):
            bucket = by_sp.get(sp) or []
            if bucket:
                woven.append(bucket.pop(0)); progressed = True
                if len(woven) >= len(new_pop):
                    break
        if not progressed:
            break
    return woven or new_pop, report


# Override v25.2 record_generation_ecology to include ecological selection files.
def record_generation_ecology(
    results_dir: Path,
    generation: int,
    score_mode: str,
    observer_population: Optional[Iterable[Any]],
    clean_results: Optional[List[Any]],
    strategy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_ecology_dirs(results_dir)
    ecology_dir = Path(results_dir) / OBSERVER_ECOLOGY_DIR
    species_summary = summarize_observer_population(observer_population)
    result_summary = summarize_results(clean_results)
    speciation_events = infer_speciation_events(results_dir, species_summary, result_summary, generation=generation)
    species_tree = update_species_tree(results_dir, species_summary, speciation_events, generation=generation)
    niche_map = build_niche_map(species_summary, result_summary)
    lineage = update_lineage_tree(results_dir, species_summary, generation=generation)
    selection_report = _ecological_species_selection(results_dir, generation, score_mode, observer_population, clean_results, strategy)

    snapshot = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "generation": generation,
        "score_mode": score_mode,
        "influences_evolution": True,
        "species_summary": species_summary,
        "result_summary": result_summary,
        "speciation_events": speciation_events,
        "ecological_selection": {
            "dominant_species": selection_report.get("dominant_species"),
            "strongest_species": selection_report.get("strongest_species"),
            "highest_extinction_risk": selection_report.get("highest_extinction_risk"),
        },
        "species_tree_summary": {"nodes": species_tree.get("node_count", 0), "edges": species_tree.get("edge_count", 0), "events": species_tree.get("event_count", 0)},
        "strategy_context": strategy or {},
    }
    atomic_write_json(ecology_dir / f"generation_{generation:02d}_ecology.json", snapshot)
    write_species_registry(results_dir, species_summary, script=f"generation_{generation:02d}")
    atomic_write_json(ecology_dir / "niche_map.json", niche_map)

    strong = selection_report.get("strongest_species") or {}
    weak = selection_report.get("highest_extinction_risk") or {}
    status = {
        "version": ECOLOGY_VERSION,
        "updated_at": now_s(),
        "mode": "ecological_selection",
        "active": True,
        "influences_evolution": True,
        "generation": generation,
        "score_mode": score_mode,
        "observer_count": species_summary.get("observer_count", 0),
        "species_count": species_summary.get("species_count", 0),
        "dominant_species": selection_report.get("dominant_species") or species_summary.get("dominant_species"),
        "strongest_species": strong.get("species"),
        "strongest_fitness": strong.get("ecological_fitness"),
        "highest_extinction_risk_species": weak.get("species"),
        "highest_extinction_risk": weak.get("extinction_risk"),
        "species_names": [s.get("species") for s in species_summary.get("species", [])],
        "valid_worlds": result_summary.get("valid_worlds", 0),
        "top_score": result_summary.get("top_score", 0.0),
        "speciation_candidates": len(speciation_events),
        "strongest_speciation": speciation_events[0] if speciation_events else None,
        "species_tree_nodes": species_tree.get("node_count", 0),
        "species_tree_edges": species_tree.get("edge_count", 0),
        "lineage_history_count": lineage.get("history_count", 0),
        "compatibility": {"renames_existing_files": False, "moves_existing_files": False, "writes_only_new_namespace": True},
        "files": {
            "species_registry": str(ecology_dir / "species_registry.json"),
            "niche_map": str(ecology_dir / "niche_map.json"),
            "lineage_tree": str(ecology_dir / "lineage_tree.json"),
            "species_tree": str(ecology_dir / "species_tree.json"),
            "speciation_events": str(ecology_dir / "speciation_events.json"),
            "ecological_selection": str(ecology_dir / "ecological_selection_status.json"),
            "generation_snapshot": str(ecology_dir / f"generation_{generation:02d}_ecology.json"),
        },
    }
    atomic_write_json(ecology_dir / "ecology_status.json", status)
    atomic_write_json(Path(results_dir) / "observer_ecology_status.json", status)
    return status


def print_status(prefix: str, status: Dict[str, Any]) -> None:
    names = status.get("species_names") or []
    names_s = ",".join(str(x) for x in names[:4]) if names else "-"
    strongest = status.get("strongest_speciation") or {}
    branch = "-"
    if isinstance(strongest, dict) and strongest.get("child_species"):
        branch = f"{strongest.get('parent_species')}->{strongest.get('child_species')}:{safe_float(strongest.get('score'),0):.2f}"
    strongest_species = status.get("strongest_species") or status.get("dominant_species") or "-"
    weak = status.get("highest_extinction_risk_species") or "-"
    print(
        f"[{prefix}] {ECOLOGY_VERSION} | active={status.get('active')} "
        f"influence={status.get('influences_evolution', False)} safe={status.get('compatibility', {}).get('writes_only_new_namespace', True)} "
        f"species={status.get('species_count', 0)} observers={status.get('observer_count', 0)} "
        f"dominant={status.get('dominant_species') or '-'} strongest={strongest_species} weak={weak} "
        f"candidates={status.get('speciation_candidates', 0)} tree={status.get('species_tree_nodes', 0)}/{status.get('species_tree_edges', 0)} "
        f"branch={branch} registry={names_s}"
    )
