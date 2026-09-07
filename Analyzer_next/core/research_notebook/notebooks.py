"""Pure notebook construction rules."""
from __future__ import annotations

from typing import Any


def build_notebook(
    passport: dict[str, Any] | None = None,
    *,
    generated_date: str,
) -> dict[str, Any]:
    notebook: dict[str, Any] = {
        "experiment": {
            "id": None,
            "date": generated_date,
            "rule": None,
            "generation": None,
            "status": "Active",
        },
        "observation": [],
        "hypothesis": [],
        "evidence": {},
        "confidence": {"level": None, "reason": []},
        "questions": [],
        "next_experiment": [],
        "notes": [],
    }
    if not passport:
        return notebook

    notebook["experiment"]["rule"] = passport.get("rule")
    lifetime = passport.get("lifetime") or 0
    dynamic_score = passport.get("dynamic_score") or 0
    classification = passport.get("classification")
    collapse = passport.get("collapse")
    objects = passport.get("objects")
    if lifetime:
        notebook["observation"].append(f"World survived {lifetime} ticks.")
    if collapse == "No":
        notebook["observation"].append("No collapse observed.")
    if objects:
        notebook["observation"].append(f"Objects remained in range {objects}.")
    if classification:
        notebook["observation"].append(f"Classification: {classification}.")
    notebook["evidence"] = {
        "lifetime": lifetime,
        "dynamic_score": passport.get("dynamic_score"),
        "breathing_score": passport.get("breathing_score"),
        "objects": objects,
        "split_birth": passport.get("split_birth"),
        "merge_death": passport.get("merge_death"),
        "collapse": collapse,
    }
    if lifetime >= 100000 and dynamic_score >= 0.8 and collapse == "No":
        notebook["confidence"]["level"] = "HIGH"
        notebook["confidence"]["reason"] = [
            "Long lifetime",
            "High dynamic score",
            "No collapse observed",
            "Bounded object count",
        ]
        notebook["hypothesis"].append(
            "Rule may implement a stable dynamic attractor."
        )
        notebook["hypothesis"].append(
            "Global morphology may persist while local structures are replaced."
        )
        notebook["next_experiment"].append(
            "Continue observation to 250000 ticks."
        )
        notebook["next_experiment"].append(
            "Save another passport and compare morphology."
        )
    elif lifetime >= 10000 or dynamic_score >= 0.5:
        notebook["confidence"]["level"] = "MEDIUM"
        notebook["confidence"]["reason"] = [
            "Some long-run or dynamic evidence exists",
            "More observation is needed",
        ]
    else:
        notebook["confidence"]["level"] = "LOW"
        notebook["confidence"]["reason"] = ["Insufficient long-run evidence"]
    return notebook


__all__ = ["build_notebook"]
