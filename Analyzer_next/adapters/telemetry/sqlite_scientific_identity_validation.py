"""Read-only SQLite implementation of scientific identity validation."""
from __future__ import annotations

import sqlite3

from Analyzer_next.core.telemetry.scientific_identity_validation import (
    ScientificIdentityValidation,
    ScientificIdentityValidationError,
)

from .connection import connect_database


class SQLiteScientificIdentityValidationRepository:
    def __init__(self, database_path) -> None:
        self.database_path = database_path

    def identity_issues(
        self,
        request: ScientificIdentityValidation,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        try:
            connection = connect_database(
                self.database_path,
                read_only=True,
            )
            try:
                if request.experiment_id:
                    row = connection.execute(
                        "SELECT 1 FROM experiments "
                        "WHERE experiment_id = ? LIMIT 1",
                        (request.experiment_id,),
                    ).fetchone()
                    if row is None:
                        issues.append(
                            "EXPERIMENT_NOT_REGISTERED:"
                            f"{request.experiment_id}"
                        )
                if request.condition_id:
                    row = connection.execute(
                        "SELECT 1 FROM experimental_conditions "
                        "WHERE condition_id = ? LIMIT 1",
                        (request.condition_id,),
                    ).fetchone()
                    if row is None:
                        issues.append(
                            "CONDITION_NOT_REGISTERED:"
                            f"{request.condition_id}"
                        )
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ScientificIdentityValidationError(str(error)) from error
        return tuple(issues)


__all__ = ["SQLiteScientificIdentityValidationRepository"]
