"""Canonical rule-ID rewriting and conservative alias merging."""
from __future__ import annotations

import json
from typing import Any

from .constants import RULE_KEYED_MAPS, RULE_REFERENCE_KEYS
from .numeric import sf, ss

def _canonical_rule_id_generic(value: Any, aliases: dict[str, str]) -> str | None:
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
    """Conservative merge used when two alias keys collapse to one key."""
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
            marker = json.dumps(value, sort_keys=True, ensure_ascii=False) \
                if isinstance(value, (dict, list)) else repr(value)
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(value)
        return merged
    # Prefer the right-hand/current value for scalar conflicts.
    return right

def canonicalize_rule_references(
    node: Any,
    aliases: dict[str, str],
    *,
    parent_key: str = "",
) -> Any:
    """Recursively rewrite active rule references to canonical IDs.

    Provenance fields such as source_rule_id are intentionally untouched.
    Dictionary keys are rewritten only for known rule-keyed registries.
    """
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
        if key_l in {
            "rules", "rule_ids", "target_rules", "seed_rules"
        }:
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

def normalize_rule(value: Any) -> str:
    s = ss(value, "unknown").strip()
    if not s or s.lower() == "none":
        return "unknown"
    if s.isdigit():
        return s.zfill(5)
    return s

def canonical_rule(value: Any, aliases: dict[str, str]) -> str:
    canonical = _canonical_rule_id_generic(value, aliases)
    return canonical or normalize_rule(value)

def _observation_quality(obs: dict[str, Any]) -> tuple[float, float, float]:
    return (
        max(
            sf(obs.get("val")),
            sf(obs.get("emg")),
            sf(obs.get("strength")),
        ),
        sf(obs.get("strength")),
        sf(obs.get("val")),
    )

def canonicalize_consensus_database(
    db: dict[str, Any],
    aliases: dict[str, str],
) -> dict[str, Any]:
    db = canonicalize_rule_references(db, aliases)
    for principle in db.get("principles", {}).values():
        observations = principle.get("observations", {})
        if not isinstance(observations, dict):
            continue
        rebuilt: dict[str, dict[str, Any]] = {}
        provenance: dict[str, set[str]] = {}
        for raw_key, raw_obs in observations.items():
            if not isinstance(raw_obs, dict):
                continue
            canonical = canonical_rule(
                raw_obs.get("rule", raw_key),
                aliases,
            )
            obs = canonicalize_rule_references(raw_obs, aliases)
            obs["rule"] = canonical
            provenance.setdefault(canonical, set()).add(
                normalize_rule(raw_key)
            )
            existing = rebuilt.get(canonical)
            if existing is None or _observation_quality(obs) >= _observation_quality(existing):
                rebuilt[canonical] = obs
        for canonical, obs in rebuilt.items():
            source_ids = sorted(provenance.get(canonical, {canonical}))
            if len(source_ids) > 1 or source_ids != [canonical]:
                obs["source_rule_ids"] = source_ids
        principle["observations"] = rebuilt
    db["alias_resolution"] = {
        "schema": "archon_duplicate_rule_aliases_v1",
        "alias_count": len(aliases),
        "aliases": aliases,
    }
    return db
