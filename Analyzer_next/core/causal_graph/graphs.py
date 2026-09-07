"""Pure transition, causal-tree, and mechanism-family projections."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Dict, List

from Analyzer_next.core.causal_graph.motifs import (
    clamp01,
    event_family,
    event_sort_key,
    event_tick,
    event_type,
    family_key,
    has_collapse_recurrence,
    has_recovery,
    is_repetition,
    is_true_cycle,
    mean,
    mechanism_label_for_family,
    stdev,
)

def build_transition_graph(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    events = sorted(events, key=event_sort_key)
    nodes = Counter(event_type(e) for e in events)
    edges = Counter()
    delays = defaultdict(list)

    for a, b in zip(events, events[1:]):
        src = event_type(a)
        dst = event_type(b)
        edges[(src, dst)] += 1
        delays[(src, dst)].append(max(0, event_tick(b) - event_tick(a)))

    outgoing = Counter()
    incoming = Counter()
    for (src, dst), count in edges.items():
        outgoing[src] += count
        incoming[dst] += count

    node_data = {}
    for node, count in nodes.items():
        node_data[node] = {
            "count": count,
            "family": event_family(node),
            "incoming_count": incoming.get(node, 0),
            "outgoing_count": outgoing.get(node, 0),
            "in_degree": len([1 for (_s, d) in edges if d == node]),
            "out_degree": len([1 for (s, _d) in edges if s == node]),
        }

    edge_data = {}
    for (src, dst), count in edges.items():
        key = f"{src} -> {dst}"
        edge_data[key] = {
            "source": src,
            "target": dst,
            "source_family": event_family(src),
            "target_family": event_family(dst),
            "family_transition": f"{event_family(src)} -> {event_family(dst)}",
            "count": count,
            "probability_from_source": count / max(1, outgoing[src]),
            "mean_delay_ticks": mean(delays[(src, dst)]),
            "min_delay_ticks": min(delays[(src, dst)]),
            "max_delay_ticks": max(delays[(src, dst)]),
        }

    return {
        "node_count": len(node_data),
        "edge_count": len(edge_data),
        "nodes": node_data,
        "edges": edge_data,
    }


def build_causal_tree_from_sequences(rule_graphs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Global causal tree:
    for each source event, summarize next-step branches and family branches.
    """
    branches = defaultdict(Counter)
    branch_rules = defaultdict(lambda: defaultdict(set))
    family_branches = defaultdict(Counter)
    family_branch_rules = defaultdict(lambda: defaultdict(set))

    for rid, graph in rule_graphs.items():
        seq = graph["motif_info"]["compact_sequence"]
        for a, b in zip(seq, seq[1:]):
            branches[a][b] += 1
            branch_rules[a][b].add(rid)
            fa, fb = event_family(a), event_family(b)
            family_branches[fa][fb] += 1
            family_branch_rules[fa][fb].add(rid)

    def finalize(counter_map, rule_map):
        out = {}
        for src, targets in counter_map.items():
            total = sum(targets.values())
            ranked = []
            for dst, count in targets.most_common():
                rules = sorted(rule_map[src][dst])
                ranked.append({
                    "target": dst,
                    "count": count,
                    "probability": count / max(1, total),
                    "rules": rules,
                    "rule_count": len(rules),
                })
            entropy = 0.0
            for count in targets.values():
                p = count / max(1, total)
                if p > 0:
                    entropy -= p * math.log2(p)
            max_entropy = math.log2(max(1, len(targets)))
            divergence = entropy / max_entropy if max_entropy > 0 else 0.0
            out[src] = {
                "total_outgoing": total,
                "branch_count": len(targets),
                "divergence_score": divergence,
                "branches": ranked,
            }
        return out

    return {
        "event_tree": finalize(branches, branch_rules),
        "family_tree": finalize(family_branches, family_branch_rules),
    }


def merge_global_motifs(rule_graphs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    global_motifs = defaultdict(lambda: {
        "motif": [],
        "count": 0,
        "rules": set(),
        "rule_counts": Counter(),
        "durations": [],
        "examples": [],
    })
    global_family_motifs = defaultdict(lambda: {
        "family_motif": [],
        "count": 0,
        "rules": set(),
        "rule_counts": Counter(),
        "event_variants": Counter(),
        "durations": [],
        "examples": [],
    })

    for rid, graph in rule_graphs.items():
        mi = graph["motif_info"]
        for key, data in mi["motifs"].items():
            item = global_motifs[key]
            item["motif"] = data["motif"]
            item["count"] += data["count"]
            item["rules"].add(rid)
            item["rule_counts"][rid] += data["count"]
            item["durations"].append(data.get("mean_duration_ticks", 0.0))
            item["examples"].extend(data.get("examples", [])[:2])

        for key, data in mi["family_motifs"].items():
            item = global_family_motifs[key]
            item["family_motif"] = data["family_motif"]
            item["count"] += data["count"]
            item["rules"].add(rid)
            item["rule_counts"][rid] += data["count"]
            item["event_variants"].update(data.get("event_variants", {}))
            item["durations"].append(data.get("mean_duration_ticks", 0.0))
            item["examples"].extend(data.get("examples", [])[:2])

    def motif_confidence(count: int, rule_count: int, durations: List[float], is_cycle: bool, variant_count: int = 1) -> float:
        count_score = min(1.0, count / 4.0)
        support_score = min(1.0, rule_count / 3.0)
        duration_score = 1.0 - clamp01(stdev(durations) / max(1.0, mean(durations))) if len(durations) >= 2 else 0.5
        variant_score = min(1.0, variant_count / 3.0)
        cycle_bonus = 0.08 if is_cycle else 0.0
        return clamp01(0.34 * count_score + 0.36 * support_score + 0.16 * duration_score + 0.08 * variant_score + cycle_bonus)

    def finalize_event(key, data):
        items = data["motif"]
        rules = sorted(data["rules"])
        durations = data["durations"]
        return {
            "motif": items,
            "motif_text": key,
            "family_motif": [event_family(x) for x in items],
            "family_motif_text": family_key(items),
            "mechanism_label": mechanism_label_for_family([event_family(x) for x in items]),
            "length": len(items),
            "count": data["count"],
            "rules": rules,
            "rule_count": len(rules),
            "rule_counts": dict(data["rule_counts"]),
            "mean_duration_ticks": mean(durations),
            "duration_stdev_ticks": stdev(durations),
            "is_true_cycle": is_true_cycle(items),
            "is_repetition": is_repetition(items),
            "has_recovery": has_recovery(items),
            "has_collapse_recurrence": has_collapse_recurrence(items),
            "confidence": motif_confidence(data["count"], len(rules), durations, is_true_cycle(items)),
            "examples": data["examples"][:8],
        }

    def finalize_family(key, data):
        families = data["family_motif"]
        rules = sorted(data["rules"])
        durations = data["durations"]
        variant_count = len(data["event_variants"])
        return {
            "family_motif": families,
            "family_motif_text": key,
            "mechanism_label": mechanism_label_for_family(families),
            "length": len(families),
            "count": data["count"],
            "rules": rules,
            "rule_count": len(rules),
            "rule_counts": dict(data["rule_counts"]),
            "event_variant_count": variant_count,
            "event_variants": dict(data["event_variants"]),
            "mean_duration_ticks": mean(durations),
            "duration_stdev_ticks": stdev(durations),
            "is_true_cycle": is_true_cycle(families),
            "is_repetition": is_repetition(families),
            "has_recovery": "Collapse" in families and "Recovery" in families[families.index("Collapse") + 1:],
            "has_collapse_recurrence": families.count("Collapse") >= 2,
            "confidence": motif_confidence(data["count"], len(rules), durations, is_true_cycle(families), variant_count),
            "examples": data["examples"][:8],
        }

    event_motifs = {k: finalize_event(k, v) for k, v in global_motifs.items()}
    family_motifs = {k: finalize_family(k, v) for k, v in global_family_motifs.items()}

    strongest_event = sorted(event_motifs.values(), key=lambda x: (x["confidence"], x["rule_count"], x["count"]), reverse=True)
    strongest_family = sorted(family_motifs.values(), key=lambda x: (x["confidence"], x["rule_count"], x["count"]), reverse=True)

    return {
        "event_motif_count": len(event_motifs),
        "family_motif_count": len(family_motifs),
        "event_motifs": event_motifs,
        "family_motifs": family_motifs,
        "strongest_event_motifs": strongest_event[:30],
        "strongest_family_motifs": strongest_family[:30],
        "recovery_families": [m for m in strongest_family if m["has_recovery"]][:30],
        "collapse_recurrence_families": [m for m in strongest_family if m["has_collapse_recurrence"]][:30],
        "true_cycle_families": [m for m in strongest_family if m["is_true_cycle"]][:30],
        "repetition_families": [m for m in strongest_family if m["is_repetition"]][:30],
    }


def build_rule_family_fingerprint(rule_id: str, events: List[Dict[str, Any]], motif_info: Dict[str, Any]) -> Dict[str, Any]:
    seq = motif_info["compact_sequence"]
    fseq = motif_info["compact_family_sequence"]

    family_counts = Counter(fseq)
    mechanisms = Counter(m["mechanism_label"] for m in motif_info["family_motifs"].values())

    recovery = sum(1 for m in motif_info["family_motifs"].values() if m["has_recovery"])
    collapse_rec = sum(1 for m in motif_info["family_motifs"].values() if m["has_collapse_recurrence"])
    true_cycles = sum(1 for m in motif_info["family_motifs"].values() if m["is_true_cycle"])
    repetitions = sum(1 for m in motif_info["family_motifs"].values() if m["is_repetition"])

    if collapse_rec:
        archetype = "collapse-recurrence mechanism"
    elif recovery and true_cycles:
        archetype = "cyclic recovery mechanism"
    elif recovery:
        archetype = "post-collapse recovery mechanism"
    elif true_cycles:
        archetype = "cyclic mechanism"
    elif family_counts.get("Recovery", 0) > family_counts.get("Collapse", 0):
        archetype = "growth-recovery mechanism"
    elif family_counts.get("Dormancy", 0):
        archetype = "dormancy-mediated mechanism"
    else:
        archetype = "mixed mechanism"

    return {
        "rule_id": rule_id,
        "mechanism_archetype": archetype,
        "event_signature": motif_info["compact_sequence_text"],
        "family_signature": motif_info["compact_family_sequence_text"],
        "family_counts": dict(family_counts),
        "mechanism_label_counts": dict(mechanisms),
        "recovery_family_count": recovery,
        "collapse_recurrence_family_count": collapse_rec,
        "true_cycle_family_count": true_cycles,
        "repetition_family_count": repetitions,
        "mechanism_complexity": clamp01((len(motif_info["family_motifs"]) / 14.0) + (true_cycles * 0.08) + (recovery * 0.04)),
        "collapse_pressure": family_counts.get("Collapse", 0) / max(1, len(fseq)),
        "recovery_pressure": family_counts.get("Recovery", 0) / max(1, len(fseq)),
        "dormancy_pressure": family_counts.get("Dormancy", 0) / max(1, len(fseq)),
    }


def build_mechanism_hypotheses(global_motifs: Dict[str, Any], causal_tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    hypotheses = []

    for fam in global_motifs.get("strongest_family_motifs", [])[:12]:
        text = ""
        if fam["has_recovery"]:
            text = f"`{fam['family_motif_text']}` may represent a reusable recovery mechanism."
        elif fam["has_collapse_recurrence"]:
            text = f"`{fam['family_motif_text']}` may represent a collapse recurrence mechanism."
        elif fam["is_true_cycle"]:
            text = f"`{fam['family_motif_text']}` may represent a cyclic causal mechanism."
        else:
            text = f"`{fam['family_motif_text']}` may represent a generalized transition mechanism."

        hypotheses.append({
            "mechanism_label": fam["mechanism_label"],
            "family_motif": fam["family_motif"],
            "family_motif_text": fam["family_motif_text"],
            "confidence": fam["confidence"],
            "rule_count": fam["rule_count"],
            "count": fam["count"],
            "hypothesis": text,
        })

    # Divergence hypotheses from family tree.
    for src, data in causal_tree.get("family_tree", {}).items():
        if data["branch_count"] >= 2 and data["divergence_score"] >= 0.6:
            branches = ", ".join(f"{b['target']} ({b['probability']:.2f})" for b in data["branches"][:4])
            hypotheses.append({
                "mechanism_label": f"{src.upper()}_DIVERGENCE",
                "family_motif": [src],
                "family_motif_text": src,
                "confidence": clamp01(data["divergence_score"]),
                "rule_count": len(set(r for b in data["branches"] for r in b["rules"])),
                "count": data["total_outgoing"],
                "hypothesis": f"`{src}` is a divergence family with branches: {branches}.",
            })

    hypotheses = sorted(hypotheses, key=lambda h: (h["confidence"], h["rule_count"], h["count"]), reverse=True)
    return hypotheses[:30]

