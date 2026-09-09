#!/usr/bin/env python3
"""Verify Search Launcher small-screen layout without changing Search science."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "Universe_Search/search_launcher.py"
CORE = ROOT / "Universe_Search/universe_search_core.py"
CYCLE = ROOT / "Universe_Search/universe_search_v34_closed_research_cycle.py"
CORE_SHA256 = "f2a715465c9506dc63a4317b3de22049f1c55719b2c87a7eacfb16a693ac871b"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_launcher_module():
    spec = importlib.util.spec_from_file_location(
        "archon_search_launcher_small_screen_test", LAUNCHER
    )
    require(spec is not None and spec.loader is not None, "cannot load Search Launcher")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_contract(module) -> None:
    require(module.launcher_window_size(1920, 1080) == (1180, 820), "large desktop layout changed")
    require(module.launcher_window_size(1280, 800) == (1180, 680), "MacBook viewport is not bounded")
    require(module.launcher_window_size(800, 600) == (900, 520), "compact fallback is unstable")
    source = LAUNCHER.read_text(encoding="utf-8")
    require('self.minsize(900, 460)' in source, "minimum height was not reduced")
    require("self.launch_canvas = tk.Canvas(" in source, "Launch Settings scroll viewport missing")
    require("self.launch_scrollbar = ttk.Scrollbar(" in source, "vertical scrollbar missing")
    require('actions.grid(row=2, column=0, sticky="ew"' in source, "action bar is not pinned below viewport")
    require("self.root_frame.rowconfigure(1, weight=1)" in source, "main viewport is not flexible")
    require(sha256(CORE) == CORE_SHA256, "Universe Search scientific core changed")
    cycle_source = CYCLE.read_text(encoding="utf-8")
    require("POPULATION = base.POPULATION" in cycle_source and "GENERATIONS = base.GENERATIONS" in cycle_source, "Universe Search scientific budget contract changed")
    require("def emit_search_runtime_event(" in cycle_source, "real Search runtime telemetry contract missing")


def verify_gui(module) -> None:
    for theme in ("light", "dark"):
        app = module.SearchLauncher(theme=theme)
        try:
            app.geometry("1000x560+0+0")
            app.update_idletasks()
            app.update()
            require(app.winfo_height() <= 560, f"{theme}: window refuses compact height")
            bottom = app.winfo_rooty() + app.winfo_height()
            for name in ("launch_button", "resume_button", "stop_button", "status_label"):
                widget = getattr(app, name)
                require(widget.winfo_ismapped(), f"{theme}: {name} is not visible")
                require(widget.winfo_rooty() + widget.winfo_height() <= bottom, f"{theme}: {name} is below viewport")
            require(app.config_card.winfo_ismapped(), f"{theme}: Search Configuration missing")
            require(app.launch_scrollbar.winfo_ismapped(), f"{theme}: compact viewport did not enable scrolling")
            before = app.launch_canvas.yview()
            app.launch_canvas.yview_moveto(1.0)
            app.update_idletasks()
            after = app.launch_canvas.yview()
            require(after != before and after[0] > 0.0, f"{theme}: Launch Settings does not scroll")
            require(app.progress_card.winfo_ismapped(), f"{theme}: Search Progress is not reachable")
            require(
                app.launch_canvas.cget("background") == module.PALETTES[theme]["window"],
                f"{theme}: scroll viewport theme mismatch",
            )
            app.geometry("1180x820+0+0")
            app.update_idletasks()
            app.update()
            require(app.action_bar.winfo_ismapped(), f"{theme}: desktop action bar missing")
            require(
                app.config_card.grid_info().get("row") == 0
                and app.config_card.grid_info().get("column") == 0,
                f"{theme}: desktop configuration-card layout changed",
            )
            if app.launch_scrollbar.winfo_ismapped():
                require(
                    app.launch_content.winfo_reqheight() > app.launch_canvas.winfo_height(),
                    f"{theme}: desktop scrollbar is visible without overflow",
                )
        finally:
            for callback_id in app.tk.call("after", "info"):
                app.after_cancel(callback_id)
            app.destroy()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", action="store_true", help="run real Tk compact-viewport checks")
    args = parser.parse_args()
    module = load_launcher_module()
    verify_contract(module)
    if args.gui:
        verify_gui(module)
    print(
        "PASS: Search Launcher small-screen layout contract"
        + (" and light/dark Tk viewport" if args.gui else "")
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
