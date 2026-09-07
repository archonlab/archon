#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


VERSION = "1.0"
TITLE = "ARCHON Authoritative Research Cycle Record"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


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


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def load_rows(path: Path, key: str) -> List[Dict[str, Any]]:
    return [
        item
        for item in as_list(as_dict(load_json(path, {})).get(key))
        if isinstance(item, dict)
    ]


def load_receipts(directory: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not directory.is_dir():
        return rows
    for path in sorted(directory.glob("*.json")):
        payload = as_dict(load_json(path, {}))
        if payload:
            rows.append({"path": str(path.resolve()), "payload": payload})
    return rows


def latest_match(
    rows: Iterable[Dict[str, Any]],
    key: str,
    value: Optional[str],
    time_keys: Iterable[str] = ("recorded_at", "issued_at", "completed_at"),
) -> Dict[str, Any]:
    if not value:
        return {}
    matches = [row for row in rows if text(row.get(key)) == value]
    if not matches:
        return {}

    def sort_key(row: Dict[str, Any]) -> str:
        for time_key in time_keys:
            if row.get(time_key):
                return str(row.get(time_key))
        return ""

    return sorted(matches, key=sort_key)[-1]


def load_result(row: Dict[str, Any], fallback: Path) -> Dict[str, Any]:
    result_path = text(row.get("result_path"))
    if result_path:
        payload = as_dict(load_json(Path(result_path), {}))
        if payload:
            return payload
    payload = as_dict(load_json(fallback, {}))
    return payload


def receipt_reference(
    path: Optional[str],
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not payload:
        return None
    declared = text(payload.get("receipt_hash"))
    body = {
        key: value
        for key, value in payload.items()
        if key != "receipt_hash"
    }
    actual = canonical_hash(body) if declared else None
    return {
        "path": path,
        "schema": payload.get("schema"),
        "status": payload.get("status"),
        "receipt_hash": declared,
        "hash_verified": bool(declared and declared == actual),
    }


def receipt_by_id(
    receipts: List[Dict[str, Any]],
    key: str,
    value: Optional[str],
) -> Dict[str, Any]:
    if not value:
        return {}
    for item in receipts:
        payload = as_dict(item.get("payload"))
        if text(payload.get(key)) == value:
            return item
    return {}


def plan_identity(
    experiments: Path,
    plan_id: Optional[str],
) -> Dict[str, Optional[str]]:
    if not plan_id:
        return {"proposal_id": None, "action_id": None}
    manifest = as_dict(
        load_json(experiments / "PlanManifests" / f"{plan_id}.json", {})
    )
    plan = as_dict(manifest.get("plan"))
    provenance = as_dict(plan.get("provenance"))
    return {
        "proposal_id": text(
            provenance.get("source_proposal_id")
            or plan.get("proposal_id")
        ),
        "action_id": text(
            provenance.get("source_action_id")
            or plan.get("action_id")
        ),
    }


def choose_state(
    cycle: Dict[str, Any],
    bridge: Dict[str, Any],
    reconciliation: Dict[str, Any],
    finalization: Dict[str, Any],
    publication: Dict[str, Any],
) -> Dict[str, str]:
    cycle_status = str(cycle.get("status") or "UNKNOWN")
    bridge_status = str(bridge.get("status") or "NOT_STARTED")
    reconciliation_status = str(
        reconciliation.get("status") or "NOT_STARTED"
    )
    finalization_status = str(
        finalization.get("status") or "NOT_STARTED"
    )
    publication_status = str(
        publication.get("status") or "NOT_STARTED"
    )

    if finalization_status in {"FINALIZED", "FINALIZATION_REUSED"}:
        if publication_status in {"PUBLISHED", "PUBLICATION_REUSED"}:
            return {
                "current_stage": "COMPLETED",
                "next_required_action": "NONE",
            }
        if publication_status == "PUBLICATION_REFUSED":
            return {
                "current_stage": "BROWSER_PUBLICATION_BLOCKED",
                "next_required_action": "RESOLVE_BROWSER_PUBLICATION",
            }
        return {
            "current_stage": "FINALIZED_PENDING_BROWSER",
            "next_required_action": "PUBLISH_BROWSER_ARTIFACTS",
        }
    if finalization_status == "FINALIZATION_REFUSED":
        return {
            "current_stage": "FINALIZATION_BLOCKED",
            "next_required_action": "RESOLVE_FINALIZATION_ISSUES",
        }
    if reconciliation_status in {
        "ANALYSIS_COMPLETED",
        "ANALYSIS_REUSED",
    }:
        return {
            "current_stage": "ANALYSIS_RECONCILED",
            "next_required_action": "FINALIZE_STAGE6_JOB",
        }
    if reconciliation_status in {
        "ANALYSIS_FAILED",
        "ANALYSIS_INCOMPLETE",
    }:
        return {
            "current_stage": "ANALYSIS_RECONCILIATION_BLOCKED",
            "next_required_action": "RESOLVE_ANALYZER_RECONCILIATION",
        }
    if bridge_status == "COMPLETED":
        return {
            "current_stage": "SCIENTIFIC_REFRESH_COMPLETED",
            "next_required_action": "RECONCILE_ANALYZER_COMPLETION",
        }
    if bridge_status == "FAILED":
        return {
            "current_stage": "ANALYZER_BRIDGE_FAILED",
            "next_required_action": "RETRY_ANALYZER_BRIDGE",
        }
    if cycle_status == "COMPLETED":
        return {
            "current_stage": "OBSERVER_COMPLETED",
            "next_required_action": "RUN_ANALYZER_BRIDGE",
        }
    if cycle_status == "FAILED":
        return {
            "current_stage": "OBSERVER_CYCLE_FAILED",
            "next_required_action": "RESOLVE_OBSERVER_CYCLE_FAILURE",
        }
    return {
        "current_stage": "CYCLE_REGISTERED",
        "next_required_action": "RUN_OBSERVER_CYCLE",
    }


def refresh_research_cycle_records(
    analysis_root: Path | str,
) -> Dict[str, Any]:
    analysis = Path(analysis_root).resolve()
    experiments = analysis / "Experiments"
    records_root = experiments / "ResearchCycleRecords"
    records_dir = records_root / "records"
    index_path = records_root / "research_cycle_index.json"

    cycle_registry = load_rows(
        experiments / "production_execution_cycle_registry.json",
        "cycles",
    )
    latest_cycle_result = as_dict(
        load_json(
            experiments / "production_execution_cycle_result.json",
            {},
        )
    )
    if latest_cycle_result.get("cycle_id"):
        cycle_registry.append(latest_cycle_result)

    cycle_receipts = load_receipts(
        experiments / "ProductionExecutionCycleReceipts"
    )
    for item in cycle_receipts:
        payload = as_dict(item.get("payload"))
        if payload.get("cycle_id"):
            cycle_registry.append(
                {
                    **payload,
                    "receipt_path": item.get("path"),
                }
            )

    unique_cycles: Dict[str, Dict[str, Any]] = {}
    for row in cycle_registry:
        cycle_id = text(row.get("cycle_id"))
        if not cycle_id:
            continue
        prior = unique_cycles.get(cycle_id, {})
        unique_cycles[cycle_id] = {**prior, **row}

    bridge_rows = load_rows(
        experiments / "production_observer_analyzer_bridge_registry.json",
        "bridges",
    )
    reconciliation_rows = load_rows(
        experiments
        / "production_analyzer_completion_reconciliation_registry.json",
        "reconciliations",
    )
    finalization_rows = load_rows(
        experiments / "production_stage6_job_finalization_registry.json",
        "finalizations",
    )
    bridge_receipts = load_receipts(
        experiments / "ProductionObserverAnalyzerBridgeReceipts"
    )
    reconciliation_receipts = load_receipts(
        experiments
        / "ProductionAnalyzerCompletionReconciliationReceipts"
    )
    finalization_receipts = load_receipts(
        experiments / "ProductionStage6JobFinalizationReceipts"
    )
    publication_rows = load_rows(
        experiments / "browser_publication_registry.json",
        "publications",
    )
    publication_receipts = load_receipts(
        experiments / "BrowserPublicationReceipts"
    )

    contract = as_dict(
        load_json(experiments / "observer_execution_contract.json", {})
    )
    manifest = as_dict(
        load_json(
            experiments / "production_observer_execution_manifest.json",
            {},
        )
    )

    records: List[Dict[str, Any]] = []
    for cycle_id, cycle in sorted(unique_cycles.items()):
        observer_run_id = text(cycle.get("observer_run_id"))
        cycle_receipt_item = receipt_by_id(
            cycle_receipts, "cycle_id", cycle_id
        )
        cycle_receipt = as_dict(cycle_receipt_item.get("payload"))

        matching_contract = (
            contract
            if (
                text(contract.get("contract_hash"))
                and text(contract.get("contract_hash"))
                == text(cycle.get("contract_hash"))
            )
            else {}
        )
        matching_manifest = (
            manifest
            if (
                text(manifest.get("contract_hash"))
                and text(manifest.get("contract_hash"))
                == text(cycle.get("contract_hash"))
            )
            else {}
        )
        identity = as_dict(
            matching_contract.get("identity")
            or matching_manifest.get("identity")
        )
        plan_id = text(identity.get("plan_id"))
        upstream = plan_identity(experiments, plan_id)

        bridge_row = latest_match(
            bridge_rows, "observer_run_id", observer_run_id
        )
        bridge_result = (
            load_result(
                bridge_row,
                experiments
                / "production_observer_analyzer_bridge_result.json",
            )
            if bridge_row else {}
        )
        bridge_id = text(
            bridge_result.get("bridge_id")
            or bridge_row.get("bridge_id")
        )
        bridge_receipt_item = receipt_by_id(
            bridge_receipts, "bridge_id", bridge_id
        )
        bridge_receipt = as_dict(bridge_receipt_item.get("payload"))

        reconciliation_row = latest_match(
            reconciliation_rows,
            "observer_run_id",
            observer_run_id,
        )
        reconciliation_result = (
            load_result(
                reconciliation_row,
                experiments
                / "production_analyzer_completion_reconciliation_result.json",
            )
            if reconciliation_row else {}
        )
        reconciliation_id = text(
            reconciliation_result.get("reconciliation_id")
            or reconciliation_row.get("reconciliation_id")
        )
        reconciliation_receipt_item = receipt_by_id(
            reconciliation_receipts,
            "reconciliation_id",
            reconciliation_id,
        )
        reconciliation_receipt = as_dict(
            reconciliation_receipt_item.get("payload")
        )

        finalization_row = latest_match(
            finalization_rows,
            "observer_run_id",
            observer_run_id,
        )
        finalization_result = (
            load_result(
                finalization_row,
                experiments
                / "production_stage6_job_finalization_result.json",
            )
            if finalization_row else {}
        )
        finalization_id = text(
            finalization_result.get("finalization_id")
            or finalization_row.get("finalization_id")
        )
        finalization_receipt_item = receipt_by_id(
            finalization_receipts,
            "finalization_id",
            finalization_id,
        )
        finalization_receipt = as_dict(
            finalization_receipt_item.get("payload")
        )

        publication_row = latest_match(
            publication_rows,
            "cycle_id",
            cycle_id,
        )
        publication_id = text(
            publication_row.get("publication_id")
        )
        publication_receipt_item = receipt_by_id(
            publication_receipts,
            "publication_id",
            publication_id,
        )
        publication_receipt = as_dict(
            publication_receipt_item.get("payload")
        )
        publication_state = publication_receipt or publication_row

        scientific_path = text(
            bridge_result.get("scientific_refresh_receipt_path")
        )
        scientific_receipt = (
            as_dict(load_json(Path(scientific_path), {}))
            if scientific_path else {}
        )

        state = choose_state(
            cycle,
            bridge_result or bridge_row,
            reconciliation_result or reconciliation_row,
            finalization_result or finalization_row,
            publication_state,
        )
        references = {
            "production_cycle": receipt_reference(
                text(cycle_receipt_item.get("path")),
                cycle_receipt,
            ),
            "analyzer_bridge": receipt_reference(
                text(bridge_receipt_item.get("path")),
                bridge_receipt,
            ),
            "scientific_refresh": receipt_reference(
                scientific_path,
                scientific_receipt,
            ),
            "analysis_reconciliation": receipt_reference(
                text(reconciliation_receipt_item.get("path")),
                reconciliation_receipt,
            ),
            "finalization": receipt_reference(
                text(finalization_receipt_item.get("path")),
                finalization_receipt,
            ),
            "browser_publication": receipt_reference(
                text(publication_receipt_item.get("path")),
                publication_receipt,
            ),
        }
        integrity_failures = [
            name
            for name, reference in references.items()
            if reference and reference.get("hash_verified") is not True
        ]
        blockers: List[str] = []
        required_receipts = {
            "production_cycle": cycle.get("status") == "COMPLETED",
            "analyzer_bridge": (
                (bridge_result or bridge_row).get("status")
                == "COMPLETED"
            ),
            "scientific_refresh": (
                bridge_result.get("scientific_refresh_completed") is True
            ),
            "analysis_reconciliation": (
                (reconciliation_result or reconciliation_row).get("status")
                in {"ANALYSIS_COMPLETED", "ANALYSIS_REUSED"}
            ),
            "finalization": (
                (finalization_result or finalization_row).get("status")
                in {"FINALIZED", "FINALIZATION_REUSED"}
            ),
            "browser_publication": (
                publication_state.get("status")
                in {"PUBLISHED", "PUBLICATION_REUSED"}
            ),
        }
        missing_receipts = [
            name
            for name, required in required_receipts.items()
            if required and not references.get(name)
        ]
        if integrity_failures:
            blockers.extend(
                f"RECEIPT_INTEGRITY_FAILED:{name}"
                for name in integrity_failures
            )
        blockers.extend(
            f"REQUIRED_RECEIPT_MISSING:{name}"
            for name in missing_receipts
        )
        if cycle.get("status") == "FAILED":
            blockers.append(
                "OBSERVER_CYCLE_FAILED:"
                f"{text(cycle.get('failed_stage')) or 'unknown'}"
            )
        for result in (
            bridge_result,
            reconciliation_result,
            finalization_result,
        ):
            for issue in as_list(result.get("issues")):
                if isinstance(issue, dict) and issue.get("code"):
                    blockers.append(str(issue.get("code")))

        browser_artifact_path = text(
            publication_receipt.get("artifact_path")
            or publication_row.get("artifact_path")
        )
        browser_artifact_hash = text(
            publication_receipt.get("artifact_hash")
            or publication_row.get("artifact_hash")
        )
        if publication_state.get("status") in {
            "PUBLISHED",
            "PUBLICATION_REUSED",
        }:
            browser_artifact = (
                as_dict(load_json(Path(browser_artifact_path), {}))
                if browser_artifact_path else {}
            )
            artifact_core = {
                key: value
                for key, value in browser_artifact.items()
                if key != "artifact_hash"
            }
            if (
                not browser_artifact
                or not browser_artifact_hash
                or browser_artifact.get("artifact_hash")
                != browser_artifact_hash
                or canonical_hash(artifact_core)
                != browser_artifact_hash
                or text(browser_artifact.get("cycle_id")) != cycle_id
            ):
                blockers.append(
                    "BROWSER_PUBLICATION_ARTIFACT_INTEGRITY_FAILED"
                )
        blockers = sorted(set(blockers))
        if (
            integrity_failures
            or missing_receipts
            or "BROWSER_PUBLICATION_ARTIFACT_INTEGRITY_FAILED"
            in blockers
        ):
            state["current_stage"] = "CYCLE_INTEGRITY_BLOCKED"
            state["next_required_action"] = "RESOLVE_CYCLE_BLOCKERS"

        scientific_complete = (
            bridge_result.get("scientific_refresh_completed") is True
            or scientific_receipt.get("status") == "COMPLETED"
        )
        record_core = {
            "schema": "archon_research_cycle_record_v1",
            "version": VERSION,
            "cycle_id": cycle_id,
            "proposal_id": upstream.get("proposal_id"),
            "action_id": (
                upstream.get("action_id")
                or text(
                    as_dict(
                        matching_contract.get("provenance")
                    ).get("source_action_id")
                )
            ),
            "plan_id": plan_id,
            "experiment_id": text(
                identity.get("experiment_id")
                or bridge_result.get("experiment_id")
            ),
            "runtime_id": text(
                identity.get("runtime_id")
                or bridge_result.get("runtime_id")
            ),
            "job_id": text(
                identity.get("job_id")
                or bridge_result.get("job_id")
            ),
            "task_id": text(
                identity.get("task_id")
                or bridge_result.get("task_id")
            ),
            "observer_run_ids": (
                [observer_run_id] if observer_run_id else []
            ),
            "telemetry_status": (
                "COMPLETED"
                if cycle.get("status") == "COMPLETED"
                else str(cycle.get("status") or "UNKNOWN")
            ),
            "profile_status": (
                "COMPLETED"
                if bridge_result.get("profile_record_found") is True
                else "NOT_STARTED"
            ),
            "scientific_refresh_status": (
                "COMPLETED" if scientific_complete else "NOT_STARTED"
            ),
            "director_refresh_status": (
                "COMPLETED"
                if (
                    scientific_complete
                    and scientific_receipt.get(
                        "director_products_verified"
                    ) is True
                )
                else "NOT_STARTED"
            ),
            "browser_publish_status": (
                "PUBLISHED"
                if publication_state.get("status")
                in {"PUBLISHED", "PUBLICATION_REUSED"}
                else "NOT_PUBLISHED"
            ),
            "browser_publication_id": publication_id,
            "browser_artifact_path": browser_artifact_path,
            "browser_artifact_hash": browser_artifact_hash,
            **state,
            "blockers": blockers,
            "receipt_integrity": (
                "FAILED"
                if (
                    integrity_failures
                    or missing_receipts
                    or (
                        "BROWSER_PUBLICATION_ARTIFACT_INTEGRITY_FAILED"
                        in blockers
                    )
                )
                else (
                    "OK"
                    if any(references.values())
                    else "NOT_VERIFIED"
                )
            ),
            "receipts": references,
            "transition_ids": {
                "bridge_id": bridge_id,
                "reconciliation_id": reconciliation_id,
                "finalization_id": finalization_id,
                "publication_id": publication_id,
            },
            "updated_at": now_iso(),
        }
        record = {
            **record_core,
            "record_hash": canonical_hash(record_core),
        }
        atomic_write_json(records_dir / f"{cycle_id}.json", record)
        records.append(record)

    index_rows = [
        {
            "cycle_id": record.get("cycle_id"),
            "proposal_id": record.get("proposal_id"),
            "experiment_id": record.get("experiment_id"),
            "runtime_id": record.get("runtime_id"),
            "observer_run_ids": record.get("observer_run_ids"),
            "current_stage": record.get("current_stage"),
            "next_required_action": record.get("next_required_action"),
            "blocker_count": len(as_list(record.get("blockers"))),
            "record_hash": record.get("record_hash"),
            "record_path": str(
                (records_dir / f"{record.get('cycle_id')}.json").resolve()
            ),
        }
        for record in records
    ]
    index_core = {
        "schema": "archon_research_cycle_index_v1",
        "version": VERSION,
        "generated_at": now_iso(),
        "cycle_count": len(index_rows),
        "blocked_count": sum(
            1 for row in index_rows if row.get("blocker_count")
        ),
        "records": index_rows,
    }
    index = {
        **index_core,
        "content_hash": canonical_hash(index_rows),
    }
    atomic_write_json(index_path, index)
    return {
        "index_path": str(index_path),
        "cycle_count": len(records),
        "blocked_count": index["blocked_count"],
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument(
        "command",
        choices=("rebuild", "show"),
        nargs="?",
        default="rebuild",
    )
    parser.add_argument("--cycle-id", default=None)
    parser.add_argument("--observer-run-id", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = refresh_research_cycle_records(args.analysis_root)
    selected = as_list(result.get("records"))
    if args.cycle_id:
        selected = [
            record
            for record in selected
            if text(record.get("cycle_id")) == text(args.cycle_id)
        ]
    if args.observer_run_id:
        selected = [
            record
            for record in selected
            if args.observer_run_id
            in as_list(record.get("observer_run_ids"))
        ]
    if (args.cycle_id or args.observer_run_id) and not selected:
        print("Research cycle not found.")
        return 1

    if args.json:
        print(
            json.dumps(
                selected if (args.cycle_id or args.observer_run_id) else result,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Cycles:  {result.get('cycle_count')}")
    print(f"Blocked: {result.get('blocked_count')}")
    print(f"Index:   {result.get('index_path')}")
    for record in selected:
        print("-" * 72)
        print(f"Cycle:       {record.get('cycle_id')}")
        print(f"Observer:    {', '.join(record.get('observer_run_ids', [])) or '-'}")
        print(f"Stage:       {record.get('current_stage')}")
        print(f"Next action: {record.get('next_required_action')}")
        print(f"Integrity:   {record.get('receipt_integrity')}")
        print(
            f"Blockers:    "
            f"{', '.join(record.get('blockers', [])) or '-'}"
        )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
