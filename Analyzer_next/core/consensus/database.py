"""Persistent consensus-memory update rules and evidence-channel intake."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .aliases import canonical_rule, canonicalize_consensus_database, canonicalize_rule_references
from .constants import DB_SCHEMA
from .numeric import clamp01, now_iso, sf, si, ss

def empty_database(root: Path, results: Path) -> dict[str, Any]:
    return {
        "schema": DB_SCHEMA,
        "created": now_iso(),
        "updated": now_iso(),
        "analyzer_root": str(root),
        "results_folder": str(results),
        "principles": {},
        "run_history": [],
    }

def ensure_database_shape(db: Any, root: Path, results: Path) -> dict[str, Any]:
    if not isinstance(db, dict):
        db = empty_database(root, results)
    db.setdefault("created", now_iso())
    db["schema"] = DB_SCHEMA
    db["updated"] = now_iso()
    db["analyzer_root"] = str(root)
    db["results_folder"] = str(results)
    db.setdefault("principles", {})
    db.setdefault("run_history", [])
    return db

def enrich_case(
    case: dict[str, Any],
    profiles_by_rule: dict[str, dict[str, Any]],
    aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    aliases = aliases or {}
    rule = canonical_rule(case.get("rule"), aliases)
    p = profiles_by_rule.get(rule, {})
    return {
        "rule": rule,
        "status": ss(case.get("status"), "neutral"),
        "strength": round(sf(case.get("strength")), 4),
        "reason": ss(case.get("reason"), ""),
        "emg": round(sf(case.get("emg", p.get("emergence_score"))), 4),
        "val": round(sf(case.get("val", p.get("validation_quality"))), 4),
        "know": round(sf(case.get("know", p.get("knowledge_score"))), 4),
        "fb": round(sf(case.get("fb", p.get("feedback_score"))), 4),
        "civ": round(sf(case.get("civ", p.get("civilization_score"))), 4),
        "observer_version": ss(p.get("observer_version"), ""),
        "classification": ss(p.get("classification"), ss(p.get("analyzer_category"), "")),
        "updated": now_iso(),
    }

def confidence_from_observations(observations: dict[str, Any]) -> float:
    support_strength = 0.0
    counter_strength = 0.0
    neutral_weight = 0.0
    for obs in observations.values():
        status = ss(obs.get("status"), "neutral")
        strength = sf(obs.get("strength"), 0.0)
        quality = 0.35 + 0.65 * clamp01(max(sf(obs.get("val")), sf(obs.get("emg")), strength))
        weighted = max(strength, 0.15) * quality
        if status == "support":
            support_strength += weighted
        elif status == "counterexample":
            counter_strength += weighted
        else:
            neutral_weight += 0.20
    score = (1.0 + support_strength) / (2.0 + support_strength + counter_strength + neutral_weight)
    return round(clamp01(score), 4)

def confidence_label(score: float, support: int, counter: int) -> str:
    if support <= 0 and counter <= 0:
        return "NONE"
    if score >= 0.85 and support >= 25:
        return "VERY_HIGH"
    if score >= 0.75 and support >= 10:
        return "HIGH"
    if score >= 0.60 and support >= 3:
        return "MEDIUM"
    if support >= 1 or counter >= 1:
        return "LOW"
    return "NONE"

def status_from_counts(support: int, counter: int, neutral: int, confidence: float) -> str:
    total = support + counter + neutral
    if total <= 0:
        return "unobserved"
    if support == 0 and counter == 0:
        return "no_signal"
    if counter > support and counter >= 2:
        return "contested"
    if support >= 25 and confidence >= 0.85 and counter <= max(2, support // 10):
        return "strong_consensus_candidate"
    if support >= 10 and confidence >= 0.75 and counter <= max(3, support // 5):
        return "supported_principle_candidate"
    if support >= 3 and confidence >= 0.60:
        return "multi_case_hypothesis"
    if support >= 1:
        return "single_case_seed"
    if counter >= 1:
        return "counterexample_seed"
    return "weak_or_unclear"

def load_principle_evidence_profiles(
    evidence: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    payload = (
        evidence.get("principle_evidence_profiles", {})
        if isinstance(evidence, dict)
        else {}
    )
    profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
    if not isinstance(profiles, dict):
        return {}
    return {
        str(key): value
        for key, value in profiles.items()
        if isinstance(value, dict)
    }

def build_consensus_context(
    evidence_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    """Channel-aware intake. It does not alter consensus score or status."""
    profile = evidence_profile or {}
    observational = profile.get("observational", {})
    experimental = profile.get("experimental", {})
    perturbation = profile.get("perturbation", {})
    overall = profile.get("overall_picture", {})

    if not isinstance(observational, dict):
        observational = {}
    if not isinstance(experimental, dict):
        experimental = {}
    if not isinstance(perturbation, dict):
        perturbation = {}
    if not isinstance(overall, dict):
        overall = {}

    experimental_picture = ss(
        overall.get("experimental_picture", experimental.get("picture")),
        "UNTESTED",
    )
    perturbation_picture = ss(
        overall.get("perturbation_picture", perturbation.get("picture")),
        "INSUFFICIENT",
    )
    gaps = list(overall.get("evidence_gaps", []) or [])

    experimental_scope_challenge = (
        si(experimental.get("challenging_links")) > 0
        or "CHALLENGE" in experimental_picture
    )
    perturbation_mixed_signal = perturbation_picture == "MIXED"
    cross_channel_tension = (
        experimental_scope_challenge
        or perturbation_picture in {
            "CHALLENGED",
            "LIMITED_CHALLENGE_SIGNAL",
            "PERSISTENT_COUNTEREXAMPLE",
        }
    )

    return {
        "schema": "archon_consensus_evidence_context_v1",
        "profile_available": bool(profile),
        "observational_strength": ss(
            overall.get(
                "observational_strength",
                observational.get("confidence_label"),
            ),
            "NONE",
        ),
        "experimental_picture": experimental_picture,
        "perturbation_picture": perturbation_picture,
        "scientific_summary": ss(overall.get("scientific_summary")),
        "evidence_gaps": gaps,
        "flags": {
            "experimental_scope_challenge": experimental_scope_challenge,
            "perturbation_mixed_signal": perturbation_mixed_signal,
            "cross_channel_tension": cross_channel_tension,
            "evidence_incomplete": bool(gaps),
        },
        "channel_counts": {
            "experimental_supportive_links": si(
                experimental.get("supportive_links")
            ),
            "experimental_contextual_links": si(
                experimental.get("contextual_links")
            ),
            "experimental_challenging_links": si(
                experimental.get("challenging_links")
            ),
            "experimental_unique_experiments": si(
                experimental.get("unique_experiment_count")
            ),
            "experimental_unique_rules": si(
                experimental.get("unique_rule_count")
            ),
            "perturbation_informative_runs": si(
                perturbation.get("informative_run_count")
            ),
            "perturbation_unique_parent_rules": si(
                perturbation.get("unique_parent_rule_count")
            ),
        },
        "scientific_policy": {
            "consensus_score_changed": False,
            "consensus_status_changed": False,
            "automatic_promotion": False,
            "automatic_demotion": False,
            "channel_aware_intake_only": True,
        },
    }

def update_database(
    db: dict[str, Any],
    evidence: dict[str, Any],
    profiles_by_rule: dict[str, dict[str, Any]],
    aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    aliases = aliases or {}
    db = canonicalize_consensus_database(db, aliases)
    evidence = canonicalize_rule_references(evidence, aliases)
    claims = evidence.get("claims", []) if isinstance(evidence, dict) else []
    if not isinstance(claims, list):
        claims = []
    principle_profiles = load_principle_evidence_profiles(evidence)

    run_id = now_iso()
    touched_principles: list[str] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        cid = ss(claim.get("id"), "UNKNOWN")
        title = ss(claim.get("title"), cid)
        desc = ss(claim.get("description"), "")
        principle = db["principles"].setdefault(cid, {
            "id": cid,
            "title": title,
            "description": desc,
            "created": now_iso(),
            "updated": now_iso(),
            "observations": {},
            "summary": {},
        })
        principle["title"] = title or principle.get("title", cid)
        principle["description"] = desc or principle.get("description", "")
        principle["updated"] = now_iso()
        previous_observations = principle.get("observations", {})
        if not isinstance(previous_observations, dict):
            previous_observations = {}
        current_observations: dict[str, Any] = {}
        perturbation = claim.get("perturbation_evidence", {})
        principle["perturbation_evidence"] = (
            perturbation
            if isinstance(perturbation, dict)
            else {}
        )
        principle["evidence_profile"] = principle_profiles.get(cid, {})
        principle["consensus_context"] = build_consensus_context(
            principle["evidence_profile"]
        )

        for raw_case in claim.get("cases", []) or []:
            if not isinstance(raw_case, dict):
                continue
            obs = enrich_case(raw_case, profiles_by_rule, aliases)
            rule = obs["rule"]
            if rule == "unknown":
                continue
            current_observations[rule] = obs
        removed_rules = sorted(set(previous_observations) - set(current_observations))
        if removed_rules:
            archive = principle.setdefault("observation_history", [])
            if not isinstance(archive, list):
                archive = []
                principle["observation_history"] = archive
            archive.append({
                "archived_at": run_id,
                "reason": "NOT_IN_CURRENT_SCIENTIFIC_VIEW",
                "observations": {
                    rule: previous_observations[rule]
                    for rule in removed_rules
                },
            })
            principle["observation_history"] = archive[-50:]
        principle["observations"] = current_observations
        principle["active_in_current_evidence"] = True
        principle["scientific_view_schema"] = "archon_scientific_view_v1"
        touched_principles.append(cid)

    for cid, principle in db.get("principles", {}).items():
        if cid not in touched_principles:
            principle["active_in_current_evidence"] = False
            continue
        obs = principle.get("observations", {})
        if not isinstance(obs, dict):
            obs = {}
            principle["observations"] = obs
        support = sum(1 for o in obs.values() if ss(o.get("status")) == "support")
        counter = sum(1 for o in obs.values() if ss(o.get("status")) == "counterexample")
        neutral = sum(1 for o in obs.values() if ss(o.get("status")) == "neutral")
        total = support + counter + neutral
        conf = confidence_from_observations(obs)
        label = confidence_label(conf, support, counter)
        principle["summary"] = {
            "rules_total": total,
            "support": support,
            "counterexamples": counter,
            "neutral": neutral,
            "confidence_score": conf,
            "confidence_label": label,
            "status": status_from_counts(support, counter, neutral, conf),
            "support_rules": sorted([r for r, o in obs.items() if ss(o.get("status")) == "support"]),
            "counterexample_rules": sorted([r for r, o in obs.items() if ss(o.get("status")) == "counterexample"]),
        }

    db.setdefault("run_history", []).append({
        "run_id": run_id,
        "source": "evidence_report.json",
        "claims_seen": len(claims),
        "evidence_profiles_seen": len(principle_profiles),
        "principles_touched": sorted(set(touched_principles)),
        "scientific_view_schema": "archon_scientific_view_v1",
        "active_rule_counts": {
            cid: len(
                principle.get("observations", {})
                if isinstance(principle.get("observations"), dict)
                else {}
            )
            for cid, principle in db.get("principles", {}).items()
            if cid in touched_principles and isinstance(principle, dict)
        },
    })
    db["run_history"] = db["run_history"][-300:]
    return db

