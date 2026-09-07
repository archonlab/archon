"""Pure composition-template inference and report assembly."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


TEMPLATE_PATTERNS = [
    {
        "template_label": "FAILED_RECOVERY_LOOP",
        "category": "recovery_cycle",
        "family_pattern": ["Collapse", "Recovery", "Collapse"],
        "atomic_pattern": ["POST_COLLAPSE_RECOVERY", "UNSTABLE_GROWTH_COLLAPSE"],
    },
    {
        "template_label": "OSCILLATING_RECOVERY",
        "category": "recovery_cycle",
        "family_pattern": ["Recovery", "Collapse", "Recovery"],
        "atomic_pattern": ["UNSTABLE_GROWTH_COLLAPSE", "POST_COLLAPSE_RECOVERY"],
    },
    {
        "template_label": "POST_COLLAPSE_RECOVERY_SETTLING",
        "category": "dormancy_recovery",
        "family_pattern": ["Collapse", "Recovery", "Dormancy"],
        "atomic_pattern": ["POST_COLLAPSE_RECOVERY", "SETTLING_AFTER_RECOVERY"],
    },
    {
        "template_label": "CASCADED_COLLAPSE_RECOVERY",
        "category": "collapse_recurrence",
        "family_pattern": ["Collapse", "Collapse", "Recovery"],
        "atomic_pattern": ["CASCADED_COLLAPSE", "POST_COLLAPSE_RECOVERY"],
    },
    {
        "template_label": "DORMANT_RECOVERY_LOOP",
        "category": "dormancy_recovery",
        "family_pattern": ["Recovery", "Dormancy", "Recovery"],
        "atomic_pattern": ["SETTLING_AFTER_RECOVERY", "DORMANCY_REACTIVATION"],
    },
    {
        "template_label": "DORMANT_COLLAPSE_RECOVERY",
        "category": "dormancy_recovery",
        "family_pattern": ["Dormancy", "Collapse", "Recovery"],
        "atomic_pattern": ["DORMANCY_DECAY", "POST_COLLAPSE_RECOVERY"],
    },
    {
        "template_label": "GROWTH_COLLAPSE_SETTLING",
        "category": "dormancy_decay",
        "family_pattern": ["Recovery", "Collapse", "Dormancy"],
        "atomic_pattern": ["UNSTABLE_GROWTH_COLLAPSE", "POST_COLLAPSE_DORMANCY"],
    },
    {
        "template_label": "DORMANCY_DECAY_CHAIN",
        "category": "dormancy_decay",
        "family_pattern": ["Dormancy", "Collapse"],
        "atomic_pattern": ["DORMANCY_DECAY"],
    },
    {
        "template_label": "SUSTAINED_RECOVERY_CHAIN",
        "category": "growth_recovery",
        "family_pattern": ["Recovery", "Recovery"],
        "atomic_pattern": ["SUSTAINED_RECOVERY"],
    },
    {
        "template_label": "CASCADED_COLLAPSE_CHAIN",
        "category": "collapse_recurrence",
        "family_pattern": ["Collapse", "Collapse"],
        "atomic_pattern": ["CASCADED_COLLAPSE"],
    },
]


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
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(text).strip().upper())
    return re.sub(r"_+", "_", text).strip("_") or "UNKNOWN"


def family_parts(text: str) -> List[str]:
    return [p.strip() for p in str(text).split(" -> ") if p.strip()]


def family_text(parts: List[str]) -> str:
    return " -> ".join(parts)


def mechanism_labels_for_ids(
    ids: List[str], mechanism_registry: Dict[str, Any]
) -> List[str]:
    out = []
    mechanisms = mechanism_registry.get("mechanisms", {})
    for mid in ids:
        out.append(mechanisms.get(mid, {}).get("label", mid))
    return out


def contains_subsequence(seq: List[str], pattern: List[str]) -> bool:
    if not pattern or len(pattern) > len(seq):
        return False
    for i in range(len(seq) - len(pattern) + 1):
        if seq[i:i + len(pattern)] == pattern:
            return True
    return False


def startswith_pattern(seq: List[str], pattern: List[str]) -> bool:
    return len(seq) >= len(pattern) and seq[:len(pattern)] == pattern


def endswith_pattern(seq: List[str], pattern: List[str]) -> bool:
    return len(seq) >= len(pattern) and seq[-len(pattern):] == pattern


def infer_template_for_composition(
    comp: Dict[str, Any], mechanism_registry: Dict[str, Any]
) -> Tuple[str, str, float, str]:
    family = comp.get("family_motif", [])
    labels = mechanism_labels_for_ids(
        comp.get("atomic_mechanism_ids", []), mechanism_registry
    )
    best = None
    for pattern in TEMPLATE_PATTERNS:
        family_pat = pattern["family_pattern"]
        atomic_pat = pattern["atomic_pattern"]
        score = 0.0
        reason = []
        if family == family_pat:
            score += 1.0
            reason.append("exact family pattern")
        elif contains_subsequence(family, family_pat):
            score += 0.72
            reason.append("contains family pattern")
        elif startswith_pattern(family, family_pat):
            score += 0.66
            reason.append("starts with family pattern")
        elif endswith_pattern(family, family_pat):
            score += 0.62
            reason.append("ends with family pattern")

        if labels == atomic_pat:
            score += 1.0
            reason.append("exact atomic pattern")
        elif contains_subsequence(labels, atomic_pat):
            score += 0.80
            reason.append("contains atomic pattern")
        elif startswith_pattern(labels, atomic_pat):
            score += 0.70
            reason.append("starts with atomic pattern")
        elif endswith_pattern(labels, atomic_pat):
            score += 0.66
            reason.append("ends with atomic pattern")

        score = score / 2.0
        if best is None or score > best[2]:
            best = (
                pattern["template_label"],
                pattern["category"],
                score,
                "; ".join(reason),
            )

    if best and best[2] >= 0.45:
        return best

    category = comp.get("category", "mixed")
    if len(family) >= 3 and family[0] == family[-1]:
        return (
            "RETURN_LOOP_" + slugify(family[0]),
            category,
            0.42,
            "fallback return loop",
        )
    if len(set(family)) == 1:
        return (
            "REPEATED_" + slugify(family[0]),
            category,
            0.40,
            "fallback repetition",
        )
    if "Collapse" in family and "Recovery" in family:
        return (
            "COLLAPSE_RECOVERY_COMPOSITE",
            category,
            0.36,
            "fallback collapse/recovery composite",
        )
    if "Dormancy" in family:
        return (
            "DORMANCY_COMPOSITE",
            category,
            0.34,
            "fallback dormancy composite",
        )
    return (
        "GENERAL_COMPOSITE",
        category,
        0.30,
        "fallback general composite",
    )


def build_templates(
    mechanism_registry: Dict[str, Any],
    composition_registry: Dict[str, Any],
    rule_map: Dict[str, Any],
    results_dir: Path,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    raw_templates = defaultdict(lambda: {
        "template_label": "",
        "category": "",
        "composition_ids": [],
        "composition_family_motifs": Counter(),
        "rules": set(),
        "rule_counts": Counter(),
        "atomic_mechanisms": Counter(),
        "atomic_sequences": Counter(),
        "counts": [],
        "confidences": [],
        "classification_scores": [],
        "examples": [],
        "reasons": Counter(),
    })
    instance_records = {}
    comp_to_template_id = {}

    for comp_id, comp in composition_registry.get("compositions", {}).items():
        label, category, cls_score, reason = infer_template_for_composition(
            comp, mechanism_registry
        )
        t = raw_templates[label]
        t["template_label"] = label
        t["category"] = category
        t["composition_ids"].append(comp_id)
        t["composition_family_motifs"][
            comp.get("family_motif_text", "")
        ] += int(comp.get("support", {}).get("count", 1))
        for rid in comp.get("support", {}).get("rules", []):
            t["rules"].add(str(rid))
        for rid, count in comp.get("support", {}).get("rule_counts", {}).items():
            t["rule_counts"][str(rid)] += int(count)
        atom_labels = mechanism_labels_for_ids(
            comp.get("atomic_mechanism_ids", []), mechanism_registry
        )
        for aid in comp.get("atomic_mechanism_ids", []):
            t["atomic_mechanisms"][aid] += 1
        t["atomic_sequences"][family_text(atom_labels)] += int(
            comp.get("support", {}).get("count", 1)
        )
        t["counts"].append(int(comp.get("support", {}).get("count", 1)))
        t["confidences"].append(
            safe_float(comp.get("scores", {}).get("composition_confidence"), 0.0)
        )
        t["classification_scores"].append(cls_score)
        t["examples"].extend(comp.get("examples", [])[:4])
        t["reasons"][reason] += 1

    ordered = []
    for label, t in raw_templates.items():
        ordered.append(
            (label, len(t["rules"]), sum(t["counts"]), mean(t["confidences"]))
        )
    ordered.sort(key=lambda x: (x[1], x[2], x[3], x[0]), reverse=True)

    templates = {}
    label_to_template_id = {}
    for idx, (label, _rule_count, _count, _conf) in enumerate(ordered, start=1):
        t = raw_templates[label]
        tid = f"TEMPLATE-{idx:03d}-{slugify(label)[:36]}"
        label_to_template_id[label] = tid
        count_total = sum(t["counts"])
        rule_count = len(t["rules"])
        mean_conf = mean(t["confidences"])
        mean_cls = mean(t["classification_scores"])
        variant_count = len(t["composition_family_motifs"])
        support_score = min(1.0, rule_count / 3.0)
        count_score = min(1.0, count_total / 6.0)
        confidence_score = mean_conf
        variant_score = min(1.0, variant_count / 5.0)
        classification_score = mean_cls
        templates[tid] = {
            "template_id": tid,
            "template_label": label,
            "category": t["category"],
            "support": {
                "count": count_total,
                "rules": sorted(t["rules"]),
                "rule_count": rule_count,
                "rule_counts": dict(t["rule_counts"]),
                "composition_count": len(t["composition_ids"]),
                "composition_ids": sorted(t["composition_ids"]),
                "family_variant_count": variant_count,
                "family_variants": [
                    {"family_motif_text": k, "count": v}
                    for k, v in t["composition_family_motifs"].most_common()
                ],
                "atomic_mechanism_ids": [
                    mid for mid, _ in t["atomic_mechanisms"].most_common()
                ],
                "atomic_sequences": [
                    {"atomic_sequence": k, "count": v}
                    for k, v in t["atomic_sequences"].most_common()
                ],
            },
            "scores": {
                "support_score": support_score,
                "count_score": count_score,
                "source_confidence_mean": confidence_score,
                "variant_score": variant_score,
                "classification_score": classification_score,
                "template_confidence": clamp01(
                    0.28 * support_score
                    + 0.22 * count_score
                    + 0.20 * confidence_score
                    + 0.14 * variant_score
                    + 0.16 * classification_score
                ),
            },
            "classification_reasons": dict(t["reasons"]),
            "examples": t["examples"][:10],
        }

    for comp_id, comp in composition_registry.get("compositions", {}).items():
        label, category, cls_score, reason = infer_template_for_composition(
            comp, mechanism_registry
        )
        tid = label_to_template_id[label]
        comp_to_template_id[comp_id] = tid
        instance_id = f"INST-{comp_id.replace('COMP-', '')}"
        instance_records[instance_id] = {
            "instance_id": instance_id,
            "template_id": tid,
            "template_label": templates[tid]["template_label"],
            "composition_id": comp_id,
            "composition_label": comp.get("label"),
            "family_motif": comp.get("family_motif"),
            "family_motif_text": comp.get("family_motif_text"),
            "category": comp.get("category"),
            "atomic_mechanism_ids": comp.get("atomic_mechanism_ids", []),
            "atomic_labels": mechanism_labels_for_ids(
                comp.get("atomic_mechanism_ids", []), mechanism_registry
            ),
            "support": comp.get("support", {}),
            "timing": comp.get("timing", {}),
            "scores": {
                "composition_confidence": safe_float(
                    comp.get("scores", {}).get("composition_confidence"), 0.0
                ),
                "template_classification_score": cls_score,
            },
            "classification_reason": reason,
        }

    rule_templates = defaultdict(lambda: {
        "rule_id": "",
        "templates": Counter(),
        "instances": Counter(),
        "atomic_mechanisms": Counter(),
        "family_signature": "NONE",
    })
    for rid, r in rule_map.get("rules", {}).items():
        rid = str(rid)
        rt = rule_templates[rid]
        rt["rule_id"] = rid
        rt["family_signature"] = r.get("family_signature", "NONE")
        for item in r.get("composition_counts", []):
            cid = item.get("composition_id")
            tid = comp_to_template_id.get(cid)
            if not tid:
                continue
            count = int(item.get("count", 1))
            rt["templates"][tid] += count
            rt["instances"][cid] += count
        for item in r.get("atomic_mechanism_counts", []):
            mid = item.get("mechanism_id")
            if mid:
                rt["atomic_mechanisms"][mid] += int(item.get("count", 1))

    final_rule_map = {}
    for rid, rt in sorted(rule_templates.items()):
        template_counts = [
            {
                "template_id": tid,
                "template_label": templates[tid]["template_label"],
                "category": templates[tid]["category"],
                "count": count,
            }
            for tid, count in rt["templates"].most_common()
        ]
        instance_counts = [
            {
                "composition_id": cid,
                "template_id": comp_to_template_id.get(cid),
                "count": count,
            }
            for cid, count in rt["instances"].most_common()
        ]
        atom_counts = [
            {
                "mechanism_id": mid,
                "label": mechanism_registry["mechanisms"].get(mid, {}).get(
                    "label", mid
                ),
                "count": count,
            }
            for mid, count in rt["atomic_mechanisms"].most_common()
        ]
        cat_counter = Counter()
        for item in template_counts:
            cat_counter[item["category"]] += item["count"]
        final_rule_map[rid] = {
            "rule_id": rid,
            "family_signature": rt["family_signature"],
            "dominant_template_category": (
                cat_counter.most_common(1)[0][0] if cat_counter else "none"
            ),
            "template_diversity": len(template_counts),
            "instance_diversity": len(instance_counts),
            "atomic_diversity": len(atom_counts),
            "template_counts": template_counts,
            "instance_counts": instance_counts,
            "atomic_mechanism_counts": atom_counts,
        }

    template_registry = {
        "schema": "universe_search_composition_templates_v10",
        "results_dir": str(results_dir),
        "template_count": len(templates),
        "templates": templates,
        "composition_to_template_id": comp_to_template_id,
    }
    instance_registry = {
        "schema": "universe_search_composition_instances_v10",
        "results_dir": str(results_dir),
        "instance_count": len(instance_records),
        "instances": instance_records,
    }
    template_rule_map = {
        "schema": "universe_search_template_rule_map_v10",
        "results_dir": str(results_dir),
        "rule_count": len(final_rule_map),
        "rules": final_rule_map,
    }
    return template_registry, instance_registry, template_rule_map


def build_report(
    template_registry: Dict[str, Any],
    instance_registry: Dict[str, Any],
    template_rule_map: Dict[str, Any],
    results_dir: Path,
) -> Dict[str, Any]:
    templates = list(template_registry.get("templates", {}).values())
    categories = Counter(t["category"] for t in templates)
    rule_categories = Counter(
        r["dominant_template_category"]
        for r in template_rule_map.get("rules", {}).values()
    )
    top_templates = sorted(
        templates,
        key=lambda t: (
            t["scores"]["template_confidence"],
            t["support"]["rule_count"],
            t["support"]["count"],
        ),
        reverse=True,
    )
    return {
        "schema": "universe_search_template_report_v10",
        "results_dir": str(results_dir),
        "template_count": template_registry.get("template_count", 0),
        "instance_count": instance_registry.get("instance_count", 0),
        "rule_count": template_rule_map.get("rule_count", 0),
        "template_category_counts": dict(categories),
        "rule_dominant_template_category_counts": dict(rule_categories),
        "top_templates": [slim_template(t) for t in top_templates[:20]],
        "rule_summaries": {
            rid: {
                "dominant_template_category": r["dominant_template_category"],
                "template_diversity": r["template_diversity"],
                "instance_diversity": r["instance_diversity"],
                "atomic_diversity": r["atomic_diversity"],
                "family_signature": r["family_signature"],
                "top_templates": r["template_counts"][:6],
            }
            for rid, r in template_rule_map.get("rules", {}).items()
        },
    }


def slim_template(t: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "template_id": t["template_id"],
        "template_label": t["template_label"],
        "category": t["category"],
        "count": t["support"]["count"],
        "rule_count": t["support"]["rule_count"],
        "composition_count": t["support"]["composition_count"],
        "family_variant_count": t["support"]["family_variant_count"],
        "template_confidence": t["scores"]["template_confidence"],
        "top_family_variants": t["support"]["family_variants"][:6],
    }
