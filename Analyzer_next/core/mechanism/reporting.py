"""Markdown projection for one inferred mechanism record."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def render_report(
    rule_path: Path,
    genome: dict[str, Any],
    behaviour: dict[str, Any],
    mechanisms: list[dict[str, Any]],
    *,
    generated: str,
) -> str:
    lines: list[str] = []
    lines.append("# Universe Search Mechanism Report")
    lines.append("")
    lines.append(f"Generated: **{generated}**")
    lines.append(f"Rule file: `{rule_path}`")
    lines.append("")
    lines.append(f"Rule: **{genome['rule_id']}**")
    if behaviour.get("canonicalized_from_alias"):
        lines.append(
            f"Historical alias: **{behaviour.get('source_rule_id')}** "
            f"→ **{behaviour.get('rule')}**"
        )
    lines.append(
        f"Parents: **{genome['parents'][0]}**, **{genome['parents'][1]}**"
    )
    lines.append("")

    lines.append("## Genome summary")
    lines.append("")
    lines.append("| Feature | Value | Reading |")
    lines.append("| --- | ---: | --- |")
    lines.append(
        f"| damping | {genome['damping']:.6f} | "
        f"{genome['memory_level']} memory retention |"
    )
    lines.append(
        f"| decay | {genome['decay']:.6f} | "
        f"{genome['decay_level']} decay pressure |"
    )
    lines.append(
        f"| noise | {genome['noise']:.10f} | "
        f"{genome['noise_level']} stochastic disruption |"
    )
    lines.append(
        f"| diffusion | {genome['diffusion']:.6f} | "
        f"{genome['diffusion_level']} diffusion |"
    )
    lines.append(
        f"| inertia | {genome['inertia']:.6f} | "
        f"{genome['inertia_level']} inertia |"
    )
    lines.append(
        f"| term count | {genome['term_count']} | nonlinear components |"
    )
    lines.append(
        f"| term kinds | {genome['term_kinds']} | functional vocabulary |"
    )
    lines.append(
        f"| local strength | {genome['local_strength']:.3f} | r1 channels |"
    )
    lines.append(
        f"| multi-scale strength | {genome['multi_scale_strength']:.3f} | "
        "r4/r12 channels |"
    )
    lines.append("")

    lines.append("## Mechanism scores")
    lines.append("")
    lines.append("| Mechanism score | Value |")
    lines.append("| --- | ---: |")
    lines.append(
        f"| Field memory | {genome['field_memory_score']:.3f} |"
    )
    lines.append(
        "| Stochastic stability | "
        f"{genome['stochastic_stability_score']:.3f} |"
    )
    lines.append(
        "| Oscillatory feedback | "
        f"{genome['oscillatory_feedback_score']:.3f} |"
    )
    lines.append(
        f"| Multi-scale feedback | {genome['multi_scale_score']:.3f} |"
    )
    lines.append(
        "| Genome complexity | "
        f"{genome['genome_complexity_score']:.3f} |"
    )
    lines.append("")

    lines.append("## Behaviour link")
    lines.append("")
    lines.append(f"- Lifetime: **{behaviour.get('lifetime')}**")
    lines.append(f"- Dynamic score: **{behaviour.get('dynamic_score')}**")
    lines.append(
        f"- Breathing score: **{behaviour.get('breathing_score')}**"
    )
    lines.append(
        f"- Classification: **{behaviour.get('classification')}**"
    )
    lines.append(f"- Collapse: **{behaviour.get('collapse')}**")
    lines.append(f"- Objects: **{behaviour.get('objects')}**")
    lines.append("")

    lines.append("## Candidate mechanisms")
    lines.append("")
    for mechanism in mechanisms:
        lines.append(
            f"### {mechanism['id']}: {mechanism['title']}"
        )
        lines.append("")
        lines.append(f"- Confidence: **{mechanism['confidence']}**")
        lines.append(f"- Claim: {mechanism['claim']}")
        lines.append(
            f"- Behaviour link: {mechanism['behaviour_link']}"
        )
        lines.append("")
        lines.append("Evidence:")
        for evidence in mechanism["evidence"]:
            lines.append(f"- {evidence}")
        lines.append("")
    if not mechanisms:
        lines.append("No strong mechanism candidates detected yet.")
        lines.append("")

    lines.append("## Mechanism hypothesis")
    lines.append("")
    lines.append(
        "The current best explanation is a combination of **field memory**, "
        "**low stochastic disruption**, and **multi-scale oscillatory feedback**. "
        "This may allow the world to preserve macro-structure while local "
        "components keep changing."
    )
    lines.append("")
    lines.append(
        "This is not proven. It is a mechanistic hypothesis to test by "
        "comparing rule genomes across many worlds."
    )
    lines.append("")
    lines.append("## Next tests")
    lines.append("")
    lines.append(
        "1. Compare this rule with matched stable, collapsed, oscillator, "
        "and noise-like controls."
    )
    lines.append(
        "2. Test each candidate mechanism by changing one genome feature at a time."
    )
    lines.append(
        "3. Re-run the rule after perturbation and measure whether the "
        "predicted behaviour changes."
    )
    lines.append(
        "4. Search for the same mechanism signature across independent rules."
    )
    lines.append(
        "5. Promote a mechanism only after behavioural and perturbation "
        "evidence agree."
    )
    lines.append("")
    return "\n".join(lines)
