"""Filesystem repository preserving Mechanism Engine v2.2 semantics."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from Analyzer_next.core.mechanism.contracts import (
    MechanismInputs,
    MechanismPaths,
    MechanismRunResult,
    RuleSource,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rule_aliases(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    raw = payload.get("aliases", {}) if isinstance(payload, dict) else {}
    aliases: dict[str, str] = {}
    if not isinstance(raw, dict):
        return aliases
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
        return str(value)
    seen: set[str] = set()
    while current in aliases and current not in seen:
        seen.add(current)
        current = aliases[current]
    return current


def load_representative_behaviours(
    path: Path,
    aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    aliases = aliases or {}
    if not path.exists():
        raise FileNotFoundError(
            f"observer_profiles_v30.json not found: {path}. "
            "Run Observer Profile first."
        )
    payload = read_json(path)
    profiles = payload.get("profiles", [])
    if not isinstance(profiles, list):
        raise ValueError(
            "Invalid observer_profiles_v30.json: profiles is not a list"
        )

    best: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        raw_rule = profile.get("rule")
        if raw_rule is None:
            continue
        source_rule_id = str(raw_rule).zfill(5)
        rule_id = canonical_rule_id(source_rule_id, aliases)
        candidate = dict(profile)
        candidate["rule"] = rule_id
        candidate["source_rule_id"] = source_rule_id
        candidate["canonicalized_from_alias"] = (
            source_rule_id if source_rule_id != rule_id else None
        )
        current = best.get(rule_id)
        candidate_key = (
            int(candidate.get("final_tick") or 0),
            str(candidate.get("created") or ""),
        )
        current_key = (
            (
                int(current.get("final_tick") or 0),
                str(current.get("created") or ""),
            )
            if current
            else (-1, "")
        )
        if current is None or candidate_key > current_key:
            best[rule_id] = candidate

    behaviours: list[dict[str, Any]] = []
    for rule_id in sorted(best):
        profile = best[rule_id]
        collapse_tick = profile.get("collapse_tick")
        behaviours.append({
            "rule": rule_id,
            "source_rule_id": profile.get("source_rule_id", rule_id),
            "canonicalized_from_alias": profile.get(
                "canonicalized_from_alias"
            ),
            "lifetime": int(
                profile.get("longest_age")
                if profile.get("longest_age") not in (None, "")
                else (
                    profile.get("final_tick")
                    if profile.get("final_tick") not in (None, "")
                    else 0
                )
            ),
            "classification": (
                profile.get("analyzer_category")
                or profile.get("scientific_confidence")
                or "unknown"
            ),
            "dynamic_score": profile.get("emergence_score"),
            "breathing_score": profile.get("feedback_score"),
            "collapse": (
                "No"
                if collapse_tick in (None, "", -1)
                else f"Yes, tick {collapse_tick}"
            ),
            "objects": f"0-{int(profile.get('peak_objects') or 0)}",
            "source_profile": profile.get("source_file"),
            "validation_quality": profile.get("validation_quality"),
            "knowledge_score": profile.get("knowledge_score"),
            "feedback_score": profile.get("feedback_score"),
            "emergence_score": profile.get("emergence_score"),
        })
    return behaviours


def find_rule_json(
    world_atlas_root: Path,
    legacy_atlas_root: Path,
    rule_id: str,
) -> Path:
    atlas_root = (
        world_atlas_root if world_atlas_root.exists() else legacy_atlas_root
    )
    if not atlas_root.exists():
        raise FileNotFoundError(
            "world atlas folder not found. Checked: "
            f"{world_atlas_root} and {legacy_atlas_root}"
        )
    rule_num = int(rule_id)
    patterns = [
        f"rule_{rule_id}_*/rule.json",
        f"rule_{rule_num:05d}_*/rule.json",
        f"rule_{rule_num}_*/rule.json",
        "*/rule.json",
        "*/*/rule.json",
    ]
    candidates: list[Path] = []
    for pattern in patterns:
        for path in atlas_root.glob(pattern):
            if path not in candidates:
                candidates.append(path)
    for path in candidates:
        parent = path.parent.name.lower()
        if (
            f"rule_{rule_id}" in parent
            or f"rule_{rule_num:05d}" in parent
            or f"rule_{rule_num}" in parent
        ):
            return path
    for path in candidates:
        try:
            data = read_json(path)
            if int(data.get("rule_id", -1)) == rule_num:
                return path
        except Exception:
            continue
    raise FileNotFoundError(
        f"rule.json for rule {rule_id} not found inside {atlas_root}"
    )


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.name + ".", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


class FileMechanismRepository:
    def load(
        self,
        paths: MechanismPaths,
        *,
        selected_rule: str | None = None,
    ) -> MechanismInputs:
        aliases = load_rule_aliases(
            paths.knowledge_root / "duplicate_rule_aliases.json"
        )
        behaviours = load_representative_behaviours(
            paths.results_root / "observer_profiles_v30.json",
            aliases,
        )
        if selected_rule is not None:
            requested = str(selected_rule).zfill(5)
            wanted = canonical_rule_id(requested, aliases)
            behaviours = [
                behaviour
                for behaviour in behaviours
                if behaviour["rule"] == wanted
            ]
            if not behaviours:
                raise ValueError(
                    f"Rule {requested} (canonical {wanted}) not found in "
                    "observer_profiles_v30.json"
                )

        sources: dict[str, RuleSource] = {}
        errors: dict[str, str] = {}
        deferred: dict[str, str] = {}
        for behaviour in behaviours:
            rule_id = behaviour["rule"]
            try:
                path = find_rule_json(
                    paths.world_atlas_root,
                    paths.results_root / "atlas",
                    rule_id,
                )
                sources[rule_id] = RuleSource(path=path, payload=read_json(path))
            except FileNotFoundError as exc:
                deferred[rule_id] = str(exc)
            except Exception as exc:
                errors[rule_id] = str(exc)
        return MechanismInputs(
            aliases=aliases,
            behaviours=tuple(behaviours),
            rule_sources=sources,
            rule_errors=errors,
            rule_deferred=deferred,
        )

    def save(
        self,
        paths: MechanismPaths,
        result: MechanismRunResult,
    ) -> None:
        paths.output_directory.mkdir(parents=True, exist_ok=True)
        for path, report in result.reports.items():
            path.write_text(report, encoding="utf-8")
        write_json_atomic(paths.aggregate_json, result.aggregate)
