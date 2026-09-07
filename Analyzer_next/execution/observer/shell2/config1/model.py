"""Immutable OL2-CONFIG1 world, configuration, and review contracts."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from Analyzer_next.execution.observer.state import RunSpec


class WorldIntegrity(str, Enum):
    VERIFIED = "VERIFIED"
    SOURCE_MISSING = "SOURCE_MISSING"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    PAYLOAD_INVALID = "PAYLOAD_INVALID"


class ProvenanceKind(str, Enum):
    CANONICAL = "canonical"
    EXPERIMENTAL = "experimental"
    REQUIRED_CONTROL = "required_control"
    CANONICAL_QUEUE = "canonical_queue"


class ConfigStep(str, Enum):
    SELECT_WORLD = "SELECT_WORLD"
    CONFIGURE = "CONFIGURE"
    REVIEW = "REVIEW"


OUTPUT_OPTIONS = (
    "samples",
    "events",
    "pressure",
    "chronicle",
    "passport",
    "log",
    "sqlite",
    "evidence",
)

DEFAULT_OUTPUTS = frozenset(OUTPUT_OPTIONS)


@dataclass(frozen=True, slots=True)
class WorldRecord:
    rule_id: int
    world_class: str
    score: float | None
    genome_hash: str | None
    observed: bool
    mutation_runs: int
    last_run: str
    source_path: str | None
    integrity: WorldIntegrity

    def __post_init__(self) -> None:
        if isinstance(self.rule_id, bool) or self.rule_id < 0:
            raise ValueError("world rule_id must be a non-negative integer")
        if self.mutation_runs < 0:
            raise ValueError("mutation_runs cannot be negative")

    @property
    def source_verified(self) -> bool:
        return self.integrity is WorldIntegrity.VERIFIED

    @property
    def display_id(self) -> str:
        return f"{self.rule_id:05d}"


@dataclass(frozen=True, slots=True)
class ForcedControl:
    field: str
    forced_value: str
    owner: str
    reason: str


@dataclass(frozen=True, slots=True)
class ConfigurationDraft:
    world: WorldRecord | None
    provenance: ProvenanceKind = ProvenanceKind.CANONICAL
    max_ticks: int = 20_000
    autosave_every: int = 5_000
    sample_every: int = 10
    pressure_every: int = 100
    speed: int = 2
    frame_delay_ms: int = 30
    cell_size: int = 8
    auto_stop: bool = False
    outputs: frozenset[str] = DEFAULT_OUTPUTS
    output_dir: str = "Results/Universe_Search/observation_logs"
    field_width: int = 96
    field_height: int = 64
    topology: str = "torus"
    boundary_mode: str = "wrap"
    seed: int | None = None
    experiment_id: str | None = None
    condition_id: str | None = None
    experiment_role: str = "baseline"
    replicate_index: int = 0
    initial_state_mode: str = "random_seed"

    def __post_init__(self) -> None:
        unknown = set(self.outputs) - set(OUTPUT_OPTIONS)
        if unknown:
            raise ValueError(f"unknown output options: {sorted(unknown)}")

    def with_updates(self, **changes: Any) -> "ConfigurationDraft":
        if "provenance" in changes:
            changes["provenance"] = ProvenanceKind(changes["provenance"])
        if "outputs" in changes:
            changes["outputs"] = frozenset(str(item) for item in changes["outputs"])
        return replace(self, **changes)

    def canonical_payload(self) -> dict[str, Any]:
        world = self.world
        return {
            "auto_stop": self.auto_stop,
            "autosave_every": self.autosave_every,
            "boundary_mode": self.boundary_mode,
            "cell_size": self.cell_size,
            "condition_id": self.condition_id,
            "experiment_id": self.experiment_id,
            "experiment_role": self.experiment_role,
            "field_height": self.field_height,
            "field_width": self.field_width,
            "frame_delay_ms": self.frame_delay_ms,
            "initial_state_mode": self.initial_state_mode,
            "max_ticks": self.max_ticks,
            "output_dir": self.output_dir,
            "outputs": sorted(self.outputs),
            "pressure_every": self.pressure_every,
            "provenance": self.provenance.value,
            "replicate_index": self.replicate_index,
            "sample_every": self.sample_every,
            "seed": self.seed,
            "speed": self.speed,
            "topology": self.topology,
            "world": (
                {
                    "genome_hash": world.genome_hash,
                    "integrity": world.integrity.value,
                    "rule_id": world.rule_id,
                    "source_path": world.source_path,
                    "world_class": world.world_class,
                }
                if world is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    field: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class PreparedConfiguration:
    effective_draft: ConfigurationDraft
    run_spec: RunSpec
    command: tuple[str, ...]
    command_text: str
    forced_controls: tuple[ForcedControl, ...]
    review_hash: str


@dataclass(frozen=True, slots=True)
class ConfigurationReview:
    draft: ConfigurationDraft
    issues: tuple[ValidationIssue, ...]
    forced_controls: tuple[ForcedControl, ...]
    prepared: PreparedConfiguration | None

    @property
    def valid(self) -> bool:
        return not self.issues and self.prepared is not None


def canonical_hash(payload: Mapping[str, Any]) -> str:
    data = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def forced_controls_for(
    provenance: ProvenanceKind | str,
) -> tuple[ForcedControl, ...]:
    kind = ProvenanceKind(provenance)
    if kind is ProvenanceKind.EXPERIMENTAL:
        return (
            ForcedControl(
                field="outputs.sqlite",
                forced_value="enabled",
                owner="Experimental Conditions contract",
                reason="Experimental identity must be persisted in canonical telemetry.",
            ),
        )
    if kind is ProvenanceKind.REQUIRED_CONTROL:
        return (
            ForcedControl(
                field="auto_stop",
                forced_value="disabled",
                owner="Required Control contract",
                reason="Control horizon cannot be shortened by collapse detection.",
            ),
            ForcedControl(
                field="outputs.samples",
                forced_value="enabled",
                owner="Required Control contract",
                reason="Control comparison requires the canonical samples channel.",
            ),
            ForcedControl(
                field="outputs.passport",
                forced_value="enabled",
                owner="Required Control contract",
                reason="Control evidence requires a run passport.",
            ),
        )
    return ()


def apply_forced_controls(draft: ConfigurationDraft) -> ConfigurationDraft:
    outputs = set(draft.outputs)
    auto_stop = draft.auto_stop
    for control in forced_controls_for(draft.provenance):
        if control.field == "auto_stop":
            auto_stop = False
        elif control.field.startswith("outputs."):
            outputs.add(control.field.split(".", 1)[1])
    return draft.with_updates(outputs=outputs, auto_stop=auto_stop)
