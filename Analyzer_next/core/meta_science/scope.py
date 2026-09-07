"""Pure scientific-view selection for Meta Science inputs."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from Analyzer_next.core.meta_science.constants import SCIENTIFIC_VIEW_SCHEMA


EXCLUDED_EVIDENCE_CHANNELS = {"experimental", "perturbation", "excluded"}


def normalize_rule(value: Any) -> str:
    raw = str(value or "unknown").strip()
    if raw.isdigit():
        return raw.zfill(5)
    return raw or "unknown"


def is_observational_eligible(profile: dict[str, Any]) -> bool:
    if profile.get("observational_eligible", True) is False:
        return False
    channel = str(
        profile.get("evidence_channel", "legacy_unverified_observational")
    ).strip().lower()
    return channel not in EXCLUDED_EVIDENCE_CHANNELS


def eligible_profiles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
    if not isinstance(profiles, list):
        return []
    return [
        profile for profile in profiles
        if isinstance(profile, dict) and is_observational_eligible(profile)
    ]


def rule_set(records: Iterable[dict[str, Any]]) -> set[str]:
    return {
        normalize_rule(record.get("rule"))
        for record in records
        if isinstance(record, dict) and normalize_rule(record.get("rule")) != "unknown"
    }


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


def profile_info(payload: dict[str, Any]) -> dict[str, Any]:
    profiles = eligible_profiles(payload)
    return {
        "count": len(profiles),
        "rules": sorted({
            str(profile.get("rule"))
            for profile in profiles
            if isinstance(profile, dict) and profile.get("rule") is not None
        }),
    }
