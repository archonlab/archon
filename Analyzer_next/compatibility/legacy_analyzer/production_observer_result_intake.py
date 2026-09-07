#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = "1.0"
TITLE = "ARCHON Stage 7.5 Production Observer Result Intake"


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
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def int_value(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except Exception:
        return None


def default_policy() -> Dict[str, Any]:
    return {
        "schema": "archon_production_observer_result_intake_policy_v1",
        "version": VERSION,
        "intake_enabled": False,
        "require_completed_launch": True,
        "require_exit_code_zero": True,
        "require_no_timeout": True,
        "require_execution_receipt": True,
        "require_execution_provenance": True,
        "require_run_summary": True,
        "require_samples_csv": True,
        "require_passport_json": True,
        "require_observation_log": True,
        "require_sqlite": True,
        "require_final_tick": True,
        "require_target_tick_reached": True,
        "require_sqlite_run_registration": True,
        "updated_at": now_iso(),
    }


def default_request() -> Dict[str, Any]:
    return {
        "schema": "archon_production_observer_result_intake_request_v1",
        "intake": False,
        "intake_id": None,
        "launch_result_path": None,
        "output_directory": None,
        "expected_launch_id": None,
        "expected_contract_hash": None,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_intake_id": None,
    }


def final_csv_tick(path: Path) -> Optional[int]:
    final_tick: Optional[int] = None
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as handle:
        for row in csv.DictReader(handle):
            tick = int_value(row.get("tick"))
            if tick is not None:
                final_tick = tick
    return final_tick


def newest(paths: List[Path]) -> Optional[Path]:
    existing = [path for path in paths if path.exists()]
    return max(
        existing,
        key=lambda path: path.stat().st_mtime_ns,
    ) if existing else None


def find_artifacts(output_dir: Path) -> Dict[str, Optional[Path]]:
    return {
        "execution_receipt": output_dir / "execution_receipt.json",
        "execution_provenance": output_dir / "execution_provenance.json",
        "run_summary": output_dir / "run_summary.json",
        "samples_csv": newest(list(output_dir.rglob("*_samples.csv"))),
        "events_csv": newest(list(output_dir.rglob("*_events.csv"))),
        "pressure_csv": newest(
            list(output_dir.rglob("*_pressure_timeline.csv"))
        ),
        "chronicle_csv": newest(list(output_dir.rglob("*_chronicle.csv"))),
        "passport_json": newest(list(output_dir.rglob("*_passport.json"))),
        "passport_md": newest(list(output_dir.rglob("*_passport.md"))),
        "observation_log": newest(list(output_dir.rglob("*_log.txt"))),
    }


def recursive_values(obj: Any, wanted: set[str]) -> List[Any]:
    values: List[Any] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key) in wanted:
                values.append(value)
            values.extend(recursive_values(value, wanted))
    elif isinstance(obj, list):
        for item in obj:
            values.extend(recursive_values(item, wanted))
    return values


def command_flag_value(
    command: Any,
    flag: str,
) -> Optional[str]:
    if not isinstance(command, list):
        return None
    for index, item in enumerate(command):
        if str(item) == flag and index + 1 < len(command):
            return str(command[index + 1])
    return None


def inspect_sqlite(path: Path, run_id: str) -> Dict[str, Any]:
    result = {
        "exists": path.exists(),
        "tables": [],
        "counts": {},
        "run_row": None,
        "run_id_found": False,
    }
    if not path.exists():
        return result

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        result["tables"] = tables
        for table in tables:
            safe = table.replace('"', '""')
            try:
                count = connection.execute(
                    f'SELECT COUNT(*) FROM "{safe}"'
                ).fetchone()[0]
            except sqlite3.Error:
                continue
            result["counts"][table] = int(count)

        if "runs" in tables:
            columns = [
                str(row[1])
                for row in connection.execute(
                    'PRAGMA table_info("runs")'
                )
            ]
            if "run_id" in columns:
                row = connection.execute(
                    'SELECT * FROM "runs" WHERE run_id = ? LIMIT 1',
                    (run_id,),
                ).fetchone()
                if row is not None:
                    result["run_row"] = dict(row)
                    result["run_id_found"] = True
    finally:
        connection.close()
    return result


def render_markdown(result: Dict[str, Any]) -> str:
    lines = [
        f"# {TITLE}",
        "",
        f"- Version: **{result.get('version')}**",
        f"- Status: **{result.get('status')}**",
        f"- Intake ID: `{result.get('intake_id') or '-'}`",
        f"- Launch ID: `{result.get('launch_id') or '-'}`",
        f"- Requested run ID: `{result.get('requested_run_id') or '-'}`",
        f"- Actual Observer run ID: `{result.get('observer_run_id') or '-'}`",
        f"- Final tick: `{result.get('final_tick')}`",
        f"- Target tick: `{result.get('target_tick')}`",
        "",
        "## Intake boundary",
        "",
        "- Process completion is not treated as scientific validity by itself.",
        "- Required artifacts and telemetry are checked independently.",
        "- Actual Observer run identity is linked back to Stage 6 identity.",
        "- Intake never executes Observer.",
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
    args = parser.parse_args()

    analysis = Path(args.analysis_root).resolve()
    experiments = analysis / "Experiments"
    experiments.mkdir(parents=True, exist_ok=True)

    request_path = (
        Path(args.request).resolve()
        if args.request
        else experiments / "production_observer_result_intake_request.json"
    )
    policy_path = experiments / "production_observer_result_intake_policy.json"
    result_path = experiments / "production_observer_result_intake_result.json"
    registry_path = experiments / "production_observer_result_intake_registry.json"
    markdown_path = experiments / "production_observer_result_intake.md"
    receipt_dir = experiments / "ProductionObserverResultIntakeReceipts"

    policy = load_json(policy_path, {})
    if not policy:
        policy = default_policy()
        atomic_write_json(policy_path, policy)

    request = load_json(request_path, {})
    if not request:
        request = default_request()
        atomic_write_json(request_path, request)

    if request.get("intake") is not True:
        result = {
            "schema": "archon_production_observer_result_intake_result_v1",
            "version": VERSION,
            "status": "NO_INTAKE_REQUEST",
            "intake_id": None,
            "issues": [],
        }
        atomic_write_json(result_path, result)
        markdown_path.write_text(render_markdown(result), encoding="utf-8")
        print("=" * 72)
        print(TITLE)
        print("=" * 72)
        print(f"Version:          {VERSION}")
        print("Status:           NO_INTAKE_REQUEST")
        print("Intake ID:        -")
        print(f"Policy:           {policy_path}")
        print(f"Request:          {request_path}")
        print(f"Result:           {result_path}")
        print(f"Registry:         {registry_path}")
        print(f"Markdown:         {markdown_path}")
        print("=" * 72)
        return 0

    issues: List[Dict[str, Any]] = []

    def issue(code: str, message: str, path: str, actual: Any = None) -> None:
        issues.append({
            "code": code,
            "message": message,
            "path": path,
            "actual": actual,
        })

    intake_id = text(request.get("intake_id"))
    if not intake_id:
        issue("INTAKE_ID_MISSING", "intake_id is required.", "$.request.intake_id")

    if policy.get("intake_enabled") is not True:
        issue(
            "INTAKE_DISABLED",
            "Production Observer result intake is disabled by policy.",
            "$.policy.intake_enabled",
            policy.get("intake_enabled"),
        )

    if request.get("confirmation") != "INTAKE_COMPLETED_OBSERVER_RESULT":
        issue(
            "CONFIRMATION_INVALID",
            "Intake confirmation is invalid.",
            "$.request.confirmation",
            request.get("confirmation"),
        )

    launch_result_value = text(request.get("launch_result_path"))
    launch_result_path = (
        Path(launch_result_value).expanduser() if launch_result_value else None
    )
    launch_result = load_json(launch_result_path, {}) if launch_result_path else {}
    if not launch_result:
        issue(
            "LAUNCH_RESULT_MISSING",
            "Launch result is missing or unreadable.",
            "$.request.launch_result_path",
            launch_result_value,
        )

    launch_id = text(launch_result.get("launch_id"))
    if (
        text(request.get("expected_launch_id"))
        and text(request.get("expected_launch_id")) != launch_id
    ):
        issue(
            "EXPECTED_LAUNCH_ID_MISMATCH",
            "Launch result belongs to another launch.",
            "$.request.expected_launch_id",
            request.get("expected_launch_id"),
        )

    contract_hash = text(launch_result.get("contract_hash"))
    if (
        text(request.get("expected_contract_hash"))
        and text(request.get("expected_contract_hash")) != contract_hash
    ):
        issue(
            "EXPECTED_CONTRACT_HASH_MISMATCH",
            "Launch result belongs to another contract.",
            "$.request.expected_contract_hash",
            request.get("expected_contract_hash"),
        )

    if (
        policy.get("require_completed_launch") is True
        and launch_result.get("status") != "COMPLETED"
    ):
        issue(
            "LAUNCH_NOT_COMPLETED",
            "Launch did not complete successfully.",
            "$.launch_result.status",
            launch_result.get("status"),
        )
    if (
        policy.get("require_exit_code_zero") is True
        and launch_result.get("exit_code") != 0
    ):
        issue(
            "EXIT_CODE_INVALID",
            "Observer process did not exit with code 0.",
            "$.launch_result.exit_code",
            launch_result.get("exit_code"),
        )
    if (
        policy.get("require_no_timeout") is True
        and launch_result.get("timed_out") is not False
    ):
        issue(
            "LAUNCH_TIMED_OUT",
            "Observer launch timed out.",
            "$.launch_result.timed_out",
            launch_result.get("timed_out"),
        )

    output_value = text(request.get("output_directory"))
    output_dir = Path(output_value).expanduser() if output_value else None
    if output_dir is None or not output_dir.is_dir():
        issue(
            "OUTPUT_DIRECTORY_MISSING",
            "Observer output directory is missing.",
            "$.request.output_directory",
            output_value,
        )
        output_dir = Path(".")

    artifacts = find_artifacts(output_dir)
    required_map = {
        "execution_receipt": policy.get("require_execution_receipt"),
        "execution_provenance": policy.get("require_execution_provenance"),
        "run_summary": policy.get("require_run_summary"),
        "samples_csv": policy.get("require_samples_csv"),
        "passport_json": policy.get("require_passport_json"),
        "observation_log": policy.get("require_observation_log"),
    }
    for key, required in required_map.items():
        path = artifacts.get(key)
        if required is True and (path is None or not path.is_file()):
            issue(
                "REQUIRED_ARTIFACT_MISSING",
                f"Required artifact is missing: {key}.",
                f"$.artifacts.{key}",
                str(path) if path else None,
            )

    execution_receipt = (
        load_json(artifacts["execution_receipt"], {})
        if artifacts.get("execution_receipt") else {}
    )
    provenance = (
        load_json(artifacts["execution_provenance"], {})
        if artifacts.get("execution_provenance") else {}
    )
    run_summary = (
        load_json(artifacts["run_summary"], {})
        if artifacts.get("run_summary") else {}
    )
    passport = (
        load_json(artifacts["passport_json"], {})
        if artifacts.get("passport_json") else {}
    )

    for source_name, source in (
        ("execution_receipt", execution_receipt),
        ("execution_provenance", provenance),
        ("run_summary", run_summary),
    ):
        source_launch_id = text(source.get("launch_id"))
        if launch_id and source_launch_id and source_launch_id != launch_id:
            issue(
                "LAUNCH_ID_CROSS_ARTIFACT_MISMATCH",
                f"{source_name} references another launch.",
                f"$.{source_name}.launch_id",
                source_launch_id,
            )

    identity = as_dict(provenance.get("identity"))
    sidecar = as_dict(provenance.get("provenance_sidecar"))
    requested_run_id = text(sidecar.get("requested_run_id")) or text(identity.get("run_id"))
    job_id = text(sidecar.get("job_id")) or text(identity.get("job_id"))
    task_id = text(sidecar.get("task_id")) or text(identity.get("task_id"))
    runtime_id = text(sidecar.get("runtime_id")) or text(identity.get("runtime_id"))

    samples_path = artifacts.get("samples_csv")
    final_tick = (
        final_csv_tick(samples_path)
        if samples_path and samples_path.is_file() else None
    )
    observer_run_id = (
        samples_path.name.removesuffix("_samples.csv") if samples_path else None
    )

    if policy.get("require_final_tick") is True and final_tick is None:
        issue(
            "FINAL_TICK_MISSING",
            "Final sample tick could not be resolved.",
            "$.artifacts.samples_csv",
            str(samples_path) if samples_path else None,
        )

    target_tick = None
    success_criteria = as_dict(run_summary.get("success_criteria"))
    for candidate in (
        success_criteria.get("target_tick"),
        success_criteria.get("max_ticks"),
        success_criteria.get("ticks"),
    ):
        parsed = int_value(candidate)
        if parsed is not None:
            target_tick = parsed
            break

    if target_tick is None:
        for candidate in recursive_values(
            passport,
            {"requested_ticks", "max_ticks", "target_tick"},
        ):
            parsed = int_value(candidate)
            if parsed is not None:
                target_tick = parsed
                break

    # The immutable executed command is the authoritative fallback for the
    # requested horizon. Stage 7.4 currently records it in provenance even
    # when run_summary.success_criteria does not expose max_ticks.
    if target_tick is None:
        target_tick = int_value(
            command_flag_value(
                provenance.get("command"),
                "--max-ticks",
            )
        )

    if (
        policy.get("require_target_tick_reached") is True
        and target_tick is None
    ):
        issue(
            "TARGET_TICK_UNRESOLVED",
            "Requested Observer horizon could not be resolved from summary, "
            "passport, or executed command.",
            "$.result.target_tick",
            None,
        )

    if (
        policy.get("require_target_tick_reached") is True
        and target_tick is not None
        and (final_tick is None or final_tick < target_tick)
    ):
        issue(
            "TARGET_TICK_NOT_REACHED",
            "Observer result ended before the requested horizon.",
            "$.result.final_tick",
            {"final_tick": final_tick, "target_tick": target_tick},
        )

    telemetry_target = as_dict(run_summary.get("telemetry_target"))
    telemetry_path_value = text(telemetry_target.get("database_path"))
    telemetry_path = (
        Path(telemetry_path_value).expanduser()
        if telemetry_path_value else None
    )

    sqlite_info: Dict[str, Any] = {}
    if policy.get("require_sqlite") is True:
        if telemetry_path is None or not telemetry_path.is_file():
            issue(
                "SQLITE_MISSING",
                "Telemetry SQLite database is missing.",
                "$.run_summary.telemetry_target.database_path",
                telemetry_path_value,
            )
        elif observer_run_id:
            sqlite_info = inspect_sqlite(telemetry_path, observer_run_id)
            if (
                policy.get("require_sqlite_run_registration") is True
                and sqlite_info.get("run_id_found") is not True
            ):
                issue(
                    "SQLITE_RUN_NOT_REGISTERED",
                    "Actual Observer run_id is not registered in SQLite.",
                    "$.sqlite.runs",
                    observer_run_id,
                )

    scientific_complete = not issues
    status = "ACCEPTED" if scientific_complete else "REJECTED"

    linkage = {
        "schema": "archon_observer_result_identity_linkage_v1",
        "version": VERSION,
        "intake_id": intake_id,
        "launch_id": launch_id,
        "contract_hash": contract_hash,
        "job_id": job_id,
        "task_id": task_id,
        "runtime_id": runtime_id,
        "requested_run_id": requested_run_id,
        "observer_run_id": observer_run_id,
        "final_tick": final_tick,
        "target_tick": target_tick,
        "linked_at": now_iso(),
    }
    linkage["linkage_hash"] = canonical_hash(linkage)

    result_core = {
        "schema": "archon_production_observer_result_intake_result_v1",
        "version": VERSION,
        "status": status,
        "scientific_complete": scientific_complete,
        "intake_id": intake_id,
        "launch_id": launch_id,
        "contract_hash": contract_hash,
        "job_id": job_id,
        "task_id": task_id,
        "runtime_id": runtime_id,
        "requested_run_id": requested_run_id,
        "observer_run_id": observer_run_id,
        "final_tick": final_tick,
        "target_tick": target_tick,
        "output_directory": str(output_dir),
        "telemetry_database": str(telemetry_path) if telemetry_path else None,
        "artifacts": {
            key: str(path) if path else None
            for key, path in artifacts.items()
        },
        "artifact_hashes": {
            key: file_sha256(path)
            for key, path in artifacts.items()
            if path is not None and path.is_file()
        },
        "sqlite": sqlite_info,
        "identity_linkage": linkage,
        "issues": issues,
        "intake_does_not_execute_observer": True,
        "accepted_at": now_iso() if scientific_complete else None,
        "rejected_at": now_iso() if not scientific_complete else None,
    }
    result = {**result_core, "intake_hash": canonical_hash(result_core)}
    atomic_write_json(result_path, result)

    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{intake_id}.json"
    receipt = {
        "schema": "archon_production_observer_result_intake_receipt_v1",
        "version": VERSION,
        "status": status,
        "intake_id": intake_id,
        "launch_id": launch_id,
        "contract_hash": contract_hash,
        "requested_run_id": requested_run_id,
        "observer_run_id": observer_run_id,
        "scientific_complete": scientific_complete,
        "intake_hash": result["intake_hash"],
        "result_path": str(result_path),
        "issued_at": now_iso(),
    }
    receipt["receipt_hash"] = canonical_hash(receipt)
    atomic_write_json(receipt_path, receipt)

    registry = load_json(registry_path, {})
    rows = [
        row for row in as_list(registry.get("intakes"))
        if isinstance(row, dict)
    ]
    rows.append({
        "intake_id": intake_id,
        "launch_id": launch_id,
        "contract_hash": contract_hash,
        "job_id": job_id,
        "task_id": task_id,
        "requested_run_id": requested_run_id,
        "observer_run_id": observer_run_id,
        "status": status,
        "scientific_complete": scientific_complete,
        "final_tick": final_tick,
        "target_tick": target_tick,
        "receipt_path": str(receipt_path),
        "result_path": str(result_path),
        "recorded_at": now_iso(),
    })
    unique = {
        str(row.get("intake_id")): row
        for row in rows if row.get("intake_id")
    }
    ordered = sorted(
        unique.values(),
        key=lambda row: str(row.get("intake_id")),
    )
    registry = {
        "schema": "archon_production_observer_result_intake_registry_v1",
        "version": VERSION,
        "updated_at": now_iso(),
        "intake_count": len(ordered),
        "accepted_count": sum(
            1 for row in ordered if row.get("status") == "ACCEPTED"
        ),
        "rejected_count": sum(
            1 for row in ordered if row.get("status") == "REJECTED"
        ),
        "intakes": ordered,
    }
    registry["content_hash"] = canonical_hash(ordered)
    atomic_write_json(registry_path, registry)

    atomic_write_json(request_path, {
        "schema": "archon_production_observer_result_intake_request_v1",
        "intake": False,
        "intake_id": None,
        "launch_result_path": None,
        "output_directory": None,
        "expected_launch_id": None,
        "expected_contract_hash": None,
        "requested_at": None,
        "requested_by": None,
        "confirmation": None,
        "last_consumed_intake_id": intake_id,
    })
    markdown_path.write_text(render_markdown(result), encoding="utf-8")

    print("=" * 72)
    print(TITLE)
    print("=" * 72)
    print(f"Version:             {VERSION}")
    print(f"Status:              {status}")
    print(f"Scientific complete: {scientific_complete}")
    print(f"Intake ID:           {intake_id or '-'}")
    print(f"Launch ID:           {launch_id or '-'}")
    print(f"Requested run ID:    {requested_run_id or '-'}")
    print(f"Observer run ID:     {observer_run_id or '-'}")
    print(f"Final tick:          {final_tick}")
    print(f"Target tick:         {target_tick}")
    print(f"Issues:              {len(issues)}")
    print(f"Result:              {result_path}")
    print(f"Receipt:             {receipt_path}")
    print(f"Registry:            {registry_path}")
    print(f"Markdown:            {markdown_path}")
    print("=" * 72)

    return 0 if status == "ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
