"""Pure scientific analysis for canonical timeline compression."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any


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


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def source_ids(ev: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(x)
        for x in ev.get("source_fused_event_ids", [])
        if x is not None
    )


def event_label(ev: dict[str, Any]) -> str:
    if ev.get("kind") == "atomic_mechanism":
        return ev.get("mechanism_label") or "UNKNOWN_ATOMIC"
    return (
        ev.get("template_label")
        or ev.get("composition_label")
        or "UNKNOWN_TEMPLATE"
    )


def event_score(ev: dict[str, Any]) -> float:
    length_score = min(1.0, len(source_ids(ev)) / 5.0)
    duration_score = min(1.0, safe_float(ev.get("duration_ticks")) / 120.0)
    confidence = safe_float(ev.get("confidence"))
    kind_bonus = 0.12 if ev.get("kind") == "composition_template" else 0.02
    return clamp01(
        0.42 * length_score
        + 0.20 * duration_score
        + 0.30 * confidence
        + kind_bonus
    )


def covers(parent: dict[str, Any], child: dict[str, Any]) -> bool:
    if parent.get("timeline_event_id") == child.get("timeline_event_id"):
        return False
    p_ids = set(source_ids(parent))
    c_ids = set(source_ids(child))
    if not c_ids or not p_ids:
        return False
    if not c_ids.issubset(p_ids):
        return False
    if int(parent.get("start_tick", 0)) > int(child.get("start_tick", 0)):
        return False
    if int(parent.get("end_tick", 0)) < int(child.get("end_tick", 0)):
        return False
    return len(p_ids) > len(c_ids)


def overlap_ratio(a: dict[str, Any], b: dict[str, Any]) -> float:
    a_ids = set(source_ids(a))
    b_ids = set(source_ids(b))
    if not a_ids or not b_ids:
        return 0.0
    return len(a_ids & b_ids) / max(1, min(len(a_ids), len(b_ids)))


def resolve_sibling_overlaps(
    canonical: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    all_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    del by_id, all_events
    kept: list[dict[str, Any]] = []
    for ev in sorted(
        canonical,
        key=lambda e: (
            -len(source_ids(e)),
            -e["compression_score"],
            e["start_tick"],
        ),
    ):
        conflict = None
        for item in kept:
            same_rule = ev.get("rule_id") == item.get("rule_id")
            if same_rule and overlap_ratio(ev, item) >= 0.80:
                conflict = item
                break
        if conflict is None:
            kept.append(ev)
            continue
        ev_better = (
            len(source_ids(ev)),
            ev["compression_score"],
            safe_float(ev.get("confidence")),
        ) > (
            len(source_ids(conflict)),
            conflict["compression_score"],
            safe_float(conflict.get("confidence")),
        )
        if ev_better:
            kept.remove(conflict)
            conflict["compressed"] = True
            conflict["parent_timeline_event_id"] = ev["timeline_event_id"]
            conflict["compression_reason"] = "overlapped_by_stronger_sibling"
            ev["child_timeline_event_ids"].append(
                conflict["timeline_event_id"]
            )
            kept.append(ev)
        else:
            ev["compressed"] = True
            ev["parent_timeline_event_id"] = conflict["timeline_event_id"]
            ev["compression_reason"] = "overlapped_by_stronger_sibling"
            conflict["child_timeline_event_ids"].append(
                ev["timeline_event_id"]
            )
    return sorted(
        kept,
        key=lambda e: (e["start_tick"], e["end_tick"], e["timeline_event_id"]),
    )


def select_parents(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    annotated = []
    for ev in events:
        item = dict(ev)
        item["compression_score"] = event_score(item)
        item["compressed"] = False
        item["parent_timeline_event_id"] = None
        item["child_timeline_event_ids"] = []
        item["compression_reason"] = None
        annotated.append(item)
    by_id = {e["timeline_event_id"]: e for e in annotated}
    for child in annotated:
        candidates = [parent for parent in annotated if covers(parent, child)]
        if not candidates:
            continue
        candidates.sort(
            key=lambda parent: (
                len(source_ids(parent)),
                parent["compression_score"],
                safe_float(parent.get("confidence")),
                safe_float(parent.get("duration_ticks")),
            ),
            reverse=True,
        )
        parent = candidates[0]
        if (
            child.get("kind") == "atomic_mechanism"
            and parent["compression_score"] < 0.58
        ):
            continue
        child["compressed"] = True
        child["parent_timeline_event_id"] = parent["timeline_event_id"]
        child["compression_reason"] = "covered_by_larger_window"
        parent["child_timeline_event_ids"].append(child["timeline_event_id"])
    canonical = [e for e in annotated if not e["compressed"]]
    canonical = resolve_sibling_overlaps(canonical, by_id, annotated)
    canonical_ids = {e["timeline_event_id"] for e in canonical}
    for item in annotated:
        if item["timeline_event_id"] not in canonical_ids and not item["compressed"]:
            item["compressed"] = True
            item["compression_reason"] = (
                item.get("compression_reason") or "sibling_overlap_removed"
            )
    compression_tree = {
        e["timeline_event_id"]: {
            "timeline_event_id": e["timeline_event_id"],
            "label": event_label(e),
            "compressed": e["compressed"],
            "parent_timeline_event_id": e["parent_timeline_event_id"],
            "child_timeline_event_ids": e["child_timeline_event_ids"],
            "source_fused_event_ids": list(source_ids(e)),
            "compression_score": e["compression_score"],
            "reason": e.get("compression_reason"),
        }
        for e in annotated
    }
    canonical = sorted(
        canonical,
        key=lambda e: (
            int(e.get("start_tick", 0)),
            int(e.get("end_tick", 0)),
            e["timeline_event_id"],
        ),
    )
    return canonical, {
        "events": annotated,
        "compression_tree": compression_tree,
    }


def make_segment(
    rule_id: str,
    index: int,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    start = min(int(e.get("start_tick", 0)) for e in events)
    end = max(int(e.get("end_tick", 0)) for e in events)
    labels = [event_label(e) for e in events]
    categories = Counter(
        e.get("mechanism_category", "unknown") for e in events
    )
    return {
        "segment_id": f"SEG-{rule_id}-{index:03d}",
        "rule_id": rule_id,
        "start_tick": start,
        "end_tick": end,
        "duration_ticks": max(0, end - start),
        "event_count": len(events),
        "timeline_event_ids": [e["timeline_event_id"] for e in events],
        "labels": labels,
        "sequence_text": " -> ".join(labels) if labels else "NONE",
        "dominant_category": (
            categories.most_common(1)[0][0] if categories else "unknown"
        ),
        "category_counts": dict(categories),
        "mean_confidence": mean(
            [safe_float(e.get("confidence")) for e in events]
        ),
        "mean_compression_score": mean(
            [safe_float(e.get("compression_score")) for e in events]
        ),
    }


def build_segments(
    rule_id: str,
    canonical: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not canonical:
        return []
    canonical = sorted(
        canonical,
        key=lambda e: (e["start_tick"], e["end_tick"]),
    )
    segments = []
    current = [canonical[0]]
    for ev in canonical[1:]:
        previous = current[-1]
        gap = int(ev.get("start_tick", 0)) - int(
            previous.get("end_tick", 0)
        )
        same_family = ev.get("mechanism_category") == previous.get(
            "mechanism_category"
        )
        connected = gap <= max(
            8, int(previous.get("duration_ticks", 0) * 0.25)
        ) or same_family
        if connected:
            current.append(ev)
        else:
            segments.append(
                make_segment(rule_id, len(segments) + 1, current)
            )
            current = [ev]
    segments.append(make_segment(rule_id, len(segments) + 1, current))
    return segments


def build_compressed_transitions(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events = sorted(
        events,
        key=lambda e: (
            int(e.get("center_tick", 0)),
            int(e.get("start_tick", 0)),
            e["timeline_event_id"],
        ),
    )
    transitions = []
    for source, target in zip(events, events[1:]):
        delay = max(
            0,
            int(target.get("center_tick", 0))
            - int(source.get("center_tick", 0)),
        )
        transitions.append({
            "source_timeline_event_id": source["timeline_event_id"],
            "target_timeline_event_id": target["timeline_event_id"],
            "source_label": event_label(source),
            "target_label": event_label(target),
            "source_category": source.get("mechanism_category"),
            "target_category": target.get("mechanism_category"),
            "source_tick": source.get("center_tick"),
            "target_tick": target.get("center_tick"),
            "delay_ticks": delay,
        })
    return transitions


def build_rule_compression(
    rule_id: str,
    rule_payload: dict[str, Any],
) -> dict[str, Any]:
    raw_events = sorted(
        rule_payload.get("timeline_events", []),
        key=lambda e: (e.get("start_tick", 0), e.get("end_tick", 0)),
    )
    canonical, details = select_parents(raw_events)
    segments = build_segments(rule_id, canonical)
    transitions = build_compressed_transitions(canonical)
    raw_count = len(raw_events)
    canonical_count = len(canonical)
    compressed_count = raw_count - canonical_count
    summary = {
        "rule_id": rule_id,
        "raw_timeline_event_count": raw_count,
        "compressed_timeline_event_count": canonical_count,
        "compressed_away_count": compressed_count,
        "compression_ratio": compressed_count / max(1, raw_count),
        "segment_count": len(segments),
        "transition_count": len(transitions),
        "mean_canonical_confidence": mean(
            [safe_float(e.get("confidence")) for e in canonical]
        ),
        "mean_compression_score": mean(
            [safe_float(e.get("compression_score")) for e in canonical]
        ),
        "dominant_segment_category": (
            Counter(s["dominant_category"] for s in segments)
            .most_common(1)[0][0]
            if segments
            else "none"
        ),
    }
    return {
        "rule_id": rule_id,
        "summary": summary,
        "canonical_timeline_events": canonical,
        "all_annotated_events": details["events"],
        "compression_tree": details["compression_tree"],
        "segments": segments,
        "compressed_transitions": transitions,
    }


def build_global_transitions(rules: dict[str, Any]) -> dict[str, Any]:
    edge_counts = Counter()
    edge_rules = defaultdict(set)
    edge_delays = defaultdict(list)
    for rule_id, rule in rules.items():
        for transition in rule.get("compressed_transitions", []):
            source = transition["source_label"]
            target = transition["target_label"]
            key = (source, target)
            edge_counts[key] += 1
            edge_rules[key].add(rule_id)
            edge_delays[key].append(
                safe_float(transition.get("delay_ticks"))
            )
    outgoing = Counter()
    incoming = Counter()
    for (source, target), count in edge_counts.items():
        outgoing[source] += count
        incoming[target] += count
    edges = {}
    for (source, target), count in edge_counts.items():
        delays = edge_delays[(source, target)]
        key = f"{source} -> {target}"
        edges[key] = {
            "source": source,
            "target": target,
            "count": count,
            "rules": sorted(edge_rules[(source, target)]),
            "rule_count": len(edge_rules[(source, target)]),
            "probability_from_source": count / max(1, outgoing[source]),
            "mean_delay_ticks": mean(delays),
            "delay_stdev_ticks": stdev(delays),
            "transition_strength": clamp01(
                0.42 * min(1.0, count / 4.0)
                + 0.36 * min(
                    1.0, len(edge_rules[(source, target)]) / 3.0
                )
                + 0.22 * (count / max(1, outgoing[source]))
            ),
        }
    nodes = Counter()
    for (source, target), count in edge_counts.items():
        nodes[source] += count
        nodes[target] += count
    node_data = {}
    for node, count in nodes.items():
        in_degree = len([1 for (_source, target) in edge_counts if target == node])
        out_degree = len([1 for (source, _target) in edge_counts if source == node])
        node_data[node] = {
            "node": node,
            "count": count,
            "incoming_count": incoming.get(node, 0),
            "outgoing_count": outgoing.get(node, 0),
            "in_degree": in_degree,
            "out_degree": out_degree,
            "centrality_score": clamp01(
                0.34 * min(1.0, count / 6.0)
                + 0.28 * min(1.0, incoming.get(node, 0) / 4.0)
                + 0.28 * min(1.0, outgoing.get(node, 0) / 4.0)
                + 0.10 * min(1.0, (in_degree + out_degree) / 5.0)
            ),
        }
    return {
        "node_count": len(node_data),
        "edge_count": len(edges),
        "nodes": node_data,
        "edges": edges,
        "top_edges": sorted(
            edges.values(),
            key=lambda e: (e["transition_strength"], e["count"]),
            reverse=True,
        )[:30],
        "top_nodes": sorted(
            node_data.values(),
            key=lambda n: n["centrality_score"],
            reverse=True,
        )[:30],
    }


def build_compression(
    timeline: dict[str, Any],
    results_dir: str,
) -> dict[str, Any]:
    rules = {}
    for rule_id, payload in sorted(timeline.get("rules", {}).items()):
        rules[rule_id] = build_rule_compression(rule_id, payload)
    global_transitions = build_global_transitions(rules)
    total_raw = sum(
        rule["summary"]["raw_timeline_event_count"]
        for rule in rules.values()
    )
    total_canonical = sum(
        rule["summary"]["compressed_timeline_event_count"]
        for rule in rules.values()
    )
    global_summary = {
        "rule_count": len(rules),
        "raw_timeline_event_count": total_raw,
        "compressed_timeline_event_count": total_canonical,
        "compressed_away_count": total_raw - total_canonical,
        "global_compression_ratio": (
            total_raw - total_canonical
        ) / max(1, total_raw),
        "segment_count": sum(
            rule["summary"]["segment_count"] for rule in rules.values()
        ),
        "transition_node_count": global_transitions["node_count"],
        "transition_edge_count": global_transitions["edge_count"],
        "mean_rule_compression_ratio": mean([
            rule["summary"]["compression_ratio"] for rule in rules.values()
        ]),
    }
    return {
        "schema": "universe_search_timeline_compression_v10",
        "results_dir": results_dir,
        "global_summary": global_summary,
        "rules": rules,
        "global_transitions": global_transitions,
    }


def build_report(compression: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "universe_search_timeline_compression_report_v10",
        "results_dir": compression.get("results_dir"),
        "global_summary": compression["global_summary"],
        "top_compressed_transitions": compression["global_transitions"][
            "top_edges"
        ][:20],
        "top_compressed_nodes": compression["global_transitions"][
            "top_nodes"
        ][:20],
        "rule_summaries": {
            rule_id: rule["summary"]
            for rule_id, rule in compression["rules"].items()
        },
    }
