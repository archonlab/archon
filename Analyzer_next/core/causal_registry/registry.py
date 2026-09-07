"""Pure scientific logic for the atomic causal-mechanism registry."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

ATOMIC_FAMILY_MOTIF_LENGTH = 2

ATOMIC_LABELS = {
    "Collapse -> Recovery": "POST_COLLAPSE_RECOVERY",
    "Recovery -> Collapse": "UNSTABLE_GROWTH_COLLAPSE",
    "Collapse -> Collapse": "CASCADED_COLLAPSE",
    "Recovery -> Dormancy": "SETTLING_AFTER_RECOVERY",
    "Dormancy -> Recovery": "DORMANCY_REACTIVATION",
    "Dormancy -> Collapse": "DORMANCY_DECAY",
    "Collapse -> Dormancy": "POST_COLLAPSE_DORMANCY",
    "Recovery -> Recovery": "SUSTAINED_RECOVERY",
    "Dormancy -> Dormancy": "SUSTAINED_DORMANCY",
}

COMPOSITION_LABELS = {
    "Collapse -> Recovery -> Collapse": "FAILED_RECOVERY_LOOP",
    "Recovery -> Collapse -> Recovery": "OSCILLATING_RECOVERY",
    "Collapse -> Recovery -> Dormancy": "POST_COLLAPSE_RECOVERY_SETTLING",
    "Collapse -> Collapse -> Recovery": "CASCADED_COLLAPSE_RECOVERY",
    "Recovery -> Dormancy -> Recovery": "DORMANT_RECOVERY_LOOP",
    "Dormancy -> Collapse -> Recovery": "DORMANT_COLLAPSE_RECOVERY",
    "Recovery -> Collapse -> Dormancy": "GROWTH_COLLAPSE_SETTLING",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", text.strip().upper())
    return re.sub(r"_+", "_", text).strip("_") or "UNKNOWN"


def family_parts(family_text: str) -> List[str]:
    return [p.strip() for p in str(family_text).split(" -> ") if p.strip()]


def family_text(parts: List[str]) -> str:
    return " -> ".join(parts)


def atomic_windows(parts: List[str]) -> List[str]:
    return [family_text(parts[i:i + 2]) for i in range(len(parts) - 1)]


def atomic_label(family_motif_text: str) -> str:
    return ATOMIC_LABELS.get(family_motif_text, "ATOMIC_" + slugify(family_motif_text))


def composition_label(family_motif_text: str) -> str:
    return COMPOSITION_LABELS.get(family_motif_text, "COMPOSITE_" + slugify(family_motif_text))


def classify_atomic(parts: List[str]) -> Dict[str, Any]:
    text = family_text(parts)
    has_collapse = "Collapse" in parts
    has_recovery = "Recovery" in parts
    has_dormancy = "Dormancy" in parts

    if text == "Collapse -> Recovery":
        category = "recovery"
    elif text == "Recovery -> Collapse":
        category = "instability"
    elif text == "Collapse -> Collapse":
        category = "collapse_recurrence"
    elif text == "Recovery -> Dormancy":
        category = "dormancy_recovery"
    elif text == "Dormancy -> Recovery":
        category = "dormancy_recovery"
    elif text == "Dormancy -> Collapse":
        category = "dormancy_decay"
    elif text == "Collapse -> Dormancy":
        category = "dormancy_decay"
    elif text == "Recovery -> Recovery":
        category = "growth_recovery"
    elif has_collapse:
        category = "collapse"
    elif has_recovery:
        category = "recovery"
    elif has_dormancy:
        category = "dormancy"
    else:
        category = "mixed"

    return {
        "family_motif_text": text,
        "category": category,
        "has_collapse": has_collapse,
        "has_recovery": has_recovery,
        "has_dormancy": has_dormancy,
        "is_atomic": True,
    }


def classify_composition(parts: List[str]) -> Dict[str, Any]:
    text = family_text(parts)
    windows = atomic_windows(parts)
    categories = Counter(classify_atomic(family_parts(w))["category"] for w in windows)

    has_collapse = "Collapse" in parts
    has_recovery = "Recovery" in parts
    has_dormancy = "Dormancy" in parts

    is_cycle = False
    for i, item in enumerate(parts):
        if item in parts[:i]:
            prev = parts[:i].index(item)
            middle = parts[prev + 1:i]
            if middle and any(x != item for x in middle):
                is_cycle = True

    is_repetition = len(parts) >= 2 and len(set(parts)) == 1

    if "collapse_recurrence" in categories:
        category = "collapse_recurrence"
    elif is_cycle and has_collapse and has_recovery:
        category = "recovery_cycle"
    elif has_collapse and has_recovery and has_dormancy:
        category = "dormancy_recovery"
    elif has_collapse and has_recovery:
        category = "recovery_instability"
    elif has_dormancy and has_recovery:
        category = "dormancy_recovery"
    elif has_dormancy and has_collapse:
        category = "dormancy_decay"
    elif has_recovery:
        category = "recovery"
    elif has_collapse:
        category = "collapse"
    else:
        category = "mixed"

    return {
        "family_motif_text": text,
        "category": category,
        "has_collapse": has_collapse,
        "has_recovery": has_recovery,
        "has_dormancy": has_dormancy,
        "is_true_cycle": is_cycle,
        "is_repetition": is_repetition,
        "atomic_windows": windows,
    }


def collect_family_records(sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = []

    mech = sources.get("mechanisms", {})
    for key, item in mech.get("global_motifs", {}).get("family_motifs", {}).items():
        family = item.get("family_motif_text", key)
        records.append({
            "source": "causal_mechanisms.global_family_motifs",
            "family_motif_text": family,
            "family_motif": item.get("family_motif", family_parts(family)),
            "event_variants": item.get("event_variants", {}),
            "rules": [str(r) for r in item.get("rules", [])],
            "rule_counts": {str(k): int(v) for k, v in item.get("rule_counts", {}).items()},
            "count": int(item.get("count", 1)),
            "confidence": safe_float(item.get("confidence"), 0.0),
            "mean_duration_ticks": safe_float(item.get("mean_duration_ticks"), 0.0),
            "examples": item.get("examples", [])[:8],
        })

    motifs = sources.get("motifs", {})
    for key, item in motifs.get("global_motifs", {}).get("event_motifs", {}).items():
        family = item.get("family_motif_text")
        if not family:
            continue
        records.append({
            "source": "causal_motifs.global_event_motifs",
            "family_motif_text": family,
            "family_motif": item.get("family_motif", family_parts(family)),
            "event_variants": {item.get("motif_text", key): int(item.get("count", 1))},
            "rules": [str(r) for r in item.get("rules", [])],
            "rule_counts": {str(k): int(v) for k, v in item.get("rule_counts", {}).items()},
            "count": int(item.get("count", 1)),
            "confidence": safe_float(item.get("confidence"), 0.0),
            "mean_duration_ticks": safe_float(item.get("mean_duration_ticks"), 0.0),
            "examples": item.get("examples", [])[:8],
        })

    return records


def build_atomic_registry(records: List[Dict[str, Any]], results_dir: Path) -> Dict[str, Any]:
    atomic = defaultdict(lambda: {
        "family_motif_text": "",
        "family_motif": [],
        "event_variants": Counter(),
        "rules": set(),
        "rule_counts": Counter(),
        "counts": [],
        "confidences": [],
        "durations": [],
        "examples": [],
        "source_family_motifs": Counter(),
    })

    composition_candidates = []

    for rec in records:
        parts = rec.get("family_motif") or family_parts(rec["family_motif_text"])
        if len(parts) < 2:
            continue

        if len(parts) == ATOMIC_FAMILY_MOTIF_LENGTH:
            windows = [family_text(parts)]
        else:
            windows = atomic_windows(parts)
            composition_candidates.append(rec)

        for win in windows:
            a = atomic[win]
            a["family_motif_text"] = win
            a["family_motif"] = family_parts(win)
            a["source_family_motifs"][rec["family_motif_text"]] += rec["count"]

            for variant, count in rec.get("event_variants", {}).items():
                # Only attach exact variant to matching length-2 source,
                # otherwise keep it as evidence/source only.
                if len(parts) == 2:
                    a["event_variants"][variant] += int(count)

            for rule in rec.get("rules", []):
                a["rules"].add(str(rule))

            for rule, count in rec.get("rule_counts", {}).items():
                # For decomposed long motifs, count as evidence but avoid huge inflation.
                a["rule_counts"][str(rule)] += max(1, int(count)) if len(parts) == 2 else 1

            a["counts"].append(rec.get("count", 1) if len(parts) == 2 else 1)
            a["confidences"].append(rec.get("confidence", 0.0))
            a["durations"].append(rec.get("mean_duration_ticks", 0.0))
            a["examples"].extend(rec.get("examples", [])[:4])

    ordered = []
    for win, a in atomic.items():
        ordered.append((
            win,
            len(a["rules"]),
            sum(a["counts"]),
            mean(a["confidences"]),
        ))
    ordered.sort(key=lambda x: (x[1], x[2], x[3], x[0]), reverse=True)

    registry = {}
    family_to_id = {}
    for idx, (win, _rc, _ct, _cf) in enumerate(ordered, start=1):
        parts = family_parts(win)
        label = atomic_label(win)
        mech_id = f"AMECH-{idx:03d}-{slugify(label)[:36]}"
        family_to_id[win] = mech_id
        a = atomic[win]
        classification = classify_atomic(parts)

        source_count = sum(a["counts"])
        rule_count = len(a["rules"])
        mean_conf = mean(a["confidences"])
        mean_duration = mean(a["durations"])
        duration_stdev = stdev(a["durations"])
        variant_count = len(a["event_variants"])

        support_score = min(1.0, rule_count / 4.0)
        count_score = min(1.0, source_count / 8.0)
        confidence_score = mean_conf
        variant_score = min(1.0, max(1, variant_count) / 3.0)
        timing_stability = 1.0 - min(1.0, duration_stdev / max(1.0, mean_duration)) if len(a["durations"]) >= 2 else 0.5

        registry[mech_id] = {
            "mechanism_id": mech_id,
            "mechanism_kind": "atomic",
            "label": label,
            "family_motif": parts,
            "family_motif_text": win,
            "category": classification["category"],
            "classification": classification,
            "support": {
                "count": source_count,
                "rules": sorted(a["rules"]),
                "rule_count": rule_count,
                "rule_counts": dict(a["rule_counts"]),
                "event_variant_count": variant_count,
                "event_variants": [
                    {"event_motif_text": k, "count": v}
                    for k, v in a["event_variants"].most_common()
                ],
                "source_family_motif_count": len(a["source_family_motifs"]),
                "source_family_motifs": [
                    {"family_motif_text": k, "count": v}
                    for k, v in a["source_family_motifs"].most_common()
                ],
            },
            "timing": {
                "mean_duration_ticks": mean_duration,
                "duration_stdev_ticks": duration_stdev,
            },
            "scores": {
                "support_score": support_score,
                "count_score": count_score,
                "source_confidence_mean": confidence_score,
                "variant_score": variant_score,
                "timing_stability_score": timing_stability,
                "registry_confidence": clamp01(
                    0.34 * support_score +
                    0.24 * count_score +
                    0.18 * confidence_score +
                    0.12 * variant_score +
                    0.12 * timing_stability
                ),
            },
            "examples": a["examples"][:10],
        }

    return {
        "schema": "universe_search_atomic_mechanism_registry_v11",
        "results_dir": str(results_dir),
        "mechanism_count": len(registry),
        "family_to_mechanism_id": family_to_id,
        "mechanisms": registry,
    }


def build_composition_registry(records: List[Dict[str, Any]], atomic_registry: Dict[str, Any], results_dir: Path) -> Dict[str, Any]:
    family_to_id = atomic_registry["family_to_mechanism_id"]
    compositions = defaultdict(lambda: {
        "family_motif_text": "",
        "family_motif": [],
        "rules": set(),
        "rule_counts": Counter(),
        "counts": [],
        "confidences": [],
        "durations": [],
        "examples": [],
        "event_variants": Counter(),
    })

    for rec in records:
        parts = rec.get("family_motif") or family_parts(rec["family_motif_text"])
        if len(parts) <= 2:
            continue
        ftxt = family_text(parts)
        c = compositions[ftxt]
        c["family_motif_text"] = ftxt
        c["family_motif"] = parts
        for rule in rec.get("rules", []):
            c["rules"].add(str(rule))
        for rule, count in rec.get("rule_counts", {}).items():
            c["rule_counts"][str(rule)] += int(count)
        for variant, count in rec.get("event_variants", {}).items():
            c["event_variants"][variant] += int(count)
        c["counts"].append(int(rec.get("count", 1)))
        c["confidences"].append(safe_float(rec.get("confidence"), 0.0))
        c["durations"].append(safe_float(rec.get("mean_duration_ticks"), 0.0))
        c["examples"].extend(rec.get("examples", [])[:5])

    ordered = []
    for ftxt, c in compositions.items():
        ordered.append((ftxt, len(c["rules"]), sum(c["counts"]), mean(c["confidences"])))
    ordered.sort(key=lambda x: (x[1], x[2], x[3], x[0]), reverse=True)

    registry = {}
    family_to_composition_id = {}

    for idx, (ftxt, _rc, _ct, _cf) in enumerate(ordered, start=1):
        c = compositions[ftxt]
        parts = c["family_motif"]
        comp_label = composition_label(ftxt)
        comp_id = f"COMP-{idx:03d}-{slugify(comp_label)[:36]}"
        family_to_composition_id[ftxt] = comp_id

        windows = atomic_windows(parts)
        atomic_ids = [family_to_id[w] for w in windows if w in family_to_id]
        missing_windows = [w for w in windows if w not in family_to_id]

        classification = classify_composition(parts)

        source_count = sum(c["counts"])
        rule_count = len(c["rules"])
        mean_conf = mean(c["confidences"])
        mean_duration = mean(c["durations"])
        duration_stdev = stdev(c["durations"])

        support_score = min(1.0, rule_count / 3.0)
        count_score = min(1.0, source_count / 4.0)
        confidence_score = mean_conf
        decomposition_score = 1.0 if not missing_windows else max(0.0, len(atomic_ids) / max(1, len(windows)))
        timing_stability = 1.0 - min(1.0, duration_stdev / max(1.0, mean_duration)) if len(c["durations"]) >= 2 else 0.5

        registry[comp_id] = {
            "composition_id": comp_id,
            "mechanism_kind": "composition",
            "label": comp_label,
            "family_motif": parts,
            "family_motif_text": ftxt,
            "category": classification["category"],
            "classification": classification,
            "atomic_mechanism_ids": atomic_ids,
            "atomic_family_windows": windows,
            "missing_atomic_windows": missing_windows,
            "support": {
                "count": source_count,
                "rules": sorted(c["rules"]),
                "rule_count": rule_count,
                "rule_counts": dict(c["rule_counts"]),
                "event_variant_count": len(c["event_variants"]),
                "event_variants": [
                    {"event_motif_text": k, "count": v}
                    for k, v in c["event_variants"].most_common()
                ],
            },
            "timing": {
                "mean_duration_ticks": mean_duration,
                "duration_stdev_ticks": duration_stdev,
            },
            "scores": {
                "support_score": support_score,
                "count_score": count_score,
                "source_confidence_mean": confidence_score,
                "decomposition_score": decomposition_score,
                "timing_stability_score": timing_stability,
                "composition_confidence": clamp01(
                    0.25 * support_score +
                    0.20 * count_score +
                    0.18 * confidence_score +
                    0.25 * decomposition_score +
                    0.12 * timing_stability
                ),
            },
            "examples": c["examples"][:10],
        }

    return {
        "schema": "universe_search_mechanism_composition_registry_v11",
        "results_dir": str(results_dir),
        "composition_count": len(registry),
        "family_to_composition_id": family_to_composition_id,
        "compositions": registry,
    }


def build_rule_mechanism_map(sources: Dict[str, Any], atomic_registry: Dict[str, Any], composition_registry: Dict[str, Any], results_dir: Path) -> Dict[str, Any]:
    family_to_atomic = atomic_registry["family_to_mechanism_id"]
    family_to_comp = composition_registry["family_to_composition_id"]

    rule_map = defaultdict(lambda: {
        "rule_id": "",
        "event_signature": "NONE",
        "family_signature": "NONE",
        "atomic_counts": Counter(),
        "composition_counts": Counter(),
        "motif_links": [],
    })

    # Use causal_mechanisms rule_mechanisms first.
    mech = sources.get("mechanisms", {})
    for rid, item in mech.get("rule_mechanisms", {}).items():
        rid = str(rid)
        rm = rule_map[rid]
        rm["rule_id"] = rid
        rm["family_signature"] = item.get("compact_family_sequence_text", rm["family_signature"])

        for _key, motif in item.get("family_motifs", {}).items():
            ftxt = motif.get("family_motif_text")
            parts = family_parts(ftxt)
            count = int(motif.get("count", 1))
            if len(parts) == 2:
                aid = family_to_atomic.get(ftxt)
                if aid:
                    rm["atomic_counts"][aid] += count
                    rm["motif_links"].append({
                        "kind": "atomic",
                        "family_motif_text": ftxt,
                        "mechanism_id": aid,
                        "count": count,
                    })
            elif len(parts) > 2:
                cid = family_to_comp.get(ftxt)
                if cid:
                    rm["composition_counts"][cid] += count
                    rm["motif_links"].append({
                        "kind": "composition",
                        "family_motif_text": ftxt,
                        "composition_id": cid,
                        "count": count,
                    })
                # Also count atomic windows once per composition occurrence.
                for win in atomic_windows(parts):
                    aid = family_to_atomic.get(win)
                    if aid:
                        rm["atomic_counts"][aid] += count

    # If no rule mechanisms, use causal_motifs rule_motifs.
    motifs_src = sources.get("motifs", {})
    if not mech.get("rule_mechanisms"):
        for rid, item in motifs_src.get("rule_motifs", {}).items():
            rid = str(rid)
            rm = rule_map[rid]
            rm["rule_id"] = rid
            rm["event_signature"] = item.get("compact_sequence_text", rm["event_signature"])
            for _key, motif in item.get("motifs", {}).items():
                ftxt = motif.get("family_motif_text")
                parts = family_parts(ftxt)
                count = int(motif.get("count", 1))
                if len(parts) == 2:
                    aid = family_to_atomic.get(ftxt)
                    if aid:
                        rm["atomic_counts"][aid] += count
                elif len(parts) > 2:
                    cid = family_to_comp.get(ftxt)
                    if cid:
                        rm["composition_counts"][cid] += count
                    for win in atomic_windows(parts):
                        aid = family_to_atomic.get(win)
                        if aid:
                            rm["atomic_counts"][aid] += count

    final = {}
    for rid, rm in sorted(rule_map.items()):
        atomic_list = [
            {
                "mechanism_id": mid,
                "label": atomic_registry["mechanisms"][mid]["label"],
                "category": atomic_registry["mechanisms"][mid]["category"],
                "count": count,
            }
            for mid, count in rm["atomic_counts"].most_common()
        ]
        comp_list = [
            {
                "composition_id": cid,
                "label": composition_registry["compositions"][cid]["label"],
                "category": composition_registry["compositions"][cid]["category"],
                "count": count,
                "atomic_mechanism_ids": composition_registry["compositions"][cid]["atomic_mechanism_ids"],
            }
            for cid, count in rm["composition_counts"].most_common()
        ]

        cat_counter = Counter()
        for item in atomic_list:
            cat_counter[item["category"]] += item["count"]
        dominant = cat_counter.most_common(1)[0][0] if cat_counter else "unknown"

        final[rid] = {
            "rule_id": rid,
            "event_signature": rm["event_signature"],
            "family_signature": rm["family_signature"],
            "dominant_atomic_category": dominant,
            "atomic_mechanism_diversity": len(atomic_list),
            "composition_diversity": len(comp_list),
            "atomic_mechanism_counts": atomic_list,
            "composition_counts": comp_list,
            "motif_links": rm["motif_links"],
        }

    return {
        "schema": "universe_search_rule_mechanism_map_v11_atomic",
        "results_dir": str(results_dir),
        "rule_count": len(final),
        "rules": final,
    }


def build_report(atomic_registry: Dict[str, Any], composition_registry: Dict[str, Any], rule_map: Dict[str, Any], results_dir: Path) -> Dict[str, Any]:
    atomic_mechs = list(atomic_registry["mechanisms"].values())
    comps = list(composition_registry["compositions"].values())

    atomic_categories = Counter(m["category"] for m in atomic_mechs)
    comp_categories = Counter(c["category"] for c in comps)
    rule_categories = Counter(r["dominant_atomic_category"] for r in rule_map["rules"].values())

    top_atomic = sorted(
        atomic_mechs,
        key=lambda m: (m["scores"]["registry_confidence"], m["support"]["rule_count"], m["support"]["count"]),
        reverse=True,
    )
    top_comps = sorted(
        comps,
        key=lambda c: (c["scores"]["composition_confidence"], c["support"]["rule_count"], c["support"]["count"]),
        reverse=True,
    )

    return {
        "schema": "universe_search_mechanism_report_v11_atomic",
        "results_dir": str(results_dir),
        "atomic_mechanism_count": atomic_registry["mechanism_count"],
        "composition_count": composition_registry["composition_count"],
        "rule_count": rule_map["rule_count"],
        "atomic_category_counts": dict(atomic_categories),
        "composition_category_counts": dict(comp_categories),
        "rule_dominant_atomic_category_counts": dict(rule_categories),
        "top_atomic_mechanisms": [slim_atomic(m) for m in top_atomic[:20]],
        "top_compositions": [slim_composition(c) for c in top_comps[:20]],
        "rule_summaries": {
            rid: {
                "dominant_atomic_category": r["dominant_atomic_category"],
                "atomic_mechanism_diversity": r["atomic_mechanism_diversity"],
                "composition_diversity": r["composition_diversity"],
                "family_signature": r["family_signature"],
                "top_atomic_mechanisms": r["atomic_mechanism_counts"][:6],
                "top_compositions": r["composition_counts"][:6],
            }
            for rid, r in rule_map["rules"].items()
        },
    }


def slim_atomic(m: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mechanism_id": m["mechanism_id"],
        "label": m["label"],
        "family_motif_text": m["family_motif_text"],
        "category": m["category"],
        "count": m["support"]["count"],
        "rule_count": m["support"]["rule_count"],
        "event_variant_count": m["support"]["event_variant_count"],
        "source_family_motif_count": m["support"]["source_family_motif_count"],
        "registry_confidence": m["scores"]["registry_confidence"],
    }


def slim_composition(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "composition_id": c["composition_id"],
        "label": c["label"],
        "family_motif_text": c["family_motif_text"],
        "category": c["category"],
        "count": c["support"]["count"],
        "rule_count": c["support"]["rule_count"],
        "atomic_mechanism_ids": c["atomic_mechanism_ids"],
        "composition_confidence": c["scores"]["composition_confidence"],
    }



