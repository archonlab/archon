"""Channel-aware interpretation that preserves legacy score and status."""
from __future__ import annotations

from typing import Any

from .numeric import ss

def interpret_channel_aware_consensus(
    *,
    legacy_status: str,
    observational_strength: str,
    experimental_picture: str,
    perturbation_picture: str,
    flags: dict[str, Any],
    evidence_gaps: list[str],
) -> dict[str, Any]:
    """Interpret consensus across channels without changing legacy scoring."""
    tension = bool(flags.get("cross_channel_tension"))
    exp_challenge = bool(flags.get("experimental_scope_challenge"))
    perturbation_mixed = bool(flags.get("perturbation_mixed_signal"))

    if legacy_status == "DISPUTED":
        channel_status = "OBSERVATIONALLY_DISPUTED"
    elif tension and experimental_picture.startswith("LIMITED_SCOPE"):
        channel_status = "OBSERVATIONALLY_SUPPORTED_BUT_SCOPE_LIMITED"
    elif tension:
        channel_status = "CROSS_CHANNEL_TENSION"
    elif experimental_picture == "CORROBORATED":
        if perturbation_picture in {"ROBUST", "LIMITED_ROBUSTNESS_SIGNAL"}:
            channel_status = "MULTI_CHANNEL_CORROBORATION"
        else:
            channel_status = "EXPERIMENTALLY_CORROBORATED"
    elif experimental_picture == "MIXED":
        channel_status = "EXPERIMENTALLY_MIXED"
    elif experimental_picture == "CONTEXT_ONLY":
        channel_status = "EXPERIMENTALLY_CONTEXTUALIZED"
    elif experimental_picture.startswith("LIMITED_SCOPE_SUPPORT"):
        channel_status = "LIMITED_EXPERIMENTAL_SUPPORT"
    elif experimental_picture.startswith("LIMITED_SCOPE_CONTEXT"):
        channel_status = "LIMITED_EXPERIMENTAL_CONTEXT"
    elif perturbation_picture == "MIXED":
        channel_status = "PERTURBATION_RESPONSE_MIXED"
    elif perturbation_picture in {"ROBUST", "LIMITED_ROBUSTNESS_SIGNAL"}:
        channel_status = "PERTURBATION_ROBUSTNESS_SIGNAL"
    elif experimental_picture == "UNTESTED":
        channel_status = "OBSERVATION_ONLY"
    else:
        channel_status = "CHANNEL_CONTEXT_AVAILABLE"

    confidence_posture = (
        "CAUTIOUS"
        if tension or legacy_status in {"PROMISING", "OBSERVATION", "DISPUTED"}
        else "PROVISIONAL"
        if experimental_picture in {"UNTESTED", "CONTEXT_ONLY"}
        else "SUPPORTED"
    )

    sentences = [
        f"Legacy consensus status is {legacy_status}.",
        f"Observational strength is {observational_strength}.",
    ]

    if experimental_picture == "UNTESTED":
        sentences.append("No mapped controlled experiment is available.")
    elif experimental_picture.startswith("LIMITED_SCOPE"):
        sentences.append(
            f"Experimental evidence is limited in scope: {experimental_picture}."
        )
    else:
        sentences.append(
            f"Experimental evidence picture is {experimental_picture}."
        )

    if perturbation_picture == "INSUFFICIENT":
        sentences.append("Perturbation evidence is insufficient.")
    else:
        sentences.append(
            f"Perturbation evidence picture is {perturbation_picture}."
        )

    if exp_challenge:
        sentences.append(
            "At least one controlled experiment raises a scope or calibration challenge."
        )
    if perturbation_mixed:
        sentences.append(
            "Perturbation responses are mixed across the available cases."
        )
    if evidence_gaps:
        sentences.append(
            f"{len(evidence_gaps)} evidence gap(s) remain open."
        )

    return {
        "schema": "archon_channel_aware_consensus_interpretation_v1",
        "channel_aware_status": channel_status,
        "confidence_posture": confidence_posture,
        "interpretation_summary": " ".join(sentences),
        "flags": {
            "legacy_status_preserved": True,
            "legacy_score_preserved": True,
            "cross_channel_tension": tension,
            "experimental_scope_challenge": exp_challenge,
            "perturbation_mixed_signal": perturbation_mixed,
        },
        "evidence_gaps": list(evidence_gaps),
        "scientific_policy": {
            "legacy_consensus_score_changed": False,
            "legacy_consensus_status_changed": False,
            "automatic_promotion": False,
            "automatic_demotion": False,
            "interpretation_only": True,
        },
    }

