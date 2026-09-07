"""Robust broad-boundary selection for epoch segmentation."""
from __future__ import annotations

from typing import Any

from Analyzer_next.core.epochs.numeric import mad, median
from Analyzer_next.core.epochs.signals import change_scores


def pick_boundaries(signal_rows: list[dict[str, Any]]) -> list[int]:
    count = len(signal_rows)
    if count <= 12:
        return [0, count - 1]
    scores = change_scores(signal_rows)
    middle = median(scores)
    noise = mad(scores)
    threshold = middle + max(0.04, 1.25 * noise)
    minimum_gap = max(4, count // 9)
    candidates = []
    for index in range(2, count - 2):
        if scores[index] < threshold:
            continue
        if scores[index] >= scores[index - 1] and scores[index] >= scores[index + 1]:
            candidates.append((index, scores[index]))
    candidates = sorted(candidates, key=lambda item: item[1], reverse=True)
    boundaries = [0, count - 1]
    maximum_boundaries = max(3, min(10, count // 10))
    for index, _score in candidates:
        if len(boundaries) >= maximum_boundaries:
            break
        if all(abs(index - boundary) >= minimum_gap for boundary in boundaries):
            boundaries.append(index)
    boundaries = sorted(set(boundaries))
    if len(boundaries) < 3 and count >= 30:
        boundaries = sorted(set([0, count // 3, 2 * count // 3, count - 1]))
    return boundaries


def epoch_slices(boundaries: list[int]) -> list[tuple[int, int]]:
    output = []
    for start, end in zip(boundaries, boundaries[1:]):
        if end > start:
            output.append((start, end))
    return output

