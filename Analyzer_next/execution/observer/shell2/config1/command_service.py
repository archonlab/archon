"""CONFIG1 validation and exact reuse of the modular Observer command builder."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
from typing import Any

from Analyzer_next.execution.observer.runs.command_builder import CommandBuilderMixin
from Analyzer_next.execution.observer.settings import SEARCH_RESULTS_DIR, SPEED_VALUES
from Analyzer_next.execution.observer.state import RunSpec

from .model import (
    ConfigurationDraft,
    ConfigurationReview,
    PreparedConfiguration,
    ProvenanceKind,
    ValidationIssue,
    apply_forced_controls,
    canonical_hash,
    forced_controls_for,
)


EXPERIMENT_ROLES = frozenset({"baseline", "treatment", "control", "calibration"})
INITIAL_STATE_MODES = frozenset(
    {"canonical_seed", "random_seed", "saved_state", "deterministic_regenerated"}
)


@dataclass(slots=True)
class _Value:
    value: Any

    def get(self) -> Any:
        return self.value


class _CommandHarness(CommandBuilderMixin):
    """Tk-free variable adapter around the production-normalized builder."""

    def __init__(self, draft: ConfigurationDraft, context: dict[str, Any] | None) -> None:
        self.rule_var = _Value(
            f"{draft.world.rule_id:05d}" if draft.world is not None else ""
        )
        self.cell_var = _Value(draft.cell_size)
        self.speed_var = _Value(draft.speed)
        self.delay_var = _Value(draft.frame_delay_ms)
        self.autosave_var = _Value(draft.autosave_every)
        self.sample_every_var = _Value(draft.sample_every)
        self.pressure_every_var = _Value(draft.pressure_every)
        self.max_ticks_var = _Value(draft.max_ticks)
        self.auto_stop_var = _Value(draft.auto_stop)
        self.samples_var = _Value("samples" in draft.outputs)
        self.events_var = _Value("events" in draft.outputs)
        self.pressure_var = _Value("pressure" in draft.outputs)
        self.chronicle_var = _Value("chronicle" in draft.outputs)
        self.passport_var = _Value("passport" in draft.outputs)
        self.log_var = _Value("log" in draft.outputs)
        self.sqlite_var = _Value("sqlite" in draft.outputs)
        self.evidence_var = _Value("evidence" in draft.outputs)
        self._context = context

    def _selected_experimental_context(self) -> dict[str, Any] | None:
        return self._context


def validate_draft(draft: ConfigurationDraft) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []

    def issue(field: str, code: str, message: str) -> None:
        issues.append(ValidationIssue(field=field, code=code, message=message))

    if draft.world is None:
        issue("world", "WORLD_REQUIRED", "Select a canonical world.")
    elif not draft.world.source_verified:
        issue(
            "world",
            "WORLD_SOURCE_NOT_VERIFIED",
            f"Rule {draft.world.display_id} source identity is not verified.",
        )
    if draft.max_ticks < 0:
        issue("max_ticks", "NEGATIVE_HORIZON", "Maximum ticks cannot be negative.")
    if draft.autosave_every < 0:
        issue("autosave_every", "NEGATIVE_AUTOSAVE", "Autosave cadence cannot be negative.")
    if draft.sample_every < 1:
        issue("sample_every", "INVALID_SAMPLE_CADENCE", "Sample cadence must be positive.")
    if draft.pressure_every < 1:
        issue("pressure_every", "INVALID_PRESSURE_CADENCE", "Pressure cadence must be positive.")
    if draft.speed not in SPEED_VALUES:
        issue("speed", "UNSUPPORTED_SPEED", "Speed is outside the modular launcher contract.")
    if not 0 <= draft.frame_delay_ms <= 1000:
        issue("frame_delay_ms", "INVALID_FRAME_DELAY", "Frame delay must be between 0 and 1000 ms.")
    if not 2 <= draft.cell_size <= 24:
        issue("cell_size", "INVALID_CELL_SIZE", "Cell size must be between 2 and 24.")
    if draft.field_width < 1 or draft.field_height < 1:
        issue("field_size", "INVALID_FIELD_SIZE", "Field dimensions must be positive.")
    if draft.topology not in {"torus", "bounded"}:
        issue("topology", "UNSUPPORTED_TOPOLOGY", f"Unsupported topology: {draft.topology}")
    if draft.boundary_mode not in {"wrap", "fixed_dead", "fixed_alive", "reflective"}:
        issue(
            "boundary_mode",
            "UNSUPPORTED_BOUNDARY",
            f"Unsupported boundary mode: {draft.boundary_mode}",
        )
    if draft.seed is not None and draft.seed < 0:
        issue("seed", "NEGATIVE_SEED", "Seed cannot be negative.")
    if not draft.output_dir.strip():
        issue("output_dir", "OUTPUT_DIR_REQUIRED", "Output directory is required.")
    if not draft.outputs:
        issue("outputs", "OUTPUT_REQUIRED", "Select at least one output channel.")
    if draft.replicate_index < 0:
        issue("replicate_index", "NEGATIVE_REPLICATE", "Replicate index cannot be negative.")

    if draft.provenance is ProvenanceKind.EXPERIMENTAL:
        if not str(draft.experiment_id or "").strip():
            issue("experiment_id", "EXPERIMENT_ID_REQUIRED", "Experiment ID is required.")
        if not str(draft.condition_id or "").strip():
            issue("condition_id", "CONDITION_ID_REQUIRED", "Condition ID is required.")
        if draft.experiment_role not in EXPERIMENT_ROLES:
            issue("experiment_role", "INVALID_EXPERIMENT_ROLE", "Experiment role is invalid.")
        if draft.initial_state_mode not in INITIAL_STATE_MODES:
            issue(
                "initial_state_mode",
                "INVALID_INITIAL_STATE_MODE",
                "Initial-state mode is invalid.",
            )
    return tuple(issues)


def experimental_context(draft: ConfigurationDraft) -> dict[str, Any] | None:
    if draft.provenance is not ProvenanceKind.EXPERIMENTAL:
        return None
    context: dict[str, Any] = {
        "experiment_id": str(draft.experiment_id),
        "condition_id": str(draft.condition_id),
        "role": draft.experiment_role,
        "replicate_index": draft.replicate_index,
        "field_width": draft.field_width,
        "field_height": draft.field_height,
        "topology": draft.topology,
        "boundary_mode": draft.boundary_mode,
        "initial_state_mode": draft.initial_state_mode,
    }
    if draft.seed is not None:
        context["seed"] = draft.seed
    return context


class ObserverCommandService:
    """Validate one draft and prepare an immutable, parity-safe launch review."""

    def __init__(self, *, default_output_dir: Path | None = None) -> None:
        self.default_output_dir = (
            Path(default_output_dir)
            if default_output_dir is not None
            else SEARCH_RESULTS_DIR / "observation_logs"
        )

    def review(self, draft: ConfigurationDraft) -> ConfigurationReview:
        controls = forced_controls_for(draft.provenance)
        effective = apply_forced_controls(draft)
        issues = validate_draft(effective)
        if issues:
            return ConfigurationReview(
                draft=draft,
                issues=issues,
                forced_controls=controls,
                prepared=None,
            )
        assert effective.world is not None
        context = experimental_context(effective)
        run_spec = RunSpec.create(
            rule_id=effective.world.rule_id,
            mode=effective.provenance.value,
            max_ticks=effective.max_ticks,
            sample_every=effective.sample_every,
            pressure_every=effective.pressure_every,
            output_dir=effective.output_dir,
            outputs=effective.outputs,
            field_width=effective.field_width,
            field_height=effective.field_height,
            topology=effective.topology,
            boundary_mode=effective.boundary_mode,
            seed=effective.seed,
            experimental_context=context,
        )
        command = self._command(effective, context)
        review_payload = {
            "configuration": effective.canonical_payload(),
            "forced_controls": [
                {
                    "field": item.field,
                    "forced_value": item.forced_value,
                    "owner": item.owner,
                    "reason": item.reason,
                }
                for item in controls
            ],
            "run_spec_hash": run_spec.content_hash,
            "command": list(command),
        }
        prepared = PreparedConfiguration(
            effective_draft=effective,
            run_spec=run_spec,
            command=command,
            command_text=shlex.join(command),
            forced_controls=controls,
            review_hash=canonical_hash(review_payload),
        )
        return ConfigurationReview(
            draft=draft,
            issues=(),
            forced_controls=controls,
            prepared=prepared,
        )

    def _command(
        self,
        draft: ConfigurationDraft,
        context: dict[str, Any] | None,
    ) -> tuple[str, ...]:
        assert draft.world is not None
        harness = _CommandHarness(draft, context)
        run: dict[str, Any] = {
            "rule_id": draft.world.rule_id,
            "mode": draft.provenance.value,
            "rule_file": None,
            "manifest_file": None,
            "experimental_context": context,
        }
        if draft.provenance is ProvenanceKind.CANONICAL_QUEUE:
            run.update(
                max_ticks_override=draft.max_ticks,
                sample_every_override=draft.sample_every,
                pressure_every_override=draft.pressure_every,
            )
        output_dir = Path(draft.output_dir)
        if output_dir.resolve() != self.default_output_dir.resolve():
            run["run_output_dir"] = output_dir
        return tuple(harness._base_command(run))
