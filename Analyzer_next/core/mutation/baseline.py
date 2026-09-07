"""Mutation sample discovery and canonical baseline selection policy."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .constants import RULE_RE
from .lifecycle import _passport_identity, _samples_run_id
from .utils import is_inside, normalize_rule_id, read_json, safe_int

def rule_id_from_filename(path: Path) -> str | None:
    match = RULE_RE.search(path.name)
    return normalize_rule_id(match.group(1)) if match else None


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        return list(csv.DictReader(fh))


def sample_files(folder: Path) -> list[Path]:
    return sorted(folder.glob("*_samples.csv"))


def choose_mutant_samples(run_dir: Path) -> Path | None:
    candidates = sample_files(run_dir)
    if not candidates:
        candidates = sorted(run_dir.rglob("*_samples.csv"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.stat().st_size, p.stat().st_mtime))


def extract_seed_from_nearby_passport(samples_path: Path) -> Any:
    run_id = _samples_run_id(samples_path)
    candidates: list[Path] = []
    for path in samples_path.parent.glob("*passport*.json"):
        identity = _passport_identity(path)
        if (
            identity.get("run_id") == run_id
            or path.name.startswith(run_id)
        ):
            candidates.append(path)
    candidates += list(samples_path.parent.glob(f"{run_id}*_header.json"))
    for path in candidates:
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            continue
        for key in ("seed", "rule_seed", "world_seed"):
            if payload.get(key) not in {None, ""}:
                return payload.get(key)
        for key in ("run", "metadata", "rule"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                for seed_key in ("seed", "rule_seed", "world_seed"):
                    if nested.get(seed_key) not in {None, ""}:
                        return nested.get(seed_key)
    return None


def discover_baseline_samples(
    results_root: Path,
    mutation_root: Path,
    rule_id: str,
) -> list[Path]:
    candidates: list[Path] = []
    pattern = f"rule_{rule_id}_*_samples.csv"
    for path in results_root.rglob(pattern):
        if is_inside(path, mutation_root):
            continue
        candidates.append(path)
    return sorted(set(candidates))


def final_tick(path: Path) -> int:
    rows = load_csv_rows(path)
    if not rows:
        return -1
    tick = safe_int(rows[-1].get("tick"))
    return -1 if tick is None else tick


def choose_baseline(
    candidates: list[Path],
    mutant_path: Path,
    original_seed: Any,
    explicit_path: str | None = None,
) -> dict[str, Any]:
    mutant_tick = final_tick(mutant_path)

    if explicit_path:
        explicit = Path(explicit_path).expanduser()
        if explicit.exists():
            return {
                "path": explicit.resolve(),
                "match_type": "exact_declared",
                "same_seed": None,
                "coverage_ratio": min(
                    1.0,
                    max(0.0, final_tick(explicit) / max(1, mutant_tick)),
                ),
                "reason": "Explicit baseline path from mutation metadata.",
            }
        return {
            "path": None,
            "match_type": "missing_declared",
            "same_seed": None,
            "coverage_ratio": 0.0,
            "reason": "Declared baseline path is missing; fallback is forbidden.",
            "declared_path": str(explicit),
        }

    if not candidates:
        return {
            "path": None,
            "match_type": "missing",
            "same_seed": None,
            "coverage_ratio": 0.0,
            "reason": "No non-mutation sample file found for canonical parent.",
        }

    ranked: list[tuple[tuple[int, float, int, float], Path, Any]] = []
    for path in candidates:
        tick = final_tick(path)
        candidate_seed = extract_seed_from_nearby_passport(path)
        same_seed = (
            candidate_seed is not None
            and original_seed is not None
            and str(candidate_seed) == str(original_seed)
        )
        covers = tick >= mutant_tick
        distance = abs(tick - mutant_tick)
        ranked.append(
            (
                (
                    1 if same_seed else 0,
                    1.0 if covers else tick / max(1, mutant_tick),
                    -distance,
                    path.stat().st_mtime,
                ),
                path,
                candidate_seed,
            )
        )

    _, chosen, candidate_seed = max(ranked, key=lambda item: item[0])
    chosen_tick = final_tick(chosen)
    same_seed = (
        candidate_seed is not None
        and original_seed is not None
        and str(candidate_seed) == str(original_seed)
    )
    coverage = min(1.0, max(0.0, chosen_tick / max(1, mutant_tick)))

    if same_seed and chosen_tick >= mutant_tick:
        match_type = "matched_seed_and_duration"
    elif same_seed:
        match_type = "matched_seed_partial_duration"
    elif chosen_tick >= mutant_tick:
        match_type = "matched_rule_and_duration"
    else:
        match_type = "approximate_rule_baseline"

    return {
        "path": chosen.resolve(),
        "match_type": match_type,
        "same_seed": same_seed if candidate_seed is not None else None,
        "candidate_seed": candidate_seed,
        "coverage_ratio": round(coverage, 4),
        "reason": (
            "Best available non-mutation baseline ranked by seed, duration, "
            "tick distance, and recency."
        ),
    }
