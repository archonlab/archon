"""BRIDGE5 specialized Observer perturbation execution adapter.

Projects an authorized ``perturbation_recovery_test`` runtime into matched
BASELINE_CONTROL and real TREATMENT Observer runs.  Treatment rows are
materialized just-in-time through the frozen production mutation adapter and
use isolated mutated rule files.  Canonical Atlas rules remain read-only.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Analyzer_next.compatibility.legacy_analyzer.production_mutation_execution_adapter import (  # noqa: E402
    ADAPTER_ID as MUTATION_ADAPTER_ID,
    MutationAdapterError,
    materialize_protocol_arm,
)
from Analyzer_next.execution.observer.shell2.config1.command_service import (  # noqa: E402
    _CommandHarness,
    experimental_context,
)
from Analyzer_next.execution.observer.shell2.config1.model import (  # noqa: E402
    PreparedConfiguration,
    canonical_hash,
)
from Analyzer_next.execution.observer.shell2.functions1g.model import (  # noqa: E402
    RuntimeQueuePreparation,
)

BRIDGE_ID = "BRIDGE5"
SUPPORTED_EXPERIMENT_TYPE = "perturbation_recovery_test"


class PerturbationRuntimeHandoffError(RuntimeError):
    pass


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _pair_key(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(row.get("rule_id") or 0),
        int(row.get("replicate_index") or 0),
        int(row.get("seed") or 0),
    )


def validate_perturbation_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    """Fail closed unless the runtime represents a genuine matched intervention."""
    failures: list[str] = []
    if runtime.get("experiment_type") != SUPPORTED_EXPERIMENT_TYPE:
        failures.append("EXPERIMENT_TYPE_NOT_PERTURBATION_RECOVERY")
    perturbation = _as_dict(runtime.get("perturbation"))
    capability = _as_dict(perturbation.get("execution_capability"))
    if capability.get("required_adapter") != MUTATION_ADAPTER_ID:
        failures.append("PERTURBATION_ADAPTER_ID_MISMATCH")
    if capability.get("available") is not True:
        failures.append("PERTURBATION_ADAPTER_UNAVAILABLE")
    arms = _as_list(perturbation.get("arms"))
    if not arms:
        failures.append("PERTURBATION_ARMS_EMPTY")

    matrix = [_as_dict(row) for row in _as_list(runtime.get("run_matrix"))]
    baselines = [row for row in matrix if str(row.get("role") or "").upper() == "BASELINE_CONTROL"]
    treatments = [row for row in matrix if str(row.get("role") or "").upper() == "TREATMENT"]
    if not baselines:
        failures.append("BASELINE_ROWS_EMPTY")
    if not treatments:
        failures.append("TREATMENT_ROWS_EMPTY")
    if any(row.get("perturbation") not in (None, {}, []) for row in baselines):
        failures.append("BASELINE_ROW_HAS_PERTURBATION")
    if any(not _as_dict(row.get("perturbation")) for row in treatments):
        failures.append("TREATMENT_ROW_MISSING_PERTURBATION")

    baseline_keys = {_pair_key(row) for row in baselines}
    treatment_keys = {_pair_key(row) for row in treatments}
    if not treatment_keys.issubset(baseline_keys):
        failures.append("TREATMENT_WITHOUT_MATCHED_BASELINE")

    for row in treatments:
        row_pert = _as_dict(row.get("perturbation"))
        row_cap = _as_dict(row_pert.get("execution_capability"))
        arm = _as_dict(row_pert.get("arm"))
        if row_cap.get("required_adapter") != MUTATION_ADAPTER_ID or row_cap.get("available") is not True:
            failures.append("TREATMENT_EXECUTION_CAPABILITY_INVALID")
        if not str(row_pert.get("protocol_id") or "") or not str(row_pert.get("protocol_hash") or ""):
            failures.append("TREATMENT_PROTOCOL_IDENTITY_MISSING")
        if not str(arm.get("arm_id") or ""):
            failures.append("TREATMENT_ARM_ID_MISSING")
        if arm.get("application") != "PRE_RUN_RULE_MUTATION":
            failures.append("TREATMENT_APPLICATION_UNSUPPORTED")

    if failures:
        raise PerturbationRuntimeHandoffError(";".join(sorted(set(failures))))
    return {
        "baseline_count": len(baselines),
        "treatment_count": len(treatments),
        "arm_count": len(arms),
        "pair_count": len(baseline_keys),
    }




def _canonical_telemetry_db(project_root: Path) -> Path:
    return (
        Path(project_root).resolve()
        / "Results"
        / "Universe_Search"
        / "observation_logs"
        / "telemetry.sqlite"
    ).resolve()


def _bind_canonical_telemetry_db(command: tuple[str, ...], project_root: Path) -> tuple[str, ...]:
    """Keep specialized treatment SQLite on the canonical experiment registry.

    Canonical experiment rows are built through EXPERIMENTS-FIX7, which pins
    ``--telemetry-db`` to the shared experimental-conditions database.  The
    perturbation adapter rebuilds the Observer command to add ``--rule-file``
    and mutation provenance, so it must preserve that routing explicitly.
    """
    items = list(command)
    canonical = str(_canonical_telemetry_db(project_root))
    if "--telemetry-db" in items:
        index = items.index("--telemetry-db")
        if index + 1 >= len(items):
            raise PerturbationRuntimeHandoffError("MALFORMED_TREATMENT_TELEMETRY_DB_ARGUMENT")
        items[index + 1] = canonical
    else:
        items.extend(["--telemetry-db", canonical])
    return tuple(items)


def _treatment_label(perturbation: dict[str, Any]) -> str:
    arm = _as_dict(perturbation.get("arm"))
    arm_id = str(arm.get("arm_id") or "").strip()
    parameter = str(arm.get("parameter") or "").strip()
    intensity = arm.get("intensity")
    return arm_id or f"{parameter}:{intensity}"


def build_treatment_prepared(
    *,
    baseline_prepared: PreparedConfiguration,
    matrix_row: dict[str, Any],
    task_id: str,
    project_root: Path,
) -> PreparedConfiguration:
    """Turn one reviewed canonical treatment draft into a real mutated command."""
    perturbation = _as_dict(matrix_row.get("perturbation"))
    output_dir = Path(str(matrix_row.get("output_directory") or "")).expanduser().resolve()
    try:
        materialized = materialize_protocol_arm(
            world_atlas_directory=Path(project_root) / "Atlas" / "Worlds",
            results_directory=Path(project_root) / "Results" / "Universe_Search",
            rule_id=int(matrix_row["rule_id"]),
            perturbation=perturbation,
            run_id=str(matrix_row["run_id"]),
            task_id=str(task_id),
            experiment_id=str(matrix_row["experiment_id"]),
            condition_id=str(matrix_row["condition_id"]),
            replicate_index=int(matrix_row["replicate_index"]),
            experiment_seed=int(matrix_row["seed"]),
            run_output_directory=output_dir,
        )
    except (MutationAdapterError, KeyError, TypeError, ValueError) as exc:
        raise PerturbationRuntimeHandoffError(f"PERTURBATION_MATERIALIZATION_REFUSED:{exc}") from exc

    manifest = _as_dict(materialized.get("manifest"))
    if manifest.get("canonical_parent_hash") == manifest.get("mutated_hash"):
        raise PerturbationRuntimeHandoffError("MUTATED_RULE_EQUALS_CANONICAL_PARENT")
    if int(manifest.get("change_count") or 0) < 1:
        raise PerturbationRuntimeHandoffError("MUTATION_HAS_NO_CHANGES")

    draft = baseline_prepared.effective_draft
    context = baseline_prepared.run_spec.experimental_context
    if not context:
        context = experimental_context(draft) or {}
    context["treatment_arm"] = _treatment_label(perturbation)
    context["perturbation_protocol_id"] = str(perturbation.get("protocol_id") or "")
    context["mutation_id"] = str(materialized.get("mutation_id") or "")
    context["mutation_materialization_hash"] = str(manifest.get("materialization_hash") or "")
    context["canonical_parent_hash"] = str(manifest.get("canonical_parent_hash") or "")
    context["mutated_rule_hash"] = str(manifest.get("mutated_hash") or "")

    harness = _CommandHarness(draft, context)
    run = {
        "rule_id": int(matrix_row["rule_id"]),
        "mode": "experimental_mutation",
        "rule_file": Path(materialized["rule_file"]),
        "manifest_file": Path(materialized["manifest_file"]),
        "run_output_dir": output_dir,
        "max_ticks_override": int(matrix_row["duration_ticks"]),
        "sample_every_override": baseline_prepared.run_spec.sample_every,
        "pressure_every_override": baseline_prepared.run_spec.pressure_every,
        "experimental_context": context,
    }
    command = tuple(harness._base_command(run))
    command = _bind_canonical_telemetry_db(command, project_root)
    if "--rule-file" not in command or "--mutation-manifest" not in command:
        raise PerturbationRuntimeHandoffError("MUTATION_COMMAND_PROVENANCE_MISSING")
    if "--max-ticks" not in command or "--exit-at-max-ticks" not in command:
        raise PerturbationRuntimeHandoffError("TREATMENT_HORIZON_NOT_PINNED")
    if "--treatment-arm" not in command:
        raise PerturbationRuntimeHandoffError("TREATMENT_ARM_NOT_EMITTED")
    if "--telemetry-db" not in command:
        raise PerturbationRuntimeHandoffError("TREATMENT_CANONICAL_TELEMETRY_DB_MISSING")
    telemetry_index = command.index("--telemetry-db")
    if (
        telemetry_index + 1 >= len(command)
        or Path(command[telemetry_index + 1]).expanduser().resolve()
        != _canonical_telemetry_db(project_root)
    ):
        raise PerturbationRuntimeHandoffError("TREATMENT_CANONICAL_TELEMETRY_DB_MISMATCH")

    run_spec = replace(
        baseline_prepared.run_spec,
        mode="experimental",
        experimental_context_json=json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    review_payload = {
        "configuration": draft.canonical_payload(),
        "forced_controls": [
            {
                "field": item.field,
                "forced_value": item.forced_value,
                "owner": item.owner,
                "reason": item.reason,
            }
            for item in baseline_prepared.forced_controls
        ],
        "run_spec_hash": run_spec.content_hash,
        "command": list(command),
    }
    return PreparedConfiguration(
        effective_draft=draft,
        run_spec=run_spec,
        command=command,
        command_text=" ".join(str(item) for item in command),
        forced_controls=baseline_prepared.forced_controls,
        review_hash=canonical_hash(review_payload),
    )


def prepare_perturbation_runtime(
    *,
    runtime_id: str,
    authorization_id: str,
    runtime: dict[str, Any],
    canonical_prepared_by_run: dict[str, PreparedConfiguration],
    project_root: Path,
    execution_attempt_id: str | None = None,
) -> RuntimeQueuePreparation:
    summary = validate_perturbation_runtime(runtime)
    prepared_rows: list[PreparedConfiguration] = []
    matrix = [_as_dict(row) for row in _as_list(runtime.get("run_matrix"))]
    for order, row in enumerate(matrix, start=1):
        run_id = str(row.get("run_id") or "")
        prepared = canonical_prepared_by_run.get(run_id)
        if prepared is None:
            raise PerturbationRuntimeHandoffError(f"CANONICAL_PREPARED_ROW_MISSING:{run_id}")
        role = str(row.get("role") or "").upper()
        if role == "TREATMENT":
            prepared = build_treatment_prepared(
                baseline_prepared=prepared,
                matrix_row=row,
                task_id=(
                    f"{runtime_id}-{execution_attempt_id}-BRIDGE5-T{order:03d}"
                    if execution_attempt_id
                    else f"{runtime_id}-BRIDGE5-T{order:03d}"
                ),
                project_root=project_root,
            )
        prepared_rows.append(prepared)

    return RuntimeQueuePreparation(
        runtime_id=runtime_id,
        authorization_id=authorization_id,
        prepared=tuple(prepared_rows),
        message=(
            f"{runtime_id}: BRIDGE5 prepared {summary['baseline_count']} baseline + "
            f"{summary['treatment_count']} real perturbation run(s) • Queue not started"
        ),
    )


__all__ = [
    "BRIDGE_ID",
    "PerturbationRuntimeHandoffError",
    "prepare_perturbation_runtime",
    "validate_perturbation_runtime",
]
