"""Persistent snapshot history and scientific-view-aware growth."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from Analyzer_next.core.meta_science.constants import HISTORY_SCHEMA, SCIENTIFIC_VIEW_SCHEMA
from Analyzer_next.core.meta_science.numeric import sf, si, ss


def update_history(
    existing: dict[str, Any],
    snapshot: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    history = deepcopy(existing) if isinstance(existing, dict) else {}
    history.setdefault("schema", HISTORY_SCHEMA)
    history.setdefault("created", now)
    history["schema"] = HISTORY_SCHEMA
    history["updated"] = now
    history.setdefault("snapshots", [])

    metrics = snapshot.get("research_metrics", {})
    age = snapshot.get("knowledge_age", {})
    inputs = snapshot.get("inputs_seen", {})
    entry = {
        "time": snapshot.get("generated", now),
        "observer_profiles": si(inputs.get("observer_profiles")),
        "principles_total": si(metrics.get("principles_total")),
        "observations": si(age.get("observations")),
        "promising": si(age.get("promising")),
        "supported": si(age.get("supported")),
        "strong": si(age.get("strong")),
        "consensus": si(age.get("consensus")),
        "foundational": si(age.get("foundational")),
        "disputed": si(age.get("disputed")),
        "support_total": si(metrics.get("support_total")),
        "counterexamples_total": si(metrics.get("counterexamples_total")),
        "knowledge_maturity_score": sf(metrics.get("knowledge_maturity_score")),
        "scientific_stability_score": sf(metrics.get("scientific_stability_score")),
        "research_velocity_score": sf(metrics.get("research_velocity_score")),
        "knowledge_efficiency_score": sf(metrics.get("knowledge_efficiency_score")),
        "scientific_health_index": sf(snapshot.get("scientific_health", {}).get("index")),
        "primary_bottleneck": ss(snapshot.get("bottlenecks", {}).get("primary", {}).get("component")),
        "scientific_view_schema": snapshot.get("scientific_view", {}).get("schema", SCIENTIFIC_VIEW_SCHEMA),
        "scientific_scope_signature": snapshot.get("scientific_view", {}).get("scope_signature"),
        "scientific_rule_count": si(snapshot.get("scientific_view", {}).get("rule_count")),
    }

    snapshots = history["snapshots"]
    if not isinstance(snapshots, list):
        snapshots = []
        history["snapshots"] = snapshots
    tail = snapshots[-1] if snapshots else None
    compare_keys = [key for key in entry if key != "time"]
    if not isinstance(tail, dict) or any(tail.get(key) != entry.get(key) for key in compare_keys):
        snapshots.append(entry)
    history["snapshots"] = snapshots[-1000:]
    return history


def compute_growth(snapshot: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    snapshots = history.get("snapshots", []) if isinstance(history, dict) else []
    if isinstance(snapshots, list):
        snapshots = [
            entry for entry in snapshots
            if isinstance(entry, dict)
            and entry.get("scientific_view_schema") == SCIENTIFIC_VIEW_SCHEMA
        ]
    if not isinstance(snapshots, list) or len(snapshots) < 2:
        return {
            "has_previous": False,
            "baseline_reason": "SCIENTIFIC_VIEW_REBASELINE",
            "new_observations": 0,
            "new_promising": 0,
            "new_supported_or_higher": 0,
            "new_disputed": 0,
            "maturity_delta": 0.0,
            "stability_delta": 0.0,
            "efficiency_delta": 0.0,
            "scientific_health_delta": 0.0,
        }
    previous = snapshots[-2]
    current = snapshots[-1]
    supported_keys = ["supported", "strong", "consensus", "foundational"]
    return {
        "has_previous": True,
        "baseline_reason": None,
        "new_observations": si(current.get("observations")) - si(previous.get("observations")),
        "new_promising": si(current.get("promising")) - si(previous.get("promising")),
        "new_supported_or_higher": sum(
            si(current.get(key)) - si(previous.get(key)) for key in supported_keys
        ),
        "new_disputed": si(current.get("disputed")) - si(previous.get("disputed")),
        "maturity_delta": round(sf(current.get("knowledge_maturity_score")) - sf(previous.get("knowledge_maturity_score")), 4),
        "stability_delta": round(sf(current.get("scientific_stability_score")) - sf(previous.get("scientific_stability_score")), 4),
        "efficiency_delta": round(sf(current.get("knowledge_efficiency_score")) - sf(previous.get("knowledge_efficiency_score")), 4),
        "scientific_health_delta": round(sf(current.get("scientific_health_index")) - sf(previous.get("scientific_health_index")), 4),
    }
