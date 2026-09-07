"""Safe metadata/lifecycle reconciliation for completed experiment runs.

BRIDGE2 keeps the frozen Analyzer read-only contract intact while allowing the
modular entrypoint to repair two pieces of canonical experiment metadata before
analysis:

* an experiment with linked runs that are all completed may advance from
  ``planned``/``running`` to ``completed``;
* an auto-generated condition label may be aligned with the experiment's
  ``source_plan_id`` when that condition is owned by exactly one experiment.

Scientific measurements and run identities are never changed here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


@dataclass(frozen=True, slots=True)
class ExperimentMetadataReconcileReport:
    status_updates: int = 0
    condition_name_updates: int = 0
    shared_condition_skips: int = 0
    malformed_metadata_skips: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_metadata(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def reconcile_experiment_metadata(database: Path) -> ExperimentMetadataReconcileReport:
    """Reconcile non-scientific experiment metadata in one atomic transaction."""
    database = Path(database).expanduser().resolve()
    connection = sqlite3.connect(str(database))
    connection.row_factory = sqlite3.Row
    status_updates = 0
    condition_name_updates = 0
    shared_condition_skips = 0
    malformed_metadata_skips = 0
    now = _utc_now()

    try:
        connection.execute("BEGIN IMMEDIATE")

        experiments = connection.execute(
            """
            SELECT
                e.experiment_id,
                e.status,
                e.metadata_json,
                COUNT(er.run_id) AS linked_runs,
                SUM(CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END) AS completed_runs
            FROM experiments e
            LEFT JOIN experiment_runs er
                ON er.experiment_id = e.experiment_id
            LEFT JOIN runs r
                ON r.run_id = er.run_id
            GROUP BY e.experiment_id, e.status, e.metadata_json
            """
        ).fetchall()

        for row in experiments:
            linked = int(row["linked_runs"] or 0)
            completed = int(row["completed_runs"] or 0)
            current = str(row["status"] or "").strip().lower()
            if linked > 0 and linked == completed and current in {"planned", "running"}:
                connection.execute(
                    """
                    UPDATE experiments
                    SET status = 'completed', updated_at_utc = ?
                    WHERE experiment_id = ? AND status IN ('planned', 'running')
                    """,
                    (now, str(row["experiment_id"])),
                )
                status_updates += 1

            metadata = _load_metadata(row["metadata_json"])
            source_plan_id = str(metadata.get("source_plan_id") or "").strip()
            if not source_plan_id:
                if row["metadata_json"] not in (None, "", "{}") and not metadata:
                    malformed_metadata_skips += 1
                continue

            condition_rows = connection.execute(
                """
                SELECT DISTINCT c.condition_id, c.name
                FROM experiment_runs er
                JOIN experimental_conditions c
                    ON c.condition_id = er.condition_id
                WHERE er.experiment_id = ?
                """,
                (str(row["experiment_id"]),),
            ).fetchall()
            expected_name = f"Auto condition for {source_plan_id}"
            for condition in condition_rows:
                condition_id = str(condition["condition_id"])
                current_name = str(condition["name"] or "")
                if not current_name.startswith("Auto condition for EXP-PLAN-"):
                    continue
                if current_name == expected_name:
                    continue
                owner_count = connection.execute(
                    """
                    SELECT COUNT(DISTINCT experiment_id)
                    FROM experiment_runs
                    WHERE condition_id = ?
                    """,
                    (condition_id,),
                ).fetchone()[0]
                if int(owner_count or 0) != 1:
                    shared_condition_skips += 1
                    continue
                connection.execute(
                    """
                    UPDATE experimental_conditions
                    SET name = ?, updated_at_utc = ?
                    WHERE condition_id = ?
                    """,
                    (expected_name, now, condition_id),
                )
                condition_name_updates += 1

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return ExperimentMetadataReconcileReport(
        status_updates=status_updates,
        condition_name_updates=condition_name_updates,
        shared_condition_skips=shared_condition_skips,
        malformed_metadata_skips=malformed_metadata_skips,
    )


__all__ = [
    "ExperimentMetadataReconcileReport",
    "reconcile_experiment_metadata",
]
