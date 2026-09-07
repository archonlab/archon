"""Hash-protected scientific closure for an authoritative ResearchCycleRecord.

BRIDGE5.8 joins the pre-execution plan/runtime/authorization/attempt chain to
the post-execution evidence contract, scientific-refresh receipt, and Research
Director decision.  It never reconstructs intent from observed outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from Analyzer_next.cli.evidence_engine import (
    build_experiment_principle_mappings,
    build_experimental_evidence,
)
from Analyzer_next.core.experimental_evidence.contract import (
    validate_evidence_contract,
)
from Analyzer_next.research.cycle.authoritative_lifecycle import (
    AuthoritativeLifecycleError,
    AuthoritativeLifecyclePaths,
    transition_authoritative_cycle,
)
RECORD_SCHEMA = "archon_research_cycle_record_v2"
INDEX_SCHEMA = "archon_research_cycle_index_v2"
CLOSURE_RECEIPT_SCHEMA = (
    "archon_authoritative_research_cycle_closure_receipt_v1"
)
VERSION = "2.0"


class AuthoritativeCycleError(RuntimeError):
    """Raised when a scientific cycle cannot be closed without guessing."""


def canonical_hash(payload: Any) -> str:
    """Return the repository canonical SHA-256 digest without package cycles."""
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


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _without_hash(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != field}


def _verified_hashed_payload(
    path: Path,
    *,
    hash_field: str,
) -> dict[str, Any]:
    payload = _as_dict(_read_json(path, {}))
    declared = _text(payload.get(hash_field))
    if not payload or not declared:
        raise AuthoritativeCycleError(f"HASHED_ARTIFACT_MISSING:{path}")
    if canonical_hash(_without_hash(payload, hash_field)) != declared:
        raise AuthoritativeCycleError(f"HASHED_ARTIFACT_TAMPERED:{path}")
    return payload


def _resolve_path(project_root: Path, raw: Any) -> Path:
    path = Path(str(raw or "")).expanduser()
    if not path.is_absolute():
        path = (project_root / path).resolve()
    return path.resolve()


@dataclass(frozen=True)
class AuthoritativeCyclePaths:
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
    def index_path(self) -> Path:
        return self.records_root / "research_cycle_index.json"

    @property
    def receipts_root(self) -> Path:
        return (
            self.experiments_root
            / "AuthoritativeResearchCycleClosureReceipts"
        )


def _authoritative_rows(
    request: Mapping[str, Any],
) -> list[dict[str, Any]]:
    completed = [
        _as_dict(row)
        for row in _as_list(request.get("runs"))
        if isinstance(row, Mapping) and row.get("status") == "COMPLETED"
    ]
    return [row for row in completed if _text(row.get("runtime_id"))]


def _verify_native_receipt(
    receipt: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _as_dict(receipt)
    declared = _text(payload.get("receipt_hash"))
    if not declared or canonical_hash(
        _without_hash(payload, "receipt_hash")
    ) != declared:
        raise AuthoritativeCycleError("SCIENTIFIC_REFRESH_RECEIPT_TAMPERED")
    if payload.get("status") != "COMPLETED":
        raise AuthoritativeCycleError("SCIENTIFIC_REFRESH_NOT_COMPLETED")
    if payload.get("refresh_id") != request.get("refresh_id"):
        raise AuthoritativeCycleError("SCIENTIFIC_REFRESH_ID_MISMATCH")
    expected_runs = {
        str(row.get("observer_run_id"))
        for row in _authoritative_rows(request)
        if row.get("observer_run_id")
    }
    actual_runs = {str(value) for value in _as_list(payload.get("observer_run_ids"))}
    if not expected_runs.issubset(actual_runs):
        raise AuthoritativeCycleError(
            "SCIENTIFIC_REFRESH_RUN_COVERAGE_INCOMPLETE"
        )
    if payload.get("director_products_verified") is not True:
        raise AuthoritativeCycleError("DIRECTOR_PRODUCTS_UNVERIFIED")
    return payload


def _resolve_runtime_chain(
    rows: Sequence[Mapping[str, Any]],
    *,
    paths: AuthoritativeCyclePaths,
) -> dict[str, Any]:
    runtime_ids = {_text(row.get("runtime_id")) for row in rows}
    attempt_ids = {_text(row.get("attempt_id")) for row in rows}
    authorization_ids = {_text(row.get("authorization_id")) for row in rows}
    if None in runtime_ids or len(runtime_ids) != 1:
        raise AuthoritativeCycleError("RUNTIME_ID_NOT_UNIQUE")
    if None in attempt_ids or len(attempt_ids) != 1:
        raise AuthoritativeCycleError("EXECUTION_ATTEMPT_ID_NOT_UNIQUE")
    if None in authorization_ids or len(authorization_ids) != 1:
        raise AuthoritativeCycleError("AUTHORIZATION_ID_NOT_UNIQUE")
    runtime_id = str(next(iter(runtime_ids)))
    attempt_id = str(next(iter(attempt_ids)))
    authorization_id = str(next(iter(authorization_ids)))

    runtime_registry = _as_dict(_read_json(
        paths.experiments_root / "experiment_runtime_registry.json", {}
    ))
    runtime_rows = [
        _as_dict(row)
        for row in _as_list(runtime_registry.get("packages"))
        if isinstance(row, Mapping) and row.get("runtime_id") == runtime_id
    ]
    if len(runtime_rows) != 1:
        raise AuthoritativeCycleError("RUNTIME_REGISTRY_MATCH_NOT_UNIQUE")
    runtime_row = runtime_rows[0]
    package_path = _resolve_path(paths.project_root, runtime_row.get("package_path"))
    package = _as_dict(_read_json(package_path, {}))
    runtime = _as_dict(package.get("runtime"))
    runtime_hash = _text(package.get("runtime_hash"))
    if not runtime or not runtime_hash or canonical_hash(runtime) != runtime_hash:
        raise AuthoritativeCycleError("RUNTIME_PACKAGE_HASH_INVALID")
    if runtime_row.get("runtime_hash") != runtime_hash:
        raise AuthoritativeCycleError("RUNTIME_REGISTRY_HASH_MISMATCH")
    if package.get("status") != "LAUNCH_AUTHORIZED":
        raise AuthoritativeCycleError("RUNTIME_NOT_LAUNCH_AUTHORIZED")

    launch = _as_dict(package.get("launch_authorization"))
    if (
        launch.get("authorized") is not True
        or launch.get("authorization_id") != authorization_id
    ):
        raise AuthoritativeCycleError("RUNTIME_AUTHORIZATION_MISMATCH")

    authorization_registry = _as_dict(_read_json(
        paths.experiments_root / "launch_authorization_registry.json", {}
    ))
    authorization_rows = [
        _as_dict(row)
        for row in _as_list(authorization_registry.get("authorizations"))
        if isinstance(row, Mapping)
        and row.get("authorization_id") == authorization_id
        and row.get("runtime_id") == runtime_id
        and row.get("lifecycle_status", "ACTIVE") == "ACTIVE"
        and row.get("superseded") is not True
    ]
    if len(authorization_rows) != 1:
        raise AuthoritativeCycleError("AUTHORIZATION_REGISTRY_MATCH_NOT_UNIQUE")
    authorization = authorization_rows[0]
    if (
        authorization.get("verification_status") != "VERIFIED"
        or authorization.get("runtime_hash") != runtime_hash
    ):
        raise AuthoritativeCycleError("AUTHORIZATION_NOT_VERIFIED")
    authorization_receipt_path = _resolve_path(
        paths.project_root, authorization.get("receipt_path")
    )
    authorization_receipt = _as_dict(_read_json(authorization_receipt_path, {}))
    for field, expected in (
        ("authorization_id", authorization_id),
        ("runtime_id", runtime_id),
        ("runtime_hash", runtime_hash),
    ):
        if authorization_receipt.get(field) != expected:
            raise AuthoritativeCycleError(
                f"AUTHORIZATION_RECEIPT_{field.upper()}_MISMATCH"
            )
    package_hash = _text(authorization_receipt.get("package_hash"))
    if not package_hash or package_hash != canonical_hash(package):
        raise AuthoritativeCycleError("AUTHORIZATION_PACKAGE_HASH_MISMATCH")

    row_attempt_paths = [
        _resolve_path(paths.project_root, row.get("attempt_receipt_path"))
        for row in rows
    ]
    if len(set(row_attempt_paths)) != len(rows):
        raise AuthoritativeCycleError("EXECUTION_ATTEMPT_RECEIPT_PATH_DUPLICATE")
    attempt_receipts: list[dict[str, Any]] = []
    review_hashes: list[str] = []
    observer_run_ids: list[str] = []
    execution_experiment_ids: set[str] = set()
    source_experiment_ids: set[str] = set()
    for row, attempt_path in zip(rows, row_attempt_paths):
        attempt = _verified_hashed_payload(
            attempt_path, hash_field="content_hash"
        )
        expected = {
            "attempt_id": attempt_id,
            "source_runtime_id": runtime_id,
            "runtime_hash": runtime_hash,
            "authorization_id": authorization_id,
            "review_hash": row.get("prepared_review_hash"),
        }
        mismatches = {
            key: {"expected": value, "actual": attempt.get(key)}
            for key, value in expected.items()
            if not value or attempt.get(key) != value
        }
        if mismatches:
            raise AuthoritativeCycleError(
                "EXECUTION_ATTEMPT_RECEIPT_MISMATCH:"
                + canonical_hash(mismatches)[:16]
            )
        if row.get("source_experiment_id") != attempt.get("source_experiment_id"):
            raise AuthoritativeCycleError("SOURCE_EXPERIMENT_ID_MISMATCH")
        if row.get("experiment_id") != attempt.get("execution_experiment_id"):
            raise AuthoritativeCycleError("EXECUTION_EXPERIMENT_ID_MISMATCH")
        if row.get("observer_run_id"):
            observer_run_ids.append(str(row["observer_run_id"]))
        review_hashes.append(str(attempt["review_hash"]))
        execution_experiment_ids.add(str(attempt.get("execution_experiment_id")))
        source_experiment_ids.add(str(attempt.get("source_experiment_id")))
        attempt_receipts.append({
            "path": str(attempt_path),
            "content_hash": attempt.get("content_hash"),
            "source_run_id": attempt.get("source_run_id"),
            "review_hash": attempt.get("review_hash"),
        })

    plan_id = _text(runtime.get("plan_id") or runtime_row.get("plan_id"))
    if not plan_id:
        raise AuthoritativeCycleError("PLAN_ID_MISSING")
    plan_manifest_path = paths.experiments_root / "PlanManifests" / f"{plan_id}.json"
    plan_manifest = _as_dict(_read_json(plan_manifest_path, {}))
    plan = _as_dict(plan_manifest.get("plan"))
    plan_hash = _text(plan_manifest.get("plan_hash"))
    if not plan or not plan_hash or canonical_hash(plan) != plan_hash:
        raise AuthoritativeCycleError("PLAN_MANIFEST_HASH_INVALID")
    if _text(plan.get("plan_id")) != plan_id:
        raise AuthoritativeCycleError("PLAN_MANIFEST_ID_MISMATCH")
    source_plan = _as_dict(runtime.get("source_plan"))
    source_plan_hash = _text(
        source_plan.get("plan_hash") or runtime.get("source_plan_hash")
    )
    if source_plan_hash and source_plan_hash != plan_hash:
        raise AuthoritativeCycleError("RUNTIME_PLAN_HASH_MISMATCH")
    source_manifest_hash = _text(source_plan.get("manifest_hash"))
    if (
        source_manifest_hash
        and source_manifest_hash != canonical_hash(plan_manifest)
    ):
        raise AuthoritativeCycleError("RUNTIME_PLAN_MANIFEST_HASH_MISMATCH")
    provenance = _as_dict(plan.get("provenance"))
    action_id = _text(provenance.get("source_action_id"))
    proposal_id = _text(provenance.get("source_proposal_id"))
    if not action_id:
        raise AuthoritativeCycleError("SOURCE_ACTION_ID_MISSING")
    target = _as_dict(runtime.get("scientific_target"))
    target_action_id = _text(target.get("action_id"))
    if target_action_id and target_action_id != action_id:
        raise AuthoritativeCycleError("TARGET_ACTION_ID_MISMATCH")

    identity_core = {
        "proposal_id": proposal_id,
        "action_id": action_id,
        "plan_id": plan_id,
        "plan_hash": plan_hash,
        "runtime_id": runtime_id,
        "runtime_hash": runtime_hash,
        "authorization_id": authorization_id,
        "attempt_id": attempt_id,
        "source_experiment_ids": sorted(source_experiment_ids),
        "execution_experiment_ids": sorted(execution_experiment_ids),
    }
    identity_hash = canonical_hash(identity_core)
    return {
        **identity_core,
        "cycle_id": f"RC-AUTO-{identity_hash[:20].upper()}",
        "identity_hash": identity_hash,
        "observer_run_ids": sorted(observer_run_ids),
        "review_hashes": sorted(review_hashes),
        "runtime_package_path": str(package_path),
        "plan_manifest_path": str(plan_manifest_path),
        "authorization_receipt_path": str(authorization_receipt_path),
        "authorization_receipt_hash": (
            _text(authorization_receipt.get("receipt_hash"))
            or _file_sha256(authorization_receipt_path)
        ),
        "attempt_receipts": attempt_receipts,
        "target_id": _text(target.get("target_id")),
    }


def _scientific_products(
    *,
    rows: Sequence[Mapping[str, Any]],
    paths: AuthoritativeCyclePaths,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    knowledge_path = paths.experiments_root / "experiment_knowledge.json"
    knowledge = _as_dict(_read_json(knowledge_path, {}))
    contract = _as_dict(knowledge.get("experimental_evidence_contract"))
    valid, failures = validate_evidence_contract(contract)
    if not valid:
        raise AuthoritativeCycleError(
            "EXPERIMENTAL_EVIDENCE_CONTRACT_INVALID:"
            + canonical_hash(list(failures))[:16]
        )
    channel, channel_summary = build_experimental_evidence(knowledge)
    mappings, mapping_summary = build_experiment_principle_mappings(channel)
    if channel_summary.get("contract_status") != "VALID":
        raise AuthoritativeCycleError("EVIDENCE_CHANNEL_CONTRACT_REJECTED")

    experiment_ids = {
        str(row.get("experiment_id")) for row in rows if row.get("experiment_id")
    }
    records = [
        _as_dict(record)
        for record in _as_list(contract.get("records"))
        if isinstance(record, Mapping)
        and str(record.get("experiment_id")) in experiment_ids
    ]
    if not records:
        raise AuthoritativeCycleError("SCIENTIFIC_OUTCOME_RECORDS_MISSING")
    principle_signals = [
        record for record in records
        if record.get("interpretation_level") == "PRINCIPLE_SIGNAL"
    ]
    mapping_ids = {
        str(row.get("evidence_record_id"))
        for row in mappings if isinstance(row, Mapping)
    }
    unmapped = [
        str(record.get("evidence_record_id"))
        for record in principle_signals
        if str(record.get("evidence_record_id")) not in mapping_ids
    ]
    if unmapped:
        raise AuthoritativeCycleError("TARGET_PRINCIPLE_SIGNAL_UNMAPPED")

    outcomes = []
    for record in records:
        effect = _as_dict(record.get("effect"))
        outcomes.append({
            "evidence_record_id": record.get("evidence_record_id"),
            "record_hash": record.get("record_hash"),
            "experiment_id": record.get("experiment_id"),
            "interpretation_level": record.get("interpretation_level"),
            "target_id": record.get("target_id"),
            "claim_id": record.get("claim_id"),
            "status": effect.get("status"),
            "direction": record.get("direction"),
            "relevance": record.get("relevance"),
            "parent_record_ids": _as_list(
                _as_dict(record.get("lineage")).get("parent_record_ids")
            ),
        })
    outcomes.sort(key=lambda row: str(row.get("evidence_record_id") or ""))

    product_names = (
        "evidence_report.json",
        "consensus_report.json",
        "predictions.json",
        "meta_science_report.json",
        "research_director_report.json",
        "next_research_actions.json",
    )
    products = []
    for name in product_names:
        path = paths.analysis_root / name
        digest = _file_sha256(path)
        if digest is None:
            raise AuthoritativeCycleError(f"SCIENTIFIC_PRODUCT_MISSING:{name}")
        products.append({"name": name, "path": str(path), "sha256": digest})
    products.append({
        "name": "experiment_knowledge.json",
        "path": str(knowledge_path),
        "sha256": _file_sha256(knowledge_path),
    })
    return outcomes, {
        "contract_schema": contract.get("schema"),
        "contract_hash": contract.get("contract_hash"),
        "record_count": len(outcomes),
        "principle_signal_count": len(principle_signals),
        "targeted_experiments_without_mapping": len(unmapped),
        "mapping_policy": mapping_summary.get("policy_schema"),
        "products": products,
    }


def _director_decision(paths: AuthoritativeCyclePaths) -> dict[str, Any]:
    actions_path = paths.analysis_root / "next_research_actions.json"
    payload = _as_dict(_read_json(actions_path, {}))
    actions = [
        _as_dict(row)
        for row in _as_list(payload.get("actions"))
        if isinstance(row, Mapping)
    ]
    action_ids = [_text(row.get("action_id")) for row in actions]
    if any(value is None for value in action_ids):
        raise AuthoritativeCycleError("DIRECTOR_ACTION_ID_MISSING")
    if len(action_ids) != len(set(action_ids)):
        raise AuthoritativeCycleError("DIRECTOR_ACTION_ID_DUPLICATE")
    if not actions:
        return {
            "status": "NO_NEXT_ACTION",
            "selection_policy": "DIRECTOR_ACTION_LIST_EMPTY",
            "next_action": None,
            "source_path": str(actions_path),
            "source_sha256": _file_sha256(actions_path),
        }
    selected = actions[0]
    missing = [
        field for field in ("action_id", "title", "kind", "done_when")
        if not _text(selected.get(field))
    ]
    if missing:
        raise AuthoritativeCycleError(
            "DIRECTOR_NEXT_STEP_NOT_VERIFIABLE:" + ",".join(missing)
        )
    snapshot = {
        "action_id": selected.get("action_id"),
        "priority": selected.get("priority"),
        "title": selected.get("title"),
        "kind": selected.get("kind"),
        "suggested_target": selected.get("suggested_target"),
        "done_when": selected.get("done_when"),
        "rationale": selected.get("rationale"),
        "expected_gain": selected.get("expected_gain"),
        "estimated_runtime": selected.get("estimated_runtime"),
    }
    return {
        "status": "NEXT_ACTION_SELECTED",
        "selection_policy": "FIRST_DIRECTOR_ORDERED_ACTION",
        "source_index": 0,
        "next_action": snapshot,
        "next_action_hash": canonical_hash(snapshot),
        "source_path": str(actions_path),
        "source_sha256": _file_sha256(actions_path),
    }


def _verified_existing_records(
    paths: AuthoritativeCyclePaths,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not paths.records_directory.is_dir():
        return records
    for path in sorted(paths.records_directory.glob("*.json")):
        record = _verified_hashed_payload(path, hash_field="record_hash")
        cycle_id = _text(record.get("cycle_id"))
        if not cycle_id or cycle_id in records:
            raise AuthoritativeCycleError("EXISTING_CYCLE_ID_INVALID_OR_DUPLICATE")
        records[cycle_id] = record
    existing_index = _as_dict(_read_json(paths.index_path, {}))
    if existing_index:
        rows = _as_list(existing_index.get("records"))
        if existing_index.get("content_hash") != canonical_hash(rows):
            raise AuthoritativeCycleError("RESEARCH_CYCLE_INDEX_HASH_INVALID")
        indexed = {
            _text(row.get("cycle_id")): _text(row.get("record_hash"))
            for row in rows if isinstance(row, Mapping)
        }
        actual = {
            cycle_id: _text(record.get("record_hash"))
            for cycle_id, record in records.items()
        }
        if indexed != actual:
            raise AuthoritativeCycleError("RESEARCH_CYCLE_INDEX_RECORD_MISMATCH")
    return records


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
        "scientific_result": record.get("scientific_result"),
        "next_required_action": record.get("next_required_action"),
        "director_decision_status": _as_dict(
            record.get("director_decision")
        ).get("status"),
        "blocker_count": len(_as_list(record.get("blockers"))),
        "record_hash": record.get("record_hash"),
        "record_path": str(path.resolve()),
    }


def _verified_existing_closure(
    receipt_path: Path,
    *,
    request_hash: str,
) -> dict[str, Any] | None:
    try:
        receipt = _verified_hashed_payload(
            receipt_path, hash_field="receipt_hash"
        )
    except AuthoritativeCycleError:
        return None
    if (
        receipt.get("status") != "COMPLETED"
        or receipt.get("request_hash") != request_hash
    ):
        return None
    for reference in _as_list(receipt.get("cycle_records")):
        row = _as_dict(reference)
        path = Path(str(row.get("path") or ""))
        try:
            record = _verified_hashed_payload(path, hash_field="record_hash")
        except AuthoritativeCycleError:
            return None
        if record.get("record_hash") != row.get("record_hash"):
            return None
    index_reference = _as_dict(receipt.get("research_cycle_index"))
    index_path = Path(str(index_reference.get("path") or ""))
    index = _as_dict(_read_json(index_path, {}))
    index_rows = _as_list(index.get("records"))
    if (
        not index
        or index.get("content_hash") != canonical_hash(index_rows)
        or index.get("content_hash") != index_reference.get("content_hash")
    ):
        return None
    return receipt


def close_authoritative_research_cycles(
    request: Mapping[str, Any],
    native_receipt: Mapping[str, Any],
    paths: AuthoritativeCyclePaths,
) -> dict[str, Any]:
    """Close every verified runtime/attempt group covered by one refresh."""
    authoritative = _authoritative_rows(request)
    if not authoritative:
        return {
            "status": "NOT_APPLICABLE",
            "cycle_ids": [],
            "receipt_path": None,
            "receipt_hash": None,
            "issues": [],
        }

    request_hash = str(request.get("request_hash") or "")
    refresh_id = str(request.get("refresh_id") or "")
    receipt_path = paths.receipts_root / f"{refresh_id}.json"
    existing = _verified_existing_closure(
        receipt_path, request_hash=request_hash
    )
    if existing is not None:
        return {
            "status": "REUSED",
            "cycle_ids": list(existing.get("cycle_ids", [])),
            "receipt_path": str(receipt_path),
            "receipt_hash": existing.get("receipt_hash"),
            "issues": [],
        }

    issues: list[dict[str, Any]] = []
    cycle_records: list[dict[str, Any]] = []
    started_at = _now_iso()
    try:
        native = _verify_native_receipt(
            native_receipt, request=request
        )
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in authoritative:
            key = (str(row.get("runtime_id")), str(row.get("attempt_id")))
            groups.setdefault(key, []).append(row)
        existing_records = _verified_existing_records(paths)
        director_decision = _director_decision(paths)
        for key in sorted(groups):
            rows = groups[key]
            chain = _resolve_runtime_chain(rows, paths=paths)
            outcomes, science = _scientific_products(rows=rows, paths=paths)
            observer_ids = set(chain.get("observer_run_ids", []))
            prior_matches = []
            for candidate_id, candidate in existing_records.items():
                if candidate.get("runtime_id") != chain.get("runtime_id"):
                    continue
                if candidate.get("plan_id") != chain.get("plan_id"):
                    continue
                if candidate.get("action_id") != chain.get("action_id"):
                    continue
                candidate_proposal = candidate.get("proposal_id")
                if (
                    candidate_proposal
                    and chain.get("proposal_id")
                    and candidate_proposal != chain.get("proposal_id")
                ):
                    continue
                candidate_observer_ids = {
                    str(value)
                    for value in _as_list(candidate.get("observer_run_ids"))
                    if value
                }
                if (
                    candidate_observer_ids
                    and not observer_ids.intersection(candidate_observer_ids)
                ):
                    continue
                prior_matches.append((candidate_id, candidate))
            if len(prior_matches) > 1:
                raise AuthoritativeCycleError(
                    "EXISTING_RESEARCH_CYCLE_MATCH_NOT_UNIQUE"
                )
            if prior_matches:
                cycle_id, prior_record = prior_matches[0]
            else:
                cycle_id = str(chain["cycle_id"])
                prior_record = existing_records.get(cycle_id, {})
            closure = {
                "schema": "archon_authoritative_scientific_cycle_closure_v1",
                "status": "CLOSED",
                "refresh_id": refresh_id,
                "request_hash": request_hash,
                "native_receipt_hash": native.get("receipt_hash"),
                "identity_hash": chain.get("identity_hash"),
                "scientific_outcomes": outcomes,
                "scientific_products": science,
                "closed_at": _now_iso(),
            }
            lifecycle = _as_dict(prior_record.get("lifecycle"))
            if lifecycle.get("receipt_chain_head"):
                identity_checks = {
                    "proposal_id": chain.get("proposal_id"),
                    "action_id": chain.get("action_id"),
                    "plan_id": chain.get("plan_id"),
                    "runtime_id": chain.get("runtime_id"),
                    "authorization_id": chain.get("authorization_id"),
                    "execution_attempt_id": chain.get("attempt_id"),
                }
                for field, expected in identity_checks.items():
                    actual = prior_record.get(field)
                    if expected and actual and actual != expected:
                        raise AuthoritativeCycleError(
                            f"LIFECYCLE_IDENTITY_MISMATCH:{field}"
                        )
                prior_observer_ids = {
                    str(value)
                    for value in _as_list(prior_record.get("observer_run_ids"))
                    if value
                }
                if prior_observer_ids and prior_observer_ids != observer_ids:
                    raise AuthoritativeCycleError(
                        "LIFECYCLE_OBSERVER_RUN_SET_MISMATCH"
                    )

                lifecycle_paths = AuthoritativeLifecyclePaths(
                    project_root=paths.project_root,
                    analysis_root=paths.analysis_root,
                )
                native_path = (
                    paths.experiments_root
                    / "ScientificRefreshReceipts"
                    / f"{refresh_id}.json"
                )
                knowledge_path = paths.experiments_root / "experiment_knowledge.json"
                evidence_path = paths.analysis_root / "evidence_report.json"
                director_path = paths.analysis_root / "research_director_report.json"
                next_actions_path = paths.analysis_root / "next_research_actions.json"

                def reference(kind: str, ident: str, path: Path) -> dict[str, Any]:
                    return {"kind": kind, "id": ident, "path": str(path.resolve())}

                principle_statuses = [
                    str(row.get("status") or "")
                    for row in outcomes
                    if row.get("interpretation_level") == "PRINCIPLE_SIGNAL"
                ]
                non_diagnostic = bool(principle_statuses) and all(
                    status in {"NON_DIAGNOSTIC", "INSUFFICIENT_DATA"}
                    for status in principle_statuses
                )
                final_state = "NON_DIAGNOSTIC" if non_diagnostic else "CLOSED"
                closure["scientific_result"] = (
                    "NON_DIAGNOSTIC" if non_diagnostic else "DIAGNOSTIC"
                )
                closure["terminal_state"] = final_state

                lifecycle_state = str(
                    prior_record.get("lifecycle_state")
                    or prior_record.get("current_stage")
                    or ""
                )
                terminal_states = {"CLOSED", "NON_DIAGNOSTIC", "FAILED", "BLOCKED", "CANCELLED"}
                if lifecycle_state in {"FAILED", "BLOCKED", "CANCELLED"}:
                    raise AuthoritativeCycleError(
                        f"LIFECYCLE_ALREADY_TERMINAL:{lifecycle_state}"
                    )
                existing_scientific_closure = _as_dict(
                    prior_record.get("scientific_closure")
                )
                if lifecycle_state in {"CLOSED", "NON_DIAGNOSTIC"}:
                    if existing_scientific_closure.get("request_hash") != request_hash:
                        raise AuthoritativeCycleError(
                            "CYCLE_ID_ALREADY_CLOSED_BY_DIFFERENT_REQUEST"
                        )
                    record = prior_record
                else:
                    progression = [
                        (
                            "OBSERVED",
                            "ANALYZED",
                            [reference("ExperimentKnowledge", "experiment_knowledge", knowledge_path)],
                        ),
                        (
                            "ANALYZED",
                            "EVIDENCE_UPDATED",
                            [reference("EvidenceReport", "evidence_report", evidence_path)],
                        ),
                        (
                            "EVIDENCE_UPDATED",
                            "SCIENCE_REFRESHED",
                            [reference("ScientificRefreshReceipt", refresh_id, native_path)],
                        ),
                        (
                            "SCIENCE_REFRESHED",
                            "DIRECTOR_REFRESHED",
                            [
                                reference("ResearchDirectorReport", "research_director_report", director_path),
                                reference("NextResearchActions", "next_research_actions", next_actions_path),
                            ],
                        ),
                    ]
                    record = prior_record
                    state = lifecycle_state
                    for predecessor, target, references in progression:
                        if state == target:
                            continue
                        if state != predecessor:
                            # A previous invocation may already be further along.
                            target_order = [
                                "OBSERVED", "ANALYZED", "EVIDENCE_UPDATED",
                                "SCIENCE_REFRESHED", "DIRECTOR_REFRESHED",
                            ]
                            if state in target_order and target_order.index(state) > target_order.index(target):
                                continue
                            raise AuthoritativeCycleError(
                                f"LIFECYCLE_SCIENCE_REFRESH_START_INVALID:{state}"
                            )
                        try:
                            record = transition_authoritative_cycle(
                                lifecycle_paths,
                                cycle_id=cycle_id,
                                to_state=target,
                                event_id=(
                                    f"BRIDGE5.8:{cycle_id}:{target}:{request_hash[:16]}"
                                ),
                                references=references,
                            )
                        except AuthoritativeLifecycleError as exc:
                            raise AuthoritativeCycleError(str(exc)) from exc
                        state = target

                    if state != "DIRECTOR_REFRESHED":
                        raise AuthoritativeCycleError(
                            f"LIFECYCLE_DIRECTOR_REFRESH_NOT_REACHED:{state}"
                        )
                    record_updates = {
                        "source_experiment_ids": chain.get("source_experiment_ids"),
                        "execution_experiment_ids": chain.get("execution_experiment_ids"),
                        "telemetry_status": "COMPLETED",
                        "profile_status": "COMPLETED",
                        "scientific_refresh_status": "COMPLETED",
                        "director_refresh_status": "COMPLETED",
                        "browser_publish_status": (
                            prior_record.get("browser_publish_status")
                            or "NOT_APPLICABLE"
                        ),
                        "scientific_closure": closure,
                        "director_decision": director_decision,
                        "execution_chain": chain,
                        "receipts": {
                            "scientific_refresh": {
                                "schema": native.get("schema"),
                                "status": native.get("status"),
                                "receipt_hash": native.get("receipt_hash"),
                                "hash_verified": True,
                            },
                            "launch_authorization": {
                                "path": chain.get("authorization_receipt_path"),
                                "receipt_hash": chain.get("authorization_receipt_hash"),
                                "hash_verified": True,
                            },
                            "execution_attempts": chain.get("attempt_receipts"),
                        },
                    }
                    try:
                        record = transition_authoritative_cycle(
                            lifecycle_paths,
                            cycle_id=cycle_id,
                            to_state=final_state,
                            event_id=(
                                f"BRIDGE5.8:{cycle_id}:{final_state}:{request_hash[:16]}"
                            ),
                            references=[
                                reference("ScientificRefreshReceipt", refresh_id, native_path),
                                reference("NextResearchActions", "next_research_actions", next_actions_path),
                            ],
                            scientific_result=(
                                "NON_DIAGNOSTIC" if non_diagnostic else "DIAGNOSTIC"
                            ),
                            reason=(
                                "SCIENTIFIC_RESULT_NON_DIAGNOSTIC"
                                if non_diagnostic
                                else None
                            ),
                            record_updates=record_updates,
                        )
                    except AuthoritativeLifecycleError as exc:
                        raise AuthoritativeCycleError(str(exc)) from exc

                existing_records[cycle_id] = record
                cycle_records.append(record)
                continue

            record_core = {
                "schema": RECORD_SCHEMA,
                "version": VERSION,
                "cycle_id": cycle_id,
                "prior_record_schema": prior_record.get("schema"),
                "prior_record_hash": prior_record.get("record_hash"),
                "proposal_id": chain.get("proposal_id"),
                "action_id": chain.get("action_id"),
                "plan_id": chain.get("plan_id"),
                "experiment_id": (
                    chain.get("execution_experiment_ids", [None])[0]
                    if len(chain.get("execution_experiment_ids", [])) == 1
                    else None
                ),
                "source_experiment_ids": chain.get("source_experiment_ids"),
                "execution_experiment_ids": chain.get(
                    "execution_experiment_ids"
                ),
                "runtime_id": chain.get("runtime_id"),
                "authorization_id": chain.get("authorization_id"),
                "execution_attempt_id": chain.get("attempt_id"),
                "observer_run_ids": chain.get("observer_run_ids"),
                "telemetry_status": "COMPLETED",
                "profile_status": "COMPLETED",
                "scientific_refresh_status": "COMPLETED",
                "director_refresh_status": "COMPLETED",
                "browser_publish_status": (
                    prior_record.get("browser_publish_status")
                    or "NOT_APPLICABLE"
                ),
                "current_stage": "COMPLETED",
                "next_required_action": "NONE",
                "blockers": [],
                "receipt_integrity": "OK",
                "authoritative_identity": chain,
                "recovery_status": (
                    "VERIFIED_HISTORICAL_CHAIN"
                    if all(
                        str(row.get("status") or "")
                        in {"NON_DIAGNOSTIC", "INSUFFICIENT_DATA"}
                        for row in outcomes
                        if row.get("interpretation_level") == "PRINCIPLE_SIGNAL"
                    ) and any(
                        row.get("interpretation_level") == "PRINCIPLE_SIGNAL"
                        for row in outcomes
                    )
                    else None
                ),
                "scientific_result": (
                    "NON_DIAGNOSTIC"
                    if all(
                        str(row.get("status") or "")
                        in {"NON_DIAGNOSTIC", "INSUFFICIENT_DATA"}
                        for row in outcomes
                        if row.get("interpretation_level") == "PRINCIPLE_SIGNAL"
                    ) and any(
                        row.get("interpretation_level") == "PRINCIPLE_SIGNAL"
                        for row in outcomes
                    )
                    else "DIAGNOSTIC"
                ),
                "reason": (
                    "HISTORICAL_TARGET_METRICS_NOT_PRECOMMITTED"
                    if all(
                        str(row.get("status") or "")
                        in {"NON_DIAGNOSTIC", "INSUFFICIENT_DATA"}
                        for row in outcomes
                        if row.get("interpretation_level") == "PRINCIPLE_SIGNAL"
                    ) and any(
                        row.get("interpretation_level") == "PRINCIPLE_SIGNAL"
                        for row in outcomes
                    )
                    else None
                ),
                "scientific_closure": closure,
                "director_decision": director_decision,
                "receipts": {
                    **_as_dict(prior_record.get("receipts")),
                    "scientific_refresh": {
                        "schema": native.get("schema"),
                        "status": native.get("status"),
                        "receipt_hash": native.get("receipt_hash"),
                        "hash_verified": True,
                    },
                    "launch_authorization": {
                        "path": chain.get("authorization_receipt_path"),
                        "receipt_hash": chain.get("authorization_receipt_hash"),
                        "hash_verified": True,
                    },
                    "execution_attempts": chain.get("attempt_receipts"),
                },
                "updated_at": _now_iso(),
            }
            record = {
                **record_core,
                "record_hash": canonical_hash(record_core),
            }
            prior = existing_records.get(cycle_id)
            if prior and prior.get("record_hash") != record.get("record_hash"):
                prior_closure = _as_dict(prior.get("scientific_closure"))
                if (
                    prior.get("schema") == RECORD_SCHEMA
                    and prior_closure.get("request_hash") != request_hash
                ):
                    raise AuthoritativeCycleError(
                        "CYCLE_ID_ALREADY_CLOSED_BY_DIFFERENT_REQUEST"
                    )
            existing_records[cycle_id] = record
            cycle_records.append(record)

        for record in cycle_records:
            _atomic_json(
                paths.records_directory / f"{record['cycle_id']}.json",
                record,
            )
        index_rows = [
            _index_row(
                record,
                paths.records_directory / f"{cycle_id}.json",
            )
            for cycle_id, record in sorted(existing_records.items())
        ]
        index_core = {
            "schema": INDEX_SCHEMA,
            "version": VERSION,
            "generated_at": _now_iso(),
            "cycle_count": len(index_rows),
            "completed_count": sum(
                row.get("current_stage") in {"COMPLETED", "CLOSED", "NON_DIAGNOSTIC"}
                for row in index_rows
            ),
            "blocked_count": sum(
                bool(row.get("blocker_count")) for row in index_rows
            ),
            "records": index_rows,
        }
        index = {
            **index_core,
            "content_hash": canonical_hash(index_rows),
        }
        _atomic_json(paths.index_path, index)
    except AuthoritativeCycleError as exc:
        issues.append({
            "code": str(exc).split(":", 1)[0],
            "message": str(exc),
        })
    except Exception as exc:  # fail closed with a durable typed boundary
        issues.append({
            "code": "AUTHORITATIVE_CYCLE_CLOSURE_ERROR",
            "message": f"{type(exc).__name__}: {exc}",
        })

    status = "COMPLETED" if not issues else "FAILED"
    cycle_references = [
        {
            "cycle_id": record.get("cycle_id"),
            "path": str(
                paths.records_directory / f"{record.get('cycle_id')}.json"
            ),
            "record_hash": record.get("record_hash"),
        }
        for record in cycle_records
    ] if status == "COMPLETED" else []
    receipt_core = {
        "schema": CLOSURE_RECEIPT_SCHEMA,
        "version": VERSION,
        "status": status,
        "refresh_id": refresh_id,
        "request_hash": request_hash,
        "native_receipt_hash": native_receipt.get("receipt_hash"),
        "cycle_ids": [row["cycle_id"] for row in cycle_references],
        "cycle_records": cycle_references,
        "research_cycle_index": (
            {
                "path": str(paths.index_path),
                "content_hash": _as_dict(
                    _read_json(paths.index_path, {})
                ).get("content_hash"),
            }
            if status == "COMPLETED"
            else None
        ),
        "issues": issues,
        "started_at": started_at,
        "completed_at": _now_iso() if status == "COMPLETED" else None,
        "failed_at": _now_iso() if status == "FAILED" else None,
    }
    receipt = {
        **receipt_core,
        "receipt_hash": canonical_hash(receipt_core),
    }
    _atomic_json(receipt_path, receipt)
    return {
        "status": status,
        "cycle_ids": list(receipt.get("cycle_ids", [])),
        "receipt_path": str(receipt_path),
        "receipt_hash": receipt.get("receipt_hash"),
        "issues": issues,
    }


def verify_authoritative_cycle_closure_reference(
    reference: Mapping[str, Any],
) -> bool:
    """Verify a closure referenced by an automatic-refresh wrapper receipt."""
    if reference.get("status") == "NOT_APPLICABLE":
        return not reference.get("receipt_path") and not reference.get("cycle_ids")
    path_value = _text(reference.get("receipt_path"))
    if not path_value:
        return False
    path = Path(path_value)
    try:
        receipt = _verified_hashed_payload(path, hash_field="receipt_hash")
    except AuthoritativeCycleError:
        return False
    if receipt.get("status") != "COMPLETED":
        return False
    if receipt.get("receipt_hash") != reference.get("receipt_hash"):
        return False
    if list(receipt.get("cycle_ids", [])) != list(reference.get("cycle_ids", [])):
        return False
    return _verified_existing_closure(
        path, request_hash=str(reference.get("request_hash") or "")
    ) is not None


__all__ = [
    "AuthoritativeCycleError",
    "AuthoritativeCyclePaths",
    "CLOSURE_RECEIPT_SCHEMA",
    "INDEX_SCHEMA",
    "RECORD_SCHEMA",
    "VERSION",
    "close_authoritative_research_cycles",
    "verify_authoritative_cycle_closure_reference",
]
