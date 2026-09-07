"""Advisory action-signal derivation, dependency handling, and ranking."""
from __future__ import annotations

from typing import Any

from .constants import ACTION_SIGNAL_PRIORITY, SIGNAL_BASE_SCORE
from .numeric import si, ss

def build_consensus_action_signals(
    *,
    principle_id: str,
    legacy_status: str,
    channel_aware_status: str,
    confidence_posture: str,
    experimental_picture: str,
    perturbation_picture: str,
    evidence_gaps: list[str],
    flags: dict[str, Any],
    counterexample_coverage_status: str,
    independent_seed_coverage: float,
    experimental_unique_experiments: int,
    experimental_unique_rules: int,
) -> dict[str, Any]:
    """Translate interpretation and evidence gaps into Director-ready signals.

    Signals are advisory only. They do not launch work, reprioritize Director,
    or change consensus score/status.
    """
    signals: list[dict[str, Any]] = []

    def add(
        signal_id: str,
        signal_type: str,
        priority: str,
        rationale: str,
        *,
        source_gaps: list[str] | None = None,
        suggested_target: str = "",
    ) -> None:
        signals.append({
            "signal_id": f"{principle_id}::{signal_id}",
            "signal_type": signal_type,
            "priority": priority,
            "rationale": rationale,
            "source_gaps": list(source_gaps or []),
            "suggested_target": suggested_target,
            "automatic_execution": False,
            "director_priority_effect": False,
        })

    gaps = set(evidence_gaps)

    if (
        independent_seed_coverage <= 0.0
        or "test_additional_independent_rules" in gaps
        or "extend_experimental_horizon" in gaps
    ):
        add(
            "CAS-001",
            "needs_replication",
            "HIGH" if confidence_posture == "CAUTIOUS" else "MEDIUM",
            (
                "The principle lacks sufficient independent replication "
                "across seeds, rules, or horizons."
            ),
            source_gaps=sorted(
                gaps.intersection({
                    "test_additional_independent_rules",
                    "extend_experimental_horizon",
                })
            ),
            suggested_target="independent_seed_rule_horizon_replication",
        )

    if (
        bool(flags.get("experimental_scope_challenge"))
        or "resolve_experimental_scope_challenge" in gaps
        or "CHALLENGE" in experimental_picture
    ):
        add(
            "CAS-002",
            "needs_scope_test",
            "HIGH",
            (
                "Controlled evidence indicates that the principle may depend "
                "on initial state, calibration, or experimental conditions."
            ),
            source_gaps=[
                gap for gap in (
                    "resolve_experimental_scope_challenge",
                    "test_additional_conditions",
                )
                if gap in gaps
            ],
            suggested_target="matched_scope_boundary_experiment",
        )

    if (
        counterexample_coverage_status == "UNTESTED_REGIME"
        or "targeted_counterexample_search" in gaps
    ):
        add(
            "CAS-003",
            "needs_counterexample_search",
            "HIGH",
            (
                "Opposing regimes remain untested or no targeted "
                "counterexample search has closed the declared gap."
            ),
            source_gaps=[
                "targeted_counterexample_search"
            ] if "targeted_counterexample_search" in gaps else [],
            suggested_target="adversarial_counterexample_search",
        )

    if (
        bool(flags.get("perturbation_mixed_signal"))
        or perturbation_picture == "MIXED"
    ):
        add(
            "CAS-004",
            "needs_perturbation_resolution",
            "HIGH",
            (
                "Perturbation outcomes are mixed and require matched controls "
                "or additional parent-rule coverage."
            ),
            suggested_target="matched_perturbation_resolution",
        )
    elif perturbation_picture == "INSUFFICIENT":
        add(
            "CAS-005",
            "needs_perturbation_evidence",
            "MEDIUM",
            (
                "The perturbation channel has insufficient informative cases "
                "for robustness interpretation."
            ),
            source_gaps=[
                "collect_informative_perturbation_evidence"
            ] if "collect_informative_perturbation_evidence" in gaps else [],
            suggested_target="informative_controlled_perturbations",
        )

    if experimental_picture == "UNTESTED":
        add(
            "CAS-006",
            "needs_controlled_experiment",
            "MEDIUM",
            (
                "No mapped controlled experiment currently informs this "
                "principle."
            ),
            source_gaps=[
                "run_controlled_experiment"
            ] if "run_controlled_experiment" in gaps else [],
            suggested_target="first_principle_targeted_experiment",
        )

    ready = (
        legacy_status in {"SUPPORTED", "STRONG", "CONSENSUS", "FOUNDATIONAL"}
        and channel_aware_status in {
            "EXPERIMENTALLY_CORROBORATED",
            "MULTI_CHANNEL_CORROBORATION",
        }
        and counterexample_coverage_status in {
            "TESTED_REGIME",
            "COUNTEREXAMPLES_FOUND",
        }
        and independent_seed_coverage > 0.0
        and experimental_unique_experiments >= 2
        and experimental_unique_rules >= 2
        and not flags.get("cross_channel_tension")
    )
    if ready:
        add(
            "CAS-007",
            "ready_for_broader_validation",
            "LOW",
            (
                "The principle has sufficient cross-channel support to justify "
                "broader validation rather than immediate gap repair."
            ),
            suggested_target="broader_validation_program",
        )

    signals.sort(
        key=lambda item: (
            ACTION_SIGNAL_PRIORITY.get(item["priority"], 0),
            item["signal_type"],
        ),
        reverse=True,
    )

    highest_priority = (
        signals[0]["priority"] if signals else "NONE"
    )
    return {
        "schema": "archon_consensus_action_signals_v1",
        "principle_id": principle_id,
        "signal_count": len(signals),
        "highest_priority": highest_priority,
        "signals": signals,
        "scientific_policy": {
            "advisory_only": True,
            "automatic_execution": False,
            "director_priority_effect": False,
            "consensus_score_changed": False,
            "consensus_status_changed": False,
        },
    }

def prioritize_consensus_action_signals(
    action_bundle: dict[str, Any],
    *,
    experimental_picture: str,
    perturbation_picture: str,
) -> dict[str, Any]:
    """Prioritize, deduplicate, and order advisory action signals."""
    raw_signals = (
        action_bundle.get("signals", [])
        if isinstance(action_bundle, dict)
        else []
    )
    if not isinstance(raw_signals, list):
        raw_signals = []

    # Keep one strongest instance of each signal type.
    deduplicated: dict[str, dict[str, Any]] = {}
    for signal in raw_signals:
        if not isinstance(signal, dict):
            continue
        signal_type = ss(signal.get("signal_type"), "unknown")
        priority = ss(signal.get("priority"), "NONE")
        base_score = SIGNAL_BASE_SCORE.get(signal_type, 20)
        priority_bonus = 5 * ACTION_SIGNAL_PRIORITY.get(priority, 0)
        score = base_score + priority_bonus

        item = dict(signal)
        item["priority_score"] = score
        item["blocked_by"] = []
        item["supersedes"] = []

        previous = deduplicated.get(signal_type)
        if (
            previous is None
            or si(item.get("priority_score"))
            > si(previous.get("priority_score"))
        ):
            deduplicated[signal_type] = item

    signals = list(deduplicated.values())
    by_type = {
        ss(signal.get("signal_type")): signal
        for signal in signals
    }

    # Dependency policy.
    controlled = by_type.get("needs_controlled_experiment")
    replication = by_type.get("needs_replication")
    scope_test = by_type.get("needs_scope_test")
    perturbation_resolution = by_type.get(
        "needs_perturbation_resolution"
    )
    perturbation_evidence = by_type.get(
        "needs_perturbation_evidence"
    )
    counterexample_search = by_type.get(
        "needs_counterexample_search"
    )

    if controlled and experimental_picture == "UNTESTED":
        if replication:
            replication["blocked_by"].append(
                "needs_controlled_experiment"
            )
            controlled["supersedes"].append(
                "needs_replication_as_first_step"
            )

    if scope_test:
        if replication:
            replication["blocked_by"].append("needs_scope_test")
            scope_test["supersedes"].append(
                "generic_replication_until_scope_is_resolved"
            )

    if perturbation_resolution and perturbation_evidence:
        perturbation_evidence["blocked_by"].append(
            "needs_perturbation_resolution"
        )
        perturbation_resolution["supersedes"].append(
            "generic_perturbation_evidence_collection"
        )

    if (
        counterexample_search
        and scope_test
        and experimental_picture.startswith("LIMITED_SCOPE")
    ):
        counterexample_search["blocked_by"].append("needs_scope_test")

    active = [
        signal
        for signal in signals
        if not signal.get("blocked_by")
    ]
    blocked = [
        signal
        for signal in signals
        if signal.get("blocked_by")
    ]

    active.sort(
        key=lambda item: (
            si(item.get("priority_score")),
            ACTION_SIGNAL_PRIORITY.get(
                ss(item.get("priority"), "NONE"),
                0,
            ),
            ss(item.get("signal_type")),
        ),
        reverse=True,
    )
    blocked.sort(
        key=lambda item: (
            si(item.get("priority_score")),
            ss(item.get("signal_type")),
        ),
        reverse=True,
    )

    primary = active[0] if active else None
    secondary = active[1:]

    return {
        "schema": "archon_prioritized_consensus_actions_v1",
        "primary_signal": primary,
        "secondary_signals": secondary,
        "blocked_signals": blocked,
        "raw_signal_count": len(raw_signals),
        "deduplicated_signal_count": len(signals),
        "active_signal_count": len(active),
        "blocked_signal_count": len(blocked),
        "highest_priority": (
            ss(primary.get("priority"), "NONE")
            if isinstance(primary, dict)
            else "NONE"
        ),
        "priority_score": (
            si(primary.get("priority_score"))
            if isinstance(primary, dict)
            else 0
        ),
        "scientific_policy": {
            "advisory_only": True,
            "automatic_execution": False,
            "director_priority_effect": False,
            "dependency_aware": True,
            "deduplicated_by_signal_type": True,
            "consensus_score_changed": False,
            "consensus_status_changed": False,
        },
    }

