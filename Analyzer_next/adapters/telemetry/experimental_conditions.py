#!/usr/bin/env python3
"""Native Experimental Conditions storage API for Project ARCHON.

This module is the single Python API used by Launcher, Observer, Analyzer, and
future ARCHON Studio code for controlled experimental runs.

It deliberately keeps UI concerns out of the storage layer.

Entities
--------
ExperimentalCondition
    Reusable environment definition such as field size, topology, boundary
    mode, and initial-state mode.

Experiment
    Scientific container describing one research question.

ExperimentRunRequest
    Immutable launch contract passed from Launcher to Observer.

ExperimentRunLink
    Persisted relation between an Observer run, an experiment, and a condition.

ExperimentPlan
    Validated scientific design that expands conditions and replicates into
    concrete ExperimentRunRequest objects without launching anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
import secrets
from typing import Any, Iterable, Mapping, Sequence

from Analyzer_next.core.telemetry.experimental_conditions import (
    ExperimentalConditionsRepositoryPort,
)

from .connection import connect_database
from .schema_manager import initialize_database, utc_now


CONDITION_SCHEMA_VERSION = 1


class ExperimentalConditionsError(RuntimeError):
    """Raised when an experimental definition or database action is invalid."""


class Topology(str, Enum):
    TORUS = "torus"
    BOUNDED = "bounded"


class BoundaryMode(str, Enum):
    WRAP = "wrap"
    FIXED_DEAD = "fixed_dead"
    FIXED_ALIVE = "fixed_alive"
    REFLECTIVE = "reflective"


class InitialStateMode(str, Enum):
    CANONICAL_SEED = "canonical_seed"
    RANDOM_SEED = "random_seed"
    SAVED_STATE = "saved_state"
    DETERMINISTIC_REGENERATED = "deterministic_regenerated"


class ExperimentStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"
    ARCHIVED = "archived"


class ExperimentRole(str, Enum):
    BASELINE = "baseline"
    TREATMENT = "treatment"
    CONTROL = "control"
    CALIBRATION = "calibration"


@dataclass(frozen=True, slots=True)
class ExperimentalCondition:
    condition_id: str
    name: str
    field_width: int
    field_height: int
    topology: Topology
    boundary_mode: BoundaryMode
    initial_state_mode: InitialStateMode
    parameters: Mapping[str, Any]
    condition_hash: str
    schema_version: int = CONDITION_SCHEMA_VERSION
    created_at_utc: str | None = None
    updated_at_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["topology"] = self.topology.value
        payload["boundary_mode"] = self.boundary_mode.value
        payload["initial_state_mode"] = self.initial_state_mode.value
        payload["parameters"] = dict(self.parameters)
        return payload


@dataclass(frozen=True, slots=True)
class Experiment:
    experiment_id: str
    title: str
    research_question: str | None
    status: ExperimentStatus
    metadata: Mapping[str, Any]
    created_at_utc: str | None = None
    updated_at_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class ExperimentRunRequest:
    """Canonical launch contract shared by Launcher and Observer."""

    rule_id: int
    experiment_id: str
    condition_id: str
    role: ExperimentRole
    replicate_index: int = 0

    field_width: int = 96
    field_height: int = 64
    topology: Topology = Topology.TORUS
    boundary_mode: BoundaryMode = BoundaryMode.WRAP
    initial_state_mode: InitialStateMode = InitialStateMode.CANONICAL_SEED

    max_ticks: int = 100_000
    sample_every: int = 1
    pressure_every: int = 100
    seed: int | None = None
    saved_state_path: str | None = None
    parent_run_id: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _require_positive_int(self.rule_id, "rule_id")
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_non_empty(self.condition_id, "condition_id")
        _require_positive_int(self.field_width, "field_width")
        _require_positive_int(self.field_height, "field_height")
        _require_non_negative_int(self.replicate_index, "replicate_index")
        _require_non_negative_int(self.max_ticks, "max_ticks")
        _require_positive_int(self.sample_every, "sample_every")
        _require_positive_int(self.pressure_every, "pressure_every")
        if self.seed is not None:
            _require_non_negative_int(self.seed, "seed")
        if (
            self.initial_state_mode is InitialStateMode.RANDOM_SEED
            and self.seed is None
        ):
            raise ExperimentalConditionsError(
                "random_seed mode requires a resolved experiment seed"
            )
        if (
            self.initial_state_mode is InitialStateMode.SAVED_STATE
            and not self.saved_state_path
        ):
            raise ExperimentalConditionsError(
                "saved_state_path is required for saved_state mode"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["role"] = self.role.value
        payload["topology"] = self.topology.value
        payload["boundary_mode"] = self.boundary_mode.value
        payload["initial_state_mode"] = self.initial_state_mode.value
        payload["metadata"] = dict(self.metadata or {})
        return payload

    def to_cli_args(self) -> list[str]:
        """Return Observer CLI arguments for this request.

        The Observer does not support these flags yet. This method defines the
        stable contract that the next integration step will implement.
        """
        args = [
            "--experiment-id", self.experiment_id,
            "--condition-id", self.condition_id,
            "--experiment-role", self.role.value,
            "--replicate-index", str(self.replicate_index),
            "--field-width", str(self.field_width),
            "--field-height", str(self.field_height),
            "--topology", self.topology.value,
            "--boundary-mode", self.boundary_mode.value,
            "--initial-state-mode", self.initial_state_mode.value,
            "--max-ticks", str(self.max_ticks),
            "--sample-every", str(self.sample_every),
            "--pressure-timeline-every", str(self.pressure_every),
        ]
        if self.seed is not None:
            args.extend(["--experiment-seed", str(self.seed)])
        if self.saved_state_path:
            args.extend(["--saved-state-path", self.saved_state_path])
        if self.parent_run_id:
            args.extend(["--parent-run-id", self.parent_run_id])
        return args



@dataclass(frozen=True, slots=True)
class ExperimentPlanItem:
    """One condition/role arm in an experiment plan."""

    condition_id: str
    role: ExperimentRole
    replicate_count: int = 1
    max_ticks: int = 100_000
    sample_every: int = 1
    pressure_every: int = 100
    enabled: bool = True
    seed_mode: str | None = None
    seed: int | None = None
    saved_state_path: str | None = None
    parent_run_id: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.condition_id, "condition_id")
        _require_positive_int(self.replicate_count, "replicate_count")
        _require_non_negative_int(self.max_ticks, "max_ticks")
        _require_positive_int(self.sample_every, "sample_every")
        _require_positive_int(self.pressure_every, "pressure_every")
        if self.seed_mode not in (None, "auto", "fixed"):
            raise ExperimentalConditionsError(
                "seed_mode must be None, 'auto', or 'fixed'"
            )
        if self.seed is not None:
            _require_non_negative_int(self.seed, "seed")
        if self.seed_mode == "fixed" and self.seed is None:
            raise ExperimentalConditionsError(
                "fixed seed_mode requires seed"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["role"] = self.role.value
        payload["metadata"] = dict(self.metadata or {})
        return payload


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    """Validated experiment design independent from Launcher and Observer."""

    experiment_id: str
    rule_id: int
    items: Sequence[ExperimentPlanItem]
    title: str | None = None
    research_question: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "experiment_id")
        _require_positive_int(self.rule_id, "rule_id")
        if not isinstance(self.items, Sequence) or not self.items:
            raise ExperimentalConditionsError(
                "ExperimentPlan requires at least one plan item"
            )
        if not all(isinstance(item, ExperimentPlanItem) for item in self.items):
            raise ExperimentalConditionsError(
                "ExperimentPlan.items must contain ExperimentPlanItem objects"
            )

        enabled = [item for item in self.items if item.enabled]
        if not enabled:
            raise ExperimentalConditionsError(
                "ExperimentPlan requires at least one enabled plan item"
            )

        baselines = [
            item for item in enabled
            if item.role is ExperimentRole.BASELINE
        ]
        if len(baselines) != 1:
            raise ExperimentalConditionsError(
                "ExperimentPlan requires exactly one enabled baseline item"
            )

        seen_arms: set[tuple[str, ExperimentRole]] = set()
        for item in enabled:
            key = (item.condition_id, item.role)
            if key in seen_arms:
                raise ExperimentalConditionsError(
                    "Duplicate enabled condition/role arm: "
                    f"{item.condition_id}/{item.role.value}"
                )
            seen_arms.add(key)

    @property
    def enabled_items(self) -> tuple[ExperimentPlanItem, ...]:
        return tuple(item for item in self.items if item.enabled)

    @property
    def total_runs(self) -> int:
        return sum(item.replicate_count for item in self.enabled_items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "rule_id": self.rule_id,
            "title": self.title,
            "research_question": self.research_question,
            "metadata": dict(self.metadata or {}),
            "total_runs": self.total_runs,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True, slots=True)
class ExperimentRunLink:
    experiment_run_id: str
    experiment_id: str
    run_id: str
    condition_id: str
    rule_id: int | None
    role: ExperimentRole
    replicate_index: int
    treatment_arm: str
    parent_run_id: str | None
    metadata: Mapping[str, Any]
    created_at_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["role"] = self.role.value
        payload["metadata"] = dict(self.metadata)
        return payload


def canonical_condition_payload(
    *,
    field_width: int,
    field_height: int,
    topology: Topology | str,
    boundary_mode: BoundaryMode | str,
    initial_state_mode: InitialStateMode | str,
    parameters: Mapping[str, Any] | None = None,
    schema_version: int = CONDITION_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Build the stable content used for deduplication and hashing."""
    topology = _coerce_enum(Topology, topology, "topology")
    boundary_mode = _coerce_enum(
        BoundaryMode, boundary_mode, "boundary_mode"
    )
    initial_state_mode = _coerce_enum(
        InitialStateMode, initial_state_mode, "initial_state_mode"
    )
    _validate_condition_compatibility(topology, boundary_mode)
    _require_positive_int(field_width, "field_width")
    _require_positive_int(field_height, "field_height")
    _require_positive_int(schema_version, "schema_version")

    return {
        "field_width": int(field_width),
        "field_height": int(field_height),
        "topology": topology.value,
        "boundary_mode": boundary_mode.value,
        "initial_state_mode": initial_state_mode.value,
        "parameters": _json_mapping(parameters or {}, "parameters"),
        "schema_version": int(schema_version),
    }


def condition_hash_from_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ExperimentalConditionsRepository(ExperimentalConditionsRepositoryPort):
    """Transactional native storage facade for schema-v4 experimental tables."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        initialize_database(self.database_path)

    def create_or_get_condition(
        self,
        *,
        condition_id: str,
        name: str,
        field_width: int,
        field_height: int,
        topology: Topology | str,
        boundary_mode: BoundaryMode | str,
        initial_state_mode: InitialStateMode | str,
        parameters: Mapping[str, Any] | None = None,
        schema_version: int = CONDITION_SCHEMA_VERSION,
    ) -> ExperimentalCondition:
        condition_id = _require_non_empty(condition_id, "condition_id")
        name = _require_non_empty(name, "name")

        payload = canonical_condition_payload(
            field_width=field_width,
            field_height=field_height,
            topology=topology,
            boundary_mode=boundary_mode,
            initial_state_mode=initial_state_mode,
            parameters=parameters,
            schema_version=schema_version,
        )
        digest = condition_hash_from_payload(payload)
        now = utc_now()

        connection = connect_database(self.database_path)
        try:
            existing = connection.execute(
                """
                SELECT *
                FROM experimental_conditions
                WHERE condition_hash = ?
                """,
                (digest,),
            ).fetchone()
            if existing is not None:
                return _condition_from_row(existing)

            id_collision = connection.execute(
                """
                SELECT condition_hash
                FROM experimental_conditions
                WHERE condition_id = ?
                """,
                (condition_id,),
            ).fetchone()
            if id_collision is not None:
                raise ExperimentalConditionsError(
                    f"condition_id already exists with different content: "
                    f"{condition_id!r}"
                )

            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO experimental_conditions (
                    condition_id,
                    name,
                    field_width,
                    field_height,
                    topology,
                    boundary_mode,
                    initial_state_mode,
                    condition_hash,
                    parameters_json,
                    schema_version,
                    created_at_utc,
                    updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    condition_id,
                    name,
                    payload["field_width"],
                    payload["field_height"],
                    payload["topology"],
                    payload["boundary_mode"],
                    payload["initial_state_mode"],
                    digest,
                    _json_text(payload["parameters"]),
                    payload["schema_version"],
                    now,
                    now,
                ),
            )
            connection.commit()
            return self.get_condition(condition_id, connection=connection)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_condition(
        self,
        condition_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ExperimentalCondition:
        condition_id = _require_non_empty(condition_id, "condition_id")
        owns_connection = connection is None
        conn = connection or connect_database(
            self.database_path, read_only=True
        )
        try:
            row = conn.execute(
                """
                SELECT *
                FROM experimental_conditions
                WHERE condition_id = ?
                """,
                (condition_id,),
            ).fetchone()
            if row is None:
                raise ExperimentalConditionsError(
                    f"Unknown condition_id: {condition_id!r}"
                )
            return _condition_from_row(row)
        finally:
            if owns_connection:
                conn.close()

    def list_conditions(self) -> tuple[ExperimentalCondition, ...]:
        connection = connect_database(self.database_path, read_only=True)
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM experimental_conditions
                ORDER BY created_at_utc, condition_id
                """
            ).fetchall()
            return tuple(_condition_from_row(row) for row in rows)
        finally:
            connection.close()

    def create_experiment(
        self,
        *,
        experiment_id: str,
        title: str,
        research_question: str | None = None,
        status: ExperimentStatus | str = ExperimentStatus.PLANNED,
        metadata: Mapping[str, Any] | None = None,
    ) -> Experiment:
        experiment_id = _require_non_empty(experiment_id, "experiment_id")
        title = _require_non_empty(title, "title")
        status = _coerce_enum(ExperimentStatus, status, "status")
        metadata = _json_mapping(metadata or {}, "metadata")
        now = utc_now()

        connection = connect_database(self.database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO experiments (
                    experiment_id,
                    title,
                    research_question,
                    status,
                    metadata_json,
                    created_at_utc,
                    updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    title,
                    _text_or_none(research_question),
                    status.value,
                    _json_text(metadata),
                    now,
                    now,
                ),
            )
            connection.commit()
            return self.get_experiment(experiment_id)
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ExperimentalConditionsError(
                f"Could not create experiment {experiment_id!r}: {exc}"
            ) from exc
        finally:
            connection.close()

    def get_experiment(self, experiment_id: str) -> Experiment:
        experiment_id = _require_non_empty(experiment_id, "experiment_id")
        connection = connect_database(self.database_path, read_only=True)
        try:
            row = connection.execute(
                """
                SELECT *
                FROM experiments
                WHERE experiment_id = ?
                """,
                (experiment_id,),
            ).fetchone()
            if row is None:
                raise ExperimentalConditionsError(
                    f"Unknown experiment_id: {experiment_id!r}"
                )
            return _experiment_from_row(row)
        finally:
            connection.close()

    def list_experiments(self) -> tuple[Experiment, ...]:
        connection = connect_database(self.database_path, read_only=True)
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM experiments
                ORDER BY created_at_utc, experiment_id
                """
            ).fetchall()
            return tuple(_experiment_from_row(row) for row in rows)
        finally:
            connection.close()

    def update_experiment_status(
        self,
        experiment_id: str,
        status: ExperimentStatus | str,
    ) -> Experiment:
        experiment_id = _require_non_empty(experiment_id, "experiment_id")
        status = _coerce_enum(ExperimentStatus, status, "status")
        connection = connect_database(self.database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE experiments
                SET status = ?, updated_at_utc = ?
                WHERE experiment_id = ?
                """,
                (status.value, utc_now(), experiment_id),
            )
            if cursor.rowcount != 1:
                raise ExperimentalConditionsError(
                    f"Unknown experiment_id: {experiment_id!r}"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get_experiment(experiment_id)

    def link_run(
        self,
        *,
        experiment_run_id: str,
        experiment_id: str,
        run_id: str,
        condition_id: str,
        rule_id: int | None,
        role: ExperimentRole | str,
        replicate_index: int = 0,
        treatment_arm: str = "",
        parent_run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        retry_context: Mapping[str, Any] | None = None,
    ) -> ExperimentRunLink:
        experiment_run_id = _require_non_empty(
            experiment_run_id, "experiment_run_id"
        )
        experiment_id = _require_non_empty(experiment_id, "experiment_id")
        run_id = _require_non_empty(run_id, "run_id")
        condition_id = _require_non_empty(condition_id, "condition_id")
        role = _coerce_enum(ExperimentRole, role, "role")
        _require_non_negative_int(replicate_index, "replicate_index")
        treatment_arm = str(treatment_arm or "").strip()
        if role is not ExperimentRole.TREATMENT and treatment_arm:
            raise ExperimentalConditionsError(
                "treatment_arm is only valid for treatment runs"
            )
        if rule_id is not None:
            _require_positive_int(rule_id, "rule_id")
        metadata = _json_mapping(metadata or {}, "metadata")
        retry_context = (
            _json_mapping(retry_context, "retry_context")
            if retry_context is not None
            else None
        )
        if retry_context is not None:
            retry_of_queue_id = str(
                retry_context.get("retry_of_queue_id") or ""
            ).strip()
            if not retry_of_queue_id:
                raise ExperimentalConditionsError(
                    "retry_context requires retry_of_queue_id"
                )
        else:
            retry_of_queue_id = ""

        connection = connect_database(self.database_path)
        try:
            # Serialize slot inspection + bind/update so two physical attempts
            # cannot both claim one scientific slot concurrently.
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise ExperimentalConditionsError(
                    f"Cannot link unknown run_id: {run_id!r}"
                )
            if (
                rule_id is not None
                and run["rule_id"] is not None
                and int(run["rule_id"]) != int(rule_id)
            ):
                raise ExperimentalConditionsError(
                    f"rule_id mismatch for {run_id!r}: "
                    f"runs={run['rule_id']} request={rule_id}"
                )

            effective_rule_id = (
                int(rule_id)
                if rule_id is not None
                else (
                    int(run["rule_id"])
                    if run["rule_id"] is not None
                    else None
                )
            )
            existing = connection.execute(
                """
                SELECT *
                FROM experiment_runs
                WHERE experiment_id = ?
                  AND condition_id = ?
                  AND rule_id IS ?
                  AND role = ?
                  AND replicate_index = ?
                  AND treatment_arm = ?
                """,
                (
                    experiment_id,
                    condition_id,
                    effective_rule_id,
                    role.value,
                    int(replicate_index),
                    treatment_arm,
                ),
            ).fetchone()

            if existing is not None:
                existing_run_id = str(existing["run_id"])
                if existing_run_id == run_id:
                    if str(existing["experiment_run_id"]) != experiment_run_id:
                        raise ExperimentalConditionsError(
                            "Experimental slot is already linked to this run_id "
                            "with a different experiment_run_id"
                        )
                    existing_parent = _text_or_none(existing["parent_run_id"])
                    requested_parent = _text_or_none(parent_run_id)
                    if existing_parent != requested_parent:
                        raise ExperimentalConditionsError(
                            "Experimental slot idempotency check failed: "
                            "parent_run_id drift"
                        )
                    connection.commit()
                    return _run_link_from_row(existing)

                if retry_context is None:
                    raise ExperimentalConditionsError(
                        "Experimental slot is already bound to run "
                        f"{existing_run_id!r}; a different physical run requires "
                        "explicit retry provenance"
                    )

                prior_run = connection.execute(
                    "SELECT * FROM runs WHERE run_id = ?",
                    (existing_run_id,),
                ).fetchone()
                if prior_run is None:
                    raise ExperimentalConditionsError(
                        "Experimental slot points to a missing prior run: "
                        f"{existing_run_id!r}"
                    )
                prior_status = str(prior_run["status"] or "").strip().lower()
                if prior_status == "completed":
                    raise ExperimentalConditionsError(
                        "Refusing retry supersession of a completed experimental "
                        f"slot: prior_run={existing_run_id!r}"
                    )
                if prior_status not in {"running", "failed", "stopped"}:
                    raise ExperimentalConditionsError(
                        "Experimental slot prior run has unsupported retry state: "
                        f"{prior_status!r}"
                    )

                now = utc_now()
                existing_metadata = _json_object(
                    existing["metadata_json"], "metadata_json"
                )
                prior_attempt_metadata = dict(existing_metadata)
                prior_attempt_metadata.pop("registration_history", None)
                prior_attempt_metadata.pop("retry_registration", None)
                history_value = existing_metadata.get("registration_history", [])
                history = list(history_value) if isinstance(history_value, list) else []
                history.append(
                    {
                        "experiment_run_id": str(existing["experiment_run_id"]),
                        "run_id": existing_run_id,
                        "run_status": prior_status,
                        "final_tick": prior_run["final_tick"],
                        "metadata": prior_attempt_metadata,
                        "superseded_at_utc": now,
                        "superseded_by_run_id": run_id,
                        "retry_context": dict(retry_context),
                    }
                )
                replacement_metadata = dict(metadata)
                replacement_metadata["registration_history"] = history
                replacement_metadata["retry_registration"] = {
                    "retry_of_queue_id": retry_of_queue_id,
                    "source": str(
                        retry_context.get("source")
                        or "OL2_QUEUE_RETRY_CLONE"
                    ),
                    "superseded_run_id": existing_run_id,
                    "registered_at_utc": now,
                }

                # A process can die before the telemetry writer finalizes its
                # runs row. Once QUEUE1 explicitly authorizes a retry clone,
                # close that stale physical attempt as FAILED while preserving
                # every partial channel row and deriving truthful counters.
                if prior_status == "running":
                    channel_counts: dict[str, int] = {}
                    max_ticks: list[int] = []
                    for table in ("samples", "events", "chronicle", "pressure"):
                        count_row = connection.execute(
                            f"SELECT COUNT(*) AS n, MAX(tick) AS max_tick FROM {table} WHERE run_id = ?",
                            (existing_run_id,),
                        ).fetchone()
                        channel_counts[table] = int(count_row["n"] or 0)
                        if count_row["max_tick"] is not None:
                            max_ticks.append(int(count_row["max_tick"]))
                    prior_metadata = _json_object(
                        prior_run["metadata_json"], "metadata_json"
                    )
                    prior_metadata.update(
                        {
                            "terminal_reason": (
                                "EXPERIMENT_SLOT_SUPERSEDED_BY_AUTHORIZED_RETRY"
                            ),
                            "superseded_by_run_id": run_id,
                            "retry_of_queue_id": retry_of_queue_id,
                        }
                    )
                    connection.execute(
                        """
                        UPDATE runs
                        SET status = 'failed',
                            finished_at_utc = COALESCE(finished_at_utc, ?),
                            final_tick = COALESCE(final_tick, ?),
                            samples_count = ?,
                            events_count = ?,
                            chronicle_count = ?,
                            pressure_count = ?,
                            metadata_json = ?,
                            updated_at_utc = ?
                        WHERE run_id = ?
                        """,
                        (
                            now,
                            max(max_ticks) if max_ticks else None,
                            channel_counts["samples"],
                            channel_counts["events"],
                            channel_counts["chronicle"],
                            channel_counts["pressure"],
                            _json_text(prior_metadata),
                            now,
                            existing_run_id,
                        ),
                    )

                connection.execute(
                    """
                    UPDATE experiment_runs
                    SET experiment_run_id = ?,
                        run_id = ?,
                        parent_run_id = ?,
                        metadata_json = ?
                    WHERE experiment_run_id = ?
                    """,
                    (
                        experiment_run_id,
                        run_id,
                        _text_or_none(parent_run_id),
                        _json_text(replacement_metadata),
                        str(existing["experiment_run_id"]),
                    ),
                )
                connection.commit()
                return self.get_run_link(run_id)

            connection.execute(
                """
                INSERT INTO experiment_runs (
                    experiment_run_id,
                    experiment_id,
                    run_id,
                    condition_id,
                    rule_id,
                    role,
                    replicate_index,
                    treatment_arm,
                    parent_run_id,
                    metadata_json,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_run_id,
                    experiment_id,
                    run_id,
                    condition_id,
                    effective_rule_id,
                    role.value,
                    int(replicate_index),
                    treatment_arm,
                    _text_or_none(parent_run_id),
                    _json_text(metadata),
                    utc_now(),
                ),
            )
            connection.commit()
            return self.get_run_link(run_id)
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ExperimentalConditionsError(
                f"Could not link run {run_id!r}: {exc}"
            ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_run_link(self, run_id: str) -> ExperimentRunLink:
        run_id = _require_non_empty(run_id, "run_id")
        connection = connect_database(self.database_path, read_only=True)
        try:
            row = connection.execute(
                """
                SELECT *
                FROM experiment_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise ExperimentalConditionsError(
                    f"run_id is not linked to an experiment: {run_id!r}"
                )
            return _run_link_from_row(row)
        finally:
            connection.close()

    def list_experiment_runs(
        self,
        experiment_id: str,
    ) -> tuple[ExperimentRunLink, ...]:
        experiment_id = _require_non_empty(experiment_id, "experiment_id")
        connection = connect_database(self.database_path, read_only=True)
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM experiment_runs
                WHERE experiment_id = ?
                ORDER BY role, replicate_index, created_at_utc
                """,
                (experiment_id,),
            ).fetchall()
            return tuple(_run_link_from_row(row) for row in rows)
        finally:
            connection.close()

    def validate_plan(self, plan: ExperimentPlan) -> ExperimentPlan:
        """Validate referenced experiment and conditions against SQLite."""
        if not isinstance(plan, ExperimentPlan):
            raise ExperimentalConditionsError(
                "plan must be an ExperimentPlan"
            )

        experiment = self.get_experiment(plan.experiment_id)
        condition_ids = {
            condition.condition_id
            for condition in self.list_conditions()
        }
        missing = sorted({
            item.condition_id
            for item in plan.enabled_items
            if item.condition_id not in condition_ids
        })
        if missing:
            raise ExperimentalConditionsError(
                "Unknown condition_id values in plan: "
                + ", ".join(missing)
            )

        if plan.title and plan.title != experiment.title:
            raise ExperimentalConditionsError(
                "ExperimentPlan title does not match stored experiment title"
            )
        return plan

    def next_replicate_index(
        self,
        *,
        experiment_id: str,
        condition_id: str,
        rule_id: int,
        role: ExperimentRole | str,
    ) -> int:
        """Return the first unused replicate index for one experiment arm."""
        experiment_id = _require_non_empty(
            experiment_id, "experiment_id"
        )
        condition_id = _require_non_empty(
            condition_id, "condition_id"
        )
        _require_positive_int(rule_id, "rule_id")
        role = _coerce_enum(ExperimentRole, role, "role")

        connection = connect_database(
            self.database_path,
            read_only=True,
        )
        try:
            row = connection.execute(
                """
                SELECT MAX(replicate_index) AS max_replicate_index
                FROM experiment_runs
                WHERE experiment_id = ?
                  AND condition_id = ?
                  AND rule_id = ?
                  AND role = ?
                """,
                (
                    experiment_id,
                    condition_id,
                    int(rule_id),
                    role.value,
                ),
            ).fetchone()
        finally:
            connection.close()

        maximum = (
            row["max_replicate_index"]
            if row is not None
            else None
        )
        return 0 if maximum is None else int(maximum) + 1

    def expand_plan(
        self,
        plan: ExperimentPlan,
    ) -> tuple[ExperimentRunRequest, ...]:
        """Expand enabled plan arms into collision-free launch requests."""
        self.validate_plan(plan)
        requests: list[ExperimentRunRequest] = []

        for item in plan.enabled_items:
            condition = self.get_condition(item.condition_id)
            first_replicate_index = self.next_replicate_index(
                experiment_id=plan.experiment_id,
                condition_id=item.condition_id,
                rule_id=plan.rule_id,
                role=item.role,
            )
            for local_index in range(item.replicate_count):
                replicate_index = first_replicate_index + local_index

                request_seed = item.seed
                if (
                    condition.initial_state_mode
                    is InitialStateMode.RANDOM_SEED
                    and item.seed_mode == "auto"
                ):
                    # Each replicate receives its own resolved seed before
                    # launch, so the exact ensemble remains reproducible.
                    request_seed = secrets.randbelow(2_147_483_648)

                metadata = {
                    "experiment_plan": {
                        "condition_id": item.condition_id,
                        "role": item.role.value,
                        "replicate_count": item.replicate_count,
                        "replicate_start_index": first_replicate_index,
                        "replicate_local_index": local_index,
                        "seed_mode": item.seed_mode,
                        "resolved_seed": request_seed,
                        "enabled": item.enabled,
                    },
                    **dict(plan.metadata or {}),
                    **dict(item.metadata or {}),
                }
                requests.append(
                    ExperimentRunRequest(
                        rule_id=plan.rule_id,
                        experiment_id=plan.experiment_id,
                        condition_id=item.condition_id,
                        role=item.role,
                        replicate_index=replicate_index,
                        field_width=condition.field_width,
                        field_height=condition.field_height,
                        topology=condition.topology,
                        boundary_mode=condition.boundary_mode,
                        initial_state_mode=condition.initial_state_mode,
                        max_ticks=item.max_ticks,
                        sample_every=item.sample_every,
                        pressure_every=item.pressure_every,
                        seed=request_seed,
                        saved_state_path=item.saved_state_path,
                        parent_run_id=item.parent_run_id,
                        metadata=metadata,
                    )
                )

        return tuple(requests)

    def build_run_request(
        self,
        *,
        rule_id: int,
        experiment_id: str,
        condition_id: str,
        role: ExperimentRole | str,
        replicate_index: int = 0,
        max_ticks: int = 100_000,
        sample_every: int = 1,
        pressure_every: int = 100,
        seed: int | None = None,
        saved_state_path: str | None = None,
        parent_run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ExperimentRunRequest:
        condition = self.get_condition(condition_id)
        self.get_experiment(experiment_id)
        role = _coerce_enum(ExperimentRole, role, "role")

        return ExperimentRunRequest(
            rule_id=int(rule_id),
            experiment_id=experiment_id,
            condition_id=condition_id,
            role=role,
            replicate_index=int(replicate_index),
            field_width=condition.field_width,
            field_height=condition.field_height,
            topology=condition.topology,
            boundary_mode=condition.boundary_mode,
            initial_state_mode=condition.initial_state_mode,
            max_ticks=int(max_ticks),
            sample_every=int(sample_every),
            pressure_every=int(pressure_every),
            seed=seed,
            saved_state_path=saved_state_path,
            parent_run_id=parent_run_id,
            metadata=dict(metadata or {}),
        )


def _condition_from_row(row: sqlite3.Row) -> ExperimentalCondition:
    return ExperimentalCondition(
        condition_id=str(row["condition_id"]),
        name=str(row["name"]),
        field_width=int(row["field_width"]),
        field_height=int(row["field_height"]),
        topology=Topology(str(row["topology"])),
        boundary_mode=BoundaryMode(str(row["boundary_mode"])),
        initial_state_mode=InitialStateMode(
            str(row["initial_state_mode"])
        ),
        parameters=_json_object(row["parameters_json"], "parameters_json"),
        condition_hash=str(row["condition_hash"]),
        schema_version=int(row["schema_version"]),
        created_at_utc=str(row["created_at_utc"]),
        updated_at_utc=str(row["updated_at_utc"]),
    )


def _experiment_from_row(row: sqlite3.Row) -> Experiment:
    return Experiment(
        experiment_id=str(row["experiment_id"]),
        title=str(row["title"]),
        research_question=_text_or_none(row["research_question"]),
        status=ExperimentStatus(str(row["status"])),
        metadata=_json_object(row["metadata_json"], "metadata_json"),
        created_at_utc=str(row["created_at_utc"]),
        updated_at_utc=str(row["updated_at_utc"]),
    )


def _run_link_from_row(row: sqlite3.Row) -> ExperimentRunLink:
    return ExperimentRunLink(
        experiment_run_id=str(row["experiment_run_id"]),
        experiment_id=str(row["experiment_id"]),
        run_id=str(row["run_id"]),
        condition_id=str(row["condition_id"]),
        rule_id=(
            int(row["rule_id"]) if row["rule_id"] is not None else None
        ),
        role=ExperimentRole(str(row["role"])),
        replicate_index=int(row["replicate_index"]),
        treatment_arm=str(row["treatment_arm"] or ""),
        parent_run_id=_text_or_none(row["parent_run_id"]),
        metadata=_json_object(row["metadata_json"], "metadata_json"),
        created_at_utc=str(row["created_at_utc"]),
    )


def _coerce_enum(enum_type, value: Any, field_name: str):
    try:
        return value if isinstance(value, enum_type) else enum_type(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ExperimentalConditionsError(
            f"{field_name} must be one of: {allowed}"
        ) from exc


def _validate_condition_compatibility(
    topology: Topology,
    boundary_mode: BoundaryMode,
) -> None:
    if topology is Topology.TORUS and boundary_mode is not BoundaryMode.WRAP:
        raise ExperimentalConditionsError(
            "torus topology requires wrap boundary_mode"
        )
    if topology is Topology.BOUNDED and boundary_mode is BoundaryMode.WRAP:
        raise ExperimentalConditionsError(
            "bounded topology cannot use wrap boundary_mode"
        )


def _json_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ExperimentalConditionsError(
            f"{field_name} must be a mapping"
        )
    payload = dict(value)
    try:
        json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ExperimentalConditionsError(
            f"{field_name} must be JSON serializable: {exc}"
        ) from exc
    return payload


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_object(value: str, field_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ExperimentalConditionsError(
            f"Invalid {field_name}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ExperimentalConditionsError(
            f"{field_name} must contain a JSON object"
        )
    return payload


def _require_non_empty(value: Any, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ExperimentalConditionsError(
            f"{field_name} must not be empty"
        )
    return text


def _require_positive_int(value: Any, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ExperimentalConditionsError(
            f"{field_name} must be an integer"
        ) from exc
    if number < 1:
        raise ExperimentalConditionsError(
            f"{field_name} must be >= 1"
        )
    return number


def _require_non_negative_int(value: Any, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ExperimentalConditionsError(
            f"{field_name} must be an integer"
        ) from exc
    if number < 0:
        raise ExperimentalConditionsError(
            f"{field_name} must be >= 0"
        )
    return number


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

