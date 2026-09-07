"""Append-only authoritative ResearchCycle lifecycle for BRIDGE5.8.

The lifecycle ledger records scientific-cycle state transitions as immutable,
hash-linked receipts.  The materialized ResearchCycleRecord is a projection of
those receipts and can therefore be rebuilt after interruption without
inventing history.

This module deliberately does not interpret scientific results.  Callers must
supply references to the already-authoritative proposal/review/plan/runtime,
Observer, Analyzer, evidence, refresh, and Director artifacts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


RECORD_SCHEMA = "archon_research_cycle_record_v2"
INDEX_SCHEMA = "archon_research_cycle_index_v2"
LIFECYCLE_RECEIPT_SCHEMA = "archon_research_cycle_lifecycle_receipt_v1"
VERSION = "2.0"

ACTIVE_STATES = (
    "PROPOSED",
    "REVIEWED",
    "PLANNED",
    "MATERIALIZED",
    "QUEUED",
    "RUNNING",
    "OBSERVED",
    "ANALYZED",
    "EVIDENCE_UPDATED",
    "SCIENCE_REFRESHED",
    "DIRECTOR_REFRESHED",
)
CLOSING_STATES = ("CLOSED", "NON_DIAGNOSTIC")
FAILURE_STATES = ("BLOCKED", "FAILED", "CANCELLED")
TERMINAL_STATES = CLOSING_STATES + FAILURE_STATES
ALL_STATES = ACTIVE_STATES + TERMINAL_STATES

_NEXT_STATE = {
    state: ACTIVE_STATES[index + 1]
    for index, state in enumerate(ACTIVE_STATES[:-1])
}
_NEXT_STATE[ACTIVE_STATES[-1]] = "CLOSED"


class AuthoritativeLifecycleError(RuntimeError):
    """Raised when a lifecycle transition cannot be proven safely."""


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


@dataclass(frozen=True)
class AuthoritativeLifecyclePaths:
    project_root: Path
    analysis_root: Path

    @property
    def experiments_root(self) -> Path:
        return self.analysis_root / "Experiments"

    @property
    def records_root(self) -> Path:
        return self.experiments_root / "ResearchCycleRecords"

    @property
    def records_directory(self) -> Path:
        return self.records_root / "records"

    @property
    def lifecycle_receipts_root(self) -> Path:
        return self.records_root / "lifecycle_receipts"

    @property
    def index_path(self) -> Path:
        return self.records_root / "research_cycle_index.json"


def _record_path(paths: AuthoritativeLifecyclePaths, cycle_id: str) -> Path:
    return paths.records_directory / f"{cycle_id}.json"


def _cycle_receipts_directory(
    paths: AuthoritativeLifecyclePaths,
    cycle_id: str,
) -> Path:
    return paths.lifecycle_receipts_root / cycle_id


def _receipt_paths(
    paths: AuthoritativeLifecyclePaths,
    cycle_id: str,
) -> list[Path]:
    directory = _cycle_receipts_directory(paths, cycle_id)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def _verify_receipt(payload: Mapping[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    receipt = _as_dict(payload)
    declared = _text(receipt.get("receipt_hash"))
    core = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if (
        receipt.get("schema") != LIFECYCLE_RECEIPT_SCHEMA
        or not declared
        or canonical_hash(core) != declared
    ):
        where = f":{path}" if path is not None else ""
        raise AuthoritativeLifecycleError(f"LIFECYCLE_RECEIPT_TAMPERED{where}")
    return receipt


def _normalize_reference(
    reference: Mapping[str, Any],
    *,
    paths: AuthoritativeLifecyclePaths,
) -> dict[str, Any]:
    row = _as_dict(reference)
    kind = _text(row.get("kind"))
    reference_id = _text(row.get("id"))
    raw_path = _text(row.get("path"))
    if not kind or not reference_id:
        raise AuthoritativeLifecycleError("LIFECYCLE_REFERENCE_IDENTITY_MISSING")

    normalized: dict[str, Any] = {
        "kind": kind,
        "id": reference_id,
        "path": None,
        "sha256": _text(row.get("sha256")),
        "receipt_hash": _text(row.get("receipt_hash")),
        "timestamp": _text(row.get("timestamp")),
    }
    if raw_path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = (paths.project_root / path).resolve()
        else:
            path = path.resolve()
        digest = _file_sha256(path)
        if digest is None:
            raise AuthoritativeLifecycleError(
                f"LIFECYCLE_REFERENCE_FILE_MISSING:{kind}:{reference_id}"
            )
        declared_sha = _text(row.get("sha256"))
        if declared_sha and declared_sha != digest:
            raise AuthoritativeLifecycleError(
                f"LIFECYCLE_REFERENCE_HASH_MISMATCH:{kind}:{reference_id}"
            )
        normalized["path"] = str(path)
        normalized["sha256"] = digest

    if not normalized.get("sha256") and not normalized.get("receipt_hash"):
        raise AuthoritativeLifecycleError(
            f"LIFECYCLE_REFERENCE_HASH_MISSING:{kind}:{reference_id}"
        )
    return normalized


def _load_cycle_receipts(
    paths: AuthoritativeLifecyclePaths,
    cycle_id: str,
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    previous_hash: str | None = None
    expected_sequence = 1
    for path in _receipt_paths(paths, cycle_id):
        receipt = _verify_receipt(_read_json(path, {}), path=path)
        if receipt.get("cycle_id") != cycle_id:
            raise AuthoritativeLifecycleError("LIFECYCLE_RECEIPT_CYCLE_ID_MISMATCH")
        if receipt.get("sequence") != expected_sequence:
            raise AuthoritativeLifecycleError("LIFECYCLE_RECEIPT_SEQUENCE_INVALID")
        if receipt.get("previous_receipt_hash") != previous_hash:
            raise AuthoritativeLifecycleError("LIFECYCLE_RECEIPT_CHAIN_BROKEN")
        receipts.append(receipt)
        previous_hash = receipt.get("receipt_hash")
        expected_sequence += 1
    return receipts


def _validate_transition(previous: str | None, target: str) -> None:
    if target not in ALL_STATES:
        raise AuthoritativeLifecycleError(f"LIFECYCLE_STATE_INVALID:{target}")
    if previous is None:
        if target != "PROPOSED":
            raise AuthoritativeLifecycleError("LIFECYCLE_MUST_BEGIN_PROPOSED")
        return
    if previous in TERMINAL_STATES:
        raise AuthoritativeLifecycleError(
            f"LIFECYCLE_TERMINAL_STATE_IMMUTABLE:{previous}"
        )
    if target in FAILURE_STATES:
        return
    expected = _NEXT_STATE.get(previous)
    if target == "NON_DIAGNOSTIC" and previous == "DIRECTOR_REFRESHED":
        return
    if target != expected:
        raise AuthoritativeLifecycleError(
            f"LIFECYCLE_TRANSITION_INVALID:{previous}->{target}"
        )


def _next_required_action(state: str) -> str:
    mapping = {
        "PROPOSED": "RECORD_HUMAN_REVIEW",
        "REVIEWED": "COMMIT_EXPERIMENT_PLAN",
        "PLANNED": "MATERIALIZE_RUNTIME",
        "MATERIALIZED": "QUEUE_OBSERVER_RUN",
        "QUEUED": "START_OBSERVER_RUN",
        "RUNNING": "WAIT_FOR_OBSERVER_TERMINAL",
        "OBSERVED": "RUN_EXPERIMENT_ANALYSIS",
        "ANALYZED": "UPDATE_EXPERIMENTAL_EVIDENCE",
        "EVIDENCE_UPDATED": "RUN_SCIENTIFIC_REFRESH",
        "SCIENCE_REFRESHED": "REFRESH_RESEARCH_DIRECTOR",
        "DIRECTOR_REFRESHED": "CLOSE_RESEARCH_CYCLE",
    }
    return mapping.get(state, "NONE")


def _materialize_record_from_receipts(
    cycle_id: str,
    receipts: Sequence[Mapping[str, Any]],
    *,
    prior_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not receipts:
        raise AuthoritativeLifecycleError("LIFECYCLE_RECEIPTS_MISSING")
    identity: dict[str, Any] = {}
    references: dict[str, list[dict[str, Any]]] = {}
    blocker: dict[str, Any] | None = None
    scientific_result: str | None = None
    projected_updates: dict[str, Any] = {}
    created_at: str | None = None
    for receipt in receipts:
        created_at = created_at or _text(receipt.get("timestamp"))
        for key, value in _as_dict(receipt.get("identity_updates")).items():
            if value is None:
                continue
            previous_value = identity.get(key)
            if previous_value is not None and previous_value != value:
                raise AuthoritativeLifecycleError(
                    f"LIFECYCLE_IDENTITY_CONFLICT:{key}"
                )
            identity[key] = value
        state = str(receipt.get("to_state"))
        references.setdefault(state, []).extend(
            _as_dict(row) for row in _as_list(receipt.get("references"))
            if isinstance(row, Mapping)
        )
        if state in FAILURE_STATES:
            blocker = {
                "state": state,
                "reason": receipt.get("reason"),
                "event_id": receipt.get("event_id"),
                "receipt_hash": receipt.get("receipt_hash"),
            }
        if state == "NON_DIAGNOSTIC":
            scientific_result = "NON_DIAGNOSTIC"
        outcome = _text(receipt.get("scientific_result"))
        if outcome:
            scientific_result = outcome
        for key, value in _as_dict(receipt.get("record_updates")).items():
            if key in {
                "schema", "version", "cycle_id", "record_hash",
                "current_stage", "lifecycle_state", "lifecycle",
                "authoritative_identity", "proposal_id", "action_id",
                "plan_id", "runtime_id", "experiment_id",
                "authorization_id", "execution_attempt_id",
                "observer_run_ids",
            }:
                raise AuthoritativeLifecycleError(
                    f"LIFECYCLE_RECORD_UPDATE_RESERVED:{key}"
                )
            projected_updates[key] = value

    final = receipts[-1]
    state = str(final.get("to_state"))
    receipt_refs = [
        {
            "sequence": receipt.get("sequence"),
            "state": receipt.get("to_state"),
            "event_id": receipt.get("event_id"),
            "receipt_hash": receipt.get("receipt_hash"),
        }
        for receipt in receipts
    ]
    observer_ids = identity.get("observer_run_ids")
    if not isinstance(observer_ids, list):
        observer_ids = []

    prior = _as_dict(prior_record)
    core = {
        "schema": RECORD_SCHEMA,
        "version": VERSION,
        "cycle_id": cycle_id,
        "prior_record_schema": prior.get("schema"),
        "prior_record_hash": prior.get("record_hash"),
        "proposal_id": identity.get("proposal_id"),
        "action_id": identity.get("action_id"),
        "plan_id": identity.get("plan_id"),
        "experiment_id": identity.get("experiment_id"),
        "runtime_id": identity.get("runtime_id"),
        "authorization_id": identity.get("authorization_id"),
        "execution_attempt_id": identity.get("attempt_id"),
        "observer_run_ids": observer_ids,
        "current_stage": state,
        "lifecycle_state": state,
        "next_required_action": _next_required_action(state),
        "scientific_result": scientific_result,
        "blockers": [blocker] if blocker else [],
        "receipt_integrity": "OK",
        "authoritative_identity": identity,
        "lifecycle": {
            "schema": "archon_research_cycle_lifecycle_v1",
            "state": state,
            "transition_count": len(receipts),
            "receipt_chain_head": final.get("receipt_hash"),
            "receipts": receipt_refs,
            "references_by_state": references,
            "terminal": state in TERMINAL_STATES,
        },
        "receipts": {
            **_as_dict(prior.get("receipts")),
            "lifecycle": receipt_refs,
        },
        "created_at": created_at,
        "updated_at": final.get("timestamp"),
        "closed_at": (
            final.get("timestamp") if state in TERMINAL_STATES else None
        ),
    }
    receipt_updates = _as_dict(projected_updates.pop("receipts", {}))
    if receipt_updates:
        core["receipts"].update(receipt_updates)
    core.update(projected_updates)
    return {**core, "record_hash": canonical_hash(core)}


def _index_row(record: Mapping[str, Any], path: Path) -> dict[str, Any]:
    return {
        "cycle_id": record.get("cycle_id"),
        "proposal_id": record.get("proposal_id"),
        "action_id": record.get("action_id"),
        "plan_id": record.get("plan_id"),
        "experiment_id": record.get("experiment_id"),
        "runtime_id": record.get("runtime_id"),
        "observer_run_ids": record.get("observer_run_ids"),
        "current_stage": record.get("current_stage"),
        "lifecycle_state": record.get("lifecycle_state"),
        "next_required_action": record.get("next_required_action"),
        "scientific_result": record.get("scientific_result"),
        "blocker_count": len(_as_list(record.get("blockers"))),
        "record_hash": record.get("record_hash"),
        "record_path": str(path.resolve()),
    }


def rebuild_authoritative_cycle_index(
    paths: AuthoritativeLifecyclePaths,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if paths.records_directory.is_dir():
        for path in sorted(paths.records_directory.glob("*.json")):
            record = _as_dict(_read_json(path, {}))
            declared = _text(record.get("record_hash"))
            core = {key: value for key, value in record.items() if key != "record_hash"}
            if not declared or canonical_hash(core) != declared:
                raise AuthoritativeLifecycleError(
                    f"RESEARCH_CYCLE_RECORD_TAMPERED:{path}"
                )
            rows.append(_index_row(record, path))
    rows.sort(key=lambda row: str(row.get("cycle_id") or ""))
    core = {
        "schema": INDEX_SCHEMA,
        "version": VERSION,
        "generated_at": _now_iso(),
        "cycle_count": len(rows),
        "closed_count": sum(
            row.get("lifecycle_state") in CLOSING_STATES for row in rows
        ),
        "failed_count": sum(
            row.get("lifecycle_state") in FAILURE_STATES for row in rows
        ),
        "records": rows,
    }
    index = {**core, "content_hash": canonical_hash(rows)}
    _atomic_json(paths.index_path, index)
    return index


def rebuild_authoritative_cycles_from_receipts(
    paths: AuthoritativeLifecyclePaths,
) -> dict[str, Any]:
    """Rebuild materialized lifecycle records and index from immutable receipts."""
    cycle_ids = []
    if paths.lifecycle_receipts_root.is_dir():
        cycle_ids = sorted(
            path.name for path in paths.lifecycle_receipts_root.iterdir()
            if path.is_dir()
        )
    rebuilt: list[str] = []
    for cycle_id in cycle_ids:
        receipts = _load_cycle_receipts(paths, cycle_id)
        if not receipts:
            continue
        current_path = _record_path(paths, cycle_id)
        prior = _as_dict(_read_json(current_path, {}))
        # A crash can leave a stale projection.  Do not chain that stale hash
        # into the rebuilt record; the receipts themselves are authoritative.
        record = _materialize_record_from_receipts(
            cycle_id,
            receipts,
            prior_record={
                "schema": prior.get("prior_record_schema"),
                "record_hash": prior.get("prior_record_hash"),
                "receipts": _as_dict(prior.get("receipts")),
            },
        )
        _atomic_json(current_path, record)
        rebuilt.append(cycle_id)
    index = rebuild_authoritative_cycle_index(paths)
    return {
        "status": "COMPLETED",
        "rebuilt_cycle_ids": rebuilt,
        "cycle_count": index.get("cycle_count"),
        "index_path": str(paths.index_path),
        "content_hash": index.get("content_hash"),
    }


def _existing_record(
    paths: AuthoritativeLifecyclePaths,
    cycle_id: str,
) -> dict[str, Any]:
    path = _record_path(paths, cycle_id)
    payload = _as_dict(_read_json(path, {}))
    if not payload:
        return {}
    declared = _text(payload.get("record_hash"))
    core = {key: value for key, value in payload.items() if key != "record_hash"}
    if not declared or canonical_hash(core) != declared:
        raise AuthoritativeLifecycleError("RESEARCH_CYCLE_RECORD_TAMPERED")
    return payload


def find_authoritative_cycle(
    paths: AuthoritativeLifecyclePaths,
    *,
    proposal_id: str | None = None,
    action_id: str | None = None,
    plan_id: str | None = None,
    runtime_id: str | None = None,
) -> dict[str, Any] | None:
    criteria = {
        "proposal_id": _text(proposal_id),
        "action_id": _text(action_id),
        "plan_id": _text(plan_id),
        "runtime_id": _text(runtime_id),
    }
    criteria = {key: value for key, value in criteria.items() if value}
    if not criteria:
        raise AuthoritativeLifecycleError("CYCLE_LOOKUP_CRITERIA_MISSING")
    matches = []
    if paths.records_directory.is_dir():
        for path in sorted(paths.records_directory.glob("*.json")):
            record = _existing_record(paths, path.stem)
            if all(record.get(key) == value for key, value in criteria.items()):
                matches.append(record)
    if len(matches) > 1:
        raise AuthoritativeLifecycleError("AUTHORITATIVE_CYCLE_MATCH_NOT_UNIQUE")
    return matches[0] if matches else None


def _cycle_id_for_proposal(proposal_id: str) -> str:
    digest = canonical_hash({"proposal_id": proposal_id})[:20].upper()
    return f"RC-AUTH-{digest}"


def transition_authoritative_cycle(
    paths: AuthoritativeLifecyclePaths,
    *,
    cycle_id: str,
    to_state: str,
    event_id: str,
    references: Sequence[Mapping[str, Any]],
    identity_updates: Mapping[str, Any] | None = None,
    reason: str | None = None,
    scientific_result: str | None = None,
    record_updates: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Append one verified lifecycle transition and update its projection.

    Idempotency is event-based.  Replaying the exact same event returns the
    current materialized record; reusing an event id with changed content is
    rejected.
    """
    cycle_id = str(cycle_id).strip()
    event_id = str(event_id).strip()
    if not cycle_id or not event_id:
        raise AuthoritativeLifecycleError("LIFECYCLE_EVENT_IDENTITY_MISSING")
    normalized_refs = [
        _normalize_reference(reference, paths=paths)
        for reference in references
    ]
    if not normalized_refs:
        raise AuthoritativeLifecycleError("LIFECYCLE_TRANSITION_RECEIPT_MISSING")
    updates = {
        str(key): value for key, value in _as_dict(identity_updates).items()
        if value is not None
    }
    projection_updates = _as_dict(record_updates)

    receipts = _load_cycle_receipts(paths, cycle_id)
    previous_state = str(receipts[-1].get("to_state")) if receipts else None
    evidence_hash = canonical_hash(normalized_refs)
    event_core = {
        "to_state": to_state,
        "references": normalized_refs,
        "evidence_hash": evidence_hash,
        "identity_updates": updates,
        "reason": reason,
        "scientific_result": scientific_result,
        "record_updates": projection_updates,
    }
    for receipt in receipts:
        if receipt.get("event_id") != event_id:
            continue
        replay_core = {
            "to_state": receipt.get("to_state"),
            "references": receipt.get("references"),
            "evidence_hash": receipt.get("evidence_hash"),
            "identity_updates": receipt.get("identity_updates"),
            "reason": receipt.get("reason"),
            "scientific_result": receipt.get("scientific_result"),
            "record_updates": receipt.get("record_updates"),
        }
        if canonical_hash(replay_core) != canonical_hash(event_core):
            raise AuthoritativeLifecycleError("LIFECYCLE_EVENT_REPLAY_CONFLICT")
        record = _existing_record(paths, cycle_id)
        if not record or record.get("lifecycle", {}).get("receipt_chain_head") != receipts[-1].get("receipt_hash"):
            rebuild_authoritative_cycles_from_receipts(paths)
            record = _existing_record(paths, cycle_id)
        return record

    _validate_transition(previous_state, to_state)
    sequence = len(receipts) + 1
    previous_hash = receipts[-1].get("receipt_hash") if receipts else None
    receipt_core = {
        "schema": LIFECYCLE_RECEIPT_SCHEMA,
        "version": "1.0",
        "cycle_id": cycle_id,
        "sequence": sequence,
        "event_id": event_id,
        "from_state": previous_state,
        "to_state": to_state,
        "previous_receipt_hash": previous_hash,
        "references": normalized_refs,
        "evidence_hash": evidence_hash,
        "identity_updates": updates,
        "reason": reason,
        "scientific_result": scientific_result,
        "record_updates": projection_updates,
        "timestamp": timestamp or _now_iso(),
    }
    receipt = {**receipt_core, "receipt_hash": canonical_hash(receipt_core)}
    receipt_path = _cycle_receipts_directory(paths, cycle_id) / (
        f"{sequence:03d}_{to_state}_{canonical_hash(event_id)[:10]}.json"
    )
    _atomic_json(receipt_path, receipt)

    # The receipt is authoritative.  If the process dies after this write,
    # rebuild_authoritative_cycles_from_receipts() restores the projection.
    prior_record = _existing_record(paths, cycle_id)
    record = _materialize_record_from_receipts(
        cycle_id,
        receipts + [receipt],
        prior_record=prior_record,
    )
    _atomic_json(_record_path(paths, cycle_id), record)
    rebuild_authoritative_cycle_index(paths)
    return record


def ensure_proposed_cycle(
    paths: AuthoritativeLifecyclePaths,
    *,
    proposal_id: str,
    event_id: str,
    proposal_reference: Mapping[str, Any],
    action_id: str | None = None,
) -> dict[str, Any]:
    proposal_id = str(proposal_id).strip()
    if not proposal_id:
        raise AuthoritativeLifecycleError("PROPOSAL_ID_MISSING")
    existing = find_authoritative_cycle(paths, proposal_id=proposal_id)
    if existing is not None:
        if action_id and existing.get("action_id") not in {None, action_id}:
            raise AuthoritativeLifecycleError("PROPOSAL_ACTION_ID_CONFLICT")
        return existing
    cycle_id = _cycle_id_for_proposal(proposal_id)
    return transition_authoritative_cycle(
        paths,
        cycle_id=cycle_id,
        to_state="PROPOSED",
        event_id=event_id,
        references=[proposal_reference],
        identity_updates={
            "proposal_id": proposal_id,
            "action_id": _text(action_id),
        },
    )


def advance_cycle_by_identity(
    paths: AuthoritativeLifecyclePaths,
    *,
    to_state: str,
    event_id: str,
    references: Sequence[Mapping[str, Any]],
    proposal_id: str | None = None,
    action_id: str | None = None,
    plan_id: str | None = None,
    runtime_id: str | None = None,
    identity_updates: Mapping[str, Any] | None = None,
    reason: str | None = None,
    scientific_result: str | None = None,
    record_updates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record = find_authoritative_cycle(
        paths,
        proposal_id=proposal_id,
        action_id=action_id,
        plan_id=plan_id,
        runtime_id=runtime_id,
    )
    if record is None:
        raise AuthoritativeLifecycleError("AUTHORITATIVE_CYCLE_NOT_FOUND")
    return transition_authoritative_cycle(
        paths,
        cycle_id=str(record["cycle_id"]),
        to_state=to_state,
        event_id=event_id,
        references=references,
        identity_updates=identity_updates,
        reason=reason,
        scientific_result=scientific_result,
        record_updates=record_updates,
    )


def verify_authoritative_lifecycle(
    paths: AuthoritativeLifecyclePaths,
    cycle_id: str,
) -> tuple[bool, tuple[str, ...]]:
    issues: list[str] = []
    try:
        receipts = _load_cycle_receipts(paths, cycle_id)
        if not receipts:
            issues.append("LIFECYCLE_RECEIPTS_MISSING")
        else:
            previous: str | None = None
            for receipt in receipts:
                _validate_transition(previous, str(receipt.get("to_state")))
                previous = str(receipt.get("to_state"))
            projected = _materialize_record_from_receipts(cycle_id, receipts)
            current = _existing_record(paths, cycle_id)
            for field in (
                "cycle_id",
                "proposal_id",
                "action_id",
                "plan_id",
                "runtime_id",
                "observer_run_ids",
                "current_stage",
                "lifecycle_state",
            ):
                if current.get(field) != projected.get(field):
                    issues.append(f"RECORD_PROJECTION_MISMATCH:{field}")
            if _as_dict(current.get("lifecycle")).get("receipt_chain_head") != receipts[-1].get("receipt_hash"):
                issues.append("RECORD_RECEIPT_CHAIN_HEAD_MISMATCH")
    except AuthoritativeLifecycleError as exc:
        issues.append(str(exc))
    return not issues, tuple(issues)


__all__ = [
    "ACTIVE_STATES",
    "ALL_STATES",
    "AuthoritativeLifecycleError",
    "AuthoritativeLifecyclePaths",
    "CLOSING_STATES",
    "FAILURE_STATES",
    "INDEX_SCHEMA",
    "LIFECYCLE_RECEIPT_SCHEMA",
    "RECORD_SCHEMA",
    "TERMINAL_STATES",
    "advance_cycle_by_identity",
    "canonical_hash",
    "ensure_proposed_cycle",
    "find_authoritative_cycle",
    "rebuild_authoritative_cycle_index",
    "rebuild_authoritative_cycles_from_receipts",
    "transition_authoritative_cycle",
    "verify_authoritative_lifecycle",
]
