"""Orchestrate deterministic causal-graph projections in memory."""
from __future__ import annotations

from collections import Counter
from typing import Any

from Analyzer_next.core.causal_graph.contracts import (
    CausalGraphInputs,
    CausalGraphPaths,
    CausalGraphRunResult,
)
from Analyzer_next.core.causal_graph.graphs import (
    build_causal_tree_from_sequences,
    build_mechanism_hypotheses,
    build_rule_family_fingerprint,
    build_transition_graph,
    merge_global_motifs,
)
from Analyzer_next.core.causal_graph.motifs import (
    event_sort_key,
    event_type,
    extract_motifs,
)


class CausalGraphOrchestrator:
    def run(
        self,
        paths: CausalGraphPaths,
        inputs: CausalGraphInputs,
    ) -> CausalGraphRunResult:
        report = build_report(inputs.fused_events, str(paths.results_root))
        return CausalGraphRunResult(report=report)


def build_report(
    source: dict[str, Any],
    results_dir: str,
) -> dict[str, Any]:
    fused = source.get("fused_events", {})
    rule_graphs: dict[str, dict[str, Any]] = {}
    family_fingerprints: dict[str, dict[str, Any]] = {}

    for rid, payload in sorted(fused.items()):
        events = sorted(payload.get("fused_events", []), key=event_sort_key)
        graph = build_transition_graph(events)
        motif_info = extract_motifs(rid, events)
        fingerprint = build_rule_family_fingerprint(
            rid, events, motif_info
        )
        rule_graphs[rid] = {
            "rule_id": rid,
            "raw_fused_event_count": len(events),
            "start_node": event_type(events[0]) if events else "NONE",
            "terminal_node": event_type(events[-1]) if events else "NONE",
            "sequence": motif_info["sequence"],
            "sequence_text": motif_info["sequence_text"],
            "compact_sequence": motif_info["compact_sequence"],
            "compact_sequence_text": motif_info["compact_sequence_text"],
            "family_sequence": motif_info["family_sequence"],
            "family_sequence_text": motif_info["family_sequence_text"],
            "compact_family_sequence": motif_info[
                "compact_family_sequence"
            ],
            "compact_family_sequence_text": motif_info[
                "compact_family_sequence_text"
            ],
            "graph": graph,
            "motif_info": motif_info,
            "family_fingerprint": fingerprint,
        }
        family_fingerprints[rid] = fingerprint

    global_motifs = merge_global_motifs(rule_graphs)
    causal_tree = build_causal_tree_from_sequences(rule_graphs)
    hypotheses = build_mechanism_hypotheses(global_motifs, causal_tree)
    archetypes = Counter(
        item["mechanism_archetype"]
        for item in family_fingerprints.values()
    )
    return {
        "schema": "universe_search_causal_graph_stage3_v10",
        "results_dir": results_dir,
        "source_schema": source.get("schema"),
        "rules_analyzed": len(rule_graphs),
        "rule_graphs": rule_graphs,
        "global_motifs": global_motifs,
        "causal_tree": causal_tree,
        "mechanism_hypotheses": hypotheses,
        "global_family_fingerprints": {
            "archetype_counts": dict(archetypes),
            "rule_fingerprints": family_fingerprints,
        },
    }
