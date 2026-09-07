"""Schema-compatible read-only experiment catalog for OL2-EXPERIMENTS-FIX2."""
from __future__ import annotations

from Analyzer_next.adapters.observer.experiment_catalog import SQLiteExperimentCatalog
from Analyzer_next.execution.observer.shell2.functions1d.model import ExperimentRow, ExperimentRunRow


class SchemaCompatibleSQLiteExperimentCatalog(SQLiteExperimentCatalog):
    """Read current/older experiment schemas without migrating scientific SQLite."""

    @staticmethod
    def _columns(connection, table: str) -> set[str]:
        return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}

    def list_experiments(self) -> tuple[ExperimentRow, ...]:
        connection = self._connect()
        try:
            tables = self._tables(connection)
            if "experiments" not in tables:
                return ()
            if "experiment_runs" in tables:
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
            else:
                rows = connection.execute(
                    """
                    SELECT experiment_id, title, research_question, status,
                           created_at_utc, updated_at_utc, 0 AS run_count
                    FROM experiments
                    ORDER BY COALESCE(updated_at_utc, created_at_utc) DESC,
                             experiment_id
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

    def list_experiment_runs(self, experiment_id: str) -> tuple[ExperimentRunRow, ...]:
        experiment_id = str(experiment_id).strip()
        if not experiment_id:
            return ()
        connection = self._connect()
        try:
            if "experiment_runs" not in self._tables(connection):
                return ()
            columns = self._columns(connection, "experiment_runs")
            required = {"experiment_run_id", "experiment_id", "run_id", "condition_id"}
            missing = sorted(required - columns)
            if missing:
                raise RuntimeError("experiment_runs missing required columns: " + ", ".join(missing))

            def expr(column: str, fallback: str) -> str:
                return column if column in columns else f"{fallback} AS {column}"

            select = ", ".join((
                "experiment_run_id",
                "run_id",
                "condition_id",
                expr("rule_id", "NULL"),
                expr("role", "'baseline'"),
                expr("replicate_index", "0"),
                expr("treatment_arm", "''"),
                expr("created_at_utc", "NULL"),
            ))
            order = "created_at_utc DESC, experiment_run_id DESC" if "created_at_utc" in columns else "experiment_run_id DESC"
            rows = connection.execute(
                f"SELECT {select} FROM experiment_runs WHERE experiment_id = ? ORDER BY {order}",
                (experiment_id,),
            ).fetchall()
            return tuple(
                ExperimentRunRow(
                    experiment_run_id=str(row["experiment_run_id"]),
                    run_id=str(row["run_id"]),
                    condition_id=str(row["condition_id"]),
                    rule_id=(int(row["rule_id"]) if row["rule_id"] is not None else None),
                    role=str(row["role"] or "baseline"),
                    replicate_index=int(row["replicate_index"] or 0),
                    treatment_arm=str(row["treatment_arm"] or ""),
                    created_at_utc=(str(row["created_at_utc"]) if row["created_at_utc"] is not None else None),
                )
                for row in rows
            )
        finally:
            connection.close()


__all__ = ["SchemaCompatibleSQLiteExperimentCatalog"]
