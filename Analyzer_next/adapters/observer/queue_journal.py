"""JSON launcher-state adapter for OL2-QUEUE1 recovery and history.

This adapter writes only launcher-owned queue metadata/history. It never opens
Observer evidence, canonical telemetry SQLite, passports, samples or run output
files during startup reconciliation.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
from typing import Any

from Analyzer_next.execution.observer.shell2.config1.model import (
    ConfigurationDraft,
    ForcedControl,
    PreparedConfiguration,
    ProvenanceKind,
    WorldIntegrity,
    WorldRecord,
    canonical_hash,
)
from Analyzer_next.execution.observer.shell2.queue1.model import (
    QueueItem,
    QueueItemStatus,
    QueueSnapshot,
)
from Analyzer_next.execution.observer.state import RunSpec


_SCHEMA = "archon_observer_launcher_2_queue_state_v1"


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _world_to_payload(world: WorldRecord | None) -> dict[str, Any] | None:
    if world is None:
        return None
    return {
        "rule_id": world.rule_id,
        "world_class": world.world_class,
        "score": world.score,
        "genome_hash": world.genome_hash,
        "observed": world.observed,
        "mutation_runs": world.mutation_runs,
        "last_run": world.last_run,
        "source_path": world.source_path,
        "integrity": world.integrity.value,
    }


def _world_from_payload(payload: dict[str, Any] | None) -> WorldRecord | None:
    if payload is None:
        return None
    return WorldRecord(
        rule_id=int(payload["rule_id"]),
        world_class=str(payload["world_class"]),
        score=float(payload["score"]) if payload.get("score") is not None else None,
        genome_hash=str(payload["genome_hash"]) if payload.get("genome_hash") is not None else None,
        observed=bool(payload.get("observed")),
        mutation_runs=int(payload.get("mutation_runs", 0)),
        last_run=str(payload.get("last_run", "—")),
        source_path=str(payload["source_path"]) if payload.get("source_path") is not None else None,
        integrity=WorldIntegrity(str(payload["integrity"])),
    )


def _draft_to_payload(draft: ConfigurationDraft) -> dict[str, Any]:
    return {
        "world": _world_to_payload(draft.world),
        "provenance": draft.provenance.value,
        "max_ticks": draft.max_ticks,
        "autosave_every": draft.autosave_every,
        "sample_every": draft.sample_every,
        "pressure_every": draft.pressure_every,
        "speed": draft.speed,
        "frame_delay_ms": draft.frame_delay_ms,
        "cell_size": draft.cell_size,
        "auto_stop": draft.auto_stop,
        "outputs": sorted(draft.outputs),
        "output_dir": draft.output_dir,
        "field_width": draft.field_width,
        "field_height": draft.field_height,
        "topology": draft.topology,
        "boundary_mode": draft.boundary_mode,
        "seed": draft.seed,
        "experiment_id": draft.experiment_id,
        "condition_id": draft.condition_id,
        "experiment_role": draft.experiment_role,
        "replicate_index": draft.replicate_index,
        "initial_state_mode": draft.initial_state_mode,
    }


def _draft_from_payload(payload: dict[str, Any]) -> ConfigurationDraft:
    return ConfigurationDraft(
        world=_world_from_payload(payload.get("world")),
        provenance=ProvenanceKind(str(payload["provenance"])),
        max_ticks=int(payload["max_ticks"]),
        autosave_every=int(payload["autosave_every"]),
        sample_every=int(payload["sample_every"]),
        pressure_every=int(payload["pressure_every"]),
        speed=int(payload["speed"]),
        frame_delay_ms=int(payload["frame_delay_ms"]),
        cell_size=int(payload["cell_size"]),
        auto_stop=bool(payload["auto_stop"]),
        outputs=frozenset(str(item) for item in payload["outputs"]),
        output_dir=str(payload["output_dir"]),
        field_width=int(payload["field_width"]),
        field_height=int(payload["field_height"]),
        topology=str(payload["topology"]),
        boundary_mode=str(payload["boundary_mode"]),
        seed=int(payload["seed"]) if payload.get("seed") is not None else None,
        experiment_id=str(payload["experiment_id"]) if payload.get("experiment_id") is not None else None,
        condition_id=str(payload["condition_id"]) if payload.get("condition_id") is not None else None,
        experiment_role=str(payload.get("experiment_role", "baseline")),
        replicate_index=int(payload.get("replicate_index", 0)),
        initial_state_mode=str(payload.get("initial_state_mode", "random_seed")),
    )


def _runspec_to_payload(spec: RunSpec) -> dict[str, Any]:
    return {
        "canonical": spec.canonical_payload(),
        "content_hash": spec.content_hash,
    }


def _runspec_from_payload(payload: dict[str, Any]) -> RunSpec:
    canonical = dict(payload["canonical"])
    spec = RunSpec.create(
        rule_id=int(canonical["rule_id"]),
        mode=str(canonical["mode"]),
        max_ticks=int(canonical["max_ticks"]),
        sample_every=int(canonical["sample_every"]),
        pressure_every=int(canonical["pressure_every"]),
        output_dir=str(canonical["output_dir"]),
        outputs=canonical.get("outputs", ()),
        field_width=int(canonical.get("field_width", 96)),
        field_height=int(canonical.get("field_height", 64)),
        topology=str(canonical.get("topology", "torus")),
        boundary_mode=str(canonical.get("boundary_mode", "wrap")),
        seed=int(canonical["seed"]) if canonical.get("seed") is not None else None,
        experimental_context=canonical.get("experimental_context") or {},
    )
    expected = str(payload["content_hash"])
    if spec.content_hash != expected:
        raise ValueError("persisted Queue1 RunSpec hash mismatch")
    return spec


def _prepared_to_payload(prepared: PreparedConfiguration) -> dict[str, Any]:
    return {
        "effective_draft": _draft_to_payload(prepared.effective_draft),
        "run_spec": _runspec_to_payload(prepared.run_spec),
        "command": list(prepared.command),
        "command_text": prepared.command_text,
        "forced_controls": [asdict(item) for item in prepared.forced_controls],
        "review_hash": prepared.review_hash,
    }


def _prepared_from_payload(payload: dict[str, Any]) -> PreparedConfiguration:
    draft = _draft_from_payload(dict(payload["effective_draft"]))
    run_spec = _runspec_from_payload(dict(payload["run_spec"]))
    command = tuple(str(item) for item in payload["command"])
    controls = tuple(ForcedControl(**dict(item)) for item in payload.get("forced_controls", ()))
    review_hash = str(payload["review_hash"])
    computed = canonical_hash(
        {
            "configuration": draft.canonical_payload(),
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
    )
    if computed != review_hash:
        raise ValueError("persisted Queue1 review hash mismatch")
    command_text = str(payload.get("command_text") or shlex.join(command))
    return PreparedConfiguration(
        effective_draft=draft,
        run_spec=run_spec,
        command=command,
        command_text=command_text,
        forced_controls=controls,
        review_hash=review_hash,
    )


def _item_to_payload(item: QueueItem) -> dict[str, Any]:
    return {
        "queue_id": item.queue_id,
        "prepared": _prepared_to_payload(item.prepared),
        "status": item.status.value,
        "retry_of": item.retry_of,
        "execution_id": item.execution_id,
        "process_identity": item.process_identity,
        "telemetry_run_id": item.telemetry_run_id,
        "exit_code": item.exit_code,
        "error": item.error,
    }


def _item_from_payload(payload: dict[str, Any]) -> QueueItem:
    return QueueItem(
        queue_id=str(payload["queue_id"]),
        prepared=_prepared_from_payload(dict(payload["prepared"])),
        status=QueueItemStatus(str(payload["status"])),
        retry_of=str(payload["retry_of"]) if payload.get("retry_of") is not None else None,
        execution_id=str(payload["execution_id"]) if payload.get("execution_id") is not None else None,
        process_identity=str(payload["process_identity"]) if payload.get("process_identity") is not None else None,
        telemetry_run_id=str(payload["telemetry_run_id"]) if payload.get("telemetry_run_id") is not None else None,
        exit_code=int(payload["exit_code"]) if payload.get("exit_code") is not None else None,
        error=str(payload["error"]) if payload.get("error") is not None else None,
    )


class JSONQueueJournal:
    """Persist Queue1 launcher state and idempotent terminal history."""

    def __init__(self, state_file: Path, history_file: Path) -> None:
        self.state_file = Path(state_file)
        self.history_file = Path(history_file)

    def load(self) -> QueueSnapshot | None:
        payload = _read_json(self.state_file, None)
        if payload is None:
            return None
        if not isinstance(payload, dict) or payload.get("schema") != _SCHEMA:
            raise ValueError("unsupported OL2-QUEUE1 state schema")
        return QueueSnapshot(
            items=tuple(_item_from_payload(dict(item)) for item in payload.get("items", ())),
            active_queue_id=(
                str(payload["active_queue_id"])
                if payload.get("active_queue_id") is not None
                else None
            ),
            dispatching=bool(payload.get("dispatching")),
            stop_requested=bool(payload.get("stop_requested")),
            blocked_queue_id=(
                str(payload["blocked_queue_id"])
                if payload.get("blocked_queue_id") is not None
                else None
            ),
            last_error=str(payload["last_error"]) if payload.get("last_error") is not None else None,
            sequence=int(payload.get("sequence", 0)),
            revision=int(payload.get("revision", 0)),
        )

    def save(self, snapshot: QueueSnapshot) -> None:
        _atomic_json(
            self.state_file,
            {
                "schema": _SCHEMA,
                "active_queue_id": snapshot.active_queue_id,
                "dispatching": snapshot.dispatching,
                "stop_requested": snapshot.stop_requested,
                "blocked_queue_id": snapshot.blocked_queue_id,
                "last_error": snapshot.last_error,
                "sequence": snapshot.sequence,
                "revision": snapshot.revision,
                "items": [_item_to_payload(item) for item in snapshot.items],
            },
        )

    def record_terminal(self, item: QueueItem) -> None:
        if not item.status.terminal:
            return
        history = _read_json(self.history_file, [])
        if not isinstance(history, list):
            history = []
        if any(
            isinstance(row, dict) and row.get("queue_id") == item.queue_id
            for row in history
        ):
            return
        history.append(
            {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "rule_id": f"{item.rule_id:05d}",
                "mode": item.mode,
                "mutation_id": None,
                "status": item.status.value.title().replace("_", " "),
                "folder": item.prepared.run_spec.output_dir,
                "exit_code": item.exit_code,
                "queue_id": item.queue_id,
                "retry_of": item.retry_of,
                "execution_id": item.execution_id,
                "telemetry_run_id": item.telemetry_run_id,
                "review_hash": item.prepared.review_hash,
                "error": item.error,
                "source": "OL2-QUEUE1",
            }
        )
        _atomic_json(self.history_file, history[-5000:])


__all__ = ["JSONQueueJournal"]
