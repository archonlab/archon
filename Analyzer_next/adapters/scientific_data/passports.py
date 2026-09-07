from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from Analyzer_next.core.scientific_data.ids import normalize_rule_id
from .io import read_text


PassportRecord = dict[str, Any]
PassportsByRule = dict[str, list[PassportRecord]]


def _first_number(
    text: str | None,
    *,
    as_float: bool = False,
) -> int | float | None:
    if not text:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", str(text).replace(",", ""))
    if not match:
        return None

    return float(match.group(0)) if as_float else int(float(match.group(0)))


def _parse_block(
    rule: str,
    block: str,
    *,
    source_index: int,
) -> PassportRecord:
    data: PassportRecord = {
        "rule": rule,
        "source_index": source_index,
        "lifetime": None,
        "classification": None,
        "dynamic_score": None,
        "breathing_score": None,
        "collapse": None,
        "objects": None,
        "split_birth": None,
        "merge_death": None,
    }

    def grab(labels: list[str]) -> str | None:
        for label in labels:
            match = re.search(
                rf"-\s*{re.escape(label)}:\s*\*\*([^*]+)\*\*",
                block,
                re.I,
            )
            if match:
                return match.group(1).strip()

            match = re.search(
                rf"^\s*{re.escape(label)}:\s*(.+)$",
                block,
                re.I | re.M,
            )
            if match:
                return match.group(1).strip()

        return None

    data["lifetime"] = _first_number(
        grab(["Lifetime", "Longest observed age", "Last alive tick"])
    )
    data["classification"] = grab(["Classification"])
    data["dynamic_score"] = _first_number(
        grab(["Dynamic score", "Dynamic attractor score"]),
        as_float=True,
    )
    data["breathing_score"] = _first_number(
        grab(["Breathing score"]),
        as_float=True,
    )
    data["collapse"] = grab(["Collapse", "Collapse tick"])
    data["objects"] = grab(["Objects", "Object range"])
    data["split_birth"] = _first_number(grab(["Split/birth events"]))
    data["merge_death"] = _first_number(grab(["Merge/death events"]))

    events = grab(["Events"])
    if events:
        split = re.search(r"split/birth\s*=\s*(\d+)", events, re.I)
        merge = re.search(r"merge/death\s*=\s*(\d+)", events, re.I)

        if split:
            data["split_birth"] = int(split.group(1))
        if merge:
            data["merge_death"] = int(merge.group(1))

    collapse = str(data["collapse"]).strip().lower()
    if collapse in {"none", "null", "no", "false"}:
        data["collapse"] = "No"

    return data


def load_passport_records(path: Path | None) -> list[PassportRecord]:
    """Load every passport section without collapsing records by rule."""
    if not path or not path.exists():
        return []

    text = read_text(path)
    matches = list(
        re.finditer(
            r"(?mi)^\s*(?:#+\s*)?Rule\s+(\d+)\s*$",
            text,
        )
    )

    records: list[PassportRecord] = []

    for index, match in enumerate(matches):
        rule = normalize_rule_id(match.group(1))
        if not rule:
            continue

        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        records.append(
            _parse_block(
                rule,
                text[start:end],
                source_index=index,
            )
        )

    return records


def group_passports_by_rule(
    records: Iterable[PassportRecord],
) -> PassportsByRule:
    """Group all passport records by canonical rule id."""
    grouped: defaultdict[str, list[PassportRecord]] = defaultdict(list)

    for item in records:
        rule = normalize_rule_id(item.get("rule") or item.get("rule_id"))
        if not rule:
            continue

        row = dict(item)
        row["rule"] = rule
        grouped[rule].append(row)

    return dict(grouped)


def _passport_rank(item: PassportRecord) -> tuple[float, int, int]:
    """
    Rank passports for the backward-compatible best-record view.

    Preference order:
    1. longest lifetime;
    2. most populated fields;
    3. later source section.
    """
    lifetime = item.get("lifetime")
    try:
        lifetime_score = float(lifetime) if lifetime is not None else -1.0
    except (TypeError, ValueError):
        lifetime_score = -1.0

    populated = sum(value is not None for value in item.values())

    source_index = item.get("source_index")
    try:
        source_score = int(source_index)
    except (TypeError, ValueError):
        source_score = -1

    return lifetime_score, populated, source_score


def select_best_passports(
    grouped: PassportsByRule,
) -> dict[str, PassportRecord]:
    """Select one representative passport per rule for legacy consumers."""
    best: dict[str, PassportRecord] = {}

    for rule_id, records in grouped.items():
        if records:
            best[rule_id] = max(records, key=_passport_rank)

    return best


def load_passports(path: Path | None) -> dict[str, PassportRecord]:
    """
    Backward-compatible loader returning the best passport per rule.

    New code should prefer load_passport_records() and
    group_passports_by_rule().
    """
    records = load_passport_records(path)
    return select_best_passports(group_passports_by_rule(records))
