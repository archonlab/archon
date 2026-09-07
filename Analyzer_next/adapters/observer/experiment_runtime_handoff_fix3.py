"""EXPERIMENTS-FIX3 exact READY runtime → CONFIG1 review projection."""
from __future__ import annotations

from pathlib import Path

import Analyzer_next.adapters.observer.experiment_runtime_handoff as base
from Analyzer_next.adapters.observer.experiment_runtime_handoff import (
    AuditedExperimentRuntimeHandoff,
    ExperimentRuntimeHandoffError,
)
from Analyzer_next.execution.observer.shell2.config1.model import (
    ConfigurationDraft,
    DEFAULT_OUTPUTS,
    PreparedConfiguration,
    ProvenanceKind,
)


class AuditedExperimentRuntimeHandoffFix3(AuditedExperimentRuntimeHandoff):
    """Add review-only exact projection without weakening Stage 6.5 authorization."""

    def prepare_runtime_for_review(self, runtime_id: str) -> tuple[PreparedConfiguration, ...]:
        entry = self._index_entry(str(runtime_id).strip())
        _path, package = self._package_for_entry(entry)
        if entry.get("status") not in {"READY_FOR_LAUNCH_REVIEW", "LAUNCH_AUTHORIZED"}:
            raise ExperimentRuntimeHandoffError(
                f"runtime {runtime_id} is {entry.get('status')}; exact CONFIG1 review requires READY_FOR_LAUNCH_REVIEW or LAUNCH_AUTHORIZED"
            )
        if package.get("status") not in {"READY_FOR_LAUNCH_REVIEW", "LAUNCH_AUTHORIZED"}:
            raise ExperimentRuntimeHandoffError(
                f"runtime package {runtime_id} is not ready for exact CONFIG1 review"
            )
        runtime = base._as_dict(package.get("runtime"))
        if not runtime or base._canonical_hash(runtime) != str(package.get("runtime_hash") or ""):
            raise ExperimentRuntimeHandoffError("runtime package hash mismatch")
        if entry.get("runtime_hash") != package.get("runtime_hash"):
            raise ExperimentRuntimeHandoffError("runtime registry/package hash mismatch")
        matrix = base._as_list(runtime.get("run_matrix"))
        if not matrix:
            raise ExperimentRuntimeHandoffError("runtime has an empty run matrix")
        if any(base._as_dict(row).get("perturbation") not in (None, {}, []) for row in matrix):
            raise ExperimentRuntimeHandoffError(
                "RUNTIME_REQUIRES_SPECIALIZED_EXECUTION_ADAPTER: perturbation rows are not projected through canonical Observer review"
            )
        sample_every = int(runtime.get("sample_interval") or 0)
        autosave_every = int(runtime.get("checkpoint_interval") or 0)
        if sample_every < 1 or autosave_every < 0:
            raise ExperimentRuntimeHandoffError("runtime telemetry/checkpoint cadence is invalid")
        worlds = {row.rule_id: row for row in self.world_catalog.load_worlds()}
        prepared_rows: list[PreparedConfiguration] = []
        seen_outputs: set[str] = set()
        for raw in matrix:
            row = base._as_dict(raw)
            try:
                rule_id = int(row["rule_id"])
                duration = int(row["duration_ticks"])
                replicate = int(row["replicate_index"])
                field_size = list(row["field_size"])
                field_width, field_height = int(field_size[0]), int(field_size[1])
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                raise ExperimentRuntimeHandoffError(f"invalid run matrix row: {exc}") from exc
            world = worlds.get(rule_id)
            if world is None or not world.source_verified:
                raise ExperimentRuntimeHandoffError(
                    f"runtime rule {rule_id:05d} has no verified canonical world source"
                )
            try:
                role = base._ROLE_MAP[str(row.get("role") or "").upper()]
                topology = base._TOPOLOGY_MAP[str(row.get("topology") or "").upper()]
                boundary = base._BOUNDARY_MAP[str(row.get("boundary_condition") or "").upper()]
                initial = base._INITIAL_MAP[
                    str(
                        row.get("initial_state_mode")
                        or runtime.get("initial_state_mode")
                        or ""
                    ).upper()
                ]
            except KeyError as exc:
                raise ExperimentRuntimeHandoffError(
                    f"unsupported runtime value: {exc.args[0]}"
                ) from exc
            experiment_id = str(
                row.get("experiment_id") or runtime.get("experiment_id") or ""
            ).strip()
            condition_id = str(
                row.get("condition_id") or runtime.get("condition_id") or ""
            ).strip()
            output_dir = str(row.get("output_directory") or "").strip()
            if not experiment_id or not condition_id or not output_dir:
                raise ExperimentRuntimeHandoffError(
                    "run matrix row is missing experiment/condition/output identity"
                )
            normalized_output = str(Path(output_dir).expanduser().resolve())
            if normalized_output in seen_outputs:
                raise ExperimentRuntimeHandoffError(
                    "run matrix contains duplicate output directories"
                )
            seen_outputs.add(normalized_output)
            seed = row.get("seed")
            draft = ConfigurationDraft(
                world=world,
                provenance=ProvenanceKind.EXPERIMENTAL,
                max_ticks=duration,
                autosave_every=autosave_every,
                sample_every=sample_every,
                pressure_every=self.pressure_every,
                speed=2,
                frame_delay_ms=30,
                cell_size=8,
                auto_stop=False,
                outputs=DEFAULT_OUTPUTS,
                output_dir=normalized_output,
                field_width=field_width,
                field_height=field_height,
                topology=topology,
                boundary_mode=boundary,
                seed=(int(seed) if seed is not None else None),
                experiment_id=experiment_id,
                condition_id=condition_id,
                experiment_role=role,
                replicate_index=replicate,
                initial_state_mode=initial,
            )
            review = self.command_service.review(draft)
            if not review.valid or review.prepared is None:
                reasons = "; ".join(issue.code for issue in review.issues) or "unknown review failure"
                raise ExperimentRuntimeHandoffError(
                    f"runtime row cannot be projected to CONFIG1: {reasons}"
                )
            prepared_rows.append(review.prepared)
        return tuple(prepared_rows)


__all__ = ["AuditedExperimentRuntimeHandoffFix3"]
