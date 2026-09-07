"""RELEASE3.1 clean bootstrap contract for Atlas runtime state.

Clean packages contain the code that owns Atlas schemas, but no scientific
memory from the machine used to build the release.  First run creates only the
Atlas directories.  Runtime owners materialize their own JSON/Markdown state
when real search or analysis work occurs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


SCHEMA = "archon_release3_1_atlas_clean_bootstrap_v1"
MILESTONE = "RELEASE3.1-ATLAS-CLEAN-BOOTSTRAP"

ATLAS_BOOTSTRAP_DIRECTORIES = (
    "Atlas/Knowledge/",
    "Atlas/Worlds/",
)

ACCUMULATED_KNOWLEDGE_FILES = (
    "duplicate_rule_aliases.json",
    "knowledge_base.json",
    "knowledge_base.md",
    "knowledge_base_integrity.json",
    "meta_science_history.json",
    "prediction_database.json",
    "prediction_database.md",
    "reference_control_registry.json",
    "reference_control_registry.md",
    "research_atlas.json",
    "research_atlas.md",
    "research_director_history.json",
    "rule_id_allocator.json",
    "consensus_database.json",
    "consensus_database.md",
)

SCHEMA_OWNER_FILES = (
    "archon_paths.py",
    "Universe_Search/universe_search_v34_closed_research_cycle.py",
    "Analyzer_next/production/catalog.py",
    "Analyzer_next/cli/atlas_engine.py",
    "Analyzer_next/core/reference_control_registry/contracts.py",
    "Analyzer_next/core/prediction_registry/contracts.py",
    "Analyzer_next/core/knowledge_base/contracts.py",
    "Analyzer_next/core/meta_science/contracts.py",
    "Analyzer_next/research/director/orchestrator.py",
)


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def ensure_atlas_layout(project_root: Path) -> dict:
    """Create Atlas runtime directories without seeding scientific records."""
    root = Path(project_root).resolve()
    created: list[str] = []
    preserved_files: list[str] = []
    for relative in ATLAS_BOOTSTRAP_DIRECTORIES:
        target = root / relative
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(relative)
        else:
            target.mkdir(parents=True, exist_ok=True)
        preserved_files.extend(
            path.relative_to(root).as_posix()
            for path in sorted(target.rglob("*"))
            if path.is_file()
        )
    return {
        "created_directories": created,
        "preserved_existing_files": preserved_files,
        "files_created": [],
        "policy": "directories-only; existing state is never deleted or rewritten",
    }


def build_atlas_bootstrap_manifest(
    root: Path,
    packaging_files: Iterable[str],
) -> dict:
    """Describe and validate the portable Atlas bootstrap boundary."""
    root = Path(root).resolve()
    packaged = sorted(set(str(item) for item in packaging_files))
    packaged_state = [
        relative
        for relative in packaged
        if any(
            relative == prefix.rstrip("/") or relative.startswith(prefix)
            for prefix in ATLAS_BOOTSTRAP_DIRECTORIES
        )
    ]
    missing_owners = [
        relative
        for relative in SCHEMA_OWNER_FILES
        if (root / relative).is_file() and relative not in packaged
    ]
    blockers: list[dict] = []
    if packaged_state:
        blockers.append({
            "code": "ATLAS_LOCAL_STATE_PACKAGED",
            "detail": (
                f"{len(packaged_state)} Atlas runtime-state file(s) entered "
                "the packaging whitelist"
            ),
            "files": packaged_state,
        })
    if missing_owners:
        blockers.append({
            "code": "ATLAS_SCHEMA_OWNER_MISSING",
            "detail": (
                f"{len(missing_owners)} code-owned Atlas schema owner(s) are "
                "missing from the runtime closure"
            ),
            "files": missing_owners,
        })

    payload = {
        "schema": SCHEMA,
        "milestone": MILESTONE,
        "status": "PASS" if not blockers else "BLOCKED",
        "bootstrap_mode": "DIRECTORIES_ONLY",
        "bootstrap_directories": list(ATLAS_BOOTSTRAP_DIRECTORIES),
        "bootstrap_files": [],
        "packaged_atlas_state": packaged_state,
        "accumulated_knowledge_files": list(ACCUMULATED_KNOWLEDGE_FILES),
        "schema_ownership": {
            "mode": "PACKAGED_PYTHON_CODE",
            "owners": list(SCHEMA_OWNER_FILES),
            "missing": missing_owners,
        },
        "first_run_contract": {
            "old_passports_absent": True,
            "old_principles_absent": True,
            "old_predictions_absent": True,
            "old_consensus_absent": True,
            "old_experiment_history_absent": True,
            "old_research_cycle_records_absent": True,
            "absolute_developer_paths_absent": True,
            "runtime_owners_create_state_on_demand": True,
            "existing_install_state_is_never_deleted": True,
        },
        "blockers": blockers,
    }
    payload["content_hash"] = _canonical_hash(payload)
    return payload


__all__ = [
    "ACCUMULATED_KNOWLEDGE_FILES",
    "ATLAS_BOOTSTRAP_DIRECTORIES",
    "MILESTONE",
    "SCHEMA",
    "SCHEMA_OWNER_FILES",
    "build_atlas_bootstrap_manifest",
    "ensure_atlas_layout",
]
