"""Filesystem repository for the modular Consensus pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from Analyzer_next.core.consensus.aliases import (
    _canonical_rule_id_generic,
    canonical_rule,
    canonicalize_rule_references,
)
from Analyzer_next.core.consensus.contracts import (
    ConsensusInputs,
    ConsensusPaths,
    ConsensusRunResult,
)
from Analyzer_next.core.consensus.numeric import si, ss


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_rule_aliases(root: Path) -> dict[str, str]:
    payload = load_json(root / "duplicate_rule_aliases.json", {})
    raw = payload.get("aliases", {}) if isinstance(payload, dict) else {}
    aliases: dict[str, str] = {}
    if isinstance(raw, dict):
        for old, new in raw.items():
            old_id = _canonical_rule_id_generic(old, {})
            new_id = _canonical_rule_id_generic(new, {})
            if old_id and new_id and old_id != new_id:
                aliases[old_id] = new_id
    return aliases


def load_profiles_by_rule(
    results: Path,
    aliases: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    aliases = aliases or {}
    data = load_json(results / "observer_profiles_v30.json", {})
    profiles = data.get("profiles", []) if isinstance(data, dict) else []
    out: dict[str, dict[str, Any]] = {}
    if isinstance(profiles, list):
        for profile in profiles:
            if isinstance(profile, dict):
                canonical = canonical_rule(profile.get("rule"), aliases)
                item = canonicalize_rule_references(dict(profile), aliases)
                item["rule"] = canonical
                out[canonical] = item
    return out


def load_counterexample_coverage(path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(path, {})
    audits = payload.get("audits", []) if isinstance(payload, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for audit in audits:
        if not isinstance(audit, dict):
            continue
        claim_id = ss(audit.get("id"))
        if not claim_id:
            continue
        out[claim_id] = {
            "coverage_status": ss(audit.get("coverage_status"), "UNTESTED_REGIME"),
            "confirmed_count": si(audit.get("confirmed_count")),
            "near_count": si(audit.get("near_count")),
            "missing_regimes": list(audit.get("missing_regimes", []) or []),
        }
    return out


def load_replication_context(
    results: Path,
    aliases: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    aliases = aliases or {}
    payload = load_json(results / "observer_profiles_v30.json", {})
    records = payload.get("profile_records", []) if isinstance(payload, dict) else []
    if not isinstance(records, list):
        records = []

    by_rule: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("observational_eligible", True) is False:
            continue
        if str(record.get("evidence_channel", "legacy_unverified_observational")).lower() in {
            "experimental",
            "perturbation",
            "excluded",
        }:
            continue
        rule = canonical_rule(record.get("rule"), aliases)
        bucket = by_rule.setdefault(
            rule,
            {"record_count": 0, "experiment_ids": set(), "seeds": set()},
        )
        bucket["record_count"] += 1
        experiment_id = record.get("experiment_id")
        if experiment_id:
            bucket["experiment_ids"].add(str(experiment_id))
        seed = record.get("seed")
        if seed not in {None, ""}:
            bucket["seeds"].add(str(seed))

    return {
        rule: {
            "record_count": data["record_count"],
            "experiment_count": len(data["experiment_ids"]),
            "seed_count": len(data["seeds"]),
        }
        for rule, data in by_rule.items()
    }


class FileConsensusRepository:
    def load(self, paths: ConsensusPaths) -> ConsensusInputs:
        evidence = load_json(paths.evidence, {})
        if not evidence:
            raise SystemExit(
                f"Evidence report not found or invalid: {paths.evidence}\n"
                "Run Evidence Engine first."
            )
        aliases = load_rule_aliases(paths.root)
        return ConsensusInputs(
            evidence=evidence,
            aliases=aliases,
            profiles_by_rule=load_profiles_by_rule(paths.results, aliases),
            counterexample_coverage=load_counterexample_coverage(paths.counterexamples),
            replication_context=load_replication_context(paths.results, aliases),
            database=load_json(paths.database_json, {}),
        )

    def save(self, paths: ConsensusPaths, result: ConsensusRunResult) -> None:
        write_json(paths.database_json, result.database)
        paths.database_markdown.write_text(result.database_markdown, encoding="utf-8")
        write_json(paths.report_json, result.report)
        paths.report_markdown.write_text(result.report_markdown, encoding="utf-8")
