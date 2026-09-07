"""Pure passport-analysis parsing for Research Notebook Engine v4."""
from __future__ import annotations

import re
from typing import Any


def first_number(text: Any, as_float: bool = False) -> int | float | None:
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(text).replace(",", ""))
    if not match:
        return None
    return float(match.group(0)) if as_float else int(float(match.group(0)))


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("**", "").replace("`", "").strip()
    return text if text else None


def parse_passport_block(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {
        "rule": None,
        "lifetime": None,
        "classification": None,
        "dynamic_score": None,
        "breathing_score": None,
        "collapse": None,
        "objects": None,
        "split_birth": None,
        "merge_death": None,
    }
    match = re.search(r"(?:##\s*)?Rule\s+(\d+)", text, re.I)
    if not match:
        match = re.search(r"\|\s*(\d{3,5})\s*\|", text)
    if match:
        data["rule"] = match.group(1).zfill(5)

    def grab_any(labels: list[str]) -> str | None:
        for label in labels:
            found = re.search(
                rf"-\s*{re.escape(label)}:\s*\*\*([^*]+)\*\*",
                text,
                re.I,
            )
            if found:
                return clean(found.group(1))
            found = re.search(
                rf"^\s*{re.escape(label)}:\s*(.+)$",
                text,
                re.I | re.M,
            )
            if found:
                return clean(found.group(1))
        return None

    data["lifetime"] = first_number(
        grab_any(["Lifetime", "Longest observed age", "Last alive tick"])
    )
    data["classification"] = grab_any(["Classification"])
    data["collapse"] = grab_any(["Collapse", "Collapse tick"])
    data["objects"] = grab_any(["Objects", "Object range"])
    data["dynamic_score"] = first_number(
        grab_any(["Dynamic score", "Dynamic attractor score"]),
        as_float=True,
    )
    data["breathing_score"] = first_number(
        grab_any(["Breathing score"]),
        as_float=True,
    )
    split = grab_any(["Split/birth events"])
    merge = grab_any(["Merge/death events"])
    if split is not None:
        data["split_birth"] = first_number(split)
    if merge is not None:
        data["merge_death"] = first_number(merge)
    events = grab_any(["Events"])
    if events:
        split_match = re.search(r"split/birth\s*=\s*(\d+)", events, re.I)
        merge_match = re.search(r"merge/death\s*=\s*(\d+)", events, re.I)
        if split_match:
            data["split_birth"] = int(split_match.group(1))
        if merge_match:
            data["merge_death"] = int(merge_match.group(1))
    if data["collapse"] in {"None", "none", "null"}:
        data["collapse"] = "No"
    return data


def parse_passport_analysis(text: str) -> list[dict[str, Any]]:
    """Return one longest/latest analysis record for every rule."""
    starts = list(
        re.finditer(r"(?mi)^\s*(?:##\s*)?Rule\s+(\d{1,5})\s*$", text)
    )
    if not starts:
        record = parse_passport_block(text)
        return [record] if record.get("rule") else []
    by_rule: dict[str, dict[str, Any]] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        record = parse_passport_block(text[match.start():end])
        rule = record.get("rule")
        previous = by_rule.get(rule)
        if rule and (
            previous is None
            or (record.get("lifetime") or 0) >= (previous.get("lifetime") or 0)
        ):
            by_rule[rule] = record
    return [by_rule[rule] for rule in sorted(by_rule)]


__all__ = ["clean", "first_number", "parse_passport_analysis", "parse_passport_block"]
