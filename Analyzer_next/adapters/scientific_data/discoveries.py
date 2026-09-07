from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from Analyzer_next.core.scientific_data.ids import normalize_rule_id
from .io import load_json, read_text


Discovery = dict[str, Any]
DiscoveriesByRule = dict[str, list[Discovery]]


def _normalize_discovery_list(value: Any) -> list[Discovery]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]

    if isinstance(value, dict):
        discoveries = value.get("discoveries", [])
        if isinstance(discoveries, list):
            return [
                dict(item)
                for item in discoveries
                if isinstance(item, dict)
            ]

    return []


def _merge_discoveries(
    target: DiscoveriesByRule,
    rule_id: str,
    discoveries: list[Discovery],
) -> None:
    if not discoveries:
        return

    bucket = target.setdefault(rule_id, [])
    seen = {
        (
            str(item.get("id")),
            str(item.get("title")),
            str(item.get("finding")),
        )
        for item in bucket
    }

    for item in discoveries:
        fingerprint = (
            str(item.get("id")),
            str(item.get("title")),
            str(item.get("finding")),
        )
        if fingerprint not in seen:
            bucket.append(item)
            seen.add(fingerprint)


def _parse_markdown_report(
    path: Path,
) -> tuple[str | None, list[Discovery]]:
    text = read_text(path)

    rule_match = re.search(
        r"Rule:\s*\*\*([^*]+)\*\*",
        text,
        re.I,
    )
    if not rule_match:
        rule_match = re.search(
            r"(?mi)^\s*Rule:\s*(.+?)\s*$",
            text,
        )

    rule = normalize_rule_id(rule_match.group(1)) if rule_match else None

    discoveries: list[Discovery] = []

    for match in re.finditer(
        r"###\s+(D\d+):\s+(.+?)\n\n(.+?)(?=\n###|\n##|\Z)",
        text,
        re.S,
    ):
        block = match.group(3)

        impact_match = re.search(
            r"Impact:\s*\*\*(.+?)\*\*",
            block,
        )
        confidence_match = re.search(
            r"Confidence:\s*\*\*(.+?)\*\*",
            block,
        )
        finding_match = re.search(
            r"(?mi)^Finding:\s*(.+)$",
            block,
        )
        next_test_match = re.search(
            r"Next test:\s*\*\*(.+?)\*\*",
            block,
        )

        impact_text = impact_match.group(1) if impact_match else ""

        discoveries.append(
            {
                "id": match.group(1),
                "title": match.group(2).strip(),
                "impact": (
                    impact_text.count("★")
                    or impact_text.count("*")
                    or None
                ),
                "confidence": (
                    confidence_match.group(1).strip()
                    if confidence_match
                    else None
                ),
                "finding": (
                    finding_match.group(1).strip()
                    if finding_match
                    else None
                ),
                "next_test": (
                    next_test_match.group(1).strip()
                    if next_test_match
                    else None
                ),
                "source_file": str(path),
            }
        )

    return rule, discoveries


def _load_json_discoveries(path: Path) -> DiscoveriesByRule:
    payload = load_json(path, {})
    if not isinstance(payload, dict) or not payload:
        return {}

    raw = payload.get("discoveries_by_rule") or payload.get("rules")
    if not isinstance(raw, dict):
        return {}

    out: DiscoveriesByRule = {}

    for raw_rule, value in raw.items():
        rule = normalize_rule_id(raw_rule)

        if not rule and isinstance(value, dict):
            rule = normalize_rule_id(
                value.get("rule") or value.get("rule_id")
            )

        if not rule:
            continue

        discoveries = _normalize_discovery_list(value)

        for item in discoveries:
            item.setdefault("rule", rule)
            item.setdefault("source_file", str(path))

        _merge_discoveries(out, rule, discoveries)

    return out


def load_discoveries(
    results_root: Path,
    analysis_root: Path,
) -> DiscoveriesByRule:
    """
    Load discoveries from canonical JSON sources, with Markdown fallback.

    Rule ids are normalized consistently across all supported schemas.
    """
    json_candidates = (
        results_root / "discovery_database.json",
        analysis_root / "discovery_database.json",
        results_root / "discovery_report.json",
        analysis_root / "discovery_report.json",
    )

    merged: DiscoveriesByRule = {}

    for path in json_candidates:
        if not path.exists():
            continue

        loaded = _load_json_discoveries(path)
        for rule_id, discoveries in loaded.items():
            _merge_discoveries(merged, rule_id, discoveries)

    if merged:
        return merged

    for path in (
        results_root / "discovery_report.md",
        analysis_root / "discovery_report.md",
    ):
        if not path.exists():
            continue

        rule, discoveries = _parse_markdown_report(path)
        if rule:
            _merge_discoveries(merged, rule, discoveries)

    return merged
