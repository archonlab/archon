"""Mirror canonical Analyzer intake products into one results workspace."""
from __future__ import annotations

from pathlib import Path


MIRRORED_INPUT_NAMES = (
    "passport_analysis.md",
    "research_questions.md",
)


def mirror_inputs(
    results_dir: Path,
    *,
    analysis_results_dir: Path,
) -> tuple[Path, ...]:
    """Refresh compatibility inputs, preferring links with a copy fallback."""
    mirrored: list[Path] = []
    for name in MIRRORED_INPUT_NAMES:
        source = analysis_results_dir / name
        destination = results_dir / name
        if not source.exists():
            continue
        try:
            if destination.exists() or destination.is_symlink():
                destination.unlink()
            destination.symlink_to(source)
        except OSError:
            destination.write_bytes(source.read_bytes())
        mirrored.append(destination)
    return tuple(mirrored)


__all__ = ["MIRRORED_INPUT_NAMES", "mirror_inputs"]
