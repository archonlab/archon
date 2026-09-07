"""Audited materialized experiment runtime → OL2 queue preparation adapter.

FUNCTIONS1G deliberately stops before execution.  It may create/verify the
existing Stage 6.5 launch authorization receipt and project an authorized,
unperturbed runtime matrix into immutable CONFIG1 PreparedConfiguration rows.
Observer process ownership remains in CONTROL1 and queue dispatch remains in
QUEUE1.
"""
from __future__ import annotations

from Tools.archon_runtime_python import runtime_python_command

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Any

from Analyzer_next.execution.observer.shell2.config1.catalog_adapter import NativeWorldCatalog
from Analyzer_next.execution.observer.shell2.config1.command_service import ObserverCommandService
from Analyzer_next.execution.observer.shell2.config1.model import (
    ConfigurationDraft,
    DEFAULT_OUTPUTS,
    PreparedConfiguration,
    ProvenanceKind,
    canonical_hash,
)
from Analyzer_next.execution.observer.state import RunSpec
from Analyzer_next.adapters.telemetry.experimental_conditions import (
    ExperimentalConditionsError,
    ExperimentalConditionsRepository,
    ExperimentStatus,
)
from Analyzer_next.execution.observer.shell2.functions1g.model import (
    ExperimentRuntimeRow,
    RuntimeAuthorizationResult,
    RuntimeQueuePreparation,
)
from Analyzer_next.adapters.observer.perturbation_runtime_handoff import (
    PerturbationRuntimeHandoffError,
    prepare_perturbation_runtime,
    validate_perturbation_runtime,
)


class ExperimentRuntimeHandoffError(RuntimeError):
    pass


class _DefaultRunner:
    def run(self, *, command, cwd, environment, timeout):
        try:
            completed = subprocess.run(
                list(command),
                cwd=str(cwd),
                env=dict(environment),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=int(timeout),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return SimpleNamespace(returncode=124, output=str(exc.stdout or ""))
        return SimpleNamespace(returncode=int(completed.returncode), output=completed.stdout or "")


def _load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {} if default is None else default
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentRuntimeHandoffError(f"cannot read {path}: {exc}") from exc


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _token(prefix: str, runtime_id: str) -> str:
    raw = f"{runtime_id}|{datetime.now(timezone.utc).isoformat()}|{os.getpid()}".encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:16].upper()}"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


_ROLE_MAP = {
    "BASELINE": "baseline",
    "BASELINE_CONTROL": "baseline",
    "TREATMENT": "treatment",
    "CONTROL": "control",
    "CALIBRATION": "calibration",
}
_TOPOLOGY_MAP = {
    "TORUS": "torus",
    "WRAP": "torus",
    "PLANE": "bounded",
    "BOUNDED": "bounded",
}
_BOUNDARY_MAP = {
    "PERIODIC": "wrap",
    "WRAP": "wrap",
    "FIXED_DEAD": "fixed_dead",
    "FIXED_ALIVE": "fixed_alive",
    "REFLECTIVE": "reflective",
}
_INITIAL_MAP = {
    "CANONICAL_SEED": "canonical_seed",
    "RANDOM_SEED": "random_seed",
    "SAVED_STATE": "saved_state",
    "DETERMINISTIC_REGENERATED": "deterministic_regenerated",
}

EXECUTION_PROFILE_SCHEMA = "archon_observer_execution_profile_v1"
EXECUTION_HORIZON_SOURCE = "OPERATOR_OVERRIDE"
EXECUTION_ATTEMPT_SCHEMA = "archon_ol2_execution_attempt_v1"


def _execution_attempt_id(runtime_id: str) -> str:
    return _token("OL2-ATTEMPT", runtime_id)


def _execution_experiment_id(source_experiment_id: str, attempt_id: str) -> str:
    digest = _canonical_hash({
        "source_experiment_id": str(source_experiment_id),
        "attempt_id": str(attempt_id),
    })[:16].upper()
    return f"EXP-EXEC-{digest}"


def _attempt_output_directory(source_output: str | Path, attempt_id: str) -> Path:
    return Path(source_output).expanduser().resolve() / "attempts" / str(attempt_id)


def _uniform_planned_horizon(matrix: list[Any]) -> int | None:
    values: set[int] = set()
    for raw in matrix:
        row = _as_dict(raw)
        try:
            value = int(row.get("duration_ticks") or 0)
        except (TypeError, ValueError):
            return None
        if value < 1:
            return None
        values.add(value)
    if len(values) != 1:
        return None
    return next(iter(values))


def _resolve_execution_profile(
    runtime: dict[str, Any],
    matrix: list[Any],
    *,
    execution_horizon: int | None,
    autosave_every: int | None,
) -> dict[str, Any]:
    planned_horizon = _uniform_planned_horizon(matrix)
    planned_autosave = int(runtime.get("checkpoint_interval") or 0)
    sample_every = int(runtime.get("sample_interval") or 0)
    if sample_every < 1 or planned_autosave < 0:
        raise ExperimentRuntimeHandoffError("runtime telemetry/checkpoint cadence is invalid")

    if execution_horizon is None:
        if planned_horizon is None:
            effective_horizon = None
        else:
            effective_horizon = planned_horizon
    else:
        if planned_horizon is None:
            raise ExperimentRuntimeHandoffError(
                "EXECUTION_HORIZON_OVERRIDE_REQUIRES_UNIFORM_PLANNED_HORIZON"
            )
        try:
            effective_horizon = int(execution_horizon)
        except (TypeError, ValueError) as exc:
            raise ExperimentRuntimeHandoffError("execution horizon must be an integer") from exc
        if effective_horizon < sample_every:
            raise ExperimentRuntimeHandoffError(
                f"execution horizon must be >= sample interval ({sample_every})"
            )
        if effective_horizon > planned_horizon:
            raise ExperimentRuntimeHandoffError(
                "execution horizon may shorten, but may not extend, the authorized scientific runtime"
            )

    if autosave_every is None:
        effective_autosave = planned_autosave
        if effective_horizon is not None and effective_autosave > effective_horizon:
            effective_autosave = effective_horizon
    else:
        try:
            effective_autosave = int(autosave_every)
        except (TypeError, ValueError) as exc:
            raise ExperimentRuntimeHandoffError("autosave cadence must be an integer") from exc
        if effective_autosave < 0:
            raise ExperimentRuntimeHandoffError("autosave cadence cannot be negative")
        if effective_horizon is not None and effective_autosave > effective_horizon:
            effective_autosave = effective_horizon

    overridden = bool(
        planned_horizon is not None
        and effective_horizon is not None
        and (
            effective_horizon != planned_horizon
            or effective_autosave != planned_autosave
        )
    )
    profile = {
        "schema": EXECUTION_PROFILE_SCHEMA,
        "planned_horizon": planned_horizon,
        "execution_horizon": effective_horizon,
        "planned_autosave_every": planned_autosave,
        "autosave_every": effective_autosave,
        "sample_every": sample_every,
        "horizon_source": EXECUTION_HORIZON_SOURCE if overridden else "PLANNED_RUNTIME",
        "overridden": overridden,
    }
    if overridden:
        identity = {
            key: profile[key]
            for key in (
                "schema",
                "planned_horizon",
                "execution_horizon",
                "planned_autosave_every",
                "autosave_every",
                "sample_every",
                "horizon_source",
            )
        }
        profile_hash = canonical_hash(identity)
        profile["profile_hash"] = profile_hash
        profile["profile_id"] = f"OL2-EXEC-{profile_hash[:16].upper()}"
    return profile


def _with_execution_profile(
    prepared: PreparedConfiguration,
    profile: dict[str, Any],
) -> PreparedConfiguration:
    if not profile.get("overridden"):
        return prepared
    context = prepared.run_spec.experimental_context
    context["execution_profile"] = {
        "schema": EXECUTION_PROFILE_SCHEMA,
        "profile_id": str(profile["profile_id"]),
        "profile_hash": str(profile["profile_hash"]),
        "planned_horizon": int(profile["planned_horizon"]),
        "execution_horizon": int(profile["execution_horizon"]),
        "planned_autosave_every": int(profile["planned_autosave_every"]),
        "autosave_every": int(profile["autosave_every"]),
        "sample_every": int(profile["sample_every"]),
        "horizon_source": EXECUTION_HORIZON_SOURCE,
    }
    spec = RunSpec.create(
        rule_id=prepared.run_spec.rule_id,
        mode=prepared.run_spec.mode,
        max_ticks=prepared.run_spec.max_ticks,
        sample_every=prepared.run_spec.sample_every,
        pressure_every=prepared.run_spec.pressure_every,
        output_dir=prepared.run_spec.output_dir,
        outputs=prepared.run_spec.outputs,
        field_width=prepared.run_spec.field_width,
        field_height=prepared.run_spec.field_height,
        topology=prepared.run_spec.topology,
        boundary_mode=prepared.run_spec.boundary_mode,
        seed=prepared.run_spec.seed,
        experimental_context=context,
    )
    review_hash = canonical_hash({
        "configuration": prepared.effective_draft.canonical_payload(),
        "forced_controls": [
            {
                "field": item.field,
                "forced_value": item.forced_value,
                "owner": item.owner,
                "reason": item.reason,
            }
            for item in prepared.forced_controls
        ],
        "run_spec_hash": spec.content_hash,
        "command": list(prepared.command),
    })
    return replace(prepared, run_spec=spec, review_hash=review_hash)


def _with_execution_attempt(
    prepared: PreparedConfiguration,
    attempt: dict[str, Any] | None,
) -> PreparedConfiguration:
    if not attempt:
        return prepared
    context = prepared.run_spec.experimental_context
    context["execution_attempt"] = dict(attempt)
    spec = RunSpec.create(
        rule_id=prepared.run_spec.rule_id,
        mode=prepared.run_spec.mode,
        max_ticks=prepared.run_spec.max_ticks,
        sample_every=prepared.run_spec.sample_every,
        pressure_every=prepared.run_spec.pressure_every,
        output_dir=prepared.run_spec.output_dir,
        outputs=prepared.run_spec.outputs,
        field_width=prepared.run_spec.field_width,
        field_height=prepared.run_spec.field_height,
        topology=prepared.run_spec.topology,
        boundary_mode=prepared.run_spec.boundary_mode,
        seed=prepared.run_spec.seed,
        experimental_context=context,
    )
    review_hash = canonical_hash({
        "configuration": prepared.effective_draft.canonical_payload(),
        "forced_controls": [
            {
                "field": item.field,
                "forced_value": item.forced_value,
                "owner": item.owner,
                "reason": item.reason,
            }
            for item in prepared.forced_controls
        ],
        "run_spec_hash": spec.content_hash,
        "command": list(prepared.command),
    })
    return replace(prepared, run_spec=spec, review_hash=review_hash)


def _with_scientific_target(
    prepared: PreparedConfiguration,
    target: dict[str, Any] | None,
) -> PreparedConfiguration:
    if not target:
        return prepared
    context = prepared.run_spec.experimental_context
    context["scientific_target"] = dict(target)
    context["scientific_target_hash"] = target.get("target_hash")
    spec = RunSpec.create(
        rule_id=prepared.run_spec.rule_id,
        mode=prepared.run_spec.mode,
        max_ticks=prepared.run_spec.max_ticks,
        sample_every=prepared.run_spec.sample_every,
        pressure_every=prepared.run_spec.pressure_every,
        output_dir=prepared.run_spec.output_dir,
        outputs=prepared.run_spec.outputs,
        field_width=prepared.run_spec.field_width,
        field_height=prepared.run_spec.field_height,
        topology=prepared.run_spec.topology,
        boundary_mode=prepared.run_spec.boundary_mode,
        seed=prepared.run_spec.seed,
        experimental_context=context,
    )
    review_hash = canonical_hash({
        "configuration": prepared.effective_draft.canonical_payload(),
        "forced_controls": [
            {
                "field": item.field,
                "forced_value": item.forced_value,
                "owner": item.owner,
                "reason": item.reason,
            }
            for item in prepared.forced_controls
        ],
        "run_spec_hash": spec.content_hash,
        "command": list(prepared.command),
    })
    return replace(prepared, run_spec=spec, review_hash=review_hash)


def _write_execution_attempt_sidecars(
    *,
    runtime_id: str,
    runtime_hash: str,
    authorization_id: str,
    source_matrix: list[Any],
    prepared_rows: tuple[PreparedConfiguration, ...] | list[PreparedConfiguration],
    attempt: dict[str, Any] | None,
    receipt_root: Path | None = None,
) -> None:
    if not attempt:
        return
    if len(source_matrix) != len(prepared_rows):
        raise ExperimentRuntimeHandoffError("execution attempt row cardinality mismatch")
    rows: list[dict[str, Any]] = []
    for raw, prepared in zip(source_matrix, prepared_rows):
        source = _as_dict(raw)
        context = prepared.run_spec.experimental_context
        execution = _as_dict(context.get("execution_attempt"))
        row_receipt = {
            "schema": EXECUTION_ATTEMPT_SCHEMA,
            "attempt_id": execution.get("attempt_id"),
            "source_runtime_id": str(runtime_id),
            "runtime_hash": str(runtime_hash),
            "authorization_id": str(authorization_id),
            "source_experiment_id": execution.get("source_experiment_id"),
            "execution_experiment_id": execution.get("execution_experiment_id"),
            "source_run_id": str(source.get("run_id") or ""),
            "rule_id": int(source.get("rule_id") or 0),
            "role": str(source.get("role") or ""),
            "replicate_index": int(source.get("replicate_index") or 0),
            "seed": (int(source["seed"]) if source.get("seed") is not None else None),
            "source_output_directory": execution.get("source_output_directory"),
            "attempt_output_directory": prepared.run_spec.output_dir,
            "review_hash": prepared.review_hash,
            "created_at_utc": attempt.get("created_at_utc"),
        }
        row_receipt["content_hash"] = _canonical_hash(row_receipt)
        output = Path(prepared.run_spec.output_dir).expanduser().resolve()
        _atomic_json(output / "ol2_execution_attempt.json", row_receipt)
        rows.append(row_receipt)
    if receipt_root is not None:
        payload = {
            "schema": EXECUTION_ATTEMPT_SCHEMA,
            "attempt_id": attempt.get("attempt_id"),
            "source_runtime_id": str(runtime_id),
            "runtime_hash": str(runtime_hash),
            "authorization_id": str(authorization_id),
            "source_experiment_id": attempt.get("source_experiment_id"),
            "execution_experiment_id": attempt.get("execution_experiment_id"),
            "row_count": len(rows),
            "rows": rows,
            "created_at_utc": attempt.get("created_at_utc"),
        }
        payload["content_hash"] = _canonical_hash(payload)
        _atomic_json(receipt_root / "ol2_execution_attempt.json", payload)


def _write_execution_profile_sidecars(
    *,
    runtime_id: str,
    runtime_hash: str,
    authorization_id: str,
    matrix: list[Any],
    prepared_rows: tuple[PreparedConfiguration, ...] | list[PreparedConfiguration],
    profile: dict[str, Any],
) -> None:
    if not profile.get("overridden"):
        return
    if len(matrix) != len(prepared_rows):
        raise ExperimentRuntimeHandoffError("execution profile row cardinality mismatch")
    for raw, prepared in zip(matrix, prepared_rows):
        row = _as_dict(raw)
        output = Path(prepared.run_spec.output_dir).expanduser().resolve()
        receipt = {
            "schema": "archon_observer_execution_profile_receipt_v1",
            "runtime_id": str(runtime_id),
            "runtime_hash": str(runtime_hash),
            "authorization_id": str(authorization_id),
            "run_id": str(row.get("run_id") or ""),
            "role": str(row.get("role") or ""),
            "rule_id": int(row.get("rule_id") or 0),
            "replicate_index": int(row.get("replicate_index") or 0),
            "seed": (int(row["seed"]) if row.get("seed") is not None else None),
            "review_hash": prepared.review_hash,
            "profile": {
                key: profile[key]
                for key in (
                    "schema",
                    "profile_id",
                    "profile_hash",
                    "planned_horizon",
                    "execution_horizon",
                    "planned_autosave_every",
                    "autosave_every",
                    "sample_every",
                    "horizon_source",
                )
            },
        }
        receipt["content_hash"] = _canonical_hash(receipt)
        _atomic_json(output / "ol2_execution_profile.json", receipt)


class AuditedExperimentRuntimeHandoff:
    """Verify Stage 6.5 authorization and project compatible rows to CONFIG1."""

    def __init__(
        self,
        project_root: Path,
        *,
        experiments_root: Path | None = None,
        authorization_script: Path | None = None,
        world_catalog: NativeWorldCatalog | None = None,
        command_service: ObserverCommandService | None = None,
        runner: Any | None = None,
        timeout: int = 120,
        pressure_every: int = 100,
        telemetry_database_path: Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.analysis_root = self.project_root / "Results" / "Analysis"
        self.experiments_root = Path(
            experiments_root or (self.analysis_root / "Experiments")
        ).resolve()
        self.authorization_script = Path(
            authorization_script or (self.project_root / "Analyzer_next/compatibility/legacy_analyzer" / "experiment_launch_authorization.py")
        ).resolve()
        self.world_catalog = world_catalog or NativeWorldCatalog()
        self.command_service = command_service or ObserverCommandService()
        self.runner = runner or _DefaultRunner()
        self.timeout = int(timeout)
        self.pressure_every = int(pressure_every)
        self.telemetry_database_path = Path(
            telemetry_database_path
            or (self.project_root / "Results" / "Universe_Search" / "observation_logs" / "telemetry.sqlite")
        ).expanduser().resolve()
        if self.pressure_every < 1:
            raise ValueError("pressure_every must be positive")

    @property
    def runtime_registry_path(self) -> Path:
        return self.experiments_root / "experiment_runtime_registry.json"

    @property
    def authorization_registry_path(self) -> Path:
        return self.experiments_root / "launch_authorization_registry.json"

    @property
    def request_path(self) -> Path:
        return self.experiments_root / "launch_authorization_request.json"

    def _registry(self) -> dict[str, Any]:
        payload = _load(self.runtime_registry_path, {})
        if not isinstance(payload, dict):
            raise ExperimentRuntimeHandoffError("runtime registry is invalid")
        return payload

    def _authorization_registry(self) -> dict[str, Any]:
        payload = _load(self.authorization_registry_path, {})
        return payload if isinstance(payload, dict) else {}

    def _index_entry(self, runtime_id: str) -> dict[str, Any]:
        matches = [
            row for row in _as_list(self._registry().get("packages"))
            if isinstance(row, dict) and str(row.get("runtime_id") or "") == runtime_id
        ]
        if len(matches) != 1:
            raise ExperimentRuntimeHandoffError(
                f"runtime {runtime_id!r} is not uniquely registered"
            )
        return dict(matches[0])

    def _package_for_entry(self, entry: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        raw_path = str(entry.get("package_path") or "").strip()
        if not raw_path:
            raise ExperimentRuntimeHandoffError("runtime registry entry has no package_path")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = (self.project_root / path).resolve()
        payload = _load(path, {})
        if not isinstance(payload, dict) or not payload:
            raise ExperimentRuntimeHandoffError(f"runtime package is missing or invalid: {path}")
        return path, payload

    def _active_authorization(self, runtime_id: str) -> dict[str, Any] | None:
        rows = [
            dict(row)
            for row in _as_list(self._authorization_registry().get("authorizations"))
            if isinstance(row, dict)
            and str(row.get("runtime_id") or "") == runtime_id
            and row.get("lifecycle_status", "ACTIVE") == "ACTIVE"
            and row.get("superseded") is not True
        ]
        if len(rows) > 1:
            raise ExperimentRuntimeHandoffError(
                f"runtime {runtime_id!r} has multiple active authorizations"
            )
        return rows[0] if rows else None

    def _verify_authorized_package(
        self, runtime_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        entry = self._index_entry(runtime_id)
        _path, package = self._package_for_entry(entry)
        runtime = _as_dict(package.get("runtime"))
        if not runtime:
            raise ExperimentRuntimeHandoffError("runtime spec is missing")
        if _canonical_hash(runtime) != str(package.get("runtime_hash") or ""):
            raise ExperimentRuntimeHandoffError("runtime package hash mismatch")
        if entry.get("runtime_hash") != package.get("runtime_hash"):
            raise ExperimentRuntimeHandoffError("runtime registry/package hash mismatch")
        if entry.get("status") != "LAUNCH_AUTHORIZED" or entry.get("launch_authorized") is not True:
            raise ExperimentRuntimeHandoffError("runtime registry is not launch-authorized")
        if package.get("status") != "LAUNCH_AUTHORIZED":
            raise ExperimentRuntimeHandoffError("runtime package is not launch-authorized")
        launch = _as_dict(package.get("launch_authorization"))
        authorization_id = str(launch.get("authorization_id") or "")
        if launch.get("authorized") is not True or not authorization_id:
            raise ExperimentRuntimeHandoffError("runtime package has no active launch authorization")
        authorization = self._active_authorization(runtime_id)
        if authorization is None:
            raise ExperimentRuntimeHandoffError("authorization registry has no active receipt")
        if authorization.get("authorization_id") != authorization_id:
            raise ExperimentRuntimeHandoffError("authorization identity mismatch")
        if authorization.get("runtime_hash") != package.get("runtime_hash"):
            raise ExperimentRuntimeHandoffError("authorization runtime hash mismatch")
        if authorization.get("verification_status") != "VERIFIED":
            raise ExperimentRuntimeHandoffError("launch authorization receipt is not VERIFIED")
        if authorization.get("execution_started") is not False:
            raise ExperimentRuntimeHandoffError("authorization registry says execution already started")
        return entry, package, authorization

    def list_runtimes(self, experiment_id: str | None = None) -> tuple[ExperimentRuntimeRow, ...]:
        registry = self._registry()
        auth_by_runtime = {
            str(row.get("runtime_id")): row
            for row in _as_list(self._authorization_registry().get("authorizations"))
            if isinstance(row, dict)
            and row.get("runtime_id")
            and row.get("lifecycle_status", "ACTIVE") == "ACTIVE"
            and row.get("superseded") is not True
        }
        rows: list[ExperimentRuntimeRow] = []
        for entry in _as_list(registry.get("packages")):
            if not isinstance(entry, dict):
                continue
            try:
                _path, package = self._package_for_entry(entry)
            except ExperimentRuntimeHandoffError:
                continue
            runtime = _as_dict(package.get("runtime"))
            package_experiment_id = str(runtime.get("experiment_id") or "").strip() or None
            if experiment_id and package_experiment_id != str(experiment_id):
                continue
            runtime_id = str(entry.get("runtime_id") or package.get("runtime_id") or "").strip()
            if not runtime_id:
                continue
            authorization = auth_by_runtime.get(runtime_id)
            launch = _as_dict(package.get("launch_authorization"))
            matrix = _as_list(runtime.get("run_matrix"))
            rows.append(
                ExperimentRuntimeRow(
                    runtime_id=runtime_id,
                    experiment_id=package_experiment_id,
                    plan_id=(str(runtime.get("plan_id")) if runtime.get("plan_id") else None),
                    status=str(entry.get("status") or package.get("status") or "UNKNOWN"),
                    run_count=int(entry.get("run_count") or len(_as_list(runtime.get("run_matrix")))),
                    unresolved_count=int(entry.get("unresolved_count") or len(_as_list(package.get("unresolved_fields")))),
                    launch_authorized=bool(entry.get("launch_authorized") is True and launch.get("authorized") is True),
                    authorization_id=(str(launch.get("authorization_id")) if launch.get("authorization_id") else None),
                    verification_status=(str(authorization.get("verification_status")) if authorization else None),
                    updated_at=(str(entry.get("updated_at") or package.get("updated_at") or "") or None),
                    experiment_type=(str(runtime.get("experiment_type")) if runtime.get("experiment_type") else None),
                    planned_horizon=_uniform_planned_horizon(matrix),
                    checkpoint_interval=(int(runtime.get("checkpoint_interval")) if runtime.get("checkpoint_interval") is not None else None),
                )
            )
        rows.sort(key=lambda row: (row.updated_at or "", row.runtime_id), reverse=True)
        return tuple(rows)

    def authorize_runtime(self, runtime_id: str, *, requested_by: str) -> RuntimeAuthorizationResult:
        runtime_id = str(runtime_id).strip()
        requested_by = str(requested_by).strip()
        if not runtime_id:
            raise ExperimentRuntimeHandoffError("runtime_id is required")
        if not requested_by:
            raise ExperimentRuntimeHandoffError("requested_by is required")
        entry = self._index_entry(runtime_id)
        _path, package = self._package_for_entry(entry)
        if entry.get("status") == "LAUNCH_AUTHORIZED" and entry.get("launch_authorized") is True:
            _entry, _package, authorization = self._verify_authorized_package(runtime_id)
            auth_id = str(authorization.get("authorization_id"))
            return RuntimeAuthorizationResult(
                runtime_id=runtime_id,
                status="ALREADY_AUTHORIZED",
                authorized=True,
                authorization_id=auth_id,
                verification_status="VERIFIED",
                message=f"{runtime_id} already has verified launch authorization {auth_id}",
            )
        if entry.get("status") != "READY_FOR_LAUNCH_REVIEW" or entry.get("launch_authorized") is not False:
            raise ExperimentRuntimeHandoffError(
                f"runtime {runtime_id} is not READY_FOR_LAUNCH_REVIEW"
            )
        if _as_list(package.get("unresolved_fields")):
            raise ExperimentRuntimeHandoffError("runtime has unresolved fields")
        authorization_id = _token("OL2-AUTH", runtime_id)
        registry = self._registry()
        request = {
            "schema": "archon_launch_authorization_request_v1",
            "authorize": True,
            "authorization_id": authorization_id,
            "runtime_id": runtime_id,
            "expected_runtime_hash": package.get("runtime_hash"),
            "expected_runtime_registry_hash": registry.get("content_hash"),
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "requested_by": requested_by,
            "confirmation": "AUTHORIZE_EXPERIMENT_LAUNCH",
            "last_consumed_authorization_id": _load(self.request_path, {}).get("last_consumed_authorization_id") if self.request_path.is_file() else None,
        }
        _atomic_json(self.request_path, request)
        if not self.authorization_script.is_file():
            raise ExperimentRuntimeHandoffError(
                f"launch authorization gateway is missing: {self.authorization_script}"
            )
        env = dict(os.environ)
        result = self.runner.run(
            command=(
                *runtime_python_command(self.project_root),
                str(self.authorization_script),
                "--analysis-root",
                str(self.analysis_root),
                "--request",
                str(self.request_path),
            ),
            cwd=self.project_root,
            environment=env,
            timeout=self.timeout,
        )
        if int(result.returncode) != 0:
            raise ExperimentRuntimeHandoffError(
                "launch authorization gateway refused or failed:\n" + str(result.output).strip()
            )
        auth_result = _load(self.experiments_root / "launch_authorization_result.json", {})
        verification = _load(
            self.experiments_root / "launch_authorization_receipt_verification.json", {}
        )
        if (
            auth_result.get("status") != "AUTHORIZED"
            or auth_result.get("authorized") is not True
            or auth_result.get("runtime_id") != runtime_id
            or auth_result.get("authorization_id") != authorization_id
            or verification.get("status") != "VERIFIED"
            or verification.get("verified") is not True
        ):
            raise ExperimentRuntimeHandoffError(
                "launch authorization did not produce a VERIFIED receipt"
            )
        self._verify_authorized_package(runtime_id)
        return RuntimeAuthorizationResult(
            runtime_id=runtime_id,
            status="AUTHORIZED",
            authorized=True,
            authorization_id=authorization_id,
            verification_status="VERIFIED",
            message=f"{runtime_id} authorized and receipt VERIFIED • execution not started",
        )

    def _execution_clone_for_runtime(
        self,
        *,
        runtime_id: str,
        package: dict[str, Any],
        authorization: dict[str, Any],
        runtime: dict[str, Any],
        matrix: list[Any],
    ) -> dict[str, Any] | None:
        # Adapter unit fixtures may omit the canonical telemetry database.
        # Production OL2 always has it; when present, execution-copy identity is
        # mandatory and failures are fail-closed.
        if not self.telemetry_database_path.is_file():
            return None
        source_experiment_ids = {
            str(_as_dict(row).get("experiment_id") or runtime.get("experiment_id") or "").strip()
            for row in matrix
        }
        source_experiment_ids.discard("")
        if len(source_experiment_ids) != 1:
            raise ExperimentRuntimeHandoffError(
                "authorized runtime execution copy requires exactly one source experiment_id"
            )
        source_experiment_id = next(iter(source_experiment_ids))
        attempt_id = _execution_attempt_id(runtime_id)
        execution_experiment_id = _execution_experiment_id(source_experiment_id, attempt_id)
        repo = ExperimentalConditionsRepository(self.telemetry_database_path)
        try:
            source = repo.get_experiment(source_experiment_id)
        except ExperimentalConditionsError as exc:
            raise ExperimentRuntimeHandoffError(
                f"cannot clone source experiment {source_experiment_id!r}: {exc}"
            ) from exc
        source_metadata = dict(source.metadata)
        created_at = datetime.now(timezone.utc).isoformat()
        clone_metadata = dict(source_metadata)
        clone_metadata.update({
            "execution_clone": True,
            "execution_clone_schema": EXECUTION_ATTEMPT_SCHEMA,
            "source_experiment_id": source_experiment_id,
            "source_runtime_id": str(runtime_id),
            "source_runtime_hash": str(package.get("runtime_hash") or ""),
            "source_authorization_id": str(authorization.get("authorization_id") or ""),
            "execution_attempt_id": attempt_id,
            "scientific_definition_copied": True,
            "created_for": "OL2_AUTHORIZED_RUNTIME_HANDOFF",
        })
        target = runtime.get("scientific_target")
        if isinstance(target, dict):
            clone_metadata["scientific_target"] = dict(target)
            clone_metadata["scientific_target_hash"] = target.get("target_hash")
        try:
            repo.create_experiment(
                experiment_id=execution_experiment_id,
                title=source.title,
                research_question=source.research_question,
                status=ExperimentStatus.PLANNED,
                metadata=clone_metadata,
            )
        except ExperimentalConditionsError as exc:
            raise ExperimentRuntimeHandoffError(
                f"could not create execution-copy experiment {execution_experiment_id!r}: {exc}"
            ) from exc
        return {
            "schema": EXECUTION_ATTEMPT_SCHEMA,
            "attempt_id": attempt_id,
            "source_runtime_id": str(runtime_id),
            "runtime_hash": str(package.get("runtime_hash") or ""),
            "authorization_id": str(authorization.get("authorization_id") or ""),
            "source_experiment_id": source_experiment_id,
            "execution_experiment_id": execution_experiment_id,
            "created_at_utc": created_at,
        }

    def prepare_authorized_runtime(
        self,
        runtime_id: str,
        *,
        execution_horizon: int | None = None,
        autosave_every: int | None = None,
    ) -> RuntimeQueuePreparation:
        _entry, package, authorization = self._verify_authorized_package(str(runtime_id).strip())
        runtime = _as_dict(package.get("runtime"))
        matrix = _as_list(runtime.get("run_matrix"))
        if not matrix:
            raise ExperimentRuntimeHandoffError("authorized runtime has an empty run matrix")
        profile = _resolve_execution_profile(
            runtime,
            matrix,
            execution_horizon=execution_horizon,
            autosave_every=autosave_every,
        )
        attempt = self._execution_clone_for_runtime(
            runtime_id=str(runtime_id),
            package=package,
            authorization=authorization,
            runtime=runtime,
            matrix=matrix,
        )
        sample_every = int(profile["sample_every"])
        effective_autosave = int(profile["autosave_every"])
        effective_matrix: list[dict[str, Any]] = []
        for raw in matrix:
            row = dict(_as_dict(raw))
            if profile.get("execution_horizon") is not None:
                row["duration_ticks"] = int(profile["execution_horizon"])
            if attempt:
                source_output = str(row.get("output_directory") or "").strip()
                if not source_output:
                    raise ExperimentRuntimeHandoffError(
                        "run matrix row is missing output identity required for execution copy"
                    )
                row["experiment_id"] = str(attempt["execution_experiment_id"])
                row["output_directory"] = str(
                    _attempt_output_directory(source_output, str(attempt["attempt_id"]))
                )
            effective_matrix.append(row)
        worlds = {row.rule_id: row for row in self.world_catalog.load_worlds()}
        prepared_rows: list[PreparedConfiguration] = []
        seen_outputs: set[str] = set()
        for raw in effective_matrix:
            row = _as_dict(raw)
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
            role_key = str(row.get("role") or "").upper()
            topology_key = str(row.get("topology") or "").upper()
            boundary_key = str(row.get("boundary_condition") or "").upper()
            initial_key = str(row.get("initial_state_mode") or runtime.get("initial_state_mode") or "").upper()
            try:
                role = _ROLE_MAP[role_key]
                topology = _TOPOLOGY_MAP[topology_key]
                boundary = _BOUNDARY_MAP[boundary_key]
                initial = _INITIAL_MAP[initial_key]
            except KeyError as exc:
                raise ExperimentRuntimeHandoffError(
                    f"unsupported authorized runtime value: {exc.args[0]}"
                ) from exc
            experiment_id = str(row.get("experiment_id") or runtime.get("experiment_id") or "").strip()
            condition_id = str(row.get("condition_id") or runtime.get("condition_id") or "").strip()
            output_dir = str(row.get("output_directory") or "").strip()
            if not experiment_id or not condition_id or not output_dir:
                raise ExperimentRuntimeHandoffError(
                    "run matrix row is missing experiment/condition/output identity"
                )
            normalized_output = str(Path(output_dir).expanduser().resolve())
            if normalized_output in seen_outputs:
                raise ExperimentRuntimeHandoffError("run matrix contains duplicate output directories")
            seen_outputs.add(normalized_output)
            seed = row.get("seed")
            draft = ConfigurationDraft(
                world=world,
                provenance=ProvenanceKind.EXPERIMENTAL,
                max_ticks=duration,
                autosave_every=effective_autosave,
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
                    f"authorized runtime row cannot be projected to CONFIG1: {reasons}"
                )
            prepared = review.prepared
            target = runtime.get("scientific_target")
            prepared = _with_scientific_target(
                prepared,
                dict(target) if isinstance(target, dict) else None,
            )
            if attempt:
                source_row = _as_dict(matrix[len(prepared_rows)])
                source_output = str(Path(str(source_row.get("output_directory") or "")).expanduser().resolve())
                execution_context = dict(attempt)
                execution_context.update({
                    "source_run_id": str(source_row.get("run_id") or ""),
                    "source_output_directory": source_output,
                    "attempt_output_directory": normalized_output,
                })
                prepared = _with_execution_attempt(prepared, execution_context)
            prepared_rows.append(_with_execution_profile(prepared, profile))
        authorization_id = str(authorization.get("authorization_id") or "")
        has_perturbation = any(
            _as_dict(row).get("perturbation") not in (None, {}, [])
            for row in effective_matrix
        )
        if has_perturbation:
            if runtime.get("experiment_type") != "perturbation_recovery_test":
                raise ExperimentRuntimeHandoffError(
                    "RUNTIME_REQUIRES_SPECIALIZED_EXECUTION_ADAPTER: perturbation rows are not projected through the canonical Observer queue"
                )
            try:
                execution_runtime = dict(runtime)
                execution_runtime["run_matrix"] = effective_matrix
                execution_runtime["checkpoint_interval"] = effective_autosave
                validate_perturbation_runtime(execution_runtime)
                preparation = prepare_perturbation_runtime(
                    runtime_id=str(runtime_id),
                    authorization_id=authorization_id,
                    runtime=execution_runtime,
                    canonical_prepared_by_run={
                        str(row.get("run_id") or ""): prepared
                        for row, prepared in zip(effective_matrix, prepared_rows)
                    },
                    project_root=self.project_root,
                    execution_attempt_id=(str(attempt["attempt_id"]) if attempt else None),
                )
                if profile.get("overridden"):
                    preparation = replace(
                        preparation,
                        message=(
                            preparation.message
                            + f" • execution horizon {int(profile['execution_horizon']):,} / "
                            f"planned {int(profile['planned_horizon']):,}"
                        ),
                    )
                    _write_execution_profile_sidecars(
                        runtime_id=str(runtime_id),
                        runtime_hash=str(package.get("runtime_hash") or ""),
                        authorization_id=authorization_id,
                        matrix=matrix,
                        prepared_rows=preparation.prepared,
                        profile=profile,
                    )
                if attempt:
                    attempt_root = (
                        self.experiments_root / "RuntimePackages" / str(runtime_id)
                        / "execution_attempts" / str(attempt["attempt_id"])
                    )
                    _write_execution_attempt_sidecars(
                        runtime_id=str(runtime_id),
                        runtime_hash=str(package.get("runtime_hash") or ""),
                        authorization_id=authorization_id,
                        source_matrix=matrix,
                        prepared_rows=preparation.prepared,
                        attempt=attempt,
                        receipt_root=attempt_root,
                    )
                    preparation = replace(
                        preparation,
                        execution_attempt_id=str(attempt["attempt_id"]),
                        execution_experiment_id=str(attempt["execution_experiment_id"]),
                        message=(
                            preparation.message
                            + f" • execution copy {attempt['attempt_id']}"
                        ),
                    )
                return preparation
            except PerturbationRuntimeHandoffError as exc:
                raise ExperimentRuntimeHandoffError(str(exc)) from exc
        profile_suffix = (
            f" • execution horizon {int(profile['execution_horizon']):,} / planned {int(profile['planned_horizon']):,}"
            if profile.get("overridden")
            else ""
        )
        preparation = RuntimeQueuePreparation(
            runtime_id=str(runtime_id),
            authorization_id=authorization_id,
            prepared=tuple(prepared_rows),
            message=(
                f"{runtime_id}: {len(prepared_rows)} authorized run(s) prepared for Queue • "
                f"queue not started{profile_suffix}"
            ),
            execution_attempt_id=(str(attempt["attempt_id"]) if attempt else None),
            execution_experiment_id=(str(attempt["execution_experiment_id"]) if attempt else None),
        )
        if profile.get("overridden"):
            _write_execution_profile_sidecars(
                runtime_id=str(runtime_id),
                runtime_hash=str(package.get("runtime_hash") or ""),
                authorization_id=authorization_id,
                matrix=matrix,
                prepared_rows=preparation.prepared,
                profile=profile,
            )
        if attempt:
            attempt_root = (
                self.experiments_root / "RuntimePackages" / str(runtime_id)
                / "execution_attempts" / str(attempt["attempt_id"])
            )
            _write_execution_attempt_sidecars(
                runtime_id=str(runtime_id),
                runtime_hash=str(package.get("runtime_hash") or ""),
                authorization_id=authorization_id,
                source_matrix=matrix,
                prepared_rows=preparation.prepared,
                attempt=attempt,
                receipt_root=attempt_root,
            )
            preparation = replace(
                preparation,
                message=preparation.message + f" • execution copy {attempt['attempt_id']}",
            )
        return preparation

    def verify_prepared_authorization(self, prepared: PreparedConfiguration) -> tuple[bool, str, str]:
        """Re-verify persisted queue rows against an active Stage 6.5 receipt."""
        if prepared.run_spec.mode != "experimental":
            return False, "NOT_EXPERIMENTAL", "prepared run is not experimental"
        matches: list[tuple[str, str]] = []
        for row in self.list_runtimes(None):
            if not row.can_queue:
                continue
            try:
                _entry, package, authorization = self._verify_authorized_package(row.runtime_id)
            except ExperimentRuntimeHandoffError:
                continue
            runtime = _as_dict(package.get("runtime"))
            execution_attempt = _as_dict(prepared.run_spec.experimental_context.get("execution_attempt"))
            if execution_attempt and str(execution_attempt.get("source_runtime_id") or "") != row.runtime_id:
                continue
            for raw in _as_list(runtime.get("run_matrix")):
                matrix = _as_dict(raw)
                if self._prepared_matches_matrix(prepared, runtime, matrix):
                    matches.append((row.runtime_id, str(authorization.get("authorization_id") or "")))
        if len(matches) != 1:
            return (
                False,
                "EXPERIMENT_AUTHORIZATION_NOT_UNIQUE",
                f"prepared run matched {len(matches)} verified authorized runtime rows",
            )
        runtime_id, authorization_id = matches[0]
        return (
            True,
            "VERIFIED_EXPERIMENT_AUTHORIZATION",
            f"runtime {runtime_id} authorized by VERIFIED receipt {authorization_id}",
        )

    def _prepared_matches_matrix(
        self,
        prepared: PreparedConfiguration,
        runtime: dict[str, Any],
        matrix: dict[str, Any],
    ) -> bool:
        spec = prepared.run_spec
        context = spec.experimental_context
        try:
            role = _ROLE_MAP[str(matrix.get("role") or "").upper()]
            topology = _TOPOLOGY_MAP[str(matrix.get("topology") or "").upper()]
            boundary = _BOUNDARY_MAP[str(matrix.get("boundary_condition") or "").upper()]
            initial = _INITIAL_MAP[
                str(
                    matrix.get("initial_state_mode")
                    or runtime.get("initial_state_mode")
                    or ""
                ).upper()
            ]
            field = list(matrix.get("field_size") or [])
            source_output = str(Path(str(matrix.get("output_directory"))).expanduser().resolve())
            seed = matrix.get("seed")
            source_experiment_id = str(matrix.get("experiment_id") or runtime.get("experiment_id") or "")
            execution_attempt = _as_dict(context.get("execution_attempt"))
            if execution_attempt:
                attempt_id = str(execution_attempt.get("attempt_id") or "")
                execution_experiment_id = str(execution_attempt.get("execution_experiment_id") or "")
                if (
                    not attempt_id
                    or str(execution_attempt.get("source_experiment_id") or "") != source_experiment_id
                    or str(execution_attempt.get("source_output_directory") or "") != source_output
                    or str(execution_attempt.get("attempt_output_directory") or "")
                    != str(_attempt_output_directory(source_output, attempt_id))
                    or context.get("experiment_id") != execution_experiment_id
                ):
                    return False
                expected_output = str(_attempt_output_directory(source_output, attempt_id))
            else:
                execution_experiment_id = source_experiment_id
                expected_output = source_output
            expected = {
                "experiment_id": execution_experiment_id,
                "condition_id": str(matrix.get("condition_id") or runtime.get("condition_id") or ""),
                "role": role,
                "replicate_index": int(matrix.get("replicate_index")),
                "field_width": int(field[0]),
                "field_height": int(field[1]),
                "topology": topology,
                "boundary_mode": boundary,
                "initial_state_mode": initial,
            }
            if seed is not None:
                expected["seed"] = int(seed)
            for key, value in expected.items():
                if context.get(key) != value:
                    return False

            planned_horizon = int(matrix.get("duration_ticks"))
            planned_autosave = int(runtime.get("checkpoint_interval") or 0)
            profile = _as_dict(context.get("execution_profile"))
            if profile:
                profile_identity = {
                    key: profile.get(key)
                    for key in (
                        "schema",
                        "planned_horizon",
                        "execution_horizon",
                        "planned_autosave_every",
                        "autosave_every",
                        "sample_every",
                        "horizon_source",
                    )
                }
                profile_hash = canonical_hash(profile_identity)
                if (
                    profile.get("schema") != EXECUTION_PROFILE_SCHEMA
                    or profile.get("horizon_source") != EXECUTION_HORIZON_SOURCE
                    or profile.get("profile_hash") != profile_hash
                    or profile.get("profile_id") != f"OL2-EXEC-{profile_hash[:16].upper()}"
                    or int(profile.get("planned_horizon") or 0) != planned_horizon
                    or int(profile.get("execution_horizon") or 0) != spec.max_ticks
                    or int(profile.get("planned_autosave_every") or 0) != planned_autosave
                    or int(profile.get("autosave_every") or -1) != prepared.effective_draft.autosave_every
                    or spec.max_ticks < int(runtime.get("sample_interval") or 0)
                    or spec.max_ticks > planned_horizon
                ):
                    return False
            else:
                if spec.max_ticks != planned_horizon:
                    return False
                if prepared.effective_draft.autosave_every != planned_autosave:
                    return False

            perturbation = _as_dict(matrix.get("perturbation"))
            command = tuple(prepared.command)
            if perturbation:
                arm = _as_dict(perturbation.get("arm"))
                arm_id = str(arm.get("arm_id") or "")
                if role != "treatment" or not arm_id:
                    return False
                if context.get("treatment_arm") != arm_id:
                    return False
                if context.get("perturbation_protocol_id") != str(perturbation.get("protocol_id") or ""):
                    return False
                if not str(context.get("mutation_id") or ""):
                    return False
                if not str(context.get("mutation_materialization_hash") or ""):
                    return False
                if not str(context.get("canonical_parent_hash") or ""):
                    return False
                if not str(context.get("mutated_rule_hash") or ""):
                    return False
                if "--rule-file" not in command or "--mutation-manifest" not in command:
                    return False
                if "--treatment-arm" not in command:
                    return False
                if "--exit-at-max-ticks" not in command:
                    return False
                if command[command.index("--treatment-arm") + 1] != arm_id:
                    return False
                if "--telemetry-db" not in command:
                    return False
                telemetry_index = command.index("--telemetry-db")
                if telemetry_index + 1 >= len(command):
                    return False
                if (
                    Path(command[telemetry_index + 1]).expanduser().resolve()
                    != self.telemetry_database_path
                ):
                    return False
            else:
                if any(
                    context.get(key)
                    for key in (
                        "treatment_arm",
                        "perturbation_protocol_id",
                        "mutation_id",
                        "mutation_materialization_hash",
                    )
                ):
                    return False
                if "--rule-file" in command or "--mutation-manifest" in command:
                    return False

            if "--max-ticks" not in command:
                return False
            max_index = command.index("--max-ticks")
            if max_index + 1 >= len(command) or int(command[max_index + 1]) != spec.max_ticks:
                return False

            return (
                spec.rule_id == int(matrix.get("rule_id"))
                and spec.sample_every == int(runtime.get("sample_interval") or 0)
                and str(Path(spec.output_dir).expanduser().resolve()) == expected_output
                and spec.seed == (int(seed) if seed is not None else None)
            )
        except (KeyError, TypeError, ValueError, IndexError):
            return False


__all__ = ["AuditedExperimentRuntimeHandoff", "ExperimentRuntimeHandoffError"]

# ARCHON RELEASE2.4 source-proven relocated compatibility dependencies.
_ARCHON_RELEASE2_RELOCATED_COMPATIBILITY_FILES = (
    'Analyzer_next/compatibility/legacy_analyzer/experiment_launch_authorization.py',
)
