"""Pure filtering and sorting for CONFIG1 canonical worlds."""
from __future__ import annotations

from typing import Iterable

from .model import WorldRecord


def filter_worlds(
    worlds: Iterable[WorldRecord],
    *,
    query: str = "",
    world_class: str = "All",
    status: str = "All",
    sort: str = "Rule ID",
) -> tuple[WorldRecord, ...]:
    query_text = query.strip().lower()
    rows = []
    for world in worlds:
        haystack = " ".join(
            (
                world.display_id,
                world.world_class,
                str(world.genome_hash or ""),
            )
        ).lower()
        if query_text and query_text not in haystack:
            continue
        if world_class != "All" and world.world_class != world_class:
            continue
        if status == "Verified" and not world.source_verified:
            continue
        if status == "Needs source" and world.source_verified:
            continue
        if status == "Observed" and not world.observed:
            continue
        if status == "Not observed" and world.observed:
            continue
        rows.append(world)
    if sort == "Score high":
        rows.sort(
            key=lambda item: (
                item.score if item.score is not None else float("-inf")
            ),
            reverse=True,
        )
    elif sort == "Score low":
        rows.sort(
            key=lambda item: (
                item.score if item.score is not None else float("inf")
            )
        )
    elif sort == "Last run":
        rows.sort(key=lambda item: item.last_run, reverse=True)
    else:
        rows.sort(key=lambda item: item.rule_id)
    return tuple(rows)
