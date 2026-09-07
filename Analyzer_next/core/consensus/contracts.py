"""Immutable requests/results and repository port for Consensus."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ConsensusPaths:
    results: Path
    root: Path
    evidence: Path
    counterexamples: Path
    database_json: Path
    database_markdown: Path
    report_json: Path
    report_markdown: Path


@dataclass(frozen=True)
class ConsensusInputs:
    evidence: dict[str, Any]
    aliases: dict[str, str]
    profiles_by_rule: dict[str, dict[str, Any]]
    counterexample_coverage: dict[str, dict[str, Any]]
    replication_context: dict[str, dict[str, Any]]
    database: dict[str, Any]


@dataclass(frozen=True)
class ConsensusRunResult:
    database: dict[str, Any]
    report: dict[str, Any]
    database_markdown: str
    report_markdown: str


class ConsensusRepository(Protocol):
    def load(self, paths: ConsensusPaths) -> ConsensusInputs:
        ...

    def save(self, paths: ConsensusPaths, result: ConsensusRunResult) -> None:
        ...
