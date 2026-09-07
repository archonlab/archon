"""Filesystem adapter for the Reference Control Registry."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from Analyzer_next.core.reference_control_registry.contracts import RegistryArtifact, RegistryInputs


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


class FileRegistryRepository:
    def __init__(self, profiles: Path, output_json: Path, output_md: Path) -> None:
        self.profiles = profiles
        self.output_json = output_json
        self.output_md = output_md

    def load(self) -> RegistryInputs:
        return RegistryInputs(load_json(self.profiles, {}), str(self.profiles.resolve()))

    def save(self, artifact: RegistryArtifact) -> None:
        self.output_json.parent.mkdir(parents=True, exist_ok=True)
        self.output_md.parent.mkdir(parents=True, exist_ok=True)
        self.output_json.write_text(json.dumps(artifact.payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.output_md.write_text(artifact.markdown, encoding="utf-8")
