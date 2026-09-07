"""Ports and immutable values for composition-template analysis."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class CompositionTemplatePaths:
    results_root: Path


@dataclass(frozen=True)
class CompositionTemplateInputs:
    mechanism_registry: dict[str, Any]
    composition_registry: dict[str, Any]
    rule_map: dict[str, Any]


@dataclass(frozen=True)
class CompositionTemplateRunResult:
    template_registry: dict[str, Any]
    instance_registry: dict[str, Any]
    template_rule_map: dict[str, Any]
    report: dict[str, Any]


class CompositionTemplateRepository(Protocol):
    def load(
        self,
        paths: CompositionTemplatePaths,
    ) -> CompositionTemplateInputs: ...

    def save(
        self,
        paths: CompositionTemplatePaths,
        result: CompositionTemplateRunResult,
    ) -> None: ...
