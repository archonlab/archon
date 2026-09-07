#!/usr/bin/env python3
"""ARCHON Studio presentation adapter for canonical Observer headless runs.

The production Observer source is release-sealed and must remain byte-identical.
This adapter imports that source unchanged, mirrors already-computed frames and
metrics to Studio, and forwards the run through the canonical ``main()`` path.

Scientific ownership stays with the canonical Observer:
FieldSim -> LifeObserver -> telemetry/evidence -> write_outputs.
The only monkeypatch is a read-only wrapper around ``LifeObserver.update``.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OBSERVER_SOURCE = PROJECT_ROOT / "Observer" / "universe_search_observer_v441_validation_calibration.py"
PREFIX = "ARCHON_STUDIO_OBSERVER_JSON="


def _arg_value(argv: list[str], name: str, default: Any) -> Any:
    try:
        index = argv.index(name)
    except ValueError:
        return default
    if index + 1 >= len(argv):
        return default
    return argv[index + 1]


def _encode_grid(grid: Any) -> tuple[int, int, str]:
    """Quantize a presentation copy of the current grid into one byte/cell."""
    try:
        height = int(len(grid))
        width = int(len(grid[0])) if height else 0
    except Exception:
        return 0, 0, ""
    raw = bytearray()
    try:
        for row in grid:
            for value in row:
                try:
                    number = float(value)
                except Exception:
                    number = 0.0
                raw.append(max(0, min(255, int(round(number * 255.0)))))
    except Exception:
        return 0, 0, ""
    return width, height, base64.b64encode(bytes(raw)).decode("ascii")


def _metric_subset(observer: Any) -> dict[str, Any]:
    current = observer.current if isinstance(getattr(observer, "current", None), dict) else {}
    keys = (
        "objects", "defect_cells", "largest", "total_living_mass",
        "ecosystem_health", "stability_index", "ecosystem_phase",
        "active_families", "deepest_generation", "knowledge_score",
        "feedback_score", "feedback_regime", "emergence_score",
        "emergence_confidence", "validation_quality", "validation_grade",
        "life_evidence_verdict", "life_evidence_score", "evo_pressure",
        "evo_recovery", "evo_phase", "chronicle_last",
    )
    out: dict[str, Any] = {}
    for key in keys:
        value = current.get(key)
        if isinstance(value, float):
            out[key] = round(value, 6)
        elif isinstance(value, (str, int, bool)) or value is None:
            out[key] = value
    return out


def _emit(*, grid: Any, observer: Any, tick: int, max_ticks: int, state: str, frame_seq: int) -> None:
    width, height, grid_b64 = _encode_grid(grid)
    payload = {
        "type": "frame",
        "state": state,
        "tick": int(tick),
        "max_ticks": int(max_ticks),
        "width": width,
        "height": height,
        "grid_b64": grid_b64,
        "metrics": _metric_subset(observer),
        "run_id": str(getattr(observer, "telemetry_run_id", "") or ""),
        "frame_seq": int(frame_seq),
    }
    print(PREFIX + json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def _load_canonical_observer():
    if not OBSERVER_SOURCE.is_file():
        raise SystemExit(f"canonical Observer source missing: {OBSERVER_SOURCE}")
    module_name = "archon_studio_canonical_observer"
    spec = importlib.util.spec_from_file_location(module_name, OBSERVER_SOURCE)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import canonical Observer source: {OBSERVER_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    studio_stream = "--studio-stream" in forwarded
    forwarded = [value for value in forwarded if value != "--studio-stream"]
    if not studio_stream:
        raise SystemExit("Studio Observer adapter requires --studio-stream")
    if "--headless" not in forwarded:
        raise SystemExit("Studio Observer adapter requires canonical --headless mode")

    # The canonical loop already has a clean early-exit boundary via --auto-stop
    # and collapse_tick. We use that boundary for SIGTERM/SIGINT instead of
    # changing the sealed run loop.
    if "--auto-stop" not in forwarded:
        forwarded.append("--auto-stop")

    max_ticks = max(1, int(_arg_value(forwarded, "--max-ticks", 1)))
    frame_steps = max(1, int(_arg_value(forwarded, "--speed", 1)))
    delay_ms = max(0, int(_arg_value(forwarded, "--delay", 30)))
    minimum_frame_seconds = max(0.03, min(0.5, delay_ms / 1000.0))

    module = _load_canonical_observer()
    original_update = module.LifeObserver.update
    stop_requested = False
    last_emit = 0.0
    last_grid: Any = None
    last_observer: Any = None
    last_tick = 0
    frame_seq = 0

    def request_stop(signum, _frame):
        nonlocal stop_requested
        stop_requested = True
        print(PREFIX + json.dumps({
            "type": "state", "state": "STOPPING", "tick": int(last_tick),
            "max_ticks": int(max_ticks), "signal": int(signum), "frame_seq": int(frame_seq),
        }, separators=(",", ":")), flush=True)

    old_handlers: dict[int, Any] = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            old_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
        except Exception:
            pass

    def studio_update(observer, grid, tick):
        nonlocal last_emit, last_grid, last_observer, last_tick, frame_seq
        result = original_update(observer, grid, tick)
        last_grid = grid
        last_observer = observer
        last_tick = int(tick)
        now = time.monotonic()
        due = (
            int(tick) == 0
            or int(tick) == 1
            or int(tick) >= max_ticks
            or int(tick) % frame_steps == 0
            or now - last_emit >= 2.0
        )
        if due and (int(tick) <= 1 or now - last_emit >= minimum_frame_seconds or int(tick) >= max_ticks):
            frame_seq += 1
            _emit(
                grid=grid,
                observer=observer,
                tick=int(tick),
                max_ticks=max_ticks,
                state="STOPPING" if stop_requested else "RUNNING",
                frame_seq=frame_seq,
            )
            last_emit = now
        if stop_requested:
            # ``run_headless_observation`` checks collapse_tick immediately after
            # update when --auto-stop is active, then follows its normal
            # write_outputs/finalization path.
            observer.collapse_tick = int(tick)
        return result

    module.LifeObserver.update = studio_update
    old_argv = sys.argv[:]
    try:
        sys.argv = [str(OBSERVER_SOURCE), *forwarded]
        result = module.main()
        if last_grid is not None and last_observer is not None:
            frame_seq += 1
            _emit(
                grid=last_grid,
                observer=last_observer,
                tick=last_tick,
                max_ticks=max_ticks,
                state="STOPPED" if stop_requested else "COMPLETE",
                frame_seq=frame_seq,
            )
        return int(result or 0)
    finally:
        sys.argv = old_argv
        module.LifeObserver.update = original_update
        for signum, handler in old_handlers.items():
            try:
                signal.signal(signum, handler)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
