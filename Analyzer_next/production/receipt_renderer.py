"""Native scientific-refresh receipt rendering and attestation."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from Analyzer_next.production.contracts import STAGE_ORDER, Step
from Analyzer_next.production.process_execution import (
    ExecutionPaths,
    module_path,
    module_route,
)


SCIENTIFIC_REFRESH_REQUIRED_PRODUCTS = (
    "meta_science_report.json",
    "research_director_report.json",
    "next_research_actions.json",
)
RECEIPT_SCHEMA = "archon_scientific_refresh_receipt_v1"
RECEIPT_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(payload: Any) -> str:
    """Return the receipt contract's canonical SHA-256 digest."""
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _safe_receipt_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned[:180] or "scientific-refresh"


def write_scientific_refresh_receipt(
    *,
    refresh_id: str,
    observer_run_ids: list[str],
    selected_steps: Sequence[Step],
    dag_state_before: dict[str, Any],
    dag_state_after: dict[str, Any],
    failures: list[str],
    started_at: str,
    paths: ExecutionPaths,
    module_overrides: Mapping[str, Path] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Render, hash, and atomically persist one scientific-refresh receipt."""
    before_steps = dag_state_before.get("steps", {})
    after_steps = dag_state_after.get("steps", {})
    if not isinstance(before_steps, dict):
        before_steps = {}
    if not isinstance(after_steps, dict):
        after_steps = {}

    step_records: list[dict[str, Any]] = []
    changed_stages: set[str] = set()
    for step in selected_steps:
        key = step.key
        before = before_steps.get(key, {})
        after = after_steps.get(key, {})
        if not isinstance(before, dict):
            before = {}
        if not isinstance(after, dict):
            after = {}
        output_changed = (
            before.get("output_digest") != after.get("output_digest")
        )
        if output_changed:
            changed_stages.add(step.stage)
        entrypoint = module_path(
            step.module,
            paths=paths,
            module_overrides=module_overrides,
        )
        step_records.append({
            "step_key": key,
            "stage": step.stage,
            "label": step.label,
            "module": step.module,
            "entrypoint": str(entrypoint),
            "entrypoint_route": module_route(
                step.module,
                module_overrides,
            ),
            "entrypoint_sha256": _file_sha256(entrypoint),
            "status": after.get("status"),
            "input_digest": after.get("input_digest"),
            "output_digest": after.get("output_digest"),
            "output_changed": output_changed,
        })

    director_products = []
    missing_products = []
    for name in SCIENTIFIC_REFRESH_REQUIRED_PRODUCTS:
        path = paths.analysis_results_dir / name
        digest = _file_sha256(path)
        director_products.append({
            "name": name,
            "path": str(path),
            "sha256": digest,
        })
        if digest is None:
            missing_products.append(name)

    required_meta_labels = {"Meta Science Engine", "Research Director"}
    meta_steps = [
        item
        for item in step_records
        if item.get("label") in required_meta_labels
    ]
    invalid_meta_steps = [
        item.get("step_key")
        for item in meta_steps
        if item.get("status") != "ok"
    ]
    issues = []
    if failures:
        issues.append({
            "code": "SCIENTIFIC_REFRESH_STEP_FAILURE",
            "message": "One or more Analyzer steps failed.",
            "actual": failures,
        })
    if missing_products:
        issues.append({
            "code": "SCIENTIFIC_REFRESH_PRODUCT_MISSING",
            "message": "Required Director refresh products are missing.",
            "actual": missing_products,
        })
    if (
        {item.get("label") for item in meta_steps}
        != required_meta_labels
        or invalid_meta_steps
    ):
        issues.append({
            "code": "SCIENTIFIC_REFRESH_META_INCOMPLETE",
            "message": "Meta/Research Director stages are not complete.",
            "actual": invalid_meta_steps or "no meta steps recorded",
        })

    status = "COMPLETED" if not issues else "FAILED"
    core = {
        "schema": RECEIPT_SCHEMA,
        "version": RECEIPT_VERSION,
        "status": status,
        "refresh_id": refresh_id,
        "observer_run_ids": observer_run_ids,
        "selected_stages": list(dict.fromkeys(
            step.stage for step in selected_steps
        )),
        "changed_stages": sorted(
            changed_stages,
            key=STAGE_ORDER.index,
        ),
        "steps": step_records,
        "director_products": director_products,
        "director_products_verified": not missing_products,
        "issues": issues,
        "started_at": started_at,
        "completed_at": _now_iso() if status == "COMPLETED" else None,
        "failed_at": _now_iso() if status == "FAILED" else None,
    }
    receipt = {
        **core,
        "receipt_hash": canonical_hash(core),
    }
    experiments = paths.analysis_results_dir / "Experiments"
    receipt_path = (
        experiments
        / "ScientificRefreshReceipts"
        / f"{_safe_receipt_id(refresh_id)}.json"
    )
    _atomic_write_json(receipt_path, receipt)
    _atomic_write_json(
        experiments / "scientific_refresh_receipt.json",
        receipt,
    )
    return receipt_path, receipt


__all__ = [
    "RECEIPT_SCHEMA",
    "RECEIPT_VERSION",
    "SCIENTIFIC_REFRESH_REQUIRED_PRODUCTS",
    "canonical_hash",
    "write_scientific_refresh_receipt",
]
