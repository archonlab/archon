"""SQLite implementation of atomic scientific identity registration."""
from __future__ import annotations

import json
import sqlite3

from Analyzer_next.core.telemetry.scientific_target_registration import (
    ScientificIdentityRegistration,
    ScientificIdentityRegistrationError,
    ScientificIdentityRegistrationResult,
)

from .connection import connect_database
from .experimental_conditions import ExperimentalConditionsRepository


class SQLiteScientificIdentityRegistrationRepository(
    ExperimentalConditionsRepository
):
    def register(
        self,
        command: ScientificIdentityRegistration,
    ) -> ScientificIdentityRegistrationResult:
        condition_id = command.condition_id
        failures: list[str] = []
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_condition = connection.execute(
                "SELECT * FROM experimental_conditions "
                "WHERE condition_hash = ?",
                (command.condition["condition_hash"],),
            ).fetchone()
            if existing_condition is not None:
                condition_id = str(existing_condition["condition_id"])
            else:
                collision = connection.execute(
                    "SELECT condition_hash FROM experimental_conditions "
                    "WHERE condition_id = ?",
                    (condition_id,),
                ).fetchone()
                if collision is not None:
                    failures.append("CONDITION_ID_COLLISION")
                else:
                    connection.execute(
                        """
                        INSERT INTO experimental_conditions (
                            condition_id, name, field_width, field_height,
                            topology, boundary_mode, initial_state_mode,
                            condition_hash, parameters_json, schema_version,
                            created_at_utc, updated_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            condition_id,
                            f"Auto condition for {command.plan_id}",
                            command.condition["field_width"],
                            command.condition["field_height"],
                            command.condition["topology"],
                            command.condition["boundary_mode"],
                            command.condition["initial_state_mode"],
                            command.condition["condition_hash"],
                            json.dumps(
                                command.condition["parameters"],
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                            command.condition["schema_version"],
                            command.timestamp,
                            command.timestamp,
                        ),
                    )

            metadata = {
                "source": "scientific_target_resolver",
                "source_plan_id": command.plan_id,
                "source_plan_hash": command.plan_hash,
                "source_action_id": command.source_action_id,
                "rule_ids": list(command.rule_ids),
            }
            if command.experiment_type:
                metadata["experiment_type"] = command.experiment_type

            existing_experiment = connection.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?",
                (command.experiment_id,),
            ).fetchone()
            if existing_experiment is not None:
                existing_metadata = json.loads(
                    existing_experiment["metadata_json"]
                )
                if not isinstance(existing_metadata, dict):
                    existing_metadata = {}
                if (
                    existing_metadata.get("source_plan_id")
                    != command.plan_id
                    or existing_metadata.get("source_plan_hash")
                    != command.plan_hash
                ):
                    failures.append("EXPERIMENT_ID_COLLISION")
                else:
                    existing_type = str(
                        existing_metadata.get("experiment_type") or ""
                    ).strip()
                    expected_type = str(command.experiment_type or "").strip()
                    if existing_type and expected_type and existing_type != expected_type:
                        failures.append("EXPERIMENT_TYPE_MISMATCH")
                    elif expected_type and not existing_type:
                        enriched_metadata = dict(existing_metadata)
                        enriched_metadata["experiment_type"] = expected_type
                        connection.execute(
                            """
                            UPDATE experiments
                            SET metadata_json = ?, updated_at_utc = ?
                            WHERE experiment_id = ?
                            """,
                            (
                                json.dumps(
                                    enriched_metadata,
                                    ensure_ascii=False,
                                    sort_keys=True,
                                ),
                                command.timestamp,
                                command.experiment_id,
                            ),
                        )
            else:
                connection.execute(
                    """
                    INSERT INTO experiments (
                        experiment_id, title, research_question, status,
                        metadata_json, created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, 'planned', ?, ?, ?)
                    """,
                    (
                        command.experiment_id,
                        command.title,
                        command.research_question,
                        json.dumps(
                            metadata,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        command.timestamp,
                        command.timestamp,
                    ),
                )

            if failures:
                connection.rollback()
                return ScientificIdentityRegistrationResult(
                    command.experiment_id,
                    condition_id,
                    tuple(failures),
                )
            connection.commit()
            return ScientificIdentityRegistrationResult(
                command.experiment_id,
                condition_id,
            )
        except (sqlite3.Error, ValueError, TypeError) as error:
            connection.rollback()
            raise ScientificIdentityRegistrationError(str(error)) from error
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.database_path)


__all__ = ["SQLiteScientificIdentityRegistrationRepository"]
