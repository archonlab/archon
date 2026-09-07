#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project ARCHON Observer Mutation Engine v1.0.

Creates isolated Observer mutation runs. It never modifies canonical Atlas
rule.json files and never promotes a mutation into Atlas automatically.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import random
import time
from pathlib import Path
from typing import Any

VERSION = "Project ARCHON Observer Mutation Engine v1.0"

FLOAT_FIELDS = {
    "diffusion": (0.0, 0.9),
    "inertia": (0.0, 0.96),
    "damping": (0.92, 0.9995),
    "decay": (0.0, 0.06),
    "noise": (1e-7, 0.02),
    "bias": (-0.04, 0.04),
    "sharpen": (-0.35, 0.35),
    "threshold_push": (-0.12, 0.12),
    "w_avg_r1": (-0.9, 0.9),
    "w_avg_r4": (-0.8, 0.8),
    "w_avg_r12": (-0.65, 0.65),
    "w_var_r1": (-0.65, 0.65),
    "w_var_r4": (-0.55, 0.55),
    "w_lap_r1": (-0.9, 0.9),
    "w_lap_r4": (-0.7, 0.7),
}

TERM_FIELDS = {
    "weight": (-0.22, 0.22),
    "freq": (0.2, 45.0),
    "center": (0.0, 1.0),
    "width": (0.002, 0.18),
    "phase": (0.0, math.tau),
}

FUNCTIONS = ["sin", "cos", "tanh", "gauss", "poly", "step", "ring"]

PRESETS = {
    "conservative": {
        "field_probability": 0.18,
        "term_probability": 0.12,
        "scale_multiplier": 0.35,
    },
    "balanced": {
        "field_probability": 0.35,
        "term_probability": 0.25,
        "scale_multiplier": 0.70,
    },
    "aggressive": {
        "field_probability": 0.62,
        "term_probability": 0.48,
        "scale_multiplier": 1.35,
    },
    "structural": {
        "field_probability": 0.50,
        "term_probability": 0.12,
        "scale_multiplier": 0.90,
    },
    "functional": {
        "field_probability": 0.12,
        "term_probability": 0.58,
        "scale_multiplier": 1.00,
    },
}


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _samples_run_id(path: Path) -> str:
    suffix = "_samples.csv"
    return path.name[:-len(suffix)] if path.name.endswith(suffix) else path.stem


def capture_baseline_provenance(
    *,
    original_rule: dict[str, Any],
    results_root: Path,
) -> dict[str, Any]:
    """Freeze the newest exact canonical baseline used to prepare a mutation.

    The returned paths are evidence references only.  Mutation creation never
    edits or copies the canonical run.
    """
    rule_id = int(original_rule.get("rule_id", -1))
    rule_token = f"{rule_id:05d}"
    expected_seed = original_rule.get("seed")
    logs = Path(results_root) / "observation_logs"
    samples_candidates = sorted(
        logs.glob(f"rule_{rule_token}_*_samples.csv")
    ) if logs.is_dir() else []
    passports = sorted(logs.glob("*passport*.json")) if logs.is_dir() else []

    identities: list[dict[str, Any]] = []
    for path in passports:
        payload = _read_json(path)
        state = (
            payload.get("observer_state")
            if isinstance(payload.get("observer_state"), dict)
            else {}
        )
        life = payload.get("life") if isinstance(payload.get("life"), dict) else {}
        tick = state.get("tick", life.get("final_tick_observed"))
        try:
            tick = int(float(tick)) if tick is not None else None
        except (TypeError, ValueError):
            tick = None
        identities.append({
            "path": path.resolve(),
            "run_id": str(
                state.get("run_id") or payload.get("run_id") or ""
            ).strip(),
            "seed": payload.get("seed", state.get("seed")),
            "tick": tick,
        })

    matches: list[dict[str, Any]] = []
    for samples in samples_candidates:
        run_id = _samples_run_id(samples)
        matched = [item for item in identities if item["run_id"] == run_id]
        if not matched:
            continue
        try:
            sample_tick = -1
            with samples.open(
                "r",
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            ) as fh:
                for row in csv.DictReader(fh):
                    try:
                        sample_tick = int(float(row.get("tick", "")))
                    except (TypeError, ValueError):
                        continue
        except Exception:
            sample_tick = -1
        eligible = [
            item for item in matched
            if item["tick"] is None or sample_tick < 0 or item["tick"] <= sample_tick
        ] or matched
        passport = max(
            eligible,
            key=lambda item: (
                item["tick"] if item["tick"] is not None else -1,
                item["path"].stat().st_mtime,
            ),
        )
        same_seed = (
            expected_seed is not None
            and passport["seed"] is not None
            and str(expected_seed) == str(passport["seed"])
        )
        matches.append({
            "samples_path": str(samples.resolve()),
            "passport_path": str(passport["path"]),
            "run_id": run_id,
            "samples_final_tick": sample_tick,
            "passport_tick": passport["tick"],
            "same_seed": same_seed,
            "modified": max(
                samples.stat().st_mtime,
                passport["path"].stat().st_mtime,
            ),
        })

    exact = [item for item in matches if item["same_seed"]]
    pool = exact or matches
    if not pool:
        return {
            "status": "unavailable",
            "reason": "no_canonical_baseline_with_resolved_passport",
            "rule_id": rule_token,
            "expected_seed": expected_seed,
        }
    chosen = max(
        pool,
        key=lambda item: (
            int(item["same_seed"]),
            item["modified"],
            item["samples_final_tick"],
        ),
    )
    return {
        "status": "resolved",
        "method": "frozen_at_mutation_preparation",
        "rule_id": rule_token,
        "expected_seed": expected_seed,
        **{key: value for key, value in chosen.items() if key != "modified"},
    }


def stable_payload_hash(payload: dict[str, Any]) -> str:
    clean = copy.deepcopy(payload)
    clean.pop("rule_id", None)
    raw = json.dumps(clean, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def mutate_number(
    value: float,
    lo: float,
    hi: float,
    intensity: float,
    rng: random.Random,
    logarithmic: bool = False,
) -> float:
    intensity = max(0.0001, float(intensity))
    if logarithmic:
        current = math.log10(max(float(value), 1e-12))
        lower = math.log10(lo)
        upper = math.log10(hi)
        span = upper - lower
        return 10 ** clamp(
            current + rng.gauss(0.0, span * 0.12 * intensity),
            lower,
            upper,
        )
    span = hi - lo
    return clamp(
        float(value) + rng.gauss(0.0, span * 0.08 * intensity),
        lo,
        hi,
    )


def diff_payload(original: Any, mutated: Any, path: str = "") -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if isinstance(original, dict) and isinstance(mutated, dict):
        keys = sorted(set(original) | set(mutated))
        for key in keys:
            child = f"{path}.{key}" if path else key
            changes.extend(
                diff_payload(original.get(key), mutated.get(key), child)
            )
    elif isinstance(original, list) and isinstance(mutated, list):
        for index in range(max(len(original), len(mutated))):
            left = original[index] if index < len(original) else None
            right = mutated[index] if index < len(mutated) else None
            changes.extend(diff_payload(left, right, f"{path}[{index}]"))
    elif original != mutated:
        changes.append({
            "path": path,
            "before": original,
            "after": mutated,
        })
    return changes


def mutate_single_parameter(
    payload: dict[str, Any],
    parameter: str,
    intensity: float,
    rng: random.Random,
) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    if parameter.startswith("term["):
        prefix, field = parameter.split("].", 1)
        index = int(prefix[5:])
        terms = out.get("terms", [])
        if not (0 <= index < len(terms)):
            raise ValueError(f"Term index out of range: {index}")
        if field == "kind":
            choices = [x for x in FUNCTIONS if x != terms[index].get("kind")]
            terms[index]["kind"] = rng.choice(choices)
        else:
            lo, hi = TERM_FIELDS[field]
            terms[index][field] = mutate_number(
                float(terms[index][field]),
                lo,
                hi,
                intensity,
                rng,
            )
            if field == "phase":
                terms[index][field] %= math.tau
        return out

    if parameter not in FLOAT_FIELDS:
        raise ValueError(f"Unknown mutation parameter: {parameter}")
    lo, hi = FLOAT_FIELDS[parameter]
    out[parameter] = mutate_number(
        float(out[parameter]),
        lo,
        hi,
        intensity,
        rng,
        logarithmic=(parameter == "noise"),
    )
    return out


def mutate_local_random(
    payload: dict[str, Any],
    intensity: float,
    rng: random.Random,
    *,
    field_probability: float = 0.35,
    term_probability: float = 0.25,
) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    changed = False

    for field, (lo, hi) in FLOAT_FIELDS.items():
        if field in out and rng.random() < field_probability:
            out[field] = mutate_number(
                float(out[field]),
                lo,
                hi,
                intensity,
                rng,
                logarithmic=(field == "noise"),
            )
            changed = True

    for term in out.get("terms", []):
        if rng.random() >= term_probability:
            continue
        candidates = list(TERM_FIELDS)
        field = rng.choice(candidates)
        lo, hi = TERM_FIELDS[field]
        term[field] = mutate_number(
            float(term[field]),
            lo,
            hi,
            intensity,
            rng,
        )
        if field == "phase":
            term[field] %= math.tau
        if rng.random() < 0.08 * intensity:
            term["kind"] = rng.choice(FUNCTIONS)
        changed = True

    if not changed:
        field = rng.choice(list(FLOAT_FIELDS))
        return mutate_single_parameter(out, field, intensity, rng)
    return out


def create_mutation_run(
    *,
    original_rule: dict[str, Any],
    mutation_root: Path,
    mode: str,
    intensity: float,
    seed: int,
    parameter: str | None = None,
    preset: str = "balanced",
    sequence: int = 1,
    baseline_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    original = copy.deepcopy(original_rule)

    if mode == "none":
        mutated = copy.deepcopy(original)
    elif mode == "single_parameter":
        if not parameter:
            raise ValueError("single_parameter mode requires parameter")
        mutated = mutate_single_parameter(
            original, parameter, intensity, rng
        )
    elif mode == "local_random":
        mutated = mutate_local_random(original, intensity, rng)
    elif mode == "preset":
        config = PRESETS.get(preset)
        if config is None:
            raise ValueError(f"Unknown preset: {preset}")
        mutated = mutate_local_random(
            original,
            intensity * config["scale_multiplier"],
            rng,
            field_probability=config["field_probability"],
            term_probability=config["term_probability"],
        )
    else:
        raise ValueError(f"Unknown mutation mode: {mode}")

    original_hash = stable_payload_hash(original)
    mutated_hash = stable_payload_hash(mutated)
    rule_id = int(original.get("rule_id", -1))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    mutation_id = (
        f"MUT-{rule_id:05d}-{stamp}-{sequence:02d}-{mutated_hash[:6]}"
    )
    run_dir = mutation_root / f"rule_{rule_id:05d}" / mutation_id
    run_dir.mkdir(parents=True, exist_ok=False)

    changes = diff_payload(original, mutated)
    baseline_provenance = copy.deepcopy(baseline_provenance or {
        "status": "unavailable",
        "reason": "baseline_not_resolved_at_mutation_preparation",
    })
    manifest = {
        "schema": "archon_observer_mutation_run_v2",
        "version": VERSION,
        "mutation_id": mutation_id,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "canonical_parent_rule_id": rule_id,
        "canonical_parent_hash": original_hash,
        "mutated_hash": mutated_hash,
        "mutation_mode": mode,
        "mutation_parameter": parameter,
        "mutation_preset": preset if mode == "preset" else None,
        "mutation_intensity": float(intensity),
        "mutation_seed": int(seed),
        "change_count": len(changes),
        "changes": changes,
        "canonical_promotion": False,
        "status": "prepared",
        "baseline_provenance": baseline_provenance,
        "execution_control": {
            "policy": "manual_stop_shared_analysis_horizon",
            "target_final_tick": None,
            "comparison_reference_tick": (
                int(baseline_provenance["samples_final_tick"])
                if baseline_provenance.get("status") == "resolved"
                and baseline_provenance.get("samples_final_tick") is not None
                else None
            ),
            "disable_auto_stop": True,
            "canonical_promotion": False,
        },
        "paths": {
            "run_dir": str(run_dir),
            "original_rule": str(run_dir / "original_rule.json"),
            "mutated_rule": str(run_dir / "mutated_rule.json"),
            "mutation_diff": str(run_dir / "mutation_diff.json"),
            "baseline_samples": (
                str(baseline_provenance["samples_path"])
                if baseline_provenance.get("status") == "resolved"
                else None
            ),
            "baseline_passport": (
                str(baseline_provenance["passport_path"])
                if baseline_provenance.get("status") == "resolved"
                else None
            ),
        },
    }

    atomic_json(run_dir / "original_rule.json", original)
    atomic_json(run_dir / "mutated_rule.json", mutated)
    atomic_json(run_dir / "mutation_diff.json", changes)
    atomic_json(run_dir / "mutation_manifest.json", manifest)

    return {
        "mutation_id": mutation_id,
        "run_dir": run_dir,
        "rule_file": run_dir / "mutated_rule.json",
        "manifest_file": run_dir / "mutation_manifest.json",
        "manifest": manifest,
        "target_final_tick": None,
    }


def parameter_choices(rule: dict[str, Any]) -> list[str]:
    choices = list(FLOAT_FIELDS)
    for index, term in enumerate(rule.get("terms", [])):
        for field in ("weight", "freq", "center", "width", "phase", "kind"):
            choices.append(f"term[{index}].{field}")
    return choices
