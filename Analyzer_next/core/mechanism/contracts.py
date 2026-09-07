"""Immutable paths, inputs, results, and repository port for mechanisms."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class MechanismPaths:
    results_root: Path
    analysis_root: Path
    knowledge_root: Path
    world_atlas_root: Path
    output_directory: Path
    aggregate_json: Path


@dataclass(frozen=True)
class RuleSource:
    path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class MechanismInputs:
    aliases: dict[str, str]
    behaviours: tuple[dict[str, Any], ...]
    rule_sources: dict[str, RuleSource]
    rule_errors: dict[str, str]
    rule_deferred: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MechanismRunResult:
    aggregate: dict[str, Any]
    reports: dict[Path, str]
    status_lines: tuple[str, ...]


class MechanismRepository(Protocol):
    def load(
        self,
        paths: MechanismPaths,
        *,
        selected_rule: str | None = None,
    ) -> MechanismInputs:
        ...

    def save(
        self,
        paths: MechanismPaths,
        result: MechanismRunResult,
    ) -> None:
        ...
