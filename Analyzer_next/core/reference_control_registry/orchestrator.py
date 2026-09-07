"""Application service for the Reference Control Registry."""
from __future__ import annotations

from .contracts import RegistryArtifact, RegistryRepository
from .registry import build_registry, render_md


def run_registry(repository: RegistryRepository) -> RegistryArtifact:
    inputs = repository.load()
    payload = build_registry(inputs.profiles, inputs.source)
    artifact = RegistryArtifact(payload=payload, markdown=render_md(payload))
    repository.save(artifact)
    return artifact
