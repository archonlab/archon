"""Pure Markdown projection for research notebooks."""
from __future__ import annotations

from typing import Any

from .related import load_optional_lines


def render_markdown(
    notebook: dict[str, Any],
    *,
    results_folder_display: str,
    questions_text: str,
    discoveries_text: str,
    mechanisms_text: str,
    principles_text: str,
    predictions_text: str,
) -> str:
    experiment = notebook["experiment"]
    evidence = notebook["evidence"]
    confidence = notebook["confidence"]
    rule = experiment.get("rule")
    questions = load_optional_lines(questions_text, "questions", rule)
    discoveries = load_optional_lines(discoveries_text, "discoveries", rule)
    mechanisms = load_optional_lines(mechanisms_text, "mechanisms")
    principles = load_optional_lines(principles_text, "principles")
    predictions = load_optional_lines(predictions_text, "predictions")
    lines: list[str] = []
    lines.append("# Universe Search Research Notebook")
    lines.append("")
    lines.append(f"## Experiment: Rule {experiment.get('rule') or 'unknown'}")
    lines.append("")
    lines.append(f"- Date: **{experiment.get('date')}**")
    lines.append(f"- Rule: **{experiment.get('rule')}**")
    lines.append(f"- Status: **{experiment.get('status')}**")
    lines.append(f"- Source folder: `{results_folder_display}`")
    lines.append("")
    lines.append("## Observation")
    lines.append("")
    for item in notebook["observation"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Hypothesis")
    lines.append("")
    for item in notebook["hypothesis"]:
        lines.append(f"- {item}")
    if not notebook["hypothesis"]:
        lines.append("- No strong hypothesis yet.")
    lines.append("")
    lines.append("## Evidence")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    for key, value in evidence.items():
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append("## Confidence")
    lines.append("")
    lines.append(f"Level: **{confidence.get('level')}**")
    lines.append("")
    lines.append("Reasons:")
    for reason in confidence.get("reason", []):
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("## Open Questions")
    lines.append("")
    if questions:
        for question in questions:
            lines.append(f"- {question}")
    else:
        lines.append("- No linked questions found yet.")
    lines.append("")
    lines.append("## Discoveries")
    lines.append("")
    if discoveries:
        for discovery in discoveries:
            lines.append(f"- {discovery}")
    else:
        lines.append("- No linked discoveries found yet.")
    lines.append("")
    lines.append("## Mechanisms")
    lines.append("")
    if mechanisms:
        for mechanism in mechanisms:
            lines.append(f"- {mechanism}")
    else:
        lines.append("- No linked mechanisms found yet.")
    lines.append("")
    lines.append("## General Principles")
    lines.append("")
    if principles:
        for principle in principles:
            lines.append(f"- {principle}")
    else:
        lines.append("- No linked principles found yet.")
    lines.append("")
    lines.append("## Predictions")
    lines.append("")
    if predictions:
        for prediction in predictions:
            lines.append(f"- {prediction}")
    else:
        lines.append("- No linked predictions found yet.")
    lines.append("")
    lines.append("## Next Experiment")
    lines.append("")
    for item in notebook["next_experiment"]:
        lines.append(f"- [ ] {item}")
    if not notebook["next_experiment"]:
        lines.append("- [ ] Continue observation and save a new passport.")
    lines.append("")
    lines.append("## Research Notes")
    lines.append("")
    lines.append("- Add manual notes here.")
    lines.append("")
    return "\n".join(lines)


__all__ = ["render_markdown"]
