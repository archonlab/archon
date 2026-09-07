"""Authoritative Observer-queue to Analyzer scientific-refresh handoff.

BRIDGE5.7 owns the orchestration boundary only.  Scientific interpretation
remains inside the existing Analyzer modes and their native receipt contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence

from Analyzer_next.production.receipt_renderer import (
    RECEIPT_SCHEMA as NATIVE_RECEIPT_SCHEMA,
    canonical_hash,
)
from Analyzer_next.research.cycle.authoritative_record import (
    AuthoritativeCyclePaths,
    close_authoritative_research_cycles,
    verify_authoritative_cycle_closure_reference,
)
from Analyzer_next.research.cycle.authoritative_lifecycle import (
    AuthoritativeLifecycleError,
    AuthoritativeLifecyclePaths,
    FAILURE_STATES,
    find_authoritative_cycle,
    transition_authoritative_cycle,
)


REQUEST_SCHEMA = "archon_automatic_scientific_refresh_request_v1"
RECEIPT_SCHEMA = "archon_automatic_scientific_refresh_receipt_v1"
VERSION = "1.0"
TRIGGER = "OBSERVER_EXPERIMENT_QUEUE_COMPLETED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def build_automatic_refresh_request(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic queue-completion request.

    Terminal failed/cancelled rows remain in the request as limitations.  Only
    COMPLETED rows are eligible for telemetry intake.
    """
    normalized = []
    for row in rows:
        normalized.append({
            "queue_id": str(row.get("queue_id") or "").strip() or None,
            "experiment_id": (
                str(row.get("experiment_id") or "").strip() or None
            ),
            "observer_run_id": (
                str(row.get("observer_run_id") or "").strip() or None
            ),
            "status": str(row.get("status") or "").strip().upper(),
            "exit_code": row.get("exit_code"),
            "mode": str(row.get("mode") or "experimental").strip(),
            "runtime_id": (
                str(row.get("runtime_id") or "").strip() or None
            ),
            "attempt_id": (
                str(row.get("attempt_id") or "").strip() or None
            ),
            "authorization_id": (
                str(row.get("authorization_id") or "").strip() or None
            ),
            "source_experiment_id": (
                str(row.get("source_experiment_id") or "").strip() or None
            ),
            "prepared_review_hash": (
                str(row.get("prepared_review_hash") or "").strip() or None
            ),
            "attempt_receipt_path": (
                str(row.get("attempt_receipt_path") or "").strip() or None
            ),
        })
    normalized.sort(key=lambda item: str(item.get("queue_id") or ""))
    core = {
        "schema": REQUEST_SCHEMA,
        "version": VERSION,
        "trigger": TRIGGER,
        "runs": normalized,
    }
    request_hash = canonical_hash(core)
    return {
        **core,
        "refresh_id": f"AUTO-SCI-{request_hash[:20].upper()}",
        "request_hash": request_hash,
    }


def validate_automatic_refresh_request(
    request: Mapping[str, Any],
) -> tuple[bool, tuple[dict[str, Any], ...]]:
    issues: list[dict[str, Any]] = []
    core = {
        "schema": request.get("schema"),
        "version": request.get("version"),
        "trigger": request.get("trigger"),
        "runs": request.get("runs"),
    }
    if request.get("schema") != REQUEST_SCHEMA:
        issues.append({
            "code": "AUTOMATIC_REFRESH_REQUEST_SCHEMA_INVALID",
            "message": "Automatic refresh request schema is unsupported.",
        })
    if request.get("version") != VERSION or request.get("trigger") != TRIGGER:
        issues.append({
            "code": "AUTOMATIC_REFRESH_REQUEST_CONTRACT_INVALID",
            "message": "Automatic refresh version/trigger contract is invalid.",
        })
    expected_hash = canonical_hash(core)
    if request.get("request_hash") != expected_hash:
        issues.append({
            "code": "AUTOMATIC_REFRESH_REQUEST_HASH_INVALID",
            "message": "Automatic refresh request hash does not match its payload.",
        })
    if request.get("refresh_id") != f"AUTO-SCI-{expected_hash[:20].upper()}":
        issues.append({
            "code": "AUTOMATIC_REFRESH_ID_INVALID",
            "message": "Automatic refresh identity is not derived from the request.",
        })
    runs = request.get("runs")
    if not isinstance(runs, list) or not runs:
        issues.append({
            "code": "AUTOMATIC_REFRESH_EXPERIMENT_RUNS_MISSING",
            "message": "Queue completion contains no experimental rows.",
        })
        runs = []
    completed = [
        row for row in runs
        if isinstance(row, dict) and row.get("status") == "COMPLETED"
    ]
    if not completed:
        issues.append({
            "code": "AUTOMATIC_REFRESH_NO_COMPLETED_RUNS",
            "message": "No completed experimental run is eligible for intake.",
        })
    for index, row in enumerate(completed):
        missing = [
            key for key in ("queue_id", "experiment_id", "observer_run_id")
            if not row.get(key)
        ]
        if missing:
            issues.append({
                "code": "AUTOMATIC_REFRESH_RUN_IDENTITY_INCOMPLETE",
                "message": "Completed experiment run identity is incomplete.",
                "path": f"$.runs[{index}]",
                "actual": missing,
            })
        if row.get("runtime_id"):
            authoritative_missing = [
                key for key in (
                    "attempt_id",
                    "authorization_id",
                    "source_experiment_id",
                    "prepared_review_hash",
                    "attempt_receipt_path",
                )
                if not row.get(key)
            ]
            if authoritative_missing:
                issues.append({
                    "code": "AUTOMATIC_REFRESH_AUTHORITATIVE_IDENTITY_INCOMPLETE",
                    "message": (
                        "An authorized runtime run is missing its immutable "
                        "pre-execution identity."
                    ),
                    "path": f"$.runs[{index}]",
                    "actual": authoritative_missing,
                })
    observer_ids = [
        str(row.get("observer_run_id"))
        for row in completed if row.get("observer_run_id")
    ]
    if len(observer_ids) != len(set(observer_ids)):
        issues.append({
            "code": "AUTOMATIC_REFRESH_RUN_ID_DUPLICATE",
            "message": "Completed Observer run IDs must be unique.",
        })
    queue_ids = [
        str(row.get("queue_id"))
        for row in runs if isinstance(row, dict) and row.get("queue_id")
    ]
    if len(queue_ids) != len(set(queue_ids)):
        issues.append({
            "code": "AUTOMATIC_REFRESH_QUEUE_ID_DUPLICATE",
            "message": "Observer Queue IDs must be unique within one refresh.",
        })
    return not issues, tuple(issues)


@dataclass(frozen=True)
class AutomaticRefreshPaths:
    project_root: Path
    results_directory: Path
    analysis_root: Path
    analyzer_entrypoint: Path
    telemetry_database: Path
    python_executable: str = sys.executable

    @property
    def experiments_root(self) -> Path:
        return self.analysis_root / "Experiments"

    @property
    def requests_root(self) -> Path:
        return self.experiments_root / "AutomaticScientificRefreshRequests"

    @property
    def receipts_root(self) -> Path:
        return self.experiments_root / "AutomaticScientificRefreshReceipts"

    @property
    def logs_root(self) -> Path:
        return self.experiments_root / "AutomaticScientificRefreshLogs"


def write_automatic_refresh_request(
    request: Mapping[str, Any],
    paths: AutomaticRefreshPaths,
) -> Path:
    refresh_id = str(request.get("refresh_id") or "automatic-refresh")
    path = paths.requests_root / f"{refresh_id}.json"
    _atomic_json(path, dict(request))
    _atomic_json(paths.experiments_root / "automatic_scientific_refresh_request.json", dict(request))
    return path


def _verified_native_receipt(
    path: Path,
    *,
    refresh_id: str,
    observer_run_ids: Sequence[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    receipt = _read_json(path, {})
    issues: list[dict[str, Any]] = []
    if not isinstance(receipt, dict) or not receipt:
        return {}, [{
            "code": "AUTOMATIC_REFRESH_NATIVE_RECEIPT_MISSING",
            "message": "Analyzer did not issue a scientific refresh receipt.",
            "actual": str(path),
        }]
    core = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if receipt.get("schema") != NATIVE_RECEIPT_SCHEMA:
        issues.append({
            "code": "AUTOMATIC_REFRESH_NATIVE_SCHEMA_INVALID",
            "message": "Analyzer scientific refresh receipt schema is invalid.",
        })
    if receipt.get("receipt_hash") != canonical_hash(core):
        issues.append({
            "code": "AUTOMATIC_REFRESH_NATIVE_HASH_INVALID",
            "message": "Analyzer scientific refresh receipt hash is invalid.",
        })
    if receipt.get("status") != "COMPLETED" or receipt.get("refresh_id") != refresh_id:
        issues.append({
            "code": "AUTOMATIC_REFRESH_NATIVE_STATUS_INVALID",
            "message": "Analyzer scientific refresh did not complete for this request.",
            "actual": {
                "status": receipt.get("status"),
                "refresh_id": receipt.get("refresh_id"),
            },
        })
    recorded_ids = {
        str(value) for value in receipt.get("observer_run_ids", [])
    }
    missing_ids = sorted(set(observer_run_ids) - recorded_ids)
    if missing_ids:
        issues.append({
            "code": "AUTOMATIC_REFRESH_NATIVE_RUN_IDS_MISSING",
            "message": "Native refresh receipt does not cover every completed run.",
            "actual": missing_ids,
        })
    if receipt.get("director_products_verified") is not True:
        issues.append({
            "code": "AUTOMATIC_REFRESH_DIRECTOR_PRODUCTS_UNVERIFIED",
            "message": "Research Director products were not verified.",
        })
    for product in receipt.get("director_products", []):
        if not isinstance(product, dict):
            continue
        product_path = Path(str(product.get("path") or ""))
        if _file_sha256(product_path) != product.get("sha256"):
            issues.append({
                "code": "AUTOMATIC_REFRESH_DIRECTOR_PRODUCT_HASH_INVALID",
                "message": "A Research Director product is missing or changed.",
                "actual": str(product_path),
            })
    return receipt, issues


def _verified_wrapper_receipt(
    path: Path,
    *,
    request_hash: str,
    native_path: Path,
    refresh_id: str,
    observer_run_ids: Sequence[str],
    authoritative_required: bool,
) -> dict[str, Any] | None:
    receipt = _read_json(path, {})
    if not isinstance(receipt, dict) or receipt.get("status") != "COMPLETED":
        return None
    core = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if receipt.get("receipt_hash") != canonical_hash(core):
        return None
    if receipt.get("request_hash") != request_hash:
        return None
    native, issues = _verified_native_receipt(
        native_path,
        refresh_id=refresh_id,
        observer_run_ids=observer_run_ids,
    )
    if issues or native.get("receipt_hash") != receipt.get("native_receipt_hash"):
        return None
    closure = receipt.get("authoritative_cycle_closure")
    if not isinstance(closure, dict):
        # BRIDGE5.7 receipts predate cycle closure.  They remain reusable only
        # for genuinely ad-hoc rows that carried no authoritative runtime.
        if not authoritative_required:
            return receipt
        return None
    closure_reference = {
        **closure,
        "request_hash": request_hash,
    }
    if not verify_authoritative_cycle_closure_reference(closure_reference):
        return None
    return receipt


def _record_authoritative_refresh_failure(
    request: Mapping[str, Any],
    paths: AutomaticRefreshPaths,
    *,
    refresh_id: str,
    request_hash: str,
    issues: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Attach a durable fail-closed receipt to tracked lifecycle cycles.

    Legacy/historical cycles without the BRIDGE5.8 append-only ledger are left
    untouched.  We never fabricate their missing earlier transitions.
    """
    lifecycle_paths = AuthoritativeLifecyclePaths(
        project_root=paths.project_root,
        analysis_root=paths.analysis_root,
    )
    runtime_ids = sorted({
        str(row.get("runtime_id"))
        for row in request.get("runs", [])
        if isinstance(row, Mapping)
        and row.get("status") == "COMPLETED"
        and row.get("runtime_id")
    })
    tracked: list[dict[str, Any]] = []
    for runtime_id in runtime_ids:
        record = find_authoritative_cycle(
            lifecycle_paths, runtime_id=runtime_id
        )
        if not record:
            continue
        lifecycle = record.get("lifecycle")
        if not isinstance(lifecycle, Mapping) or not lifecycle.get("receipt_chain_head"):
            continue
        tracked.append(record)

    if not tracked:
        return {
            "status": "NOT_APPLICABLE",
            "cycle_ids": [],
            "receipt_path": None,
            "receipt_hash": None,
            "issues": [],
        }

    failure_core = {
        "schema": "archon_scientific_refresh_failure_receipt_v1",
        "version": VERSION,
        "status": "FAILED",
        "refresh_id": refresh_id,
        "request_hash": request_hash,
        "issue_codes": [
            str(row.get("code") or "AUTOMATIC_REFRESH_FAILED")
            for row in issues
        ],
        "issues": [dict(row) for row in issues],
        "runtime_ids": runtime_ids,
        "recorded_at": _now_iso(),
    }
    failure_receipt = {
        **failure_core,
        "receipt_hash": canonical_hash(failure_core),
    }
    failure_path = (
        paths.experiments_root
        / "ScientificRefreshFailureReceipts"
        / f"{refresh_id}.json"
    )
    _atomic_json(failure_path, failure_receipt)

    transition_issues: list[dict[str, Any]] = []
    cycle_ids: list[str] = []
    reason = (
        str(issues[0].get("code"))
        if issues else "AUTOMATIC_SCIENTIFIC_REFRESH_FAILED"
    )
    for record in tracked:
        cycle_id = str(record.get("cycle_id"))
        cycle_ids.append(cycle_id)
        state = str(record.get("lifecycle_state") or record.get("current_stage") or "")
        if state in FAILURE_STATES:
            continue
        try:
            transition_authoritative_cycle(
                lifecycle_paths,
                cycle_id=cycle_id,
                to_state="FAILED",
                event_id=(
                    f"BRIDGE5.8:{cycle_id}:SCIENTIFIC_REFRESH_FAILED:"
                    f"{request_hash[:16]}"
                ),
                references=[{
                    "kind": "ScientificRefreshFailureReceipt",
                    "id": refresh_id,
                    "path": str(failure_path.resolve()),
                    "receipt_hash": failure_receipt["receipt_hash"],
                }],
                reason=reason,
                scientific_result="NOT_PRODUCED",
                record_updates={
                    "scientific_refresh_status": "FAILED",
                    "director_refresh_status": "NOT_RUN",
                },
            )
        except AuthoritativeLifecycleError as exc:
            transition_issues.append({
                "code": "AUTHORITATIVE_CYCLE_FAILURE_RECORDING_FAILED",
                "message": str(exc),
                "cycle_id": cycle_id,
            })

    return {
        "status": "FAILED" if not transition_issues else "FAILED_INTEGRITY",
        "cycle_ids": cycle_ids,
        "receipt_path": str(failure_path),
        "receipt_hash": failure_receipt["receipt_hash"],
        "issues": transition_issues,
    }


def run_automatic_scientific_refresh(
    request: Mapping[str, Any],
    paths: AutomaticRefreshPaths,
    *,
    timeout_seconds: int = 7200,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Run intake then scientific refresh and attest the closed handoff."""
    request = dict(request)
    valid, validation_issues = validate_automatic_refresh_request(request)
    declared_refresh_id = str(
        request.get("refresh_id") or "AUTOMATIC-REFRESH-INVALID"
    )
    refresh_id = (
        declared_refresh_id
        if valid
        else f"AUTO-SCI-INVALID-{canonical_hash(request)[:20].upper()}"
    )
    request_hash = str(request.get("request_hash") or "")
    runs = [row for row in request.get("runs", []) if isinstance(row, dict)]
    completed = [row for row in runs if row.get("status") == "COMPLETED"]
    observer_ids = [
        str(row.get("observer_run_id"))
        for row in completed if row.get("observer_run_id")
    ]
    experiment_ids = sorted({
        str(row.get("experiment_id"))
        for row in runs if row.get("experiment_id")
    })
    queue_ids = [
        str(row.get("queue_id")) for row in runs if row.get("queue_id")
    ]
    receipt_path = paths.receipts_root / f"{refresh_id}.json"
    native_path = (
        paths.experiments_root
        / "ScientificRefreshReceipts"
        / f"{refresh_id}.json"
    )
    reused = (
        _verified_wrapper_receipt(
            receipt_path,
            request_hash=request_hash,
            native_path=native_path,
            refresh_id=refresh_id,
            observer_run_ids=observer_ids,
            authoritative_required=any(
                row.get("runtime_id") for row in completed
            ),
        )
        if valid else None
    )
    if reused is not None:
        return {
            "status": "REUSED",
            "refresh_id": refresh_id,
            "receipt_path": str(receipt_path),
            "receipt": reused,
        }

    started_at = _now_iso()
    issues = list(validation_issues)
    paths.logs_root.mkdir(parents=True, exist_ok=True)
    intake_log = paths.logs_root / f"{refresh_id}.intake.log"
    refresh_log = paths.logs_root / f"{refresh_id}.scientific-refresh.log"
    intake_command: list[str] = []
    refresh_command: list[str] = []
    intake_returncode: int | None = None
    refresh_returncode: int | None = None
    native_receipt: dict[str, Any] = {}
    cycle_closure: dict[str, Any] = {
        "status": "NOT_APPLICABLE",
        "cycle_ids": [],
        "receipt_path": None,
        "receipt_hash": None,
        "issues": [],
    }

    environment = os.environ.copy()
    environment["ARCHON_RESULTS_DIR"] = str(paths.results_directory)
    environment["ARCHON_ANALYSIS_DIR"] = str(paths.analysis_root)
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (
            str(paths.project_root),
            environment.get("PYTHONPATH", ""),
        ) if value
    )

    if valid:
        intake_command = [
            paths.python_executable,
            str(paths.analyzer_entrypoint),
            str(paths.results_directory),
            "--mode",
            "intake",
            "--telemetry-db",
            str(paths.telemetry_database),
            "--telemetry-status",
            "completed",
            "--force-stage",
            "profiles",
        ]
        for run_id in observer_ids:
            intake_command.extend(["--telemetry-run-id", run_id])
        try:
            completed_process = runner(
                intake_command,
                cwd=str(paths.project_root),
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
            intake_returncode = int(completed_process.returncode)
            intake_log.write_text(completed_process.stdout or "", encoding="utf-8")
            if intake_returncode != 0:
                issues.append({
                    "code": "AUTOMATIC_REFRESH_INTAKE_FAILED",
                    "message": "Analyzer intake returned a non-zero exit code.",
                    "actual": intake_returncode,
                })
        except subprocess.TimeoutExpired as exc:
            intake_log.write_text(str(exc.stdout or ""), encoding="utf-8")
            issues.append({
                "code": "AUTOMATIC_REFRESH_INTAKE_TIMEOUT",
                "message": "Analyzer intake exceeded its timeout.",
                "actual": timeout_seconds,
            })
        except Exception as exc:
            issues.append({
                "code": "AUTOMATIC_REFRESH_INTAKE_ERROR",
                "message": f"{type(exc).__name__}: {exc}",
            })

    if not issues:
        refresh_command = [
            paths.python_executable,
            str(paths.analyzer_entrypoint),
            str(paths.results_directory),
            "--mode",
            "scientific-refresh",
            "--scientific-refresh-id",
            refresh_id,
        ]
        for run_id in observer_ids:
            refresh_command.extend(["--telemetry-run-id", run_id])
        try:
            completed_process = runner(
                refresh_command,
                cwd=str(paths.project_root),
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
            refresh_returncode = int(completed_process.returncode)
            refresh_log.write_text(completed_process.stdout or "", encoding="utf-8")
            if refresh_returncode != 0:
                issues.append({
                    "code": "AUTOMATIC_REFRESH_SCIENCE_FAILED",
                    "message": "Analyzer scientific refresh returned a non-zero exit code.",
                    "actual": refresh_returncode,
                })
        except subprocess.TimeoutExpired as exc:
            refresh_log.write_text(str(exc.stdout or ""), encoding="utf-8")
            issues.append({
                "code": "AUTOMATIC_REFRESH_SCIENCE_TIMEOUT",
                "message": "Analyzer scientific refresh exceeded its timeout.",
                "actual": timeout_seconds,
            })
        except Exception as exc:
            issues.append({
                "code": "AUTOMATIC_REFRESH_SCIENCE_ERROR",
                "message": f"{type(exc).__name__}: {exc}",
            })

    if not issues:
        native_receipt, native_issues = _verified_native_receipt(
            native_path,
            refresh_id=refresh_id,
            observer_run_ids=observer_ids,
        )
        issues.extend(native_issues)

    if not issues:
        cycle_closure = close_authoritative_research_cycles(
            request,
            native_receipt,
            AuthoritativeCyclePaths(
                project_root=paths.project_root,
                analysis_root=paths.analysis_root,
            ),
        )
        if cycle_closure.get("status") == "FAILED":
            issues.extend(list(cycle_closure.get("issues", [])))

    if issues and valid:
        failure_closure = _record_authoritative_refresh_failure(
            request,
            paths,
            refresh_id=refresh_id,
            request_hash=request_hash,
            issues=issues,
        )
        if failure_closure.get("status") != "NOT_APPLICABLE":
            cycle_closure = failure_closure
            issues.extend(list(failure_closure.get("issues", [])))

    status = "COMPLETED" if not issues else "FAILED"
    core = {
        "schema": RECEIPT_SCHEMA,
        "version": VERSION,
        "status": status,
        "refresh_id": refresh_id,
        "trigger": TRIGGER,
        "request_hash": request_hash,
        "queue_ids": queue_ids,
        "experiment_ids": experiment_ids,
        "observer_run_ids": observer_ids,
        "queue_summary": {
            "total_experimental_runs": len(runs),
            "completed": len(completed),
            "failed": sum(row.get("status") == "FAILED" for row in runs),
            "cancelled": sum(row.get("status") == "CANCELLED" for row in runs),
            "recovery_required": sum(
                row.get("status") == "RECOVERY_REQUIRED" for row in runs
            ),
        },
        "mode_sequence": ["intake", "scientific-refresh"],
        "intake": {
            "command": intake_command,
            "returncode": intake_returncode,
            "log_path": str(intake_log) if intake_command else None,
            "forced_stage": "profiles" if intake_command else None,
        },
        "scientific_refresh": {
            "command": refresh_command,
            "returncode": refresh_returncode,
            "log_path": str(refresh_log) if refresh_command else None,
        },
        "native_receipt_path": str(native_path) if native_receipt else None,
        "native_receipt_hash": native_receipt.get("receipt_hash"),
        "director_products_verified": (
            native_receipt.get("director_products_verified") is True
        ),
        "authoritative_cycle_closure": {
            "status": cycle_closure.get("status"),
            "cycle_ids": list(cycle_closure.get("cycle_ids", [])),
            "receipt_path": cycle_closure.get("receipt_path"),
            "receipt_hash": cycle_closure.get("receipt_hash"),
        },
        "issues": issues,
        "started_at": started_at,
        "completed_at": _now_iso() if status == "COMPLETED" else None,
        "failed_at": _now_iso() if status == "FAILED" else None,
    }
    receipt = {**core, "receipt_hash": canonical_hash(core)}
    _atomic_json(receipt_path, receipt)
    _atomic_json(
        paths.experiments_root / "automatic_scientific_refresh_receipt.json",
        receipt,
    )

    registry_path = (
        paths.experiments_root / "automatic_scientific_refresh_registry.json"
    )
    registry = _read_json(registry_path, {})
    rows_registry = (
        registry.get("refreshes", []) if isinstance(registry, dict) else []
    )
    rows_registry = [
        row for row in rows_registry
        if isinstance(row, dict) and row.get("refresh_id") != refresh_id
    ]
    rows_registry.append({
        "refresh_id": refresh_id,
        "status": status,
        "request_hash": request_hash,
        "experiment_ids": experiment_ids,
        "observer_run_ids": observer_ids,
        "cycle_ids": list(cycle_closure.get("cycle_ids", [])),
        "receipt_path": str(receipt_path),
        "recorded_at": _now_iso(),
    })
    _atomic_json(registry_path, {
        "schema": "archon_automatic_scientific_refresh_registry_v1",
        "version": VERSION,
        "refreshes": rows_registry[-1000:],
    })
    return {
        "status": status,
        "refresh_id": refresh_id,
        "receipt_path": str(receipt_path),
        "receipt": receipt,
    }


__all__ = [
    "AutomaticRefreshPaths",
    "RECEIPT_SCHEMA",
    "REQUEST_SCHEMA",
    "TRIGGER",
    "VERSION",
    "build_automatic_refresh_request",
    "run_automatic_scientific_refresh",
    "validate_automatic_refresh_request",
    "write_automatic_refresh_request",
]
