"""Reconcile mutation effects with canonical typed lifecycle observations.

Stage 2E is a descriptive shadow layer.  It compares the Mutation Analyzer's
technical zero-structure result with lifecycle events already persisted by the
Observer.  It never changes the mutation effect, lifecycle history, thresholds,
canonical evidence, or promotion policy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any


RECONCILIATION_SCHEMA_VERSION = "1.2.0"


def reconcile_perturbation_lifecycle(
    baseline_lifecycle: Mapping[str, Any] | None,
    mutant_lifecycle: Mapping[str, Any] | None,
    structural_extinction: Mapping[str, Any] | None,
    effect_interpretation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a non-canonical comparison of mutation and lifecycle semantics."""

    technical = (
        structural_extinction
        if isinstance(structural_extinction, Mapping)
        else {}
    )
    effect = (
        effect_interpretation
        if isinstance(effect_interpretation, Mapping)
        else {}
    )

    baseline_tick = _non_negative_int(
        technical.get("baseline_structural_extinction_tick")
    )
    mutant_tick = _non_negative_int(
        technical.get("mutant_structural_extinction_tick")
    )

    baseline = _arm_reconciliation(
        "baseline",
        baseline_lifecycle,
        technical_extinction_tick=baseline_tick,
    )
    mutant = _arm_reconciliation(
        "mutant",
        mutant_lifecycle,
        technical_extinction_tick=mutant_tick,
    )
    effect_relation = _effect_relation(
        str(effect.get("primary") or "unknown"),
        baseline,
        mutant,
    )

    relations = {baseline["relation"], mutant["relation"]}
    mismatch_fields: list[str] = []
    if baseline["relation"] == "criterion_mismatch":
        mismatch_fields.append("baseline.structural_extinction")
    if mutant["relation"] == "criterion_mismatch":
        mismatch_fields.append("mutant.structural_extinction")
    if effect_relation["status"] == "mismatch":
        mismatch_fields.append("effect_interpretation.primary")

    if mismatch_fields:
        status = "mismatch"
    elif effect_relation["status"] == "compatible_scope_difference":
        status = "compatible_scope_difference"
    elif "compatible_scope_difference" in relations:
        status = "compatible_scope_difference"
    elif effect_relation["status"] == "unavailable" or relations == {"unavailable"}:
        status = "unavailable"
    elif (
        effect_relation["status"] == "partial"
        or "partial" in relations
        or "unavailable" in relations
    ):
        status = "partial"
    else:
        status = "verified"

    return {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "mode": "shadow",
        "verification_status": status,
        "mismatch_fields": mismatch_fields,
        "baseline": baseline,
        "mutant": mutant,
        "effect_relation": effect_relation,
        "scientific_policy": {
            "changes_mutation_effect": False,
            "changes_lifecycle_history": False,
            "canonical_evidence": False,
            "automatic_promotion": False,
            "technical_zero_structure_is_life_verdict": False,
        },
    }


def _arm_reconciliation(
    arm: str,
    lifecycle: Mapping[str, Any] | None,
    *,
    technical_extinction_tick: int | None,
) -> dict[str, Any]:
    contract = lifecycle if isinstance(lifecycle, Mapping) else {}
    summary = (
        contract.get("summary")
        if isinstance(contract.get("summary"), Mapping)
        else {}
    )
    events = _event_list(contract.get("events"))
    event_types = {
        str(event.get("event_type"))
        for event in events
        if event.get("event_type")
    }
    if not event_types:
        raw_types = summary.get("event_types")
        if isinstance(raw_types, Sequence) and not isinstance(
            raw_types, (str, bytes, bytearray)
        ):
            event_types = {str(item) for item in raw_types}

    source = str(contract.get("canonical_source") or "unavailable")
    history_status = str(summary.get("history_status") or "unavailable")
    observed_through = _non_negative_int(summary.get("observed_through_tick"))
    history_complete = bool(
        summary.get("history_complete_for_supported_types")
    )
    source_resolution = (
        deepcopy(dict(contract.get("source_resolution")))
        if isinstance(contract.get("source_resolution"), Mapping)
        else {
            "status": "unavailable",
            "reason": "source_resolution_not_provided",
        }
    )
    temporal_integrity = (
        deepcopy(dict(contract.get("temporal_integrity")))
        if isinstance(contract.get("temporal_integrity"), Mapping)
        else {
            "status": "unavailable",
            "issue_count": 0,
            "issue_codes": [],
            "issues": [],
        }
    )
    temporal_status = str(
        temporal_integrity.get("status") or "unavailable"
    )
    typed_structural = "structural_extinction" in event_types
    typed_population = "population_collapse" in event_types
    typed_ecological = "ecological_collapse" in event_types

    available = source != "unavailable" and history_status != "unavailable"
    if not available:
        relation = "unavailable"
        explanation = "Typed lifecycle history is unavailable for this arm."
    elif temporal_status == "invalid":
        relation = "partial"
        explanation = (
            "Typed lifecycle source has an internally inconsistent temporal "
            "history, so it cannot fully verify this arm."
        )
    elif technical_extinction_tick is not None and typed_structural:
        relation = "verified"
        explanation = (
            "Technical zero-structure extinction and typed structural "
            "extinction are both present."
        )
    elif technical_extinction_tick is None and not typed_structural:
        relation = "verified"
        explanation = (
            "Neither source reports structural extinction on the observed horizon."
        )
    elif technical_extinction_tick is not None and (
        typed_population or typed_ecological
    ):
        relation = "compatible_scope_difference"
        explanation = (
            "Typed lifecycle records a population/ecological collapse while "
            "the sample comparator reports terminal zero structure; these are "
            "different scopes, not opposite claims."
        )
    elif (
        technical_extinction_tick is not None
        and (
            not history_complete
            or observed_through is None
            or observed_through < technical_extinction_tick
        )
    ):
        relation = "partial"
        explanation = (
            "Typed lifecycle coverage is insufficient to verify the technical "
            "structural-extinction tick."
        )
    else:
        relation = "criterion_mismatch"
        explanation = (
            "Typed lifecycle and the technical zero-structure comparator make "
            "opposite structural-extinction observations on a covered horizon."
        )

    return {
        "arm": arm,
        "canonical_source": source,
        "contract_verification_status": str(
            contract.get("verification_status") or "unavailable"
        ),
        "passport_path": contract.get("passport_path"),
        "source_resolution": source_resolution,
        "temporal_integrity": temporal_integrity,
        "history_status": history_status,
        "history_complete_for_supported_types": history_complete,
        "observed_through_tick": observed_through,
        "event_types": sorted(event_types),
        "events": events,
        "typed_population_collapse": typed_population,
        "typed_ecological_collapse": typed_ecological,
        "typed_structural_extinction": typed_structural,
        "technical_structural_extinction_tick": technical_extinction_tick,
        "relation": relation,
        "explanation": explanation,
    }


def _effect_relation(
    primary: str,
    baseline: Mapping[str, Any],
    mutant: Mapping[str, Any],
) -> dict[str, str]:
    baseline_available = baseline.get("relation") != "unavailable"
    mutant_available = mutant.get("relation") != "unavailable"
    if not baseline_available or not mutant_available:
        return {
            "status": "unavailable",
            "explanation": (
                "Both typed lifecycle arms are required to reconcile the "
                "mutation effect."
            ),
        }

    if "partial" in {baseline.get("relation"), mutant.get("relation")}:
        return {
            "status": "partial",
            "explanation": (
                "Typed lifecycle coverage is insufficient to reconcile the "
                "mutation effect on the full shared horizon."
            ),
        }

    baseline_structural = bool(baseline.get("typed_structural_extinction"))
    mutant_structural = bool(mutant.get("typed_structural_extinction"))
    mutant_scoped_collapse = bool(
        mutant.get("typed_population_collapse")
        or mutant.get("typed_ecological_collapse")
    )

    if primary == "structural_extinction_induced":
        if not baseline_structural and mutant_structural:
            return {
                "status": "verified",
                "explanation": "Typed lifecycle also records induced structural extinction.",
            }
        if not baseline_structural and mutant_scoped_collapse:
            return {
                "status": "compatible_scope_difference",
                "explanation": (
                    "Mutation Analyzer reports terminal zero structure while "
                    "typed lifecycle records collapse at population/ecology scope."
                ),
            }
        return {
            "status": "mismatch",
            "explanation": (
                "Typed lifecycle does not support the induced structural-extinction "
                "direction on the covered comparison."
            ),
        }

    if primary == "structural_extinction_prevented":
        status = (
            "verified"
            if baseline_structural and not mutant_structural
            else "mismatch"
        )
        return {
            "status": status,
            "explanation": (
                "Typed lifecycle supports prevented structural extinction."
                if status == "verified"
                else "Typed lifecycle does not support prevented structural extinction."
            ),
        }

    if primary == "structural_extinction_preserved":
        status = (
            "verified"
            if baseline_structural and mutant_structural
            else "compatible_scope_difference"
            if (
                baseline.get("typed_population_collapse")
                and mutant.get("typed_population_collapse")
            )
            else "mismatch"
        )
        return {
            "status": status,
            "explanation": (
                "Typed lifecycle supports the preserved terminal outcome."
                if status == "verified"
                else "The preserved effect is recorded at a different lifecycle scope."
                if status == "compatible_scope_difference"
                else "Typed lifecycle does not support the preserved terminal outcome."
            ),
        }

    return {
        "status": "not_applicable",
        "explanation": (
            f"Effect '{primary}' is not a structural-extinction claim; typed "
            "lifecycle is retained as context and does not replace it."
        ),
    }


def _event_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        return []
    return [
        deepcopy(dict(event))
        for event in value
        if isinstance(event, Mapping)
    ]


def _non_negative_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


__all__ = [
    "RECONCILIATION_SCHEMA_VERSION",
    "reconcile_perturbation_lifecycle",
]
