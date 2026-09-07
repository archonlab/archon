#!/usr/bin/env python3
"""Run the canonical legacy Observer without a desktop window and stream UI state.

Scientific execution remains entirely inside the existing Observer module. The
bridge only replaces Tk widgets with no-op objects, then mirrors the legacy
WorldViewer's already-computed presentation state over stdout as framed JSONL.
"""
from __future__ import annotations

import argparse
import base64
import importlib
import json
import sys
import time
import zlib
from typing import Any

from .headless_tk import HeadlessTkModule


PREFIX = "[ol2-ui] "
PROTOCOL = "archon.ol2.legacy-presentation.v1"
DEFAULT_LEGACY_MODULE = "Observer.universe_search_observer_v441_validation_calibration"


def _quantized_field(viewer: Any) -> tuple[int, int, str]:
    sim = viewer.sim
    width = int(sim.width)
    height = int(sim.height)
    packed = bytearray(width * height)
    index = 0
    for row in sim.a:
        for value in row:
            try:
                numeric = float(value)
            except Exception:
                numeric = 0.0
            numeric = max(0.0, min(1.0, numeric))
            packed[index] = int(round(numeric * 255.0))
            index += 1
    encoded = base64.b64encode(zlib.compress(bytes(packed), level=1)).decode("ascii")
    return width, height, encoded


def _legacy_panels(viewer: Any) -> dict[str, dict[str, str]]:
    sections = {
        "UNIVERSE": ("status", "world", "phase", "era"),
        "LIFE": ("life_evidence", "life", "life_births", "life_survival", "lineage"),
        "ONTOLOGY / LIFECYCLE": (
            "ontology_state",
            "ontology_coverage",
            "ontology_first",
            "ontology_confidence",
            "ontology_terminal",
        ),
        "PRESSURE": ("pressure", "pressure_cause"),
        "MORPHOLOGY": ("morph_class", "morph_shape1", "morph_shape2", "morph_change"),
        "KNOWLEDGE / EVIDENCE": ("knowledge", "feedback", "emergence", "validation"),
        "PERFORMANCE": ("perf", "perf2", "keys"),
    }
    labels = getattr(viewer, "panel_labels", {}) or {}
    result: dict[str, dict[str, str]] = {}
    for section, keys in sections.items():
        rows: dict[str, str] = {}
        for key in keys:
            widget = labels.get(key)
            text = ""
            if widget is not None:
                try:
                    text = str(widget.cget("text") or "")
                except Exception:
                    text = ""
            rows[key] = text
        result[section] = rows
    return result


def _widget_text(viewer: Any, name: str) -> str:
    widget = getattr(viewer, name, None)
    if widget is None:
        return ""
    try:
        return str(widget.cget("text") or "")
    except Exception:
        return ""


class PresentationEmitter:
    def __init__(self, *, interval_ms: int = 100) -> None:
        self.interval_seconds = max(0.02, int(interval_ms) / 1000.0)
        self.last_emit = 0.0
        self.sequence = 0
        self.last_tick = -1

    def emit(self, viewer: Any, *, force: bool = False) -> None:
        tick = int(getattr(viewer, "tick", 0))
        now = time.monotonic()
        if not force and tick == self.last_tick and now - self.last_emit < self.interval_seconds:
            return
        if not force and self.last_emit and now - self.last_emit < self.interval_seconds:
            return
        width, height, field = _quantized_field(viewer)
        self.sequence += 1
        payload = {
            "protocol": PROTOCOL,
            "sequence": self.sequence,
            "tick": tick,
            "rule_id": int(viewer.rec["rule_id"]),
            "width": width,
            "height": height,
            "encoding": "zlib-u8-base64",
            "field": field,
            "panels": _legacy_panels(viewer),
            "chronicle": _widget_text(viewer, "chronicle_label"),
            "status_bar": _widget_text(viewer, "info"),
            "running": bool(getattr(viewer, "running", False)),
        }
        print(PREFIX + json.dumps(payload, separators=(",", ":"), ensure_ascii=False), flush=True)
        self.last_emit = now
        self.last_tick = tick


def run_bridge(legacy_module: str, legacy_argv: list[str], *, interval_ms: int) -> int:
    legacy = importlib.import_module(legacy_module)
    if getattr(legacy, "tk", None) is None:
        raise SystemExit("Legacy Observer imported without tkinter support")

    legacy.tk = HeadlessTkModule()
    emitter = PresentationEmitter(interval_ms=interval_ms)
    original_draw = legacy.WorldViewer.draw
    original_close = legacy.WorldViewer.close

    def streamed_draw(viewer: Any, *args: Any, **kwargs: Any) -> Any:
        viewer.visualization_enabled = False
        result = original_draw(viewer, *args, **kwargs)
        emitter.emit(viewer)
        return result

    def streamed_close(viewer: Any, *args: Any, **kwargs: Any) -> Any:
        emitter.emit(viewer, force=True)
        return original_close(viewer, *args, **kwargs)

    legacy.WorldViewer.draw = streamed_draw
    legacy.WorldViewer.close = streamed_close

    previous_argv = sys.argv
    sys.argv = [getattr(legacy, "__file__", legacy_module), *legacy_argv]
    try:
        result = legacy.main()
    finally:
        sys.argv = previous_argv
    return int(result or 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Headless legacy Observer presentation bridge"
    )
    parser.add_argument("--legacy-module", default=DEFAULT_LEGACY_MODULE)
    parser.add_argument("--interval-ms", type=int, default=100)
    parser.add_argument("legacy_args", nargs=argparse.REMAINDER)
    known = parser.parse_args()
    remainder = list(known.legacy_args)
    if remainder and remainder[0] == "--":
        remainder = remainder[1:]
    return run_bridge(known.legacy_module, remainder, interval_ms=known.interval_ms)


if __name__ == "__main__":
    raise SystemExit(main())
