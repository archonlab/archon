"""Desktop path-opening adapter isolated from the OL2 presentation shell."""
from __future__ import annotations

from pathlib import Path
from Tools.archon_platform import open_folder


class DesktopPathOpener:
    def open(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(str(resolved))
        open_folder(resolved)



__all__ = ["DesktopPathOpener"]
