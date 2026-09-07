"""Immutable inputs, outputs, paths, and repository port for discovery."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class DiscoveryPaths:
    results_root: Path
    analysis_root: Path
    knowledge_root: Path
    atlas_path: Path
    database_json: Path
    report_markdown: Path


@dataclass(frozen=True)
class DiscoveryInputs:
    rule_ids: tuple[str, ...]
    passports: dict[str, dict[str, Any]]
    atlas: dict[str, dict[str, Any]]
    questions_by_rule: dict[str, dict[str, list[dict[str, Any]]]]


@dataclass(frozen=True)
class DiscoveryRunResult:
    database: dict[str, Any]
    report_markdown: str


class DiscoveryRepository(Protocol):
    def load(self, paths: DiscoveryPaths) -> DiscoveryInputs:
        ...

    def save(self, paths: DiscoveryPaths, result: DiscoveryRunResult) -> None:
        ...
