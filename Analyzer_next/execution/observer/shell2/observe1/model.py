"""Immutable presentation model for OL2-OBSERVE1."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstrumentSection:
    title: str
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class LegacyPresentationFrame:
    sequence: int
    tick: int
    rule_id: int
    width: int
    height: int
    field: bytes
    sections: tuple[InstrumentSection, ...]
    chronicle: str
    status_bar: str
    running: bool


__all__ = ["InstrumentSection", "LegacyPresentationFrame"]
