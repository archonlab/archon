#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Analyzer_next.compatibility.legacy_analyzer.research_cycle_record import (
    atomic_write_json,
    canonical_hash,
    refresh_research_cycle_records,
)


VERSION = "1.0"
TITLE = "ARCHON Production Browser Publication"
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def file_sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_record(path: Path) -> Dict[str, Any]:
    record = as_dict(load_json(path, {}))
    declared = text(record.get("record_hash"))
    core = {
        key: value
        for key, value in record.items()
        if key != "record_hash"
    }
    if not declared or declared != canonical_hash(core):
        raise ValueError("AUTHORITATIVE_CYCLE_RECORD_INTEGRITY_FAILED")
    return record


def verified_receipt(path: Path) -> Dict[str, Any]:
    receipt = as_dict(load_json(path, {}))
    declared = text(receipt.get("receipt_hash"))
    core = {
        key: value
        for key, value in receipt.items()
        if key != "receipt_hash"
    }
    if not declared or declared != canonical_hash(core):
        raise ValueError(f"RECEIPT_INTEGRITY_FAILED:{path}")
    return receipt


def source_reference(path: Path) -> Optional[Dict[str, Any]]:
    digest = file_sha256(path)
    if not digest:
        return None
    return {
        "path": str(path.resolve()),
        "sha256": digest,
    }


def compact_director_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: payload.get(key)
        for key in (
            "stage",
            "maturity",
            "risk",
            "trend",
            "integrity",
            "recommendations",
            "primary_recommendation",
        )
        if payload.get(key) is not None
    }


def compact_experiment_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    experiments = as_list(payload.get("experiments"))
    return {
        "experiment_count": (
            payload.get("experiment_count")
            if payload.get("experiment_count") is not None
            else len(experiments)
        ),
        "experiments": [
            {
                key: item.get(key)
                for key in (
                    "experiment_id",
                    "title",
                    "status",
                    "run_count",
                    "arm_count",
                    "analysis_confidence",
                )
                if item.get(key) is not None
            }
            for item in experiments[:100]
            if isinstance(item, dict)
        ],
    }


def find_cycle_record(
    analysis_root: Path,
    cycle_id: Optional[str],
    observer_run_id: Optional[str],
) -> Dict[str, Any]:
    refreshed = refresh_research_cycle_records(analysis_root)
    matches = []
    for record in as_list(refreshed.get("records")):
        if not isinstance(record, dict):
            continue
        if cycle_id and text(record.get("cycle_id")) != cycle_id:
            continue
        if (
            observer_run_id
            and observer_run_id
            not in as_list(record.get("observer_run_ids"))
        ):
            continue
        matches.append(record)
    if len(matches) != 1:
        raise ValueError(
            "RESEARCH_CYCLE_NOT_UNIQUELY_RESOLVED:"
            f"{len(matches)}"
        )
    return matches[0]


def publish_browser_artifacts(
    analysis_root: Path | str,
    *,
    cycle_id: Optional[str] = None,
    observer_run_id: Optional[str] = None,
    publication_id: Optional[str] = None,
) -> Dict[str, Any]:
    analysis = Path(analysis_root).resolve()
    experiments = analysis / "Experiments"
    record = find_cycle_record(
        analysis,
        text(cycle_id),
        text(observer_run_id),
    )
    resolved_cycle_id = text(record.get("cycle_id"))
    if not resolved_cycle_id or not SAFE_ID.fullmatch(resolved_cycle_id):
        raise ValueError("UNSAFE_OR_MISSING_CYCLE_ID")

    publication_id = (
        text(publication_id)
        or f"BROWSER-PUB-{resolved_cycle_id}"
    )
    if not SAFE_ID.fullmatch(publication_id):
        raise ValueError("UNSAFE_PUBLICATION_ID")

    records_dir = experiments / "ResearchCycleRecords" / "records"
    record_path = records_dir / f"{resolved_cycle_id}.json"
    verified_cycle = verified_record(record_path)

    receipt_dir = experiments / "BrowserPublicationReceipts"
    receipt_path = receipt_dir / f"{publication_id}.json"
    artifact_dir = analysis / "Browser" / "Publications"
    artifact_path = artifact_dir / f"{resolved_cycle_id}.json"
    registry_path = experiments / "browser_publication_registry.json"
    result_path = experiments / "browser_publication_result.json"

    if receipt_path.exists():
        receipt = verified_receipt(receipt_path)
        if text(receipt.get("cycle_id")) != resolved_cycle_id:
            raise ValueError("PUBLICATION_RECEIPT_CYCLE_MISMATCH")
        declared_artifact_hash = text(receipt.get("artifact_hash"))
        artifact = as_dict(load_json(artifact_path, {}))
        artifact_core = {
            key: value
            for key, value in artifact.items()
            if key != "artifact_hash"
        }
        if (
            not declared_artifact_hash
            or artifact.get("artifact_hash") != declared_artifact_hash
            or canonical_hash(artifact_core) != declared_artifact_hash
        ):
            raise ValueError("PUBLISHED_BROWSER_ARTIFACT_INTEGRITY_FAILED")
        result = {
            "schema": "archon_browser_publication_result_v1",
            "version": VERSION,
            "status": "PUBLICATION_REUSED",
            "publication_id": publication_id,
            "cycle_id": resolved_cycle_id,
            "artifact_path": str(artifact_path),
            "artifact_hash": declared_artifact_hash,
            "receipt_path": str(receipt_path),
            "issues": [],
            "completed_at": now_iso(),
        }
        atomic_write_json(result_path, result)
        refresh_research_cycle_records(analysis)
        return result

    if verified_cycle.get("current_stage") != "FINALIZED_PENDING_BROWSER":
        raise ValueError(
            "CYCLE_NOT_READY_FOR_BROWSER_PUBLICATION:"
            f"{verified_cycle.get('current_stage')}"
        )
    if verified_cycle.get("receipt_integrity") != "OK":
        raise ValueError("CYCLE_RECEIPTS_NOT_VERIFIED")
    if as_list(verified_cycle.get("blockers")):
        raise ValueError("CYCLE_HAS_BLOCKERS")

    finalization_reference = as_dict(
        as_dict(verified_cycle.get("receipts")).get("finalization")
    )
    scientific_reference = as_dict(
        as_dict(verified_cycle.get("receipts")).get("scientific_refresh")
    )
    finalization_path = Path(
        str(finalization_reference.get("path") or "")
    )
    scientific_path = Path(
        str(scientific_reference.get("path") or "")
    )
    finalization_receipt = verified_receipt(finalization_path)
    scientific_receipt = verified_receipt(scientific_path)

    if text(finalization_receipt.get("observer_run_id")) not in as_list(
        verified_cycle.get("observer_run_ids")
    ):
        raise ValueError("FINALIZATION_OBSERVER_IDENTITY_MISMATCH")

    director_path = analysis / "research_director_report.json"
    actions_path = analysis / "next_research_actions.json"
    experiment_path = experiments / "experiment_analysis.json"
    director = as_dict(load_json(director_path, {}))
    experiment_analysis = as_dict(load_json(experiment_path, {}))

    sources = {
        "cycle_record": source_reference(record_path),
        "finalization_receipt": source_reference(finalization_path),
        "scientific_refresh_receipt": source_reference(scientific_path),
        "research_director": source_reference(director_path),
        "next_research_actions": source_reference(actions_path),
        "experiment_analysis": source_reference(experiment_path),
    }
    artifact_core = {
        "schema": "archon_browser_publication_artifact_v1",
        "version": VERSION,
        "status": "PUBLISHED",
        "publication_id": publication_id,
        "cycle_id": resolved_cycle_id,
        "proposal_id": verified_cycle.get("proposal_id"),
        "action_id": verified_cycle.get("action_id"),
        "plan_id": verified_cycle.get("plan_id"),
        "experiment_id": verified_cycle.get("experiment_id"),
        "runtime_id": verified_cycle.get("runtime_id"),
        "job_id": verified_cycle.get("job_id"),
        "task_id": verified_cycle.get("task_id"),
        "observer_run_ids": as_list(
            verified_cycle.get("observer_run_ids")
        ),
        "scientific_state": {
            "telemetry_status": verified_cycle.get("telemetry_status"),
            "profile_status": verified_cycle.get("profile_status"),
            "scientific_refresh_status": verified_cycle.get(
                "scientific_refresh_status"
            ),
            "director_refresh_status": verified_cycle.get(
                "director_refresh_status"
            ),
        },
        "director_summary": compact_director_summary(director),
        "experiment_summary": compact_experiment_summary(
            experiment_analysis
        ),
        "sources": sources,
        "prepublication_cycle_record_hash": verified_cycle.get(
            "record_hash"
        ),
        "published_at": now_iso(),
    }
    artifact = {
        **artifact_core,
        "artifact_hash": canonical_hash(artifact_core),
    }
    atomic_write_json(artifact_path, artifact)

    receipt_core = {
        "schema": "archon_browser_publication_receipt_v1",
        "version": VERSION,
        "status": "PUBLISHED",
        "publication_id": publication_id,
        "cycle_id": resolved_cycle_id,
        "observer_run_ids": as_list(
            verified_cycle.get("observer_run_ids")
        ),
        "artifact_path": str(artifact_path),
        "artifact_hash": artifact["artifact_hash"],
        "prepublication_cycle_record_hash": verified_cycle.get(
            "record_hash"
        ),
        "finalization_receipt_hash": finalization_receipt.get(
            "receipt_hash"
        ),
        "scientific_refresh_receipt_hash": scientific_receipt.get(
            "receipt_hash"
        ),
        "issued_at": now_iso(),
    }
    receipt = {
        **receipt_core,
        "receipt_hash": canonical_hash(receipt_core),
    }
    atomic_write_json(receipt_path, receipt)

    registry = as_dict(load_json(registry_path, {}))
    rows = [
        dict(item)
        for item in as_list(registry.get("publications"))
        if isinstance(item, dict)
        and text(item.get("publication_id")) != publication_id
    ]
    rows.append(
        {
            "publication_id": publication_id,
            "cycle_id": resolved_cycle_id,
            "status": "PUBLISHED",
            "artifact_path": str(artifact_path),
            "artifact_hash": artifact["artifact_hash"],
            "receipt_path": str(receipt_path),
            "receipt_hash": receipt["receipt_hash"],
            "recorded_at": now_iso(),
        }
    )
    rows.sort(key=lambda item: str(item.get("publication_id") or ""))
    registry_payload = {
        "schema": "archon_browser_publication_registry_v1",
        "version": VERSION,
        "updated_at": now_iso(),
        "publication_count": len(rows),
        "published_count": sum(
            item.get("status") == "PUBLISHED" for item in rows
        ),
        "publications": rows,
        "content_hash": canonical_hash(rows),
    }
    atomic_write_json(registry_path, registry_payload)

    result = {
        "schema": "archon_browser_publication_result_v1",
        "version": VERSION,
        "status": "PUBLISHED",
        "publication_id": publication_id,
        "cycle_id": resolved_cycle_id,
        "artifact_path": str(artifact_path),
        "artifact_hash": artifact["artifact_hash"],
        "receipt_path": str(receipt_path),
        "issues": [],
        "completed_at": now_iso(),
    }
    atomic_write_json(result_path, result)
    refresh_research_cycle_records(analysis)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--cycle-id", default=None)
    parser.add_argument("--observer-run-id", default=None)
    parser.add_argument("--publication-id", default=None)
    args = parser.parse_args()

    try:
        result = publish_browser_artifacts(
            args.analysis_root,
            cycle_id=text(args.cycle_id),
            observer_run_id=text(args.observer_run_id),
            publication_id=text(args.publication_id),
        )
    except Exception as exc:
        print("=" * 72)
        print(TITLE)
        print("=" * 72)
        print("Status:         PUBLICATION_REFUSED")
        print(f"Error:          {type(exc).__name__}: {exc}")
        print("=" * 72)
        return 1

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Status:         {result.get('status')}")
    print(f"Publication ID: {result.get('publication_id')}")
    print(f"Cycle ID:       {result.get('cycle_id')}")
    print(f"Artifact:       {result.get('artifact_path')}")
    print(f"Receipt:        {result.get('receipt_path')}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
