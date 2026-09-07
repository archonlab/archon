"""Recover the World Atlas index from authoritative active rule folders.

Universe Search writes a rule folder before committing the updated Atlas index.
An interrupted search can therefore leave valid ``rule.json`` folders missing
from ``atlas_index.json``.  The active folders are authoritative for identity;
the index remains the derived discovery/catalog projection.

Reconciliation is deliberately fail-closed.  It never guesses through
duplicate identities, active quarantined aliases, malformed rules, or an
apparently incomplete World Atlas materialization.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any, Mapping

from Analyzer_next.production.alias_canonicalization import (
    load_aliases,
    normalize_rule_id,
)


SCHEMA = "archon_world_atlas_index_reconciliation_v1"
REPORT_NAME = "world_atlas_index_reconciliation.json"
_FOLDER_PATTERN = re.compile(r"^rule_\d+_([0-9a-fA-F]{12,64})$")
_METRIC_FIELDS = {
    "active": "active",
    "edge": "edge",
    "life": "ms_local_life",
    "flow": "ms_flow",
    "rotation": "ms_rotation_flow",
    "memory": "memory_trace_score",
    "recovery": "cosmic_recovery",
    "region": "best_region_score",
    "entities": "entity_count",
    "tracks": "persistent_tracks",
    "observer_id": "observer_id",
    "observer_archetype": "observer_archetype",
    "observer_note": "observer_note",
    "post_test_truth": "post_test_truth",
    "crystal_order": "crystal_order",
    "defect_density": "defect_density",
    "defect_persistence": "defect_persistence",
    "defect_motion": "defect_motion",
    "quasi_particle_score": "quasi_particle_score",
    "organism_lifetime": "organism_lifetime",
    "organism_peak_largest": "organism_peak_largest",
    "organism_events": "organism_events",
    "organism_survived_probe": "organism_survived_probe",
    "information_survival": "information_survival",
    "identity_persistence": "identity_persistence",
    "legacy_score": "legacy_score",
    "post_collapse_structure": "post_collapse_structure",
    "expansion_front_speed": "expansion_front_speed",
    "collapse_reason_hint": "collapse_reason_hint",
}


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _write_if_changed(path: Path, content: str) -> bool:
    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except OSError:
        pass
    _atomic_text(path, content)
    return True


def _file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _rule_key(folder: Path, payload: Mapping[str, Any]) -> str | None:
    for field in ("key", "genome_hash", "rule_hash"):
        value = str(payload.get(field) or "").strip().lower()
        if value:
            return value
    match = _FOLDER_PATTERN.match(folder.name)
    return match.group(1).lower() if match else None


def _load_active_rules(
    atlas_root: Path,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    active: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for rule_file in sorted(atlas_root.rglob("rule.json")):
        payload = _read_json(rule_file, None)
        if not isinstance(payload, dict):
            errors.append({
                "code": "RULE_JSON_INVALID",
                "path": str(rule_file),
            })
            continue
        rule_id = normalize_rule_id(payload.get("rule_id"))
        if rule_id is None:
            errors.append({
                "code": "RULE_ID_INVALID",
                "path": str(rule_file),
            })
            continue
        if rule_id in active:
            errors.append({
                "code": "DUPLICATE_ACTIVE_RULE_ID",
                "rule_id": rule_id,
                "path": str(rule_file),
                "first_path": str(active[rule_id]["rule_file"]),
            })
            continue
        active[rule_id] = {
            "rule_file": rule_file,
            "folder": rule_file.parent.resolve(),
            "payload": payload,
        }
    return active, errors


def _load_index_rows(
    index_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, str]]]:
    if not index_path.exists():
        return [], {}, []
    payload = _read_json(index_path, None)
    if not isinstance(payload, list):
        return [], {}, [{
            "code": "ATLAS_INDEX_ROOT_INVALID",
            "path": str(index_path),
        }]
    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for position, raw_row in enumerate(payload):
        if not isinstance(raw_row, dict):
            errors.append({
                "code": "ATLAS_INDEX_ROW_INVALID",
                "position": str(position),
            })
            continue
        row = dict(raw_row)
        rule_id = normalize_rule_id(row.get("rule_id"))
        if rule_id is None:
            errors.append({
                "code": "ATLAS_INDEX_RULE_ID_INVALID",
                "position": str(position),
            })
            continue
        if rule_id in by_id:
            errors.append({
                "code": "DUPLICATE_ATLAS_INDEX_RULE_ID",
                "rule_id": rule_id,
                "position": str(position),
            })
            continue
        rows.append(row)
        by_id[rule_id] = row
    return rows, by_id, errors


def _recovered_row(record: Mapping[str, Any]) -> dict[str, Any] | None:
    folder = Path(record["folder"])
    payload = record["payload"]
    key = _rule_key(folder, payload)
    if not key:
        return None
    metrics = _read_json(folder / "metrics.json", {})
    if not isinstance(metrics, dict):
        metrics = {}
    world_class = (
        metrics.get("class")
        or metrics.get("world_class")
        or folder.parent.name.replace("_", " ").title()
    )
    score = metrics.get("score")
    if score is None:
        score = metrics.get("last_evaluated_score", 0.0)
    row: dict[str, Any] = {
        "key": key,
        "rule_id": int(normalize_rule_id(payload.get("rule_id")) or 0),
        "class": world_class,
        "generation": metrics.get("generation"),
        "score_mode": metrics.get("score_mode"),
        "score": score,
        "source": metrics.get("source") or "atlas_index_reconciliation",
        "folder": str(folder).replace("\\", "/"),
        "preview": None,
        "preview_gif": None,
        "index_recovery": {
            "schema": SCHEMA,
            "reason": "ACTIVE_RULE_MISSING_FROM_INDEX",
        },
    }
    for target, source in _METRIC_FIELDS.items():
        row[target] = metrics.get(source)
    return row


def _refresh_paths(row: dict[str, Any], folder: Path) -> int:
    changes = 0
    folder_text = str(folder).replace("\\", "/")
    if row.get("folder") != folder_text:
        row["folder"] = folder_text
        changes += 1
    for field, filename in (("preview", "preview.png"), ("preview_gif", "preview.gif")):
        candidate = folder / filename
        value = str(candidate).replace("\\", "/") if candidate.is_file() else None
        if row.get(field) != value:
            row[field] = value
            changes += 1
    latest = row.get("latest_evidence")
    if latest:
        candidate = folder / "search_evidence" / Path(str(latest)).name
        if candidate.is_file():
            value = str(candidate).replace("\\", "/")
            if latest != value:
                row["latest_evidence"] = value
                changes += 1
    return changes


def _score(row: Mapping[str, Any]) -> float:
    try:
        return float(row.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _backup_indexes(
    *,
    index_path: Path,
    jsonl_path: Path,
    backup_root: Path,
) -> list[str]:
    digest = _file_digest(index_path) or "missing"
    target = backup_root / digest[:16]
    target.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for source in (index_path, jsonl_path):
        if not source.is_file():
            continue
        destination = target / source.name
        if not destination.exists():
            shutil.copy2(source, destination)
        copied.append(str(destination))
    return copied


def reconcile_world_atlas_index(
    *,
    atlas_root: Path,
    knowledge_root: Path,
    analysis_root: Path,
) -> dict[str, Any]:
    """Make the derived Atlas index exactly cover authoritative active rules."""
    atlas_root = atlas_root.expanduser().resolve()
    knowledge_root = knowledge_root.expanduser().resolve()
    analysis_root = analysis_root.expanduser().resolve()
    index_path = atlas_root / "atlas_index.json"
    jsonl_path = atlas_root / "atlas_index.jsonl"
    report_path = analysis_root / "Integrity" / REPORT_NAME

    active, active_errors = _load_active_rules(atlas_root)
    old_rows, old_by_id, index_errors = _load_index_rows(index_path)
    aliases = load_aliases(knowledge_root)
    active_aliases = sorted(set(active) & set(aliases))
    errors = [*active_errors, *index_errors]
    if active_aliases:
        errors.append({
            "code": "ALIASES_STILL_ACTIVE",
            "rule_ids": ",".join(active_aliases),
        })
    if not active and old_rows:
        errors.append({
            "code": "INCOMPLETE_WORLD_ATLAS_MATERIALIZATION",
            "detail": "Index is populated but no active rule.json files were found.",
        })

    missing_ids = sorted(set(active) - set(old_by_id))
    extra_ids = sorted(set(old_by_id) - set(active))
    rebuilt: list[dict[str, Any]] = []
    recovered_ids: list[str] = []
    refreshed_path_fields = 0
    seen_keys: dict[str, str] = {}

    if not errors:
        for rule_id, record in sorted(active.items()):
            existing = old_by_id.get(rule_id)
            if existing is None:
                row = _recovered_row(record)
                if row is None:
                    errors.append({
                        "code": "RULE_KEY_UNRECOVERABLE",
                        "rule_id": rule_id,
                        "path": str(record["folder"]),
                    })
                    continue
                recovered_ids.append(rule_id)
            else:
                row = dict(existing)
                row["rule_id"] = int(rule_id)
                folder_key = _rule_key(record["folder"], record["payload"])
                existing_key = str(row.get("key") or row.get("genome_hash") or "").lower()
                if folder_key and existing_key and folder_key != existing_key:
                    errors.append({
                        "code": "RULE_KEY_MISMATCH",
                        "rule_id": rule_id,
                        "index_key": existing_key,
                        "folder_key": folder_key,
                    })
                    continue
            refreshed_path_fields += _refresh_paths(row, record["folder"])
            key = str(row.get("key") or row.get("genome_hash") or "").lower()
            if key and key in seen_keys and seen_keys[key] != rule_id:
                errors.append({
                    "code": "DUPLICATE_ACTIVE_RULE_KEY",
                    "rule_id": rule_id,
                    "other_rule_id": seen_keys[key],
                    "key": key,
                })
                continue
            if key:
                seen_keys[key] = rule_id
            rebuilt.append(row)

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "FAILED" if errors else "CURRENT",
        "changed": False,
        "active_rules": len(active),
        "previous_index_rules": len(old_by_id),
        "final_index_rules": len(old_by_id),
        "missing_rule_ids": missing_ids,
        "extra_rule_ids": extra_ids,
        "recovered_rule_ids": [],
        "removed_rule_ids": [],
        "refreshed_path_fields": 0,
        "backup_files": [],
        "errors": errors,
    }

    if not errors:
        rebuilt.sort(
            key=lambda row: (
                -_score(row),
                normalize_rule_id(row.get("rule_id")) or "",
            )
        )
        index_text = _json_text(rebuilt)
        jsonl_text = "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in rebuilt
        )
        semantic_change = old_rows != rebuilt
        jsonl_change = (
            not jsonl_path.exists()
            or jsonl_path.read_text(encoding="utf-8") != jsonl_text
        )
        changed = semantic_change or jsonl_change
        backups: list[str] = []
        if changed:
            backups = _backup_indexes(
                index_path=index_path,
                jsonl_path=jsonl_path,
                backup_root=(
                    analysis_root
                    / "Integrity"
                    / "WorldAtlasIndexBackups"
                ),
            )
            _write_if_changed(index_path, index_text)
            _write_if_changed(jsonl_path, jsonl_text)
        report.update({
            "status": "REPAIRED" if changed else "CURRENT",
            "changed": changed,
            "final_index_rules": len(rebuilt),
            "recovered_rule_ids": recovered_ids,
            "removed_rule_ids": extra_ids,
            "refreshed_path_fields": refreshed_path_fields,
            "backup_files": backups,
            "errors": [],
        })

    _write_if_changed(report_path, _json_text(report))
    report["report_path"] = str(report_path)
    return report


__all__ = ["REPORT_NAME", "SCHEMA", "reconcile_world_atlas_index"]
