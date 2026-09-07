#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
question_tracker.py

Generates research hypotheses and open questions from passport_analysis.md
or a Life Passport markdown file.

Usage:
    python question_tracker.py universe_search_v23_results/passport_analysis.md

Or folder:
    python question_tracker.py universe_search_v23_results

Output:
    research_questions.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from dataclasses import dataclass


@dataclass
class WorldSignal:
    rule: str
    lifetime: int = 0
    classification: str = "unknown"
    dynamic_score: float = 0.0
    breathing_score: float = 0.0
    collapse: str = "unknown"
    objects: str = "unknown"
    split_birth: int = 0
    merge_death: int = 0


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def find_input_file(path: Path) -> Path:
    if path.is_file():
        return path

    preferred = path / "passport_analysis.md"
    if preferred.exists():
        return preferred

    matches = sorted(path.rglob("passport_analysis.md"))
    if matches:
        return matches[0]

    matches = sorted(path.rglob("*passport*.md"))
    if matches:
        return matches[0]

    raise FileNotFoundError(f"No passport analysis or passport file found in {path}")


def parse_passport_analysis(text: str) -> list[WorldSignal]:
    worlds: list[WorldSignal] = []

    # Parse detailed sections from passport_analyzer output.
    sections = re.split(r"\n## Rule\s+", text)
    if len(sections) > 1:
        for sec in sections[1:]:
            first = sec.splitlines()[0].strip()
            rule = re.findall(r"\d+", first)
            signal = WorldSignal(rule=rule[0].zfill(5) if rule else "unknown")

            def grab(label: str) -> str | None:
                m = re.search(rf"-\s*{re.escape(label)}:\s*\*\*([^*]+)\*\*", sec)
                return m.group(1).strip() if m else None

            lifetime = grab("Longest observed age")
            if lifetime:
                signal.lifetime = int(lifetime.replace(",", ""))

            signal.classification = grab("Classification") or signal.classification

            dyn = grab("Dynamic attractor score")
            if dyn:
                signal.dynamic_score = float(dyn)

            breath = grab("Breathing score")
            if breath:
                signal.breathing_score = float(breath)

            collapse = grab("Collapse tick")
            if collapse:
                signal.collapse = collapse

            obj = grab("Object range")
            if obj:
                signal.objects = obj.replace("–", "-")

            split = grab("Split/birth events")
            if split:
                signal.split_birth = int(split)

            merge = grab("Merge/death events")
            if merge:
                signal.merge_death = int(merge)

            worlds.append(signal)
        return worlds

    # Parse console-like output fallback.
    chunks = re.split(r"\nRule\s+", text)
    for chunk in chunks[1:]:
        lines = chunk.splitlines()
        rule_match = re.match(r"(\d+)", lines[0].strip())
        if not rule_match:
            continue
        signal = WorldSignal(rule=rule_match.group(1).zfill(5))

        def grab_line(name: str) -> str | None:
            m = re.search(rf"{re.escape(name)}:\s*(.+)", chunk)
            return m.group(1).strip() if m else None

        lifetime = grab_line("Lifetime")
        if lifetime:
            nums = re.findall(r"\d+", lifetime)
            if nums:
                signal.lifetime = int(nums[0])

        signal.classification = grab_line("Classification") or signal.classification

        dyn = grab_line("Dynamic score")
        if dyn:
            signal.dynamic_score = float(re.findall(r"[\d.]+", dyn)[0])

        breath = grab_line("Breathing score")
        if breath:
            signal.breathing_score = float(re.findall(r"[\d.]+", breath)[0])

        signal.collapse = grab_line("Collapse") or signal.collapse
        signal.objects = grab_line("Objects") or signal.objects

        events = grab_line("Events")
        if events:
            sm = re.search(r"split/birth=(\d+)", events)
            mm = re.search(r"merge/death=(\d+)", events)
            if sm:
                signal.split_birth = int(sm.group(1))
            if mm:
                signal.merge_death = int(mm.group(1))

        worlds.append(signal)

    return worlds


def priority_star(level: int) -> str:
    return "★" * level + "☆" * (5 - level)


def generate_questions(worlds: list[WorldSignal]) -> str:
    lines: list[str] = []
    lines.append("# Research Question Tracker")
    lines.append("")
    lines.append("Automatically generated from passport analysis.")
    lines.append("")

    if not worlds:
        lines.append("No world signals found.")
        return "\n".join(lines)

    lines.append("## High-priority questions")
    lines.append("")
    lines.append("| Priority | Rule | Question | Why it matters | Suggested test |")
    lines.append("| --- | --- | --- | --- | --- |")

    for w in worlds:
        if w.lifetime >= 100000 and w.dynamic_score >= 0.8:
            lines.append(
                f"| {priority_star(5)} | {w.rule} | Is this a true long-lived dynamic attractor? | "
                f"It survived {w.lifetime:,} ticks with dynamic score {w.dynamic_score:.3f}. | "
                "Run to 250k/1M ticks and compare morphology snapshots. |"
            )
            lines.append(
                f"| {priority_star(5)} | {w.rule} | What keeps object count bounded around {w.objects}? | "
                "Bounded object turnover suggests regulation rather than collapse or explosive growth. | "
                "Track object count distribution over time. |"
            )

        if w.split_birth + w.merge_death >= 20:
            lines.append(
                f"| {priority_star(4)} | {w.rule} | Are split/birth events reproduction-like or just fragmentation? | "
                f"Observed {w.split_birth} split/birth and {w.merge_death} merge/death events. | "
                "Add lineage tracking for objects across events. |"
            )

        if w.breathing_score >= 0.7:
            lines.append(
                f"| {priority_star(4)} | {w.rule} | Is the 'breathing' periodic, chaotic, or quasi-stable? | "
                f"Breathing score is {w.breathing_score:.3f}. | "
                "Record event intervals and run autocorrelation / cycle detection. |"
            )

    lines.append("")
    lines.append("## Working hypotheses")
    lines.append("")
    for w in worlds:
        if w.dynamic_score >= 0.8:
            lines.append(f"### H-{w.rule}-A: Dynamic morphological stability")
            lines.append("")
            lines.append(
                f"Rule **{w.rule}** may preserve global morphology while replacing local components. "
                f"Evidence: lifetime **{w.lifetime:,}**, dynamic score **{w.dynamic_score:.3f}**, "
                f"object range **{w.objects}**."
            )
            lines.append("")
        if w.split_birth > 0 and w.merge_death > 0:
            lines.append(f"### H-{w.rule}-B: Turnover regulation")
            lines.append("")
            lines.append(
                f"Rule **{w.rule}** may maintain a regulated object ecology through recurring split/merge turnover. "
                f"Evidence: split/birth **{w.split_birth}**, merge/death **{w.merge_death}**."
            )
            lines.append("")

    lines.append("## Next actions")
    lines.append("")
    lines.append("1. Save passports at 250k and 1M ticks if the world survives.")
    lines.append("2. Add morphology snapshots to compare visible structure over time.")
    lines.append("3. Add lineage tracking for split/birth and merge/death events.")
    ranked = sorted(worlds, key=lambda w: (w.dynamic_score, w.lifetime), reverse=True)
    comparison_ids = [w.rule for w in ranked[:5]]
    if len(comparison_ids) >= 2:
        lines.append(f"4. Compare the strongest current cohort: {', '.join(comparison_ids)}.")
    else:
        lines.append("4. Add more rules before running a cross-rule comparison.")
    lines.append("5. Feed results back into Notebook as confirmed / rejected hypotheses.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate research questions from Universe Search passport analysis.")
    parser.add_argument("input", help="passport_analysis.md, passport.md, or results folder")
    parser.add_argument("--out", default=None, help="Output markdown path")
    args = parser.parse_args()

    input_path = Path(args.input)
    source = find_input_file(input_path)
    text = read_text(source)
    worlds = parse_passport_analysis(text)

    md = generate_questions(worlds)

    if args.out:
        out = Path(args.out)
    elif input_path.is_dir():
        out = input_path / "research_questions.md"
    else:
        out = source.with_name("research_questions.md")

    out.write_text(md, encoding="utf-8")

    print("")
    print("=" * 58)
    print("Universe Search Question Tracker")
    print("=" * 58)
    print(f"Input:              {source}")
    print(f"Worlds parsed:      {len(worlds)}")
    print(f"Output:             {out}")
    print("-" * 58)

    for w in worlds:
        print(f"Rule {w.rule}: lifetime={w.lifetime}, dynamic={w.dynamic_score:.3f}, breathing={w.breathing_score:.3f}")
    print("-" * 58)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
