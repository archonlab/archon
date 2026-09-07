"""Collect Observer passport records needed by experiment analysis.

The legacy Observer Profile v31 parser scans only the canonical Universe Search
``observation_logs`` tree. Experiment runs launched by Observer Launcher 2.0
write their passports under ``Results/Analysis/Experiments/RuntimePackages``.
This adapter joins both evidence roots without changing the frozen legacy
parser or its scientific provenance policy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _dedupe(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for raw in paths:
        path = Path(raw)
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path.absolute())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return sorted(result, key=lambda item: str(item))


def experiment_runtime_root(results_folder: Path) -> Path:
    """Return the sibling experiment runtime root for a Universe Search root."""
    results_folder = Path(results_folder).resolve()
    return results_folder.parent / "Analysis" / "Experiments" / "RuntimePackages"


def collect_passport_json(
    results_folder: Path,
    *,
    legacy_files: Iterable[Path] = (),
) -> list[Path]:
    """Return canonical + experiment passport JSON files exactly once.

    ``legacy_files`` is intentionally injectable so the compatibility CLI can
    preserve the legacy collector's behavior first and only add the missing
    experiment evidence root.
    """
    files = list(legacy_files)
    runtime_root = experiment_runtime_root(results_folder)
    if runtime_root.is_dir():
        files.extend(runtime_root.rglob("*passport.json"))
    return _dedupe(files)


__all__ = ["collect_passport_json", "experiment_runtime_root"]
