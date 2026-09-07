from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from Analyzer_next.core.scientific_data.ids import normalize_rule_id
from .io import load_json


AtlasRecord = dict[str, Any]
AtlasByRule = dict[str, list[AtlasRecord]]


def _extract_candidates(payload: Any) -> list[AtlasRecord]:
    """Extract atlas records from supported legacy and current schemas."""
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    candidates: list[AtlasRecord] = []

    for key in ("experiments", "records", "profiles", "rules"):
        value = payload.get(key)

        if isinstance(value, list):
            candidates.extend(
                dict(item)
                for item in value
                if isinstance(item, dict)
            )
            continue

        if isinstance(value, dict):
            for raw_rule, item in value.items():
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                row.setdefault("rule", raw_rule)
                candidates.append(row)

    return candidates


def _normalized_record(item: AtlasRecord) -> AtlasRecord | None:
    """Return a shallow copy with a canonical five-digit rule id."""
    rule = normalize_rule_id(item.get("rule") or item.get("rule_id"))
    if not rule:
        return None

    row = dict(item)
    row["rule"] = rule
    return row


def load_atlas_experiments(path: Path) -> list[AtlasRecord]:
    """Load every atlas experiment without collapsing records by rule."""
    payload = load_json(path, {})
    records: list[AtlasRecord] = []

    for item in _extract_candidates(payload):
        normalized = _normalized_record(item)
        if normalized is not None:
            records.append(normalized)

    return records


def group_atlas_by_rule(records: Iterable[AtlasRecord]) -> AtlasByRule:
    """Group all experiment records by canonical rule id."""
    grouped: defaultdict[str, list[AtlasRecord]] = defaultdict(list)

    for item in records:
        normalized = _normalized_record(item)
        if normalized is not None:
            grouped[normalized["rule"]].append(normalized)

    return dict(grouped)


def _record_rank(item: AtlasRecord) -> tuple[float, float, int]:
    """
    Rank records for the backward-compatible current-record view.

    Preference order:
    1. longest observed lifetime/tick;
    2. newest generated/updated timestamp when present;
    3. most populated record.
    """
    lifetime_fields = (
        "lifetime",
        "max_tick",
        "last_tick",
        "ticks",
        "age",
        "longest_observed_age",
    )

    lifetime = 0.0
    for key in lifetime_fields:
        value = item.get(key)
        try:
            if value is not None:
                lifetime = max(lifetime, float(value))
        except (TypeError, ValueError):
            pass

    timestamp_fields = (
        "updated_at",
        "generated_at",
        "generated",
        "created_at",
        "created",
        "timestamp",
    )
    timestamp_score = 0.0
    for index, key in enumerate(timestamp_fields, start=1):
        if item.get(key):
            timestamp_score = float(len(timestamp_fields) - index + 1)
            break

    populated = sum(value is not None for value in item.values())
    return lifetime, timestamp_score, populated


def select_current_atlas_records(
    grouped: AtlasByRule,
) -> dict[str, AtlasRecord]:
    """
    Select one representative record per rule for legacy consumers.

    This is intentionally separate from the complete experiment history.
    """
    current: dict[str, AtlasRecord] = {}

    for rule_id, records in grouped.items():
        if records:
            current[rule_id] = max(records, key=_record_rank)

    return current


def load_atlas_records(path: Path) -> dict[str, AtlasRecord]:
    """
    Backward-compatible loader returning one representative record per rule.

    New code should prefer load_atlas_experiments() and group_atlas_by_rule().
    """
    experiments = load_atlas_experiments(path)
    return select_current_atlas_records(group_atlas_by_rule(experiments))
