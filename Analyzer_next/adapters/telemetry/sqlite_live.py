"""Read-only SQLite implementation of the OL2 live Telemetry port."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from Analyzer_next.core.telemetry.contracts import TelemetryQueryError
from Analyzer_next.core.telemetry.live import (
    LiveTelemetryFrame,
    LiveTelemetrySample,
)

from .sqlite_repository import SQLiteTelemetryRepository


class SQLiteLiveTelemetryAdapter:
    """Build a bounded chronological sample window without owning SQLite writes."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self._repository = SQLiteTelemetryRepository(self.database_path)

    def read_frame(
        self,
        run_id: str,
        *,
        history_limit: int = 8,
    ) -> LiveTelemetryFrame | None:
        if int(history_limit) < 2:
            raise TelemetryQueryError("history_limit must be >= 2")
        expected_run_id = str(run_id).strip()
        if not expected_run_id:
            raise TelemetryQueryError("run_id is required")

        run = self._repository.get_run(expected_run_id)
        rows = self._repository.read_channel(
            expected_run_id,
            "sample",
            limit=int(history_limit),
            newest_first=True,
            payload_only=False,
        )
        if not rows:
            return None

        samples: list[LiveTelemetrySample] = []
        for row in reversed(rows):
            row_run_id = str(row.get("run_id") or "")
            if row_run_id != expected_run_id:
                raise TelemetryQueryError(
                    "Telemetry row identity mismatch: "
                    f"expected {expected_run_id!r}, got {row_run_id!r}"
                )
            payload = row.get("payload")
            if payload is None:
                payload = {}
            if not isinstance(payload, dict):
                raise TelemetryQueryError("decoded sample payload must be an object")
            tick = row.get("tick")
            if tick is None:
                raise TelemetryQueryError("sample row has no tick")
            fields: dict[str, Any] = {
                key: value
                for key, value in row.items()
                if key != "payload"
            }
            samples.append(
                LiveTelemetrySample(
                    run_id=row_run_id,
                    tick=int(tick),
                    fields=fields,
                    payload=payload,
                    created_at_utc=(
                        str(row["created_at_utc"])
                        if row.get("created_at_utc") is not None
                        else None
                    ),
                )
            )

        return LiveTelemetryFrame(
            run_id=expected_run_id,
            run_status=run.status,
            final_tick=run.final_tick,
            samples=tuple(samples),
        )

    def close(self) -> None:
        self._repository.close()

    def __enter__(self) -> "SQLiteLiveTelemetryAdapter":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


__all__ = ["SQLiteLiveTelemetryAdapter"]
