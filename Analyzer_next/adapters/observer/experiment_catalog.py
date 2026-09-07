"""Read-only SQLite adapter for OL2-FUNCTIONS1D experiment browsing."""
from __future__ import annotations

from pathlib import Path
import sqlite3

from Analyzer_next.execution.observer.shell2.functions1d.model import (
    ConditionRow,
    ExperimentRow,
    ExperimentRunRow,
)


class SQLiteExperimentCatalog:
    """Project experiment/condition/run catalog opened strictly read-only."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)
        uri = f"file:{self.database_path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {str(row[0]) for row in rows}

    def list_experiments(self) -> tuple[ExperimentRow, ...]:
        connection = self._connect()
        try:
            if "experiments" not in self._tables(connection):
                return ()
            rows = connection.execute(
                """
                SELECT e.experiment_id, e.title, e.research_question, e.status,
                       e.created_at_utc, e.updated_at_utc,
                       COUNT(er.experiment_run_id) AS run_count
                FROM experiments AS e
                LEFT JOIN experiment_runs AS er
                  ON er.experiment_id = e.experiment_id
                GROUP BY e.experiment_id, e.title, e.research_question, e.status,
                         e.created_at_utc, e.updated_at_utc
                ORDER BY COALESCE(e.updated_at_utc, e.created_at_utc) DESC,
                         e.experiment_id
                """
            ).fetchall()
            return tuple(
                ExperimentRow(
                    experiment_id=str(row["experiment_id"]),
                    title=str(row["title"] or row["experiment_id"]),
                    research_question=(str(row["research_question"]) if row["research_question"] is not None else None),
                    status=str(row["status"] or "unknown"),
                    created_at_utc=(str(row["created_at_utc"]) if row["created_at_utc"] is not None else None),
                    updated_at_utc=(str(row["updated_at_utc"]) if row["updated_at_utc"] is not None else None),
                    run_count=int(row["run_count"] or 0),
                )
                for row in rows
            )
        finally:
            connection.close()

    def list_conditions(self) -> tuple[ConditionRow, ...]:
        connection = self._connect()
        try:
            if "experimental_conditions" not in self._tables(connection):
                return ()
            rows = connection.execute(
                """
                SELECT condition_id, name, field_width, field_height, topology,
                       boundary_mode, initial_state_mode
                FROM experimental_conditions
                ORDER BY condition_id
                """
            ).fetchall()
            return tuple(
                ConditionRow(
                    condition_id=str(row["condition_id"]),
                    name=str(row["name"] or row["condition_id"]),
                    field_width=int(row["field_width"]),
                    field_height=int(row["field_height"]),
                    topology=str(row["topology"]),
                    boundary_mode=str(row["boundary_mode"]),
                    initial_state_mode=str(row["initial_state_mode"]),
                )
                for row in rows
            )
        finally:
            connection.close()

    def list_experiment_runs(self, experiment_id: str) -> tuple[ExperimentRunRow, ...]:
        experiment_id = str(experiment_id).strip()
        if not experiment_id:
            return ()
        connection = self._connect()
        try:
            if "experiment_runs" not in self._tables(connection):
                return ()
            rows = connection.execute(
                """
                SELECT experiment_run_id, run_id, condition_id, rule_id, role,
                       replicate_index, treatment_arm, created_at_utc
                FROM experiment_runs
                WHERE experiment_id = ?
                ORDER BY created_at_utc DESC, experiment_run_id DESC
                """,
                (experiment_id,),
            ).fetchall()
            return tuple(
                ExperimentRunRow(
                    experiment_run_id=str(row["experiment_run_id"]),
                    run_id=str(row["run_id"]),
                    condition_id=str(row["condition_id"]),
                    rule_id=(int(row["rule_id"]) if row["rule_id"] is not None else None),
                    role=str(row["role"] or "unknown"),
                    replicate_index=int(row["replicate_index"] or 0),
                    treatment_arm=str(row["treatment_arm"] or ""),
                    created_at_utc=(str(row["created_at_utc"]) if row["created_at_utc"] is not None else None),
                )
                for row in rows
            )
        finally:
            connection.close()


__all__ = ["SQLiteExperimentCatalog"]
