"""Desktop path-opening adapter used by the Observer UI."""
from __future__ import annotations

from pathlib import Path
from Tools.archon_platform import open_folder
from tkinter import messagebox


def open_path(path: Path) -> None:
    if not path.exists():
        messagebox.showwarning("Path not found", str(path))
        return
    try:
        open_folder(path)
    except Exception as exc:
        messagebox.showerror("Could not open path", repr(exc))
