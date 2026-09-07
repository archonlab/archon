"""Pure event-family and motif analysis for Causal Graph Builder."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple



MOTIF_LENGTHS = [2, 3, 4, 5]

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

RECOVERY_EVENTS = {"STRUCTURAL_EXPANSION_EVENT", "REORGANIZATION_EVENT", "REVIVAL_EVENT", "ORDERING_EVENT"}
COLLAPSE_EVENTS = {"COLLAPSE_EVENT", "FRAGMENTATION_EVENT"}
DORMANCY_EVENTS = {"DORMANCY_TRANSITION"}


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


def event_sort_key(event: Dict[str, Any]) -> Tuple[int, str]:
    return (
        int(event.get("center_tick", event.get("start_tick", 0))),
        str(event.get("fused_event_id", "")),
    )


def event_type(event: Dict[str, Any]) -> str:
    return str(event.get("fused_event_type", "UNKNOWN_EVENT"))


def event_tick(event: Dict[str, Any]) -> int:
    return int(event.get("center_tick", event.get("start_tick", event.get("end_tick", 0))))


def event_family(etype: str) -> str:
    return EVENT_TO_FAMILY.get(etype, "Other")


def motif_key(items: List[str]) -> str:
    return " -> ".join(items)


def family_key(items: List[str]) -> str:
    return " -> ".join(event_family(x) for x in items)


def compact_sequence(seq: List[str]) -> List[str]:
    out = []
    for item in seq:
        if not out or out[-1] != item:
            out.append(item)
    return out


def is_true_cycle(items: List[str]) -> bool:
    """
    True cycle means the sequence returns to a previously visited state after
    passing through at least one different state.

    A -> A is repetition, not cycle.
    A -> A -> B is repetition, not cycle.
    A -> B -> A is cycle.
    A -> B -> B is not cycle unless A repeats later.
    """
    if len(items) < 3:
        return False
    for i, item in enumerate(items):
        if item in items[:i]:
            prev_i = items[:i].index(item)
            middle = items[prev_i + 1:i]
            if middle and any(x != item for x in middle):
                return True
    return False


def is_repetition(items: List[str]) -> bool:
    return len(items) >= 2 and len(set(items)) == 1


def has_collapse_recurrence(items: List[str]) -> bool:
    if items.count("COLLAPSE_EVENT") >= 2:
        # A collapse recurrence is stronger if separated by another event.
        positions = [i for i, x in enumerate(items) if x == "COLLAPSE_EVENT"]
        for a, b in zip(positions, positions[1:]):
            if b - a > 1:
                return True
        return True
    return False


def has_recovery(items: List[str]) -> bool:
    for i, x in enumerate(items):
        if x in COLLAPSE_EVENTS and any(y in RECOVERY_EVENTS for y in items[i + 1:]):
            return True
    return False


def mechanism_label_for_family(families: List[str]) -> str:
    text = " -> ".join(families)
    mapping = {
        "Collapse -> Recovery": "POST_COLLAPSE_RECOVERY",
        "Recovery -> Collapse": "UNSTABLE_GROWTH_COLLAPSE",
        "Collapse -> Dormancy": "POST_COLLAPSE_DORMANCY",
        "Dormancy -> Recovery": "DORMANCY_REACTIVATION",
        "Dormancy -> Collapse": "DORMANCY_DECAY",
        "Recovery -> Dormancy": "SETTLING_AFTER_RECOVERY",
        "Collapse -> Recovery -> Collapse": "FAILED_RECOVERY_LOOP",
        "Recovery -> Collapse -> Recovery": "OSCILLATING_RECOVERY",
        "Dormancy -> Collapse -> Recovery": "DORMANT_COLLAPSE_RECOVERY",
        "Recovery -> Collapse -> Dormancy": "GROWTH_COLLAPSE_SETTLING",
        "Collapse -> Collapse": "CASCADED_COLLAPSE",
        "Recovery -> Recovery": "SUSTAINED_RECOVERY",
    }
    return mapping.get(text, "GENERALIZED_" + "_".join(families).upper())


def sequence_from_events(events: List[Dict[str, Any]], compact: bool = False) -> List[str]:
    seq = [event_type(e) for e in sorted(events, key=event_sort_key)]
    return compact_sequence(seq) if compact else seq


def ticks_from_events(events: List[Dict[str, Any]]) -> List[int]:
    return [event_tick(e) for e in sorted(events, key=event_sort_key)]


def extract_motifs(rule_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    sorted_events = sorted(events, key=event_sort_key)
    seq = sequence_from_events(sorted_events, compact=False)
    cseq = sequence_from_events(sorted_events, compact=True)
    ticks = ticks_from_events(sorted_events)

    motifs = defaultdict(lambda: {
        "motif": [],
        "count": 0,
        "durations": [],
        "examples": [],
    })

    compact_motifs = defaultdict(lambda: {
        "motif": [],
        "count": 0,
        "examples": [],
    })

    family_motifs = defaultdict(lambda: {
        "family_motif": [],
        "event_motifs": Counter(),
        "count": 0,
        "durations": [],
        "examples": [],
    })

    for length in MOTIF_LENGTHS:
        if len(seq) >= length:
            for i in range(len(seq) - length + 1):
                win = seq[i:i + length]
                key = motif_key(win)
                duration = max(0, ticks[i + length - 1] - ticks[i])
                motifs[key]["motif"] = win
                motifs[key]["count"] += 1
                motifs[key]["durations"].append(duration)
                if len(motifs[key]["examples"]) < 5:
                    motifs[key]["examples"].append({
                        "rule_id": rule_id,
                        "start_tick": ticks[i],
                        "end_tick": ticks[i + length - 1],
                        "duration_ticks": duration,
                        "event_ids": [sorted_events[j].get("fused_event_id") for j in range(i, i + length)],
                    })

                fwin = [event_family(x) for x in win]
                fkey = motif_key(fwin)
                family_motifs[fkey]["family_motif"] = fwin
                family_motifs[fkey]["event_motifs"][key] += 1
                family_motifs[fkey]["count"] += 1
                family_motifs[fkey]["durations"].append(duration)
                if len(family_motifs[fkey]["examples"]) < 5:
                    family_motifs[fkey]["examples"].append({
                        "rule_id": rule_id,
                        "start_tick": ticks[i],
                        "end_tick": ticks[i + length - 1],
                        "duration_ticks": duration,
                        "event_motif": win,
                    })

        if len(cseq) >= length:
            for i in range(len(cseq) - length + 1):
                win = cseq[i:i + length]
                key = motif_key(win)
                compact_motifs[key]["motif"] = win
                compact_motifs[key]["count"] += 1
                if len(compact_motifs[key]["examples"]) < 5:
                    compact_motifs[key]["examples"].append({
                        "rule_id": rule_id,
                        "compact_index": i,
                    })

    def finalize_motif(key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        items = data["motif"]
        return {
            "motif": items,
            "motif_text": key,
            "family_motif": [event_family(x) for x in items],
            "family_motif_text": family_key(items),
            "mechanism_label": mechanism_label_for_family([event_family(x) for x in items]),
            "length": len(items),
            "count": data["count"],
            "mean_duration_ticks": mean(data.get("durations", [])),
            "duration_stdev_ticks": stdev(data.get("durations", [])),
            "is_true_cycle": is_true_cycle(items),
            "is_repetition": is_repetition(items),
            "has_collapse_recurrence": has_collapse_recurrence(items),
            "has_recovery": has_recovery(items),
            "examples": data.get("examples", []),
        }

    def finalize_compact(key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        items = data["motif"]
        return {
            "motif": items,
            "motif_text": key,
            "family_motif": [event_family(x) for x in items],
            "family_motif_text": family_key(items),
            "mechanism_label": mechanism_label_for_family([event_family(x) for x in items]),
            "length": len(items),
            "count": data["count"],
            "is_true_cycle": is_true_cycle(items),
            "is_repetition": is_repetition(items),
            "has_collapse_recurrence": has_collapse_recurrence(items),
            "has_recovery": has_recovery(items),
            "examples": data.get("examples", []),
        }

    def finalize_family(key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        families = data["family_motif"]
        variants = data["event_motifs"]
        return {
            "family_motif": families,
            "family_motif_text": key,
            "mechanism_label": mechanism_label_for_family(families),
            "length": len(families),
            "count": data["count"],
            "event_variant_count": len(variants),
            "event_variants": dict(variants),
            "mean_duration_ticks": mean(data.get("durations", [])),
            "duration_stdev_ticks": stdev(data.get("durations", [])),
            "is_true_cycle": is_true_cycle(families),
            "is_repetition": is_repetition(families),
            "has_collapse_recurrence": families.count("Collapse") >= 2,
            "has_recovery": "Collapse" in families and any(x == "Recovery" for x in families[families.index("Collapse") + 1:]),
            "examples": data.get("examples", []),
        }

    motif_out = {k: finalize_motif(k, v) for k, v in motifs.items()}
    compact_out = {k: finalize_compact(k, v) for k, v in compact_motifs.items()}
    family_out = {k: finalize_family(k, v) for k, v in family_motifs.items()}

    return {
        "rule_id": rule_id,
        "sequence": seq,
        "sequence_text": motif_key(seq) if seq else "NONE",
        "compact_sequence": cseq,
        "compact_sequence_text": motif_key(cseq) if cseq else "NONE",
        "family_sequence": [event_family(x) for x in seq],
        "family_sequence_text": motif_key([event_family(x) for x in seq]) if seq else "NONE",
        "compact_family_sequence": [event_family(x) for x in cseq],
        "compact_family_sequence_text": motif_key([event_family(x) for x in cseq]) if cseq else "NONE",
        "motifs": motif_out,
        "compact_motifs": compact_out,
        "family_motifs": family_out,
        "true_cycle_motifs": {k: v for k, v in motif_out.items() if v["is_true_cycle"]},
        "repetition_motifs": {k: v for k, v in motif_out.items() if v["is_repetition"]},
        "recovery_motifs": {k: v for k, v in motif_out.items() if v["has_recovery"]},
        "collapse_recurrence_motifs": {k: v for k, v in motif_out.items() if v["has_collapse_recurrence"]},
    }


