"""CONTROL1-compatible parser for the legacy Observer presentation stream."""
from __future__ import annotations

import base64
import json
import zlib

from Analyzer_next.execution.observer.shell2.control1.controller import (
    ObserverControlController,
)

from .model import InstrumentSection, LegacyPresentationFrame


PREFIX = "[ol2-ui] "
PROTOCOL = "archon.ol2.legacy-presentation.v1"
_MAX_CELLS = 512 * 512


class PresentationProtocolError(ValueError):
    pass


def decode_presentation_line(text: str) -> LegacyPresentationFrame:
    stripped = text.strip()
    if not stripped.startswith(PREFIX):
        raise PresentationProtocolError("missing presentation prefix")
    try:
        payload = json.loads(stripped[len(PREFIX):])
    except json.JSONDecodeError as exc:
        raise PresentationProtocolError(f"invalid JSON: {exc}") from exc
    if payload.get("protocol") != PROTOCOL:
        raise PresentationProtocolError("unsupported presentation protocol")
    try:
        sequence = int(payload["sequence"])
        tick = int(payload["tick"])
        rule_id = int(payload["rule_id"])
        width = int(payload["width"])
        height = int(payload["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PresentationProtocolError("invalid frame identity/geometry") from exc
    if sequence < 1 or tick < 0 or width < 1 or height < 1:
        raise PresentationProtocolError("negative/empty frame values")
    cells = width * height
    if cells > _MAX_CELLS:
        raise PresentationProtocolError(f"frame too large: {width}x{height}")
    if payload.get("encoding") != "zlib-u8-base64":
        raise PresentationProtocolError("unsupported field encoding")
    try:
        compressed = base64.b64decode(str(payload["field"]), validate=True)
        field = zlib.decompress(compressed)
    except Exception as exc:
        raise PresentationProtocolError(f"invalid field payload: {exc}") from exc
    if len(field) != cells:
        raise PresentationProtocolError(
            f"field length mismatch: expected {cells}, got {len(field)}"
        )

    sections_payload = payload.get("panels") or {}
    if not isinstance(sections_payload, dict):
        raise PresentationProtocolError("panels must be an object")
    sections: list[InstrumentSection] = []
    for title, rows_payload in sections_payload.items():
        if not isinstance(rows_payload, dict):
            continue
        rows = tuple((str(key), str(value or "")) for key, value in rows_payload.items())
        sections.append(InstrumentSection(title=str(title), rows=rows))

    return LegacyPresentationFrame(
        sequence=sequence,
        tick=tick,
        rule_id=rule_id,
        width=width,
        height=height,
        field=field,
        sections=tuple(sections),
        chronicle=str(payload.get("chronicle") or ""),
        status_bar=str(payload.get("status_bar") or ""),
        running=bool(payload.get("running", False)),
    )


class ObserverPresentationController(ObserverControlController):
    """Keep CONTROL1 process semantics while consuming non-scientific UI frames."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._presentation_frame: LegacyPresentationFrame | None = None
        self._presentation_error: str | None = None

    @property
    def presentation_frame(self) -> LegacyPresentationFrame | None:
        with self._lock:
            return self._presentation_frame

    @property
    def presentation_error(self) -> str | None:
        with self._lock:
            return self._presentation_error

    def start(self, prepared, *, retry_of: str | None = None):
        with self._lock:
            self._presentation_frame = None
            self._presentation_error = None
        return super().start(prepared, retry_of=retry_of)

    def _capture_output(self, text: str) -> None:
        if not text.lstrip().startswith(PREFIX):
            super()._capture_output(text)
            return
        try:
            frame = decode_presentation_line(text)
        except PresentationProtocolError as exc:
            with self._lock:
                self._presentation_error = str(exc)
            super()._capture_output(f"[OBSERVE1 presentation error] {exc}\n")
            return
        with self._lock:
            current = self._presentation_frame
            if current is not None and frame.sequence <= current.sequence:
                return
            telemetry_run_id = self.snapshot.telemetry_run_id
            if telemetry_run_id and f"rule_{frame.rule_id:05d}_" not in telemetry_run_id:
                self._presentation_error = (
                    "presentation rule identity does not match canonical telemetry identity"
                )
                return
            self._presentation_frame = frame
            self._presentation_error = None


__all__ = [
    "ObserverPresentationController",
    "PresentationProtocolError",
    "decode_presentation_line",
]
