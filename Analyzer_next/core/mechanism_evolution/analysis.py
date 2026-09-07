"""Pure mechanism-evolution inference and report assembly."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


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


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def normalize_template_sequence(rule_record: Dict[str, Any]) -> List[str]:
    """Reconstruct the legacy weighted template path for one rule."""
    out = []
    for item in rule_record.get("template_counts", []):
        label = item.get("template_label", "UNKNOWN_TEMPLATE")
        count = int(item.get("count", 1))
        out.extend([label] * max(1, count))
    return out


def normalize_atomic_sequence(rule_record: Dict[str, Any]) -> List[str]:
    out = []
    for item in rule_record.get("atomic_mechanism_counts", []):
        label = item.get("label", "UNKNOWN_ATOMIC")
        count = int(item.get("count", 1))
        out.extend([label] * max(1, count))
    return out


def compact_sequence(seq: List[str]) -> List[str]:
    out = []
    for item in seq:
        if not out or out[-1] != item:
            out.append(item)
    return out


def build_transition_edges(
    paths: Dict[str, List[str]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    node_counts = Counter()
    edge_counts = Counter()
    edge_rules = defaultdict(set)

    for rid, seq in paths.items():
        for node in seq:
            node_counts[node] += 1
        for a, b in zip(seq, seq[1:]):
            edge_counts[(a, b)] += 1
            edge_rules[(a, b)].add(rid)

    outgoing = Counter()
    incoming = Counter()
    for (a, b), count in edge_counts.items():
        outgoing[a] += count
        incoming[b] += count

    nodes = {}
    for node, count in node_counts.items():
        in_degree = len([1 for (_a, b) in edge_counts if b == node])
        out_degree = len([1 for (a, _b) in edge_counts if a == node])
        nodes[node] = {
            "node": node,
            "count": count,
            "incoming_count": incoming.get(node, 0),
            "outgoing_count": outgoing.get(node, 0),
            "in_degree": in_degree,
            "out_degree": out_degree,
            "centrality_score": clamp01(
                0.35 * min(1.0, count / 12.0)
                + 0.30 * min(1.0, incoming.get(node, 0) / 8.0)
                + 0.30 * min(1.0, outgoing.get(node, 0) / 8.0)
                + 0.05 * min(1.0, (in_degree + out_degree) / 6.0)
            ),
        }

    edges = {}
    for (a, b), count in edge_counts.items():
        key = f"{a} -> {b}"
        edges[key] = {
            "source": a,
            "target": b,
            "count": count,
            "rules": sorted(edge_rules[(a, b)]),
            "rule_count": len(edge_rules[(a, b)]),
            "probability_from_source": count / max(1, outgoing[a]),
            "transition_strength": clamp01(
                0.45 * min(1.0, count / 6.0)
                + 0.35 * min(1.0, len(edge_rules[(a, b)]) / 3.0)
                + 0.20 * (count / max(1, outgoing[a]))
            ),
        }

    return nodes, edges


def detect_evolution_motifs(
    paths: Dict[str, List[str]], max_len: int = 4
) -> Dict[str, Any]:
    motifs = defaultdict(
        lambda: {
            "motif": [],
            "count": 0,
            "rules": set(),
            "examples": [],
        }
    )

    for rid, seq in paths.items():
        for length in range(2, max_len + 1):
            if len(seq) < length:
                continue
            for i in range(len(seq) - length + 1):
                win = seq[i:i + length]
                key = " -> ".join(win)
                motif = motifs[key]
                motif["motif"] = win
                motif["count"] += 1
                motif["rules"].add(rid)
                if len(motif["examples"]) < 6:
                    motif["examples"].append(
                        {"rule_id": rid, "index": i, "motif": win}
                    )

    out = {}
    for key, motif in motifs.items():
        out[key] = {
            "motif": motif["motif"],
            "motif_text": key,
            "length": len(motif["motif"]),
            "count": motif["count"],
            "rules": sorted(motif["rules"]),
            "rule_count": len(motif["rules"]),
            "is_cycle": is_true_cycle(motif["motif"]),
            "confidence": clamp01(
                0.45 * min(1.0, motif["count"] / 4.0)
                + 0.45 * min(1.0, len(motif["rules"]) / 3.0)
                + 0.10 * (1.0 if is_true_cycle(motif["motif"]) else 0.0)
            ),
            "examples": motif["examples"],
        }

    strongest = sorted(
        out.values(),
        key=lambda item: (
            item["confidence"],
            item["rule_count"],
            item["count"],
        ),
        reverse=True,
    )
    cycles = [motif for motif in strongest if motif["is_cycle"]]
    return {
        "motif_count": len(out),
        "motifs": out,
        "strongest_motifs": strongest[:30],
        "cycle_motifs": cycles[:30],
    }


def is_true_cycle(seq: List[str]) -> bool:
    if len(seq) < 3:
        return False
    for i, item in enumerate(seq):
        if item in seq[:i]:
            previous = seq[:i].index(item)
            middle = seq[previous + 1:i]
            if middle and any(value != item for value in middle):
                return True
    return False


def classify_evolution_path(seq: List[str]) -> str:
    if not seq:
        return "empty evolution path"
    if any("FAILED_RECOVERY_LOOP" in item for item in seq) and any(
        "OSCILLATING_RECOVERY" in item for item in seq
    ):
        return "loop-amplifying evolution"
    if any("CASCADED_COLLAPSE" in item for item in seq) and any(
        "RECOVERY" in item for item in seq
    ):
        return "collapse-recovery evolution"
    if any("DORMANT" in item or "DORMANCY" in item for item in seq):
        return "dormancy-mediated evolution"
    if any("SUSTAINED_RECOVERY" in item for item in seq):
        return "growth-stability evolution"
    if len(set(seq)) == 1:
        return "single-template evolution"
    return "mixed template evolution"


def build_evolution_report(
    mechanism_registry: Dict[str, Any],
    template_registry: Dict[str, Any],
    instance_registry: Dict[str, Any],
    template_rule_map: Dict[str, Any],
    results_dir: Path,
) -> Dict[str, Any]:
    # The first three documents remain part of the legacy input contract even
    # though v1.0 derives its weighted paths from template_rule_map.
    del mechanism_registry, template_registry, instance_registry
    rule_template_paths = {}
    rule_atomic_paths = {}

    for rid, record in template_rule_map.get("rules", {}).items():
        rule_template_paths[rid] = compact_sequence(
            normalize_template_sequence(record)
        )
        rule_atomic_paths[rid] = compact_sequence(
            normalize_atomic_sequence(record)
        )

    template_nodes, template_edges = build_transition_edges(rule_template_paths)
    atomic_nodes, atomic_edges = build_transition_edges(rule_atomic_paths)
    template_motifs = detect_evolution_motifs(rule_template_paths)
    atomic_motifs = detect_evolution_motifs(rule_atomic_paths)

    rule_paths = {}
    for rid in sorted(rule_template_paths):
        template_path = rule_template_paths[rid]
        atomic_path = rule_atomic_paths.get(rid, [])
        rule_paths[rid] = {
            "rule_id": rid,
            "template_path": template_path,
            "template_path_text": (
                " -> ".join(template_path) if template_path else "NONE"
            ),
            "atomic_path": atomic_path,
            "atomic_path_text": (
                " -> ".join(atomic_path) if atomic_path else "NONE"
            ),
            "template_evolution_archetype": classify_evolution_path(
                template_path
            ),
            "atomic_evolution_archetype": classify_evolution_path(atomic_path),
            "template_path_length": len(template_path),
            "atomic_path_length": len(atomic_path),
            "template_cycle_detected": is_true_cycle(template_path),
            "atomic_cycle_detected": is_true_cycle(atomic_path),
        }

    top_template_nodes = sorted(
        template_nodes.values(),
        key=lambda node: node["centrality_score"],
        reverse=True,
    )
    top_template_edges = sorted(
        template_edges.values(),
        key=lambda edge: edge["transition_strength"],
        reverse=True,
    )
    top_atomic_nodes = sorted(
        atomic_nodes.values(),
        key=lambda node: node["centrality_score"],
        reverse=True,
    )
    top_atomic_edges = sorted(
        atomic_edges.values(),
        key=lambda edge: edge["transition_strength"],
        reverse=True,
    )
    archetypes = Counter(
        record["template_evolution_archetype"]
        for record in rule_paths.values()
    )

    return {
        "schema": "universe_search_mechanism_evolution_graph_v10",
        "results_dir": str(results_dir),
        "rule_count": len(rule_paths),
        "template_layer": {
            "node_count": len(template_nodes),
            "edge_count": len(template_edges),
            "nodes": template_nodes,
            "edges": template_edges,
            "top_nodes": top_template_nodes[:20],
            "top_edges": top_template_edges[:20],
            "motifs": template_motifs,
        },
        "atomic_layer": {
            "node_count": len(atomic_nodes),
            "edge_count": len(atomic_edges),
            "nodes": atomic_nodes,
            "edges": atomic_edges,
            "top_nodes": top_atomic_nodes[:20],
            "top_edges": top_atomic_edges[:20],
            "motifs": atomic_motifs,
        },
        "rule_paths": rule_paths,
        "global": {
            "template_evolution_archetype_counts": dict(archetypes),
        },
    }


def build_compact_report(
    evolution_graph: Dict[str, Any], results_dir: Path
) -> Dict[str, Any]:
    return {
        "schema": "universe_search_mechanism_evolution_report_v10",
        "results_dir": str(results_dir),
        "rule_count": evolution_graph["rule_count"],
        "template_layer_summary": {
            "node_count": evolution_graph["template_layer"]["node_count"],
            "edge_count": evolution_graph["template_layer"]["edge_count"],
            "top_nodes": evolution_graph["template_layer"]["top_nodes"][:10],
            "top_edges": evolution_graph["template_layer"]["top_edges"][:10],
            "strongest_motifs": evolution_graph["template_layer"]["motifs"][
                "strongest_motifs"
            ][:10],
            "cycle_motifs": evolution_graph["template_layer"]["motifs"][
                "cycle_motifs"
            ][:10],
        },
        "atomic_layer_summary": {
            "node_count": evolution_graph["atomic_layer"]["node_count"],
            "edge_count": evolution_graph["atomic_layer"]["edge_count"],
            "top_nodes": evolution_graph["atomic_layer"]["top_nodes"][:10],
            "top_edges": evolution_graph["atomic_layer"]["top_edges"][:10],
            "strongest_motifs": evolution_graph["atomic_layer"]["motifs"][
                "strongest_motifs"
            ][:10],
            "cycle_motifs": evolution_graph["atomic_layer"]["motifs"][
                "cycle_motifs"
            ][:10],
        },
        "rule_summaries": evolution_graph["rule_paths"],
        "global": evolution_graph["global"],
    }
