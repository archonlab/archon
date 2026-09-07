"""Pure helpers for OL2-FUNCTIONS1A world search semantics."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorldSearchIntent:
    raw: str
    normalized: str
    numeric_rule_id: int | None
    canonical_display_id: str | None


def parse_world_search(query: str) -> WorldSearchIntent:
    """Normalize one UI query without changing its matching semantics.

    Numeric queries keep their original text for broad substring filtering, but
    expose a canonical five-digit identity so an exact rule can be ranked first.
    ``251``, ``0251`` and ``00251`` therefore all identify rule 251 without
    silently selecting it.
    """

    raw = str(query)
    normalized = raw.strip()
    numeric_rule_id: int | None = None
    canonical_display_id: str | None = None
    if normalized.isdigit():
        try:
            value = int(normalized, 10)
        except ValueError:
            value = -1
        if 0 <= value <= 99_999:
            numeric_rule_id = value
            canonical_display_id = f"{value:05d}"
    return WorldSearchIntent(
        raw=raw,
        normalized=normalized,
        numeric_rule_id=numeric_rule_id,
        canonical_display_id=canonical_display_id,
    )


def is_fresh_review_for_world(review, world) -> bool:
    """Fail closed unless every immutable review identity names the same world."""

    if review is None or not getattr(review, "valid", False):
        return False
    prepared = getattr(review, "prepared", None)
    if prepared is None or world is None or not getattr(world, "source_verified", False):
        return False
    try:
        expected = int(world.rule_id)
        return (
            int(review.draft.world.rule_id) == expected
            and int(prepared.effective_draft.world.rule_id) == expected
            and int(prepared.run_spec.rule_id) == expected
        )
    except (AttributeError, TypeError, ValueError):
        return False


__all__ = ["WorldSearchIntent", "is_fresh_review_for_world", "parse_world_search"]
