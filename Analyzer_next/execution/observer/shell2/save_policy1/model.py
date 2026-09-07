"""Shared human-readable save policy for Observer Launcher 2.0."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SavePolicy:
    max_ticks: int
    autosave_ticks: int
    output_dir: str
    finite_exit: bool = True

    def __post_init__(self) -> None:
        if self.max_ticks < 0:
            raise ValueError("max_ticks cannot be negative")
        if self.autosave_ticks < 0:
            raise ValueError("autosave_ticks cannot be negative")
        if not str(self.output_dir).strip():
            raise ValueError("output_dir is required")

    @property
    def periodic_text(self) -> str:
        if self.autosave_ticks == 0:
            return "Periodic save: Off"
        return f"Periodic save: Every {self.autosave_ticks:,} ticks"

    @property
    def final_text(self) -> str:
        if self.max_ticks > 0 and self.finite_exit:
            return f"Final save: Always at max ticks ({self.max_ticks:,})"
        if self.max_ticks > 0:
            return f"Final save: Runtime-dependent at {self.max_ticks:,} ticks"
        return "Final save: Save & Stop for manual-horizon runs"

    @property
    def output_text(self) -> str:
        return f"Output: {self.output_dir}"

    @property
    def compact(self) -> str:
        periodic = "off" if self.autosave_ticks == 0 else f"{self.autosave_ticks:,}"
        final = "final@max" if self.max_ticks > 0 and self.finite_exit else "manual-final"
        return f"autosave {periodic} • {final}"

    @property
    def multiline(self) -> str:
        return f"{self.final_text}\n{self.periodic_text}\n{self.output_text}"


def display_output_dir(value: str, *, project_root: Path | None = None) -> str:
    text = str(value).strip()
    path = Path(text)
    if project_root is not None and not path.is_absolute():
        try:
            return str((project_root / path).resolve())
        except OSError:
            return str(project_root / path)
    return text


__all__ = ["SavePolicy", "display_output_dir"]
