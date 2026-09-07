"""Native SQLite initialization and integrity inspection for Stage 2M."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping

from .connection import connect_database
from .schema_catalog import TELEMETRY_SCHEMA_CONTRACT
from .schema_manager import initialize_database


class NativeMigrationAuditDatabase:
    def __init__(self, *, clock: Callable[[], str]) -> None:
        self.clock = clock

    def resolve_path(self, value: str) -> str:
        return str(Path(value).expanduser().resolve())

    def exists(self, database_path: str) -> bool:
        return Path(database_path).exists()

    def initialize(self, database_path: str) -> None:
        initialize_database(database_path, clock=self.clock)

    def inspect(self, database_path: str) -> Mapping[str, Any]:
        return inspect_database(database_path)


def inspect_database(database_path: str) -> dict[str, Any]:
    path = Path(database_path).expanduser().resolve()
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "passed": False,
            "quick_check": ["database does not exist"],
            "run_ids": [],
            "run_count": 0,
        }

    connection = connect_database(path, timeout=60.0, read_only=True)
    result: dict[str, Any] = {"path": str(path), "exists": True}
    issues: list[dict[str, Any]] = []
    try:
        try:
            _validate_schema(connection)
            result["schema_valid"] = True
        except Exception as exc:
            result["schema_valid"] = False
            issues.append({"kind": "schema", "detail": str(exc)})

        quick = [str(row[0]) for row in connection.execute("PRAGMA quick_check")]
        result["quick_check"] = quick
        if quick != ["ok"]:
            issues.append({"kind": "quick_check", "detail": quick})

        foreign_keys = [
            dict(row) for row in connection.execute("PRAGMA foreign_key_check")
        ]
        result["foreign_key_violations"] = foreign_keys[:100]
        result["foreign_key_violation_count"] = len(foreign_keys)
        if foreign_keys:
            issues.append({"kind": "foreign_keys", "count": len(foreign_keys)})

        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {"runs", "samples", "events", "chronicle", "pressure"}
        if not required.issubset(tables):
            missing = sorted(required - tables)
            issues.append({"kind": "missing_tables", "tables": missing})
            result.update({
                "run_ids": [],
                "run_count": 0,
                "issues": issues,
                "passed": False,
            })
            return result

        run_rows = connection.execute(
            """
            SELECT
                r.*,
                (SELECT COUNT(*) FROM samples s
                 WHERE s.run_id=r.run_id) AS samples_actual,
                (SELECT COUNT(*) FROM events e
                 WHERE e.run_id=r.run_id) AS events_actual,
                (SELECT COUNT(*) FROM chronicle c
                 WHERE c.run_id=r.run_id) AS chronicle_actual,
                (SELECT COUNT(*) FROM pressure p
                 WHERE p.run_id=r.run_id) AS pressure_actual,
                MAX(
                    COALESCE((SELECT MAX(tick) FROM samples s
                              WHERE s.run_id=r.run_id), -1),
                    COALESCE((SELECT MAX(tick) FROM events e
                              WHERE e.run_id=r.run_id), -1),
                    COALESCE((SELECT MAX(tick) FROM chronicle c
                              WHERE c.run_id=r.run_id), -1),
                    COALESCE((SELECT MAX(tick) FROM pressure p
                              WHERE p.run_id=r.run_id), -1)
                ) AS max_tick_actual
            FROM runs r
            ORDER BY r.run_id
            """
        ).fetchall()
        result["run_ids"] = [str(row["run_id"]) for row in run_rows]
        result["run_count"] = len(run_rows)

        counter_mismatches: list[dict[str, Any]] = []
        final_tick_mismatches: list[dict[str, Any]] = []
        for row in run_rows:
            for channel in ("samples", "events", "chronicle", "pressure"):
                stored = int(row[f"{channel}_count"])
                actual = int(row[f"{channel}_actual"])
                if stored != actual:
                    counter_mismatches.append({
                        "run_id": row["run_id"],
                        "channel": channel,
                        "stored": stored,
                        "actual": actual,
                    })
            actual_tick = int(row["max_tick_actual"])
            stored_tick = row["final_tick"]
            if actual_tick >= 0 and (
                stored_tick is None or int(stored_tick) != actual_tick
            ):
                final_tick_mismatches.append({
                    "run_id": row["run_id"],
                    "stored": stored_tick,
                    "actual": actual_tick,
                })
        result["counter_mismatches"] = counter_mismatches
        result["final_tick_mismatches"] = final_tick_mismatches
        if counter_mismatches:
            issues.append({"kind": "run_counters", "count": len(counter_mismatches)})
        if final_tick_mismatches:
            issues.append({"kind": "final_tick", "count": len(final_tick_mismatches)})

        orphan_counts: dict[str, int] = {}
        invalid_json: dict[str, int] = {}
        for table in ("samples", "events", "chronicle", "pressure"):
            orphan_counts[table] = int(connection.execute(
                f"""
                SELECT COUNT(*)
                FROM {table} child
                LEFT JOIN runs r ON r.run_id=child.run_id
                WHERE r.run_id IS NULL
                """
            ).fetchone()[0])
            invalid_json[table] = int(connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE NOT json_valid(payload_json)"
            ).fetchone()[0])
        result["orphan_rows"] = orphan_counts
        result["invalid_payload_json"] = invalid_json
        if any(orphan_counts.values()):
            issues.append({"kind": "orphan_rows", "counts": orphan_counts})
        if any(invalid_json.values()):
            issues.append({"kind": "invalid_payload_json", "counts": invalid_json})
    finally:
        connection.close()

    result["issues"] = issues
    result["passed"] = not issues
    return result


def _validate_schema(connection: sqlite3.Connection) -> None:
    contract = TELEMETRY_SCHEMA_CONTRACT
    tables = {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing = set(contract.required_tables) - tables
    if missing:
        raise RuntimeError(f"Missing required tables: {sorted(missing)}")

    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
    ).fetchone()
    version = int(row["version"])
    if version != contract.expected_version:
        raise RuntimeError(
            f"Schema version {version} does not match expected "
            f"{contract.expected_version}"
        )
    try:
        valid = connection.execute(
            "SELECT json_valid(?) AS valid", ('{"ok": true}',)
        ).fetchone()["valid"]
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("SQLite JSON functions are unavailable") from exc
    if valid != 1:
        raise RuntimeError("SQLite JSON validation is not working")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("SQLite foreign_keys must be enabled")


__all__ = ["NativeMigrationAuditDatabase", "inspect_database"]
