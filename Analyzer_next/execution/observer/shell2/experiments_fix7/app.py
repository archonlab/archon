"""OL2-EXPERIMENTS-FIX7: canonical SQLite identity for queued experiment rows."""
from __future__ import annotations

import tkinter as tk

from Analyzer_next.execution.observer.shell2.experiments_fix6.app import ObserverLauncher2ExperimentsFix6Shell


class ObserverLauncher2ExperimentsFix7Shell(ObserverLauncher2ExperimentsFix6Shell):
    def __init__(self, root: tk.Tk, *args, **kwargs) -> None:
        super().__init__(root, *args, **kwargs)
        self.root.title("ARCHON Observer Launcher 2.0 — EXPERIMENTS-FIX7")
        self.footer_hint.set(
            "EXPERIMENTS-FIX7 • per-row file outputs + canonical experiment SQLite identity • no auto-dispatch"
        )


__all__ = ["ObserverLauncher2ExperimentsFix7Shell"]
