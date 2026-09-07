"""Pure per-run morphological epoch analysis."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from Analyzer_next.core.epochs.boundaries import epoch_slices, pick_boundaries
from Analyzer_next.core.epochs.classification import (
    archetype_from_epochs,
    classify_epoch,
    detect_epoch_cycles,
    epoch_indices,
    epoch_signature,
    make_epoch,
    merge_same_type_epochs,
)
from Analyzer_next.core.epochs.numeric import (
    mean,
    normalized_series,
    safe_float,
    slope,
    sparkline,
)
from Analyzer_next.core.epochs.rows import infer_rule_id, normalize_rows
from Analyzer_next.core.epochs.signals import build_signal_rows


def analyze_rows(
    path: Path,
    raw_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    rows = normalize_rows(raw_rows)
    if not rows:
        return None
    rule_id = infer_rule_id(path, rows)
    signal_rows = build_signal_rows(rows)
    boundaries = pick_boundaries(signal_rows)
    slices = epoch_slices(boundaries)
    epochs = []
    previous = None
    for index, (start, end) in enumerate(slices):
        epoch_type = classify_epoch(
            signal_rows, start, end, index, len(slices), previous
        )
        epochs.append(make_epoch(rows, signal_rows, start, end, epoch_type))
        previous = epoch_type
    epochs = merge_same_type_epochs(epochs, rows, signal_rows)
    signature = epoch_signature(epochs)
    cycles = detect_epoch_cycles(signature)
    indices = epoch_indices(epochs)
    archetype = archetype_from_epochs(epochs, indices)
    mci = [row["_mci"] for row in rows]
    mass = [safe_float(row.get("_total_living_mass"), 0.0) for row in rows]
    change = [safe_float(row.get("_morphology_change_rate"), 0.0) for row in rows]
    pressure = [safe_float(row.get("_evo_pressure"), 0.0) for row in rows]
    return {
        "rule_id": rule_id,
        "source_csv": str(path),
        "first_tick": rows[0]["_tick"],
        "last_tick": rows[-1]["_tick"],
        "observed_ticks": max(1, rows[-1]["_tick"] - rows[0]["_tick"]),
        "samples": len(rows),
        "epoch_archetype": archetype,
        "epoch_signature": signature,
        "epoch_signature_text": " -> ".join(signature) if signature else "NONE",
        "epochs": epochs,
        "cycles": cycles,
        "indices": indices,
        "boundaries": boundaries,
        "sparklines": {
            "mci": sparkline(mci),
            "mass": sparkline(mass),
            "change_rate": sparkline(change),
            "pressure": sparkline(pressure),
        },
        "summary": {
            "mean_mci": mean(mci),
            "mci_slope": slope(normalized_series(mci)),
            "mean_mass": mean(mass),
            "mass_slope": slope(normalized_series(mass)),
            "mean_change_rate": mean(change),
            "mean_pressure": mean(pressure),
        },
    }

