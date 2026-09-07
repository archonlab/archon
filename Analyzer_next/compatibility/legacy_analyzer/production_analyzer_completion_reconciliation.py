#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Analyzer_next.compatibility.legacy_analyzer.research_cycle_record import (
    refresh_research_cycle_records,
)


VERSION = "1.2"
TITLE = "ARCHON Stage 7.8 Analyzer Completion Reconciliation"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
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


def file_sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_production_analyzer_completion_reconciliation_policy_v1",
        "version": VERSION,
        "reconciliation_enabled": False,
        "require_bridge_completed_or_reused": True,
        "require_bridge_receipt_for_completed": True,
        "require_telemetry_manifest": True,
        "require_observer_profile": True,
        "require_experiment_analysis": True,
        "require_scientific_refresh_receipt": True,
        "require_director_products": True,
        "require_dag_state": True,
        "allow_missing_dag_state_for_reused": False,
        "require_no_failed_dag_steps": True,
        "allow_idempotent_reuse": True,
        "updated_at": now_iso(),
    }


def default_request() -> Dict[str, Any]:
    return {
        "schema": "archon_production_analyzer_completion_reconciliation_request_v1",
        "reconcile": False,
        "reconciliation_id": None,
        "bridge_result_path": None,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_reconciliation_id": None,
    }


def find_profile_record(
    payload: Dict[str, Any],
    observer_run_id: str,
) -> Optional[Dict[str, Any]]:
    for record in as_list(payload.get("profile_records")):
        if not isinstance(record, dict):
            continue
        if text(record.get("observer_state_run_id")) == observer_run_id:
            return record
        if text(record.get("experiment_id")) == observer_run_id:
            return record
    return None


def find_experiment_record(
    payload: Dict[str, Any],
    *,
    experiment_id: Optional[str],
    observer_run_id: str,
) -> Optional[Dict[str, Any]]:
    experiments = as_list(payload.get("experiments"))
    if experiment_id:
        for item in experiments:
            if (
                isinstance(item, dict)
                and text(item.get("experiment_id")) == experiment_id
            ):
                return item

    for item in experiments:
        if not isinstance(item, dict):
            continue
        for arm in as_dict(item.get("arms")).values():
            if not isinstance(arm, dict):
                continue
            run_ids = {
                text(value)
                for value in as_list(arm.get("run_ids"))
            }
            if observer_run_id in run_ids:
                return item
    return None


def extract_dag_steps(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Any] = []

    for key in ("steps", "nodes", "records", "dag", "state"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif isinstance(value, dict):
            for name, item in value.items():
                if isinstance(item, dict):
                    candidates.append({"step_key": name, **item})

    unique: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        key = (
            text(item.get("step_key"))
            or text(item.get("key"))
            or text(item.get("name"))
            or text(item.get("label"))
            or canonical_hash(item)
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def dag_step_status(item: Dict[str, Any]) -> Optional[str]:
    for key in (
        "status",
        "last_status",
        "execution_status",
        "result",
    ):
        value = text(item.get(key))
        if value:
            return value.lower()
    return None


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{result.get('version')}**",
        f"- Status: **{result.get('status')}**",
        f"- Reconciliation ID: `{result.get('reconciliation_id') or '-'}`",
        f"- Bridge ID: `{result.get('bridge_id') or '-'}`",
        f"- Observer run ID: `{result.get('observer_run_id') or '-'}`",
        f"- Experiment ID: `{result.get('experiment_id') or '-'}`",
        "",
        "## Meaning",
        "",
        "- Analyzer process completion is checked separately from scientific completeness.",
        "- The actual Observer run must appear in telemetry materialization and profiles.",
        "- The experiment must appear in experiment analysis.",
        "- A verified scientific refresh receipt must cover the actual Observer run.",
        "- Meta Science and Research Director products must exist with matching hashes.",
        "- Failed Analyzer DAG steps prevent completion.",
        "",
    ]
    if result.get("issues"):
        lines.extend(["## Issues", ""])
        for item in result["issues"]:
            lines.append(
                f"- `{item.get('code')}` at `{item.get('path')}`: "
                f"{item.get('message')}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--request", default=None)
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).resolve()
    experiments_root = analysis_root / "Experiments"
    experiments_root.mkdir(parents=True, exist_ok=True)

    policy_path = (
        experiments_root
        / "production_analyzer_completion_reconciliation_policy.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments_root
        / "production_analyzer_completion_reconciliation_request.json"
    )
    result_path = (
        experiments_root
        / "production_analyzer_completion_reconciliation_result.json"
    )
    registry_path = (
        experiments_root
        / "production_analyzer_completion_reconciliation_registry.json"
    )
    markdown_path = (
        experiments_root
        / "production_analyzer_completion_reconciliation.md"
    )
    receipt_dir = (
        experiments_root
        / "ProductionAnalyzerCompletionReconciliationReceipts"
    )

    policy = load_json(policy_path, {})
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    request = load_json(request_path, {})
    if not request:
        request = default_request()
        atomic_write_json(request_path, request)

    if request.get("reconcile") is not True:
        result = {
            "schema": (
                "archon_production_analyzer_completion_reconciliation_result_v1"
            ),
            "version": VERSION,
            "status": "NO_RECONCILIATION_REQUEST",
            "reconciliation_id": None,
            "issues": [],
        }
        atomic_write_json(result_path, result)
        markdown_path.write_text(
            render_markdown(result),
            encoding="utf-8",
        )
        print("=" * 72)
        print(TITLE)
        print("=" * 72)
        print(f"Version:            {VERSION}")
        print("Status:             NO_RECONCILIATION_REQUEST")
        print("Reconciliation ID:  -")
        print(f"Policy:             {policy_path}")
        print(f"Request:            {request_path}")
        print(f"Result:             {result_path}")
        print(f"Registry:           {registry_path}")
        print(f"Markdown:           {markdown_path}")
        print("=" * 72)
        return 0

    issues: List[Dict[str, Any]] = []

    def issue(
        code: str,
        message: str,
        path: str,
        actual: Any = None,
    ) -> None:
        issues.append({
            "code": code,
            "message": message,
            "path": path,
            "actual": actual,
        })

    reconciliation_id = text(request.get("reconciliation_id"))
    if not reconciliation_id:
        issue(
            "RECONCILIATION_ID_MISSING",
            "reconciliation_id is required.",
            "$.request.reconciliation_id",
        )

    if policy.get("reconciliation_enabled") is not True:
        issue(
            "RECONCILIATION_DISABLED",
            "Analyzer completion reconciliation is disabled by policy.",
            "$.policy.reconciliation_enabled",
            policy.get("reconciliation_enabled"),
        )

    for key in (
        "require_scientific_refresh_receipt",
        "require_director_products",
    ):
        if policy.get(key, True) is not True:
            issue(
                "SCIENTIFIC_REFRESH_POLICY_UNSAFE",
                (
                    "Analyzer completion cannot be reconciled while "
                    f"{key} is disabled."
                ),
                f"$.policy.{key}",
                policy.get(key),
            )

    if (
        request.get("confirmation")
        != "RECONCILE_COMPLETED_ANALYZER_RESULT"
    ):
        issue(
            "CONFIRMATION_INVALID",
            "Reconciliation confirmation is invalid.",
            "$.request.confirmation",
            request.get("confirmation"),
        )

    bridge_value = text(request.get("bridge_result_path"))
    bridge_path = (
        Path(bridge_value).expanduser().resolve()
        if bridge_value else None
    )
    bridge = load_json(bridge_path, {}) if bridge_path else {}

    if not bridge:
        issue(
            "BRIDGE_RESULT_MISSING",
            "Analyzer bridge result is missing or unreadable.",
            "$.request.bridge_result_path",
            bridge_value,
        )

    bridge_status = text(bridge.get("status"))
    if (
        policy.get("require_bridge_completed_or_reused") is True
        and bridge_status not in {"COMPLETED", "REUSED"}
    ):
        issue(
            "BRIDGE_NOT_COMPLETE",
            "Analyzer bridge is neither COMPLETED nor REUSED.",
            "$.bridge.status",
            bridge_status,
        )

    bridge_id = text(bridge.get("bridge_id"))
    observer_run_id = text(bridge.get("observer_run_id"))
    experiment_id = text(bridge.get("experiment_id"))
    intake_hash = text(bridge.get("intake_hash"))
    results_value = text(bridge.get("results_directory"))
    results_dir = (
        Path(results_value).expanduser().resolve()
        if results_value else None
    )

    if not observer_run_id:
        issue(
            "OBSERVER_RUN_ID_MISSING",
            "Bridge result does not identify the actual Observer run.",
            "$.bridge.observer_run_id",
        )

    if (
        policy.get("require_scientific_refresh_receipt", True) is True
        and bridge.get("scientific_refresh_completed") is not True
    ):
        issue(
            "SCIENTIFIC_REFRESH_NOT_COMPLETED",
            "Analyzer bridge did not complete scientific refresh.",
            "$.bridge.scientific_refresh_completed",
            bridge.get("scientific_refresh_completed"),
        )

    if results_dir is None or not results_dir.is_dir():
        issue(
            "RESULTS_DIRECTORY_MISSING",
            "Bridge results workspace is missing.",
            "$.bridge.results_directory",
            results_value,
        )

    registry = load_json(registry_path, {})
    previous = None
    for item in as_list(registry.get("reconciliations")):
        if not isinstance(item, dict):
            continue
        if (
            text(item.get("observer_run_id")) == observer_run_id
            and text(item.get("bridge_hash"))
            == text(bridge.get("bridge_hash"))
            and item.get("status") in {
                "ANALYSIS_COMPLETED",
                "ANALYSIS_REUSED",
            }
        ):
            previous = item
            break

    bridge_receipt_path: Optional[Path] = None
    if bridge_status == "COMPLETED":
        receipt_value = text(bridge.get("receipt_path"))
        if receipt_value:
            bridge_receipt_path = Path(
                receipt_value
            ).expanduser().resolve()
        elif bridge_id:
            bridge_receipt_path = (
                bridge_path.parent
                / "ProductionObserverAnalyzerBridgeReceipts"
                / f"{bridge_id}.json"
            )

        if (
            policy.get("require_bridge_receipt_for_completed") is True
            and (
                bridge_receipt_path is None
                or not bridge_receipt_path.is_file()
            )
        ):
            issue(
                "BRIDGE_RECEIPT_MISSING",
                "Completed bridge has no durable receipt.",
                "$.bridge.receipt",
                (
                    str(bridge_receipt_path)
                    if bridge_receipt_path else None
                ),
            )

    telemetry_manifest: Dict[str, Any] = {}
    profile_record: Optional[Dict[str, Any]] = None
    experiment_record: Optional[Dict[str, Any]] = None
    scientific_refresh_receipt: Dict[str, Any] = {}
    scientific_refresh_receipt_path: Optional[Path] = None
    scientific_refresh_products_verified = False
    dag_payload: Dict[str, Any] = {}
    dag_steps: List[Dict[str, Any]] = []
    failed_dag_steps: List[Dict[str, Any]] = []

    if results_dir is not None and results_dir.is_dir():
        refresh_receipt_value = text(
            bridge.get("scientific_refresh_receipt_path")
        )
        scientific_refresh_receipt_path = (
            Path(refresh_receipt_value).expanduser().resolve()
            if refresh_receipt_value else None
        )
        scientific_refresh_receipt = load_json(
            scientific_refresh_receipt_path,
            {},
        ) if scientific_refresh_receipt_path else {}

        if (
            policy.get("require_scientific_refresh_receipt", True) is True
            and not scientific_refresh_receipt
        ):
            issue(
                "SCIENTIFIC_REFRESH_RECEIPT_MISSING",
                "Scientific refresh receipt is missing or unreadable.",
                "$.analyzer.scientific_refresh_receipt",
                refresh_receipt_value,
            )

        if scientific_refresh_receipt:
            if scientific_refresh_receipt.get("status") != "COMPLETED":
                issue(
                    "SCIENTIFIC_REFRESH_RECEIPT_INCOMPLETE",
                    "Scientific refresh receipt is not COMPLETED.",
                    "$.analyzer.scientific_refresh_receipt.status",
                    scientific_refresh_receipt.get("status"),
                )

            expected_receipt_hash = canonical_hash({
                key: value
                for key, value in scientific_refresh_receipt.items()
                if key != "receipt_hash"
            })
            actual_receipt_hash = text(
                scientific_refresh_receipt.get("receipt_hash")
            )
            if actual_receipt_hash != expected_receipt_hash:
                issue(
                    "SCIENTIFIC_REFRESH_RECEIPT_HASH_INVALID",
                    "Scientific refresh receipt hash is invalid.",
                    "$.analyzer.scientific_refresh_receipt.receipt_hash",
                    actual_receipt_hash,
                )

            bridge_receipt_hash = text(
                bridge.get("scientific_refresh_receipt_hash")
            )
            if (
                bridge_receipt_hash
                and bridge_receipt_hash != actual_receipt_hash
            ):
                issue(
                    "SCIENTIFIC_REFRESH_BRIDGE_HASH_MISMATCH",
                    "Bridge and scientific refresh receipt hashes differ.",
                    "$.bridge.scientific_refresh_receipt_hash",
                    {
                        "bridge": bridge_receipt_hash,
                        "receipt": actual_receipt_hash,
                    },
                )

            receipt_run_ids = {
                text(value)
                for value in as_list(
                    scientific_refresh_receipt.get(
                        "observer_run_ids"
                    )
                )
            }
            if observer_run_id not in receipt_run_ids:
                issue(
                    "SCIENTIFIC_REFRESH_RUN_ID_MISSING",
                    "Scientific refresh receipt does not cover the actual run.",
                    "$.analyzer.scientific_refresh_receipt.observer_run_ids",
                    sorted(value for value in receipt_run_ids if value),
                )

            invalid_products = []
            required_product_names = {
                "meta_science_report.json",
                "research_director_report.json",
                "next_research_actions.json",
            }
            observed_product_names: set[str] = set()
            for product in as_list(
                scientific_refresh_receipt.get("director_products")
            ):
                if not isinstance(product, dict):
                    invalid_products.append(product)
                    continue
                product_name = text(product.get("name"))
                if product_name:
                    observed_product_names.add(product_name)
                product_path_value = text(product.get("path"))
                product_path = (
                    Path(product_path_value).expanduser().resolve()
                    if product_path_value else None
                )
                expected_hash = text(product.get("sha256"))
                actual_hash = (
                    file_sha256(product_path)
                    if product_path else None
                )
                expected_path = (
                    analysis_root / product_name
                    if product_name else None
                )
                if (
                    product_path is None
                    or expected_path is None
                    or product_path != expected_path
                    or actual_hash is None
                    or actual_hash != expected_hash
                ):
                    invalid_products.append({
                        "name": product.get("name"),
                        "path": product_path_value,
                        "expected_path": (
                            str(expected_path)
                            if expected_path else None
                        ),
                        "expected_sha256": expected_hash,
                        "actual_sha256": actual_hash,
                    })
            missing_product_names = sorted(
                required_product_names - observed_product_names
            )
            if missing_product_names:
                invalid_products.append({
                    "missing_required_products": missing_product_names,
                })

            scientific_refresh_products_verified = (
                scientific_refresh_receipt.get(
                    "director_products_verified"
                ) is True
                and not invalid_products
            )
            if (
                policy.get("require_director_products", True) is True
                and not scientific_refresh_products_verified
            ):
                issue(
                    "SCIENTIFIC_REFRESH_PRODUCTS_INVALID",
                    "Meta Science or Research Director products failed verification.",
                    "$.analyzer.scientific_refresh_receipt.director_products",
                    invalid_products,
                )

        telemetry_manifest_path = (
            results_dir
            / "observation_logs"
            / "telemetry_bridge_manifest.json"
        )
        telemetry_manifest = load_json(
            telemetry_manifest_path,
            {},
        )

        if (
            policy.get("require_telemetry_manifest") is True
            and not telemetry_manifest
        ):
            issue(
                "TELEMETRY_MANIFEST_MISSING",
                "Telemetry materialization manifest is missing.",
                "$.analyzer.telemetry_manifest",
                str(telemetry_manifest_path),
            )

        if telemetry_manifest and observer_run_id:
            manifest_run_ids = {
                text(item.get("run_id"))
                for item in as_list(telemetry_manifest.get("runs"))
                if isinstance(item, dict)
            }
            if observer_run_id not in manifest_run_ids:
                issue(
                    "TELEMETRY_RUN_NOT_MATERIALIZED",
                    "Actual Observer run is absent from telemetry manifest.",
                    "$.analyzer.telemetry_manifest.runs",
                    sorted(
                        value
                        for value in manifest_run_ids
                        if value
                    ),
                )

        profiles_path = results_dir / "observer_profiles_v31.json"
        profiles = load_json(profiles_path, {})
        profile_record = (
            find_profile_record(profiles, observer_run_id)
            if observer_run_id else None
        )
        if (
            policy.get("require_observer_profile") is True
            and profile_record is None
        ):
            issue(
                "OBSERVER_PROFILE_MISSING",
                "Actual Observer run has no normalized Analyzer profile.",
                "$.analyzer.observer_profiles_v31",
                str(profiles_path),
            )

        experiment_analysis_path = (
            analysis_root
            / "Experiments"
            / "experiment_analysis.json"
        )
        experiment_analysis = load_json(
            experiment_analysis_path,
            {},
        )
        experiment_record = (
            find_experiment_record(
                experiment_analysis,
                experiment_id=experiment_id,
                observer_run_id=observer_run_id,
            )
            if observer_run_id else None
        )
        if (
            policy.get("require_experiment_analysis") is True
            and experiment_record is None
        ):
            issue(
                "EXPERIMENT_ANALYSIS_MISSING",
                "Actual Observer run has no experiment analysis record.",
                "$.analyzer.experiment_analysis",
                {
                    "path": str(experiment_analysis_path),
                    "experiment_id": experiment_id,
                    "observer_run_id": observer_run_id,
                },
            )

        dag_candidates = [
            analysis_root
            / "Integrity"
            / "analyzer_dag_state.json",
            analysis_root
            / "Integrity"
            / "analyzer_dag.json",
            analysis_root
            / "Integrity"
            / "incremental_dag_state.json",
        ]
        dag_path = next(
            (
                path
                for path in dag_candidates
                if path.is_file()
            ),
            None,
        )
        if dag_path is not None:
            dag_payload = load_json(dag_path, {})
            dag_steps = extract_dag_steps(dag_payload)

        dag_required = policy.get("require_dag_state") is True
        if (
            bridge_status == "REUSED"
            and policy.get(
                "allow_missing_dag_state_for_reused"
            ) is True
        ):
            dag_required = False

        if dag_required and not dag_payload:
            issue(
                "ANALYZER_DAG_STATE_MISSING",
                "Analyzer DAG state is missing.",
                "$.analyzer.dag_state",
                [str(path) for path in dag_candidates],
            )

        for step in dag_steps:
            status = dag_step_status(step)
            if status in {
                "failed",
                "error",
                "invalid",
                "rejected",
            }:
                failed_dag_steps.append(step)

        if (
            policy.get("require_no_failed_dag_steps") is True
            and failed_dag_steps
        ):
            issue(
                "ANALYZER_DAG_FAILED_STEPS",
                "Analyzer DAG contains failed steps.",
                "$.analyzer.dag_state",
                [
                    {
                        "step": (
                            item.get("step_key")
                            or item.get("key")
                            or item.get("name")
                            or item.get("label")
                        ),
                        "status": dag_step_status(item),
                    }
                    for item in failed_dag_steps
                ],
            )

    if issues:
        if bridge_status not in {"COMPLETED", "REUSED"}:
            status = "ANALYSIS_FAILED"
        else:
            status = "ANALYSIS_INCOMPLETE"
    else:
        status = (
            "ANALYSIS_REUSED"
            if (
                bridge_status == "REUSED"
                or (
                    previous is not None
                    and policy.get("allow_idempotent_reuse") is True
                )
            )
            else "ANALYSIS_COMPLETED"
        )

    evidence = {
        "bridge_result": (
            {
                "path": str(bridge_path),
                "sha256": file_sha256(bridge_path),
            }
            if bridge_path and bridge_path.is_file()
            else None
        ),
        "bridge_receipt": (
            {
                "path": str(bridge_receipt_path),
                "sha256": file_sha256(bridge_receipt_path),
            }
            if bridge_receipt_path
            and bridge_receipt_path.is_file()
            else None
        ),
        "telemetry_manifest": telemetry_manifest,
        "profile_record": profile_record,
        "experiment_analysis": experiment_record,
        "scientific_refresh_receipt": (
            {
                "path": str(scientific_refresh_receipt_path),
                "sha256": file_sha256(
                    scientific_refresh_receipt_path
                ),
                "receipt_hash": scientific_refresh_receipt.get(
                    "receipt_hash"
                ),
            }
            if scientific_refresh_receipt_path
            and scientific_refresh_receipt_path.is_file()
            else None
        ),
        "scientific_refresh_products_verified": (
            scientific_refresh_products_verified
        ),
        "dag_step_count": len(dag_steps),
        "failed_dag_step_count": len(failed_dag_steps),
    }

    result_core = {
        "schema": (
            "archon_production_analyzer_completion_reconciliation_result_v1"
        ),
        "version": VERSION,
        "status": status,
        "reconciliation_id": reconciliation_id,
        "bridge_id": bridge_id,
        "bridge_status": bridge_status,
        "bridge_hash": bridge.get("bridge_hash"),
        "intake_hash": intake_hash,
        "observer_run_id": observer_run_id,
        "experiment_id": experiment_id,
        "reused_reconciliation_id": (
            previous.get("reconciliation_id")
            if previous is not None
            and status == "ANALYSIS_REUSED"
            else None
        ),
        "job_id": bridge.get("job_id"),
        "task_id": bridge.get("task_id"),
        "runtime_id": bridge.get("runtime_id"),
        "requested_run_id": bridge.get("requested_run_id"),
        "results_directory": (
            str(results_dir) if results_dir else None
        ),
        "profile_record_found": profile_record is not None,
        "experiment_analysis_found": experiment_record is not None,
        "scientific_refresh_receipt_found": bool(
            scientific_refresh_receipt
        ),
        "scientific_refresh_products_verified": (
            scientific_refresh_products_verified
        ),
        "telemetry_materialized": bool(telemetry_manifest),
        "dag_state_found": bool(dag_payload),
        "dag_step_count": len(dag_steps),
        "failed_dag_step_count": len(failed_dag_steps),
        "evidence": evidence,
        "issues": issues,
        "scientific_analysis_complete": (
            status
            in {"ANALYSIS_COMPLETED", "ANALYSIS_REUSED"}
        ),
        "completed_at": (
            now_iso()
            if status
            in {"ANALYSIS_COMPLETED", "ANALYSIS_REUSED"}
            else None
        ),
        "failed_at": (
            now_iso()
            if status
            in {"ANALYSIS_FAILED", "ANALYSIS_INCOMPLETE"}
            else None
        ),
    }
    result = {
        **result_core,
        "reconciliation_hash": canonical_hash(result_core),
    }
    atomic_write_json(result_path, result)

    receipt_path: Optional[Path] = None
    if status in {"ANALYSIS_COMPLETED", "ANALYSIS_REUSED"}:
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / f"{reconciliation_id}.json"
        receipt = {
            "schema": (
                "archon_production_analyzer_completion_reconciliation_receipt_v1"
            ),
            "version": VERSION,
            "status": status,
            "reconciliation_id": reconciliation_id,
            "bridge_id": bridge_id,
            "observer_run_id": observer_run_id,
            "experiment_id": experiment_id,
            "scientific_analysis_complete": True,
            "scientific_refresh_receipt_hash": (
                scientific_refresh_receipt.get("receipt_hash")
            ),
            "scientific_refresh_products_verified": (
                scientific_refresh_products_verified
            ),
            "reconciliation_hash": result["reconciliation_hash"],
            "result_path": str(result_path),
            "issued_at": now_iso(),
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        atomic_write_json(receipt_path, receipt)

    rows = [
        item
        for item in as_list(registry.get("reconciliations"))
        if isinstance(item, dict)
    ]
    rows.append({
        "reconciliation_id": reconciliation_id,
        "status": status,
        "bridge_id": bridge_id,
        "bridge_hash": bridge.get("bridge_hash"),
        "observer_run_id": observer_run_id,
        "experiment_id": experiment_id,
        "job_id": bridge.get("job_id"),
        "task_id": bridge.get("task_id"),
        "scientific_analysis_complete": (
            status
            in {"ANALYSIS_COMPLETED", "ANALYSIS_REUSED"}
        ),
        "receipt_path": str(receipt_path) if receipt_path else None,
        "result_path": str(result_path),
        "recorded_at": now_iso(),
    })
    unique = {
        str(item.get("reconciliation_id")): item
        for item in rows
        if item.get("reconciliation_id")
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: str(item.get("reconciliation_id")),
    )
    registry_payload = {
        "schema": (
            "archon_production_analyzer_completion_reconciliation_registry_v1"
        ),
        "version": VERSION,
        "updated_at": now_iso(),
        "reconciliation_count": len(ordered),
        "completed_count": sum(
            item.get("status") == "ANALYSIS_COMPLETED"
            for item in ordered
        ),
        "reused_count": sum(
            item.get("status") == "ANALYSIS_REUSED"
            for item in ordered
        ),
        "incomplete_count": sum(
            item.get("status") == "ANALYSIS_INCOMPLETE"
            for item in ordered
        ),
        "failed_count": sum(
            item.get("status") == "ANALYSIS_FAILED"
            for item in ordered
        ),
        "reconciliations": ordered,
    }
    registry_payload["content_hash"] = canonical_hash(ordered)
    atomic_write_json(registry_path, registry_payload)

    atomic_write_json(
        request_path,
        {
            **default_request(),
            "last_consumed_reconciliation_id": reconciliation_id,
        },
    )
    markdown_path.write_text(
        render_markdown(result),
        encoding="utf-8",
    )
    refresh_research_cycle_records(analysis_root)

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Version:                    {VERSION}")
    print(f"Status:                     {status}")
    print(f"Reconciliation ID:          {reconciliation_id or '-'}")
    print(f"Bridge ID:                  {bridge_id or '-'}")
    print(f"Observer run ID:            {observer_run_id or '-'}")
    print(f"Experiment ID:              {experiment_id or '-'}")
    print(f"Telemetry materialized:     {bool(telemetry_manifest)}")
    print(f"Profile found:              {profile_record is not None}")
    print(f"Experiment analysis found:  {experiment_record is not None}")
    print(f"DAG state found:            {bool(dag_payload)}")
    print(f"Failed DAG steps:           {len(failed_dag_steps)}")
    print(f"Issues:                     {len(issues)}")
    print(f"Result:                     {result_path}")
    print(
        f"Receipt:                    "
        f"{str(receipt_path) if receipt_path else '-'}"
    )
    print(f"Registry:                   {registry_path}")
    print(f"Markdown:                   {markdown_path}")
    print("=" * 72)

    return (
        0
        if status in {"ANALYSIS_COMPLETED", "ANALYSIS_REUSED"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
