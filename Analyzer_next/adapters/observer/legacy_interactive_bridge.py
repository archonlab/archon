#!/usr/bin/env python3
"""Interactive headless bridge for the canonical legacy Observer.

The legacy module still owns simulation, observation, telemetry and persistence.
This bridge only replaces Tk widgets, emits the existing presentation frames,
and applies explicit launcher controls scheduled onto the legacy event loop.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import threading
from typing import Any

from .headless_tk import HeadlessTkModule
from .interactive_process_runner import CONTROL_PROTOCOL
from .legacy_presentation_bridge import (
    DEFAULT_LEGACY_MODULE,
    PresentationEmitter,
)

CONTROL_PREFIX = "[ol2-control] "


def _ack(
    viewer: Any,
    *,
    sequence: int,
    command: str,
    status: str,
    error: str | None = None,
) -> None:
    payload = {
        "protocol": CONTROL_PROTOCOL,
        "sequence": int(sequence),
        "command": str(command),
        "status": str(status),
        "tick": int(getattr(viewer, "tick", 0)),
        "running": bool(getattr(viewer, "running", False)),
        "speed": int(getattr(getattr(viewer, "args", None), "speed", 0) or 0),
    }
    if error:
        payload["error"] = str(error)
    print(CONTROL_PREFIX + json.dumps(payload, separators=(",", ":")), flush=True)


def _apply_command(viewer: Any, payload: dict[str, Any]) -> None:
    sequence = int(payload.get("sequence") or 0)
    command = str(payload.get("command") or "").strip().lower()
    try:
        if command == "pause":
            viewer.running = False
        elif command == "resume":
            viewer.running = True
        elif command == "speed":
            speed = int(payload.get("value") or 0)
            if speed < 1 or speed > 1000:
                raise ValueError("speed must be within 1..1000")
            labels = {
                1: "x1 normal",
                2: "x2",
                10: "x10 fast",
                100: "x100 turbo",
                1000: "x1000 ultra",
            }
            viewer.set_speed(speed, labels.get(speed, f"x{speed}"))
        elif command == "save":
            viewer.save_checkpoint(reason="interactive")
        else:
            raise ValueError(f"unsupported command: {command}")
    except Exception as exc:
        _ack(viewer, sequence=sequence, command=command, status="error", error=f"{type(exc).__name__}: {exc}")
        return
    _ack(viewer, sequence=sequence, command=command, status="ok")


def _control_reader(holder: dict[str, Any]) -> None:
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
            if payload.get("protocol") != CONTROL_PROTOCOL:
                raise ValueError("unsupported control protocol")
            sequence = int(payload.get("sequence") or 0)
            if sequence < 1:
                raise ValueError("sequence must be positive")
            viewer = holder.get("viewer")
            if viewer is None:
                raise RuntimeError("legacy viewer is not ready")
            viewer.root.after_idle(lambda p=payload, v=viewer: _apply_command(v, p))
        except Exception as exc:
            viewer = holder.get("viewer")
            if viewer is not None:
                _ack(viewer, sequence=int(payload.get("sequence") or 0) if isinstance(locals().get("payload"), dict) else 0, command=str(payload.get("command") or "invalid") if isinstance(locals().get("payload"), dict) else "invalid", status="error", error=f"{type(exc).__name__}: {exc}")


def run_bridge(legacy_module: str, legacy_argv: list[str], *, interval_ms: int) -> int:
    legacy = importlib.import_module(legacy_module)
    if getattr(legacy, "tk", None) is None:
        raise SystemExit("Legacy Observer imported without tkinter support")

    legacy.tk = HeadlessTkModule()
    emitter = PresentationEmitter(interval_ms=interval_ms)
    holder: dict[str, Any] = {}
    original_init = legacy.WorldViewer.__init__
    original_draw = legacy.WorldViewer.draw
    original_close = legacy.WorldViewer.close

    def interactive_init(viewer: Any, *args: Any, **kwargs: Any) -> None:
        original_init(viewer, *args, **kwargs)
        holder["viewer"] = viewer
        threading.Thread(
            target=_control_reader,
            args=(holder,),
            name="ol2-legacy-control-reader",
            daemon=True,
        ).start()

    def streamed_draw(viewer: Any, *args: Any, **kwargs: Any) -> Any:
        viewer.visualization_enabled = False
        result = original_draw(viewer, *args, **kwargs)
        emitter.emit(viewer)
        return result

    def streamed_close(viewer: Any, *args: Any, **kwargs: Any) -> Any:
        emitter.emit(viewer, force=True)
        return original_close(viewer, *args, **kwargs)

    legacy.WorldViewer.__init__ = interactive_init
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
    parser = argparse.ArgumentParser(description="Interactive headless legacy Observer bridge")
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
