"""Pure ranking policy for Research Notebook Index v1."""
from __future__ import annotations

from .contracts import ResearchNotebookIndexItem


def research_score(item: ResearchNotebookIndexItem) -> float:
    score = 0.0
    lifetime = item.lifetime or 0
    dynamic = item.dynamic or 0
    breathing = item.breathing or 0
    if isinstance(lifetime, (int, float)):
        score += min(lifetime / 100000, 1.0) * 3.0
    if isinstance(dynamic, (int, float)):
        score += min(dynamic, 1.0) * 2.0
    if isinstance(breathing, (int, float)):
        score += min(breathing, 1.0) * 1.0
    score += min(item.discoveries / 4, 1.0) * 1.5
    score += min(item.mechanisms / 5, 1.0) * 1.0
    score += min(item.principles / 5, 1.0) * 1.0
    score += min(item.predictions / 5, 1.0) * 0.5
    return round(min(score, 10.0), 2)


__all__ = ["research_score"]
