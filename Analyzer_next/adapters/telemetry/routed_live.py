"""Route OL2 live telemetry between the canonical DB and isolated run-local DBs.

The canonical Telemetry database remains the default source.  Workflows such as
mutation execution may arm one isolated database before launch.  Once the
Observer publishes its canonical telemetry run_id, the router binds that run_id
to the isolated read-only source without copying or promoting any scientific
rows into the canonical database.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from Analyzer_next.core.telemetry.contracts import TelemetryQueryError
from Analyzer_next.core.telemetry.live import LiveTelemetryFrame, LiveTelemetryPort

from .sqlite_live import SQLiteLiveTelemetryAdapter


PortFactory = Callable[[Path], LiveTelemetryPort]


class RoutedLiveTelemetryAdapter:
    """Default canonical live port with an explicit one-run local override."""

    def __init__(
        self,
        default_port: LiveTelemetryPort,
        *,
        port_factory: PortFactory | None = None,
    ) -> None:
        self.default_port = default_port
        self.port_factory = port_factory or (lambda path: SQLiteLiveTelemetryAdapter(path))
        self._armed_database: Path | None = None
        self._armed_port: LiveTelemetryPort | None = None
        self._run_ports: dict[str, LiveTelemetryPort] = {}
        self._closed = False

    @property
    def armed_database(self) -> Path | None:
        return self._armed_database

    def arm_database(self, database_path: str | Path) -> None:
        """Arm one isolated database for the next published telemetry run_id."""
        self._ensure_open()
        self._close_armed_port()
        self._armed_database = Path(database_path).expanduser().resolve()

    def clear_armed_database(self) -> None:
        """Cancel a pending override, for example when process launch fails."""
        self._close_armed_port()
        self._armed_database = None

    def finalize_armed_database(
        self,
        run_id: str | None,
        *,
        history_limit: int = 8,
    ) -> LiveTelemetryFrame | None:
        """Bind a terminal run if its local DB is ready, otherwise release it."""
        if self._armed_database is None:
            return None
        normalized = str(run_id or "").strip()
        if not normalized:
            self.clear_armed_database()
            return None
        try:
            frame = self.read_frame(normalized, history_limit=history_limit)
        except TelemetryQueryError:
            self.clear_armed_database()
            return None
        if frame is None and self._armed_database is not None:
            self.clear_armed_database()
        return frame

    def read_frame(self, run_id: str, *, history_limit: int = 8) -> LiveTelemetryFrame | None:
        self._ensure_open()
        normalized = str(run_id).strip()
        if not normalized:
            raise TelemetryQueryError("run_id is required")

        bound = self._run_ports.get(normalized)
        if bound is not None:
            return bound.read_frame(normalized, history_limit=history_limit)

        # An explicitly armed isolated source wins over the canonical DB for
        # the next identity.  While the Observer is creating that SQLite file
        # and schema, report CONNECTING (None) rather than a false ERROR.
        if self._armed_database is not None:
            if not self._armed_database.is_file():
                return None
            if self._armed_port is None:
                try:
                    self._armed_port = self.port_factory(self._armed_database)
                except TelemetryQueryError as exc:
                    if self._is_transient_initialization_error(exc):
                        return None
                    raise
            try:
                frame = self._armed_port.read_frame(normalized, history_limit=history_limit)
            except TelemetryQueryError as exc:
                if self._is_pending_identity_error(exc, normalized):
                    return None
                raise
            if frame is None:
                return None

            self._run_ports[normalized] = self._armed_port
            self._armed_port = None
            self._armed_database = None
            return frame

        return self.default_port.read_frame(normalized, history_limit=history_limit)

    @staticmethod
    def _is_transient_initialization_error(exc: TelemetryQueryError) -> bool:
        text = str(exc).lower()
        return (
            "invalid telemetry schema" in text
            or "does not exist" in text
            or "could not open telemetry database" in text
        )

    @staticmethod
    def _is_pending_identity_error(exc: TelemetryQueryError, run_id: str) -> bool:
        text = str(exc)
        return "run_id not found" in text and run_id in text

    def _close_armed_port(self) -> None:
        if self._armed_port is not None:
            try:
                self._armed_port.close()
            finally:
                self._armed_port = None

    def _ensure_open(self) -> None:
        if self._closed:
            raise TelemetryQueryError("live telemetry router is closed")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._close_armed_port()
        seen: set[int] = set()
        for port in (self.default_port, *self._run_ports.values()):
            marker = id(port)
            if marker in seen:
                continue
            seen.add(marker)
            port.close()
        self._run_ports.clear()
        self._armed_database = None


__all__ = ["RoutedLiveTelemetryAdapter"]
