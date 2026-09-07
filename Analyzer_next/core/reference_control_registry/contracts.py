"""Ports for the Reference Control Registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class RegistryInputs:
    profiles: Any
    source: str


@dataclass(frozen=True)
class RegistryArtifact:
    payload: dict[str, Any]
    markdown: str


class RegistryRepository(Protocol):
    def load(self) -> RegistryInputs: ...
    def save(self, artifact: RegistryArtifact) -> None: ...
