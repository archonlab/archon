#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universe Search Atlas Engine v30

Step 3: Atlas integration with ObserverProfile v30.

Reads from a shared results folder:
- observer_profiles_v30.json              [new preferred input]
- passport_analysis.md                    [legacy fallback]
- research_questions.md
- discovery_report.md

Writes / updates in the Analyzer folder by default:
- research_atlas.json
- research_atlas.md

Usage:
    python atlas_engine.py ../universe_search_v23_results
    python atlas_engine.py ../universe_search_v23_results --atlas research_atlas.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from Analyzer_next.adapters.scientific_view_adapter import (
    is_observational_eligible,
    profile_payload_path,
    scientific_atlas_records,
)

from Analyzer_next.adapters.atlas_engine.workspace_paths import (
    PROJECT_ROOT,
    knowledge_atlas_dir,
    resolve_results_dir,
)


CONF_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "VERY_HIGH": 4}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def norm_conf(value: Any) -> str:
    s = str(value or "NONE").strip().upper().replace(" ", "_")
    return s if s in CONF_RANK else "NONE"


def first_number(text: str | None, as_float: bool = False):
    if not text:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(text).replace(",", ""))
    if not m:
        return None
    return float(m.group(0)) if as_float else int(float(m.group(0)))


def find_file(folder: Path, name: str) -> Path | None:
    direct = folder / name
    if direct.exists():
        return direct
    matches = list(folder.rglob(name))
    return matches[0] if matches else None



def load_rule_aliases(atlas_path: Path) -> dict[str, str]:
    path = atlas_path.parent / "duplicate_rule_aliases.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    raw = payload.get("aliases", {}) if isinstance(payload, dict) else {}
    aliases: dict[str, str] = {}
    if isinstance(raw, dict):
        for old, new in raw.items():
            try:
                old_id = f"{int(str(old)):05d}"
                new_id = f"{int(str(new)):05d}"
            except Exception:
                continue
            if old_id != new_id:
                aliases[old_id] = new_id
    return aliases


def canonical_rule_id(value: Any, aliases: dict[str, str]) -> str:
    try:
        current = f"{int(str(value)):05d}"
    except Exception:
        return str(value or "unknown")
    seen: set[str] = set()
    while current in aliases and current not in seen:
        seen.add(current)
        current = aliases[current]
    return current


def canonicalize_profile(
    profile: dict[str, Any],
    aliases: dict[str, str],
) -> dict[str, Any]:
    out = dict(profile)
    original = str(profile.get("rule") or "unknown").zfill(5)
    canonical = canonical_rule_id(original, aliases)
    out["rule"] = canonical
    if canonical != original:
        out["source_rule_id"] = original
        out["canonicalized_from_alias"] = original
    return out


def load_observer_profile_data(
    results_folder: Path,
) -> tuple[list[dict[str, Any]], set[str]]:
    """
    Load the complete Observer Profile history.

    Returns:
    - profile_records: every passport-derived profile;
    - representative_ids: experiment IDs used by the backward-compatible
      one-profile-per-rule `profiles` view.
    """
    path = profile_payload_path(results_folder)
    if not path.exists():
        return [], set()

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        print(f"[WARN] Could not read observer profile data {path.name}: {exc}")
        return [], set()

    if not isinstance(data, dict):
        return [], set()

    representatives = [
        profile
        for profile in data.get("profiles", [])
        if isinstance(profile, dict) and is_observational_eligible(profile)
    ]
    representative_ids = {
        str(profile.get("experiment_id"))
        for profile in representatives
        if isinstance(profile, dict) and profile.get("experiment_id")
    }

    records = data.get("profile_records")
    if not isinstance(records, list):
        records = representatives
    records = [record for record in records if isinstance(record, dict)]

    return records, representative_ids


def load_observer_profiles(results_folder: Path) -> list[dict[str, Any]]:
    """Backward-compatible helper returning complete profile records."""
    records, _ = load_observer_profile_data(results_folder)
    return records

def parse_passport_analysis(path: Path | None) -> dict[str, Any]:
    data = {
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

    if not path or not path.exists():
        return data

    text = read_text(path)

    m = re.search(r"(?:##\s*)?Rule\s+(\d+)", text, re.I)
    if not m:
        m = re.search(r"\|\s*(\d{3,5})\s*\|", text)
    if m:
        data["rule"] = m.group(1).zfill(5)

    def grab_any(labels: list[str]):
        for label in labels:
            m = re.search(rf"-\s*{re.escape(label)}:\s*\*\*([^*]+)\*\*", text, re.I)
            if m:
                return m.group(1).strip()
            m = re.search(rf"^\s*{re.escape(label)}:\s*(.+)$", text, re.I | re.M)
            if m:
                return m.group(1).strip()
        return None

    data["lifetime"] = first_number(grab_any(["Lifetime", "Longest observed age", "Last alive tick"]))
    data["classification"] = grab_any(["Classification"])
    data["dynamic_score"] = first_number(grab_any(["Dynamic score", "Dynamic attractor score"]), as_float=True)
    data["breathing_score"] = first_number(grab_any(["Breathing score"]), as_float=True)
    data["collapse"] = grab_any(["Collapse", "Collapse tick"])
    data["objects"] = grab_any(["Objects", "Object range"])
    data["split_birth"] = first_number(grab_any(["Split/birth events"]))
    data["merge_death"] = first_number(grab_any(["Merge/death events"]))

    events = grab_any(["Events"])
    if events:
        sm = re.search(r"split/birth\s*=\s*(\d+)", events, re.I)
        mm = re.search(r"merge/death\s*=\s*(\d+)", events, re.I)
        if sm:
            data["split_birth"] = int(sm.group(1))
        if mm:
            data["merge_death"] = int(mm.group(1))

    if data["collapse"] in {"None", "none", "null"}:
        data["collapse"] = "No"

    return data


def parse_discovery_report(path: Path | None) -> dict[str, Any]:
    data = {"discoveries": [], "discovery_count": 0, "top_discovery": None, "max_impact": 0, "verdict": None}
    if not path or not path.exists():
        return data
    text = read_text(path)
    for m in re.finditer(r"###\s+(D\d+):\s+(.+?)\n\n(.+?)(?=\n###|\n##|\Z)", text, re.S):
        did = m.group(1).strip()
        title = m.group(2).strip()
        block = m.group(3)
        impact_match = re.search(r"Impact:\s*\*\*(.+?)\*\*", block)
        confidence_match = re.search(r"Confidence:\s*\*\*(.+?)\*\*", block)
        finding_match = re.search(r"Finding:\s*(.+)", block)
        impact_text = impact_match.group(1).strip() if impact_match else ""
        impact = impact_text.count("★")
        data["discoveries"].append({
            "id": did,
            "title": title,
            "impact": impact,
            "confidence": confidence_match.group(1).strip() if confidence_match else None,
            "finding": finding_match.group(1).strip() if finding_match else None,
        })
    data["discovery_count"] = len(data["discoveries"])
    if data["discoveries"]:
        data["top_discovery"] = data["discoveries"][0]["title"]
        data["max_impact"] = max(d.get("impact", 0) for d in data["discoveries"])
    verdict_match = re.search(r"## Discovery engine verdict\s+(.+)", text, re.S)
    if verdict_match:
        data["verdict"] = " ".join(verdict_match.group(1).strip().split())
    return data


def parse_questions(path: Path | None) -> dict[str, Any]:
    data = {"high_priority_questions": 0, "hypotheses": 0, "next_actions": 0}
    if not path or not path.exists():
        return data
    text = read_text(path)
    data["high_priority_questions"] = len([line for line in text.splitlines() if line.startswith("| ★") and "| Rule |" not in line])
    data["hypotheses"] = len(re.findall(r"^###\s+H-", text, re.M))
    data["next_actions"] = len(re.findall(r"^\d+\.\s+", text, re.M))
    return data


def compute_legacy_research_value(passport: dict[str, Any], discovery: dict[str, Any], questions: dict[str, Any]) -> float:
    lifetime = passport.get("lifetime") or 0
    dynamic = passport.get("dynamic_score") or 0.0
    breathing = passport.get("breathing_score") or 0.0
    max_impact = discovery.get("max_impact") or 0
    q = questions.get("high_priority_questions") or 0
    score = 0.0
    score += min(lifetime / 100000, 1.0) * 3.0
    score += min(dynamic, 1.0) * 2.5
    score += min(breathing, 1.0) * 1.5
    score += min(max_impact / 5, 1.0) * 2.0
    score += min(q / 4, 1.0) * 1.0
    return round(min(score, 10.0), 2)


def compute_v30_research_value(profile: dict[str, Any], discovery: dict[str, Any], questions: dict[str, Any]) -> float:
    layer = safe_float(profile.get("layer_stack_score"))
    emg = safe_float(profile.get("emergence_score"))
    val = safe_float(profile.get("validation_quality"))
    know = safe_float(profile.get("knowledge_score"))
    fb = safe_float(profile.get("feedback_score"))
    civ = safe_float(profile.get("civilization_score"))
    life = min(safe_float(profile.get("longest_age")) / 100000.0, 1.0)
    discovery_bonus = min((discovery.get("max_impact") or 0) / 5.0, 1.0)
    question_bonus = min((questions.get("high_priority_questions") or 0) / 4.0, 1.0)
    score = (
        2.0 * layer
        + 1.6 * emg
        + 1.3 * val
        + 1.2 * fb
        + 1.0 * know
        + 0.8 * civ
        + 0.8 * life
        + 0.8 * discovery_bonus
        + 0.5 * question_bonus
    )
    return round(min(score, 10.0), 2)


def status_from_record(record: dict[str, Any]) -> str:
    # v30 compatibility: ObserverProfile records may intentionally contain None
    # for old v29 fields such as dynamic_score/lifetime. Always normalize before
    # numeric comparisons so Atlas can mix legacy and v30 records safely.
    fp_risk = safe_float(record.get("validation_false_positive_risk"))
    emg = safe_float(record.get("emergence_score"))
    val_q = safe_float(record.get("validation_quality"))
    fb = safe_float(record.get("feedback_score"))
    know = safe_float(record.get("knowledge_score"))
    lifetime = safe_int(record.get("lifetime"))
    dynamic = safe_float(record.get("dynamic_score"))
    discovery_count = safe_int(record.get("discovery_count"))

    if fp_risk >= 0.35:
        return "Needs calibration check"
    if emg >= 0.6 and val_q >= 0.6:
        return "Credible emergence candidate"
    if fb >= 0.55:
        return "Adaptive feedback candidate"
    if know >= 0.5:
        return "Knowledge candidate"
    if lifetime >= 100000 and dynamic >= 0.8:
        return "Needs replication"
    if discovery_count > 0:
        return "Interesting"
    if record.get("analyzer_category") == "beautiful_dead_or_static_world":
        return "Beautiful dead/static world"
    return "Unclear"


def derive_family_from_profile(profile: dict[str, Any]) -> str:
    cat = profile.get("analyzer_category") or ""
    if cat == "credible_emergent_organization":
        return "Credible Emergent Organization"
    if cat == "adaptive_feedback_candidate":
        return "Adaptive Feedback System"
    if cat == "knowledge_accumulation_candidate":
        return "Knowledge Accumulation System"
    if cat == "civilization_like_candidate":
        return "Civilization-like Candidate"
    if cat == "beautiful_dead_or_static_world":
        return "Beautiful Dead / Static World"
    if cat == "collapsed_world":
        return "Collapsed / Terminal"
    return "Weak or Unclear Signal"


def derive_family_legacy(passport: dict[str, Any]) -> str:
    classification = (passport.get("classification") or "").lower()
    lifetime = passport.get("lifetime") or 0
    dynamic = passport.get("dynamic_score") or 0.0
    breathing = passport.get("breathing_score") or 0.0
    collapse = passport.get("collapse")
    if lifetime >= 100000 and dynamic >= 0.8 and collapse == "No":
        return "Stable Dynamic Attractor"
    if "stable dynamic attractor" in classification:
        return "Stable Dynamic Attractor"
    if lifetime >= 100000:
        return "Long-lived World"
    if dynamic >= 0.7 and breathing >= 0.6:
        return "Dynamic Scaffold"
    if breathing >= 0.7:
        return "Breathing Scaffold"
    if collapse not in {None, "No"}:
        return "Collapsed / Terminal"
    return "Unclassified"


def derive_tags_from_profile(profile: dict[str, Any], discovery: dict[str, Any], questions: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    if safe_int(profile.get("longest_age")) >= 100000:
        tags.append("long-lived")
    if safe_int(profile.get("collapse_tick"), -1) < 0:
        tags.append("no-collapse")
    if safe_float(profile.get("civilization_score")) >= 0.45:
        tags.append("civilization")
    if safe_float(profile.get("knowledge_score")) >= 0.5:
        tags.append("knowledge")
    if safe_float(profile.get("feedback_score")) >= 0.5:
        tags.append("feedback")
    if safe_float(profile.get("emergence_score")) >= 0.6:
        tags.append("emergence")
    if norm_conf(profile.get("validation_grade")) in {"HIGH", "VERY_HIGH"}:
        tags.append("validated")
    if safe_float(profile.get("validation_false_positive_risk")) >= 0.35:
        tags.append("fp-risk")
    if safe_float(profile.get("validation_noise_sensitivity")) >= 0.45:
        tags.append("noise-sensitive")
    if safe_float(discovery.get("max_impact")) >= 5:
        tags.append("high-impact")
    if safe_int(questions.get("high_priority_questions")) >= 4:
        tags.append("research-rich")
    tags.extend(str(x) for x in profile.get("key_reasons") or [])
    return sorted(set(t for t in tags if t))


def derive_tags_legacy(passport: dict[str, Any], discovery: dict[str, Any], questions: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    lifetime = passport.get("lifetime") or 0
    dynamic = passport.get("dynamic_score") or 0.0
    breathing = passport.get("breathing_score") or 0.0
    collapse = passport.get("collapse")
    split = passport.get("split_birth") or 0
    merge = passport.get("merge_death") or 0
    if lifetime >= 100000:
        tags.append("long-lived")
    if dynamic >= 0.8:
        tags.append("dynamic-attractor")
    if breathing >= 0.7:
        tags.append("breathing")
    if collapse == "No":
        tags.append("no-collapse")
    if split + merge >= 20:
        tags.append("object-turnover")
    if safe_float(discovery.get("max_impact")) >= 5:
        tags.append("high-impact")
    if safe_int(questions.get("high_priority_questions")) >= 4:
        tags.append("research-rich")
    return sorted(set(tags))


def numeric_similarity(a: dict[str, Any], b: dict[str, Any], key: str, scale: float) -> float | None:
    av = a.get(key)
    bv = b.get(key)
    if av is None or bv is None:
        return None
    return max(0.0, 1.0 - min(abs(float(av) - float(bv)) / scale, 1.0))


def similarity_between(a: dict[str, Any], b: dict[str, Any]) -> float:
    score = 0.0
    weight = 0.0

    weight += 2.0
    if a.get("family") and a.get("family") == b.get("family"):
        score += 2.0

    weight += 1.0
    if a.get("analyzer_category") and a.get("analyzer_category") == b.get("analyzer_category"):
        score += 1.0
    elif a.get("classification") and a.get("classification") == b.get("classification"):
        score += 1.0

    for key, scale, w in [
        ("layer_stack_score", 1.0, 1.6),
        ("emergence_score", 1.0, 1.5),
        ("validation_quality", 1.0, 1.2),
        ("feedback_score", 1.0, 1.2),
        ("knowledge_score", 1.0, 1.1),
        ("civilization_score", 1.0, 1.0),
        ("dynamic_score", 1.0, 1.0),
        ("breathing_score", 1.0, 0.8),
        ("research_value", 10.0, 1.0),
        ("lifetime", 200000.0, 0.8),
    ]:
        sim = numeric_similarity(a, b, key, scale)
        if sim is not None:
            weight += w
            score += w * sim

    tags_a = set(a.get("tags") or [])
    tags_b = set(b.get("tags") or [])
    if tags_a or tags_b:
        weight += 1.3
        union = len(tags_a | tags_b)
        score += 1.3 * (len(tags_a & tags_b) / union if union else 0.0)

    return round(score / weight, 3) if weight else 0.0


def update_similarity_and_replications(atlas: dict[str, Any]) -> None:
    experiments = atlas.get("experiments", [])

    for e in experiments:
        sims = []
        for other in experiments:
            if other is e:
                continue
            sim = similarity_between(e, other)
            if sim >= 0.65:
                sims.append({
                    "rule": other.get("rule"),
                    "experiment_id": other.get("experiment_id"),
                    "folder": other.get("experiment_folder"),
                    "similarity": sim,
                    "family": other.get("family"),
                })
        e["similar_to"] = sorted(
            sims,
            key=lambda x: x["similarity"],
            reverse=True,
        )[:5]

    by_rule: dict[str, list[dict[str, Any]]] = {}
    for e in experiments:
        rule = str(e.get("rule") or "unknown").zfill(5)
        by_rule.setdefault(rule, []).append(e)

    for rule, records in by_rule.items():
        experiment_ids = {
            str(record.get("experiment_id") or record.get("experiment_key"))
            for record in records
        }
        seeds = {
            str(record.get("seed"))
            for record in records
            if record.get("seed") not in {None, ""}
        }

        record_count = len(records)
        experiment_count = len(experiment_ids)
        seed_count = len(seeds)

        for record in records:
            record["record_count"] = record_count
            record["experiment_count"] = experiment_count
            record["seed_count"] = seed_count

            # Kept only so older consumers do not crash. It must not be
            # interpreted as independent replication.
            record["replication_count"] = record_count

            if record.get("status") == "Needs replication":
                if seed_count >= 2:
                    record["status"] = "Multi-seed candidate"
                elif experiment_count >= 2:
                    record["status"] = "Repeated-observation candidate"


def refresh_workspace_records(
    atlas: dict[str, Any],
    results_folder: Path,
) -> int:
    """
    Remove every previous Atlas record originating from this workspace.

    Historical Atlas versions used several shapes:
    - v30 records with experiment_path;
    - legacy records with experiment_folder;
    - records identified only through experiment_key or source_file.

    When a complete profile history is imported, all of those older slices
    must be replaced, otherwise old representatives remain beside the new
    record history.
    """
    target = results_folder.resolve()
    target_text = str(target)
    existing = atlas.get("experiments", [])

    def belongs_to_workspace(record: dict[str, Any]) -> bool:
        candidates = [
            record.get("experiment_path"),
            record.get("experiment_folder"),
            record.get("results_folder"),
        ]

        for value in candidates:
            if not value:
                continue
            try:
                if Path(str(value)).resolve() == target:
                    return True
            except Exception:
                if str(value) == target_text:
                    return True

        experiment_key = str(record.get("experiment_key") or "")
        if experiment_key.startswith(target_text + "::"):
            return True

        source_file = str(record.get("source_file") or "")
        if source_file:
            try:
                Path(source_file).resolve().relative_to(target)
                return True
            except (ValueError, OSError):
                pass

        return False

    retained = [
        record
        for record in existing
        if not (
            isinstance(record, dict)
            and belongs_to_workspace(record)
        )
    ]
    removed = len(existing) - len(retained)
    atlas["experiments"] = retained
    return removed

def compute_novelty(record: dict[str, Any], atlas: dict[str, Any]) -> float:
    existing = atlas.get("experiments", [])
    if not existing:
        return 1.0
    best = 0.0
    for old in existing:
        if old.get("experiment_key") == record.get("experiment_key"):
            continue
        best = max(best, similarity_between(record, old))
    return round(1.0 - best, 3)


def build_record_from_profile(
    results_folder: Path,
    profile: dict[str, Any],
    discovery: dict[str, Any],
    questions: dict[str, Any],
    representative_ids: set[str] | None = None,
) -> dict[str, Any]:
    rule = str(profile.get("rule") or "unknown").zfill(5)
    experiment_id = str(
        profile.get("experiment_id")
        or profile.get("run_id")
        or profile.get("source_file")
        or f"rule_{rule}"
    )
    representative_ids = representative_ids or set()
    family = derive_family_from_profile(profile)
    tags = derive_tags_from_profile(profile, discovery, questions)
    collapse_tick = profile.get("collapse_tick")
    collapse = "No" if collapse_tick in {None, "", -1} else str(collapse_tick)

    record = {
        "schema": "atlas_record_v30_1",
        "experiment_key": f"{results_folder.resolve()}::{experiment_id}",
        "experiment_id": experiment_id,
        "seed": profile.get("seed"),
        "is_representative": experiment_id in representative_ids,
        "observational_eligible": profile.get("observational_eligible"),
        "evidence_channel": profile.get("evidence_channel"),
        "evidence_exclusion_reason": profile.get("evidence_exclusion_reason"),
        "telemetry_run_status": profile.get("telemetry_run_status"),
        "telemetry_experiment_id": profile.get("telemetry_experiment_id"),
        "telemetry_condition_id": profile.get("telemetry_condition_id"),
        "telemetry_experiment_role": profile.get("telemetry_experiment_role"),
        "experiment_folder": results_folder.name,
        "experiment_path": str(results_folder.resolve()),
        "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rule": rule,
        "source_profile": profile.get("source_file"),
        "lifetime": safe_int(profile.get("longest_age")),
        "classification": profile.get("analyzer_category"),
        "family": family,
        "tags": tags,
        "dynamic_score": None,
        "breathing_score": None,
        "collapse": collapse,
        "objects": profile.get("peak_objects"),
        "split_birth": None,
        "merge_death": None,
        "discovery_count": discovery.get("discovery_count"),
        "top_discovery": discovery.get("top_discovery"),
        "max_impact": discovery.get("max_impact"),
        "high_priority_questions": questions.get("high_priority_questions"),
        "hypotheses": questions.get("hypotheses"),
        "next_actions": questions.get("next_actions"),
        "research_value": compute_v30_research_value(profile, discovery, questions),
        "novelty_score": None,
        "record_count": 1,
        "seed_count": 0,
        "experiment_count": 1,
        # Deprecated compatibility field. This is a record count, not proof
        # of independent scientific replication.
        "replication_count": 1,
        "similar_to": [],
        "status": None,
        "analyzer_category": profile.get("analyzer_category"),
        "scientific_confidence": profile.get("scientific_confidence"),
        "layer_stack_score": safe_float(profile.get("layer_stack_score")),
        "civilization_stage": profile.get("civilization_stage"),
        "civilization_score": safe_float(profile.get("civilization_score")),
        "civilization_tech": safe_float(profile.get("civilization_tech")),
        "civilization_culture": safe_float(profile.get("civilization_culture")),
        "knowledge_score": safe_float(profile.get("knowledge_score")),
        "knowledge_axis": profile.get("knowledge_axis"),
        "knowledge_discoveries": profile.get("knowledge_discoveries") or [],
        "feedback_regime": profile.get("feedback_regime"),
        "feedback_score": safe_float(profile.get("feedback_score")),
        "feedback_self_direction": safe_float(profile.get("feedback_self_direction")),
        "emergence_confidence": profile.get("emergence_confidence"),
        "emergence_score": safe_float(profile.get("emergence_score")),
        "emergence_evidence_count": safe_int(profile.get("emergence_evidence_count")),
        "validation_grade": profile.get("validation_grade"),
        "validation_quality": safe_float(profile.get("validation_quality")),
        "validation_repeatability": safe_float(profile.get("validation_repeatability")),
        "validation_false_positive_risk": safe_float(profile.get("validation_false_positive_risk")),
        "validation_false_negative_risk": safe_float(profile.get("validation_false_negative_risk")),
        "validation_noise_sensitivity": safe_float(profile.get("validation_noise_sensitivity")),
        "validation_warning": profile.get("validation_warning"),
        "key_reasons": profile.get("key_reasons") or [],
        "warnings": profile.get("warnings") or [],
        "files": {
            "observer_profile": str(results_folder / "observer_profiles_v30.json"),
            "observer_profile_md": str(results_folder / "observer_profiles_v30.md"),
            "source_passport": profile.get("source_file"),
            "research_questions": str(find_file(results_folder, "research_questions.md") or "") or None,
            "discovery_report": str(find_file(results_folder, "discovery_report.md") or "") or None,
        },
    }
    record["is_scientific_observational"] = (
        record["is_representative"]
        and is_observational_eligible(profile)
    )
    record["status"] = status_from_record(record)
    return record


def build_legacy_record(results_folder: Path, discovery: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
    passport_path = find_file(results_folder, "passport_analysis.md")
    passport = parse_passport_analysis(passport_path)
    family = derive_family_legacy(passport)
    tags = derive_tags_legacy(passport, discovery, questions)
    record = {
        "schema": "atlas_record_legacy",
        "experiment_key": str(results_folder.resolve()),
        "experiment_folder": results_folder.name,
        "experiment_path": str(results_folder.resolve()),
        "date_added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rule": passport.get("rule"),
        "lifetime": passport.get("lifetime"),
        "classification": passport.get("classification"),
        "family": family,
        "tags": tags,
        "dynamic_score": passport.get("dynamic_score"),
        "breathing_score": passport.get("breathing_score"),
        "collapse": passport.get("collapse"),
        "objects": passport.get("objects"),
        "split_birth": passport.get("split_birth"),
        "merge_death": passport.get("merge_death"),
        "discovery_count": discovery.get("discovery_count"),
        "top_discovery": discovery.get("top_discovery"),
        "max_impact": discovery.get("max_impact"),
        "high_priority_questions": questions.get("high_priority_questions"),
        "hypotheses": questions.get("hypotheses"),
        "next_actions": questions.get("next_actions"),
        "research_value": compute_legacy_research_value(passport, discovery, questions),
        "novelty_score": None,
        "replication_count": 1,
        "similar_to": [],
        "status": None,
        "files": {
            "passport_analysis": str(passport_path) if passport_path else None,
            "research_questions": str(find_file(results_folder, "research_questions.md")) if find_file(results_folder, "research_questions.md") else None,
            "discovery_report": str(find_file(results_folder, "discovery_report.md")) if find_file(results_folder, "discovery_report.md") else None,
        },
    }
    record["status"] = status_from_record(record)
    return record


def build_records(
    results_folder: Path,
    aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    aliases = aliases or {}
    discovery = parse_discovery_report(
        find_file(results_folder, "discovery_report.md")
    )
    questions = parse_questions(
        find_file(results_folder, "research_questions.md")
    )
    profiles, representative_ids = load_observer_profile_data(results_folder)
    if profiles:
        return [
            build_record_from_profile(
                results_folder,
                canonicalize_profile(profile, aliases),
                discovery,
                questions,
                representative_ids,
            )
            for profile in profiles
        ]
    legacy = build_legacy_record(results_folder, discovery, questions)
    original = str(legacy.get("rule") or "unknown").zfill(5)
    legacy["rule"] = canonical_rule_id(original, aliases)
    if legacy["rule"] != original:
        legacy["source_rule_id"] = original
        legacy["canonicalized_from_alias"] = original
    return [legacy]


def load_atlas(path: Path) -> dict[str, Any]:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if "experiments" not in data:
            data["experiments"] = []
        data["version"] = "Universe Search Atlas v30"
        return data
    return {"version": "Universe Search Atlas v30", "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "updated": None, "experiments": []}


def save_atlas(atlas: dict[str, Any], path: Path) -> None:
    experiments = atlas.get("experiments", [])
    atlas["version"] = "Universe Search Atlas v30.2"
    atlas["record_count"] = len(experiments)
    atlas["unique_rule_count"] = len({
        str(record.get("rule") or "unknown").zfill(5)
        for record in experiments
    })
    atlas["representative_record_count"] = sum(
        1 for record in experiments if record.get("is_representative")
    )
    scientific_records = scientific_atlas_records(atlas)
    atlas["scientific_view"] = {
        "schema": "archon_scientific_view_v1",
        "record_count": len(scientific_records),
        "unique_rule_count": len({
            str(record.get("rule") or "unknown").zfill(5)
            for record in scientific_records
        }),
        "policy": (
            "One current observational-eligible representative per rule. "
            "Historical, experimental, perturbation and incomplete records "
            "remain in the Atlas but are excluded from scientific claims."
        ),
    }
    atlas["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(
        json.dumps(atlas, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def upsert_record(atlas: dict[str, Any], record: dict[str, Any]) -> str:
    key = record.get("experiment_key") or record.get("experiment_path")
    for i, old in enumerate(atlas["experiments"]):
        old_key = old.get("experiment_key") or old.get("experiment_path")
        if old_key == key:
            atlas["experiments"][i] = record
            return "updated"
    atlas["experiments"].append(record)
    return "added"


def fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)


def render_atlas_markdown(atlas: dict[str, Any], path: Path) -> None:
    experiments = sorted(atlas.get("experiments", []), key=lambda x: x.get("research_value") or 0, reverse=True)
    lines: list[str] = []
    lines.append("# Universe Search Research Atlas v30")
    lines.append("")
    unique_rule_count = len({str(e.get("rule") or "unknown").zfill(5) for e in experiments})
    lines.append(f"Experiment records: **{len(experiments)}**")
    representative_count = sum(
        1 for e in experiments if e.get("is_representative")
    )
    lines.append(f"Unique rules: **{unique_rule_count}**")
    lines.append(f"Representative records: **{representative_count}**")
    lines.append(
        "Record count is not interpreted as independent replication. "
        "Seed and experiment counts are reported separately."
    )
    lines.append(f"Updated: **{atlas.get('updated')}**")
    lines.append("")
    lines.append("## Top experiments")
    lines.append("")
    lines.append("| Rule | Family | Layer | EMG | VAL | KNOW | FB | CIV | Value | Novelty | Status |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for e in experiments:
        lines.append(
            f"| {e.get('rule')} | {e.get('family')} | "
            f"{fmt(e.get('layer_stack_score'))} | "
            f"{fmt(e.get('emergence_score'))} {e.get('emergence_confidence') or ''} | "
            f"{fmt(e.get('validation_quality'))} {e.get('validation_grade') or ''} | "
            f"{fmt(e.get('knowledge_score'))} | "
            f"{fmt(e.get('feedback_score'))} | "
            f"{fmt(e.get('civilization_score'))} | "
            f"{fmt(e.get('research_value'))} | "
            f"{fmt(e.get('novelty_score'))} | "
            f"{e.get('status')} |"
        )

    lines.append("")
    lines.append("## v30 layer leaders")
    lines.append("")
    leader_specs = [
        ("Emergence", "emergence_score"),
        ("Validation", "validation_quality"),
        ("Knowledge", "knowledge_score"),
        ("Feedback", "feedback_score"),
        ("Civilization", "civilization_score"),
        ("Layer stack", "layer_stack_score"),
    ]
    for title, key in leader_specs:
        top = sorted([e for e in experiments if e.get(key) is not None], key=lambda x: x.get(key) or 0, reverse=True)[:5]
        if not top:
            continue
        lines.append(f"### {title}")
        for e in top:
            lines.append(f"- **Rule {e.get('rule')}**: {fmt(e.get(key), 3)} | {e.get('family')} | {e.get('status')}")
        lines.append("")

    lines.append("## Families")
    lines.append("")
    family_map: dict[str, list[dict[str, Any]]] = {}
    for e in experiments:
        family_map.setdefault(e.get("family") or "Unclassified", []).append(e)
    for family, members in sorted(family_map.items(), key=lambda kv: len(kv[1]), reverse=True):
        member_rules = sorted({str(m.get("rule") or "unknown").zfill(5) for m in members})
        rules = ", ".join(member_rules)
        avg_emg = sum(safe_float(m.get("emergence_score")) for m in members) / max(1, len(members))
        avg_val = sum(safe_float(m.get("validation_quality")) for m in members) / max(1, len(members))
        lines.append(
            f"- **{family}**: {len(members)} record(s), {len(member_rules)} unique rule(s), "
            f"avg EMG={avg_emg:.2f}, avg VAL={avg_val:.2f}, rules: {rules}"
        )

    lines.append("")
    lines.append("## Similarity links")
    lines.append("")
    has_links = False
    for e in experiments:
        links = e.get("similar_to") or []
        if links:
            has_links = True
            best = links[0]
            lines.append(f"- **Rule {e.get('rule')}** is similar to **Rule {best.get('rule')}** ({best.get('similarity')}) in family **{best.get('family')}**.")
    if not has_links:
        lines.append("- No strong similarity links yet. Add more experiments to build clusters.")

    lines.append("")
    lines.append("## Discovery highlights")
    lines.append("")
    any_highlights = False
    for e in experiments:
        if e.get("top_discovery"):
            any_highlights = True
            lines.append(f"- **Rule {e.get('rule')}**: {e.get('top_discovery')} ({e.get('status')})")
    if not any_highlights:
        lines.append("- No discovery highlights yet.")

    lines.append("")
    lines.append("## Rule details")
    lines.append("")
    for e in experiments:
        lines.append(f"### Rule {e.get('rule')}")
        lines.append("")
        lines.append(f"- Family: **{e.get('family')}**")
        lines.append(f"- Status: **{e.get('status')}**")
        lines.append(f"- Scientific confidence: **{e.get('scientific_confidence') or '-'}**")
        lines.append(f"- Civilization: stage={e.get('civilization_stage') or '-'}, score={fmt(e.get('civilization_score'), 3)}, tech={fmt(e.get('civilization_tech'), 3)}, culture={fmt(e.get('civilization_culture'), 3)}")
        lines.append(f"- Knowledge: score={fmt(e.get('knowledge_score'), 3)}, axis={e.get('knowledge_axis') or '-'}, discoveries={', '.join(e.get('knowledge_discoveries') or []) or '-'}")
        lines.append(f"- Feedback: regime={e.get('feedback_regime') or '-'}, score={fmt(e.get('feedback_score'), 3)}, self_direction={fmt(e.get('feedback_self_direction'), 3)}")
        lines.append(f"- Emergence: {e.get('emergence_confidence') or '-'}, score={fmt(e.get('emergence_score'), 3)}, evidence={e.get('emergence_evidence_count') or 0}")
        lines.append(f"- Validation: {e.get('validation_grade') or '-'}, quality={fmt(e.get('validation_quality'), 3)}, repeatability={fmt(e.get('validation_repeatability'), 3)}, fp={fmt(e.get('validation_false_positive_risk'), 3)}, fn={fmt(e.get('validation_false_negative_risk'), 3)}")
        reasons = ", ".join(e.get("key_reasons") or []) or "-"
        warnings = ", ".join(e.get("warnings") or []) or "-"
        tags = ", ".join(e.get("tags") or []) or "-"
        lines.append(f"- Reasons: {reasons}")
        lines.append(f"- Warnings: {warnings}")
        lines.append(f"- Tags: {tags}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Update Project ARCHON research atlas with ObserverProfile v30 layers.")
    parser.add_argument(
        "results_folder",
        nargs="?",
        default=None,
        help="Raw Universe Search results folder. Default: Project ARCHON/Results/Universe_Search",
    )
    parser.add_argument(
        "--atlas",
        default=None,
        help="Atlas JSON path. Default: Project ARCHON/Atlas/Knowledge/research_atlas.json",
    )
    args = parser.parse_args()

    try:
        results_folder = resolve_results_dir(args.results_folder)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 1

    if args.atlas:
        raw_atlas = Path(args.atlas).expanduser()
        atlas_path = raw_atlas if raw_atlas.is_absolute() else PROJECT_ROOT / raw_atlas
        atlas_path = atlas_path.resolve()
    else:
        atlas_path = knowledge_atlas_dir() / "research_atlas.json"

    atlas_path.parent.mkdir(parents=True, exist_ok=True)
    md_path = atlas_path.with_suffix(".md")

    aliases = load_rule_aliases(atlas_path)
    records = build_records(results_folder, aliases)
    atlas = load_atlas(atlas_path)

    # Full profile history is an authoritative snapshot of the current
    # workspace. Replace the old experiment list completely so orphaned
    # legacy records cannot survive without provenance fields.
    removed_old_records = len(atlas.get("experiments", []))
    atlas["experiments"] = []
    actions = []
    for record in records:
        record["novelty_score"] = compute_novelty(record, atlas)
        actions.append(upsert_record(atlas, record))
    atlas["alias_resolution"] = {
        "schema": "archon_duplicate_rule_aliases_v1",
        "alias_count": len(aliases),
        "aliases": aliases,
    }
    update_similarity_and_replications(atlas)
    save_atlas(atlas, atlas_path)
    render_atlas_markdown(atlas, md_path)

    print("")
    print("=" * 64)
    print("Universe Search Atlas Engine v30.2 Alias Canonicalization")
    print("=" * 64)
    print(f"Records loaded:  {len(records)}")
    print(f"Previous records removed: {removed_old_records}")
    print(f"Added:           {actions.count('added')}")
    print(f"Updated:         {actions.count('updated')}")
    print(f"Atlas JSON:      {atlas_path}")
    print(f"Atlas Markdown:  {md_path}")
    print(f"Total records:   {len(atlas['experiments'])}")
    print("-" * 64)
    for record in sorted(records, key=lambda r: r.get("research_value") or 0, reverse=True)[:10]:
        print(
            f"Rule {record.get('rule')}: {record.get('family')} | "
            f"EMG={fmt(record.get('emergence_score'), 3)} {record.get('emergence_confidence') or ''} | "
            f"VAL={fmt(record.get('validation_quality'), 3)} {record.get('validation_grade') or ''} | "
            f"Value={fmt(record.get('research_value'))} | {record.get('status')}"
        )
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

