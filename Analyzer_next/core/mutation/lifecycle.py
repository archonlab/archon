"""Observer passport discovery and lifecycle contract resolution."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from .contracts import LifecycleReconciler
from .utils import normalize_rule_id, read_json

_PASSPORT_IDENTITY_CACHE: dict[str, tuple[int, int, dict[str, Any]]] = {}

def _samples_run_id(samples_path: Path) -> str:
    name = samples_path.name
    if name.endswith("_samples.csv"):
        return name[: -len("_samples.csv")]
    return samples_path.stem


def _passport_identity(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
        cache_key = str(path.resolve())
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = _PASSPORT_IDENTITY_CACHE.get(cache_key)
        if cached and cached[:2] == signature:
            return dict(cached[2])
    except OSError:
        cache_key = str(path)
        signature = (0, 0)

    payload = read_json(path, {})
    if not isinstance(payload, dict):
        payload = {}
    state = (
        payload.get("observer_state")
        if isinstance(payload.get("observer_state"), dict)
        else {}
    )
    life = payload.get("life") if isinstance(payload.get("life"), dict) else {}
    tick = state.get("tick")
    if tick is None:
        tick = life.get("final_tick_observed")
    try:
        tick = int(float(tick)) if tick is not None else None
    except (TypeError, ValueError):
        tick = None
    identity = {
        "path": path,
        "run_id": str(
            state.get("run_id") or payload.get("run_id") or ""
        ).strip(),
        "rule_id": normalize_rule_id(
            payload.get("rule_id") or state.get("world_id")
        ),
        "source": str(payload.get("source") or "").strip(),
        "tick": tick,
        "has_lifecycle_summary": isinstance(
            payload.get("lifecycle_summary"), dict
        ),
        "has_observer_state": bool(state),
    }
    _PASSPORT_IDENTITY_CACHE[cache_key] = (
        signature[0],
        signature[1],
        dict(identity),
    )
    return identity


def _sample_final_tick(samples_path: Path) -> int | None:
    try:
        last_tick: int | None = None
        with samples_path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        ) as fh:
            for row in csv.DictReader(fh):
                try:
                    last_tick = int(float(row.get("tick", "")))
                except (TypeError, ValueError):
                    continue
        return last_tick
    except OSError:
        return None


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    unique: dict[str, Path] = {}
    for path in paths:
        try:
            if path.is_file():
                unique[str(path.resolve())] = path.resolve()
        except OSError:
            continue
    return sorted(unique.values(), key=str)


def _passport_candidates(
    samples_path: Path,
    search_roots: Iterable[Path],
    explicit_paths: Iterable[Path],
) -> list[Path]:
    prefix = _samples_run_id(samples_path)
    paths: list[Path] = [
        samples_path.with_name(f"{prefix}_passport.json"),
        *explicit_paths,
    ]
    for root in search_roots:
        try:
            root = Path(root)
            if root.is_file():
                paths.append(root)
            elif root.is_dir():
                paths.extend(root.rglob("*passport*.json"))
        except OSError:
            continue
    return _unique_paths(paths)


def resolve_lifecycle_passport(
    samples_path: Path | None,
    *,
    search_roots: Iterable[Path] = (),
    explicit_paths: Iterable[Path] = (),
    expected_source_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve one run's passport by declared path or stable run identity.

    Observer checkpoint filenames contain the save time, while samples use the
    run start time.  ``observer_state.run_id`` is therefore the canonical join
    key.  Multiple passports with the same run ID are checkpoints; the best
    checkpoint at the samples horizon is selected deterministically.
    """

    if samples_path is None:
        return {
            "status": "unavailable",
            "method": None,
            "reason": "samples_path_unavailable",
            "passport_path": None,
            "samples_run_id": None,
            "passport_run_id": None,
            "candidate_count": 0,
            "matched_count": 0,
        }

    samples_path = Path(samples_path).resolve()
    run_id = _samples_run_id(samples_path)
    exact_sibling = samples_path.with_name(f"{run_id}_passport.json")
    explicit = _unique_paths(Path(path) for path in explicit_paths)
    candidates = _passport_candidates(
        samples_path,
        search_roots,
        explicit,
    )
    if not candidates:
        return {
            "status": "unavailable",
            "method": None,
            "reason": "no_passport_candidates",
            "passport_path": None,
            "samples_run_id": run_id,
            "passport_run_id": None,
            "candidate_count": 0,
            "matched_count": 0,
        }

    identities = [_passport_identity(path) for path in candidates]
    explicit_set = {str(path.resolve()) for path in explicit}
    expected_source = (
        str(Path(expected_source_path).resolve())
        if expected_source_path is not None
        else None
    )

    method = None
    matched: list[dict[str, Any]] = []
    if explicit_set:
        matched = [
            item
            for item in identities
            if str(item["path"].resolve()) in explicit_set
        ]
        if matched:
            method = "declared_passport_path"
    if not matched and exact_sibling.exists():
        matched = [
            item
            for item in identities
            if item["path"].resolve() == exact_sibling.resolve()
        ]
        if matched:
            method = "exact_samples_prefix"
    if not matched:
        matched = [
            item for item in identities if item["run_id"] == run_id
        ]
        if matched:
            method = "observer_state_run_id"
    if not matched and expected_source:
        matched = []
        for item in identities:
            if not item["source"]:
                continue
            try:
                source = str(Path(item["source"]).expanduser().resolve())
            except OSError:
                source = item["source"]
            if source == expected_source:
                matched.append(item)
        if matched:
            method = "passport_source_path"
    if not matched:
        matched = [
            item
            for item in identities
            if item["path"].name.startswith(run_id)
        ]
        if matched:
            method = "filename_run_prefix"

    if not matched:
        return {
            "status": "unavailable",
            "method": None,
            "reason": "no_identity_match",
            "passport_path": None,
            "samples_run_id": run_id,
            "passport_run_id": None,
            "candidate_count": len(candidates),
            "matched_count": 0,
        }

    horizon = _sample_final_tick(samples_path)

    def checkpoint_rank(item: dict[str, Any]) -> tuple[int, int, int, int, float]:
        tick = item["tick"]
        if horizon is None or tick is None:
            horizon_class = 0
            distance_rank = -1
        elif tick <= horizon:
            horizon_class = 2
            distance_rank = tick
        else:
            horizon_class = 1
            distance_rank = -abs(tick - horizon)
        try:
            modified = item["path"].stat().st_mtime
        except OSError:
            modified = 0.0
        return (
            horizon_class,
            distance_rank,
            int(item["has_lifecycle_summary"]),
            int(item["has_observer_state"]),
            modified,
        )

    chosen = max(matched, key=checkpoint_rank)
    return {
        "status": "resolved",
        "method": method,
        "reason": f"resolved_by_{method}",
        "passport_path": str(chosen["path"].resolve()),
        "samples_run_id": run_id,
        "passport_run_id": chosen["run_id"] or None,
        "samples_final_tick": horizon,
        "passport_tick": chosen["tick"],
        "candidate_count": len(candidates),
        "matched_count": len(matched),
        "checkpoint_policy": "latest_at_or_before_samples_horizon",
    }


def related_passport_path(
    samples_path: Path | None,
    *,
    search_roots: Iterable[Path] = (),
    explicit_paths: Iterable[Path] = (),
    expected_source_path: Path | None = None,
) -> Path | None:
    """Compatibility wrapper returning the resolved passport path."""

    resolution = resolve_lifecycle_passport(
        samples_path,
        search_roots=search_roots,
        explicit_paths=explicit_paths,
        expected_source_path=expected_source_path,
    )
    path = resolution.get("passport_path")
    return Path(path) if path else None


def lifecycle_contract_for_samples(
    samples_path: Path | None,
    reconciler: LifecycleReconciler,
    *,
    search_roots: Iterable[Path] = (),
    explicit_paths: Iterable[Path] = (),
    expected_source_path: Path | None = None,
) -> dict[str, Any]:
    """Load and reconcile one run's typed lifecycle contract."""

    resolution = resolve_lifecycle_passport(
        samples_path,
        search_roots=search_roots,
        explicit_paths=explicit_paths,
        expected_source_path=expected_source_path,
    )
    passport_path = (
        Path(resolution["passport_path"])
        if resolution.get("passport_path")
        else None
    )
    passport = (
        read_json(passport_path, {})
        if passport_path is not None
        else {}
    )
    if not isinstance(passport, dict):
        passport = {}

    contract = reconciler.reconcile_contract(
        passport.get("lifecycle_summary")
        if isinstance(passport.get("lifecycle_summary"), dict)
        else None,
        passport.get("observer_state")
        if isinstance(passport.get("observer_state"), dict)
        else None,
    )
    return {
        **contract,
        "passport_path": (
            str(passport_path.resolve())
            if passport_path is not None
            else None
        ),
        "source_resolution": resolution,
    }

