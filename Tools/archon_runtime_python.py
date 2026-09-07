#!/usr/bin/env python3
"""Resolve the Python interpreter used by ARCHON child processes.

Source releases normally reuse the interpreter that launched Studio. Packaged
releases may bundle a private interpreter and advertise it through
ARCHON_RUNTIME_PYTHON or the canonical Runtime/python layout.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from typing import Iterable

ENV_NAME = "ARCHON_RUNTIME_PYTHON"


def _candidate_paths(root: Path) -> Iterable[Path]:
    runtime = root / "Runtime" / "python"
    if os.name == "nt":
        yield runtime / "python.exe"
        yield runtime / "python3.exe"
        yield root / "Runtime" / "python.exe"
    else:
        yield runtime / "bin" / "python3"
        yield runtime / "bin" / "python"
        yield root / "Runtime" / "python3"
        yield root / "Runtime" / "python"


def _valid_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def runtime_python_command(root: Path) -> list[str]:
    """Return the command prefix for the interpreter that runs ARCHON scripts."""
    root = root.resolve()
    explicit = os.environ.get(ENV_NAME, "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not _valid_file(path):
            raise RuntimeError(f"{ENV_NAME} points to a missing interpreter: {path}")
        return [str(path.resolve())]

    for path in _candidate_paths(root):
        if _valid_file(path):
            return [str(path.resolve())]

    # In a source checkout sys.executable is the most reliable interpreter.
    # Frozen application launchers are not Python interpreters, so never feed
    # child .py files back into a frozen executable.
    if not getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        if _valid_file(executable):
            return [str(executable.resolve())]

    # Last-resort PATH lookup is useful for relocatable source trees.
    for name in (("python3", "python") if os.name != "nt" else ("python", "python3")):
        found = shutil.which(name)
        if found:
            return [str(Path(found).resolve())]

    # Windows' py launcher is a command dispatcher, not a direct interpreter.
    if os.name == "nt":
        py = shutil.which("py")
        if py:
            return [str(Path(py).resolve()), "-3"]

    raise RuntimeError(
        "No Python 3 runtime is available for ARCHON child processes. "
        f"Set {ENV_NAME} or install/bundle Python in Runtime/python."
    )


def runtime_python_display(root: Path) -> str:
    return " ".join(runtime_python_command(root))
