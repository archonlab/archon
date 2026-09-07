"""Canonicalize duplicate Atlas rule aliases in declared DAG products.

The production coordinator applies this repair only after a successful step
and before the incremental DAG fingerprints its products. The implementation
is independent from ``Analyzer.alias_integrity_audit`` so the modular
execution path does not acquire a second legacy import boundary.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ALIAS_CANONICAL_PRODUCT_NAMES = frozenset({
    "knowledge_base.json",
    "research_atlas.json",
    "consensus_database.json",
    "general_principles.json",
    "predictions.json",
    "validation_report.json",
    "cohort_report.json",
    "cohort_targets.json",
    "experiment_plan.json",
    "research_director_report.json",
    "next_research_actions.json",
})
RULE_KEY_HINTS = frozenset({
    "rule",
    "rule_id",
    "rule_ids",
    "rules",
    "target_rule",
    "target_rules",
    "seed_rule",
    "seed_rules",
    "parent_a",
    "parent_b",
    "canonical_rule_id",
})
RULE_KEYED_MAPS = frozenset({
    "observations",
    "rules_by_id",
    "profiles_by_rule",
})
RULE_ID_LISTS = frozenset({
    "rules",
    "rule_ids",
    "target_rules",
    "seed_rules",
})


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def normalize_rule_id(value: Any) -> str | None:
    try:
        return f"{int(str(value)):05d}"
    except Exception:
        return None


def _atomic_write_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _merge_values(left: Any, right: Any) -> Any:
    if left is None:
        return right
    if right is None:
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        for key, value in right.items():
            merged[key] = (
                _merge_values(merged[key], value)
                if key in merged
                else value
            )
        return merged
    if isinstance(left, list) and isinstance(right, list):
        merged: list[Any] = []
        seen: set[str] = set()
        for value in (*left, *right):
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


def canonicalize_product(
    node: Any,
    aliases: Mapping[str, str],
    *,
    parent_key: str = "",
) -> tuple[Any, int]:
    """Rewrite structured rule references and return the change count."""
    changes = 0
    key_lower = str(parent_key).lower()

    if isinstance(node, dict):
        rewritten_map: dict[str, Any] = {}
        for key, value in node.items():
            new_key = str(key)
            if key_lower in RULE_KEYED_MAPS:
                old_id = normalize_rule_id(key)
                if old_id in aliases:
                    new_key = aliases[old_id]
                    changes += 1
            rewritten, child_changes = canonicalize_product(
                value,
                aliases,
                parent_key=str(key),
            )
            changes += child_changes
            if new_key in rewritten_map:
                rewritten_map[new_key] = _merge_values(
                    rewritten_map[new_key],
                    rewritten,
                )
                changes += 1
            else:
                rewritten_map[new_key] = rewritten
        return rewritten_map, changes

    if isinstance(node, list):
        rewritten_list: list[Any] = []
        seen: set[str] = set()
        deduplicate = key_lower in RULE_ID_LISTS
        for value in node:
            rewritten, child_changes = canonicalize_product(
                value,
                aliases,
                parent_key=parent_key,
            )
            changes += child_changes
            marker = repr(rewritten)
            if deduplicate and marker in seen:
                changes += 1
                continue
            seen.add(marker)
            rewritten_list.append(rewritten)
        return rewritten_list, changes

    if key_lower in RULE_KEY_HINTS:
        old_id = normalize_rule_id(node)
        if old_id in aliases:
            return aliases[old_id], 1

    return node, changes


def repair_product(path: Path, aliases: Mapping[str, str]) -> int:
    payload = read_json(path, None)
    if payload is None:
        return 0
    repaired, changes = canonicalize_product(payload, aliases)
    if changes:
        _atomic_write_json(path, repaired)
    return changes


def load_aliases(knowledge_atlas_dir: Path) -> dict[str, str]:
    payload = read_json(
        knowledge_atlas_dir / "duplicate_rule_aliases.json",
        {},
    )
    raw_aliases = (
        payload.get("aliases", {})
        if isinstance(payload, dict)
        else {}
    )
    aliases: dict[str, str] = {}
    for old, new in raw_aliases.items():
        old_id = normalize_rule_id(old)
        new_id = normalize_rule_id(new)
        if old_id and new_id:
            aliases[old_id] = new_id
    return aliases


def canonicalize_declared_alias_outputs(
    step: Any,
    *,
    knowledge_atlas_dir: Path,
) -> int:
    """Canonicalize known JSON products before output fingerprinting."""
    aliases = load_aliases(knowledge_atlas_dir)
    if not aliases:
        return 0
    changes = 0
    for output in step.outputs:
        if output.name in ALIAS_CANONICAL_PRODUCT_NAMES and output.is_file():
            changes += repair_product(output, aliases)
    return changes


__all__ = [
    "ALIAS_CANONICAL_PRODUCT_NAMES",
    "RULE_KEY_HINTS",
    "canonicalize_declared_alias_outputs",
    "canonicalize_product",
    "load_aliases",
    "normalize_rule_id",
    "read_json",
    "repair_product",
]
