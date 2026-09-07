#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project ARCHON Search Mode / Search Job Loader v1.0.

This is a thin orchestration layer above the existing Universe Search engine.

It does not replace scoring or EvolutionPolicy. It:
- loads one Search job from Analyzer/experiment_plan.json;
- normalizes explicit Search modes;
- converts the selected job into ResearchPlan-compatible intent;
- resolves Atlas seed rules without changing their canonical rule.json files;
- writes a provenance manifest for the Search run.

Supported modes:
- ordinary
- diversity
- cohort_target
- counterexample
- local_around_rule
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

LOADER_VERSION = "v1.2 Search Job Loader + Resume Integrity"
SEARCH_MODES = {
    "ordinary",
    "diversity",
    "cohort_target",
    "counterexample",
    "local_around_rule",
}


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists() and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def normalize_rule_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return f"{int(text):05d}"
    except Exception:
        return text


@dataclass
class SearchModeConfig:
    version: str = LOADER_VERSION
    search_mode: str = "ordinary"
    active: bool = False

    source_plan: Optional[str] = None
    job_id: Optional[str] = None
    claim_id: Optional[str] = None
    target_regime: Optional[str] = None
    priority: int = 0
    constraints: dict[str, Any] = field(default_factory=dict)
    seed_rules: list[str] = field(default_factory=list)

    creates_canonical_rules: bool = True
    preserve_parent_rules: bool = True
    record_provenance: bool = True

    requested_score_mode: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def valid(self) -> bool:
        return not self.errors


def search_config_identity(
    config: Optional[SearchModeConfig],
) -> dict[str, Any]:
    """Return the scientific identity that must survive checkpoint resume.

    File locations and explanatory notes are deliberately excluded. The
    identity contains only fields capable of changing the experiment itself.
    """
    if config is None:
        payload: dict[str, Any] = {
            "search_mode": "ordinary",
            "job_id": None,
            "claim_id": None,
            "target_regime": None,
            "constraints": {},
            "seed_rules": [],
            "requested_score_mode": None,
        }
    else:
        payload = {
            "search_mode": str(config.search_mode or "ordinary"),
            "job_id": config.job_id,
            "claim_id": config.claim_id,
            "target_regime": config.target_regime,
            "constraints": dict(config.constraints or {}),
            "seed_rules": sorted(dict.fromkeys(config.seed_rules or [])),
            "requested_score_mode": config.requested_score_mode,
        }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema": "archon_search_config_identity_v1",
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        **payload,
    }


def default_experiment_plan(project_root: Path) -> Path:
    return Path(project_root) / "Results" / "Analysis" / "experiment_plan.json"


def _find_job(
    jobs: list[dict[str, Any]],
    *,
    job_id: Optional[str] = None,
    target_regime: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    if job_id:
        wanted = job_id.strip().lower()
        for job in jobs:
            if str(job.get("id") or "").strip().lower() == wanted:
                return job
        return None
    if target_regime:
        wanted = target_regime.strip().lower()
        for job in jobs:
            if str(job.get("target_regime") or "").strip().lower() == wanted:
                return job
        return None
    return jobs[0] if jobs else None


def load_search_mode_config(
    *,
    project_root: Path,
    search_mode: str = "ordinary",
    experiment_plan: Optional[Path] = None,
    job_id: Optional[str] = None,
    target_regime: Optional[str] = None,
    seed_rules: Optional[Iterable[str]] = None,
    requested_score_mode: Optional[str] = None,
) -> SearchModeConfig:
    mode = str(search_mode or "ordinary").strip().lower()
    config = SearchModeConfig(
        search_mode=mode,
        active=mode != "ordinary",
        requested_score_mode=requested_score_mode,
    )

    if mode not in SEARCH_MODES:
        config.errors.append(
            f"unknown search mode {mode!r}; falling back to ordinary"
        )
        config.search_mode = "ordinary"
        config.active = False
        mode = "ordinary"

    explicit_seeds = [
        normalize_rule_id(x)
        for x in (seed_rules or [])
        if normalize_rule_id(x)
    ]

    if mode in {"cohort_target", "counterexample"}:
        plan_path = Path(
            experiment_plan or default_experiment_plan(project_root)
        ).expanduser().resolve()
        config.source_plan = str(plan_path)
        payload = _read_json(plan_path, {})
        jobs = payload.get("search_jobs", []) if isinstance(payload, dict) else []
        jobs = [x for x in jobs if isinstance(x, dict)]
        job = _find_job(
            jobs,
            job_id=job_id,
            target_regime=target_regime,
        )
        if job is None:
            config.errors.append(
                "no matching search job found in experiment_plan.json"
            )
            return config

        config.job_id = str(job.get("id") or "") or None
        config.claim_id = str(job.get("claim_id") or "") or None
        config.target_regime = (
            str(job.get("target_regime") or "") or None
        )
        config.priority = int(job.get("priority") or 0)
        config.constraints = dict(job.get("constraints") or {})
        config.seed_rules = [
            normalize_rule_id(x)
            for x in (job.get("seed_rules") or [])
            if normalize_rule_id(x)
        ]
        output_policy = job.get("output_policy") or {}
        config.creates_canonical_rules = bool(
            output_policy.get("creates_canonical_rules", True)
        )
        config.preserve_parent_rules = bool(
            output_policy.get("preserve_parent_rules", True)
        )
        config.record_provenance = bool(
            output_policy.get("record_provenance", True)
        )
        config.notes.append(
            f"loaded Analyzer search job {config.job_id}"
        )

        if mode == "counterexample":
            config.notes.append(
                "counterexample mode uses control-heavy search intent"
            )

    elif mode == "local_around_rule":
        config.seed_rules = explicit_seeds
        if not config.seed_rules:
            config.errors.append(
                "local_around_rule requires at least one --seed-rule"
            )
        config.notes.append(
            "local mode keeps Atlas parents immutable and searches nearby"
        )

    elif mode == "diversity":
        config.seed_rules = explicit_seeds
        config.notes.append(
            "diversity mode raises exploration and novelty pressure"
        )

    else:
        config.seed_rules = explicit_seeds
        config.notes.append("ordinary legacy-compatible search")

    # Explicit CLI seeds extend Planner seeds without duplicates.
    for rid in explicit_seeds:
        if rid not in config.seed_rules:
            config.seed_rules.append(rid)

    return config


def _mode_actions(config: SearchModeConfig) -> list[dict[str, Any]]:
    if config.search_mode == "ordinary":
        return []
    if config.search_mode == "diversity":
        return [{
            "id": "SEARCH-MODE-DIVERSITY",
            "type": "explore",
            "mode": "explore",
            "title": "Increase diversity and novelty coverage",
            "source": "SearchModeConfig",
        }]
    if config.search_mode == "local_around_rule":
        return [{
            "id": "SEARCH-MODE-LOCAL",
            "type": "local",
            "mode": "local",
            "title": "Search the neighbourhood of selected Atlas rules",
            "seed_rules": list(config.seed_rules),
            "source": "SearchModeConfig",
        }]
    if config.search_mode == "counterexample":
        return [{
            "id": config.job_id or "SEARCH-MODE-COUNTEREXAMPLE",
            "type": "control",
            "mode": "control",
            "title": (
                f"Search for counterexample regime "
                f"{config.target_regime or 'unknown'}"
            ),
            "claim_id": config.claim_id,
            "target_regime": config.target_regime,
            "constraints": dict(config.constraints),
            "seed_rules": list(config.seed_rules),
            "source": "experiment_plan.json",
        }]
    return [{
        "id": config.job_id or "SEARCH-MODE-COHORT",
        "type": "local",
        "mode": "local",
        "title": (
            f"Fill cohort regime "
            f"{config.target_regime or 'unknown'}"
        ),
        "claim_id": config.claim_id,
        "target_regime": config.target_regime,
        "constraints": dict(config.constraints),
        "seed_rules": list(config.seed_rules),
        "source": "experiment_plan.json",
    }]


def apply_config_to_research_plan(
    plan: Any,
    config: SearchModeConfig,
) -> Any:
    """Attach explicit Search intent without replacing ResearchBridge."""
    if plan is None or config is None:
        return plan

    setattr(plan, "search_mode_config", config.to_dict())
    setattr(plan, "search_mode", config.search_mode)
    setattr(plan, "search_job_id", config.job_id)
    setattr(plan, "target_regime", config.target_regime)
    setattr(plan, "target_constraints", dict(config.constraints))
    setattr(plan, "seed_rules", list(config.seed_rules))

    if not config.active:
        return plan

    plan.active = True
    plan.mode = f"search_mode:{config.search_mode}"

    existing_actions = list(getattr(plan, "actions", []) or [])
    actions = _mode_actions(config) + existing_actions
    plan.actions = actions

    action_types = set(getattr(plan, "action_types", []) or [])
    action_types.update(
        str(x.get("type") or x.get("mode") or "")
        for x in _mode_actions(config)
    )
    plan.action_types = sorted(x for x in action_types if x)

    notes = list(getattr(plan, "notes", []) or [])
    notes.extend(config.notes)
    notes.extend(f"SearchModeConfig warning: {x}" for x in config.errors)
    plan.notes = notes

    priorities = list(getattr(plan, "priorities", []) or [])
    if config.target_regime:
        priorities.insert(
            0,
            f"Search target: {config.target_regime}",
        )
    plan.priorities = priorities
    return plan


def find_atlas_rule_file(
    atlas_worlds_dir: Path,
    rule_id: str,
) -> Optional[Path]:
    rid = normalize_rule_id(rule_id)
    if not rid:
        return None
    matches = sorted(
        Path(atlas_worlds_dir).glob(f"rule_{rid}_*/rule.json")
    )
    if matches:
        return matches[0]
    # Compatibility fallback for unusual legacy names.
    matches = sorted(
        Path(atlas_worlds_dir).rglob(f"rule_{rid}*/rule.json")
    )
    return matches[0] if matches else None


def load_seed_rule_payloads(
    atlas_worlds_dir: Path,
    seed_rules: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payloads: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for rid in seed_rules:
        normalized = normalize_rule_id(rid)
        path = find_atlas_rule_file(atlas_worlds_dir, normalized)
        if path is None:
            provenance.append({
                "rule_id": normalized,
                "status": "missing",
                "source_file": None,
            })
            continue
        payload = _read_json(path, None)
        if not isinstance(payload, dict):
            provenance.append({
                "rule_id": normalized,
                "status": "invalid_json",
                "source_file": str(path),
            })
            continue
        payloads.append(payload)
        provenance.append({
            "rule_id": normalized,
            "status": "loaded",
            "source_file": str(path),
        })
    return payloads, provenance


def write_search_mode_manifest(
    run_history_dir: Path,
    config: SearchModeConfig,
    *,
    score_mode: str,
    search_run_id: str,
    seed_provenance: Optional[list[dict[str, Any]]] = None,
) -> Path:
    path = Path(run_history_dir) / "search_mode_manifest.json"
    payload = {
        "schema": "archon_search_mode_manifest_v2",
        "loader_version": LOADER_VERSION,
        "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "search_run_id": search_run_id,
        "score_mode": score_mode,
        "config": config.to_dict(),
        "seed_provenance": list(seed_provenance or []),
    }
    _atomic_write_json(path, payload)
    return path
