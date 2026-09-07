"""Compose deterministic timeline projections over injected documents."""
from __future__ import annotations

import time
from collections.abc import Callable

from Analyzer_next.core.mechanism_timeline.analysis import (
    build_atomic_family_map,
    build_composition_lookup,
    build_global_summary,
    build_global_transitions,
    build_report,
    build_rule_timeline,
)
from Analyzer_next.core.mechanism_timeline.contracts import (
    MechanismTimelineInputs,
    MechanismTimelinePaths,
    MechanismTimelineProgress,
    MechanismTimelineRunResult,
)


class MechanismTimelineOrchestrator:
    def __init__(
        self,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._clock = clock

    def run(
        self,
        paths: MechanismTimelinePaths,
        inputs: MechanismTimelineInputs,
        progress: MechanismTimelineProgress | None = None,
    ) -> MechanismTimelineRunResult:
        sources = inputs.as_sources()
        fused = inputs.fused.get("fused_events", {})
        atomic_map = build_atomic_family_map(inputs.mechanism_registry)
        composition_lookup = build_composition_lookup(sources)
        rules = {}
        items = sorted(fused.items())
        total = len(items)
        for index, (rule_id, payload) in enumerate(items, start=1):
            started = self._clock()
            rules[rule_id] = build_rule_timeline(
                rule_id,
                payload,
                atomic_map,
                composition_lookup,
            )
            elapsed = self._clock() - started
            if progress is not None:
                progress(
                    index,
                    total,
                    rule_id,
                    rules[rule_id].get("timeline_event_count", 0),
                    elapsed,
                )
        global_transitions = build_global_transitions(rules)
        timeline = {
            "schema": "universe_search_mechanism_timeline_v10",
            "results_dir": str(paths.results_root),
            "rule_count": len(rules),
            "rules": rules,
            "global_summary": build_global_summary(
                rules, global_transitions
            ),
            "global_transitions": global_transitions,
        }
        return MechanismTimelineRunResult(
            timeline=timeline,
            report=build_report(timeline, paths.results_root),
        )
