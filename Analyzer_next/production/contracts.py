"""Stable contracts for the production Analyzer DAG.

The contract is intentionally independent from the legacy coordinator.  Paths
are concrete because the incremental cache fingerprints files, while the
``products`` alias makes the producer/consumer meaning explicit to catalog
validation and migration tooling.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ANALYZER_MODES = ("intake", "scientific-refresh", "full")
STAGE_ORDER = (
    "profiles",
    "discovery",
    "mutation",
    "morphology",
    "mechanism",
    "science",
    "knowledge",
    "prediction",
    "notebook",
    "meta",
)


@dataclass(frozen=True)
class Step:
    """One declarative Analyzer process and its content dependencies."""

    label: str
    module: str
    args: tuple[str, ...]
    outputs: tuple[Path, ...] = ()
    inputs: tuple[Path, ...] = ()
    optional: bool = False
    heavy: bool = False
    stage: str = "core"
    revision: str = ""

    @property
    def products(self) -> tuple[Path, ...]:
        """Products declared by this step (compatibility name: outputs)."""
        return self.outputs

    @property
    def key(self) -> str:
        value = f"{self.stage}:{self.label}:{self.module}"
        return f"{value}:{self.revision}" if self.revision else value


def validate_step_catalog(
    steps: Sequence[Step],
    *,
    stage_order: Sequence[str] = STAGE_ORDER,
) -> None:
    """Fail closed on malformed or ambiguous production declarations."""
    known_stages = set(stage_order)
    identities: set[tuple[str, str, str]] = set()
    keys: set[str] = set()
    product_owners: dict[Path, str] = {}
    for step in steps:
        if not step.label.strip():
            raise RuntimeError("Analyzer step label must not be empty")
        if Path(step.module).name != step.module or not step.module.endswith(".py"):
            raise RuntimeError(f"Invalid Analyzer module name: {step.module!r}")
        if step.stage not in known_stages:
            raise RuntimeError(
                f"Unknown Analyzer stage {step.stage!r} for {step.label}"
            )
        identity = (step.stage, step.label, step.module)
        if identity in identities or step.key in keys:
            raise RuntimeError(f"Duplicate Analyzer step contract: {step.key}")
        identities.add(identity)
        keys.add(step.key)
        for product in step.products:
            resolved = product.resolve()
            owner = product_owners.get(resolved)
            if owner and owner != step.key:
                raise RuntimeError(
                    f"Analyzer product has multiple producers: {resolved} "
                    f"({owner}, {step.key})"
                )
            product_owners[resolved] = step.key


def downstream_steps(
    steps: Sequence[Step],
    changed_products: Iterable[Path],
) -> tuple[Step, ...]:
    """Return the transitive consumer closure in catalog execution order."""
    changed = {path.resolve() for path in changed_products}
    affected: list[Step] = []
    for step in steps:
        if any(path.resolve() in changed for path in step.inputs):
            affected.append(step)
            changed.update(path.resolve() for path in step.products)
    return tuple(affected)


__all__ = [
    "ANALYZER_MODES",
    "STAGE_ORDER",
    "Step",
    "downstream_steps",
    "validate_step_catalog",
]
