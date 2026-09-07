"""Save-policy transformations that preserve reviewed scientific identity."""
from __future__ import annotations

from dataclasses import replace
import shlex

from Analyzer_next.execution.observer.shell2.config1.model import (
    PreparedConfiguration,
    canonical_hash,
)


def with_autosave_ticks(prepared: PreparedConfiguration, autosave_ticks: int) -> PreparedConfiguration:
    """Return the same selected mutation launch with only autosave cadence changed.

    Mutation identity, RunSpec, rule/manifest arguments and output directory stay
    frozen.  Autosave is a launcher/runtime checkpoint policy and is represented
    in the effective draft, normalized command, and a fresh review hash.
    """
    ticks = int(autosave_ticks)
    if ticks < 0:
        raise ValueError("Autosave ticks cannot be negative")
    if ticks == int(prepared.effective_draft.autosave_every):
        return prepared

    command = list(prepared.command)
    try:
        index = command.index("--autosave-every")
    except ValueError as exc:
        raise ValueError("prepared command has no autosave checkpoint contract") from exc
    if index + 1 >= len(command):
        raise ValueError("prepared command has malformed autosave checkpoint contract")
    command[index + 1] = str(ticks)

    effective = replace(prepared.effective_draft, autosave_every=ticks)
    review_hash = canonical_hash({
        "base_review_hash": prepared.review_hash,
        "autosave_every": ticks,
        "command": command,
    })
    return replace(
        prepared,
        effective_draft=effective,
        command=tuple(command),
        command_text=shlex.join(command),
        review_hash=review_hash,
    )


__all__ = ["with_autosave_ticks"]
