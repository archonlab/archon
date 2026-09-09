"""BRIDGE4 explicit Universe Search authorization and dispatch handoff.

The BRIDGE3 cohort runtime is intentionally not an Observer queue workload.
This adapter owns the narrow boundary from a hash-pinned
``READY_FOR_SEARCH_LAUNCH_REVIEW`` package to an explicitly authorized and then
explicitly started Universe Search process.  It never projects Search work into
QUEUE1 and never mutates frozen ``Analyzer/`` or ``Universe_Search/`` sources.
"""
from __future__ import annotations

from Tools.archon_platform import pid_alive

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Sequence

from Tools.archon_runtime_python import (
    runtime_python_environment,
    runtime_python_selection,
)
from Universe_Search.search_runtime_contract import (
    SearchDependencyError,
    preflight_search_dependencies,
    search_command_parts,
)

from Analyzer_next.adapters.observer.cohort_search_runtime import (
    BRIDGE_ID as MATERIALIZATION_BRIDGE_ID,
    SEARCH_READY_STATUS,
    validate_cohort_search_runtime,
)
from Analyzer_next.execution.observer.shell2.functions1g.model import (
    RuntimeAuthorizationResult,
    SearchDispatchResult,
    SearchLauncherOpenResult,
)

BRIDGE_ID = "BRIDGE4"
SEARCH_AUTHORIZED_STATUS = "SEARCH_LAUNCH_AUTHORIZED"
SEARCH_STARTED_STATUS = "SEARCH_EXECUTION_STARTED"
SEARCH_COMPLETED_STATUS = "SEARCH_EXECUTION_COMPLETED"
SEARCH_AUTH_SCHEMA = "archon_search_launch_authorization_registry_v1"
SEARCH_RECEIPT_SCHEMA = "archon_search_launch_authorization_receipt_v1"
SEARCH_DISPATCH_SCHEMA = "archon_search_execution_dispatch_receipt_v1"


class CohortSearchExecutionError(RuntimeError):
    pass


class _DefaultProcessRunner:
    def start(self, command: Sequence[str], **kwargs: Any):
        return subprocess.Popen(list(command), **kwargs)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {} if default is None else default
    except (OSError, json.JSONDecodeError) as exc:
        raise CohortSearchExecutionError(f"cannot read {path}: {exc}") from exc


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _token(prefix: str, runtime_id: str) -> str:
    raw = f"{runtime_id}|{_now()}|{os.getpid()}".encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:16].upper()}"


def _resolve(project_root: Path, value: Any) -> Path:
    path = Path(str(value or "")).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _refresh_runtime_registry_hash(registry: dict[str, Any]) -> None:
    packages = [dict(row) for row in _as_list(registry.get("packages")) if isinstance(row, dict)]
    summary = dict(_as_dict(registry.get("summary")))
    summary["ready_for_launch_review_count"] = sum(
        1 for row in packages if row.get("status") == "READY_FOR_LAUNCH_REVIEW"
    )
    summary["ready_for_search_launch_review_count"] = sum(
        1 for row in packages if row.get("status") == SEARCH_READY_STATUS
    )
    summary["launch_authorized_count"] = sum(
        1 for row in packages if row.get("status") in {"LAUNCH_AUTHORIZED", SEARCH_AUTHORIZED_STATUS, SEARCH_STARTED_STATUS, SEARCH_COMPLETED_STATUS}
    )
    summary["search_launch_authorized_count"] = sum(
        1 for row in packages if row.get("status") in {SEARCH_AUTHORIZED_STATUS, SEARCH_STARTED_STATUS, SEARCH_COMPLETED_STATUS}
    )
    summary["search_execution_started_count"] = sum(
        1 for row in packages if row.get("status") == SEARCH_STARTED_STATUS
    )
    summary["search_execution_completed_count"] = sum(
        1 for row in packages if row.get("status") == SEARCH_COMPLETED_STATUS
    )
    registry["summary"] = summary
    registry["content_hash"] = _canonical_hash({
        "summary": summary,
        "packages": packages,
        "blocked_plans": _as_list(registry.get("blocked_plans")),
        "source_registry": _as_dict(registry.get("source_registry")),
    })


def _refresh_auth_registry_hash(registry: dict[str, Any]) -> None:
    rows = [dict(row) for row in _as_list(registry.get("authorizations")) if isinstance(row, dict)]
    registry["authorizations"] = rows
    registry["content_hash"] = _canonical_hash({"authorizations": rows})


@dataclass(frozen=True, slots=True)
class SearchAuthorizationSnapshot:
    runtime_id: str
    authorization_id: str
    runtime_hash: str
    receipt_path: Path
    entry: dict[str, Any]


class CohortSearchExecutionHandoff:
    def __init__(
        self,
        project_root: Path,
        *,
        experiments_root: Path | None = None,
        runner: Any | None = None,
        launcher_runner: Any | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.experiments_root = Path(
            experiments_root
            or self.project_root / "Results" / "Analysis" / "Experiments"
        ).resolve()
        self.runner = runner or _DefaultProcessRunner()
        self.launcher_runner = launcher_runner or _DefaultProcessRunner()

    @property
    def runtime_registry_path(self) -> Path:
        return self.experiments_root / "experiment_runtime_registry.json"

    @property
    def authorization_registry_path(self) -> Path:
        return self.experiments_root / "search_launch_authorization_registry.json"

    def _runtime_registry(self) -> dict[str, Any]:
        payload = _load(self.runtime_registry_path, {})
        if not isinstance(payload, dict):
            raise CohortSearchExecutionError("runtime registry is invalid")
        return payload

    def _authorization_registry(self) -> dict[str, Any]:
        payload = _load(self.authorization_registry_path, {})
        if not isinstance(payload, dict):
            return {"schema": SEARCH_AUTH_SCHEMA, "authorizations": []}
        payload.setdefault("schema", SEARCH_AUTH_SCHEMA)
        payload.setdefault("authorizations", [])
        return payload

    def _runtime_entry(self, runtime_id: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
        registry = self._runtime_registry()
        matches = [
            row for row in _as_list(registry.get("packages"))
            if isinstance(row, dict) and str(row.get("runtime_id") or "") == runtime_id
        ]
        if len(matches) != 1:
            raise CohortSearchExecutionError(f"runtime {runtime_id!r} is not uniquely registered")
        entry = dict(matches[0])
        path = _resolve(self.project_root, entry.get("package_path"))
        package = _load(path, {})
        if not isinstance(package, dict) or not package:
            raise CohortSearchExecutionError(f"runtime package missing or invalid: {path}")
        return entry, package, path

    def _active_authorization(self, runtime_id: str) -> dict[str, Any] | None:
        rows = [
            dict(row)
            for row in _as_list(self._authorization_registry().get("authorizations"))
            if isinstance(row, dict)
            and str(row.get("runtime_id") or "") == runtime_id
            and row.get("lifecycle_status", "ACTIVE") == "ACTIVE"
            and row.get("superseded") is not True
        ]
        if len(rows) > 1:
            raise CohortSearchExecutionError(f"runtime {runtime_id!r} has multiple active Search authorizations")
        return rows[0] if rows else None

    def authorization_for_runtime(self, runtime_id: str) -> dict[str, Any] | None:
        runtime_id = str(runtime_id).strip()
        active = self._active_authorization(runtime_id)
        if active is not None:
            return active
        rows = [
            dict(row)
            for row in _as_list(self._authorization_registry().get("authorizations"))
            if isinstance(row, dict)
            and str(row.get("runtime_id") or "") == runtime_id
            and row.get("superseded") is not True
        ]
        rows.sort(key=lambda row: str(row.get("authorized_at") or ""))
        return rows[-1] if rows else None

    def managed_launcher_context(self, runtime_id: str) -> dict[str, Any]:
        """Return a verified, read-only Search contract for Search Launcher v2.

        BRIDGE4.2 deliberately keeps scientific authorization in OL2 while the
        long-running Search operator surface moves to Universe Search Launcher.
        This method never starts Search and never writes Observer Queue rows.
        """
        runtime_id = str(runtime_id).strip()
        entry, package, _package_path = self._runtime_entry(runtime_id)
        runtime, search = self._verify_immutable_search_contract(
            runtime_id,
            entry,
            package,
            require_ready=False,
            revalidate_live_files=False,
        )
        status = str(entry.get("status") or package.get("status") or "")
        if status not in {SEARCH_AUTHORIZED_STATUS, SEARCH_STARTED_STATUS, SEARCH_COMPLETED_STATUS}:
            raise CohortSearchExecutionError(
                f"runtime {runtime_id} is not authorized/started/completed for managed Search Launcher"
            )
        if status == SEARCH_AUTHORIZED_STATUS:
            auth = self._verify_authorized(runtime_id)
        else:
            auth = self.authorization_for_runtime(runtime_id) or {}
            if auth.get("verification_status") != "VERIFIED":
                raise CohortSearchExecutionError("managed Search authorization is not VERIFIED")
            launch = _as_dict(package.get("search_launch_authorization"))
            if launch.get("authorization_id") != auth.get("authorization_id"):
                raise CohortSearchExecutionError("managed Search authorization identity mismatch")
            if auth.get("runtime_hash") != package.get("runtime_hash"):
                raise CohortSearchExecutionError("managed Search authorization runtime hash mismatch")

        state = _as_dict(package.get("search_execution_state"))
        dispatch: dict[str, Any] = {}
        dispatch_id = str(state.get("dispatch_id") or auth.get("dispatch_id") or "")
        if dispatch_id:
            dispatch_path = self.experiments_root / "SearchExecutionDispatches" / f"{dispatch_id}.json"
            loaded = _load(dispatch_path, {})
            if isinstance(loaded, dict) and loaded.get("dispatch_id") == dispatch_id:
                dispatch = loaded

        outcome: dict[str, Any] = {}
        outcome_value = state.get("outcome_path") or dispatch.get("outcome_path") or auth.get("outcome_path")
        if outcome_value:
            outcome_path = _resolve(self.project_root, outcome_value)
            loaded = _load(outcome_path, {}) if outcome_path.exists() else {}
            if isinstance(loaded, dict):
                outcome = loaded

        budget = _as_dict(search.get("budget"))
        live_contract_drift = self._live_search_contract_drift(search)
        return {
            "bridge": "BRIDGE4.2",
            "managed": True,
            "runtime_id": runtime_id,
            "runtime_status": status,
            "runtime_hash": package.get("runtime_hash"),
            "authorization_id": auth.get("authorization_id"),
            "verification_status": auth.get("verification_status"),
            "execution_kind": runtime.get("execution_kind"),
            "design_mode": runtime.get("design_mode"),
            "score_mode": search.get("score_mode") or "observer_niches",
            "search_mode": search.get("search_mode") or "cohort_target",
            "search_job_id": search.get("search_job_id"),
            "target_regime": search.get("target_regime"),
            "reference_rules": list(_as_list(search.get("reference_rules"))),
            "seed_rules": list(_as_list(search.get("seed_rules")) or _as_list(search.get("reference_rules"))),
            "experiment_plan_path": search.get("experiment_plan_path"),
            "command": list(_as_list(search.get("command"))),
            "budget": budget,
            "mutation_branch": _as_dict(runtime.get("mutation_branch")),
            "dispatch_id": dispatch_id or None,
            "pid": state.get("pid") or auth.get("pid") or dispatch.get("pid"),
            "log_path": state.get("log_path") or auth.get("log_path") or dispatch.get("log_path"),
            "outcome_path": state.get("outcome_path") or auth.get("outcome_path") or dispatch.get("outcome_path"),
            "execution_completed": bool(state.get("execution_completed") or status == SEARCH_COMPLETED_STATUS),
            "scientific_status": state.get("scientific_status") or outcome.get("scientific_status"),
            "scientific_reason": state.get("scientific_reason") or outcome.get("reason"),
            "live_contract_drift": live_contract_drift,
            "historical_monitoring_safe": bool(
                status in {SEARCH_STARTED_STATUS, SEARCH_COMPLETED_STATUS}
                and live_contract_drift
            ),
        }

    def open_authorized_search_launcher(
        self,
        runtime_id: str,
        *,
        requested_by: str,
    ) -> SearchLauncherOpenResult:
        runtime_id = str(runtime_id).strip()
        requested_by = str(requested_by).strip()
        if not runtime_id or not requested_by:
            raise CohortSearchExecutionError("runtime_id and requested_by are required")
        context = self.managed_launcher_context(runtime_id)
        launcher = (self.project_root / "Universe_Search" / "search_launcher.py").resolve()
        if not launcher.exists():
            raise CohortSearchExecutionError(f"Search Launcher missing: {launcher}")
        selection = runtime_python_selection(self.project_root)
        command = [*selection.command, str(launcher), "--managed-runtime", runtime_id]
        env = runtime_python_environment(self.project_root, selection=selection)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(self.project_root), env.get("PYTHONPATH", "")) if item
        )
        env["ARCHON_MANAGED_SEARCH_OPENED_BY"] = requested_by
        try:
            process = self.launcher_runner.start(
                command,
                cwd=str(self.project_root),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
        except Exception as exc:
            raise CohortSearchExecutionError(
                f"Search Launcher start failed: {type(exc).__name__}: {exc}"
            ) from exc
        return SearchLauncherOpenResult(
            runtime_id=runtime_id,
            opened=True,
            launcher_pid=int(process.pid),
            message=(
                f"{runtime_id}: Search Launcher v2 opened in ARCHON-managed mode • "
                f"authorization={context.get('authorization_id')} • Search not started by OL2"
            ),
        )

    def _live_search_contract_drift(self, search: dict[str, Any]) -> list[str]:
        """Report current-file drift without changing historical runtime validity.

        A VERIFIED runtime pins the files that were authorized at dispatch time.
        Those files may legitimately change after a Search has started or finished
        (POSTSEARCH1 is one such migration). Monitoring a historical execution must
        therefore stay available. Fresh start/resume paths still call the strict
        verifier and fail closed on any item returned here.
        """
        budget = _as_dict(search.get("budget"))
        entrypoint = _resolve(self.project_root, budget.get("entrypoint_path"))
        core = _resolve(self.project_root, budget.get("engine_config_path"))
        plan_path = _resolve(self.project_root, search.get("experiment_plan_path"))
        drift: list[str] = []
        if _file_sha256(entrypoint) != budget.get("entrypoint_sha256"):
            drift.append("SEARCH_ENTRYPOINT_DRIFT")
        if _file_sha256(core) != budget.get("engine_config_sha256"):
            drift.append("SEARCH_ENGINE_CONFIG_DRIFT")
        if _file_sha256(plan_path) != search.get("experiment_plan_sha256"):
            drift.append("EXPERIMENT_PLAN_DRIFT")
        return drift

    def _verify_immutable_search_contract(
        self,
        runtime_id: str,
        entry: dict[str, Any],
        package: dict[str, Any],
        *,
        require_ready: bool,
        revalidate_live_files: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        runtime = _as_dict(package.get("runtime"))
        if not runtime:
            raise CohortSearchExecutionError("runtime spec is missing")
        if runtime.get("design_integrity_bridge") != MATERIALIZATION_BRIDGE_ID:
            raise CohortSearchExecutionError("runtime is not a BRIDGE3 Search contract")
        if runtime.get("execution_kind") != "UNIVERSE_SEARCH":
            raise CohortSearchExecutionError("runtime execution_kind is not UNIVERSE_SEARCH")
        if _as_list(runtime.get("run_matrix")):
            raise CohortSearchExecutionError("UNIVERSE_SEARCH_MUST_NOT_USE_OBSERVER_QUEUE: run_matrix is not empty")
        if _canonical_hash(runtime) != str(package.get("runtime_hash") or ""):
            raise CohortSearchExecutionError("runtime package hash mismatch")
        if entry.get("runtime_hash") != package.get("runtime_hash"):
            raise CohortSearchExecutionError("runtime registry/package hash mismatch")
        if _as_list(package.get("unresolved_fields")):
            raise CohortSearchExecutionError("runtime has unresolved fields")
        if require_ready:
            failures = validate_cohort_search_runtime(package, project_root=self.project_root)
            if failures:
                raise CohortSearchExecutionError(
                    "Search runtime validation refused: " + ",".join(sorted(set(failures)))
                )
        search = _as_dict(runtime.get("search_execution"))
        command = [str(item) for item in _as_list(search.get("command"))]
        if not command:
            raise CohortSearchExecutionError("Search command is missing")
        budget = _as_dict(search.get("budget"))
        entrypoint = _resolve(self.project_root, budget.get("entrypoint_path"))
        if revalidate_live_files:
            live_drift = self._live_search_contract_drift(search)
            if live_drift:
                raise CohortSearchExecutionError(live_drift[0])
        try:
            _python_prefix, entrypoint_index = search_command_parts(command)
        except ValueError as exc:
            raise CohortSearchExecutionError("SEARCH_COMMAND_INTERPRETER_BOUNDARY_MISMATCH") from exc
        if Path(command[entrypoint_index]).resolve() != entrypoint:
            raise CohortSearchExecutionError("SEARCH_COMMAND_ENTRYPOINT_MISMATCH")
        return runtime, search

    def authorize_runtime(self, runtime_id: str, *, requested_by: str) -> RuntimeAuthorizationResult:
        runtime_id = str(runtime_id).strip()
        requested_by = str(requested_by).strip()
        if not runtime_id or not requested_by:
            raise CohortSearchExecutionError("runtime_id and requested_by are required")
        entry, package, package_path = self._runtime_entry(runtime_id)
        if entry.get("status") == SEARCH_AUTHORIZED_STATUS and entry.get("launch_authorized") is True:
            auth = self._verify_authorized(runtime_id)
            return RuntimeAuthorizationResult(
                runtime_id=runtime_id,
                status="ALREADY_AUTHORIZED",
                authorized=True,
                authorization_id=str(auth["authorization_id"]),
                verification_status="VERIFIED",
                message=f"{runtime_id} already has VERIFIED Search authorization {auth['authorization_id']}",
            )
        if entry.get("status") != SEARCH_READY_STATUS or entry.get("launch_authorized") is not False:
            raise CohortSearchExecutionError(f"runtime {runtime_id} is not {SEARCH_READY_STATUS}")
        _runtime, search = self._verify_immutable_search_contract(
            runtime_id, entry, package, require_ready=True
        )
        if self._active_authorization(runtime_id) is not None:
            raise CohortSearchExecutionError("runtime already has an active Search authorization")

        authorization_id = _token("OL2-SEARCH-AUTH", runtime_id)
        authorized_at = _now()
        package["search_launch_authorization"] = {
            "authorized": True,
            "authorization_id": authorization_id,
            "authorized_at": authorized_at,
            "authorized_by": requested_by,
            "confirmation": "AUTHORIZE_UNIVERSE_SEARCH_LAUNCH",
            "bridge": BRIDGE_ID,
        }
        package["status"] = SEARCH_AUTHORIZED_STATUS
        package["updated_at"] = authorized_at
        policy = dict(_as_dict(package.get("policy")))
        policy["launch_authorized"] = True
        policy["search_launch_authorized"] = True
        policy["observer_queue_handoff_forbidden"] = True
        policy["separate_search_start_required"] = True
        policy["execution_bridge"] = BRIDGE_ID
        package["policy"] = policy
        authorized_package_hash = _canonical_hash(package)

        receipt_path = self.experiments_root / "SearchLaunchAuthorizationReceipts" / f"{authorization_id}.json"
        receipt = {
            "schema": SEARCH_RECEIPT_SCHEMA,
            "status": "AUTHORIZED",
            "verification_status": "VERIFIED",
            "authorization_id": authorization_id,
            "runtime_id": runtime_id,
            "runtime_hash": package.get("runtime_hash"),
            "authorized_package_hash": authorized_package_hash,
            "command_hash": _canonical_hash(_as_list(search.get("command"))),
            "search_job_id": search.get("search_job_id"),
            "authorized_at": authorized_at,
            "authorized_by": requested_by,
            "execution_started": False,
            "execution_starting": False,
        }
        _atomic_json(package_path, package)
        _atomic_json(receipt_path, receipt)

        runtime_registry = self._runtime_registry()
        for row in _as_list(runtime_registry.get("packages")):
            if isinstance(row, dict) and str(row.get("runtime_id") or "") == runtime_id:
                row["status"] = SEARCH_AUTHORIZED_STATUS
                row["launch_authorized"] = True
                row["updated_at"] = authorized_at
        _refresh_runtime_registry_hash(runtime_registry)
        _atomic_json(self.runtime_registry_path, runtime_registry)

        auth_registry = self._authorization_registry()
        auth_registry["generated_at"] = authorized_at
        auth_registry.setdefault("authorizations", []).append({
            "authorization_id": authorization_id,
            "runtime_id": runtime_id,
            "runtime_hash": package.get("runtime_hash"),
            "receipt_path": str(receipt_path),
            "verification_status": "VERIFIED",
            "execution_started": False,
            "execution_starting": False,
            "lifecycle_status": "ACTIVE",
            "superseded": False,
            "authorized_at": authorized_at,
            "authorized_by": requested_by,
        })
        _refresh_auth_registry_hash(auth_registry)
        _atomic_json(self.authorization_registry_path, auth_registry)
        return RuntimeAuthorizationResult(
            runtime_id=runtime_id,
            status="AUTHORIZED",
            authorized=True,
            authorization_id=authorization_id,
            verification_status="VERIFIED",
            message=f"{runtime_id} Search launch authorized and VERIFIED • execution not started",
        )

    def _verify_authorized(self, runtime_id: str) -> dict[str, Any]:
        entry, package, _package_path = self._runtime_entry(runtime_id)
        if entry.get("status") != SEARCH_AUTHORIZED_STATUS or entry.get("launch_authorized") is not True:
            raise CohortSearchExecutionError("Search runtime registry is not launch-authorized")
        if package.get("status") != SEARCH_AUTHORIZED_STATUS:
            raise CohortSearchExecutionError("Search runtime package is not launch-authorized")
        _runtime, search = self._verify_immutable_search_contract(
            runtime_id, entry, package, require_ready=False
        )
        launch = _as_dict(package.get("search_launch_authorization"))
        if launch.get("authorized") is not True or not launch.get("authorization_id"):
            raise CohortSearchExecutionError("Search launch authorization is missing")
        auth = self._active_authorization(runtime_id)
        if auth is None:
            raise CohortSearchExecutionError("Search authorization registry has no active receipt")
        if auth.get("authorization_id") != launch.get("authorization_id"):
            raise CohortSearchExecutionError("Search authorization identity mismatch")
        if auth.get("runtime_hash") != package.get("runtime_hash"):
            raise CohortSearchExecutionError("Search authorization runtime hash mismatch")
        if auth.get("verification_status") != "VERIFIED":
            raise CohortSearchExecutionError("Search authorization is not VERIFIED")
        receipt_path = _resolve(self.project_root, auth.get("receipt_path"))
        receipt = _load(receipt_path, {})
        if _as_dict(receipt).get("authorization_id") != auth.get("authorization_id"):
            raise CohortSearchExecutionError("Search authorization receipt identity mismatch")
        if receipt.get("runtime_hash") != package.get("runtime_hash"):
            raise CohortSearchExecutionError("Search authorization receipt runtime hash mismatch")
        if receipt.get("authorized_package_hash") != _canonical_hash(package):
            raise CohortSearchExecutionError("Search authorized package changed after verification")
        if receipt.get("command_hash") != _canonical_hash(_as_list(search.get("command"))):
            raise CohortSearchExecutionError("Search authorized command changed after verification")
        return auth

    def resume_authorized_search(self, runtime_id: str, *, requested_by: str) -> SearchDispatchResult:
        """Resume one paused managed Search under the original VERIFIED contract.

        The only authorized command mutation is ``evolve`` -> ``resume``.  All
        scientific arguments remain pinned to the BRIDGE3 runtime.
        """
        runtime_id = str(runtime_id).strip()
        requested_by = str(requested_by).strip()
        if not runtime_id or not requested_by:
            raise CohortSearchExecutionError("runtime_id and requested_by are required")
        entry, package, package_path = self._runtime_entry(runtime_id)
        if entry.get("status") != SEARCH_STARTED_STATUS or package.get("status") != SEARCH_STARTED_STATUS:
            raise CohortSearchExecutionError("managed Search resume requires SEARCH_EXECUTION_STARTED")
        runtime, search = self._verify_immutable_search_contract(
            runtime_id, entry, package, require_ready=False
        )
        auth = self.authorization_for_runtime(runtime_id) or {}
        if auth.get("verification_status") != "VERIFIED" or auth.get("execution_started") is not True:
            raise CohortSearchExecutionError("managed Search resume requires consumed VERIFIED authorization")
        state = _as_dict(package.get("search_execution_state"))
        previous_dispatch_id = str(state.get("dispatch_id") or auth.get("dispatch_id") or "")
        if not previous_dispatch_id:
            raise CohortSearchExecutionError("managed Search resume has no prior dispatch")
        previous_dispatch_path = self.experiments_root / "SearchExecutionDispatches" / f"{previous_dispatch_id}.json"
        previous_dispatch = _load(previous_dispatch_path, {})
        if not isinstance(previous_dispatch, dict) or previous_dispatch.get("dispatch_id") != previous_dispatch_id:
            raise CohortSearchExecutionError("managed Search prior dispatch receipt is missing")
        previous_pid = int(previous_dispatch.get("pid") or state.get("pid") or 0)
        if pid_alive(previous_pid):
            raise CohortSearchExecutionError("managed Search is still running; pause/finish it before resume")
        old_outcome = previous_dispatch.get("outcome_path") or state.get("outcome_path")
        if old_outcome and _resolve(self.project_root, old_outcome).exists():
            raise CohortSearchExecutionError("managed Search already produced a final outcome; resume refused")

        checkpoint_path = self.project_root / "Results" / "Universe_Search" / "checkpoint_observer_niches.json"
        checkpoint = _load(checkpoint_path, {})
        identity = _as_dict(_as_dict(checkpoint).get("search_config_identity"))
        budget = _as_dict(search.get("budget"))
        completed_generation = int(_as_dict(checkpoint).get("completed_generation") or 0)
        generations = int(budget.get("generations") or 0)
        if not checkpoint or completed_generation >= generations:
            raise CohortSearchExecutionError("managed Search checkpoint is missing or already complete")
        expected_job = str(search.get("search_job_id") or "")
        expected_mode = str(search.get("search_mode") or "")
        if str(identity.get("job_id") or "") != expected_job:
            raise CohortSearchExecutionError("managed Search checkpoint job identity mismatch")
        if str(identity.get("search_mode") or "") != expected_mode:
            raise CohortSearchExecutionError("managed Search checkpoint mode identity mismatch")
        expected_seeds = [str(x).zfill(5) for x in _as_list(search.get("reference_rules"))]
        checkpoint_seeds = [str(x).zfill(5) for x in _as_list(identity.get("seed_rules"))]
        if expected_seeds and checkpoint_seeds != expected_seeds:
            raise CohortSearchExecutionError("managed Search checkpoint seed identity mismatch")

        pinned = [str(item) for item in _as_list(search.get("command"))]
        try:
            python_prefix, entrypoint_index = search_command_parts(pinned)
        except ValueError as exc:
            raise CohortSearchExecutionError("managed Search pinned command cannot be resumed safely") from exc
        run_index = entrypoint_index + 1
        if run_index >= len(pinned) or pinned[run_index] != "evolve":
            raise CohortSearchExecutionError("managed Search pinned command cannot be resumed safely")
        command = list(pinned)
        command[run_index] = "resume"
        authorization_id = str(auth.get("authorization_id") or "")
        dispatch_id = _token("OL2-SEARCH-DISPATCH", runtime_id)
        log_path = self.experiments_root / "SearchExecutionLogs" / f"{dispatch_id}.log"
        outcome_path = self.experiments_root / "SearchExecutionOutcomes" / f"{dispatch_id}.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        outcome_path.parent.mkdir(parents=True, exist_ok=True)
        started_at = _now()
        selection = runtime_python_selection(self.project_root)
        process_env = runtime_python_environment(self.project_root, selection=selection)
        process_env.update({
            "ARCHON_SEARCH_RUNTIME_ID": runtime_id,
            "ARCHON_SEARCH_DISPATCH_ID": dispatch_id,
            "ARCHON_SEARCH_AUTHORIZATION_ID": authorization_id,
            "ARCHON_SEARCH_OUTCOME_PATH": str(outcome_path),
        })
        try:
            preflight_search_dependencies(python_prefix, process_env)
        except SearchDependencyError as exc:
            raise CohortSearchExecutionError(str(exc)) from exc
        try:
            with log_path.open("a", encoding="utf-8") as log_handle:
                process = self.runner.start(
                    tuple(command),
                    cwd=str(self.project_root),
                    env=process_env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
            pid = int(process.pid)
        except Exception as exc:
            raise CohortSearchExecutionError(
                f"Universe Search resume failed: {type(exc).__name__}: {exc}"
            ) from exc

        previous_dispatch["status"] = "PAUSED"
        previous_dispatch["paused_at"] = started_at
        previous_dispatch["resumed_by_dispatch_id"] = dispatch_id
        _atomic_json(previous_dispatch_path, previous_dispatch)

        dispatch_path = self.experiments_root / "SearchExecutionDispatches" / f"{dispatch_id}.json"
        dispatch = {
            "schema": SEARCH_DISPATCH_SCHEMA,
            "status": "STARTED",
            "dispatch_id": dispatch_id,
            "continuation_of_dispatch_id": previous_dispatch_id,
            "runtime_id": runtime_id,
            "runtime_hash": package.get("runtime_hash"),
            "authorization_id": authorization_id,
            "search_job_id": search.get("search_job_id"),
            "command": command,
            "command_hash": _canonical_hash(command),
            "resume_from_checkpoint": str(checkpoint_path),
            "completed_generation_before_resume": completed_generation,
            "cwd": str(self.project_root),
            "pid": pid,
            "log_path": str(log_path),
            "outcome_path": str(outcome_path),
            "started_at": started_at,
            "started_by": requested_by,
            "observer_queue_handoff": False,
        }
        _atomic_json(dispatch_path, dispatch)

        auth_registry = self._authorization_registry()
        for row in _as_list(auth_registry.get("authorizations")):
            if isinstance(row, dict) and str(row.get("authorization_id") or "") == authorization_id:
                history = [str(x) for x in _as_list(row.get("dispatch_history")) if str(x)]
                if previous_dispatch_id not in history:
                    history.append(previous_dispatch_id)
                history.append(dispatch_id)
                row["dispatch_history"] = history
                row["dispatch_id"] = dispatch_id
                row["pid"] = pid
                row["log_path"] = str(log_path)
                row["outcome_path"] = str(outcome_path)
                row["execution_resumed_at"] = started_at
        _refresh_auth_registry_hash(auth_registry)
        _atomic_json(self.authorization_registry_path, auth_registry)

        state.update({
            "execution_started": True,
            "execution_completed": False,
            "dispatch_id": dispatch_id,
            "continuation_of_dispatch_id": previous_dispatch_id,
            "pid": pid,
            "log_path": str(log_path),
            "outcome_path": str(outcome_path),
            "started_at": started_at,
            "started_by": requested_by,
            "bridge": "BRIDGE4.2",
        })
        package["search_execution_state"] = state
        package["updated_at"] = started_at
        _atomic_json(package_path, package)

        return SearchDispatchResult(
            runtime_id=runtime_id,
            dispatch_id=dispatch_id,
            started=True,
            pid=pid,
            log_path=str(log_path),
            message=(
                f"{runtime_id}: Universe Search resumed from generation {completed_generation} • "
                f"pid={pid} • Observer Queue not used"
            ),
        )

    def start_authorized_search(self, runtime_id: str, *, requested_by: str) -> SearchDispatchResult:
        runtime_id = str(runtime_id).strip()
        requested_by = str(requested_by).strip()
        if not runtime_id or not requested_by:
            raise CohortSearchExecutionError("runtime_id and requested_by are required")
        auth = self._verify_authorized(runtime_id)
        if auth.get("execution_started") is True:
            raise CohortSearchExecutionError("Search execution already started for this authorization")
        if auth.get("execution_starting") is True:
            raise CohortSearchExecutionError("Search execution start is already in progress")
        entry, package, package_path = self._runtime_entry(runtime_id)
        _runtime, search = self._verify_immutable_search_contract(
            runtime_id, entry, package, require_ready=False
        )
        command = tuple(str(item) for item in _as_list(search.get("command")))
        if not command:
            raise CohortSearchExecutionError("Search command is empty")
        try:
            python_prefix, _entrypoint_index = search_command_parts(command)
        except ValueError as exc:
            raise CohortSearchExecutionError("Search command interpreter boundary is invalid") from exc

        # Claim the single-use start intent before touching the OS.  A second UI
        # click/process will then fail closed even if it races this one.
        auth_registry = self._authorization_registry()
        authorization_id = str(auth.get("authorization_id") or "")
        claimed = False
        for row in _as_list(auth_registry.get("authorizations")):
            if isinstance(row, dict) and str(row.get("authorization_id") or "") == authorization_id:
                if row.get("execution_started") is True or row.get("execution_starting") is True:
                    raise CohortSearchExecutionError("Search execution authorization has already been consumed")
                row["execution_starting"] = True
                row["execution_starting_at"] = _now()
                claimed = True
        if not claimed:
            raise CohortSearchExecutionError("active Search authorization disappeared before dispatch")
        _refresh_auth_registry_hash(auth_registry)
        _atomic_json(self.authorization_registry_path, auth_registry)

        dispatch_id = _token("OL2-SEARCH-DISPATCH", runtime_id)
        log_path = self.experiments_root / "SearchExecutionLogs" / f"{dispatch_id}.log"
        outcome_path = self.experiments_root / "SearchExecutionOutcomes" / f"{dispatch_id}.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        outcome_path.parent.mkdir(parents=True, exist_ok=True)
        started_at = _now()
        selection = runtime_python_selection(self.project_root)
        process_env = runtime_python_environment(self.project_root, selection=selection)
        process_env.update({
            "ARCHON_SEARCH_RUNTIME_ID": runtime_id,
            "ARCHON_SEARCH_DISPATCH_ID": dispatch_id,
            "ARCHON_SEARCH_AUTHORIZATION_ID": authorization_id,
            "ARCHON_SEARCH_OUTCOME_PATH": str(outcome_path),
        })
        try:
            preflight_search_dependencies(python_prefix, process_env)
        except SearchDependencyError as exc:
            rollback = self._authorization_registry()
            for row in _as_list(rollback.get("authorizations")):
                if isinstance(row, dict) and str(row.get("authorization_id") or "") == authorization_id:
                    row["execution_starting"] = False
                    row["execution_start_failed_at"] = _now()
                    row["execution_start_failure"] = "DEPENDENCY_ERROR"
            _refresh_auth_registry_hash(rollback)
            _atomic_json(self.authorization_registry_path, rollback)
            raise CohortSearchExecutionError(str(exc)) from exc
        try:
            with log_path.open("a", encoding="utf-8") as log_handle:
                process = self.runner.start(
                    command,
                    cwd=str(self.project_root),
                    env=process_env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
            pid = int(process.pid)
        except Exception as exc:
            rollback = self._authorization_registry()
            for row in _as_list(rollback.get("authorizations")):
                if isinstance(row, dict) and str(row.get("authorization_id") or "") == authorization_id:
                    row["execution_starting"] = False
                    row["execution_start_failed_at"] = _now()
                    row["execution_start_failure"] = f"{type(exc).__name__}: {exc}"
            _refresh_auth_registry_hash(rollback)
            _atomic_json(self.authorization_registry_path, rollback)
            raise CohortSearchExecutionError(f"Universe Search start failed: {type(exc).__name__}: {exc}") from exc

        dispatch_path = self.experiments_root / "SearchExecutionDispatches" / f"{dispatch_id}.json"
        dispatch = {
            "schema": SEARCH_DISPATCH_SCHEMA,
            "status": "STARTED",
            "dispatch_id": dispatch_id,
            "runtime_id": runtime_id,
            "runtime_hash": package.get("runtime_hash"),
            "authorization_id": authorization_id,
            "search_job_id": search.get("search_job_id"),
            "command": list(command),
            "command_hash": _canonical_hash(list(command)),
            "cwd": str(self.project_root),
            "pid": pid,
            "log_path": str(log_path),
            "outcome_path": str(outcome_path),
            "started_at": started_at,
            "started_by": requested_by,
            "observer_queue_handoff": False,
        }
        _atomic_json(dispatch_path, dispatch)

        auth_registry = self._authorization_registry()
        for row in _as_list(auth_registry.get("authorizations")):
            if isinstance(row, dict) and str(row.get("authorization_id") or "") == authorization_id:
                row["execution_starting"] = False
                row["execution_started"] = True
                row["execution_started_at"] = started_at
                row["dispatch_id"] = dispatch_id
                row["pid"] = pid
                row["log_path"] = str(log_path)
                row["outcome_path"] = str(outcome_path)
        _refresh_auth_registry_hash(auth_registry)
        _atomic_json(self.authorization_registry_path, auth_registry)

        package["status"] = SEARCH_STARTED_STATUS
        package["updated_at"] = started_at
        package["search_execution_state"] = {
            "execution_started": True,
            "dispatch_id": dispatch_id,
            "pid": pid,
            "log_path": str(log_path),
            "outcome_path": str(outcome_path),
            "started_at": started_at,
            "started_by": requested_by,
            "bridge": BRIDGE_ID,
        }
        _atomic_json(package_path, package)

        runtime_registry = self._runtime_registry()
        for row in _as_list(runtime_registry.get("packages")):
            if isinstance(row, dict) and str(row.get("runtime_id") or "") == runtime_id:
                row["status"] = SEARCH_STARTED_STATUS
                row["launch_authorized"] = True
                row["updated_at"] = started_at
        _refresh_runtime_registry_hash(runtime_registry)
        _atomic_json(self.runtime_registry_path, runtime_registry)

        return SearchDispatchResult(
            runtime_id=runtime_id,
            dispatch_id=dispatch_id,
            started=True,
            pid=pid,
            log_path=str(log_path),
            message=(
                f"{runtime_id}: Universe Search started • pid={pid} • "
                f"job={search.get('search_job_id')} • Observer Queue not used"
            ),
        )


__all__ = [
    "BRIDGE_ID",
    "CohortSearchExecutionError",
    "CohortSearchExecutionHandoff",
    "SEARCH_AUTHORIZED_STATUS",
    "SEARCH_STARTED_STATUS",
    "SEARCH_COMPLETED_STATUS",
]
