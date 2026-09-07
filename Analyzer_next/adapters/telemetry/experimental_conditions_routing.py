"""Fail-closed selection of the complete Experimental Conditions aggregate."""
from __future__ import annotations

import importlib
import os
from types import ModuleType

from . import experimental_conditions as native_experimental_conditions


PROFILE_ENV = "ARCHON_TELEMETRY_EXPERIMENTAL_CONDITIONS_PROFILE"
DEFAULT_PROFILE = "native"
SUPPORTED_PROFILES = ("native", "legacy")


def resolve_experimental_conditions_module(
    profile: str | None = None,
) -> ModuleType:
    selected = str(
        profile if profile is not None else os.environ.get(
            PROFILE_ENV, DEFAULT_PROFILE
        )
    ).strip().lower()
    if selected == "native":
        return native_experimental_conditions
    if selected == "legacy":
        try:
            return importlib.import_module(
                "Experiments.experimental_conditions"
            )
        except ModuleNotFoundError as error:
            if error.name not in {"Experiments", "Experiments.experimental_conditions"}:
                raise
            return importlib.import_module(
                "Telemetry.Experiments.experimental_conditions"
            )
    raise RuntimeError(
        "Unsupported Telemetry Experimental Conditions profile: "
        f"{selected!r}; expected one of {SUPPORTED_PROFILES}"
    )


SELECTED_EXPERIMENTAL_CONDITIONS_MODULE = (
    resolve_experimental_conditions_module()
)

CONDITION_SCHEMA_VERSION = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.CONDITION_SCHEMA_VERSION
)
ExperimentalConditionsError = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.ExperimentalConditionsError
)
Topology = SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.Topology
BoundaryMode = SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.BoundaryMode
InitialStateMode = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.InitialStateMode
)
ExperimentStatus = SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.ExperimentStatus
ExperimentRole = SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.ExperimentRole
ExperimentalCondition = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.ExperimentalCondition
)
Experiment = SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.Experiment
ExperimentRunRequest = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.ExperimentRunRequest
)
ExperimentPlanItem = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.ExperimentPlanItem
)
ExperimentPlan = SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.ExperimentPlan
ExperimentRunLink = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.ExperimentRunLink
)
ExperimentalConditionsRepository = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.ExperimentalConditionsRepository
)
canonical_condition_payload = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.canonical_condition_payload
)
condition_hash_from_payload = (
    SELECTED_EXPERIMENTAL_CONDITIONS_MODULE.condition_hash_from_payload
)


__all__ = [
    "BoundaryMode",
    "CONDITION_SCHEMA_VERSION",
    "DEFAULT_PROFILE",
    "Experiment",
    "ExperimentPlan",
    "ExperimentPlanItem",
    "ExperimentRole",
    "ExperimentRunLink",
    "ExperimentRunRequest",
    "ExperimentStatus",
    "ExperimentalCondition",
    "ExperimentalConditionsError",
    "ExperimentalConditionsRepository",
    "InitialStateMode",
    "PROFILE_ENV",
    "SELECTED_EXPERIMENTAL_CONDITIONS_MODULE",
    "SUPPORTED_PROFILES",
    "Topology",
    "canonical_condition_payload",
    "condition_hash_from_payload",
    "resolve_experimental_conditions_module",
]
