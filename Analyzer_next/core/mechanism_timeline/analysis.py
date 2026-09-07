"""Deterministic scientific analysis for time-ordered mechanisms."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EVENT_TO_FAMILY = {
    "COLLAPSE_EVENT": "Collapse",
    "FRAGMENTATION_EVENT": "Collapse",
    "STRUCTURAL_EXPANSION_EVENT": "Recovery",
    "REORGANIZATION_EVENT": "Recovery",
    "REVIVAL_EVENT": "Recovery",
    "ORDERING_EVENT": "Recovery",
    "DORMANCY_TRANSITION": "Dormancy",
    "MIXED_SIGNAL_EVENT": "Transition",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = mean(values)
    return math.sqrt(
        sum((value - average) ** 2 for value in values) / (len(values) - 1)
    )


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def event_type(event: dict[str, Any]) -> str:
    return str(event.get("fused_event_type", "UNKNOWN_EVENT"))


def event_family(event_or_type: Any) -> str:
    event_name = (
        event_or_type
        if isinstance(event_or_type, str)
        else event_type(event_or_type)
    )
    return EVENT_TO_FAMILY.get(event_name, "Other")


def event_tick(event: dict[str, Any]) -> int:
    return int(
        event.get(
            "center_tick",
            event.get("start_tick", event.get("end_tick", 0)),
        )
    )


def event_sort_key(event: dict[str, Any]) -> tuple[int, str]:
    return event_tick(event), str(event.get("fused_event_id", ""))


def family_text(parts: list[str]) -> str:
    return " -> ".join(parts)


def build_atomic_family_map(
    mechanism_registry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result = {}
    for mechanism_id, mechanism in mechanism_registry.get(
        "mechanisms", {}
    ).items():
        motif_text = mechanism.get("family_motif_text")
        if motif_text:
            result[motif_text] = {
                "mechanism_id": mechanism_id,
                "label": mechanism.get("label", mechanism_id),
                "category": mechanism.get("category", "unknown"),
                "confidence": safe_float(
                    mechanism.get("scores", {}).get("registry_confidence"),
                    0.0,
                ),
            }
    return result


def build_composition_lookup(
    sources: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Map family motif text to composition and template information."""
    result = {}
    composition_registry = sources.get("composition_registry", {})
    for composition_id, composition in composition_registry.get(
        "compositions", {}
    ).items():
        motif_text = composition.get("family_motif_text")
        if motif_text:
            result[motif_text] = {
                "composition_id": composition_id,
                "composition_label": composition.get(
                    "label", composition_id
                ),
                "composition_category": composition.get("category"),
                "composition_confidence": safe_float(
                    composition.get("scores", {}).get(
                        "composition_confidence"
                    ),
                    0.0,
                ),
                "atomic_mechanism_ids": composition.get(
                    "atomic_mechanism_ids", []
                ),
            }

    instances = sources.get("composition_instances", {})
    for instance_id, instance in instances.get("instances", {}).items():
        motif_text = instance.get("family_motif_text")
        if motif_text:
            result.setdefault(motif_text, {})
            result[motif_text].update({
                "instance_id": instance_id,
                "template_id": instance.get("template_id"),
                "template_label": instance.get("template_label"),
                "template_classification_score": safe_float(
                    instance.get("scores", {}).get(
                        "template_classification_score"
                    ),
                    0.0,
                ),
            })
    return result


def make_atomic_event(
    rule_id: str,
    first: dict[str, Any],
    second: dict[str, Any],
    atomic_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    first_family = event_family(first)
    second_family = event_family(second)
    transition = f"{first_family} -> {second_family}"
    info = atomic_map.get(transition, {})
    start_tick = event_tick(first)
    end_tick = event_tick(second)
    duration = max(0, end_tick - start_tick)
    severity = mean([
        safe_float(first.get("severity")),
        safe_float(second.get("severity")),
    ])
    confidence = mean([
        safe_float(first.get("confidence")),
        safe_float(second.get("confidence")),
        safe_float(info.get("confidence")),
    ])
    return {
        "timeline_event_id": None,
        "rule_id": rule_id,
        "kind": "atomic_mechanism",
        "start_tick": start_tick,
        "end_tick": end_tick,
        "center_tick": int(round((start_tick + end_tick) / 2)),
        "duration_ticks": duration,
        "source_fused_event_ids": [
            first.get("fused_event_id"),
            second.get("fused_event_id"),
        ],
        "source_fused_event_types": [
            event_type(first),
            event_type(second),
        ],
        "family_transition": transition,
        "mechanism_id": info.get("mechanism_id"),
        "mechanism_label": info.get(
            "label", "UNKNOWN_ATOMIC_MECHANISM"
        ),
        "mechanism_category": info.get("category", "unknown"),
        "template_id": None,
        "template_label": None,
        "composition_id": None,
        "composition_label": None,
        "severity": severity,
        "confidence": confidence,
    }


def make_composition_event(
    rule_id: str,
    window: list[dict[str, Any]],
    composition_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if len(window) < 3:
        return None
    transition = family_text([event_family(event) for event in window])
    info = composition_lookup.get(transition)
    if not info:
        return None
    ticks = [event_tick(event) for event in window]
    start_tick = min(ticks)
    end_tick = max(ticks)
    severity = mean([safe_float(event.get("severity")) for event in window])
    confidence = mean([
        mean([
            safe_float(event.get("confidence")) for event in window
        ]),
        safe_float(info.get("composition_confidence")),
        safe_float(info.get("template_classification_score")),
    ])
    return {
        "timeline_event_id": None,
        "rule_id": rule_id,
        "kind": "composition_template",
        "start_tick": start_tick,
        "end_tick": end_tick,
        "center_tick": int(round(mean(ticks))),
        "duration_ticks": max(0, end_tick - start_tick),
        "source_fused_event_ids": [
            event.get("fused_event_id") for event in window
        ],
        "source_fused_event_types": [
            event_type(event) for event in window
        ],
        "family_transition": transition,
        "mechanism_id": None,
        "mechanism_label": None,
        "mechanism_category": info.get(
            "composition_category", "unknown"
        ),
        "template_id": info.get("template_id"),
        "template_label": info.get("template_label"),
        "composition_id": info.get("composition_id"),
        "composition_label": info.get("composition_label"),
        "severity": severity,
        "confidence": confidence,
    }


def timeline_node_label(event: dict[str, Any]) -> str:
    if event.get("kind") == "atomic_mechanism":
        return event.get("mechanism_label") or "UNKNOWN_ATOMIC_MECHANISM"
    return (
        event.get("template_label")
        or event.get("composition_label")
        or "UNKNOWN_TEMPLATE"
    )


def build_timeline_transitions(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered = [
        event
        for event in events
        if event.get("kind")
        in ("atomic_mechanism", "composition_template")
    ]
    ordered.sort(key=lambda event: (
        event["center_tick"],
        event["start_tick"],
        event["end_tick"],
    ))
    result = []
    for first, second in zip(ordered, ordered[1:]):
        result.append({
            "source_timeline_event_id": first["timeline_event_id"],
            "target_timeline_event_id": second["timeline_event_id"],
            "source_label": timeline_node_label(first),
            "target_label": timeline_node_label(second),
            "source_kind": first.get("kind"),
            "target_kind": second.get("kind"),
            "source_tick": first["center_tick"],
            "target_tick": second["center_tick"],
            "delay_ticks": max(
                0, second["center_tick"] - first["center_tick"]
            ),
        })
    return result


def summarize_rule_timeline(
    rule_id: str,
    fused_events: list[dict[str, Any]],
    timeline_events: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
) -> dict[str, Any]:
    atomic_events = [
        event
        for event in timeline_events
        if event["kind"] == "atomic_mechanism"
    ]
    template_events = [
        event
        for event in timeline_events
        if event["kind"] == "composition_template"
    ]
    mechanism_counts = Counter(
        event.get("mechanism_label") for event in atomic_events
    )
    template_counts = Counter(
        event.get("template_label")
        for event in template_events
        if event.get("template_label")
    )
    category_counts = Counter(
        event.get("mechanism_category") for event in timeline_events
    )
    span = 0
    if fused_events:
        ticks = [event_tick(event) for event in fused_events]
        span = max(ticks) - min(ticks)
    delays = [transition["delay_ticks"] for transition in transitions]
    dominant_category = (
        category_counts.most_common(1)[0][0]
        if category_counts
        else "unknown"
    )
    return {
        "rule_id": rule_id,
        "timeline_span_ticks": span,
        "atomic_event_count": len(atomic_events),
        "template_event_count": len(template_events),
        "mechanism_counts": dict(mechanism_counts),
        "template_counts": dict(template_counts),
        "category_counts": dict(category_counts),
        "dominant_category": dominant_category,
        "transition_count": len(transitions),
        "mean_transition_delay_ticks": mean(delays),
        "transition_delay_stdev_ticks": stdev(delays),
        "mean_event_duration_ticks": mean([
            event["duration_ticks"] for event in timeline_events
        ]),
        "mean_confidence": mean([
            safe_float(event.get("confidence"))
            for event in timeline_events
        ]),
        "timeline_density": len(timeline_events) / max(1, span),
    }


def build_rule_timeline(
    rule_id: str,
    payload: dict[str, Any],
    atomic_map: dict[str, dict[str, Any]],
    composition_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    fused_events = sorted(
        payload.get("fused_events", []), key=event_sort_key
    )
    timeline_events = [
        make_atomic_event(rule_id, first, second, atomic_map)
        for first, second in zip(fused_events, fused_events[1:])
    ]
    for length in range(3, 6):
        if len(fused_events) < length:
            continue
        for index in range(len(fused_events) - length + 1):
            event = make_composition_event(
                rule_id,
                fused_events[index:index + length],
                composition_lookup,
            )
            if event:
                timeline_events.append(event)
    timeline_events.sort(key=lambda event: (
        event["start_tick"],
        event["end_tick"],
        event["kind"],
    ))
    for index, event in enumerate(timeline_events, start=1):
        event["timeline_event_id"] = f"TL-{rule_id}-{index:04d}"
    transitions = build_timeline_transitions(timeline_events)
    summary = summarize_rule_timeline(
        rule_id, fused_events, timeline_events, transitions
    )
    return {
        "rule_id": rule_id,
        "fused_event_count": len(fused_events),
        "timeline_event_count": len(timeline_events),
        "summary": summary,
        "timeline_events": timeline_events,
        "transitions": transitions,
    }


def build_global_transitions(
    rules: dict[str, Any],
) -> dict[str, Any]:
    edge_counts = Counter()
    edge_rules = defaultdict(set)
    edge_delays = defaultdict(list)
    for rule_id, item in rules.items():
        for transition in item.get("transitions", []):
            source = transition["source_label"]
            target = transition["target_label"]
            key = source, target
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
        edges[f"{source} -> {target}"] = {
            "source": source,
            "target": target,
            "count": count,
            "rules": sorted(edge_rules[(source, target)]),
            "rule_count": len(edge_rules[(source, target)]),
            "probability_from_source": count / max(1, outgoing[source]),
            "mean_delay_ticks": mean(delays),
            "delay_stdev_ticks": stdev(delays),
            "min_delay_ticks": min(delays) if delays else 0,
            "max_delay_ticks": max(delays) if delays else 0,
            "transition_strength": clamp01(
                0.40 * min(1.0, count / 5.0)
                + 0.35
                * min(1.0, len(edge_rules[(source, target)]) / 3.0)
                + 0.25 * (count / max(1, outgoing[source]))
            ),
        }

    node_counts = Counter()
    for (source, target), count in edge_counts.items():
        node_counts[source] += count
        node_counts[target] += count
    nodes = {}
    for node, count in node_counts.items():
        in_degree = len([1 for (_source, target) in edge_counts if target == node])
        out_degree = len([1 for (source, _target) in edge_counts if source == node])
        nodes[node] = {
            "node": node,
            "count": count,
            "incoming_count": incoming.get(node, 0),
            "outgoing_count": outgoing.get(node, 0),
            "in_degree": in_degree,
            "out_degree": out_degree,
            "centrality_score": clamp01(
                0.30 * min(1.0, count / 8.0)
                + 0.30 * min(1.0, incoming.get(node, 0) / 6.0)
                + 0.30 * min(1.0, outgoing.get(node, 0) / 6.0)
                + 0.10 * min(1.0, (in_degree + out_degree) / 6.0)
            ),
        }
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "top_edges": sorted(
            edges.values(),
            key=lambda edge: (
                edge["transition_strength"], edge["count"]
            ),
            reverse=True,
        )[:30],
        "top_nodes": sorted(
            nodes.values(),
            key=lambda node: node["centrality_score"],
            reverse=True,
        )[:30],
    }


def build_global_summary(
    rules: dict[str, Any],
    global_transitions: dict[str, Any],
) -> dict[str, Any]:
    category_counts = Counter()
    mechanism_counts = Counter()
    template_counts = Counter()
    timeline_counts = []
    densities = []
    delays = []
    for item in rules.values():
        summary = item["summary"]
        category_counts.update(summary.get("category_counts", {}))
        mechanism_counts.update(summary.get("mechanism_counts", {}))
        template_counts.update(summary.get("template_counts", {}))
        timeline_counts.append(item.get("timeline_event_count", 0))
        densities.append(summary.get("timeline_density", 0))
        delays.append(summary.get("mean_transition_delay_ticks", 0))
    return {
        "timeline_event_count": sum(timeline_counts),
        "mean_timeline_events_per_rule": mean(timeline_counts),
        "mean_timeline_density": mean(densities),
        "mean_transition_delay_ticks": mean(delays),
        "category_counts": dict(category_counts),
        "mechanism_counts": dict(mechanism_counts),
        "template_counts": dict(template_counts),
        "top_mechanisms": mechanism_counts.most_common(20),
        "top_templates": template_counts.most_common(20),
        "transition_node_count": global_transitions.get("node_count", 0),
        "transition_edge_count": global_transitions.get("edge_count", 0),
    }


def build_report(
    timeline: dict[str, Any],
    results_dir: Path,
) -> dict[str, Any]:
    return {
        "schema": "universe_search_mechanism_timeline_report_v10",
        "results_dir": str(results_dir),
        "rule_count": timeline.get("rule_count", 0),
        "global_summary": timeline.get("global_summary", {}),
        "top_transition_edges": timeline.get(
            "global_transitions", {}
        ).get("top_edges", [])[:20],
        "top_transition_nodes": timeline.get(
            "global_transitions", {}
        ).get("top_nodes", [])[:20],
        "rule_summaries": {
            rule_id: rule["summary"]
            for rule_id, rule in timeline.get("rules", {}).items()
        },
    }

