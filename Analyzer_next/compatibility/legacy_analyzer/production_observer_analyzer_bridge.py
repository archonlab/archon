#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Analyzer_next.compatibility.legacy_analyzer.research_cycle_record import (
    refresh_research_cycle_records,
)


VERSION = "1.2"
TITLE = "ARCHON Stage 7.7 Production Observer Analyzer Bridge"


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
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ) + "\n",
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


def log_tail(path: Optional[Path], max_lines: int = 40) -> Optional[str]:
    """Return a bounded diagnostic tail without making logs authoritative."""
    if path is None or not path.is_file():
        return None
    try:
        lines = path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError:
        return None
    return "\n".join(lines[-max_lines:])


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_production_observer_analyzer_bridge_policy_v1",
        "version": VERSION,
        "bridge_enabled": False,
        "require_accepted_intake": True,
        "require_scientific_complete": True,
        "require_completed_telemetry_status": True,
        "analysis_mode": "intake_and_scientific_refresh",
        "require_scientific_refresh": True,
        "require_scientific_refresh_receipt": True,
        "require_director_products": True,
        "copy_passport_into_results": True,
        "require_profile_record_for_run": True,
        "require_experiment_analysis": True,
        "allow_idempotent_reuse": True,
        "default_timeout_seconds": 1800,
        "maximum_timeout_seconds": 86400,
        "updated_at": now_iso(),
    }


def default_request() -> Dict[str, Any]:
    return {
        "schema": "archon_production_observer_analyzer_bridge_request_v1",
        "bridge": False,
        "bridge_id": None,
        "intake_result_path": None,
        "results_directory": None,
        "analyzer_entrypoint": None,
        "timeout_seconds": None,
        "force_profiles": False,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_bridge_id": None,
    }


def copy_verified(source: Path, destination: Path) -> Dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)

    source_hash = file_sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        destination_hash = file_sha256(destination)
        if destination_hash == source_hash:
            return {
                "source": str(source),
                "destination": str(destination),
                "sha256": source_hash,
                "status": "REUSED",
            }
        raise RuntimeError(
            f"Refusing to overwrite different artifact: {destination}"
        )

    temporary = destination.with_name(destination.name + ".tmp")
    shutil.copy2(source, temporary)
    if file_sha256(temporary) != source_hash:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f"Artifact copy hash mismatch: {source} -> {destination}"
        )
    temporary.replace(destination)
    return {
        "source": str(source),
        "destination": str(destination),
        "sha256": source_hash,
        "status": "COPIED",
    }


def ensure_telemetry_link(
    source: Path,
    destination: Path,
) -> Dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)

    destination.parent.mkdir(parents=True, exist_ok=True)
    resolved_source = source.resolve()

    if destination.is_symlink():
        current_target = destination.resolve()
        if current_target == resolved_source:
            return {
                "source": str(resolved_source),
                "destination": str(destination),
                "status": "REUSED_SYMLINK",
            }
        raise RuntimeError(
            f"Refusing to replace telemetry symlink pointing elsewhere: "
            f"{destination} -> {current_target}"
        )

    if destination.exists():
        try:
            same_file = os.path.samefile(source, destination)
        except OSError:
            same_file = False
        if same_file:
            return {
                "source": str(resolved_source),
                "destination": str(destination),
                "status": "REUSED_FILE",
            }
        raise RuntimeError(
            f"Refusing to overwrite existing telemetry database: {destination}"
        )

    temporary = destination.with_name(destination.name + ".tmp-link")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(resolved_source)
    temporary.replace(destination)

    if not destination.is_symlink() or destination.resolve() != resolved_source:
        destination.unlink(missing_ok=True)
        raise RuntimeError(
            f"Telemetry symlink verification failed: {destination}"
        )

    return {
        "source": str(resolved_source),
        "destination": str(destination),
        "status": "CREATED_SYMLINK",
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


def find_experiment(
    payload: Dict[str, Any],
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
        run_ids: List[str] = []
        for arm in as_dict(item.get("arms")).values():
            if not isinstance(arm, dict):
                continue
            run_ids.extend(
                str(value)
                for value in as_list(arm.get("run_ids"))
            )
        if observer_run_id in run_ids:
            return item
    return None


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{result.get('version')}**",
        f"- Status: **{result.get('status')}**",
        f"- Bridge ID: `{result.get('bridge_id') or '-'}`",
        f"- Observer run ID: `{result.get('observer_run_id') or '-'}`",
        f"- Experiment ID: `{result.get('experiment_id') or '-'}`",
        f"- Analyzer return code: `{result.get('analyzer_returncode')}`",
        f"- Intake return code: `{result.get('intake_returncode')}`",
        f"- Scientific refresh return code: "
        f"`{result.get('scientific_refresh_returncode')}`",
        "",
        "## Boundary",
        "",
        "- Only ACCEPTED and scientifically complete Observer results are analyzed.",
        "- The actual Observer run identity is preserved through telemetry and profiles.",
        "- Passport artifacts are copied into the canonical Analyzer workspace with hash verification.",
        "- Analyzer intake is followed by a complete incremental scientific refresh.",
        "- Completion requires a durable scientific refresh receipt and refreshed Research Director products.",
        "- The bridge invokes the existing Analyzer entrypoint rather than duplicating Analyzer logic.",
        "",
    ]
    if result.get("issues"):
        lines.extend(["## Issues", ""])
        for issue in result["issues"]:
            lines.append(
                f"- `{issue.get('code')}` at `{issue.get('path')}`: "
                f"{issue.get('message')}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--analysis-root", required=True)
    parser.add_argument("--request", default=None)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    analysis_root = Path(args.analysis_root).resolve()
    experiments_root = analysis_root / "Experiments"
    experiments_root.mkdir(parents=True, exist_ok=True)

    policy_path = (
        experiments_root
        / "production_observer_analyzer_bridge_policy.json"
    )
    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments_root
        / "production_observer_analyzer_bridge_request.json"
    )
    result_path = (
        experiments_root
        / "production_observer_analyzer_bridge_result.json"
    )
    registry_path = (
        experiments_root
        / "production_observer_analyzer_bridge_registry.json"
    )
    markdown_path = (
        experiments_root
        / "production_observer_analyzer_bridge.md"
    )
    receipt_dir = (
        experiments_root
        / "ProductionObserverAnalyzerBridgeReceipts"
    )
    logs_dir = (
        experiments_root
        / "ProductionObserverAnalyzerBridgeLogs"
    )

    policy = load_json(policy_path, {})
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    request = load_json(request_path, {})
    if not request:
        request = default_request()
        atomic_write_json(request_path, request)

    if request.get("bridge") is not True:
        result = {
            "schema": "archon_production_observer_analyzer_bridge_result_v1",
            "version": VERSION,
            "status": "NO_BRIDGE_REQUEST",
            "bridge_id": None,
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
        print(f"Version:       {VERSION}")
        print("Status:        NO_BRIDGE_REQUEST")
        print("Bridge ID:     -")
        print(f"Policy:        {policy_path}")
        print(f"Request:       {request_path}")
        print(f"Result:        {result_path}")
        print(f"Registry:      {registry_path}")
        print(f"Markdown:      {markdown_path}")
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

    bridge_id = text(request.get("bridge_id"))
    if not bridge_id:
        issue(
            "BRIDGE_ID_MISSING",
            "bridge_id is required.",
            "$.request.bridge_id",
        )

    if policy.get("bridge_enabled") is not True:
        issue(
            "BRIDGE_DISABLED",
            "Production Observer Analyzer bridge is disabled by policy.",
            "$.policy.bridge_enabled",
            policy.get("bridge_enabled"),
        )

    for key in (
        "require_scientific_refresh",
        "require_scientific_refresh_receipt",
        "require_director_products",
    ):
        if policy.get(key, True) is not True:
            issue(
                "SCIENTIFIC_REFRESH_POLICY_UNSAFE",
                (
                    "Production bridge cannot complete while the "
                    f"{key} safeguard is disabled."
                ),
                f"$.policy.{key}",
                policy.get(key),
            )

    if (
        request.get("confirmation")
        != "BRIDGE_ACCEPTED_OBSERVER_RESULT_TO_ANALYZER"
    ):
        issue(
            "CONFIRMATION_INVALID",
            "Bridge confirmation is invalid.",
            "$.request.confirmation",
            request.get("confirmation"),
        )

    timeout = request.get("timeout_seconds")
    if timeout is None:
        timeout = policy.get("default_timeout_seconds", 1800)
    try:
        timeout = int(timeout)
    except Exception:
        timeout = -1
    maximum_timeout = int(
        policy.get("maximum_timeout_seconds", 86400)
    )
    if timeout <= 0 or timeout > maximum_timeout:
        issue(
            "TIMEOUT_INVALID",
            "Analyzer timeout is outside policy.",
            "$.request.timeout_seconds",
            timeout,
        )

    intake_value = text(request.get("intake_result_path"))
    intake_path = (
        Path(intake_value).expanduser().resolve()
        if intake_value
        else None
    )
    intake = load_json(intake_path, {}) if intake_path else {}
    if not intake:
        issue(
            "INTAKE_RESULT_MISSING",
            "Observer intake result is missing or unreadable.",
            "$.request.intake_result_path",
            intake_value,
        )

    if (
        policy.get("require_accepted_intake") is True
        and intake.get("status") != "ACCEPTED"
    ):
        issue(
            "INTAKE_NOT_ACCEPTED",
            "Observer result intake is not ACCEPTED.",
            "$.intake.status",
            intake.get("status"),
        )

    if (
        policy.get("require_scientific_complete") is True
        and intake.get("scientific_complete") is not True
    ):
        issue(
            "INTAKE_NOT_SCIENTIFICALLY_COMPLETE",
            "Observer result is not scientifically complete.",
            "$.intake.scientific_complete",
            intake.get("scientific_complete"),
        )

    observer_run_id = text(intake.get("observer_run_id"))
    telemetry_value = text(intake.get("telemetry_database"))
    telemetry_path = (
        Path(telemetry_value).expanduser().resolve()
        if telemetry_value else None
    )
    identity_linkage = as_dict(intake.get("identity_linkage"))
    experiment_id = text(identity_linkage.get("experiment_id"))
    if not experiment_id:
        experiment_id = text(
            as_dict(
                as_dict(intake.get("sqlite")).get("run_row")
            ).get("metadata_json")
        )
        experiment_id = None

    if not observer_run_id:
        issue(
            "OBSERVER_RUN_ID_MISSING",
            "Actual Observer run_id is missing.",
            "$.intake.observer_run_id",
        )
    if telemetry_path is None or not telemetry_path.is_file():
        issue(
            "TELEMETRY_DATABASE_MISSING",
            "Telemetry SQLite database is missing.",
            "$.intake.telemetry_database",
            telemetry_value,
        )

    results_value = text(request.get("results_directory"))
    results_dir = (
        Path(results_value).expanduser().resolve()
        if results_value else None
    )
    if results_dir is None or not results_dir.is_dir():
        issue(
            "RESULTS_DIRECTORY_MISSING",
            "Canonical Analyzer results directory is missing.",
            "$.request.results_directory",
            results_value,
        )

    knowledge_value = text(request.get("knowledge_atlas_directory"))
    knowledge_atlas_dir = (
        Path(knowledge_value).expanduser().resolve()
        if knowledge_value else None
    )
    if (
        knowledge_atlas_dir is not None
        and not knowledge_atlas_dir.is_dir()
    ):
        issue(
            "KNOWLEDGE_ATLAS_DIRECTORY_MISSING",
            "Requested Knowledge Atlas directory is missing.",
            "$.request.knowledge_atlas_directory",
            knowledge_value,
        )

    world_value = text(request.get("world_atlas_directory"))
    world_atlas_dir = (
        Path(world_value).expanduser().resolve()
        if world_value else None
    )
    if world_atlas_dir is not None and not world_atlas_dir.is_dir():
        issue(
            "WORLD_ATLAS_DIRECTORY_MISSING",
            "Requested World Atlas directory is missing.",
            "$.request.world_atlas_directory",
            world_value,
        )

    entrypoint_value = text(request.get("analyzer_entrypoint"))
    analyzer_entrypoint = (
        Path(entrypoint_value).expanduser().resolve()
        if entrypoint_value
        else Path(__file__).resolve().parent / "analyze_results.py"
    )
    if not analyzer_entrypoint.is_file():
        issue(
            "ANALYZER_ENTRYPOINT_MISSING",
            "Analyzer entrypoint is missing.",
            "$.request.analyzer_entrypoint",
            str(analyzer_entrypoint),
        )

    intake_hash = text(intake.get("intake_hash"))
    registry = load_json(registry_path, {})
    previous = None
    for item in as_list(registry.get("bridges")):
        if not isinstance(item, dict):
            continue
        if (
            text(item.get("observer_run_id")) == observer_run_id
            and text(item.get("intake_hash")) == intake_hash
            and item.get("status") == "COMPLETED"
            and item.get("scientific_refresh_completed") is True
            and Path(
                str(item.get("scientific_refresh_receipt_path") or "")
            ).is_file()
        ):
            previous = item
            break

    if previous and policy.get("allow_idempotent_reuse") is True and not issues:
        result = {
            "schema": "archon_production_observer_analyzer_bridge_result_v1",
            "version": VERSION,
            "status": "REUSED",
            "bridge_id": bridge_id,
            "observer_run_id": observer_run_id,
            "experiment_id": previous.get("experiment_id"),
            "intake_hash": intake_hash,
            "reused_bridge_id": previous.get("bridge_id"),
            "receipt_path": previous.get("receipt_path"),
            "results_directory": previous.get("results_directory"),
            "scientific_refresh_completed": True,
            "scientific_refresh_receipt_path": previous.get(
                "scientific_refresh_receipt_path"
            ),
            "scientific_refresh_receipt_hash": previous.get(
                "scientific_refresh_receipt_hash"
            ),
            "director_products_verified": True,
            "issues": [],
            "bridge_does_not_duplicate_analyzer_logic": True,
            "completed_at": now_iso(),
        }
        atomic_write_json(result_path, result)
        atomic_write_json(
            request_path,
            {
                **default_request(),
                "last_consumed_bridge_id": bridge_id,
            },
        )
        markdown_path.write_text(
            render_markdown(result),
            encoding="utf-8",
        )
        print("=" * 72)
        print(TITLE)
        print("=" * 72)
        print("Status:          REUSED")
        print(f"Bridge ID:       {bridge_id}")
        print(f"Observer run ID: {observer_run_id}")
        print(f"Previous bridge: {previous.get('bridge_id')}")
        print(f"Result:          {result_path}")
        print("=" * 72)
        return 0

    copied_artifacts: List[Dict[str, Any]] = []
    telemetry_link: Optional[Dict[str, Any]] = None
    analyzer_returncode: Optional[int] = None
    analyzer_log_path: Optional[Path] = None
    analyzer_command: List[str] = []
    intake_returncode: Optional[int] = None
    intake_log_path: Optional[Path] = None
    intake_command: List[str] = []
    scientific_refresh_returncode: Optional[int] = None
    scientific_refresh_log_path: Optional[Path] = None
    scientific_refresh_command: List[str] = []
    scientific_refresh_receipt_path: Optional[Path] = None
    scientific_refresh_receipt: Dict[str, Any] = {}
    profile_record: Optional[Dict[str, Any]] = None
    experiment_record: Optional[Dict[str, Any]] = None
    telemetry_manifest: Dict[str, Any] = {}

    if not issues:
        artifacts = as_dict(intake.get("artifacts"))
        observation_logs = results_dir / "observation_logs"
        observation_logs.mkdir(parents=True, exist_ok=True)

        try:
            telemetry_link = ensure_telemetry_link(
                telemetry_path,
                observation_logs / "telemetry.sqlite",
            )
        except Exception as exc:
            issue(
                "TELEMETRY_LINK_FAILED",
                str(exc),
                "$.analyzer.telemetry_link",
                {
                    "source": str(telemetry_path),
                    "destination": str(
                        observation_logs / "telemetry.sqlite"
                    ),
                },
            )

        if policy.get("copy_passport_into_results") is True:
            for role in (
                "passport_json",
                "passport_md",
                "observation_log",
            ):
                source_value = text(artifacts.get(role))
                if not source_value:
                    if role == "passport_json":
                        issue(
                            "PASSPORT_JSON_PATH_MISSING",
                            "Accepted intake does not expose passport_json.",
                            f"$.intake.artifacts.{role}",
                        )
                    continue
                source = Path(source_value).expanduser().resolve()
                destination = observation_logs / source.name
                try:
                    copied_artifacts.append(
                        copy_verified(source, destination)
                    )
                except Exception as exc:
                    issue(
                        "ARTIFACT_COPY_FAILED",
                        str(exc),
                        f"$.intake.artifacts.{role}",
                        source_value,
                    )

    if not issues:
        intake_command = [
            args.python,
            str(analyzer_entrypoint),
            str(results_dir),
            "--mode",
            "intake",
            "--telemetry-db",
            str(telemetry_path),
            "--telemetry-run-id",
            str(observer_run_id),
            "--telemetry-status",
            "completed",
        ]
        if request.get("force_profiles") is True:
            intake_command.extend([
                "--force-stage",
                "profiles",
            ])

        logs_dir.mkdir(parents=True, exist_ok=True)
        intake_log_path = logs_dir / f"{bridge_id}.intake.log"
        environment = os.environ.copy()
        # The bridge is an ARCHON production stage. Its cwd and import root must
        # therefore remain anchored to ARCHON even when a contract test supplies
        # an Analyzer-compatible entrypoint from a temporary directory.
        project_root = Path(__file__).resolve().parent.parent
        environment["PYTHONPATH"] = os.pathsep.join(
            part
            for part in (
                str(project_root),
                environment.get("PYTHONPATH", ""),
            )
            if part
        )
        # Keep the Analyzer invocation isolated and make its canonical path
        # resolver point at the bridge-selected workspaces.
        environment["ARCHON_RESULTS_DIR"] = str(results_dir)
        environment["ARCHON_ANALYSIS_DIR"] = str(analysis_root)
        if knowledge_atlas_dir is not None:
            environment["ARCHON_KNOWLEDGE_ATLAS_DIR"] = str(
                knowledge_atlas_dir
            )
        if world_atlas_dir is not None:
            environment["ARCHON_WORLD_ATLAS_DIR"] = str(
                world_atlas_dir
            )

        try:
            completed = subprocess.run(
                intake_command,
                cwd=str(project_root),
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            intake_returncode = completed.returncode
            intake_log_path.write_text(
                completed.stdout,
                encoding="utf-8",
            )
            if intake_returncode != 0:
                issue(
                    "ANALYZER_INTAKE_FAILED",
                    "Analyzer intake returned a non-zero exit code.",
                    "$.analyzer.intake.returncode",
                    intake_returncode,
                )
        except subprocess.TimeoutExpired as exc:
            intake_returncode = None
            intake_log_path.write_text(
                (exc.stdout or "")
                + "\n[bridge] Analyzer intake timeout\n",
                encoding="utf-8",
            )
            issue(
                "ANALYZER_INTAKE_TIMEOUT",
                "Analyzer intake exceeded the configured timeout.",
                "$.analyzer.intake.timeout_seconds",
                timeout,
            )
        except Exception as exc:
            issue(
                "ANALYZER_INTAKE_ERROR",
                str(exc),
                "$.analyzer.intake",
            )

    if (
        not issues
        and policy.get("require_scientific_refresh", True) is True
    ):
        scientific_refresh_command = [
            args.python,
            str(analyzer_entrypoint),
            str(results_dir),
            "--mode",
            "scientific-refresh",
            "--scientific-refresh-id",
            str(bridge_id),
            "--telemetry-run-id",
            str(observer_run_id),
        ]
        scientific_refresh_log_path = (
            logs_dir / f"{bridge_id}.scientific-refresh.log"
        )
        try:
            completed = subprocess.run(
                scientific_refresh_command,
                cwd=str(project_root),
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            scientific_refresh_returncode = completed.returncode
            scientific_refresh_log_path.write_text(
                completed.stdout,
                encoding="utf-8",
            )
            if scientific_refresh_returncode != 0:
                issue(
                    "SCIENTIFIC_REFRESH_FAILED",
                    "Analyzer scientific refresh returned a non-zero exit code.",
                    "$.analyzer.scientific_refresh.returncode",
                    scientific_refresh_returncode,
                )
        except subprocess.TimeoutExpired as exc:
            scientific_refresh_log_path.write_text(
                (exc.stdout or "")
                + "\n[bridge] Scientific refresh timeout\n",
                encoding="utf-8",
            )
            issue(
                "SCIENTIFIC_REFRESH_TIMEOUT",
                "Analyzer scientific refresh exceeded the configured timeout.",
                "$.analyzer.scientific_refresh.timeout_seconds",
                timeout,
            )
        except Exception as exc:
            issue(
                "SCIENTIFIC_REFRESH_ERROR",
                str(exc),
                "$.analyzer.scientific_refresh",
            )

    analyzer_command = intake_command
    analyzer_returncode = (
        scientific_refresh_returncode
        if scientific_refresh_command
        else intake_returncode
    )
    analyzer_log_path = (
        scientific_refresh_log_path
        if scientific_refresh_command
        else intake_log_path
    )

    if not issues and policy.get(
        "require_scientific_refresh_receipt",
        True,
    ) is True:
        scientific_refresh_receipt_path = (
            analysis_root
            / "Experiments"
            / "ScientificRefreshReceipts"
            / f"{bridge_id}.json"
        )
        scientific_refresh_receipt = load_json(
            scientific_refresh_receipt_path,
            {},
        )
        if not scientific_refresh_receipt:
            issue(
                "SCIENTIFIC_REFRESH_RECEIPT_MISSING",
                "Scientific refresh did not issue a durable receipt.",
                "$.analyzer.scientific_refresh.receipt",
                str(scientific_refresh_receipt_path),
            )
        elif scientific_refresh_receipt.get("status") != "COMPLETED":
            issue(
                "SCIENTIFIC_REFRESH_RECEIPT_FAILED",
                "Scientific refresh receipt is not COMPLETED.",
                "$.analyzer.scientific_refresh.receipt.status",
                scientific_refresh_receipt.get("status"),
            )
        elif observer_run_id not in {
            text(value)
            for value in as_list(
                scientific_refresh_receipt.get("observer_run_ids")
            )
        }:
            issue(
                "SCIENTIFIC_REFRESH_RUN_ID_MISSING",
                "Scientific refresh receipt does not contain the Observer run.",
                "$.analyzer.scientific_refresh.receipt.observer_run_ids",
                scientific_refresh_receipt.get("observer_run_ids"),
            )
        elif (
            policy.get("require_director_products", True) is True
            and scientific_refresh_receipt.get(
                "director_products_verified"
            ) is not True
        ):
            issue(
                "DIRECTOR_PRODUCTS_NOT_VERIFIED",
                "Scientific refresh did not verify Research Director products.",
                "$.analyzer.scientific_refresh.receipt.director_products_verified",
                scientific_refresh_receipt.get(
                    "director_products_verified"
                ),
            )

    if not issues:
        telemetry_manifest_path = (
            results_dir
            / "observation_logs"
            / "telemetry_bridge_manifest.json"
        )
        telemetry_manifest = load_json(
            telemetry_manifest_path,
            {},
        )
        manifest_run_ids = {
            text(item.get("run_id"))
            for item in as_list(telemetry_manifest.get("runs"))
            if isinstance(item, dict)
        }
        if observer_run_id not in manifest_run_ids:
            issue(
                "TELEMETRY_RUN_NOT_MATERIALIZED",
                "Telemetry bridge manifest does not contain the Observer run.",
                "$.telemetry_bridge_manifest.runs",
                sorted(value for value in manifest_run_ids if value),
            )

        profiles_path = results_dir / "observer_profiles_v31.json"
        profiles_payload = load_json(profiles_path, {})
        profile_record = find_profile_record(
            profiles_payload,
            str(observer_run_id),
        )
        if (
            policy.get("require_profile_record_for_run") is True
            and profile_record is None
        ):
            issue(
                "PROFILE_RECORD_MISSING",
                "Analyzer did not produce a profile record for the actual run.",
                "$.observer_profiles_v31.profile_records",
                observer_run_id,
            )

        experiment_analysis_path = (
            analysis_root
            / "Experiments"
            / "experiment_analysis.json"
        )
        experiment_payload = load_json(
            experiment_analysis_path,
            {},
        )

        if not experiment_id:
            sqlite_row = as_dict(
                as_dict(intake.get("sqlite")).get("run_row")
            )
            metadata_raw = sqlite_row.get("metadata_json")
            try:
                metadata = (
                    json.loads(metadata_raw)
                    if isinstance(metadata_raw, str)
                    else as_dict(metadata_raw)
                )
            except Exception:
                metadata = {}
            experiment_id = text(
                as_dict(
                    metadata.get("experimental_context")
                ).get("experiment_id")
            )

        experiment_record = find_experiment(
            experiment_payload,
            experiment_id,
            str(observer_run_id),
        )
        if (
            policy.get("require_experiment_analysis") is True
            and experiment_record is None
        ):
            issue(
                "EXPERIMENT_ANALYSIS_MISSING",
                "Analyzer did not include the run's experiment.",
                "$.experiment_analysis.experiments",
                {
                    "experiment_id": experiment_id,
                    "observer_run_id": observer_run_id,
                },
            )

    status = "COMPLETED" if not issues else "FAILED"

    result_core = {
        "schema": "archon_production_observer_analyzer_bridge_result_v1",
        "version": VERSION,
        "status": status,
        "bridge_id": bridge_id,
        "intake_result_path": str(intake_path) if intake_path else None,
        "intake_hash": intake_hash,
        "observer_run_id": observer_run_id,
        "experiment_id": experiment_id,
        "job_id": identity_linkage.get("job_id"),
        "task_id": identity_linkage.get("task_id"),
        "results_directory": (
            str(results_dir) if results_dir else None
        ),
        "knowledge_atlas_directory": (
            str(knowledge_atlas_dir)
            if knowledge_atlas_dir else None
        ),
        "world_atlas_directory": (
            str(world_atlas_dir)
            if world_atlas_dir else None
        ),
        "runtime_id": identity_linkage.get("runtime_id"),
        "requested_run_id": identity_linkage.get("requested_run_id"),
        "telemetry_database": (
            str(telemetry_path) if telemetry_path else None
        ),
        "results_directory": (
            str(results_dir) if results_dir else None
        ),
        "analyzer_entrypoint": str(analyzer_entrypoint),
        "analyzer_command": analyzer_command,
        "analyzer_returncode": analyzer_returncode,
        "analyzer_log_path": (
            str(analyzer_log_path)
            if analyzer_log_path else None
        ),
        "intake_command": intake_command,
        "intake_returncode": intake_returncode,
        "intake_log_path": (
            str(intake_log_path) if intake_log_path else None
        ),
        "scientific_refresh_command": scientific_refresh_command,
        "scientific_refresh_returncode": scientific_refresh_returncode,
        "scientific_refresh_log_path": (
            str(scientific_refresh_log_path)
            if scientific_refresh_log_path else None
        ),
        "intake_log_tail": (
            log_tail(intake_log_path)
            if intake_returncode not in (None, 0)
            else None
        ),
        "scientific_refresh_log_tail": (
            log_tail(scientific_refresh_log_path)
            if scientific_refresh_returncode not in (None, 0)
            else None
        ),
        "scientific_refresh_receipt_path": (
            str(scientific_refresh_receipt_path)
            if scientific_refresh_receipt_path else None
        ),
        "scientific_refresh_receipt_hash": (
            scientific_refresh_receipt.get("receipt_hash")
        ),
        "scientific_refresh_completed": (
            scientific_refresh_receipt.get("status") == "COMPLETED"
        ),
        "director_products_verified": (
            scientific_refresh_receipt.get(
                "director_products_verified"
            ) is True
        ),
        "copied_artifacts": copied_artifacts,
        "telemetry_link": telemetry_link,
        "telemetry_manifest": telemetry_manifest,
        "profile_record_found": profile_record is not None,
        "profile_record": profile_record,
        "experiment_analysis_found": experiment_record is not None,
        "experiment_analysis": experiment_record,
        "issues": issues,
        "bridge_does_not_duplicate_analyzer_logic": True,
        "completed_at": now_iso() if not issues else None,
        "failed_at": now_iso() if issues else None,
    }
    result = {
        **result_core,
        "bridge_hash": canonical_hash(result_core),
    }
    atomic_write_json(result_path, result)

    receipt_path: Optional[Path] = None
    if status == "COMPLETED":
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / f"{bridge_id}.json"
        receipt = {
            "schema": (
                "archon_production_observer_analyzer_bridge_receipt_v1"
            ),
            "version": VERSION,
            "status": "COMPLETED",
            "bridge_id": bridge_id,
            "intake_hash": intake_hash,
            "observer_run_id": observer_run_id,
            "experiment_id": experiment_id,
            "profile_record_found": True,
            "experiment_analysis_found": True,
            "scientific_refresh_completed": True,
            "scientific_refresh_receipt_path": str(
                scientific_refresh_receipt_path
            ),
            "scientific_refresh_receipt_hash": (
                scientific_refresh_receipt.get("receipt_hash")
            ),
            "director_products_verified": True,
            "bridge_hash": result["bridge_hash"],
            "result_path": str(result_path),
            "issued_at": now_iso(),
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        atomic_write_json(receipt_path, receipt)

    rows = [
        item
        for item in as_list(registry.get("bridges"))
        if isinstance(item, dict)
    ]
    rows.append({
        "bridge_id": bridge_id,
        "status": status,
        "intake_hash": intake_hash,
        "observer_run_id": observer_run_id,
        "experiment_id": experiment_id,
        "job_id": identity_linkage.get("job_id"),
        "task_id": identity_linkage.get("task_id"),
        "analyzer_returncode": analyzer_returncode,
        "intake_returncode": intake_returncode,
        "scientific_refresh_returncode": scientific_refresh_returncode,
        "scientific_refresh_completed": (
            scientific_refresh_receipt.get("status") == "COMPLETED"
        ),
        "scientific_refresh_receipt_path": (
            str(scientific_refresh_receipt_path)
            if scientific_refresh_receipt_path else None
        ),
        "receipt_path": str(receipt_path) if receipt_path else None,
        "result_path": str(result_path),
        "recorded_at": now_iso(),
    })
    unique = {
        str(item.get("bridge_id")): item
        for item in rows
        if item.get("bridge_id")
    }
    ordered = sorted(
        unique.values(),
        key=lambda item: str(item.get("bridge_id")),
    )
    registry_payload = {
        "schema": (
            "archon_production_observer_analyzer_bridge_registry_v1"
        ),
        "version": VERSION,
        "updated_at": now_iso(),
        "bridge_count": len(ordered),
        "completed_count": sum(
            item.get("status") == "COMPLETED"
            for item in ordered
        ),
        "failed_count": sum(
            item.get("status") == "FAILED"
            for item in ordered
        ),
        "bridges": ordered,
    }
    registry_payload["content_hash"] = canonical_hash(ordered)
    atomic_write_json(registry_path, registry_payload)

    atomic_write_json(
        request_path,
        {
            **default_request(),
            "last_consumed_bridge_id": bridge_id,
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
    print(f"Version:             {VERSION}")
    print(f"Status:              {status}")
    print(f"Bridge ID:           {bridge_id or '-'}")
    print(f"Observer run ID:     {observer_run_id or '-'}")
    print(f"Experiment ID:       {experiment_id or '-'}")
    print(f"Analyzer returncode: {analyzer_returncode}")
    print(f"Intake returncode:   {intake_returncode}")
    print(
        f"Refresh returncode:  {scientific_refresh_returncode}"
    )
    print(
        f"Scientific refresh:  "
        f"{scientific_refresh_receipt.get('status') or '-'}"
    )
    print(f"Profile found:       {profile_record is not None}")
    print(f"Experiment found:    {experiment_record is not None}")
    print(f"Issues:              {len(issues)}")
    print(f"Result:              {result_path}")
    print(
        f"Receipt:             "
        f"{str(receipt_path) if receipt_path else '-'}"
    )
    print(f"Registry:            {registry_path}")
    print(f"Markdown:            {markdown_path}")
    if status == "FAILED":
        intake_tail = result.get("intake_log_tail")
        refresh_tail = result.get("scientific_refresh_log_tail")
        if intake_tail:
            print("-" * 72)
            print("Analyzer intake log tail:")
            print(intake_tail)
        if refresh_tail:
            print("-" * 72)
            print("Scientific refresh log tail:")
            print(refresh_tail)
    print("=" * 72)

    return 0 if status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
