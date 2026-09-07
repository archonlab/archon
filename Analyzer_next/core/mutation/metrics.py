"""Numeric deltas and structural-extinction measurements."""
from __future__ import annotations

from typing import Any

from .utils import safe_float, safe_int

def relative_delta(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    if abs(before) < 1e-12:
        return None
    return (after - before) / abs(before)


def compare_summaries(
    baseline: dict[str, Any],
    mutant: dict[str, Any],
) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}

    for view in ("final", "tail_median", "peak"):
        base_values = baseline.get(view, {})
        mutant_values = mutant.get(view, {})
        view_delta: dict[str, Any] = {}

        for metric in sorted(set(base_values) | set(mutant_values)):
            before = safe_float(base_values.get(metric))
            after = safe_float(mutant_values.get(metric))
            if before is None or after is None:
                continue
            view_delta[metric] = {
                "baseline": round(before, 8),
                "mutant": round(after, 8),
                "absolute_delta": round(after - before, 8),
                "relative_delta": (
                    round(rel, 8)
                    if (rel := relative_delta(before, after)) is not None
                    else None
                ),
            }
        comparisons[view] = view_delta

    base_categories = baseline.get("categorical_final", {})
    mutant_categories = mutant.get("categorical_final", {})
    comparisons["categorical_transitions"] = {
        metric: {
            "baseline": base_categories.get(metric),
            "mutant": mutant_categories.get(metric),
            "changed": base_categories.get(metric) != mutant_categories.get(metric),
        }
        for metric in sorted(set(base_categories) | set(mutant_categories))
    }
    return comparisons


def is_structurally_extinct(row: dict[str, str]) -> bool:
    """
    Technical extinction criterion used before the Observer Life Detector exists.

    This is not a claim about life or death. It only means that the sampled
    world contains no detected living mass or objects.
    """
    objects = safe_float(row.get("objects"))
    total_mass = safe_float(row.get("total_living_mass"))
    largest = safe_float(row.get("largest"))
    active_families = safe_float(row.get("active_families"))

    core_zero = (
        objects is not None
        and total_mass is not None
        and objects <= 0.0
        and total_mass <= 0.0
    )
    if not core_zero:
        return False

    optional_zero = True
    if largest is not None:
        optional_zero = optional_zero and largest <= 0.0
    if active_families is not None:
        optional_zero = optional_zero and active_families <= 0.0

    return optional_zero


def persistent_structural_extinction_tick(
    rows: list[dict[str, str]],
    grace_samples: int = 3,
) -> int | None:
    """
    Return the first tick of the terminal structural-extinction run.

    Temporary zero states are ignored when detectable structure returns later.
    The final sampled state must remain structurally extinct through the end.
    """
    states: list[tuple[int, bool]] = []
    for row in rows:
        tick = safe_int(row.get("tick"))
        if tick is None:
            continue
        states.append((tick, is_structurally_extinct(row)))

    if not states or states[-1][1] is not True:
        return None

    index = len(states) - 1
    while index >= 0 and states[index][1] is True:
        index -= 1
    run_start = index + 1
    extinct_run = states[run_start:]

    if not extinct_run or any(state is not True for _, state in extinct_run):
        return None

    if len(extinct_run) < max(1, grace_samples):
        if len(states) >= grace_samples + 1:
            return None

    return extinct_run[0][0]


def structural_extinction_comparison(
    baseline_rows: list[dict[str, str]],
    mutant_rows: list[dict[str, str]],
    grace_samples: int = 3,
) -> dict[str, Any]:
    baseline_tick = persistent_structural_extinction_tick(
        baseline_rows,
        grace_samples=grace_samples,
    )
    mutant_tick = persistent_structural_extinction_tick(
        mutant_rows,
        grace_samples=grace_samples,
    )

    result = {
        "method": "terminal_zero_structure_run",
        "grace_samples": grace_samples,
        "criterion": {
            "objects": 0,
            "total_living_mass": 0,
            "largest": "0 when available",
            "active_families": "0 when available",
        },
        "baseline_structural_extinction_tick": baseline_tick,
        "mutant_structural_extinction_tick": mutant_tick,
        "tick_delta": None,
        "relative_delay": None,
        "classification": None,
        "life_claim": False,
    }

    if baseline_tick is None or mutant_tick is None:
        return result

    delta = mutant_tick - baseline_tick
    result["tick_delta"] = delta
    if baseline_tick > 0:
        result["relative_delay"] = round(delta / baseline_tick, 8)

    tolerance = max(2, int(round(0.05 * max(baseline_tick, mutant_tick))))
    if abs(delta) <= tolerance:
        result["classification"] = "structural_extinction_timing_preserved"
    elif delta > 0:
        result["classification"] = "structural_extinction_delayed"
    else:
        result["classification"] = "structural_extinction_accelerated"
    return result

