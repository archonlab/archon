"""Pure duplicate-rule alias canonicalization."""
from __future__ import annotations

import json
from typing import Any

from Analyzer_next.core.scientific_data.ids import normalize_rule_id


ALIAS_SCHEMA = "archon_duplicate_rule_aliases_v1"
RULE_REFERENCE_KEYS = {
    "rule", "rule_id", "rule_ids", "rules",
    "target_rule", "target_rules",
    "seed_rule", "seed_rules",
    "parent_a", "parent_b",
    "canonical_rule_id",
}
RULE_KEYED_MAPS = {
    "observations",
    "rules_by_id",
    "profiles_by_rule",
}


def _canonical_rule_id_generic(
    value: Any,
    aliases: dict[str, str],
) -> str | None:
    try:
        current = f"{int(str(value)):05d}"
    except Exception:
        return None
    seen: set[str] = set()
    while current in aliases and current not in seen:
        seen.add(current)
        current = aliases[current]
    return current


def _merge_alias_values(left: Any, right: Any) -> Any:
    if left is None:
        return right
    if right is None:
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        for key, value in right.items():
            if key in merged:
                merged[key] = _merge_alias_values(merged[key], value)
            else:
                merged[key] = value
        return merged
    if isinstance(left, list) and isinstance(right, list):
        merged = []
        seen = set()
        for value in [*left, *right]:
            marker = (
                json.dumps(value, sort_keys=True, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else repr(value)
            )
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(value)
        return merged
    return right


def canonicalize_rule_references(
    node: Any,
    aliases: dict[str, str],
    *,
    parent_key: str = "",
) -> Any:
    key_l = str(parent_key).lower()
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            new_key = str(key)
            if key_l in RULE_KEYED_MAPS:
                canonical_key = _canonical_rule_id_generic(key, aliases)
                if canonical_key:
                    new_key = canonical_key
            rewritten = canonicalize_rule_references(
                value,
                aliases,
                parent_key=str(key),
            )
            if new_key in out:
                out[new_key] = _merge_alias_values(out[new_key], rewritten)
            else:
                out[new_key] = rewritten
        return out
    if isinstance(node, list):
        rewritten = [
            canonicalize_rule_references(
                value,
                aliases,
                parent_key=parent_key,
            )
            for value in node
        ]
        if key_l in {"rules", "rule_ids", "target_rules", "seed_rules"}:
            deduped = []
            seen = set()
            for value in rewritten:
                marker = repr(value)
                if marker in seen:
                    continue
                seen.add(marker)
                deduped.append(value)
            return deduped
        return rewritten
    if key_l in RULE_REFERENCE_KEYS:
        canonical = _canonical_rule_id_generic(node, aliases)
        return canonical if canonical else node
    return node


def canonical_rule_id(value: Any, aliases: dict[str, str]) -> str | None:
    current = normalize_rule_id(value)
    if not current:
        return None
    seen: set[str] = set()
    while current in aliases and current not in seen:
        seen.add(current)
        current = aliases[current]
    return current


def canonical_rule_set(values: Any, aliases: dict[str, str]) -> set[str]:
    out: set[str] = set()
    for value in values or []:
        rule_id = canonical_rule_id(value, aliases)
        if rule_id:
            out.add(rule_id)
    return out
