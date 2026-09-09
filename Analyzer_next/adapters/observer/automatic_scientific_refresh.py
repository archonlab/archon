"""OL2 Queue adapter for BRIDGE5.7 automatic scientific refresh.

The adapter translates immutable QUEUE1 terminal items into the domain-neutral
automatic-refresh request and owns the detached CLI process.  Tk remains a
read-only consumer of the handoff snapshot; Analyzer orchestration stays in
``Analyzer_next.production.automatic_refresh``.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import subprocess
import threading
from typing import Any, Iterable, Sequence

from Tools.archon_runtime_python import runtime_python_environment

from Analyzer_next.execution.observer.shell2.queue1.model import retry_leaf_items

from Analyzer_next.production.automatic_refresh import (
    AutomaticRefreshPaths,
    build_automatic_refresh_request,
    write_automatic_refresh_request,
)


RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
BLOCKED = "BLOCKED"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default


def _queue_item_context(item: Any) -> dict[str, Any]:
    try:
        context = item.prepared.run_spec.experimental_context
    except (AttributeError, TypeError, ValueError):
        return {}
    return context if isinstance(context, dict) else {}


def completed_refresh_run_ids(paths: AutomaticRefreshPaths) -> set[str]:
    """Return only run IDs covered by completed automatic-refresh receipts."""
    registry = _read_json(
        paths.experiments_root / "automatic_scientific_refresh_registry.json",
        {},
    )
    rows = registry.get("refreshes", []) if isinstance(registry, dict) else []
    return {
        str(run_id)
        for row in rows
        if isinstance(row, dict) and row.get("status") == COMPLETED
        for run_id in row.get("observer_run_ids", [])
        if run_id
    }


def automatic_refresh_rows_from_queue(
    items: Iterable[Any],
    *,
    covered_run_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Project terminal experimental QUEUE1 items into refresh rows.

    A refresh is emitted only when at least one completed experimental run has
    not already been covered by a completed receipt.  Failed/cancelled rows are
    retained as limitations for that same terminal snapshot, but can never
    trigger scientific interpretation on their own.
    """
    covered = {str(value) for value in covered_run_ids}
    rows: list[dict[str, Any]] = []
    has_new_completed = False
    unresolved_recovery = False
    for item in retry_leaf_items(items):
        context = _queue_item_context(item)
        experiment_id = str(context.get("experiment_id") or "").strip()
        if not experiment_id:
            continue
        status_value = getattr(getattr(item, "status", None), "value", None)
        status = str(status_value or getattr(item, "status", "")).upper()
        if status not in {
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "RECOVERY_REQUIRED",
        }:
            continue
        if status == "RECOVERY_REQUIRED":
            unresolved_recovery = True
        observer_run_id = str(
            getattr(item, "telemetry_run_id", None) or ""
        ).strip() or None
        execution_attempt = context.get("execution_attempt")
        if not isinstance(execution_attempt, dict):
            execution_attempt = {}
        runtime_id = str(
            execution_attempt.get("source_runtime_id")
            or context.get("runtime_id")
            or ""
        ).strip() or None
        attempt_id = str(
            execution_attempt.get("attempt_id") or ""
        ).strip() or None
        authorization_id = str(
            execution_attempt.get("authorization_id") or ""
        ).strip() or None
        source_experiment_id = str(
            execution_attempt.get("source_experiment_id") or ""
        ).strip() or None
        prepared = getattr(item, "prepared", None)
        review_hash = str(
            getattr(prepared, "review_hash", None) or ""
        ).strip() or None
        output_directory = str(
            getattr(getattr(prepared, "run_spec", None), "output_dir", None)
            or ""
        ).strip()
        attempt_receipt_path = (
            str((Path(output_directory) / "ol2_execution_attempt.json").resolve())
            if runtime_id and attempt_id and output_directory
            else None
        )
        if status == "COMPLETED":
            if observer_run_id and observer_run_id in covered:
                continue
            has_new_completed = True
        rows.append({
            "queue_id": str(getattr(item, "queue_id", "") or "").strip() or None,
            "experiment_id": experiment_id,
            "observer_run_id": observer_run_id,
            "status": status,
            "exit_code": getattr(item, "exit_code", None),
            "mode": str(getattr(item, "mode", "experimental") or "experimental"),
            "runtime_id": runtime_id,
            "attempt_id": attempt_id,
            "authorization_id": authorization_id,
            "source_experiment_id": source_experiment_id,
            "prepared_review_hash": review_hash,
            "attempt_receipt_path": attempt_receipt_path,
        })
    if unresolved_recovery or not has_new_completed:
        return []
    return rows


@dataclass(frozen=True, slots=True)
class AutomaticRefreshHandoffSnapshot:
    revision: int = 0
    state: str = "IDLE"
    refresh_id: str | None = None
    request_path: str | None = None
    receipt_path: str | None = None
    log_path: str | None = None
    process_id: int | None = None
    message: str = ""


class AutomaticScientificRefreshHandoff:
    """Start and monitor one detached automatic-refresh CLI process."""

    def __init__(
        self,
        paths: AutomaticRefreshPaths,
        *,
        process_factory: Any = subprocess.Popen,
    ) -> None:
        self.paths = paths
        self.process_factory = process_factory
        self._lock = threading.RLock()
        self._process: Any | None = None
        self._snapshot = AutomaticRefreshHandoffSnapshot()

    @property
    def snapshot(self) -> AutomaticRefreshHandoffSnapshot:
        with self._lock:
            return self._snapshot

    def _publish(self, **changes: Any) -> AutomaticRefreshHandoffSnapshot:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                revision=self._snapshot.revision + 1,
                **changes,
            )
            return self._snapshot

    def _previous_failed_request(self, request_hash: str) -> bool:
        registry = _read_json(
            self.paths.experiments_root
            / "automatic_scientific_refresh_registry.json",
            {},
        )
        rows = registry.get("refreshes", []) if isinstance(registry, dict) else []
        return any(
            isinstance(row, dict)
            and row.get("request_hash") == request_hash
            and row.get("status") == FAILED
            for row in rows
        )

    def schedule_queue_items(
        self,
        items: Sequence[Any],
        *,
        timeout_seconds: int = 7200,
    ) -> AutomaticRefreshHandoffSnapshot | None:
        with self._lock:
            if self._process is not None:
                return self._snapshot

        rows = automatic_refresh_rows_from_queue(
            items,
            covered_run_ids=completed_refresh_run_ids(self.paths),
        )
        if not rows:
            return None
        request = build_automatic_refresh_request(rows)
        refresh_id = str(request["refresh_id"])
        request_hash = str(request["request_hash"])
        if self._previous_failed_request(request_hash):
            return self._publish(
                state=BLOCKED,
                refresh_id=refresh_id,
                message=(
                    "Automatic scientific refresh is blocked by its previous "
                    "failed receipt; inspect or rerun the durable request explicitly."
                ),
            )

        request_path = write_automatic_refresh_request(request, self.paths)
        receipt_path = self.paths.receipts_root / f"{refresh_id}.json"
        log_path = self.paths.logs_root / f"{refresh_id}.launcher.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        cli = (
            self.paths.project_root
            / "Analyzer_next"
            / "cli"
            / "automatic_scientific_refresh.py"
        )
        command = [
            self.paths.python_executable,
            str(cli),
            "--request",
            str(request_path),
            "--results-directory",
            str(self.paths.results_directory),
            "--analysis-root",
            str(self.paths.analysis_root),
            "--analyzer-entrypoint",
            str(self.paths.analyzer_entrypoint),
            "--telemetry-database",
            str(self.paths.telemetry_database),
            "--python",
            self.paths.python_executable,
            "--timeout-seconds",
            str(max(1, int(timeout_seconds))),
        ]
        try:
            with log_path.open("a", encoding="utf-8") as log_handle:
                process = self.process_factory(
                    command,
                    cwd=str(self.paths.project_root),
                    env=runtime_python_environment(self.paths.project_root),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
        except Exception as exc:
            return self._publish(
                state=FAILED,
                refresh_id=refresh_id,
                request_path=str(request_path),
                receipt_path=str(receipt_path),
                log_path=str(log_path),
                message=f"Automatic refresh process could not start: {type(exc).__name__}: {exc}",
            )

        with self._lock:
            self._process = process
        snapshot = self._publish(
            state=RUNNING,
            refresh_id=refresh_id,
            request_path=str(request_path),
            receipt_path=str(receipt_path),
            log_path=str(log_path),
            process_id=int(getattr(process, "pid", 0) or 0) or None,
            message="Automatic scientific refresh is running.",
        )
        threading.Thread(
            target=self._monitor,
            args=(process, receipt_path),
            daemon=True,
            name=f"archon-auto-refresh-{refresh_id}",
        ).start()
        return snapshot

    def _monitor(self, process: Any, receipt_path: Path) -> None:
        try:
            return_code = int(process.wait())
        except Exception as exc:
            return_code = -1
            wait_error = f"{type(exc).__name__}: {exc}"
        else:
            wait_error = ""
        receipt = _read_json(receipt_path, {})
        receipt_status = (
            str(receipt.get("status") or "")
            if isinstance(receipt, dict) else ""
        )
        if return_code == 0 and receipt_status == COMPLETED:
            state = COMPLETED
            message = "Automatic scientific refresh completed and was attested."
        else:
            state = FAILED
            issues = receipt.get("issues", []) if isinstance(receipt, dict) else []
            issue = issues[0].get("code") if issues and isinstance(issues[0], dict) else None
            detail = issue or wait_error or f"exit code {return_code}"
            message = f"Automatic scientific refresh failed: {detail}."
        with self._lock:
            if self._process is process:
                self._process = None
        self._publish(state=state, message=message)


__all__ = [
    "AutomaticRefreshHandoffSnapshot",
    "AutomaticScientificRefreshHandoff",
    "automatic_refresh_rows_from_queue",
    "completed_refresh_run_ids",
]
