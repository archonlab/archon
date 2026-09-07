"""OL2-EXPERIMENTS-FIX6: preserve/recover Stage 6.5 authorization state."""
from __future__ import annotations

import tkinter as tk

from Analyzer_next.execution.observer.shell2.experiments_fix5.app import ObserverLauncher2ExperimentsFix5Shell


class ObserverLauncher2ExperimentsFix6Shell(ObserverLauncher2ExperimentsFix5Shell):
    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — EXPERIMENTS-FIX6")
        self.footer_hint.set(
            "EXPERIMENTS-FIX6 • durable Stage 6.5 authorization/runtime reconciliation • no auto-dispatch"
        )


__all__ = ["ObserverLauncher2ExperimentsFix6Shell"]
