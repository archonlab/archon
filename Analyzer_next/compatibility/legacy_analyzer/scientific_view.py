#!/usr/bin/env python3
"""Shared scientific-view routing helpers.

The full Atlas and Knowledge Base are historical catalogues.  Scientific
claims must instead use the current one-representative-per-rule observational
view emitted by Observer Profile v31.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


SCIENTIFIC_VIEW_SCHEMA = "archon_scientific_view_v1"
EXCLUDED_EVIDENCE_CHANNELS = {"experimental", "perturbation", "excluded"}


def normalize_rule(value: Any) -> str:
    raw = str(value or "unknown").strip()
    if raw.isdigit():
        return raw.zfill(5)
    return raw or "unknown"


def profile_payload_path(results: Path) -> Path:
    for name in ("observer_profiles_v31.json", "observer_profiles_v30.json"):
        candidate = results / name
        if candidate.exists():
            return candidate
    return results / "observer_profiles_v31.json"


def load_profile_payload(results: Path) -> dict[str, Any]:
    path = profile_payload_path(results)
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def is_observational_eligible(profile: dict[str, Any]) -> bool:
    if profile.get("observational_eligible", True) is False:
        return False
    channel = str(
        profile.get("evidence_channel", "legacy_unverified_observational")
    ).strip().lower()
    return channel not in EXCLUDED_EVIDENCE_CHANNELS


def eligible_profiles_from_payload(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
    if not isinstance(profiles, list):
        return []
    return [
        profile
        for profile in profiles
        if isinstance(profile, dict) and is_observational_eligible(profile)
    ]


def eligible_profiles(results: Path) -> list[dict[str, Any]]:
    return eligible_profiles_from_payload(load_profile_payload(results))


def rule_set(records: Iterable[dict[str, Any]]) -> set[str]:
    return {
        normalize_rule(record.get("rule"))
        for record in records
        if isinstance(record, dict) and normalize_rule(record.get("rule")) != "unknown"
    }


def scientific_atlas_records(atlas: dict[str, Any]) -> list[dict[str, Any]]:
    records = atlas.get("experiments", []) if isinstance(atlas, dict) else []
    if not isinstance(records, list):
        return []

    explicitly_routed = any(
        isinstance(record, dict) and "is_scientific_observational" in record
        for record in records
    )
    if explicitly_routed:
        return [
            record
            for record in records
            if isinstance(record, dict)
            and record.get("is_scientific_observational") is True
        ]

    # Compatibility for pre-v1 Atlas files.  The representative flag is the
    # narrowest safe historical view; explicit exclusions still win.
    return [
        record
        for record in records
        if isinstance(record, dict)
        and record.get("is_representative", True)
        and is_observational_eligible(record)
    ]


def evidence_rule_set(evidence: dict[str, Any]) -> set[str]:
    claims = evidence.get("claims", []) if isinstance(evidence, dict) else []
    if not isinstance(claims, list):
        return set()
    rules: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        cases = claim.get("cases", [])
        if isinstance(cases, list):
            rules.update(rule_set(case for case in cases if isinstance(case, dict)))
    return rules


def scope_signature(rules: Iterable[str]) -> str:
    normalized = sorted({normalize_rule(rule) for rule in rules})
    raw = json.dumps(
        {"schema": SCIENTIFIC_VIEW_SCHEMA, "rules": normalized},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def describe_rules(rules: Iterable[str]) -> dict[str, Any]:
    normalized = sorted({normalize_rule(rule) for rule in rules})
    return {
        "schema": SCIENTIFIC_VIEW_SCHEMA,
        "rule_count": len(normalized),
        "rule_ids": normalized,
        "scope_signature": scope_signature(normalized),
    }
