#!/usr/bin/env python3
"""Canonical ownership contract for Python processes started by ARCHON.

Interpreter paths are made absolute but are deliberately *not* resolved through
symlinks. A virtual environment's ``bin/python`` is commonly a symlink; replacing
it with its physical Homebrew/system target discards the virtual environment.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable, Mapping

ENV_NAME = "ARCHON_RUNTIME_PYTHON"
PROPAGATED_ENV_NAME = "ARCHON_PYTHON_EXECUTABLE"
SOURCE_ENV_NAME = "ARCHON_PYTHON_SOURCE"


@dataclass(frozen=True, slots=True)
class RuntimePythonSelection:
    command: tuple[str, ...]
    executable: str
    source: str


def _candidate_paths(root: Path, *, windows: bool | None = None) -> Iterable[Path]:
    runtime = root / "Runtime" / "python"
    is_windows = os.name == "nt" if windows is None else windows
    if is_windows:
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


def _absolute_without_dereference(value: str | os.PathLike[str]) -> str:
    """Return an absolute spelling while preserving a venv interpreter symlink."""
    return os.path.abspath(os.path.expanduser(os.fspath(value)))


def _selection(path: Path | str, source: str) -> RuntimePythonSelection:
    executable = _absolute_without_dereference(path)
    return RuntimePythonSelection((executable,), executable, source)


def runtime_python_selection(
    root: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> RuntimePythonSelection:
    """Select configured, propagated, packaged, inherited, then PATH Python."""
    env = os.environ if environ is None else environ
    project = Path(_absolute_without_dereference(root))

    explicit = str(env.get(ENV_NAME, "")).strip()
    if explicit:
        path = Path(_absolute_without_dereference(explicit))
        if not _valid_file(path):
            raise RuntimeError(f"{ENV_NAME} points to a missing interpreter: {path}")
        return _selection(path, "configured")

    propagated = str(env.get(PROPAGATED_ENV_NAME, "")).strip()
    if propagated:
        path = Path(_absolute_without_dereference(propagated))
        if not _valid_file(path):
            raise RuntimeError(f"{PROPAGATED_ENV_NAME} points to a missing interpreter: {path}")
        inherited_source = str(env.get(SOURCE_ENV_NAME, "")).strip()
        source = inherited_source if inherited_source in {"configured", "packaged", "inherited"} else "inherited"
        return _selection(path, source)

    for path in _candidate_paths(project):
        if _valid_file(path):
            return _selection(path, "packaged")

    # Do not dereference this path. On macOS .venv/bin/python is normally a
    # symlink to Homebrew Python and the spelling owns the virtual environment.
    if not getattr(sys, "frozen", False):
        executable = Path(_absolute_without_dereference(sys.executable))
        if _valid_file(executable):
            return _selection(executable, "inherited")

    names = ("python", "python3") if os.name == "nt" else ("python3", "python")
    for name in names:
        found = shutil.which(name)
        if found:
            return _selection(found, "path_fallback")

    if os.name == "nt":
        py = shutil.which("py")
        if py:
            executable = _absolute_without_dereference(py)
            return RuntimePythonSelection((executable, "-3"), executable, "path_fallback")

    raise RuntimeError(
        "No Python 3 runtime is available for ARCHON child processes. "
        f"Set {ENV_NAME} or install/bundle Python in Runtime/python."
    )


def runtime_python_command(root: Path) -> list[str]:
    """Compatibility API returning the canonical interpreter command prefix."""
    return list(runtime_python_selection(root).command)


def runtime_python_environment(
    root: Path,
    base: Mapping[str, str] | None = None,
    *,
    selection: RuntimePythonSelection | None = None,
) -> dict[str, str]:
    """Copy an environment and propagate interpreter ownership downstream."""
    env = dict(os.environ if base is None else base)
    selected = selection or runtime_python_selection(root, environ=env)
    env[PROPAGATED_ENV_NAME] = selected.executable
    env[SOURCE_ENV_NAME] = selected.source
    return env


def probe_runtime_python(selection: RuntimePythonSelection) -> dict[str, str]:
    """Report the identity of the interpreter that will actually run children."""
    script = (
        "import json,platform,sys;"
        "print(json.dumps({'executable':sys.executable,'version':platform.python_version(),"
        "'prefix':sys.prefix,'base_prefix':sys.base_prefix}))"
    )
    try:
        result = subprocess.run(
            [*selection.command, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        payload = json.loads(result.stdout.strip()) if result.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        payload = {}
    return {
        "executable": selection.executable,
        "version": str(payload.get("version") or "unavailable"),
        "reported_executable": str(payload.get("executable") or ""),
        "prefix": str(payload.get("prefix") or ""),
        "base_prefix": str(payload.get("base_prefix") or ""),
        "source": selection.source,
    }


def runtime_python_display(root: Path) -> str:
    return " ".join(runtime_python_command(root))
