"""Pure Markdown rendering for Research Notebook Index v1."""
from __future__ import annotations

from .contracts import ResearchNotebookIndexItem
from .scoring import research_score


def fmt(value) -> str:
    if value is None:
        return "None"
    return str(value)


def render_index(
    items: list[ResearchNotebookIndexItem],
    generated_at: str,
) -> str:
    ranked = sorted(items, key=research_score, reverse=True)
    families: dict[str, int] = {}
    for item in ranked:
        family = item.classification or "unknown"
        families[family] = families.get(family, 0) + 1

    lines: list[str] = []
    lines.append("# Universe Search Research Notebook Index")
    lines.append("")
    lines.append(f"Generated: **{generated_at}**")
    lines.append(f"Experiments: **{len(ranked)}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total experiments: **{len(ranked)}**")
    lines.append(f"- Families/classes: **{len(families)}**")
    lines.append(f"- Total discoveries: **{sum(item.discoveries for item in ranked)}**")
    lines.append(f"- Total mechanisms: **{sum(item.mechanisms for item in ranked)}**")
    lines.append(
        f"- Total principles linked: **{sum(item.principles for item in ranked)}**"
    )
    lines.append(
        f"- Total predictions linked: **{sum(item.predictions for item in ranked)}**"
    )
    lines.append("")
    lines.append("## Families")
    lines.append("")
    for family, count in sorted(
        families.items(),
        key=lambda pair: pair[1],
        reverse=True,
    ):
        lines.append(f"- **{family}**: {count}")
    lines.append("")
    lines.append("## Top Research Worlds")
    lines.append("")
    lines.append(
        "| Rank | Rule | Class | Lifetime | Dynamic | Breathing | Confidence | Score | Notebook |"
    )
    lines.append("| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | --- |")
    for rank, item in enumerate(ranked, start=1):
        lines.append(
            f"| {rank} | {item.rule} | {item.classification} | "
            f"{fmt(item.lifetime)} | {fmt(item.dynamic)} | "
            f"{fmt(item.breathing)} | {item.confidence} | "
            f"{research_score(item)} | [open]({item.filename}) |"
        )
    lines.append("")
    lines.append("## Research Coverage")
    lines.append("")
    lines.append(
        "| Rule | Questions | Discoveries | Mechanisms | Principles | Predictions | Status |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for item in ranked:
        lines.append(
            f"| {item.rule} | {item.questions} | {item.discoveries} | "
            f"{item.mechanisms} | {item.principles} | {item.predictions} | "
            f"{item.status} |"
        )
    lines.append("")
    lines.append("## Research Timeline")
    lines.append("")
    for item in sorted(ranked, key=lambda candidate: candidate.date or ""):
        lines.append(
            f"- **{item.date}**: Rule **{item.rule}** → "
            f"{item.classification} / confidence {item.confidence}"
        )
    lines.append("")
    lines.append("## Next Index Improvements")
    lines.append("")
    lines.append("- Add validation status when Prediction/Validation Engine matures.")
    lines.append("- Add similarity links from Atlas.")
    lines.append("- Add mechanism score summary from mechanism reports.")
    lines.append("- Add manual research notes index.")
    lines.append("")
    return "\n".join(lines)


__all__ = ["fmt", "render_index"]
