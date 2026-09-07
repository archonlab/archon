#!/usr/bin/env python3
"""Build the canonical ARCHON Studio snapshot from release-safe scientific outputs.

STUDIO5 keeps the Web UI downstream of ARCHON's scientific pipeline. It reads
canonical Atlas/Knowledge state, normalizes it into a human-facing contract,
and copies only preview assets referenced by the generated Research Feed.
Scientific engine modules are never imported by Studio.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_IMPORT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_IMPORT_ROOT))
from World_Portability import compute_world_uid  # noqa: E402

SCHEMA = "archon_studio_snapshot_v5"
FEED_LIMITS = {
    "Worlds": 6,
    "Experiments": 6,
    "Evidence": 8,
    "Mechanisms": 6,
    "Predictions": 6,
}


def _read_json(path: Path, expected: type | tuple[type, ...]) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"STUDIO_SNAPSHOT_MISSING_SOURCE: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"STUDIO_SNAPSHOT_INVALID_JSON: {path}: {exc}") from exc
    if not isinstance(value, expected):
        names = ", ".join(t.__name__ for t in expected) if isinstance(expected, tuple) else expected.__name__
        raise SystemExit(f"STUDIO_SNAPSHOT_WRONG_TYPE: {path}: expected {names}, got {type(value).__name__}")
    return value

def _read_json_optional(path: Path, expected: type | tuple[type, ...], default: Any) -> Any:
    """Read an optional canonical source without turning first-run Studio into an error.

    Missing scientific state is normal before the first Search/Analyzer cycle. Existing
    but malformed files still fail closed because corruption is different from absence.
    """
    if not path.is_file():
        return default
    return _read_json(path, expected)


def _world_uid(root: Path, world: dict[str, Any]) -> str | None:
    recorded = world.get("world_uid")
    if isinstance(recorded, str) and recorded.startswith("WORLD-") and len(recorded) == 70:
        return recorded
    candidates: list[Path] = []
    raw_folder = world.get("folder")
    if isinstance(raw_folder, str) and raw_folder.strip():
        folder = Path(raw_folder)
        candidates.append((folder if folder.is_absolute() else root / folder) / "rule.json")
    try:
        rule_id = int(world.get("rule_id"))
        key = str(world.get("key") or "").strip()
        if key:
            candidates.extend((root / "Atlas" / "Worlds").glob(f"*/rule_{rule_id:05d}_{key}/rule.json"))
        candidates.extend((root / "Atlas" / "Worlds").glob(f"*/rule_{rule_id:05d}_*/rule.json"))
    except (TypeError, ValueError):
        pass
    for path in candidates:
        try:
            resolved = path.resolve()
            resolved.relative_to(root.resolve())
            rule = json.loads(resolved.read_text(encoding="utf-8"))
            return compute_world_uid(rule)
        except Exception:
            continue
    return None


def _has_scientific_results(root: Path) -> bool:
    for directory in (root / "Results" / "Universe_Search", root / "Results" / "Analysis"):
        if not directory.is_dir():
            continue
        try:
            if any(
                path.is_file()
                and not any(part.startswith(".") or part in {"Integrity", "__pycache__"} for part in path.relative_to(directory).parts)
                and path.suffix.lower() not in {".log", ".lock", ".tmp", ".pyc"}
                and path.name.lower() not in {"readme", "readme.md", "readme.txt"}
                for path in directory.rglob("*")
            ):
                return True
        except OSError:
            continue
    return False


def _empty_snapshot(root: Path) -> dict[str, Any]:
    feed_sources = {
        kind: {"available": 0, "cards": 0}
        for kind in ("Worlds", "Experiments", "Evidence", "Mechanisms", "Predictions", "Director")
    }
    browser_meta = {
        "world_count": 0,
        "world_preview_count": 0,
        "rule_count": 0,
        "scientific_rule_count": 0,
        "rules_with_worlds": 0,
        "experiment_count": 0,
        "representative_experiment_count": 0,
        "observational_experiment_count": 0,
        "evidence_count": 0,
        "evidence_with_support": 0,
        "mechanism_count": 0,
        "medium_plus_mechanism_count": 0,
        "scientific_mechanism_count": 0,
        "prediction_count": 0,
        "open_prediction_count": 0,
        "confirmed_prediction_count": 0,
    }
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "empty_research_state",
        "source_state": {
            "atlas_updated": None,
            "knowledge_generated": None,
            "director_generated_at": None,
            "live_results_available": _has_scientific_results(root),
            "knowledge_integrity_ok": False,
            "research_empty": True,
        },
        "metrics": [
            {"key": "worlds", "label": "Worlds", "value": 0, "detail": "No retained worlds yet"},
            {"key": "rules", "label": "Rules", "value": 0, "detail": "Research has not started"},
            {"key": "experiments", "label": "Experiments", "value": 0, "detail": "No experiments yet"},
            {"key": "discoveries", "label": "Discoveries", "value": 0, "detail": "No discoveries yet"},
            {"key": "mechanisms", "label": "Mechanisms", "value": 0, "detail": "No mechanisms yet"},
            {"key": "predictions", "label": "Predictions", "value": 0, "detail": "No predictions yet"},
        ],
        "research_map": {"worlds": 0, "rules": 0, "mechanisms": 0, "principles": 0, "predictions": 0},
        "director": {
            "generated_at": None,
            "stage": "Research not started",
            "trend": "Waiting",
            "maturity": 0.0,
            "risk": 0.0,
            "maturity_delta": 0.0,
            "risk_delta": 0.0,
            "evidence_strength": 0.0,
            "consensus_strength": 0.0,
            "planned_experiments": 0,
            "confirmed_predictions": 0,
            "testing_predictions": 0,
            "integrity_ok": False,
            "summary": "No retained worlds are present yet. Start Universe Search to begin research; Studio will populate automatically when canonical Atlas data appears.",
            "priority_follow_up": None,
            "sources": [],
        },
        "highlights": [],
        "feed": [],
        "feed_meta": {"card_count": 0, "preview_card_count": 0, "source_family_count": 0, "sources": feed_sources},
        "worlds": [],
        "rules": [],
        "experiments": [],
        "evidence": [],
        "mechanisms": [],
        "predictions": [],
        "browser_meta": browser_meta,
        "provenance": {
            "worlds": "Atlas/Worlds/atlas_index.json",
            "research_atlas": "Atlas/Knowledge/research_atlas.json",
            "knowledge_base": "Atlas/Knowledge/knowledge_base.json",
            "research_director": "Atlas/Knowledge/research_director_history.json",
            "knowledge_integrity": "Atlas/Knowledge/knowledge_base_integrity.json",
            "predictions": "Atlas/Knowledge/prediction_database.json",
            "consensus": "Atlas/Knowledge/consensus_database.json",
        },
    }


def _int(value: Any, default: int = 0) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _float(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _clean(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _rule_id(value: Any) -> str:
    text = _clean(value)
    if text.isdigit():
        return f"{int(text):05d}"
    return text


def _relative_source(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.replace("\\", "/")
    for marker in ("Results/", "Atlas/", "Config/", "Observer/", "Analyzer_next/", "Universe_Search/"):
        index = text.find(marker)
        if index >= 0:
            return text[index:]
    if text.startswith("/home/") or text.startswith("/Users/"):
        return Path(text).name
    return text


def _root_path(root: Path, value: Any) -> Path | None:
    source = _relative_source(value)
    if not source:
        return None
    candidate = root / source
    return candidate if candidate.is_file() else None


def _confidence_rank(value: Any) -> int:
    key = _clean(value).lower().replace("_", "-")
    return {
        "very-high": 6,
        "high": 5,
        "medium-high": 4,
        "medium": 3,
        "low-medium": 2,
        "low": 1,
        "none": 0,
    }.get(key, 0)


def _timestamp(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    normalized = text.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return text
    if dt.tzinfo is None:
        # Canonical ARCHON files historically store many human/runtime timestamps
        # as naive local wall-clock values (for example ``2026-09-05 01:22:00``).
        # Treating those values as UTC shifts them into the future when Studio
        # later renders the instant in a positive-offset locale such as CEST.
        # ``astimezone()`` on a naive datetime interprets it in the host's local
        # timezone and applies the correct historical DST offset for that date.
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _sort_stamp(value: Any) -> float:
    text = _timestamp(value)
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _first(values: list[Any], fallback: str) -> str:
    for value in values:
        text = _clean(value)
        if text:
            return text
    return fallback


def _human_class(value: Any) -> str:
    return _clean(value, "Unclassified").replace("_", " ").replace("-", " ").title()


def _pick_highlights(discoveries: dict[str, Any], limit: int = 2) -> list[dict[str, Any]]:
    candidates = [item for item in discoveries.values() if isinstance(item, dict)]
    candidates.sort(
        key=lambda item: (
            _int(item.get("impact")),
            _confidence_rank(item.get("confidence")),
            _rule_id(item.get("rule_id") or item.get("rule")),
            _clean(item.get("id")),
        ),
        reverse=True,
    )
    highlights: list[dict[str, Any]] = []
    for item in candidates[:limit]:
        source = _relative_source(item.get("source_file"))
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        sources = [source] if source else []
        sources.extend(str(value) for value in evidence[:2] if isinstance(value, (str, int, float)))
        highlights.append(
            {
                "id": _clean(item.get("id"), "DISCOVERY"),
                "rule_id": _rule_id(item.get("rule_id") or item.get("rule")),
                "title": _clean(item.get("title"), "Research discovery"),
                "text": _clean(item.get("finding"), "No readable finding was recorded."),
                "why": _clean(item.get("why_it_matters"), "This finding is part of the current knowledge base."),
                "confidence": _clean(item.get("confidence"), "Unknown"),
                "impact": _int(item.get("impact")),
                "sources": sources,
            }
        )
    return highlights


def _priority_follow_up(predictions: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for item in predictions.values():
        if not isinstance(item, dict):
            continue
        status = _clean(item.get("status")).lower()
        if status in {"confirmed", "rejected", "failed", "closed"}:
            continue
        validation = item.get("validation") if isinstance(item.get("validation"), dict) else {}
        next_action = validation.get("next_action") or item.get("next_action")
        if not isinstance(next_action, str) or not next_action.strip():
            continue
        candidates.append(item)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            _int(item.get("priority")),
            _float(item.get("confidence_score")),
            _clean(item.get("id")),
        ),
        reverse=True,
    )
    item = candidates[0]
    validation = item.get("validation") if isinstance(item.get("validation"), dict) else {}
    return {
        "id": _clean(item.get("id")),
        "title": _first([item.get("based_on"), item.get("prediction")], "Priority follow-up"),
        "action": _clean(validation.get("next_action") or item.get("next_action"), "Review this prediction."),
        "priority": _int(item.get("priority")),
        "confidence": _clean(item.get("confidence"), "Unknown"),
        "status": _clean(item.get("status"), "Open"),
    }


def _copy_preview(
    root: Path,
    asset_dir: Path,
    public_prefix: str,
    world: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Copy an existing canonical preview to Studio public assets.

    Prefer a real GIF when it survives the release whitelist, otherwise use PNG.
    Returns (public_url, relative_canonical_source).
    """
    candidates = [world.get("preview_gif"), world.get("preview")]
    source_path: Path | None = None
    canonical_source: str | None = None
    for candidate in candidates:
        path = _root_path(root, candidate)
        if path is not None:
            source_path = path
            canonical_source = _relative_source(candidate)
            break
    if source_path is None:
        return None, None

    rule = _rule_id(world.get("rule_id")) or "unknown"
    key = _clean(world.get("key"), "world")[:16]
    suffix = source_path.suffix.lower() or ".png"
    filename = f"rule_{rule}_{key}{suffix}"
    asset_dir.mkdir(parents=True, exist_ok=True)
    target = asset_dir / filename
    shutil.copy2(source_path, target)
    return f"{public_prefix}/{filename}", canonical_source


def _preview_generation() -> str:
    # A unique asset generation makes every snapshot point only at a fully-built
    # preview directory.  It also cache-busts browsers after live Analyzer/Search
    # refreshes without mutating canonical Atlas assets.
    return f"g{time.time_ns():x}-{os.getpid():x}"


def _live_preview_generations(output_dir: Path) -> set[str]:
    """Return preview generations referenced by the currently published snapshot."""
    snapshot_path = output_dir / "snapshot.json"
    if not snapshot_path.is_file():
        return set()
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, str):
            return
        marker = "/studio/previews/"
        if marker not in value:
            return
        tail = value.split(marker, 1)[1]
        generation = tail.split("/", 1)[0]
        if generation.startswith("g"):
            found.add(generation)

    walk(payload)
    return found


def _cleanup_preview_generations(output_dir: Path, new_generation: str, keep_recent: int = 3) -> None:
    """Bound Studio-owned preview cache without deleting assets a live snapshot uses."""
    root = output_dir / "previews"
    if not root.is_dir():
        return
    protected = _live_preview_generations(output_dir) | {new_generation}
    generations = [path for path in root.iterdir() if path.is_dir() and path.name.startswith("g")]
    generations.sort(key=lambda path: path.stat().st_mtime_ns if path.exists() else 0, reverse=True)
    protected.update(path.name for path in generations[:keep_recent])
    for path in generations:
        if path.name in protected:
            continue
        shutil.rmtree(path, ignore_errors=True)


def _build_preview_index(
    root: Path,
    output_dir: Path,
    worlds: list[Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], str]:
    generation = _preview_generation()
    asset_dir = output_dir / "previews" / generation
    public_prefix = f"/studio/previews/{generation}"
    best_by_rule: dict[str, dict[str, Any]] = {}
    preview_worlds: list[dict[str, Any]] = []
    for raw in worlds:
        if not isinstance(raw, dict):
            continue
        rule = _rule_id(raw.get("rule_id"))
        if not rule:
            continue
        public_url, source = _copy_preview(root, asset_dir, public_prefix, raw)
        if not public_url:
            continue
        item = dict(raw)
        item["_preview_url"] = public_url
        item["_preview_source"] = source
        preview_worlds.append(item)
        previous = best_by_rule.get(rule)
        if previous is None or _float(item.get("score")) > _float(previous.get("score")):
            best_by_rule[rule] = item
    preview_worlds.sort(key=lambda item: (_float(item.get("score")), _rule_id(item.get("rule_id"))), reverse=True)
    _cleanup_preview_generations(output_dir, generation)
    return best_by_rule, preview_worlds, generation


def _preview_fields(rule: str, preview_index: dict[str, dict[str, Any]]) -> tuple[str | None, list[str]]:
    world = preview_index.get(rule)
    if not world:
        return None, []
    sources = []
    if world.get("_preview_source"):
        sources.append(str(world["_preview_source"]))
    return _clean(world.get("_preview_url")) or None, sources


def _feed_item(
    *,
    item_id: str,
    kind: str,
    author: str,
    timestamp: Any,
    title: str,
    text: str,
    why: str,
    label: str,
    tone: str,
    confidence: str,
    sources: list[Any],
    preview_url: str | None = None,
    rule_id: str = "",
    visual: int = 1,
    metadata: dict[str, Any] | None = None,
    sort_bias: float = 0.0,
) -> dict[str, Any]:
    clean_sources: list[str] = []
    for value in sources:
        source = _relative_source(value) if isinstance(value, str) else _clean(value)
        if source and source not in clean_sources:
            clean_sources.append(source)
    ts = _timestamp(timestamp)
    return {
        "id": item_id,
        "kind": kind,
        "author": author,
        "timestamp": ts,
        "title": title,
        "text": text,
        "why": why,
        "label": label,
        "tone": tone,
        "confidence": confidence,
        "visual": visual,
        "rule_id": rule_id,
        "preview_url": preview_url,
        "sources": clean_sources,
        "metadata": {str(k): _clean(v) for k, v in (metadata or {}).items() if v is not None and _clean(v)},
        "_sort": _sort_stamp(ts) + sort_bias,
    }


def _build_feed(
    *,
    worlds: list[Any],
    atlas: dict[str, Any],
    kb: dict[str, Any],
    director: dict[str, Any],
    preview_index: dict[str, dict[str, Any]],
    preview_worlds: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    discoveries = kb.get("discoveries") if isinstance(kb.get("discoveries"), dict) else {}
    mechanisms = kb.get("mechanisms") if isinstance(kb.get("mechanisms"), dict) else {}
    predictions = kb.get("predictions") if isinstance(kb.get("predictions"), dict) else {}
    experiments = atlas.get("experiments") if isinstance(atlas.get("experiments"), list) else []
    knowledge_time = kb.get("generated") or atlas.get("updated")
    feed: list[dict[str, Any]] = []

    # Research Director brief: one grounded summary of the latest canonical state.
    priority = _priority_follow_up(predictions)
    stage = _clean(director.get("stage"), "Awaiting Analyzer")
    trend = _clean(director.get("trend"), "WAITING FOR ANALYSIS").replace("_", " ").title()
    director_text = (
        f"ARCHON is in {stage}. The latest state is {trend.lower()}, with scientific maturity "
        f"{_float(director.get('maturity')):.3f}, research risk {_float(director.get('risk')):.3f}, "
        f"and evidence strength {_float(director.get('evidence_strength')):.3f}."
    )
    director_why = (
        f"Priority follow-up {priority['id']}: {priority['action']}" if priority else
        "No open priority follow-up was identified in the current prediction ledger."
    )
    feed.append(_feed_item(
        item_id="DIRECTOR-LATEST",
        kind="Director",
        author="Research Director",
        timestamp=director.get("generated_at"),
        title=f"Research state: {stage}",
        text=director_text,
        why=director_why,
        label="DIRECTOR BRIEF",
        tone="blue",
        confidence=f"Integrity {'verified' if director.get('integrity_ok') else 'not verified'}",
        sources=["Atlas/Knowledge/research_director_history.json", "Atlas/Knowledge/knowledge_base.json"],
        visual=2,
        metadata={
            "Trend": trend,
            "Planned experiments": _int(director.get("planned_experiments")),
            "Testing predictions": _int(director.get("testing_predictions")),
            "Consensus strength": f"{_float(director.get('consensus_strength')):.3f}",
        },
        sort_bias=0.9,
    ))

    # Predictions: all current canonical predictions fit comfortably in the feed.
    prediction_items = [item for item in predictions.values() if isinstance(item, dict)]
    prediction_items.sort(key=lambda item: (_sort_stamp(item.get("updated")), _int(item.get("priority")), _float(item.get("confidence_score"))), reverse=True)
    for index, item in enumerate(prediction_items[: FEED_LIMITS["Predictions"]]):
        validation = item.get("validation") if isinstance(item.get("validation"), dict) else {}
        status = _clean(item.get("validation_status") or item.get("status"), "Open")
        next_action = _clean(validation.get("next_action"))
        verdict = _clean(validation.get("verdict") or item.get("validation_verdict"))
        why = next_action or verdict or _clean(item.get("success_criteria"), "This prediction remains part of the active scientific ledger.")
        evidence = validation.get("evidence") if isinstance(validation.get("evidence"), list) else []
        feed.append(_feed_item(
            item_id=_clean(item.get("id"), f"PRED-{index+1}"),
            kind="Predictions",
            author="Research Director",
            timestamp=item.get("updated") or item.get("created") or knowledge_time,
            title=_clean(item.get("based_on"), "Scientific prediction"),
            text=_clean(item.get("prediction"), "No readable prediction text was recorded."),
            why=why,
            label=status.upper().replace("_", " "),
            tone="green" if status.lower() == "confirmed" else "amber" if "testing" in status.lower() or status.lower() == "open" else "rose",
            confidence=f"{_clean(item.get('confidence'), 'Unknown')} · {_float(item.get('confidence_score')):.2f}",
            sources=["Atlas/Knowledge/knowledge_base.json", *evidence[:2]],
            visual=4,
            metadata={
                "Priority": _int(item.get("priority")),
                "Status": status,
                "Validation verdict": verdict,
                "Success criteria": _clean(item.get("success_criteria")),
            },
            sort_bias=0.7,
        ))

    # Experiments: current representative observational records only, highest research value first.
    representative = [item for item in experiments if isinstance(item, dict) and item.get("is_representative") is True]
    representative.sort(
        key=lambda item: (
            _sort_stamp(item.get("date_added")),
            _float(item.get("research_value")),
            _float(item.get("emergence_score")),
            _float(item.get("validation_quality")),
        ),
        reverse=True,
    )
    seen_rules: set[str] = set()
    chosen_experiments: list[dict[str, Any]] = []
    for item in representative:
        rule = _rule_id(item.get("rule"))
        if rule in seen_rules:
            continue
        seen_rules.add(rule)
        chosen_experiments.append(item)
        if len(chosen_experiments) >= FEED_LIMITS["Experiments"]:
            break
    for index, item in enumerate(chosen_experiments):
        rule = _rule_id(item.get("rule"))
        preview_url, preview_sources = _preview_fields(rule, preview_index)
        classification = _human_class(item.get("family") or item.get("classification"))
        status = _clean(item.get("status"), "Unclear")
        evidence_channel = _clean(item.get("evidence_channel"), "canonical observational")
        text = (
            f"Rule {rule} is the current representative {classification} record. "
            f"Emergence score is {_float(item.get('emergence_score')):.3f} and validation quality "
            f"is {_float(item.get('validation_quality')):.3f}."
        )
        why = (
            f"This record is eligible for the {evidence_channel.replace('_', ' ')} channel and is the version used for current scientific claims."
            if item.get("observational_eligible") else
            "This record remains in the Atlas but is not currently eligible for observational claims."
        )
        file_sources = item.get("files") if isinstance(item.get("files"), dict) else {}
        feed.append(_feed_item(
            item_id=_clean(item.get("experiment_id"), f"EXP-{rule}-{index+1}"),
            kind="Experiments",
            author="Analyzer",
            timestamp=item.get("date_added") or atlas.get("updated"),
            title=f"Representative experiment for Rule {rule}",
            text=text,
            why=why,
            label="REPRESENTATIVE",
            tone="violet",
            confidence=f"{_clean(item.get('scientific_confidence'), 'Unknown')} · VAL {_float(item.get('validation_quality')):.3f}",
            sources=[
                "Atlas/Knowledge/research_atlas.json",
                file_sources.get("source_passport"),
                file_sources.get("discovery_report"),
                *preview_sources,
            ],
            preview_url=preview_url,
            rule_id=rule,
            visual=2,
            metadata={
                "Family": classification,
                "Scientific status": status,
                "Research value": f"{_float(item.get('research_value')):.3f}",
                "Evidence channel": evidence_channel,
            },
            sort_bias=0.5,
        ))

    # Discoveries: highest impact and confidence, deduplicated by id.
    discovery_items = [item for item in discoveries.values() if isinstance(item, dict)]
    discovery_items.sort(key=lambda item: (_int(item.get("impact")), _confidence_rank(item.get("confidence")), _rule_id(item.get("rule_id") or item.get("rule"))), reverse=True)
    for index, item in enumerate(discovery_items[: FEED_LIMITS["Evidence"]]):
        rule = _rule_id(item.get("rule_id") or item.get("rule"))
        preview_url, preview_sources = _preview_fields(rule, preview_index)
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        next_test = _clean(item.get("next_test"))
        feed.append(_feed_item(
            item_id=_clean(item.get("id"), f"DISC-{index+1}"),
            kind="Evidence",
            author="Analyzer",
            timestamp=knowledge_time,
            title=_clean(item.get("title"), "Research discovery"),
            text=_clean(item.get("finding"), "No readable finding was recorded."),
            why=_clean(item.get("why_it_matters"), next_test or "This finding contributes to the current knowledge base."),
            label="DISCOVERY",
            tone="green" if _confidence_rank(item.get("confidence")) >= 5 else "cyan",
            confidence=f"{_clean(item.get('confidence'), 'Unknown')} · impact {_int(item.get('impact'))}",
            sources=[item.get("source_file"), *evidence[:3], *preview_sources],
            preview_url=preview_url,
            rule_id=rule,
            visual=1,
            metadata={
                "Rule": rule,
                "Category": _clean(item.get("category")),
                "Next test": next_test,
            },
            sort_bias=0.3,
        ))

    # Mechanisms: prefer high-confidence, distinct mechanism titles so the feed is not repetitive.
    mechanism_items = [item for item in mechanisms.values() if isinstance(item, dict)]
    mechanism_items.sort(key=lambda item: (_confidence_rank(item.get("confidence")), _rule_id(item.get("rule_id")), _clean(item.get("id"))), reverse=True)
    chosen_mechanisms: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for item in mechanism_items:
        title_key = _clean(item.get("title")).lower()
        if title_key and title_key in seen_titles:
            continue
        if title_key:
            seen_titles.add(title_key)
        chosen_mechanisms.append(item)
        if len(chosen_mechanisms) >= FEED_LIMITS["Mechanisms"]:
            break
    for index, item in enumerate(chosen_mechanisms):
        rule = _rule_id(item.get("rule_id"))
        preview_url, preview_sources = _preview_fields(rule, preview_index)
        confidence = _clean(item.get("confidence"), "Unknown")
        feed.append(_feed_item(
            item_id=_clean(item.get("id"), f"MECH-{index+1}"),
            kind="Mechanisms",
            author="Analyzer",
            timestamp=knowledge_time,
            title=_clean(item.get("title"), "Candidate mechanism"),
            text=_clean(item.get("claim"), "No readable mechanism claim was recorded."),
            why=f"This is a {confidence.lower()} mechanism hypothesis linked to Rule {rule}; it remains a candidate explanation until stronger causal evidence is accumulated.",
            label="MECHANISM",
            tone="violet",
            confidence=confidence,
            sources=["Atlas/Knowledge/knowledge_base.json", *preview_sources],
            preview_url=preview_url,
            rule_id=rule,
            visual=3,
            metadata={"Rule": rule, "Confidence": confidence},
            sort_bias=0.2,
        ))

    # Worlds: real canonical retained-world previews where the release actually contains an asset.
    for index, world in enumerate(preview_worlds[: FEED_LIMITS["Worlds"]]):
        rule = _rule_id(world.get("rule_id"))
        class_name = _human_class(world.get("class"))
        score = _float(world.get("score"))
        memory = _float(world.get("memory"))
        recovery = _float(world.get("recovery"))
        info = _float(world.get("information_survival"))
        text = (
            f"Rule {rule} is retained in the World Atlas as {class_name} with score {score:.2f}. "
            f"Memory is {memory:.2f}, recovery {recovery:.3f}, and information survival {info:.3f}."
        )
        why = (
            "This is a real retained Atlas world with a release-safe visual preview, so the card can be inspected without reconstructing the original runtime run."
        )
        feed.append(_feed_item(
            item_id=f"WORLD-{rule}-{_clean(world.get('key'), 'world')[:8]}",
            kind="Worlds",
            author="Observer",
            timestamp=atlas.get("updated") or knowledge_time,
            title=f"{class_name} · Rule {rule}",
            text=text,
            why=why,
            label="ATLAS WORLD",
            tone="cyan",
            confidence=f"Atlas score {score:.2f}",
            sources=[world.get("folder"), world.get("latest_evidence"), world.get("_preview_source")],
            preview_url=_clean(world.get("_preview_url")) or None,
            rule_id=rule,
            visual=(index % 4) + 1,
            metadata={
                "Generation": _int(world.get("generation")),
                "Entities": _int(world.get("entities")),
                "Tracks": _int(world.get("tracks")),
                "Observer archetype": _clean(world.get("observer_archetype")),
                "World key": _clean(world.get("key")),
            },
            sort_bias=0.1,
        ))

    feed.sort(key=lambda item: (item.get("_sort", 0), item.get("id", "")), reverse=True)
    for item in feed:
        item.pop("_sort", None)

    source_counts = {
        "Worlds": {"available": len(worlds), "cards": sum(1 for item in feed if item["kind"] == "Worlds")},
        "Experiments": {"available": len(experiments), "cards": sum(1 for item in feed if item["kind"] == "Experiments")},
        "Evidence": {"available": len(discoveries), "cards": sum(1 for item in feed if item["kind"] == "Evidence")},
        "Mechanisms": {"available": len(mechanisms), "cards": sum(1 for item in feed if item["kind"] == "Mechanisms")},
        "Predictions": {"available": len(predictions), "cards": sum(1 for item in feed if item["kind"] == "Predictions")},
        "Director": {"available": 1, "cards": sum(1 for item in feed if item["kind"] == "Director")},
    }
    preview_count = sum(1 for item in feed if item.get("preview_url"))
    feed_meta = {
        "card_count": len(feed),
        "preview_card_count": preview_count,
        "source_family_count": len(source_counts),
        "sources": source_counts,
    }
    return feed, feed_meta



def _browser_source_list(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            nested = _browser_source_list(*value)
            for source in nested:
                if source not in result:
                    result.append(source)
            continue
        source = _relative_source(value) if isinstance(value, str) else None
        if source and source not in result:
            result.append(source)
    return result


def _build_browsers(
    *,
    root: Path,
    worlds: list[Any],
    atlas: dict[str, Any],
    kb: dict[str, Any],
    preview_index: dict[str, dict[str, Any]],
    preview_worlds: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    preview_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for item in preview_worlds:
        preview_lookup[(_rule_id(item.get("rule_id")), _clean(item.get("key")))] = item

    world_rows: list[dict[str, Any]] = []
    for raw in worlds:
        if not isinstance(raw, dict):
            continue
        rule = _rule_id(raw.get("rule_id"))
        key = _clean(raw.get("key"), "world")
        preview = preview_lookup.get((rule, key), {})
        preview_url = _clean(preview.get("_preview_url")) or None
        preview_source = preview.get("_preview_source")
        world_rows.append({
            "id": f"WORLD-{rule}-{key[:12]}",
            "key": key,
            "world_uid": _world_uid(root, raw),
            "rule_id": rule,
            "class": _human_class(raw.get("class")),
            "generation": _int(raw.get("generation")),
            "score": _float(raw.get("score")),
            "score_mode": _clean(raw.get("score_mode")),
            "source": _clean(raw.get("source")),
            "preview_url": preview_url,
            "metrics": {
                "active": _float(raw.get("active")),
                "edge": _float(raw.get("edge")),
                "life": _float(raw.get("life")),
                "flow": _float(raw.get("flow")),
                "rotation": _float(raw.get("rotation")),
                "memory": _float(raw.get("memory")),
                "recovery": _float(raw.get("recovery")),
                "region": _float(raw.get("region")),
                "crystal_order": _float(raw.get("crystal_order")),
                "defect_density": _float(raw.get("defect_density")),
                "quasi_particle_score": _float(raw.get("quasi_particle_score")),
                "information_survival": _float(raw.get("information_survival")),
                "identity_persistence": _float(raw.get("identity_persistence")),
                "post_collapse_structure": _float(raw.get("post_collapse_structure")),
            },
            "entities": _int(raw.get("entities")),
            "tracks": _int(raw.get("tracks")),
            "organism_lifetime": _int(raw.get("organism_lifetime")),
            "organism_peak_largest": _int(raw.get("organism_peak_largest")),
            "organism_survived_probe": bool(raw.get("organism_survived_probe", False)),
            "observer": {
                "id": _clean(raw.get("observer_id")),
                "archetype": _clean(raw.get("observer_archetype")),
                "note": _clean(raw.get("observer_note")),
            },
            "last_evaluation": {
                "run": _clean(raw.get("last_evaluated_run")),
                "generation": _int(raw.get("last_evaluated_generation")),
                "score": _float(raw.get("last_evaluated_score")),
                "count": _int(raw.get("evaluation_count")),
            },
            "sources": _browser_source_list(raw.get("folder"), raw.get("latest_evidence"), preview_source, "Atlas/Worlds/atlas_index.json"),
        })
    world_rows.sort(key=lambda item: (item["score"], item["rule_id"], item["key"]), reverse=True)

    experiments = atlas.get("experiments") if isinstance(atlas.get("experiments"), list) else []
    representative_rules = {
        _rule_id(item.get("rule"))
        for item in experiments
        if isinstance(item, dict) and item.get("is_representative") is True
    }
    world_count_by_rule: dict[str, int] = {}
    for item in world_rows:
        world_count_by_rule[item["rule_id"]] = world_count_by_rule.get(item["rule_id"], 0) + 1

    rules = kb.get("rules") if isinstance(kb.get("rules"), dict) else {}
    rule_rows: list[dict[str, Any]] = []
    for key, raw in rules.items():
        if not isinstance(raw, dict):
            continue
        rule = _rule_id(raw.get("rule_id") or key)
        record = raw.get("atlas") if isinstance(raw.get("atlas"), dict) else {}
        passport = raw.get("passport") if isinstance(raw.get("passport"), dict) else {}
        preview = preview_index.get(rule, {})
        discovery_ids = [str(v) for v in raw.get("discovery_ids", []) if isinstance(v, (str, int))]
        mechanism_ids = [str(v) for v in raw.get("mechanism_ids", []) if isinstance(v, (str, int))]
        principle_ids = [str(v) for v in raw.get("principle_ids", []) if isinstance(v, (str, int))]
        prediction_ids = [str(v) for v in raw.get("prediction_ids", []) if isinstance(v, (str, int))]
        validation_ids = [str(v) for v in raw.get("validation_ids", []) if isinstance(v, (str, int))]
        family = _clean(raw.get("family") or record.get("family"), "Unclassified")
        classification = _human_class(record.get("classification") or passport.get("classification"))
        rule_rows.append({
            "rule_id": rule,
            "title": f"Rule {rule} · {family}",
            "status": _clean(raw.get("status") or record.get("status"), "Unclear"),
            "family": family,
            "classification": classification,
            "tags": [str(v) for v in raw.get("tags", []) if isinstance(v, (str, int))],
            "scientific_eligible": rule in representative_rules,
            "preview_url": _clean(preview.get("_preview_url")) or None,
            "world_count": world_count_by_rule.get(rule, 0),
            "best_world_key": _clean(preview.get("key")),
            "lifetime": _int(record.get("lifetime"), _int(passport.get("lifetime"))),
            "research_value": _float(record.get("research_value")),
            "novelty_score": _float(record.get("novelty_score")),
            "emergence_score": _float(record.get("emergence_score")),
            "emergence_confidence": _clean(record.get("emergence_confidence"), "NONE"),
            "validation_quality": _float(record.get("validation_quality")),
            "validation_grade": _clean(record.get("validation_grade"), "UNKNOWN"),
            "validation_repeatability": _float(record.get("validation_repeatability")),
            "layer_stack_score": _float(record.get("layer_stack_score")),
            "civilization_stage": _clean(record.get("civilization_stage"), "NONE"),
            "civilization_score": _float(record.get("civilization_score")),
            "knowledge_score": _float(record.get("knowledge_score")),
            "knowledge_axis": _clean(record.get("knowledge_axis")),
            "feedback_regime": _clean(record.get("feedback_regime")),
            "feedback_score": _float(record.get("feedback_score")),
            "experiment_count": _int(record.get("experiment_count")),
            "replication_count": _int(record.get("replication_count")),
            "discovery_ids": discovery_ids,
            "mechanism_ids": mechanism_ids,
            "principle_ids": principle_ids,
            "prediction_ids": prediction_ids,
            "validation_ids": validation_ids,
            "mechanism_scores": {
                str(k): _float(v) for k, v in (raw.get("mechanism_scores") or {}).items()
                if isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)
            },
            "sources": _browser_source_list(
                "Atlas/Knowledge/knowledge_base.json",
                "Atlas/Knowledge/research_atlas.json",
                record.get("source_profile"),
                (record.get("files") or {}).get("source_passport") if isinstance(record.get("files"), dict) else None,
                preview.get("_preview_source"),
            ),
        })
    rule_rows.sort(key=lambda item: (item["scientific_eligible"], item["research_value"], item["emergence_score"], item["rule_id"]), reverse=True)

    browser_meta = {
        "world_count": len(world_rows),
        "world_preview_count": sum(1 for item in world_rows if item["preview_url"]),
        "rule_count": len(rule_rows),
        "scientific_rule_count": sum(1 for item in rule_rows if item["scientific_eligible"]),
        "rules_with_worlds": sum(1 for item in rule_rows if item["world_count"] > 0),
    }
    return world_rows, rule_rows, browser_meta


def _cohort_stats(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    return {
        "run_count": _int(raw.get("run_count")),
        "unique_rule_count": _int(raw.get("unique_rule_count")),
        "canonical_rule_count": _int(raw.get("canonical_rule_count")),
        "seed_observed_run_count": _int(raw.get("seed_observed_run_count")),
        "seed_coverage": _float(raw.get("seed_coverage")),
        "behavioural_family_count": _int(raw.get("behavioural_family_count")),
        "representative_profile_count": _int(raw.get("representative_profile_count")),
    }


def _build_experiment_evidence_browsers(
    *,
    atlas: dict[str, Any],
    kb: dict[str, Any],
    preview_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rules = kb.get("rules") if isinstance(kb.get("rules"), dict) else {}
    experiments = atlas.get("experiments") if isinstance(atlas.get("experiments"), list) else []
    experiment_rows: list[dict[str, Any]] = []

    for raw in experiments:
        if not isinstance(raw, dict):
            continue
        rule = _rule_id(raw.get("rule"))
        rule_record = rules.get(rule) if isinstance(rules.get(rule), dict) else {}
        preview = preview_index.get(rule, {})
        files = raw.get("files") if isinstance(raw.get("files"), dict) else {}
        similar = raw.get("similar_to") if isinstance(raw.get("similar_to"), list) else []
        experiment_rows.append({
            "id": _clean(raw.get("experiment_id"), f"EXP-{rule}"),
            "rule_id": rule,
            "representative": bool(raw.get("is_representative", False)),
            "scientific_observational": bool(raw.get("is_scientific_observational", False)),
            "observational_eligible": bool(raw.get("observational_eligible", False)),
            "evidence_channel": _clean(raw.get("evidence_channel"), "unclassified"),
            "evidence_exclusion_reason": _clean(raw.get("evidence_exclusion_reason")),
            "telemetry_run_status": _clean(raw.get("telemetry_run_status"), _clean(raw.get("status"), "unknown")),
            "date_added": _timestamp(raw.get("date_added")),
            "family": _clean(raw.get("family"), "Unclassified"),
            "classification": _human_class(raw.get("classification")),
            "status": _clean(raw.get("status"), "Unclear"),
            "lifetime": _int(raw.get("lifetime")),
            "research_value": _float(raw.get("research_value")),
            "novelty_score": _float(raw.get("novelty_score")),
            "emergence_score": _float(raw.get("emergence_score")),
            "emergence_confidence": _clean(raw.get("emergence_confidence"), "NONE"),
            "emergence_evidence_count": _int(raw.get("emergence_evidence_count")),
            "validation_quality": _float(raw.get("validation_quality")),
            "validation_grade": _clean(raw.get("validation_grade"), "UNKNOWN"),
            "validation_repeatability": _float(raw.get("validation_repeatability")),
            "validation_false_positive_risk": _float(raw.get("validation_false_positive_risk")),
            "validation_false_negative_risk": _float(raw.get("validation_false_negative_risk")),
            "validation_noise_sensitivity": _float(raw.get("validation_noise_sensitivity")),
            "validation_warning": _clean(raw.get("validation_warning")),
            "experiment_count": _int(raw.get("experiment_count")),
            "replication_count": _int(raw.get("replication_count")),
            "discovery_count": _int(raw.get("discovery_count")),
            "max_impact": _int(raw.get("max_impact")),
            "hypotheses": _int(raw.get("hypotheses")),
            "high_priority_questions": _int(raw.get("high_priority_questions")),
            "next_actions": _int(raw.get("next_actions")),
            "tags": [str(v) for v in raw.get("tags", []) if isinstance(v, (str, int))],
            "key_reasons": [str(v) for v in raw.get("key_reasons", []) if isinstance(v, (str, int))],
            "warnings": [str(v) for v in raw.get("warnings", []) if isinstance(v, (str, int))],
            "preview_url": _clean(preview.get("_preview_url")) or None,
            "validation_ids": [str(v) for v in rule_record.get("validation_ids", []) if isinstance(v, (str, int))],
            "prediction_ids": [str(v) for v in rule_record.get("prediction_ids", []) if isinstance(v, (str, int))],
            "discovery_ids": [str(v) for v in rule_record.get("discovery_ids", []) if isinstance(v, (str, int))],
            "mechanism_ids": [str(v) for v in rule_record.get("mechanism_ids", []) if isinstance(v, (str, int))],
            "similar_to": [
                {
                    "rule_id": _rule_id(item.get("rule")),
                    "experiment_id": _clean(item.get("experiment_id")),
                    "similarity": _float(item.get("similarity")),
                    "family": _clean(item.get("family")),
                }
                for item in similar[:5] if isinstance(item, dict)
            ],
            "sources": _browser_source_list(
                "Atlas/Knowledge/research_atlas.json",
                raw.get("source_profile"),
                files.get("source_passport"),
                files.get("observer_profile"),
                files.get("discovery_report"),
                preview.get("_preview_source"),
            ),
        })

    experiment_rows.sort(
        key=lambda item: (
            _sort_stamp(item.get("date_added")),
            item["representative"],
            item["research_value"],
            item["validation_quality"],
            item["id"],
        ),
        reverse=True,
    )

    validations = kb.get("validations") if isinstance(kb.get("validations"), dict) else {}
    predictions = kb.get("predictions") if isinstance(kb.get("predictions"), dict) else {}
    validation_rules: dict[str, list[str]] = {}
    for rule_id, rule_record in rules.items():
        if not isinstance(rule_record, dict):
            continue
        for validation_id in rule_record.get("validation_ids", []):
            if not isinstance(validation_id, (str, int)):
                continue
            validation_rules.setdefault(str(validation_id), []).append(_rule_id(rule_id))

    evidence_rows: list[dict[str, Any]] = []
    for key, raw in validations.items():
        if not isinstance(raw, dict):
            continue
        evidence_id = _clean(raw.get("id") or key, str(key))
        prediction = predictions.get(evidence_id) if isinstance(predictions.get(evidence_id), dict) else {}
        principle_ids = [str(v) for v in prediction.get("principle_ids", []) if isinstance(v, (str, int))]
        if not principle_ids:
            based_on = _clean(raw.get("based_on"))
            for token in based_on.replace(":", " ").split():
                if token.startswith("GP-"):
                    principle_ids.append(token)
                    break
        evidence_values = [str(v) for v in raw.get("evidence", []) if isinstance(v, (str, int, float))]
        evidence_rows.append({
            "id": evidence_id,
            "based_on": _clean(raw.get("based_on") or prediction.get("based_on"), "Validation evidence"),
            "prediction": _clean(raw.get("prediction") or prediction.get("prediction")),
            "status_before": _clean(raw.get("status_before")),
            "status_after": _clean(raw.get("status_after") or prediction.get("status"), "Unknown"),
            "verdict": _clean(raw.get("verdict"), "No verdict recorded"),
            "support_count": _int(raw.get("support_count"), _int(raw.get("support"))),
            "negative_cohort_count": _int(raw.get("negative_cohort_count")),
            "claim_counterexample_count": _int(raw.get("claim_counterexample_count")),
            "failed_prediction_count": _int(raw.get("failed_prediction_count")),
            "support": _int(raw.get("support")),
            "counterexamples": _int(raw.get("counterexamples")),
            "evidence": evidence_values,
            "next_action": _clean(raw.get("next_action")),
            "confidence": _clean(prediction.get("confidence"), "Unknown"),
            "confidence_score": _float(prediction.get("confidence_score")),
            "priority": _int(prediction.get("priority")),
            "updated": _timestamp(prediction.get("updated") or kb.get("generated")),
            "related_rule_ids": sorted(set(validation_rules.get(evidence_id, []))),
            "principle_ids": principle_ids,
            "stats": {
                "support": _cohort_stats(raw.get("support_statistics")),
                "negative": _cohort_stats(raw.get("negative_cohort_statistics")),
                "counterexample": _cohort_stats(raw.get("claim_counterexample_statistics")),
                "failed": _cohort_stats(raw.get("failed_prediction_statistics")),
            },
            "sources": _browser_source_list(
                "Atlas/Knowledge/knowledge_base.json",
                "Atlas/Knowledge/prediction_database.json",
                "Atlas/Knowledge/consensus_database.json",
            ),
        })
    evidence_rows.sort(
        key=lambda item: (_sort_stamp(item.get("updated")), item["priority"], item["support_count"], item["id"]),
        reverse=True,
    )

    meta = {
        "experiment_count": len(experiment_rows),
        "representative_experiment_count": sum(1 for item in experiment_rows if item["representative"]),
        "observational_experiment_count": sum(1 for item in experiment_rows if item["scientific_observational"]),
        "evidence_count": len(evidence_rows),
        "evidence_with_support": sum(1 for item in evidence_rows if item["support_count"] > 0),
    }
    return experiment_rows, evidence_rows, meta


def _build_mechanism_prediction_browsers(
    *,
    atlas: dict[str, Any],
    kb: dict[str, Any],
    preview_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Normalize Knowledge Base mechanisms and prediction-ledger objects for Studio."""

    rules = kb.get("rules") if isinstance(kb.get("rules"), dict) else {}
    mechanisms = kb.get("mechanisms") if isinstance(kb.get("mechanisms"), dict) else {}
    predictions = kb.get("predictions") if isinstance(kb.get("predictions"), dict) else {}
    experiments = atlas.get("experiments") if isinstance(atlas.get("experiments"), list) else []

    scientific_rules = {
        _rule_id(item.get("rule"))
        for item in experiments
        if isinstance(item, dict) and item.get("is_representative") is True
    }

    experiment_ids_by_rule: dict[str, list[tuple[float, str]]] = {}
    for raw in experiments:
        if not isinstance(raw, dict):
            continue
        rule = _rule_id(raw.get("rule"))
        experiment_id = _clean(raw.get("experiment_id"))
        if not rule or not experiment_id:
            continue
        experiment_ids_by_rule.setdefault(rule, []).append((_sort_stamp(raw.get("date_added")), experiment_id))
    for rows in experiment_ids_by_rule.values():
        rows.sort(reverse=True)

    mechanism_rows: list[dict[str, Any]] = []
    for key, raw in mechanisms.items():
        if not isinstance(raw, dict):
            continue
        mechanism_id = _clean(raw.get("id") or key, str(key))
        rule = _rule_id(raw.get("rule_id"))
        rule_record = rules.get(rule) if isinstance(rules.get(rule), dict) else {}
        atlas_record = rule_record.get("atlas") if isinstance(rule_record.get("atlas"), dict) else {}
        preview = preview_index.get(rule, {})
        experiment_ids = [value for _, value in experiment_ids_by_rule.get(rule, [])[:12]]
        mechanism_rows.append({
            "id": mechanism_id,
            "local_id": _clean(raw.get("local_id")),
            "rule_id": rule,
            "title": _clean(raw.get("title"), "Candidate mechanism"),
            "claim": _clean(raw.get("claim"), "No readable mechanism claim was recorded."),
            "confidence": _clean(raw.get("confidence"), "Unknown"),
            "confidence_rank": _confidence_rank(raw.get("confidence")),
            "family": _clean(rule_record.get("family") or atlas_record.get("family"), "Unclassified"),
            "classification": _human_class(atlas_record.get("classification")),
            "scientific_eligible": rule in scientific_rules,
            "preview_url": _clean(preview.get("_preview_url")) or None,
            "research_value": _float(atlas_record.get("research_value")),
            "emergence_score": _float(atlas_record.get("emergence_score")),
            "validation_quality": _float(atlas_record.get("validation_quality")),
            "discovery_ids": [str(v) for v in rule_record.get("discovery_ids", []) if isinstance(v, (str, int))],
            "principle_ids": [str(v) for v in rule_record.get("principle_ids", []) if isinstance(v, (str, int))],
            "prediction_ids": [str(v) for v in rule_record.get("prediction_ids", []) if isinstance(v, (str, int))],
            "validation_ids": [str(v) for v in rule_record.get("validation_ids", []) if isinstance(v, (str, int))],
            "experiment_ids": experiment_ids,
            "sources": _browser_source_list(
                "Atlas/Knowledge/knowledge_base.json",
                "Atlas/Knowledge/research_atlas.json",
                preview.get("_preview_source"),
            ),
        })
    mechanism_rows.sort(
        key=lambda item: (
            item["confidence_rank"],
            item["scientific_eligible"],
            item["validation_quality"],
            item["research_value"],
            item["id"],
        ),
        reverse=True,
    )

    prediction_rules: dict[str, set[str]] = {}
    for rule_key, raw in rules.items():
        if not isinstance(raw, dict):
            continue
        rule = _rule_id(raw.get("rule_id") or rule_key)
        for prediction_id in raw.get("prediction_ids", []):
            if isinstance(prediction_id, (str, int)):
                prediction_rules.setdefault(str(prediction_id), set()).add(rule)

    prediction_rows: list[dict[str, Any]] = []
    for key, raw in predictions.items():
        if not isinstance(raw, dict):
            continue
        prediction_id = _clean(raw.get("id") or key, str(key))
        validation = raw.get("validation") if isinstance(raw.get("validation"), dict) else {}
        target_rules = {_rule_id(v) for v in raw.get("target_rules", []) if isinstance(v, (str, int)) and _rule_id(v)}
        related_rules = sorted(target_rules | prediction_rules.get(prediction_id, set()))
        related_mechanisms: list[str] = []
        related_experiments: list[tuple[float, str]] = []
        for rule in related_rules:
            rule_record = rules.get(rule) if isinstance(rules.get(rule), dict) else {}
            related_mechanisms.extend(str(v) for v in rule_record.get("mechanism_ids", []) if isinstance(v, (str, int)))
            related_experiments.extend(experiment_ids_by_rule.get(rule, [])[:3])
        related_experiments.sort(reverse=True)
        history = raw.get("history") if isinstance(raw.get("history"), list) else []
        history_rows = []
        for event in history[-8:]:
            if not isinstance(event, dict):
                continue
            history_rows.append({
                "timestamp": _timestamp(event.get("timestamp")),
                "event": _clean(event.get("event"), "update"),
                "status": _clean(event.get("to_status") or event.get("status") or event.get("from_status")),
                "verdict": _clean(event.get("verdict")),
                "confidence": _clean(event.get("confidence")),
            })
        prediction_rows.append({
            "id": prediction_id,
            "based_on": _clean(raw.get("based_on"), "Scientific prediction"),
            "category": _human_class(raw.get("category")),
            "prediction": _clean(raw.get("prediction"), "No readable prediction text was recorded."),
            "expected_observation": _clean(raw.get("expected_observation")),
            "test": _clean(raw.get("test")),
            "success_criteria": _clean(raw.get("success_criteria")),
            "priority": _int(raw.get("priority")),
            "confidence": _clean(raw.get("confidence"), "Unknown"),
            "confidence_score": _float(raw.get("confidence_score")),
            "status": _clean(raw.get("status"), "Open"),
            "created": _timestamp(raw.get("created")),
            "updated": _timestamp(raw.get("updated")),
            "last_validated": _timestamp(raw.get("last_validated")),
            "validation_id": _clean(raw.get("validation_id"), prediction_id),
            "validation_status": _clean(raw.get("validation_status") or raw.get("status"), "Unknown"),
            "validation_verdict": _clean(raw.get("validation_verdict") or validation.get("verdict"), "Not yet validated"),
            "support": _int(validation.get("support")),
            "counterexamples": _int(validation.get("counterexamples")),
            "evidence": [str(v) for v in validation.get("evidence", []) if isinstance(v, (str, int, float))],
            "next_action": _clean(validation.get("next_action") or raw.get("next_action")),
            "principle_ids": [str(v) for v in raw.get("principle_ids", []) if isinstance(v, (str, int))],
            "target_rule_ids": sorted(target_rules),
            "related_rule_ids": related_rules,
            "related_mechanism_ids": sorted(set(related_mechanisms)),
            "related_experiment_ids": [value for _, value in related_experiments[:24]],
            "history": history_rows,
            "sources": _browser_source_list(
                "Atlas/Knowledge/prediction_database.json",
                "Atlas/Knowledge/knowledge_base.json",
                "Atlas/Knowledge/consensus_database.json",
                "Atlas/Knowledge/research_atlas.json",
            ),
        })

    def _prediction_state_rank(item: dict[str, Any]) -> int:
        status = _clean(item.get("status")).lower()
        if status in {"open", "testing", "pending", "needs_revision"}:
            return 3
        if status in {"confirmed", "supported"}:
            return 2
        if status in {"rejected", "failed"}:
            return 1
        return 0

    prediction_rows.sort(
        key=lambda item: (
            _prediction_state_rank(item),
            item["priority"],
            _sort_stamp(item.get("updated")),
            item["confidence_score"],
            item["id"],
        ),
        reverse=True,
    )

    meta = {
        "mechanism_count": len(mechanism_rows),
        "medium_plus_mechanism_count": sum(1 for item in mechanism_rows if item["confidence_rank"] >= 3),
        "scientific_mechanism_count": sum(1 for item in mechanism_rows if item["scientific_eligible"]),
        "prediction_count": len(prediction_rows),
        "open_prediction_count": sum(1 for item in prediction_rows if item["status"].lower() not in {"confirmed", "rejected", "failed", "closed"}),
        "confirmed_prediction_count": sum(1 for item in prediction_rows if item["status"].lower() == "confirmed"),
    }
    return mechanism_rows, prediction_rows, meta

def build_snapshot(root: Path, output_dir: Path) -> dict[str, Any]:
    worlds_path = root / "Atlas/Worlds/atlas_index.json"
    atlas_path = root / "Atlas/Knowledge/research_atlas.json"
    kb_path = root / "Atlas/Knowledge/knowledge_base.json"
    director_path = root / "Atlas/Knowledge/research_director_history.json"
    integrity_path = root / "Atlas/Knowledge/knowledge_base_integrity.json"

    worlds = _read_json_optional(worlds_path, list, [])
    if not worlds:
        return _empty_snapshot(root)

    # A retained world can exist before Analyzer has produced every Knowledge
    # source.  Missing downstream files therefore degrade to an honest partial
    # snapshot instead of preventing Studio from starting.
    atlas = _read_json_optional(atlas_path, dict, {})
    kb = _read_json_optional(kb_path, dict, {})
    director_history = _read_json_optional(director_path, list, [])
    integrity = _read_json_optional(integrity_path, dict, {})

    director = director_history[-1] if director_history and isinstance(director_history[-1], dict) else {}

    summary = kb.get("summary") if isinstance(kb.get("summary"), dict) else {}
    scientific_view = atlas.get("scientific_view") if isinstance(atlas.get("scientific_view"), dict) else {}
    predictions = kb.get("predictions") if isinstance(kb.get("predictions"), dict) else {}
    discoveries = kb.get("discoveries") if isinstance(kb.get("discoveries"), dict) else {}
    mechanisms = kb.get("mechanisms") if isinstance(kb.get("mechanisms"), dict) else {}
    principles = kb.get("principles") if isinstance(kb.get("principles"), dict) else {}
    confirmed_predictions = _int(director.get("confirmed_predictions"))
    testing_predictions = _int(director.get("testing_predictions"))
    representative_rules = _int(scientific_view.get("unique_rule_count"), _int(director.get("rules")))
    total_rules = _int(summary.get("rules"), _int(atlas.get("unique_rule_count")))
    total_experiments = _int(atlas.get("record_count"), len(atlas.get("experiments", [])) if isinstance(atlas.get("experiments"), list) else 0)
    representative_experiments = _int(atlas.get("representative_record_count"), representative_rules)
    discovery_count = _int(summary.get("discoveries"), len(discoveries))
    mechanism_count = _int(summary.get("mechanisms"), len(mechanisms))
    prediction_count = _int(summary.get("predictions"), len(predictions))
    principle_count = _int(summary.get("principles"), len(principles))

    maturity = max(0.0, min(1.0, _float(director.get("maturity"))))
    risk = max(0.0, min(1.0, _float(director.get("risk"))))
    maturity_delta = _float(director.get("maturity_delta"))
    risk_delta = _float(director.get("risk_delta"))
    trend = _clean(director.get("trend"), "WAITING FOR ANALYSIS").replace("_", " ").title()
    stage = _clean(director.get("stage"), "Awaiting Analyzer")
    priority = _priority_follow_up(predictions)

    summary_text = (
        f"Research is in {stage}. The latest Director state is {trend.lower()}; "
        f"maturity changed by {maturity_delta:+.3f} and risk by {risk_delta:+.3f}. "
        f"{representative_rules} representative rules are currently eligible for scientific claims, "
        f"with {confirmed_predictions} predictions confirmed and {testing_predictions} testing."
        if director
        else f"{len(worlds)} retained worlds are available. Research Director state has not been generated yet; run Analyzer when the search cohort is ready."
    )

    live_results_available = _has_scientific_results(root)

    # Build previews into an immutable generation.  The published snapshot is
    # swapped only after this generation is complete, so live browsers never
    # observe a snapshot whose image directory is being deleted/rebuilt.
    preview_index, preview_worlds, preview_generation = _build_preview_index(root, output_dir, worlds)
    feed, feed_meta = _build_feed(
        worlds=worlds,
        atlas=atlas,
        kb=kb,
        director=director,
        preview_index=preview_index,
        preview_worlds=preview_worlds,
    )
    world_browser, rule_browser, browser_meta = _build_browsers(
        root=root,
        worlds=worlds,
        atlas=atlas,
        kb=kb,
        preview_index=preview_index,
        preview_worlds=preview_worlds,
    )
    experiment_browser, evidence_browser, research_browser_meta = _build_experiment_evidence_browsers(
        atlas=atlas,
        kb=kb,
        preview_index=preview_index,
    )
    browser_meta.update(research_browser_meta)
    mechanism_browser, prediction_browser, mechanism_prediction_meta = _build_mechanism_prediction_browsers(
        atlas=atlas,
        kb=kb,
        preview_index=preview_index,
    )
    browser_meta.update(mechanism_prediction_meta)

    snapshot = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "canonical_atlas_snapshot",
        "source_state": {
            "atlas_updated": atlas.get("updated"),
            "knowledge_generated": kb.get("generated"),
            "director_generated_at": director.get("generated_at"),
            "live_results_available": live_results_available,
            "knowledge_integrity_ok": bool(integrity.get("ok", False)),
            "research_empty": False,
            "preview_generation": preview_generation,
        },
        "metrics": [
            {"key": "worlds", "label": "Worlds", "value": len(worlds), "detail": "Atlas world records"},
            {"key": "rules", "label": "Rules", "value": total_rules, "detail": f"{representative_rules} in scientific view"},
            {"key": "experiments", "label": "Experiments", "value": total_experiments, "detail": f"{representative_experiments} representative"},
            {"key": "discoveries", "label": "Discoveries", "value": discovery_count, "detail": f"{_int(summary.get('rules_with_discoveries'))} rules linked"},
            {"key": "mechanisms", "label": "Mechanisms", "value": mechanism_count, "detail": f"{_int(summary.get('rules_with_mechanisms'))} rules linked"},
            {"key": "predictions", "label": "Predictions", "value": prediction_count, "detail": f"{confirmed_predictions} confirmed · {testing_predictions} testing"},
        ],
        "research_map": {
            "worlds": len(worlds),
            "rules": total_rules,
            "mechanisms": mechanism_count,
            "principles": principle_count,
            "predictions": prediction_count,
        },
        "director": {
            "generated_at": director.get("generated_at"),
            "stage": stage,
            "trend": trend,
            "maturity": maturity,
            "risk": risk,
            "maturity_delta": maturity_delta,
            "risk_delta": risk_delta,
            "evidence_strength": _float(director.get("evidence_strength")),
            "consensus_strength": _float(director.get("consensus_strength")),
            "planned_experiments": _int(director.get("planned_experiments")),
            "confirmed_predictions": confirmed_predictions,
            "testing_predictions": testing_predictions,
            "integrity_ok": bool(director.get("integrity_ok", False)),
            "summary": summary_text,
            "priority_follow_up": priority,
            "sources": [
                "Atlas/Knowledge/research_director_history.json",
                "Atlas/Knowledge/knowledge_base.json",
                "Atlas/Knowledge/research_atlas.json",
            ],
        },
        "highlights": _pick_highlights(discoveries),
        "feed": feed,
        "feed_meta": feed_meta,
        "worlds": world_browser,
        "rules": rule_browser,
        "experiments": experiment_browser,
        "evidence": evidence_browser,
        "mechanisms": mechanism_browser,
        "predictions": prediction_browser,
        "browser_meta": browser_meta,
        "provenance": {
            "worlds": "Atlas/Worlds/atlas_index.json",
            "research_atlas": "Atlas/Knowledge/research_atlas.json",
            "knowledge_base": "Atlas/Knowledge/knowledge_base.json",
            "research_director": "Atlas/Knowledge/research_director_history.json",
            "knowledge_integrity": "Atlas/Knowledge/knowledge_base_integrity.json",
            "predictions": "Atlas/Knowledge/prediction_database.json",
            "consensus": "Atlas/Knowledge/consensus_database.json",
        },
    }
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the ARCHON Studio canonical snapshot and Research Feed.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output.resolve() if args.output else root / "archon-studio/public/studio/snapshot.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = build_snapshot(root, output.parent)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=" * 78)
    print("Project ARCHON Studio Snapshot Builder")
    print("=" * 78)
    print(f"Schema:        {snapshot['schema']}")
    print(f"Mode:          {snapshot['mode']}")
    print(f"Output:        {output.relative_to(root) if output.is_relative_to(root) else output}")
    print(f"Live Results:  {'YES' if snapshot['source_state']['live_results_available'] else 'NO'}")
    print("Metrics:       " + ", ".join(f"{m['label']}={m['value']}" for m in snapshot["metrics"]))
    print(f"Feed:          {snapshot['feed_meta']['card_count']} canonical cards / {snapshot['feed_meta']['preview_card_count']} with real previews")
    print(f"Browsers:      Worlds={snapshot['browser_meta']['world_count']} / Rules={snapshot['browser_meta']['rule_count']} / Experiments={snapshot['browser_meta']['experiment_count']} / Evidence={snapshot['browser_meta']['evidence_count']} / Mechanisms={snapshot['browser_meta']['mechanism_count']} / Predictions={snapshot['browser_meta']['prediction_count']}")
    print(f"Director:      {snapshot['director']['stage']} / maturity={snapshot['director']['maturity']:.3f} / risk={snapshot['director']['risk']:.3f}")
    print("Status:        PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
